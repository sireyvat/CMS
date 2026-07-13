"""
app/security.py
----------------
Two independent trust boundaries:
1. Students, via the Telegram Mini App (HMAC-SHA256).
2. The teacher, via the web dashboard (bcrypt + itsdangerous).
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings
from app.database import AsyncSessionLocal as SessionLocal # បន្ថែមដើម្បីប្រើក្នុង verify_teacher_credentials
from app.models import Teacher        # បន្ថែមដើម្បីប្រើក្នុង verify_teacher_credentials

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY, salt="teacher-session")

# ---------------------------------------------------------------------------
# Telegram WebApp initData verification
# ---------------------------------------------------------------------------
class InitDataInvalid(Exception):
    pass

def verify_telegram_init_data(init_data: str) -> dict:
    if not init_data:
        raise InitDataInvalid("Missing initData")
    
    pairs = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataInvalid("No hash field in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataInvalid("Signature mismatch")

    auth_date = int(pairs.get("auth_date", "0"))
    if time.time() - auth_date > settings.TELEGRAM_INITDATA_MAX_AGE_SECONDS:
        raise InitDataInvalid("initData is stale")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataInvalid("No user field")

    user = json.loads(user_raw)
    return user

# ---------------------------------------------------------------------------
# Teacher dashboard auth (Updated to use Database instead of Settings)
# ---------------------------------------------------------------------------
def verify_teacher_credentials(username: str, password: str) -> bool:
    db = SessionLocal()
    teacher = db.query(Teacher).filter(Teacher.username == username).first()
    db.close()
    
    if not teacher:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), teacher.password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def create_teacher_session_token(username: str) -> str:
    return _serializer.dumps({"role": "teacher", "username": username, "iat": time.time()})

def read_teacher_session_token(token: str, max_age_seconds: int = 60 * 60 * 12) -> bool:
    try:
        data = _serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("role") == "teacher"
