from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
from sqlalchemy import func
from db import get_db
from models import User, Folio, Scheme, Valuation, Transaction, AMC, StatementPeriod


