# File: routes/pdf_converter.py
import json
import logging
from datetime import datetime
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import delete, update
import casparser
from typing import Dict, Any, List, Optional
from sqlalchemy.exc import SQLAlchemyError
import os
from datetime import datetime, date
from decimal import Decimal
from models import User, Folio, StatementPeriod, Scheme, Valuation, Transaction, AMC, SchemeMaster, SchemeNavHistory
from schemas import TransactionType
from db import SessionLocal, get_db

# from logging_config import logger 
logger = logging.getLogger("PDF")
class ProgressHandler(logging.Handler):
    """
    A custom logging handler that appends log messages to a progress report list.
    """
    def __init__(self, progress_report):
        super().__init__()
        self.progress_report = progress_report

    def emit(self, record):
        log_message = self.format(record)
        self.progress_report.append(log_message)

# Create and add the custom logging handler
progress_report = []
success = True
progress_handler = ProgressHandler(progress_report)

# Set formatter for the custom handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
progress_handler.setFormatter(formatter)

# Attach custom handler to the logger
logger.addHandler(progress_handler)
logger.info("PDF Converter initialized with custom progress handler")

def clear_database_for_identifier(db: Session, identifier: str, identifier_type: str = "user_id"):
    """
    Clears all database records associated with a user, identified by either user_id or email,
    ensuring all deletions are user-specific.

    Args:
        db: SQLAlchemy Session object.
        identifier: The user_id or email address.
        identifier_type: Specifies whether the identifier is "user_id" or "email". Defaults to "user_id".
    """
    user_id = None
    user = ""
    try:
        logger.info("Starting to clean database.")
        if identifier_type == "user_id":
            user_id = identifier
            logger.info(f"Using user identification as: {identifier}")
        elif identifier_type == "email":
            user = db.query(User).filter(User.email == identifier).first()
            if user:
                user_id = user.user_id
                logger.info(f"Found user_id {user_id} for email {identifier}")
            else:
                logger.info(f"No user found with email: {identifier}")
                return
        else:
            raise ValueError("identifier_type must be 'user_id' or 'email'")

        if not user_id:
            logger.info("User ID not found, exiting deletion.")
            return

        # 1. Retrieve all folios for the user.
        logger.info("Retrieving folios for deletion.")
        user_folios = db.query(Folio).filter(Folio.user_id == user_id).all()
        folio_numbers = [folio.folio_number for folio in user_folios]
        statement_period_ids = [folio.statement_period_id for folio in user_folios]
        logger.info("Folios Deleted.")
        # 2. Delete Transactions for schemes associated with these folios.
        scheme_ids = [
            scheme.id for scheme in db.query(Scheme).filter(Scheme.folio_id.in_(folio_numbers)).all()
        ]
        db.execute(delete(Transaction).where(Transaction.scheme_id.in_(scheme_ids)))
        logger.info(f"Transactions deleted for user {user_id}")

        # 3. Delete Valuations for those schemes.
        db.execute(delete(Valuation).where(Valuation.scheme_id.in_(scheme_ids)))
        logger.info(f"Valuations deleted for user {user_id}")

        # 4. Delete Schemes associated with these folios.
        db.execute(delete(Scheme).where(Scheme.folio_id.in_(folio_numbers)))
        logger.info(f"Schemes deleted for user {user_id}")

        # 5. Delete Folios for the user.
        db.execute(delete(Folio).where(Folio.user_id == user_id))
        logger.info(f"Folios deleted for user {user_id}")

        # 6. Delete StatementPeriods that belong to the user and are no longer referenced by any folio.
        for sp_id in set(statement_period_ids):
            # Check if any folios remain associated with this statement period for this user.
            folio_exists = db.query(Folio).filter(
                Folio.statement_period_id == sp_id,
                Folio.user_id == user_id
            ).first()
            if not folio_exists:
                db.execute(
                    delete(StatementPeriod).where(
                        StatementPeriod.id == sp_id,
                        StatementPeriod.user_id == user_id
                    )
                )
                logger.info(f"StatementPeriod {sp_id} deleted for user {user_id}")
        logger.info(f"StatementPeriods cleanup completed for user {user_id}")

        # 7. Finally, is_active is false for the user record.
        db.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(is_active=False)
        )
        logger.info(f"User {user_id} Deactivated")

        db.commit()
        logger.info(f"Database cleared for {identifier_type}: {identifier}, user: {user}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing database for {identifier}: {e}", exc_info=False)
        raise

def publish_json_to_db(data: Dict[str, Any], email: str, db: Session) -> bool:
    """
    Adds data from parsed JSON to the database.

    Args:
        data: A dictionary containing the parsed JSON data.
        email: The email of the user uploading the data.
        db:   The database session.

    Returns:
        True if the data was successfully added to the database, False otherwise.
    """

    def parse_date(date_str: str) -> Optional[date]:
        """Helper function to parse dates in multiple formats."""
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%b-%d", "%d-%b-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        raise ValueError(f"Unrecognized date format: {date_str}")

    try:
        # 1. Extract and validate statement period
        sp_data = data.get("statement_period")
        if not sp_data:
            raise ValueError("Missing 'statement_period' in JSON data.")
        new_sp_from = parse_date(sp_data.get("from"))
        new_sp_to = parse_date(sp_data.get("to"))

        if not new_sp_from or not new_sp_to:
            raise ValueError("Invalid date format for statement period.")

        # 2. Get investor details
        investor_info = data.get("investor_info", {})
        name = investor_info.get("name")
        mobile = investor_info.get("mobile")
        address = investor_info.get("address")

        if not email:
            raise ValueError("Investor email is missing.")

        # 3. Fetch user from DB
        user = db.query(User).filter_by(email=email).first()
        if not user:
            raise ValueError(f"User with email '{email}' not found.")

        # 4. Update user details if missing
        if not user.full_name and name:
            user.full_name = name
        if not user.mobile and mobile:
            user.mobile = mobile
        if not user.address and address:
            user.address = address

        db.add(user)

        # 5. Process folios
        folios_data: List[Dict[str, Any]] = data.get("folios",)  # type: ignore
        for folio_data in folios_data:
            folio_number = folio_data.get("folio")
            pan = folio_data.get("PAN")
            amc_name = folio_data.get("amc")
            # kyc_status = folio_data.get("KYC")
            # pan_kyc_status = folio_data.get("PANKYC")

            if not folio_number or not amc_name:
                logger.warning(f"Skipping invalid folio: {folio_data}")
                continue

            # 6. Ensure AMC exists
            try:
                amc_obj = db.query(AMC).filter_by(amc_name=amc_name).first()
                if not amc_obj:
                    amc_obj = AMC(amc_name=amc_name)
                    db.add(amc_obj)
                    db.flush()  # Get amc_obj.amc_id
            except SQLAlchemyError as e:
                logger.error(f"Error fetching/creating AMC: {e}", exc_info=True)
                raise

            # 7. Check if folio exists
            existing_folio = db.query(Folio).filter_by(
                folio_number=folio_number, user_id=user.user_id
            ).first()

            # 8. Ensure statement period exists
            sp = db.query(StatementPeriod).filter_by(
                from_date=new_sp_from, to_date=new_sp_to, user_id=user.user_id
            ).first()
            if not sp:
                sp = StatementPeriod(from_date=new_sp_from, to_date=new_sp_to, user_id=user.user_id)
                db.add(sp)
                db.flush()  # Get sp.id

            if not existing_folio:
                folio_obj = Folio(
                    folio_number=folio_number,
                    pan=pan,
                    statement_period_id=sp.id,  # Use sp.id
                    user_id=user.user_id,
                    amc_id=amc_obj.amc_id,  # Use amc_obj.amc_id
                    # kyc_status=kyc_status,
                    # pan_kyc_status=pan_kyc_status,
                )
                db.add(folio_obj)
            else:
                folio_obj = existing_folio
                # Update statement period range if necessary
                if new_sp_from < sp.from_date or new_sp_to > sp.to_date:
                    sp.from_date = min(sp.from_date, new_sp_from)
                    sp.to_date = max(sp.to_date, new_sp_to)
                    db.add(sp)

            # 9. Process schemes
            schemes_data: List[Dict[str, Any]] = folio_data.get("schemes",)  # type: ignore
            for scheme_data in schemes_data:
                scheme_name = scheme_data.get("scheme")
                scheme_isin = scheme_data.get("isin")
                scheme_amfi = scheme_data.get("amfi")
                scheme_advisor = scheme_data.get("advisor")
                scheme_rta_code = scheme_data.get("rta_code")
                scheme_rta = scheme_data.get("rta")
                scheme_type = scheme_data.get("type")
                scheme_nominees = scheme_data.get("nominees")
                scheme_open = scheme_data.get("open")
                scheme_close = scheme_data.get("close")
                scheme_close_calculated = scheme_data.get("close_calculated")

                if not (scheme_isin or scheme_amfi):
                    logger.warning(f"Skipping scheme with missing isin/amfi: {scheme_data}")
                    continue

                # 10. Ensure SchemeMaster exists (with amc_id check)
                try:
                    scheme_master = db.query(SchemeMaster).filter_by(
                        scheme_isin=scheme_isin, amc_id=amc_obj.amc_id
                    ).first()
                    if not scheme_master:
                        scheme_master = SchemeMaster(
                            scheme_name=scheme_name,
                            scheme_isin=scheme_isin,
                            scheme_amfi_code=scheme_amfi,
                            amc_id=amc_obj.amc_id,  # Use amc_id
                            scheme_type=scheme_type,
                        )
                        db.add(scheme_master)
                        db.flush()  # Get scheme_master.scheme_id
                except SQLAlchemyError as e:
                    logger.error(f"Error fetching/creating SchemeMaster: {e}", exc_info=True)
                    raise

                # 11. Check if scheme exists
                try:
                    existing_scheme = db.query(Scheme).filter_by(
                        folio_id=folio_obj.folio_number,
                        scheme_master_id=scheme_master.scheme_id,  # Use scheme_master.scheme_id
                    ).first()
                    if not existing_scheme:
                        scheme_obj = Scheme(
                            folio_id=folio_obj.folio_number,  # Use folio_obj.folio_number
                            amc_id=amc_obj.amc_id,
                            scheme_master_id=scheme_master.scheme_id,
                            advisor=scheme_advisor,
                            rta_code=scheme_rta_code,
                            rta=scheme_rta,
                            nominees=scheme_nominees,
                            open_units=scheme_open,
                            close_units=scheme_close,
                            close_calculated_units=scheme_close_calculated,
                        )
                        db.add(scheme_obj)
                        db.flush()  # Get scheme_obj.id
                    else:
                        scheme_obj = existing_scheme
                except SQLAlchemyError as e:
                    logger.error(f"Error fetching/creating Scheme: {e}", exc_info=True)
                    raise

                # 12. Process valuation
                valuation_data = scheme_data.get("valuation")
                if valuation_data:
                    valuation_date_str = valuation_data.get("date")
                    valuation_date = parse_date(valuation_date_str) if valuation_date_str else None
                    valuation_nav = valuation_data.get("nav")
                    valuation_value = valuation_data.get("value")
                    valuation_cost = valuation_data.get("cost")

                    if not valuation_date:
                        logger.warning(f"Skipping valuation with invalid date: {valuation_data}")
                        continue

                    try:
                        existing_valuation = db.query(Valuation).filter_by(
                            scheme_id=scheme_obj.id
                        ).first()
                        if existing_valuation:
                            existing_valuation.valuation_date = valuation_date
                            existing_valuation.valuation_nav = (
                                Decimal(str(valuation_nav)) if valuation_nav is not None else None
                            )
                            existing_valuation.valuation_value = (
                                Decimal(str(valuation_value)) if valuation_value is not None else None
                            )
                            existing_valuation.valuation_cost = (
                                Decimal(str(valuation_cost)) if valuation_cost is not None else None
                            )
                            db.add(existing_valuation)
                        else:
                            valuation_obj = Valuation(
                                scheme_id=scheme_obj.id,
                                valuation_date=valuation_date,
                                valuation_nav=Decimal(str(valuation_nav)) if valuation_nav is not None else None,
                                valuation_value=Decimal(str(valuation_value)) if valuation_value is not None else None,
                                valuation_cost=Decimal(str(valuation_cost)) if valuation_cost is not None else None,
                            )
                            db.add(valuation_obj)
                    except SQLAlchemyError as e:
                        logger.error(f"Error handling valuation: {e}", exc_info=True)
                        raise

                # 13. Process transactions
                transactions_data: List[Dict[str, Any]] = scheme_data.get("transactions",)  # type: ignore
                for txn_data in transactions_data:
                    txn_date_str = txn_data.get("date")
                    txn_date = parse_date(txn_date_str) if txn_date_str else None
                    txn_description = txn_data.get("description")
                    txn_amount = txn_data.get("amount")
                    txn_units = txn_data.get("units")
                    txn_nav = txn_data.get("nav")
                    txn_balance = txn_data.get("balance")
                    txn_type = txn_data.get("type")
                    txn_dividend_rate = txn_data.get("dividend_rate")

                    if not txn_date:
                        logger.warning(f"Skipping transaction with invalid date: {txn_data}")
                        continue

                    # 14. Transaction Type Validation
                    try:
                        transaction_type = TransactionType(txn_type) if txn_type else None
                    except ValueError:
                        logger.error(f"Invalid transaction type: {txn_type}")
                        raise ValueError(f"Invalid transaction type: {txn_type}")

                    # 15. Dividend Rate Validation
                    if transaction_type in (TransactionType.DIVIDEND_PAYOUT, TransactionType.DIVIDEND_REINVESTMENT):
                        if txn_dividend_rate is None:
                            logger.error("dividend_rate is required for DIVIDEND transactions")
                            raise ValueError("dividend_rate is required for DIVIDEND transactions")
                    else:
                        if txn_dividend_rate is not None:
                            logger.warning("dividend_rate should be None for non-DIVIDEND transactions")

                    # 16. Check for duplicate transactions (simplified example)
                    try:
                        existing_txn = db.query(Transaction).filter_by(
                            scheme_id=scheme_obj.id,
                            transaction_date=txn_date,
                            amount=Decimal(str(txn_amount)) if txn_amount is not None else None,
                            units=Decimal(str(txn_units)) if txn_units is not None else None,
                        ).first()
                        if not existing_txn:
                            txn_obj = Transaction(
                                scheme_id=scheme_obj.id,
                                transaction_date=txn_date,
                                description=txn_description,
                                amount=Decimal(str(txn_amount)) if txn_amount is not None else None,
                                units=Decimal(str(txn_units)) if txn_units is not None else None,
                                nav=Decimal(str(txn_nav)) if txn_nav is not None else None,
                                balance=Decimal(str(txn_balance)) if txn_balance is not None else None,
                                transaction_type=transaction_type,
                                dividend_rate=Decimal(str(txn_dividend_rate))
                                if txn_dividend_rate is not None
                                else None,
                            )
                            db.add(txn_obj)
                    except SQLAlchemyError as e:
                        logger.error(f"Error handling transaction: {e}", exc_info=True)
                        raise

        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error. Raise a ticket for support.")
    except ValueError as e:
        db.rollback()
        logger.error(f"Data validation error: {e}", exc_info=False)
        raise HTTPException(status_code=400, detail=f"Invalid data: {e}")
    except HTTPException as e:
        db.rollback()
        raise e  # Re-raise HTTPException to be handled by caller
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
    finally:
        db.close()

def process_log_messages(log_messages: list):
    """
    Processes a list of log messages, extracting and formatting the useful information.

    Args:
        log_messages: A list of log message strings.

    Returns:
        A list of formatted log messages.
    """
    log_items_html = "<ul>"
    for message in log_messages:
        log_items_html += f"<li>{message}</li>"
    log_items_html += "</ul>"
    html_content = f"<html><body><h1>Log Messages:</h1>{log_items_html}</body></html>"
    return html_content

def convertpdf(pdf_file_path: str, password: str, email: str) -> bool:
    """
    Converts a CAS PDF to JSON data, then attempts to publish the JSON data to the DB.
    Returns True on success, raises HTTPException on failure.
    """
    logger.info("File Conversion START")
    try:
        logger.debug(f"Converting {pdf_file_path}")
        json_str = casparser.read_cas_pdf(pdf_file_path, password, output="json")
        data = json.loads(json_str)

        with open("output.json", "w") as f:
            json.dump(data, f, indent=4)
        logger.info("File Conversion FINISH")
    except casparser.exceptions.CASParserError as e:  # Catching specific exception
        logger.error(f"Conversion PDF PARSER Module FAILED. {e}", exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # Use appropriate status code
            detail=f"PDF Conversion Module FAILED. {e}"
        )
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}", exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid JSON format."
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)  # Catching other exceptions
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

    logger.info("Adding data to DB")
    try:
        db = SessionLocal()
        if not publish_json_to_db(data, email,db):
            logger.error("Failed to push data to DB.")
            raise HTTPException(  # Raise HTTPException for DB failure
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to push data to DB."
            )
        return True  # Indicate success
    except HTTPException as e:
        raise e # Re-raise HTTPException to be handled by caller
    except Exception as e:
        logger.error(f"An unexpected error occurred during database operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during database operation."
        )



