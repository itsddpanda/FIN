# file: cronrun.py
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import Base, SchemeMaster  # Import your models
# from routes.history import update_valuations_async  # Import the update function
from routes.history import update_allvaluations_async, get_hist_data  # Assuming you move it here

# Import the async engine and get_async_db from your existing db.py
from db import async_engine, get_async_db

from logging_config import logger  # Assuming you have this configured

async def main():
    """
    Gets an async session from the existing FastAPI setup and calls the 
    update function.
    """
    try:
        async for db in get_async_db():  # Use the existing dependency
            try:
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
                logger.error(f"Background task error: {e}", exc_info=True)
            await update_allvaluations_async(db)

    except Exception as e:
        logger.error(f"An error occurred in cronrun: {e}", exc_info=True)
        return  # Or take other appropriate action

    await async_engine.dispose()  # Properly close the engine

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())