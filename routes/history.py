import logging
from fastapi import Depends, HTTPException, status
from schemas import HistoricalDataResponse
from models import Scheme, SchemeNavHistory
from db import get_async_db,AsyncSessionLocal
from datetime import datetime
import asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_
import httpx

logger = logging.getLogger("history")

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
            logger.info(f"Inserted {len(nav_entries)} records for scheme_master: {scheme_master_id}.")
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

            # Call save function
            # logger.info("Calling Save Scheme NAV")
            await save_scheme_nav_history(scheme_master_id, data, db)

        except Exception as e:
            logger.error(f"Error in get_hist_data for scheme_id {scheme_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

