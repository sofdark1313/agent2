from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting

PUBLIC_SETTING_KEYS = {
    "default_author": "",
    "wechat_account_name": "",
    "wechat_original_id": "",
}


def get_public_settings(db: Session) -> dict[str, str]:
    rows = db.scalars(select(Setting).where(Setting.key.in_(PUBLIC_SETTING_KEYS))).all()
    values = {key: default for key, default in PUBLIC_SETTING_KEYS.items()}
    for row in rows:
        values[row.key] = row.value or ""
    return values


def update_public_settings(db: Session, payload: dict[str, str]) -> dict[str, str]:
    for key in PUBLIC_SETTING_KEYS:
        if key not in payload:
            continue
        value = (payload.get(key) or "").strip()
        row = db.scalars(select(Setting).where(Setting.key == key)).first()
        if row:
            row.value = value
            row.is_secret = False
        else:
            db.add(Setting(key=key, value=value, is_secret=False))
    db.commit()
    return get_public_settings(db)


def get_public_setting(db: Session, key: str, default: str = "") -> str:
    if key not in PUBLIC_SETTING_KEYS:
        return default
    row = db.scalars(select(Setting).where(Setting.key == key)).first()
    return (row.value or default) if row else default
