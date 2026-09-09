from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import User
from app.core.security import get_current_user, require_admin, require_admin_or_accountant
from app.schemas.bank import (
    BankStockStatementCreate, BankReconciliationImport,
    NotificationSettingsUpdate, ScheduledReportSettings,
    BankReconCreate, ManualMatchRequest, UnmatchRequest, AdjustmentRequest,
)
from app.services.bank_service import (
    BankStockStatementService, BankReconciliationService,
    NotificationService, ScheduledReportService, BackupService,
)
from app.services.bank_recon_service import BankReconService

bank_stmt_router = APIRouter(prefix="/bank-stock-statement", tags=["bank-statement"])

@bank_stmt_router.get("/")
async def list_statements(page: int = Query(1, ge=1), page_size: int = Query(20), db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankStockStatementService.list_statements(db, page, page_size)

@bank_stmt_router.post("/", status_code=201)
async def generate_statement(payload: BankStockStatementCreate, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankStockStatementService.generate(db, payload, current_user.id)

@bank_stmt_router.get("/{stmt_id}")
async def get_statement(stmt_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankStockStatementService.get_by_id(db, stmt_id)

bank_recon_router = APIRouter(prefix="/bank-reconciliation", tags=["bank-reconciliation"])

@bank_recon_router.post("/reconcile")
async def reconcile_bank(payload: BankReconciliationImport, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconciliationService.reconcile(db, payload)


@bank_recon_router.post("/", status_code=201)
async def create_reconciliation(payload: BankReconCreate, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.create_draft(db, payload, current_user.id)


@bank_recon_router.get("/")
async def list_reconciliations(page: int = Query(1, ge=1), page_size: int = Query(20), db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankReconService.list_recons(db, page, page_size)


@bank_recon_router.get("/{recon_id}")
async def get_reconciliation(recon_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankReconService.get(db, recon_id)


@bank_recon_router.post("/{recon_id}/match")
async def match_line(recon_id: int, payload: ManualMatchRequest, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.manual_match(db, recon_id, payload.line_id, payload.journal_line_id, current_user.id)


@bank_recon_router.post("/{recon_id}/unmatch")
async def unmatch_line(recon_id: int, payload: UnmatchRequest, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.unmatch(db, recon_id, payload.line_id, current_user.id)


@bank_recon_router.post("/{recon_id}/adjustment")
async def add_adjustment(recon_id: int, payload: AdjustmentRequest, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.add_adjustment(db, recon_id, payload, current_user.id)


@bank_recon_router.post("/{recon_id}/finalize")
async def finalize_reconciliation(recon_id: int, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.finalize(db, recon_id, current_user.id)


@bank_recon_router.post("/import-file")
async def import_statement_file(file: UploadFile = File(...), _: User = Depends(require_admin_or_accountant)):
    content = await file.read()
    entries = BankReconService.parse_statement_file(file.filename, content)
    return {"entries": entries, "count": len(entries)}

notification_router = APIRouter(prefix="/notifications", tags=["notifications"])

@notification_router.get("/settings")
async def get_notification_settings(_: User = Depends(require_admin)):
    return NotificationService.get_settings()

@notification_router.put("/settings")
async def update_notification_settings(payload: NotificationSettingsUpdate, _: User = Depends(require_admin)):
    return NotificationService.update_settings(payload)

@notification_router.post("/test-email")
async def test_email(payload: dict, _: User = Depends(require_admin)):
    return NotificationService.test_email(payload.get("to_email", ""))

scheduled_router = APIRouter(prefix="/scheduled-reports", tags=["scheduled-reports"])

@scheduled_router.get("/settings")
async def get_scheduled_settings(_: User = Depends(require_admin)):
    return ScheduledReportService.get_settings()

@scheduled_router.put("/settings")
async def update_scheduled_settings(payload: ScheduledReportSettings, _: User = Depends(require_admin)):
    return ScheduledReportService.update_settings(payload)

backup_router = APIRouter(prefix="/backup", tags=["backup"])

@backup_router.get("/status")
async def get_backup_status(_: User = Depends(require_admin)):
    return BackupService.get_status()
