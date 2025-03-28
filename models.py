# File: models.py
from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, ARRAY, UniqueConstraint, Boolean
from db import Base
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    full_name = Column(String)
    folios = relationship("Folio", back_populates="user")  # Relationship with Folio

class StatementPeriod(Base):
    __tablename__ = 'statement_period'
    id = Column(Integer, primary_key=True)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    user_id = Column(String, ForeignKey('users.user_id'))  # Foreign key to User
    user = relationship("User")
    folios = relationship("Folio", backref="statement_period", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('user_id', 'from_date', 'to_date', name='uq_statement_period_user'),
    )

class AMC(Base):
    __tablename__ = "amc"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    # AMC now only has a name.
    # Relationships:
    folios = relationship("Folio", back_populates="amc")
    schemes = relationship("Scheme", back_populates="amc")

class Folio(Base):
    __tablename__ = 'folio'
    folio_number = Column(String, primary_key=True, index=True)
    statement_period_id = Column(Integer, ForeignKey('statement_period.id'))
    user_id = Column(String, ForeignKey('users.user_id'))
    pan = Column(String)
    amc_id = Column(Integer, ForeignKey('amc.id'), nullable=False)
    schemes = relationship("Scheme", back_populates="folio", cascade="all, delete-orphan")
    user = relationship("User", back_populates="folios")
    amc = relationship("AMC", back_populates="folios")
    __table_args__ = (
        UniqueConstraint('folio_number', name='uq_folio_statement_period'),
    )

class Scheme(Base):
    __tablename__ = 'scheme'
    id = Column(Integer, primary_key=True, index=True)
    folio_id = Column(String, ForeignKey('folio.folio_number'))
    amc_id = Column(Integer, ForeignKey('amc.id'), nullable=False)
    scheme_name = Column(String)
    advisor = Column(String, nullable=True)
    rta_code = Column(String, nullable=True)
    rta = Column(String, nullable=True)
    scheme_type = Column(String, nullable=True)
    isin = Column(String, nullable=True)       # Scheme-specific ISIN
    amfi_code = Column(String, nullable=True)    # Scheme-specific AMFI code
    nominees = Column(ARRAY(String), nullable=True)
    open_units = Column(Float, nullable=True)
    close_units = Column(Float, nullable=True)
    close_calculated_units = Column(Float, nullable=True)
    folio = relationship("Folio", back_populates="schemes")
    amc = relationship("AMC", back_populates="schemes")
    valuation = relationship("Valuation", back_populates="scheme", uselist=False, cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="scheme", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('folio_id', 'scheme_name', name='uq_scheme_folio'),
    )

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
