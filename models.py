#file models.py
from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, ARRAY, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from db import Base

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    full_name = Column(String)
    mobile = Column(String, nullable=True)  # Added mobile field
    address = Column(String, nullable=True) # Added address field
    folios = relationship("Folio", back_populates="user")
    statement_periods = relationship("StatementPeriod", back_populates="user")

class StatementPeriod(Base):
    __tablename__ = 'statement_period'
    id = Column(Integer, primary_key=True)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    user_id = Column(String, ForeignKey('users.user_id'))
    user = relationship("User", back_populates="statement_periods")
    folios = relationship("Folio", backref="statement_period", cascade="all, delete-orphan")
    upload_date = Column(Date, nullable=True)  # Added upload date (Date only)
    __table_args__ = (
        UniqueConstraint('user_id', 'from_date', 'to_date', name='uq_statement_period_user'),
    )

class AMC(Base):
    __tablename__ = "amc"
    amc_id = Column(Integer, primary_key=True, autoincrement=True)
    amc_name = Column(String, unique=True, nullable=False)
    folios = relationship("Folio", back_populates="amc")
    schemes = relationship("Scheme", back_populates="amc", cascade="all, delete-orphan")
    scheme_masters = relationship("SchemeMaster", back_populates="amc")

class Folio(Base):
    __tablename__ = 'folio'
    folio_number = Column(String, primary_key=True, index=True)
    statement_period_id = Column(Integer, ForeignKey('statement_period.id'))
    user_id = Column(String, ForeignKey('users.user_id'))
    pan = Column(String)
    amc_id = Column(Integer, ForeignKey('amc.amc_id'), nullable=False)
    schemes = relationship("Scheme", back_populates="folio", cascade="all, delete-orphan")
    user = relationship("User", back_populates="folios")
    amc = relationship("AMC", back_populates="folios")
    __table_args__ = (
        UniqueConstraint('folio_number', name='uq_folio_statement_period'),
    )

class SchemeMaster(Base):
    __tablename__ = 'scheme_master'
    scheme_id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_isin = Column(String, nullable=False, unique=True)
    scheme_amfi_code = Column(String, nullable=True, unique=True)
    scheme_name = Column(String, nullable=False)
    amc_id = Column(Integer, ForeignKey('amc.amc_id'), nullable=False)
    scheme_type = Column(String, nullable=True)
    amc = relationship("AMC", back_populates="scheme_masters")
    nav_history = relationship("SchemeNavHistory", back_populates="scheme_master", cascade="all, delete-orphan")
    schemes = relationship("Scheme", back_populates="scheme_master", cascade="all, delete-orphan")

class Scheme(Base):
    __tablename__ = 'scheme'
    id = Column(Integer, primary_key=True, index=True)
    folio_id = Column(String, ForeignKey('folio.folio_number'))
    amc_id = Column(Integer, ForeignKey('amc.amc_id'), nullable=False)
    scheme_master_id = Column(Integer, ForeignKey('scheme_master.scheme_id'), nullable=False, index=True)
    advisor = Column(String, nullable=True)
    rta_code = Column(String, nullable=True)
    rta = Column(String, nullable=True)
    nominees = Column(ARRAY(String), nullable=True)
    open_units = Column(Float, nullable=True)
    close_units = Column(Float, nullable=True)
    close_calculated_units = Column(Float, nullable=True)
    folio = relationship("Folio", back_populates="schemes")
    amc = relationship("AMC", back_populates="schemes")
    valuation = relationship("Valuation", back_populates="scheme", uselist=False, cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="scheme", cascade="all, delete-orphan")
    scheme_master = relationship("SchemeMaster", back_populates="schemes")

class Valuation(Base):
    __tablename__ = 'valuation'
    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey('scheme.id'), unique=True)
    valuation_date = Column(Date, nullable=True)
    valuation_nav = Column(Float, nullable=True)
    valuation_cost = Column(Float, nullable=True)
    valuation_value = Column(Float, nullable=True)
    scheme = relationship("Scheme", back_populates="valuation")

class Transaction(Base):
    __tablename__ = 'transaction'
    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey('scheme.id'))
    transaction_date = Column(Date, nullable=True)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    units = Column(Float, nullable=True)
    nav = Column(Float, nullable=True)
    balance = Column(Float, nullable=True)
    transaction_type = Column(String, nullable=True)
    dividend_rate = Column(Float, nullable=True)
    scheme = relationship("Scheme", back_populates="transactions")

class SchemeNavHistory(Base):
    __tablename__ = 'scheme_nav_history'
    id = Column(Integer, primary_key=True, index=True)
    nav_date = Column(Date)
    nav_value = Column(Float)
    scheme_master_id = Column(Integer, ForeignKey('scheme_master.scheme_id'))
    scheme_master = relationship("SchemeMaster", back_populates="nav_history")
