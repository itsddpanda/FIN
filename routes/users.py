# File: routes/users.py
from ipaddress import ip_address
from math import log
from pickle import FALSE
from venv import logger
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging
import os
from db import get_db
from routes.pdf_converter import clear_database_for_identifier
from models import User, Folio, Scheme, AMC, Valuation
from schemas import UserOut, SchemeOut, PortfolioOut, FolioOut, AMCOut, SchemeDetailsOut, TransactionOut, ValuationOut, AMCWithSchemesOut
from auth import SECRET_KEY, ALGORITHM
from routes.pdf_converter import convertpdf, process_log_messages

router = APIRouter(prefix="/users", tags=["Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logger = logging.getLogger("users")

def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    # If middleware already set the user email, use it.
    if hasattr(request.state, "user_email") and request.state.user_email != "Anonymous":
        email = request.state.user_email
        logger.info("Got email from request")
    else:
        # Fallback: decode the token if for some reason the middleware didn't set it.
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            logger.info("Got email from JWT")
            if email is None:
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
    # Now, query the database using the email (as sub contains the email)
    try:
        user = db.query(User).filter(User.email == email).first()
        isactive = user.is_active
        if not user or not isactive:
            logger.info("User Record not found")
            return False
    except Exception as e:
        logger.error(f"Error in fetching user record: {e}", exc_info=False)
        return False
    # folios = db.query(Folio).join(User, Folio.user_id == User.user_id).filter(User.email == email).all()
    # if not folios:
    #     logger.info("User folio record not found; redirecting to /users/getstarted")
    #     # Return a RedirectResponse if the user is new (i.e. no record in DB)
    #     return JSONResponse(
    #             content={"detail": "Unauthorized. Please log in", "status" : "Error"},
    #             status_code=401
    #         )
    return user

# Endpoint to fetch current user details (if user exists)
@router.get("/me", response_model=UserOut)
def read_users_me(request: Request, current_user = Depends(get_current_user),):
    if isinstance(current_user, RedirectResponse):
        logger.info("User not found in database.")
        return JSONResponse(
        who = request.client.host,
        status_code=401,
        content=UserOut(email="no@e.mail", is_active=False, user_id="").model_dump(),
    )
    elif current_user is False: #check for false return value.
        logger.info("User not found in database.")
        return JSONResponse(
        who = request.client.host,
        status_code=401,
        content=UserOut(email="no@.mail", is_active=False, user_id="").model_dump(),
    )
    logger.info("User validated via /me endpoint.")
    current_user.user_id = "hidden response"
    return current_user

@router.post("/deleteme", response_model=UserOut)
def del_users_me(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    try:
        if clear_database_for_identifier(db, current_user.user_id, "user_id"):
            logger.info(f"User {current_user.full_name} deleted from database.")
            current_user.is_active = False
            current_user.user_id = "hidden response"
            return current_user
        else:
            logger.error(f"Unable to delete user {current_user.user_id} from database.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to delete user.")
    except Exception as e:
        logger.error(f"Unable to delete user {current_user.user_id} from database. Error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to delete user.")

# USER PROFILE ENDPOINT
@router.post("/uploading", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
    current_user = Depends(get_current_user)
):
    if current_user is False:
        return JSONResponse(
            who = request.client.host,
            status_code=401,
            content={"detail": "Unauthorized. Please log in", "status" : "Error"},
        )
    email = current_user.email 
    # Define the upload folder and ensure it exists.
    pwd = os.getcwd()
    UPLOAD_FOLDER = os.path.join(pwd, "upload")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    file_location = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_location, "wb") as f:
        content = await file.read()
        f.write(content)
    try:
        logger.info(f"Received file '{file.filename}' with provided password.")
        temp = convertpdf(file_location,password,email)
        response = process_log_messages (temp)
        html_content = f"<html><body><h1>{response}</h1></body></html>"
        return html_content
    except Exception as e:
        logger.info(f"Error in execution {e}")
        response = e
        html_content = f"<html><body><h1>{response}</h1></body></html>"
        return html_content

# API Endpoints
@router.get("/{user_id}/portfolio", response_model=PortfolioOut)
def get_portfolio(request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user is False:
        return JSONResponse(
            who = request.client.host,
            status_code=401,
            content={"detail": "Unauthorized. Please log in", "status" : "Error"},
        )
    logger.info(f"USER EMAIL: {request.state.user_email}")
    user_email = request.state.user_email
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    portfolio_value = 0.0
    total_investment = 0.0
    folios_out = []

    amc_valuations = {} # store amc data, to only do loop once.

    for folio in user.folios:
        amc = folio.amc
        amc_id = amc.id
        if amc_id not in amc_valuations:
            amc_valuations[amc_id] = {"valuation_value": 0.0, "valuation_cost": 0.0}

        for scheme in folio.schemes:
            if scheme.valuation:
                portfolio_value += scheme.valuation.valuation_value or 0.0
                total_investment += scheme.valuation.valuation_cost or 0.0
                amc_valuations[amc_id]["valuation_value"] += scheme.valuation.valuation_value or 0.0
                amc_valuations[amc_id]["valuation_cost"] += scheme.valuation.valuation_cost or 0.0

    for folio in user.folios:
        amc_id = folio.amc.id
        amc_data = amc_valuations[amc_id]
        gain_loss = amc_data["valuation_value"] - amc_data["valuation_cost"]
        gain_loss_percent = (gain_loss / amc_data["valuation_cost"]) * 100 if amc_data["valuation_cost"] else 0.0
        amc_out = AMCOut.model_validate(folio.amc)
        amc_out.valuation_value = amc_data["valuation_value"]
        amc_out.valuation_cost = amc_data["valuation_cost"]
        amc_out.gain_loss = gain_loss
        amc_out.gain_loss_percent = gain_loss_percent
        folios_out.append(FolioOut(folio_number=folio.folio_number, amc=amc_out))

    total_gain_loss = portfolio_value - total_investment
    total_gain_loss_percent = (total_gain_loss / total_investment) * 100 if total_investment else 0.0

    return PortfolioOut(
        folios=folios_out,
        portfolio_value=portfolio_value,
        total_investment=total_investment,
        total_gain_loss=total_gain_loss,
        total_gain_loss_percent=total_gain_loss_percent,
    )

@router.get("/schemes/{scheme_id}", response_model=SchemeDetailsOut)
def get_scheme_details(request: Request,scheme_id: int,current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user is False:
        raise JSONResponse(
            who = request.client.host,
            status_code=401,
            content={"detail": "Unauthorized. Please log in", "status" : "Error"},
        )
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    return SchemeDetailsOut(
        scheme=SchemeOut.model_validate(scheme),
        transactions=[TransactionOut.model_validate(transaction) for transaction in scheme.transactions],
    )

class AMCNotFoundException(Exception):
    """Custom exception for when an AMC is not found."""
    pass
@router.get("/amc/{amc_id}", response_model=AMCWithSchemesOut)
def get_amc_schemes_with_valuation(amc_id: int,request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)) -> AMCWithSchemesOut:
    """
    Retrieves schemes data for a given AMC, along with AMC valuation.

    Args:
        amc_id: The ID of the AMC.
        db: The database session (provided as a dependency).

    Returns:
        An AMCWithSchemesOut object containing AMC details and schemes.

    Raises:
        HTTPException: If the AMC is not found or a database error occurs.
    """
    try:
        amc = db.query(AMC).filter(AMC.id == amc_id).first()
        if not amc:
            logger.warning(f"AMC with ID {amc_id} not found.")
            raise HTTPException(status_code=404, detail=f"AMC with ID {amc_id} not found.")

        schemes = db.query(Scheme).filter(Scheme.amc_id == amc_id).all()

        scheme_outs = []
        total_valuation_value = 0.0
        total_valuation_cost = 0.0

        for scheme in schemes:
            valuation = db.query(Valuation).filter(Valuation.scheme_id == scheme.id).first()

            scheme_out = SchemeOut.model_validate(scheme)
            if valuation:
                valuation_out = ValuationOut.model_validate(valuation)
                scheme_out.valuation = valuation_out
                total_valuation_value += valuation.valuation_value or 0.0
                total_valuation_cost += valuation.valuation_cost or 0.0

            scheme_outs.append(scheme_out)

        gain_loss = total_valuation_value - total_valuation_cost
        gain_loss_percent = (gain_loss / total_valuation_cost) * 100 if total_valuation_cost else 0

        amc_out = AMCOut.model_validate(amc)
        amc_out.valuation_value = total_valuation_value
        amc_out.valuation_cost = total_valuation_cost
        amc_out.gain_loss = gain_loss
        amc_out.gain_loss_percent = gain_loss_percent

        logger.info(f"Retrieved AMC {amc_id} schemes with valuation.")
        return AMCWithSchemesOut(amc=amc_out, schemes=scheme_outs)

    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")