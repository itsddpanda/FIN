# file: history.py
import requests
import logging
from fastapi import Depends, HTTPException, status
from schemas import HistoricalDataResponse
from models import SchemeNavHistory
from db import get_db
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import exists, and_

logger = logging.getLogger("history")

def save_scheme_nav_history(scheme_id: int, historical_data, db: Session = Depends(get_db)):
    """Saves the scheme NAV history to the database."""
    try:
        for nav_entry in historical_data.data:
            nav_date = datetime.strptime(nav_entry.date, "%d-%m-%Y").date()
            nav_value = float(nav_entry.nav)

            # Check for existing record
            existing_record = db.query(exists().where(and_(
                SchemeNavHistory.scheme_id == scheme_id,
                SchemeNavHistory.nav_date == nav_date
            ))).scalar()

            if not existing_record:
                nav_history_entry = SchemeNavHistory(
                    scheme_id=scheme_id,
                    nav_date=nav_date,
                    nav_value=nav_value,
                )
                db.add(nav_history_entry)

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

async def get_hist_data(amfi_code: str, scheme_id: int) -> HistoricalDataResponse:
    URL = f"https://api.mfapi.in/mf/{amfi_code}"
    try:
        logger.info(f"Fetching Historical Data for {amfi_code} ")
        response = requests.get(URL)
        response.raise_for_status()  # Check for HTTP errors

        data = response.json()
        historical_data = HistoricalDataResponse(**data) # Validate with Pydantic

        if historical_data.status != "SUCCESS":
            logger.error(f"External API returned non-success status for amfi_code: {amfi_code}. Status: {historical_data.status}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="External API returned non-success status")
        save_scheme_nav_history(scheme_id, historical_data)
        return historical_data

    except requests.RequestException as e:
        logger.error(f"Error fetching data from {URL}: {e}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching data from external API")
    except ValueError as e: # Handle JSON decoding errors
        logger.error(f"Error decoding JSON from {URL}: {e}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error decoding JSON from external API")
    except Exception as e: # Handle any other exception.
        logger.error(f"Unexpected error from {URL}: {e}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error from external API")
    

