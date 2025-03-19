# File: routes/users.py
from decimal import Decimal
from typing import List
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.future import select
import uuid  # For generating unique filenames
from sqlalchemy import False_, func
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging
import os
from db import SessionLocal, get_db, AsyncSessionLocal, redis_client
from routes.pdf_converter import clear_database_for_identifier
from models import User, Folio, Scheme, StatementPeriod, SchemeMaster, SchemeNavHistory
from schemas import SchemeOut, PortfoliowithAMCOut, MetaData, AMCOut, SchemeDetailsOut,NavData,HistoricalDataResponse, TransactionOut, UserOut, ValuationOut, AMCWithSchemesOut, SchemeMasterOut, AMCWithValuationOut
from auth import SECRET_KEY, ALGORITHM
import time  # Import standard time module
from routes.pdf_converter import convertpdf
from .history import get_hist_data, update_allvaluations_async

router = APIRouter(prefix="/users", tags=["Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logger = logging.getLogger("users")

def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Retrieves the current user based on the provided token.

    Args:
        request: The incoming request object.
        token: The JWT token obtained from the Authorization header.
        db: The database session.

    Returns:
        The User object corresponding to the authenticated user.

    Raises:
        HTTPException:
            - 401 UNAUTHORIZED: If credentials could not be validated (e.g., invalid token, no email in token, user not found or inactive).
            - 500 INTERNAL SERVER ERROR: If any unexpected error occurs during user retrieval.
    """
    try:
        # 1. Get email from request state (if available)
        email = getattr(request.state, "user_email", None)
        if email == "Anonymous" or not email:
            # 2. Fallback: Decode the token
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                email = payload.get("sub")
                if not email:
                    logger.info("No email found in token payload.")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Could not validate credentials",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            except JWTError:
                logger.info("JWT error during token decoding.")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
    except HTTPException as http_exc:
            raise http_exc
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.is_active:
            logger.info(f"User with email {email} not found or inactive.")
            raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Please log in or ensure your account is active."
        )
        return user
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in fetching user record: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user"
        )

# Endpoint to fetch current user details (if user exists)
@router.get("/me", response_model=UserOut)
def read_users_me(request: Request, current_user: User = Depends(get_current_user)):
    """
    Retrieves the details of the currently authenticated user.

    Args:
        request: The incoming request object.
        current_user: The User object obtained from the get_current_user dependency.

    Returns:
        A UserOut object representing the current user's details.
    """
    return UserOut.model_validate(current_user)

@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp_time = payload.get("exp", int(time.time()))  # Default to now if missing
        remaining_ttl = max(exp_time - int(time.time()), 0)  # Calculate TTL
        # Store token in Redis blacklist
        redis_client.setex(f"blacklist:{token}", remaining_ttl, "revoked")

        return {"message": "Successfully logged out."}
    except HTTPException as http_exc:
        raise http_exc
    except JWTError:
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

@router.delete("/deleteme", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_data(token: str = Depends(oauth2_scheme),current_user: User=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Deletes all user-specific data and deactivates the user, using cascade deletion.
    """
    try:
        user = db.query(User).filter(User.email == current_user.email).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        # Delete StatementPeriod (cascades to Folio, Scheme, Valuation, Transaction)
        db.query(StatementPeriod).filter(StatementPeriod.user_id == user.user_id).delete(synchronize_session=False)
        # Deactivate the user
        user.is_active = False
        user.user_id = ""
        user.hashed_password = ""
        db.commit()
        db.flush()
        logout(token)
        logger.info(f"User data deleted and user deactivated for: {current_user.email}")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting user data: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

# USER PROFILE ENDPOINT
@router.post("/uploading", response_model=UserOut)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> UserOut:
    """
    Handles file uploads, processes the uploaded file, and initiates background tasks.

    Args:
        request: The incoming request.
        file: The uploaded file.
        password: The password provided for PDF access.
        current_user: The authenticated user.
        background_tasks: Background tasks manager.

    Returns:
        UserOut: Details of the current user.

    Raises:
        HTTPException:
            - 400 Bad Request: If the file type is invalid or other validation errors occur.
            - 401 Unauthorized: If the user is not authenticated.
            - 500 Internal Server Error: For any errors during file processing, PDF conversion, or background task initiation.
    """
    email = current_user.email
    try:
        # 1. Validate file type
        if file.content_type != "application/pdf":
            logger.error(f"Invalid file type: {file.content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only PDF files are allowed.",
            )
        # 2. Sanitize filename and define upload directory
        upload_dir = "upload"  # Define upload directory
        os.makedirs(upload_dir, exist_ok=True)  # Ensure directory exists
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"  # Generate unique filename
        file_location = os.path.join(upload_dir, unique_filename)

        # 3. Save the file
        logger.info(f"Saving uploaded file: {file.filename} to {file_location}")
        try:
            with open(file_location, "wb") as f:
                content = await file.read()
                f.write(content)
        except Exception as e:
            logger.error(f"Error saving file: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error saving uploaded file.",
            )
        # 4. Process the PDF (Ensure password is not logged)
        logger.info(f"Processing PDF file: {file_location}")
        try:
            convertpdf(file_location, password, email)  # Pass password directly
        except Exception as e:
            logger.error(f"Error processing PDF: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing PDF.",
            )

        # 5. Add background task (before convertpdf or handle errors explicitly)
        try:
            background_tasks.add_task(process_scheme_data, email)
            logger.info("Background task added successfully.")
        except Exception as e:
            logger.error(f"Error adding background task: {e}", exc_info=True)
            # Consider how to handle this - possibly log and continue or raise an exception
            # For now, logging and continuing
            # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error adding background task.")

        # 6. Return success
        logger.info(f"File '{file.filename}' processed successfully.")
        os.remove(file_location) # remove file uploaded
        return UserOut.model_validate(current_user)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error during file upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error during file upload.",
        )

# API Endpoints
@router.get("/portfolio", response_model=PortfoliowithAMCOut)
async def get_portfolio(includezerovalue: bool = False, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user.user_id
    # Fetch valid schemes (close_units > 0)
    if includezerovalue:
        valid_schemes = (
            db.query(Scheme)
            .join(Folio)
            .filter(Folio.user_id == user_id) #, Scheme.close_units > 0
            .all()
        )
    else:
        valid_schemes = (
            db.query(Scheme)
            .join(Folio)
            .filter(Folio.user_id == user_id, Scheme.close_units > 0)
            .all()
        )
    if not valid_schemes:
        raise HTTPException(status_code=404, detail="No valid schemes found")

    # Initialize portfolio totals
    total_valuation = Decimal(0)
    total_investment = Decimal(0)
    amc_valuations = {}
    transactions_list = []

    for scheme in valid_schemes:
        valuation = scheme.valuation
        if valuation:
            total_valuation += Decimal(valuation.valuation_value or 0)
            total_investment += Decimal(valuation.valuation_cost or 0)

            # Aggregate AMC-wise valuations
            amc_id = scheme.amc_id
            if amc_id not in amc_valuations:
                amc_valuations[amc_id] = {
                    "name": scheme.amc.amc_name,
                    "valuation_value": Decimal(0),
                    "valuation_cost": Decimal(0)
                }
            amc_valuations[amc_id]["valuation_value"] += Decimal(valuation.valuation_value or 0)
            amc_valuations[amc_id]["valuation_cost"] += Decimal(valuation.valuation_cost or 0)

        # Fetch transactions
        for txn in scheme.transactions:
            transaction_value = Decimal(txn.amount or 0)
            if txn.transaction_type in ["PURCHASE", "PURCHASE_SIP", "SWITCH_IN"]:
                transaction_value = -transaction_value
            transactions_list.append(
                TransactionOut(
                    transaction_date=txn.transaction_date,
                    description=txn.description,
                    amount=round(transaction_value, 4),
                    units=round(Decimal(txn.units or 0), 4),
                    nav=round(Decimal(txn.nav or 0), 4),
                    balance=round(Decimal(txn.balance or 0), 4),
                    transaction_type=txn.transaction_type,
                    dividend_rate=round(Decimal(txn.dividend_rate or 0), 4)
                )
            )

    # Compute gain/loss
    total_gain_loss = total_valuation - total_investment
    total_gain_loss_percent = (total_gain_loss / total_investment * 100) if total_investment > 0 else Decimal(0)

    # Prepare AMC output
    amc_output = [
        AMCWithValuationOut(
            id=amc_id,
            name=amc["name"],
            valuation_value=round(amc["valuation_value"], 4),
            valuation_cost=round(amc["valuation_cost"], 4),
            gain_loss=round(amc["valuation_value"] - amc["valuation_cost"], 4),
            gain_loss_percent=round((amc["valuation_value"] - amc["valuation_cost"]) / amc["valuation_cost"] * 100, 4) if amc["valuation_cost"] > 0 else Decimal(0),
        )
        for amc_id, amc in amc_valuations.items()
    ]

    return PortfoliowithAMCOut(
        portfolio_value=round(total_valuation, 4),
        total_investment=round(total_investment, 4),
        total_gain_loss=round(total_gain_loss, 4),
        total_gain_loss_percent=round(total_gain_loss_percent, 4),
        AMC=amc_output,
    )

@router.get("/amc/{amc_id}")
def get_amc_schemes(
    amc_id: int,
    exclude_zero_close_units: bool = False,  # Renamed for clarity
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[SchemeOut]:  # Specify return type for clarity
    """
    Retrieves schemes for a given AMC and user, with an option to exclude schemes with zero close units.

    Args:
        amc_id: The ID of the AMC.
        exclude_zero_close_units: If True, excludes schemes with close_units <= 0.
        db: The database session.
        current_user: The current user.

    Returns:
        A tuple containing the count of schemes and a list of SchemeOut objects.
    """
    # Build the base query
    query = db.query(Scheme).join(Folio, Scheme.folio_id == Folio.folio_number).filter(
        Folio.amc_id == amc_id, Folio.user_id == current_user.user_id
    )
    # Add the filter for close_units if exclude_zero_close_units is True
    if exclude_zero_close_units:
        query = query.filter(Scheme.close_units > 0)

    # Count the schemes
    count_query = db.query(func.count(Scheme.scheme_master_id.distinct())).join(
        Folio, Scheme.folio_id == Folio.folio_number
    ).filter(Folio.amc_id == amc_id, Folio.user_id == current_user.user_id)

    if exclude_zero_close_units:
        count_query = count_query.filter(Scheme.close_units > 0)

    count = count_query.scalar()

    # Retrieve the schemes
    schemes = query.all()

    # Convert Scheme objects to SchemeOut objects
    scheme_out_list = list()
    for scheme in schemes:
        scheme_master_out = SchemeMasterOut(
            id=scheme.scheme_master.scheme_id,
            isin=scheme.scheme_master.scheme_isin,
            amfi_code=scheme.scheme_master.scheme_amfi_code,
            name=scheme.scheme_master.scheme_name,
            amc_id=scheme.scheme_master.amc_id,
            scheme_type=scheme.scheme_master.scheme_type,
        )

        valuation_out = None
        if scheme.valuation:
            valuation_out = ValuationOut(
                valuation_date=scheme.valuation.valuation_date,
                valuation_nav=scheme.valuation.valuation_nav,
                valuation_cost=scheme.valuation.valuation_cost,
                valuation_value=scheme.valuation.valuation_value,
            )

        scheme_out = SchemeOut(
            id=scheme.id,
            folio_id=scheme.folio_id,
            scheme_master=scheme_master_out,
            advisor=scheme.advisor,
            rta_code=scheme.rta_code,
            rta=scheme.rta,
            nominees=scheme.nominees,
            open_units=scheme.open_units,
            close_units=scheme.close_units,
            close_calculated_units=scheme.close_calculated_units,
            valuation=valuation_out,
        )
        scheme_out_list.append(scheme_out)

    return scheme_out_list

@router.get("/schemes/{scheme_id}", response_model=SchemeDetailsOut)
def get_scheme_details(
    scheme_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # If you need user authentication
):
    """
    Retrieves a specific scheme along with its NAV history.

    Args:
        scheme_id: The ID of the scheme to retrieve.
        db: The database session.
        # current_user: The current user (if authentication is needed).

    Returns:
        A SchemeDetailsOut object containing the scheme and its NAV history.

    Raises:
        HTTPException: 404 if the scheme is not found.
    """

    # Retrieve the scheme
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()

    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    # Retrieve the NAV history for the scheme's master
    nav_history = db.query(SchemeNavHistory).filter(
        SchemeNavHistory.scheme_master_id == scheme.scheme_master_id
    ).all()

    # Construct the SchemeOut object
    scheme_master_out = SchemeMasterOut(
        id=scheme.scheme_master.scheme_id,
        isin=scheme.scheme_master.scheme_isin,
        amfi_code=scheme.scheme_master.scheme_amfi_code,
        name=scheme.scheme_master.scheme_name,
        amc_id=scheme.scheme_master.amc_id,
        scheme_type=scheme.scheme_master.scheme_type,
    )

    valuation_out = None
    if scheme.valuation:
        valuation_out = ValuationOut(
            valuation_date=scheme.valuation.valuation_date,
            valuation_nav=scheme.valuation.valuation_nav,
            valuation_cost=scheme.valuation.valuation_cost,
            valuation_value=scheme.valuation.valuation_value,
        )

    scheme_out = SchemeOut(
        id=scheme.id,
        folio_id=scheme.folio_id,
        scheme_master=scheme_master_out,
        advisor=scheme.advisor,
        rta_code=scheme.rta_code,
        rta=scheme.rta,
        nominees=scheme.nominees,
        open_units=scheme.open_units,
        close_units=scheme.close_units,
        close_calculated_units=scheme.close_calculated_units,
        valuation=valuation_out,
    )

    # Construct the SchemeDetailsOut object
    scheme_details_out = SchemeDetailsOut(
        scheme=scheme_out,
        nav_history=nav_history,
    )

    return scheme_details_out

async def process_scheme_data(email: str):
    """Processes scheme data asynchronously in the background for the user email"""
    logger.info(f"Starting scheme data processing for {email}")

    async with AsyncSessionLocal() as db:
        try:
            try:
                user = await db.execute(select(User).filter_by(email=email))
                user = user.scalars().first()

                if not user:
                    logger.error(f"User with email {email} not found.")
                    return  # Exit if user is not found
            except Exception as e:
                logger.error(f"User not found {email}: {e}", exc_info=True)

            # 2. Fetch schemes associated with the user
            # Construct a query that joins User, Folio, Scheme, and SchemeMaster
            query = select(SchemeMaster).join(
                Scheme, Scheme.scheme_master_id == SchemeMaster.scheme_id
            ).join(
                Folio, Scheme.folio_id == Folio.folio_number
            ).join(
                User, Folio.user_id == User.user_id
            ).where(
                User.email == email,
                SchemeMaster.scheme_amfi_code.isnot(None)  # Filter for valid AMFI codes
            )
            result = await db.execute(query)
            scheme_masters = result.scalars().all()  # Fetch SchemeMaster instead of Scheme

            tasks = []
            for scheme_master in scheme_masters:  # Iterate through SchemeMaster
                scheme_master_id, amfi_code = scheme_master.scheme_id, scheme_master.scheme_amfi_code
                if amfi_code:
                    tasks.append(get_hist_data(amfi_code, scheme_master_id))
                else:
                    logger.warning(f"No AMFI code for scheme_master_id: {scheme_master_id}")

            # 4. Execute all `get_hist_data` tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 5. Log any failures
            for scheme_master, result in zip(scheme_masters, results):  # zip with SchemeMaster
                if isinstance(result, Exception):
                    logger.error(f"Failed processing scheme_master_id {scheme_master.scheme_id}: {result}")

            # 6. Commit only if everything runs successfully
            await db.commit()
            

        except Exception as e:
            logger.error(f"Background task error for {email}: {e}", exc_info=True)
            await db.rollback()
        finally:
            logger.info("Updating NAV for all")
            try:
                await update_allvaluations_async(db)
            except Exception as e:
                logger.error(f"Error in updating valuation {e}", exc_info=False)  
                await db.rollback()     
            finally:
                await db.close() 

    logger.info(f"Finished processing scheme data for {email}")






    