# File: routes/users.py
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form, BackgroundTasks
from pydantic import EmailStr
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.future import select
import uuid  # For generating unique filenames
from sqlalchemy.exc import SQLAlchemyError
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging
import os
from db import SessionLocal, get_db, AsyncSessionLocal  
from routes.pdf_converter import clear_database_for_identifier
from models import User, Folio, Scheme, AMC, Valuation, SchemeMaster
from schemas import HistoricalDataOut, SchemeOut, PortfolioOut, FolioOut, AMCOut, SchemeDetailsOut, TransactionOut, UserOut, ValuationOut, AMCWithSchemesOut, SchemeMasterOut
from auth import SECRET_KEY, ALGORITHM
from routes.pdf_converter import convertpdf
from .history import get_hist_data, save_scheme_nav_history

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
        # 3. Validate email format
    # try:
    #     EmailStr(email)
    # except ValueError:
    #     logger.error(f"Invalid email format: {email}")
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Invalid email format"
    #     )
    # 4. Query the database
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

@router.post("/deleteme", response_model=UserOut)
def del_users_me(request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if isinstance(current_user, UserOut):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Please log in or ensure your account is active."
        )
    try:
        if clear_database_for_identifier(db, current_user.user_id, "user_id"):
            logger.info(f"User {current_user.full_name} deleted from database.")
            current_user.is_active = False
            # current_user.user_id = "hidden response"
            return UserOut.model_validate(current_user)
        else:
            logger.error(f"Unable to delete user {current_user.user_id} from database.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to delete user.")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Unable to delete user from database. Error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to delete user.")

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
@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio(request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if not isinstance(current_user, User):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Please log in or ensure your account is active."
        )
    logger.info(f"USER EMAIL: {current_user.email}")
    portfolio_value = 0.0
    total_investment = 0.0
    folios_out = []
    amc_valuations = {}

    # Optimized Query to Reduce Database Calls
    folios = db.query(Folio)\
        .filter(Folio.user_id == current_user.user_id)\
        .options(joinedload(Folio.schemes).joinedload(Scheme.valuation))\
        .all()

    for folio in folios:
        amc = folio.amc
        amc_id = amc.id

        if amc_id not in amc_valuations:
            amc_valuations[amc_id] = {"valuation_value": 0.0, "valuation_cost": 0.0}

        for scheme in folio.schemes:
            if scheme.valuation:
                valuation_value = scheme.valuation.valuation_value or 0.0
                valuation_cost = scheme.valuation.valuation_cost or 0.0
                portfolio_value += valuation_value
                total_investment += valuation_cost
                amc_valuations[amc_id]["valuation_value"] += valuation_value
                amc_valuations[amc_id]["valuation_cost"] += valuation_cost

        # Compute AMC Summary
        amc_data = amc_valuations[amc_id]
        gain_loss = amc_data["valuation_value"] - amc_data["valuation_cost"]
        gain_loss_percent = (gain_loss / amc_data["valuation_cost"] * 100) if amc_data["valuation_cost"] else 0.0

        amc_out = AMCOut(
            id=amc.id,
            name=amc.name,
            valuation_value=amc_data["valuation_value"],
            valuation_cost=amc_data["valuation_cost"],
            gain_loss=gain_loss,
            gain_loss_percent=gain_loss_percent
        )

        folios_out.append(FolioOut(folio_number=folio.folio_number, amc=amc_out))

    total_gain_loss = portfolio_value - total_investment
    total_gain_loss_percent = (total_gain_loss / total_investment * 100) if total_investment else 0.0

    return PortfolioOut(
        folios=folios_out,
        portfolio_value=portfolio_value,
        total_investment=total_investment,
        total_gain_loss=total_gain_loss,
        total_gain_loss_percent=total_gain_loss_percent,
    )

@router.get("/schemes/{scheme_id}", response_model=SchemeDetailsOut)
async def get_scheme_details(
    request: Request,
    scheme_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if isinstance(current_user, UserOut):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Please log in or ensure your account is active.",
        )

    scheme = (
        db.query(Scheme)
        .filter(Scheme.id == scheme_id)
        .options(
            joinedload(Scheme.scheme_master),
            joinedload(Scheme.transactions),
        )
        .first()
    )

    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    if not scheme.scheme_master:
        logger.error(f"Scheme Master not found for scheme_id {scheme_id}")
        raise HTTPException(status_code=500, detail="Scheme master not found")

    scheme_data = scheme.__dict__
    scheme_data["scheme_name"] = scheme.scheme_master.scheme_name
    scheme_out = SchemeOut.model_validate(scheme_data)

    # Historical Data Fetching
    historical_data = None
    amfi_code = scheme.scheme_master.scheme_amfi_code if scheme.scheme_master else None
    if amfi_code:
        try:
            hist_data = await get_hist_data(amfi_code, scheme_id)
            historical_data = HistoricalDataOut(data=hist_data)
        except HTTPException as e:
            logger.error(f"Error getting historical data for scheme_id {scheme_id}: {e.detail}")
    else:
        logger.warning(f"No AMFI code for scheme_id {scheme_id}, skipping historical data")

    return SchemeDetailsOut(
        scheme=scheme_out,
        transactions=[
            TransactionOut.model_validate(transaction) for transaction in scheme.transactions or []
        ],
        historical_data=historical_data,
    )

class AMCNotFoundException(Exception):
    """Custom exception for when an AMC is not found."""
    pass
@router.get("/amc/{amc_id}", response_model=AMCWithSchemesOut)
def get_amc_schemes_with_valuation(
    amc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
) -> AMCWithSchemesOut:
    """
    Retrieves schemes data for a given AMC, along with AMC valuation.
    """

    if not isinstance(current_user, User):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Please log in or ensure your account is active."
        )

    try:
        # Fetch AMC
        amc = db.query(AMC).filter(AMC.id == amc_id).first()
        if not amc:
            logger.warning(f"AMC with ID {amc_id} not found.")
            raise HTTPException(status_code=404, detail=f"AMC with ID {amc_id} not found.")

        # Fetch schemes linked to the user's folios for the given AMC
        schemes = (
            db.query(Scheme)
            .join(Folio)
            .filter(Folio.user_id == current_user.user_id, Scheme.amc_id == amc_id)
            .options(
                joinedload(Scheme.valuation),
                joinedload(Scheme.scheme_master)  # ✅ Preload SchemeMaster for related fields
            )
            .all()
        )

        total_valuation_value = 0.0
        total_valuation_cost = 0.0

        scheme_outs = [
            SchemeOut(
                id=scheme.id,
                folio_id=scheme.folio_id,
                amc_id=scheme.amc_id,
                scheme_master_id=scheme.scheme_master_id,
                scheme_master=SchemeMasterOut.model_validate(scheme.scheme_master) if scheme.scheme_master else None,
                advisor=scheme.advisor,
                rta_code=scheme.rta_code,
                rta=scheme.rta,
                nominees=scheme.nominees,
                open_units=scheme.open_units,
                close_units=scheme.close_units,
                close_calculated_units=scheme.close_calculated_units,
                valuation=ValuationOut.model_validate(scheme.valuation) if scheme.valuation else None
            )
            for scheme in schemes
        ]

        # Calculate total valuation values
        total_valuation_value = sum(s.valuation.valuation_value or 0.0 for s in schemes if s.valuation)
        total_valuation_cost = sum(s.valuation.valuation_cost or 0.0 for s in schemes if s.valuation)

        gain_loss = total_valuation_value - total_valuation_cost
        gain_loss_percent = (gain_loss / total_valuation_cost * 100) if total_valuation_cost else 0.0

        amc_out = AMCOut(
            id=amc.id,
            name=amc.name,
            valuation_value=total_valuation_value,
            valuation_cost=total_valuation_cost,
            gain_loss=gain_loss,
            gain_loss_percent=gain_loss_percent
        )

        logger.info(f"Retrieved AMC {amc_id} schemes for user {current_user.user_id}.")
        return AMCWithSchemesOut(amc=amc_out, schemes=scheme_outs)

    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred.")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

async def process_scheme_data(email: str):
    """Processes scheme data asynchronously in the background."""
    logger.info(f"Starting scheme data processing for {email}")

    async with AsyncSessionLocal() as db:
        try:
            # Fetch schemes with valid AMFI codes
            result = await db.execute(select(SchemeMaster).where(SchemeMaster.scheme_amfi_code.isnot(None)))
            schemes = result.scalars().all()

            # Run all tasks concurrently
            tasks = []
            for scheme in schemes:
                scheme_master_id, amfi_code = scheme.scheme_id, scheme.scheme_amfi_code
                if amfi_code:
                    tasks.append(get_hist_data(amfi_code, scheme_master_id))
                else:
                    logger.warning(f"No AMFI code for scheme_master_id: {scheme_master_id}")

            # Execute all `get_hist_data` tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any failures
            for scheme, result in zip(schemes, results):
                if isinstance(result, Exception):
                    logger.error(f"Failed processing scheme_master_id {scheme.scheme_id}: {result}")

            # ✅ Commit only if everything runs successfully
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(f"Background task error for {email}: {e}", exc_info=True)

    logger.info(f"Finished processing scheme data for {email}")






    