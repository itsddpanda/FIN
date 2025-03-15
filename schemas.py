# File: schemas.py
from operator import is_
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import date

from models import User

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    is_active: bool
    user_id: str

    class Config:
        from_attributes = True

class Usernoid(UserBase):
    is_active: bool

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

class SchemeMasterOut(BaseModel):
    scheme_id: int
    scheme_isin: str
    scheme_amfi_code: Optional[str] = None
    scheme_name: str
    amc_id: int
    scheme_type: Optional[str] = None

    model_config = {'from_attributes': True}

class SchemeOut(BaseModel):
    id: int
    scheme_name: str
    isin: Optional[str] = None
    amfi_code: Optional[str] = None
    advisor: Optional[str] = None
    rta_code: Optional[str] = None
    rta: Optional[str] = None
    nominees: Optional[List[str]] = None
    open_units: Optional[float] = None
    close_units: Optional[float] = None
    close_calculated_units: Optional[float] = None
    valuation: Optional["ValuationOut"] = None
    scheme_master_id: int
    scheme_master: Optional["SchemeMasterOut"] = None  # Add relationship

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


class DashboardOut(BaseModel):
    user: UserOut
    portfolio_value: float = Field(..., description="Total portfolio value")
    total_investment: float = Field(..., description="Total investment cost")
    total_gain_loss: float = Field(..., description="Total gain or loss")
    total_gain_loss_percent: float = Field(..., description="Total gain or loss percent")

class AMCWithSchemesOut(BaseModel):
    amc: AMCOut
    schemes: List[SchemeOut]

class MetaData(BaseModel):
    fund_house: str
    scheme_type: str
    scheme_category: str
    scheme_code: int
    scheme_name: str
    isin_growth: str
    isin_div_reinvestment: Optional[str] = None

class NavData(BaseModel):
    date: str
    nav: str

class HistoricalDataResponse(BaseModel):
    meta: MetaData
    data: List[NavData]
    status: str

class HistoricalDataOut(BaseModel):
    data: HistoricalDataResponse

class SchemeDetailsOut(BaseModel):
    scheme: SchemeOut
    transactions: List[TransactionOut]
    historical_data: Optional[HistoricalDataOut] = None



class SchemeNavHistoryOut(BaseModel):
    id: int
    scheme_master_id: int  # Updated from scheme_id
    nav_date: date
    nav_value: float

    model_config = {'from_attributes': True}
