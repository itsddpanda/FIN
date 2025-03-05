# File: routes/pdf_converter.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging
import os
from db import get_db
from models import User, Folio
from schemas import UserOut
from auth import SECRET_KEY, ALGORITHM
import jsonify

#router = APIRouter(prefix="/")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logger_module = logging.getLogger(__name__)

import casparser
import os
from dotenv import load_dotenv

def convertpdf(pdf_file_path, password, userid):
    """
    Converts a CAS PDF to CSV data.

    Args:
        pdf_file_path (str): The path to the CAS PDF file.
        password (str): The password for the CAS PDF file.

    Returns:
        str: The CSV data as a string, or None if an error occurs.
    """
    try:
        logger_module.debug(f"Converting {pdf_file_path}")
        csv_str = casparser.read_cas_pdf(pdf_file_path, password, output="json")
        logger_module.info(f"File Converted")
        return csv_str
    except Exception as e:
        logger_module.error(f"Conversion PDF PARSER Module FAILED. {e}", exc_info=False)
        # Log the error for debugging
        return e



