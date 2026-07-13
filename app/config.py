"""
app/config.py
-------------
All environment-driven configuration in one place. Nothing secret is
hard-coded; everything comes from the environment / .env file so the
same image can be deployed to Render, Fly.io, Railway, etc. unchanged.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    # Production: postgresql+asyncpg://user:pass@host:5432/dbname
    # Local/dev fallback: sqlite+aiosqlite:///./classroom.db
    DATABASE_URL: str = "sqlite+aiosqlite:///./classroom.db"

    # --- Telegram ---
    BOT_TOKEN: str = "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE"
    TEACHER_ALERT_CHAT_ID: str = ""          # where "Cheating Detected" alerts are sent
    WEBAPP_PUBLIC_URL: str = "https://your-domain.example.com"  # public HTTPS URL of this app
    TELEGRAM_INITDATA_MAX_AGE_SECONDS: int = 3600  # reject stale initData

    # --- Teacher dashboard auth ---
    TEACHER_USERNAME: str = "teacher"
    # Generate with: python -c "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"
    TEACHER_PASSWORD_HASH: str = "$2b$12$0AkCy.IGsICzHKqlNw927uhUpOM1xby1zszl.gtKcEFg6ZJi7OS2G"  # = "changeme"
    SESSION_SECRET_KEY: str = "please-change-this-in-production"

    # --- Quiz security rules ---
    QUIZ_TIME_LIMIT_SECONDS: int = 15 * 60   # 15-minute hard deadline, enforced server-side
    DAILY_QUIZ_QUESTION_COUNT: int = 9        # 3 per section (Writing / MCQ / Listening)

    # --- Exam generator ---
    EXAM_QUESTION_COUNT: int = 30


settings = Settings()
