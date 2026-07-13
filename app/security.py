"""
app/security.py
----------------
Two independent trust boundaries:

1. Students, via the Telegram Mini App: authenticated by cryptographically
   verifying Telegram's `initData` payload (HMAC-SHA256), exactly per
   https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
   NEVER trust a client-supplied telegram_id directly — always re-derive it
   from a verified initData string on every security-sensitive request.

2. The teacher, via the web dashboard: authenticated by username/password
   (bcrypt-hashed) with a signed, expiring session cookie (itsdangerous).
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY, salt="teacher-session")


# ---------------------------------------------------------------------------
# Telegram WebApp initData verification
# ---------------------------------------------------------------------------
class InitDataInvalid(Exception):
    pass


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Validates the `initData` string sent by the Telegram Mini App JS bridge.
    Returns the parsed Telegram user dict on success.
    Raises InitDataInvalid on any failure (bad signature, missing hash, stale auth_date).

    This is the ONLY function allowed to establish "this request really came
    from Telegram user X" — every quiz endpoint depends on it.
    """
    if not init_data:
        raise InitDataInvalid("Missing initData")

    pairs = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataInvalid("No hash field in initData")

    # Build the data-check-string: all key=value pairs (except hash), sorted, newline-joined
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))

    # secret_key = HMAC-SHA256(key="WebAppData", data=bot_token)
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataInvalid("Signature mismatch — initData was not signed by Telegram for this bot")

    auth_date = int(pairs.get("auth_date", "0"))
    if time.time() - auth_date > settings.TELEGRAM_INITDATA_MAX_AGE_SECONDS:
        raise InitDataInvalid("initData is stale — please reopen the quiz from Telegram")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataInvalid("No user field in initData")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise InitDataInvalid(f"Malformed user field: {e}")

    if "id" not in user:
        raise InitDataInvalid("Telegram user object missing id")

    return user  # {'id': 123456, 'first_name': ..., 'username': ..., ...}


# ---------------------------------------------------------------------------
# Teacher dashboard auth
# ---------------------------------------------------------------------------
def verify_teacher_credentials(username: str, password: str) -> bool:
    if username != settings.TEACHER_USERNAME:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), settings.TEACHER_PASSWORD_HASH.encode("utf-8"))
    except ValueError:
        return False  # malformed hash in config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_teacher_session_token() -> str:
    return _serializer.dumps({"role": "teacher", "iat": time.time()})


def read_teacher_session_token(token: str, max_age_seconds: int = 60 * 60 * 12) -> bool:
    """Returns True if the cookie is a valid, unexpired teacher session."""
    try:
        data = _serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("role") == "teacher"
