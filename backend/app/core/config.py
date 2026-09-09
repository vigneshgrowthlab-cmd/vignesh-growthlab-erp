from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Wholesale ERP"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "change-this-to-a-random-secret-key-minimum-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = "mysql+pymysql://erp_user:erp_password@localhost:3306/wholesale_erp"

    # Files
    UPLOAD_DIR: str = "./uploads"
    EXPORT_DIR: str = "./exports"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Company
    COMPANY_NAME: str = "My Wholesale Company"
    COMPANY_GSTIN: str = "29AAAAA0000A1Z5"
    COMPANY_STATE: str = "Karnataka"
    COMPANY_STATE_CODE: int = 29
    COMPANY_ADDRESS: str = "123 Main Street"
    COMPANY_CITY: str = "Bangalore"
    COMPANY_PINCODE: str = "560001"
    COMPANY_PHONE: str = "9999999999"
    COMPANY_EMAIL: str = "info@company.com"
    FINANCIAL_YEAR_START_MONTH: int = 4

    # Cleartax / GST
    CLEARTAX_API_URL: str = "https://my.cleartax.in/api/integration"
    CLEARTAX_AUTH_TOKEN: str = ""
    CLEARTAX_GSTIN: str = ""
    CLEARTAX_SANDBOX: bool = True
    GSTIN_LOOKUP_URL: str = ""
    GSTIN_LOOKUP_TOKEN: str = ""
    EWAY_BILL_THRESHOLD: float = 50000.0
    # GSTR-1: an inter-state B2C invoice above this value is reported invoice-wise
    # under B2CL (Table 5); everything else is summarised under B2CS (Table 7).
    GSTR1_B2CL_THRESHOLD: float = 250000.0
    # Minimum HSN digits required on e-invoices. NIC mandates >=6 for
    # businesses with aggregate turnover > Rs 5 crore; set to 4 only if
    # turnover is <= Rs 5 crore.
    HSN_MIN_DIGITS: int = 6

    # Business Rules
    EXPENSE_APPROVAL_THRESHOLD: float = 5000.0
    LOW_STOCK_THRESHOLD_DEFAULT: int = 10
    CREDIT_DAYS_DEFAULT: int = 30
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # Email / SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_TLS: bool = True
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@company.com"

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_ORIGINS: str = '["http://localhost:5173","http://localhost:3000","http://127.0.0.1:5173"]'

    def get_allowed_origins(self) -> List[str]:
        try:
            return json.loads(self.ALLOWED_ORIGINS)
        except Exception:
            return [self.FRONTEND_URL, "http://localhost:5173"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
