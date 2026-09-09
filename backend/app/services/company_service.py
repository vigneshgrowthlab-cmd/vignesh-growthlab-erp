from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.models import CompanySettings
from app.core.config import settings


@dataclass(frozen=True)
class CompanyIdentity:
    name: str
    gstin: str
    state: str
    state_code: int
    address: str
    city: str
    pincode: str
    phone: str
    email: str


class CompanyService:
    """Company identity for outward documents (E-Invoice, E-Way Bill, GSTR).

    company_settings (DB) is what the business maintains through the UI;
    the COMPANY_* env values are deploy-time defaults that can go stale.
    Each field falls back to env only when the row is missing or blank.
    """

    @staticmethod
    def identity(db: Session) -> CompanyIdentity:
        row = db.query(CompanySettings).first()

        def pick(field: str, env_val):
            val = getattr(row, field, None) if row else None
            return val if val not in (None, "") else env_val

        address = None
        if row and row.address_line1:
            address = row.address_line1 + (
                f", {row.address_line2}" if row.address_line2 else ""
            )
        return CompanyIdentity(
            name=pick("company_name", settings.COMPANY_NAME),
            gstin=pick("gstin", settings.COMPANY_GSTIN),
            state=pick("state", settings.COMPANY_STATE),
            state_code=pick("state_code", settings.COMPANY_STATE_CODE),
            address=address or settings.COMPANY_ADDRESS,
            city=pick("city", settings.COMPANY_CITY),
            pincode=pick("pincode", settings.COMPANY_PINCODE),
            phone=pick("phone", settings.COMPANY_PHONE),
            email=pick("email", settings.COMPANY_EMAIL),
        )
