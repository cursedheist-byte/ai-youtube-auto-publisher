import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import AccessCode, User, AccessMode
from app.schemas import CredentialSettingsOut, CredentialSettingsUpdate, AccessCodeRedeem, AccessCodeCreated, AccessCodeOut
from app.services.access_service import generate_access_code, redeem_access_code, save_user_credentials, validate_user_credentials
router = APIRouter(prefix="/api/access", tags=["access"])
admin_router = APIRouter(prefix="/api/admin/access-codes", tags=["admin-access-codes"])

def _out(user):
    grant = user.access_grant
    row = user.credentials
    return CredentialSettingsOut(access_mode=user.access_mode.value, google_client_id_configured=bool(row and row.google_client_id), google_client_secret_configured=bool(row and row.google_client_secret), openrouter_api_key_configured=bool(row and row.openrouter_api_key), daily_video_limit=grant.daily_video_limit if grant else None, channel_limit=grant.channel_limit if grant else None)
@router.get("/credentials", response_model=CredentialSettingsOut)
def get_credentials(user: User = Depends(get_current_user)): return _out(user)
@router.put("/credentials", response_model=CredentialSettingsOut)
def put_credentials(payload: CredentialSettingsUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        validate_user_credentials(payload.google_client_id, payload.google_client_secret, payload.openrouter_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    save_user_credentials(db, user, payload.google_client_id, payload.google_client_secret, payload.openrouter_api_key)
    return _out(user)
@router.post("/redeem", response_model=CredentialSettingsOut)
def redeem(payload: AccessCodeRedeem, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try: redeem_access_code(db, user, payload.code)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc))
    return _out(user)
@admin_router.post("", response_model=AccessCodeCreated)
def create_code(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    code, row = generate_access_code(db); return AccessCodeCreated(code=code, id=row.id, created_at=row.created_at, expires_at=row.expires_at)
@admin_router.get("", response_model=list[AccessCodeOut])
def list_codes(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [AccessCodeOut(id=x.id, created_at=x.created_at, redeemed_at=x.redeemed_at, redeemed_by_user_id=x.redeemed_by_user_id, expires_at=x.expires_at, status=x.status.value, channel_limit=x.channel_limit, daily_video_limit=x.daily_video_limit) for x in db.query(AccessCode).order_by(AccessCode.created_at.desc()).all()]
