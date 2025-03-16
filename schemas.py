from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import date
from decimal import Decimal
from enum import Enum

### User Schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    is_active: bool

    model_config = {'from_attributes': True}

### Token
class Token(BaseModel):
    access_token: str
    token_type: str

### AMC Schemas
class AMCOut(BaseModel):
    id: int
    name: str

    model_config = {'from_attributes': True}

class AMCWithValuationOut(AMCOut):
    valuation_value: Decimal = 0.0
    valuation_cost: Decimal = 0.0
    gain_loss: Decimal = 0.0
    gain_loss_percent: Decimal = 0.0

class FolioOut(BaseModel):
    folio_number: str
    amc: AMCOut

    model_config = {'from_attributes': True}

### Scheme Master Schema (Reference Data)
class SchemeMasterOut(BaseModel):
    id: int
    isin: Optional[str] = None
    amfi_code: Optional[str] = None
    name: str
    amc_id: int
    scheme_type: Optional[str] = None

    model_config = {'from_attributes': True}

class ValuationOut(BaseModel):
    valuation_date: date  # Valuation date is required
    valuation_nav: Optional[Decimal] = None
    valuation_cost: Optional[Decimal] = None
    valuation_value: Optional[Decimal] = None

    model_config = {'from_attributes': True}

### Scheme Schema (Linked to SchemeMaster)
class SchemeOut(BaseModel):
    id: int
    folio_id: int
    # amc_id: int  # Removed redundant amc_id
    scheme_master: SchemeMasterOut
    advisor: Optional[str] = None
    rta_code: Optional[str] = None
    rta: Optional[str] = None
    nominees: Optional[List[str]] = None
    open_units: Optional[Decimal] = None
    close_units: Optional[Decimal] = None
    close_calculated_units: Optional[Decimal] = None
    valuation: Optional[ValuationOut] = None

    model_config = {'from_attributes': True}

class TransactionType(str, Enum):
    PURCHASE = "PURCHASE"
    PURCHASE_SIP = "PURCHASE_SIP"
    REDEMPTION = "REDEMPTION"
    SWITCH_IN = "SWITCH_IN"
    SWITCH_IN_MERGER = "SWITCH_IN_MERGER"
    SWITCH_OUT = "SWITCH_OUT"
    SWITCH_OUT_MERGER = "SWITCH_OUT_MERGER"
    DIVIDEND_PAYOUT = "DIVIDEND_PAYOUT"
    DIVIDEND_REINVESTMENT = "DIVIDEND_REINVESTMENT"
    SEGREGATION = "SEGREGATION"
    STAMP_DUTY_TAX = "STAMP_DUTY_TAX"
    TDS_TAX = "TDS_TAX"
    STT_TAX = "STT_TAX"
    MISC = "MISC"

class TransactionOut(BaseModel):
    transaction_date: Optional[date] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    units: Optional[Decimal] = None
    nav: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    transaction_type: Optional[TransactionType] = None  # Using Enum
    dividend_rate: Optional[Decimal] = None

    model_config = {'from_attributes': True}

### Portfolio Schema
class PortfolioOut(BaseModel):
    portfolio_value: Decimal = 0.0
    total_investment: Decimal = 0.0
    total_gain_loss: Decimal = 0.0
    total_gain_loss_percent: Decimal = 0.0
    folios: List[FolioOut]

### Dashboard Schema
class DashboardOut(BaseModel):
    user: UserOut
    portfolio_value: Decimal = Field(..., description="Total portfolio value")
    total_investment: Decimal = Field(..., description="Total investment cost")
    total_gain_loss: Decimal = Field(..., description="Total gain or loss")
    total_gain_loss_percent: Decimal = Field(..., description="Total gain or loss percent")

### AMC with Schemes Response
class AMCWithSchemesOut(BaseModel):
    amc: AMCWithValuationOut
    schemes: List[SchemeOut]

### Historical NAV Data
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
    scheme_master_id: int
    nav_date: date
    nav_value: Decimal
    
    model_config = {'from_attributes': True}