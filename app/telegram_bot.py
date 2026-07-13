"""
app/telegram_bot.py
--------------------
Thin wrapper around the raw Telegram Bot API (no heavy bot framework needed
since this bot's only jobs are: (1) show a button that opens the Mini App,
and (2) push "Cheating Detected" alerts to the teacher). Uses httpx so it
works fine inside the async FastAPI app.
"""
import httpx

from app.config import settings

API_BASE = f"https://api.telegram.org/bot{settings.BOT_TOKEN}"


async def send_webapp_launch_button(chat_id: str):
    """Sent in reply to /start — opens the secure Mini App quiz inside Telegram."""
    payload = {
        "chat_id": chat_id,
        "text": "👋 Welcome! Tap below to open today's English quiz.",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "📝 Open Daily Quiz", "web_app": {"url": f"{settings.WEBAPP_PUBLIC_URL}/webapp/quiz.html"}}
            ]]
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{API_BASE}/sendMessage", json=payload)


async def notify_teacher_cheating(student, session, reason: str):
    """Pushed instantly when the frontend reports focus loss / tab switch during a quiz."""
    if not settings.TEACHER_ALERT_CHAT_ID:
        return
    text = (
        "🚨 *Cheating Detected*\n"
        f"Student: {student.full_name} (@{student.username or 'n/a'})\n"
        f"Quiz date: {session.quiz_date}\n"
        f"Reason: `{reason}`\n"
        f"Score forced to: *0*"
    )
    payload = {"chat_id": settings.TEACHER_ALERT_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(f"{API_BASE}/sendMessage", json=payload)
        except httpx.HTTPError:
            pass  # never let a notification failure break the student's auto-submit flow


async def set_bot_commands():
    commands = [{"command": "start", "description": "Open today's English quiz"}]
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{API_BASE}/setMyCommands", json={"commands": commands})
