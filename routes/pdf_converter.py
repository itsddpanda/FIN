# File: routes/pdf_converter.py
import json
import logging
from datetime import datetime
from turtle import shearfactor
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import delete
import casparser
import os
from models import User, Folio, StatementPeriod, Scheme, Valuation, Transaction, AMC
from db import SessionLocal
from dotenv import load_dotenv
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
    try:
        user_id = None
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

        # 7. Finally, delete the user record.
        db.execute(delete(User).where(User.user_id == user_id))
        logger.info(f"User {user_id} deleted")

        db.commit()
        logger.info(f"Database cleared for {identifier_type}: {identifier}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing database for {identifier}: {e}", exc_info=False)
        raise

def publish_json_to_db(data: dict) -> bool:
    """
    Parses the JSON data and updates the DB.
    For each folio:
      - If the folio is new, a new StatementPeriod is created and all schemes,
        valuations and transactions are inserted.
      - If the folio already exists (for the user), the existing StatementPeriod
        is examined. The new statement period from the JSON is compared against
        the stored period. Only transactions falling into the "new" period (i.e.,
        outside the existing date range) are added. If the new period extends the
        existing range, the valuation record is updated accordingly.
    """
    session = SessionLocal()

    def parse_date(date_str: str) -> datetime.date:
        """
        Try multiple date formats.
        Formats include:
          - "YYYY-MM-DD" (e.g., "2025-03-05")
          - "YYYY-MMM-DD" (e.g., "2025-Mar-05")
          - "DD-MMM-YYYY" (e.g., "01-Jan-2025")
        """
        for fmt in ("%Y-%m-%d", "%Y-%b-%d", "%d-%b-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        raise ValueError(f"Date format for '{date_str}' not recognized.")

    try:
        # 1. Extract and parse the new statement period from JSON.
        sp_data = data.get("statement_period")
        if not sp_data:
            raise ValueError("Missing 'statement_period' in JSON data.")
        new_sp_from = parse_date(sp_data.get("from"))
        new_sp_to = parse_date(sp_data.get("to"))
        logger.debug(f"New Statement from: {new_sp_from} to {new_sp_to}")
        # 2. Process investor info and obtain the user.
        investor_info = data.get("investor_info", {})
        email = "test@ting.com"  # for testing purposes else investor_info.get("email") 
        name = investor_info.get("name")
        if not email:
            raise ValueError("Investor email is missing.")

        user = session.query(User).filter_by(email=email).first()
        logger.debug(f"Uesr feteched for {email} is {user}")
        if not user:
            logger.error(f"User with email {email} not found.")
            raise ValueError("User not found.")
        else:
            # If the user exists but their full name is missing, update it.
            if not user.full_name:
                user.full_name = name
                session.add(user)
                session.flush()

        # 3. Process each folio in the JSON.
        for folio_data in data.get("folios", []):
            folio_number = folio_data.get("folio")
            amc = folio_data.get("amc")
            pan = folio_data.get("PAN")

            # Query for an existing folio (belongs to this user).
            existing_folio = session.query(Folio).filter_by(
                folio_number=folio_number, user_id=user.user_id
            ).first()
            logger.debug(f"Existing Folio: {existing_folio}")
            if not existing_folio:
                # New folio: create a new statement period and associate with the folio.
                logger.debug(f"Adding New Folio for statement {new_sp_from} to {new_sp_to}")
                # Check if a statement period with these parameters already exists
                existing_sp = session.query(StatementPeriod).filter_by(
                    from_date=new_sp_from, 
                    to_date=new_sp_to, 
                    user_id=user.user_id
                ).first()

                if existing_sp:
                    # Use the existing statement period
                    sp = existing_sp
                    logger.info("Using existing statement period")
                    logger.debug(f"Using existing statement period: {sp.id} ({sp.from_date} to {sp.to_date})")
                else:
                    # Create a new statement period
                    sp = StatementPeriod(from_date=new_sp_from, to_date=new_sp_to, user_id=user.user_id)
                    session.add(sp)
                    session.flush()  # assign an id to sp
                    logger.debug(f"Created new statement period: {sp.id} ({sp.from_date} to {sp.to_date})")

                folio_obj = Folio(
                    folio_number=folio_number,
                    pan=pan,
                    statement_period=sp,
                    user=user
                )
                session.add(folio_obj)
                session.flush()
                logger.debug(f"Folio Deatils: {folio_obj}")
                # For a new folio, add all schemes, valuations and transactions.
                for scheme_data in folio_data.get("schemes", []):
                    scheme_obj = Scheme(
                        folio_id=folio_number,
                        scheme_name=scheme_data.get("scheme"),
                        advisor=scheme_data.get("advisor"),
                        rta_code=scheme_data.get("rta_code"),
                        rta=scheme_data.get("rta"),
                        scheme_type=scheme_data.get("type"),
                        isin=scheme_data.get("isin"),
                        amfi_code=scheme_data.get("amfi"),
                        nominees=scheme_data.get("nominees"),
                        open_units=scheme_data.get("open"),
                        close_units=scheme_data.get("close"),
                        close_calculated_units=scheme_data.get("close_calculated")
                    )
                    session.add(scheme_obj)
                    session.flush()
                    logger.debug(f"Schemes Added: {scheme_obj}")
                    # Add valuation
                    valuation_data = scheme_data.get("valuation")
                    if valuation_data:
                        valuation_obj = Valuation(
                            scheme=scheme_obj,
                            valuation_date=parse_date(valuation_data.get("date")),
                            valuation_nav=valuation_data.get("nav"),
                            valuation_value=valuation_data.get("value"),
                            valuation_cost=valuation_data.get("cost")
                        )
                        session.add(valuation_obj)

                    # Add all transactions.
                    for txn_data in scheme_data.get("transactions", []):
                        txn_date = parse_date(txn_data.get("date"))
                        txn_obj = Transaction(
                            scheme=scheme_obj,
                            transaction_date=txn_date,
                            description=txn_data.get("description"),
                            amount=txn_data.get("amount"),
                            units=txn_data.get("units"),
                            nav=txn_data.get("nav"),
                            balance=txn_data.get("balance"),
                            transaction_type=txn_data.get("type"),
                            dividend_rate=txn_data.get("dividend_rate")
                        )
                        session.add(txn_obj)

            else:
                logger.info(f"Existing Folio found {folio_data.get('folio')} with {amc}")
                # Existing folio: use its associated statement period.
                sp = existing_folio.statement_period
                # Determine if the new statement period extends the stored period.
                missing_periods = []
                if new_sp_from < sp.from_date:
                    missing_periods.append((new_sp_from, min(new_sp_to, sp.from_date)))
                if new_sp_to > sp.to_date:
                    missing_periods.append((max(new_sp_from, sp.to_date), new_sp_to))

                # Update the StatementPeriod record if the new period extends the boundaries.
                new_union_from = min(sp.from_date, new_sp_from)
                new_union_to = max(sp.to_date, new_sp_to)
                if new_union_from != sp.from_date or new_union_to != sp.to_date:
                    logger.info(
                        f"Updating StatementPeriod for folio {folio_number} from {sp.from_date} - {sp.to_date} "
                        f"to {new_union_from} - {new_union_to}"
                    )
                    sp.from_date = new_union_from
                    sp.to_date = new_union_to
                    sp.user_id=user.user_id
                    session.add(sp)
                    session.flush()

                # Process each scheme for the folio.
                for scheme_data in folio_data.get("schemes", []):
                    scheme_name = scheme_data.get("scheme")
                    existing_scheme = session.query(Scheme).filter_by(
                        folio_id=folio_number, scheme_name=scheme_name
                    ).first()

                    if not existing_scheme:
                        # New scheme in an existing folio: add it with all related data.
                        scheme_obj = Scheme(
                            folio_id=folio_number,
                            scheme_name=scheme_name,
                            advisor=scheme_data.get("advisor"),
                            rta_code=scheme_data.get("rta_code"),
                            rta=scheme_data.get("rta"),
                            scheme_type=scheme_data.get("type"),
                            isin=scheme_data.get("isin"),
                            amfi_code=scheme_data.get("amfi"),
                            nominees=scheme_data.get("nominees"),
                            open_units=scheme_data.get("open"),
                            close_units=scheme_data.get("close"),
                            close_calculated_units=scheme_data.get("close_calculated")
                        )
                        session.add(scheme_obj)
                        session.flush()

                        valuation_data = scheme_data.get("valuation")
                        if valuation_data:
                            valuation_obj = Valuation(
                                scheme=scheme_obj,
                                valuation_date=parse_date(valuation_data.get("date")),
                                valuation_nav=valuation_data.get("nav"),
                                valuation_value=valuation_data.get("value"),
                                valuation_cost=valuation_data.get("cost")
                            )
                            session.add(valuation_obj)

                        for txn_data in scheme_data.get("transactions", []):
                            txn_date = parse_date(txn_data.get("date"))
                            txn_obj = Transaction(
                                scheme=scheme_obj,
                                transaction_date=txn_date,
                                description=txn_data.get("description"),
                                amount=txn_data.get("amount"),
                                units=txn_data.get("units"),
                                nav=txn_data.get("nav"),
                                balance=txn_data.get("balance"),
                                transaction_type=txn_data.get("type"),
                                dividend_rate=txn_data.get("dividend_rate")
                            )
                            session.add(txn_obj)
                    else:
                        # Existing scheme: add only transactions that fall in the "missing" (new) periods.
                        for txn_data in scheme_data.get("transactions", []):
                            txn_date = parse_date(txn_data.get("date"))
                            add_txn = any(period_start <= txn_date < period_end for period_start, period_end in missing_periods)
                            if add_txn:
                                txn_obj = Transaction(
                                    scheme=existing_scheme,
                                    transaction_date=txn_date,
                                    description=txn_data.get("description"),
                                    amount=txn_data.get("amount"),
                                    units=txn_data.get("units"),
                                    nav=txn_data.get("nav"),
                                    balance=txn_data.get("balance"),
                                    transaction_type=txn_data.get("type"),
                                    dividend_rate=txn_data.get("dividend_rate")
                                )
                                session.add(txn_obj)

                        # Update valuation if the new period extends beyond the existing period.
                        valuation_data = scheme_data.get("valuation")
                        if valuation_data and new_sp_to > sp.to_date:
                            existing_valuation = session.query(Valuation).filter_by(
                                scheme_id=existing_scheme.id
                            ).first()
                            if existing_valuation:
                                existing_valuation.valuation_date = parse_date(valuation_data.get("date"))
                                existing_valuation.valuation_nav = valuation_data.get("nav")
                                existing_valuation.valuation_value = valuation_data.get("value")
                                existing_valuation.valuation_cost = valuation_data.get("cost")
                                session.add(existing_valuation)
                            else:
                                valuation_obj = Valuation(
                                    scheme=existing_scheme,
                                    valuation_date=parse_date(valuation_data.get("date")),
                                    valuation_nav=valuation_data.get("nav"),
                                    valuation_value=valuation_data.get("value"),
                                    valuation_cost=valuation_data.get("cost")
                                )
                                session.add(valuation_obj)

        session.commit()
        logger.info("Finished DB query.")
        return True

    except Exception as e:
        session.rollback()
        if e == "User not found.":
            logger.error(f"Error publishing JSON to DB, Exception: Is user registered?!", exc_info=False)
            logger.warning("Unauthorised access to add data to db")
        logger.error(f"Error publishing JSON to DB, Exception: {e}", exc_info=False)
        return False
    finally:
        session.close()

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

def publish_to_db(data: dict, emailr: str) -> bool:
    """
    Parses the JSON data and updates the DB.
    For each folio:
      - If the folio is new, a new StatementPeriod is created and all schemes,
        valuations, and transactions are inserted.
      - If the folio already exists (for the user), the existing StatementPeriod
        is examined. The new statement period from the JSON is compared against
        the stored period. Only transactions falling into the "new" period (i.e.,
        outside the existing date range) are added. If the new period extends the
        existing range, the valuation record is updated accordingly.
    """
    session = SessionLocal()

    def parse_date(date_str: str) -> datetime.date:
        """
        Try multiple date formats.
        Formats include:
          - "YYYY-MM-DD" (e.g., "2025-03-05")
          - "YYYY-MMM-DD" (e.g., "2025-Mar-05")
          - "DD-MMM-YYYY" (e.g., "01-Jan-2025")
        """
        for fmt in ("%Y-%m-%d", "%Y-%b-%d", "%d-%b-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        raise ValueError(f"Date format for '{date_str}' not recognized.")

    try:
        # 1. Extract and parse the new statement period from JSON.
        sp_data = data.get("statement_period")
        if not sp_data:
            raise ValueError("Missing 'statement_period' in JSON data.")
        new_sp_from = parse_date(sp_data.get("from"))
        new_sp_to = parse_date(sp_data.get("to"))
        logger.debug(f"New Statement from: {new_sp_from} to {new_sp_to}")

        # 2. Process investor info and obtain the user.
        investor_info = data.get("investor_info", {})
        email = emailr  # Use the provided email parameter.
        name = investor_info.get("name")
        if not email:
            raise ValueError("Investor email is missing.")

        user = session.query(User).filter_by(email=email).first()
        logger.debug(f"User fetched for {email} is {user}")
        if not user:
            logger.error(f"User with email {email} not found.")
            raise ValueError("User not found.")
        else:
            if not user.full_name:
                user.full_name = name
                session.add(user)
                session.flush()

        # 3. Process each folio in the JSON.
        for folio_data in data.get("folios", []):
            folio_number = folio_data.get("folio")
            pan = folio_data.get("PAN")

            # --- Process AMC details ---
            # Expect JSON field: "amc"
            amc_name = folio_data.get("amc")
            if not amc_name:
                logger.warning(f"Skipping folio {folio_number} because AMC name is missing.")
                continue

            # Lookup AMC; if not found, create a new AMC record.
            amc_obj = session.query(AMC).filter_by(name=amc_name).first()
            if not amc_obj:
                amc_obj = AMC(name=amc_name)
                session.add(amc_obj)
                session.flush()  # Assigns id to amc_obj

            # Query for an existing folio (for this user).
            existing_folio = session.query(Folio).filter_by(
                folio_number=folio_number, user_id=user.user_id
            ).first()
            logger.debug(f"Existing Folio: {existing_folio}")

            if not existing_folio:
                # New folio: create or use an existing StatementPeriod.
                logger.debug(f"Adding New Folio for statement {new_sp_from} to {new_sp_to}")
                existing_sp = session.query(StatementPeriod).filter_by(
                    from_date=new_sp_from,
                    to_date=new_sp_to,
                    user_id=user.user_id
                ).first()
                if existing_sp:
                    sp = existing_sp
                    logger.info("Using existing statement period")
                    logger.debug(f"Using existing statement period: {sp.id} ({sp.from_date} to {sp.to_date})")
                else:
                    sp = StatementPeriod(from_date=new_sp_from, to_date=new_sp_to, user_id=user.user_id)
                    session.add(sp)
                    session.flush()
                    logger.debug(f"Created new statement period: {sp.id} ({sp.from_date} to {sp.to_date})")

                # Create new Folio with AMC_ID set.
                folio_obj = Folio(
                    folio_number=folio_number,
                    pan=pan,
                    statement_period=sp,
                    user=user,
                    amc_id=amc_obj.id
                )
                session.add(folio_obj)
                session.flush()
                logger.debug(f"Folio Details: {folio_obj}")

                # For a new folio, add all schemes, valuations, and transactions.
                for scheme_data in folio_data.get("schemes", []):
                    scheme_isin = scheme_data.get("isin")
                    scheme_amfi = scheme_data.get("amfi")
                    if not (scheme_isin or scheme_amfi):
                        logger.warning(f"Skipping scheme addition for folio {folio_number} due to missing both ISIN and AMFI code.")
                        continue
                    else:
                        scheme_obj = Scheme(
                            folio_id=folio_number,
                            amc_id=amc_obj.id,
                            scheme_name=scheme_data.get("scheme"),
                            advisor=scheme_data.get("advisor"),
                            rta_code=scheme_data.get("rta_code"),
                            rta=scheme_data.get("rta"),
                            scheme_type=scheme_data.get("type"),
                            isin=scheme_isin,
                            amfi_code=scheme_amfi,
                            nominees=scheme_data.get("nominees"),
                            open_units=scheme_data.get("open"),
                            close_units=scheme_data.get("close"),
                            close_calculated_units=scheme_data.get("close_calculated")
                        )
                        session.add(scheme_obj)
                        session.flush()
                        logger.debug(f"Scheme Added: {scheme_obj}")
                        valuation_data = scheme_data.get("valuation")
                        if valuation_data:
                            valuation_obj = Valuation(
                                scheme=scheme_obj,
                                valuation_date=parse_date(valuation_data.get("date")),
                                valuation_nav=valuation_data.get("nav"),
                                valuation_value=valuation_data.get("value"),
                                valuation_cost=valuation_data.get("cost")
                            )
                            session.add(valuation_obj)
                        for txn_data in scheme_data.get("transactions", []):
                            txn_date = parse_date(txn_data.get("date"))
                            txn_obj = Transaction(
                                scheme=scheme_obj,
                                transaction_date=txn_date,
                                description=txn_data.get("description"),
                                amount=txn_data.get("amount"),
                                units=txn_data.get("units"),
                                nav=txn_data.get("nav"),
                                balance=txn_data.get("balance"),
                                transaction_type=txn_data.get("type"),
                                dividend_rate=txn_data.get("dividend_rate")
                            )
                            session.add(txn_obj)
            else:
                logger.info(f"Existing Folio found {folio_number} with AMC {amc_name}")
                sp = existing_folio.statement_period
                missing_periods = []
                if new_sp_from < sp.from_date:
                    missing_periods.append((new_sp_from, min(new_sp_to, sp.from_date)))
                if new_sp_to > sp.to_date:
                    missing_periods.append((max(new_sp_from, sp.to_date), new_sp_to))
                new_union_from = min(sp.from_date, new_sp_from)
                new_union_to = max(sp.to_date, new_sp_to)
                if new_union_from != sp.from_date or new_union_to != sp.to_date:
                    logger.info(
                        f"Updating StatementPeriod for folio {folio_number} from {sp.from_date} - {sp.to_date} "
                        f"to {new_union_from} - {new_union_to}"
                    )
                    sp.from_date = new_union_from
                    sp.to_date = new_union_to
                    sp.user_id = user.user_id
                    session.add(sp)
                    session.flush()

                for scheme_data in folio_data.get("schemes", []):
                    scheme_name = scheme_data.get("scheme")
                    existing_scheme = session.query(Scheme).filter_by(
                        folio_id=folio_number, scheme_name=scheme_name
                    ).first()
                    if not existing_scheme:
                        scheme_obj = Scheme(
                            folio_id=folio_number,
                            amc_id=amc_obj.id,
                            scheme_name=scheme_name,
                            advisor=scheme_data.get("advisor"),
                            rta_code=scheme_data.get("rta_code"),
                            rta=scheme_data.get("rta"),
                            scheme_type=scheme_data.get("type"),
                            isin=scheme_data.get("isin"),
                            amfi_code=scheme_data.get("amfi"),
                            nominees=scheme_data.get("nominees"),
                            open_units=scheme_data.get("open"),
                            close_units=scheme_data.get("close"),
                            close_calculated_units=scheme_data.get("close_calculated")
                        )
                        session.add(scheme_obj)
                        session.flush()
                        valuation_data = scheme_data.get("valuation")
                        if valuation_data:
                            valuation_obj = Valuation(
                                scheme=scheme_obj,
                                valuation_date=parse_date(valuation_data.get("date")),
                                valuation_nav=valuation_data.get("nav"),
                                valuation_value=valuation_data.get("value"),
                                valuation_cost=valuation_data.get("cost")
                            )
                            session.add(valuation_obj)
                        for txn_data in scheme_data.get("transactions", []):
                            txn_date = parse_date(txn_data.get("date"))
                            txn_obj = Transaction(
                                scheme=scheme_obj,
                                transaction_date=txn_date,
                                description=txn_data.get("description"),
                                amount=txn_data.get("amount"),
                                units=txn_data.get("units"),
                                nav=txn_data.get("nav"),
                                balance=txn_data.get("balance"),
                                transaction_type=txn_data.get("type"),
                                dividend_rate=txn_data.get("dividend_rate")
                            )
                            session.add(txn_obj)
                    else:
                        for txn_data in scheme_data.get("transactions", []):
                            txn_date = parse_date(txn_data.get("date"))
                            add_txn = any(period_start <= txn_date < period_end
                                          for period_start, period_end in missing_periods)
                            if add_txn:
                                txn_obj = Transaction(
                                    scheme=existing_scheme,
                                    transaction_date=txn_date,
                                    description=txn_data.get("description"),
                                    amount=txn_data.get("amount"),
                                    units=txn_data.get("units"),
                                    nav=txn_data.get("nav"),
                                    balance=txn_data.get("balance"),
                                    transaction_type=txn_data.get("type"),
                                    dividend_rate=txn_data.get("dividend_rate")
                                )
                                session.add(txn_obj)
                        valuation_data = scheme_data.get("valuation")
                        if valuation_data and new_sp_to > sp.to_date:
                            existing_valuation = session.query(Valuation).filter_by(
                                scheme_id=existing_scheme.id
                            ).first()
                            if existing_valuation:
                                existing_valuation.valuation_date = parse_date(valuation_data.get("date"))
                                existing_valuation.valuation_nav = valuation_data.get("nav")
                                existing_valuation.valuation_value = valuation_data.get("value")
                                existing_valuation.valuation_cost = valuation_data.get("cost")
                                session.add(existing_valuation)
                            else:
                                valuation_obj = Valuation(
                                    scheme=existing_scheme,
                                    valuation_date=parse_date(valuation_data.get("date")),
                                    valuation_nav=valuation_data.get("nav"),
                                    valuation_value=valuation_data.get("value"),
                                    valuation_cost=valuation_data.get("cost")
                                )
                                session.add(valuation_obj)

        session.commit()
        logger.info("Finished DB query.")
        return True

    except Exception as e:
        session.rollback()
        if str(e) == "User not found.":
            logger.error("Error publishing JSON to DB, Exception: Is user registered?!", exc_info=False)
            logger.warning("Unauthorised access to add data to db")
        logger.error(f"Error publishing JSON to DB, Exception: {e}", exc_info=True)
        return False

    finally:
        session.close()


def convertpdf(pdf_file_path: str, password: str, email: str):
    """
    Converts a CAS PDF to JSON data, then attempts to publish the JSON data to the DB.
    """
    logger.info("File Conversion START")
    try:
        logger.debug(f"Converting {pdf_file_path}")
        json_str = casparser.read_cas_pdf(pdf_file_path, password, output="json")
        data = json.loads(json_str)

        # Ensure the output file exists (create if missing)
        if not os.path.exists("output.json"):
            with open("output.json", "w") as f:
                f.write("")  # Create an empty file

        with open("output.json", "w") as f:
            json.dump(data, f, indent=4)
        logger.info("File Conversion FINISH")
    except Exception as e:
        logger.error(f"Conversion PDF PARSER Module FAILED. {e}", exc_info=False)
        logger.removeHandler(progress_handler)
        return None

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}", exc_info=False)
        logger.removeHandler(progress_handler)
        return None
    logger.info("Adding data to DB")
    if not publish_to_db(data, email):
        logger.error("Failed to push data to DB.")
        logger.removeHandler(progress_handler)
        return progress_report
    logger.removeHandler(progress_handler)
    return progress_report



