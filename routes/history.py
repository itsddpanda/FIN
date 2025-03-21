# file: routes/history.py
import logging
from fastapi import Depends, HTTPException, status, APIRouter, Request
from models import Scheme, SchemeNavHistory, Valuation
from db import get_async_db,AsyncSessionLocal
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session, joinedload
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_
from sqlalchemy import func
import httpx

logger = logging.getLogger("history")
router = APIRouter(prefix="/test", tags=["test"])

async def save_scheme_nav_history(scheme_id: int, historical_data, db: AsyncSession):
    """Efficiently saves NAV history with bulk inserts and schema validation."""
    try:
        # Fetch correct scheme_master_id
        result = await db.execute(
            select(Scheme.scheme_master_id).where(Scheme.id == scheme_id)
        )
        scheme_master_id = result.scalar()
        logger.info(f"Scheme Master = {scheme_master_id} where scheme_id was {scheme_id}")
        if not scheme_master_id:
            raise HTTPException(status_code=400, detail="Invalid scheme_id")

        # Fetch existing NAV history for the given scheme_master_id
        existing_records = await db.execute(
            select(SchemeNavHistory.nav_date)
            .where(SchemeNavHistory.scheme_master_id == scheme_master_id)
        )
        existing_dates = set(existing_records.scalars().all())  # Convert to a set

        # Prepare bulk insert data
        nav_entries = []
        for nav_entry in historical_data["data"]:  # ✅ Corrected dictionary access
            nav_date = datetime.strptime(nav_entry["date"], "%d-%m-%Y").date()
            nav_value = float(nav_entry["nav"])

            if nav_date not in existing_dates:
                # logging.info(f"Adding {nav_date} ")
                nav_entries.append(SchemeNavHistory(
                    scheme_master_id=scheme_master_id,
                    nav_date=nav_date,
                    nav_value=nav_value
                ))

        if nav_entries:
            db.add_all(nav_entries)  # Alternative: Use `db.execute(insert(SchemeNavHistory), nav_entries)`
            await db.commit()
            logger.debug(f"Inserted {len(nav_entries)} records for scheme_master: {scheme_master_id}.")
        else:
            logger.info(f"DUPES not added for scheme_master: {scheme_master_id}")

    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving NAV history for scheme_id {scheme_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save NAV history")

async def get_hist_data(amfi_code: str, scheme_id: int):
    """Fetches NAV history for a scheme from AMFI API and saves it."""
    async with AsyncSessionLocal() as db:
        try:
            # Validate and fetch the correct scheme_master_id
            scheme_master_id = await db.execute(
                select(Scheme.scheme_master_id).where(Scheme.id == scheme_id)
            )
            scheme_master_id = scheme_master_id.scalar()
            if not scheme_master_id:
                raise HTTPException(status_code=400, detail="Invalid scheme_id")

            url = f"https://api.mfapi.in/mf/{amfi_code}"
            async with httpx.AsyncClient() as client:
                response = await client.get(url)

            # Validate API response
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch NAV history")
            # logger.info(f"Got response for {amfi_code}")
            data = response.json()
            if not data or "data" not in data:
                logger.error("Invalid response")
                raise HTTPException(status_code=400, detail="Invalid NAV data received")

            await save_scheme_nav_history(scheme_master_id, data, db)

        except Exception as e:
            logger.error(f"Error in get_hist_data for scheme_id {scheme_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

async def update_allvaluations_async(db: AsyncSession = Depends(get_async_db)):
    """
    Asynchronously updates the Valuation table based on SchemeNavHistory.

    Args:
        db: An asynchronous database session.
    """
    try:
        # 1. Fetch all Schemes
        logger.info("Starting with Scheme valuation")
        query = select(Scheme)  # Remove joinedload
        result = await db.execute(query)
        schemes: List[Scheme] = result.scalars().all()

        for scheme in schemes:
            # 2. Get the latest nav_date from SchemeNavHistory for the scheme's master
            subquery = (
                select(func.max(SchemeNavHistory.nav_date))
                .filter(SchemeNavHistory.scheme_master_id == scheme.scheme_master_id)
                .scalar_subquery()
            )
            query = select(SchemeNavHistory).filter(
                SchemeNavHistory.scheme_master_id == scheme.scheme_master_id,
                SchemeNavHistory.nav_date == subquery
            )
            result = await db.execute(query)
            latest_nav_history = result.scalars().first()
            logger.info("Fetching NAV History")
            if latest_nav_history:
                # 3. Fetch the latest Valuation
                valuation_query = select(Valuation).filter(Valuation.scheme_id == scheme.id)
                valuation_result = await db.execute(valuation_query)
                scheme.valuation = valuation_result.scalars().first()

                # 4. Compare dates and update Valuation
                if (
                    scheme.valuation is not None and
                    latest_nav_history.nav_date > scheme.valuation.valuation_date
                ):
                    logger.info(f"For Scheme {scheme.id} Latest: {latest_nav_history.nav_date} is newer than {scheme.valuation.valuation_date}")
                    scheme.valuation.valuation_date = latest_nav_history.nav_date
                    scheme.valuation.valuation_nav = float(latest_nav_history.nav_value)
                    # Valuation cost remains unchanged
                    scheme.valuation.valuation_value = scheme.close_units * scheme.valuation.valuation_nav
                    db.add(scheme.valuation)
                    # change below to debug for prod
                    logger.info(
                        f"Updated valuation for scheme_id: {scheme.id} to "
                        f"date: {scheme.valuation.valuation_date}, "
                        f"nav: {scheme.valuation.valuation_nav}, "
                        f"close units: {scheme.close_units}, "
                        f"value: {scheme.valuation.valuation_value}"
                    )
                else:
                    logger.info(
                        f"No valuation update needed for scheme_id: {scheme.id}."
                    )
            else:
                logger.warning(
                    f"No NAV history found for scheme_master_id: {scheme.scheme_master_id}"
                )

        await db.commit()
        logger.info("Valuation updates completed.")

    except Exception as e:
        logger.error(f"Error updating valuations: {e}", exc_info=True)
        await db.rollback()
        raise
    finally:
        await db.close()