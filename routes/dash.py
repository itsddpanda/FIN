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
from schemas import UserOut, SchemeOut, PortfolioOut, FolioOut, AMCOut, SchemeDetailsOut, TransactionOut
import pandas as pd

load_dotenv()

router = APIRouter(prefix="/test", tags=["Test"])
DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger("DASH")


# API Endpoints
@router.get("/users/{user_id}/portfolio", response_model=PortfolioOut)
def get_portfolio(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
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
def get_scheme_details(scheme_id: int, db: Session = Depends(get_db)):
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    return SchemeDetailsOut(
        scheme=SchemeOut.model_validate(scheme),
        transactions=[TransactionOut.model_validate(transaction) for transaction in scheme.transactions],
    )


@router.post("/3")
def deldata(email:str):
    Session = SessionLocal()
    clear_database_for_identifier(Session, email, "email" )
