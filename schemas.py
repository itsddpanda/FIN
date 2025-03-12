# File: schemas.py
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import date

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    is_active: bool
    user_id: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
# Pydantic Models for API Responses
class AMCOut(BaseModel):
    id: int
    name: str
    valuation_value: float = 0.0
    valuation_cost: float = 0.0
    gain_loss: float = 0.0
    gain_loss_percent: float = 0.0

    model_config = {'from_attributes': True}

class FolioOut(BaseModel):
    folio_number: str
    amc: AMCOut

    model_config = {'from_attributes': True}

class SchemeOut(BaseModel):
    id: int
    scheme_name: str
    isin: Optional[str] = None
    amfi_code: Optional[str] = None
    open_units: Optional[float] = None
    close_units: Optional[float] = None
    close_calculated_units: Optional[float] = None
    valuation: Optional["ValuationOut"] = None

    model_config = {'from_attributes': True}

class ValuationOut(BaseModel):
    valuation_date: Optional[date] = None
    valuation_nav: Optional[float] = None
    valuation_cost: Optional[float] = None
    valuation_value: Optional[float] = None

    model_config = {'from_attributes': True}

class TransactionOut(BaseModel):
    transaction_date: Optional[date] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    units: Optional[float] = None
    nav: Optional[float] = None
    balance: Optional[float] = None
    transaction_type: Optional[str] = None
    dividend_rate: Optional[float] = None

    model_config = {'from_attributes': True}


class PortfolioOut(BaseModel):
    portfolio_value: float = 0.0
    total_investment: float = 0.0
    total_gain_loss: float = 0.0
    total_gain_loss_percent: float = 0.0
    folios: List[FolioOut]

class SchemeDetailsOut(BaseModel):
    scheme: SchemeOut
    transactions: List[TransactionOut]

class DashboardOut(BaseModel):
    user: UserOut
    portfolio_value: float = Field(..., description="Total portfolio value")
    total_investment: float = Field(..., description="Total investment cost")
    total_gain_loss: float = Field(..., description="Total gain or loss")
    total_gain_loss_percent: float = Field(..., description="Total gain or loss percent")