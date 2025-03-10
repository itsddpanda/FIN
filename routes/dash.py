from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
import logging
from models import User, Folio, Scheme, Transaction, Valuation
from db import SessionLocal
import os
from logging_config import logger
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
def get_user_dashboard(email: str):
    """
    Fetches user dashboard data based on email.

    :param email: User's email address.
    :return: JSON containing user details, folios, schemes, transactions, and valuations.
    """
    session = SessionLocal()
    
    try:
        # Fetch the user with related folios, schemes, transactions, and valuations
        user = (
            session.query(User)
            .options(
                joinedload(User.folios)
                .joinedload(Folio.schemes)
                .joinedload(Scheme.transactions)
            )
            .options(
                joinedload(User.folios)
                .joinedload(Folio.schemes)
                .joinedload(Scheme.valuation)
            )
            .filter(User.email == email)
            .first()
        )

        if not user:
            logger.warning(f"User not found: {email}")
            raise HTTPException(status_code=404, detail="User not found")

        # Construct response
        response = {
            "user_id": user.user_id,
            "email": user.email,
            "full_name": user.full_name,
            "folios": [
                {
                    "folio_number": folio.folio_number,
                    "amc": folio.amc,
                    "pan": folio.pan,
                    "schemes": [
                        {
                            "scheme_name": scheme.scheme_name,
                            "advisor": scheme.advisor,
                            "transactions": [
                                {
                                    "date": txn.transaction_date.isoformat() if txn.transaction_date else None,
                                    "description": txn.description,
                                    "amount": txn.amount,
                                    "units": txn.units,
                                    "nav": txn.nav,
                                    "balance": txn.balance,
                                    "type": txn.transaction_type,
                                    "dividend_rate": txn.dividend_rate,
                                }
                                for txn in scheme.transactions
                            ],
                            "valuation": {
                                "date": scheme.valuation.valuation_date.isoformat() if scheme.valuation and scheme.valuation.valuation_date else None,
                                "nav": scheme.valuation.valuation_nav if scheme.valuation else None,
                                "cost": scheme.valuation.valuation_cost if scheme.valuation else None,
                                "value": scheme.valuation.valuation_value if scheme.valuation else None,
                            } if scheme.valuation else None,
                        }
                        for scheme in folio.schemes
                    ],
                }
                for folio in user.folios
            ],
        }

        logger.info(f"User dashboard retrieved for {email}")
        return response

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error while fetching dashboard for {email}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

    finally:
        session.close()
