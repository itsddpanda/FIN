import logging
from pytest import Session
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, Depends, APIRouter
from models import User, Folio, Scheme, Transaction, Valuation
from db import SessionLocal
from routes.pdf_converter import clear_database_for_identifier
import os
from dotenv import load_dotenv
from db import get_db
from schemas import UserOut
import pandas as pd

load_dotenv()

router = APIRouter(prefix="/test", tags=["Test"])
DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger("DASH")



@router.post("/deleteme", response_model=UserOut)
def deldata(email:str):
    
    try:
        Session = SessionLocal()
        user = clear_database_for_identifier(Session, email, "email" )
        logger.info("User Deleted from Database")
        return user
    except Exception as e:
        logger.error(f"Unable to Delete {email} from Database check Error: {e}")
    finally:
        Session.close() 
