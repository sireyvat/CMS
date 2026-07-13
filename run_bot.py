"""
run_bot.py
----------
Minimal long-polling loop that only handles /start (opens the Mini App).
Run this as a separate process/container alongside the FastAPI app:

    python run_bot.py

For production you may prefer a Telegram webhook pointed at a FastAPI route
instead of polling — both are valid; polling is simpler to deploy and is
used here for clarity.
"""
import asyncio
import httpx

from app.config import settings
from app.telegram_bot import send_webapp_launch_button, set_bot_commands, API_BASE


async def poll_loop():
    await set_bot_commands()
    offset = 0
    async with httpx.AsyncClient(timeout=35) as client:
        print("Bot polling started...")
        while True:
            try:
                resp = await client.get(f"{API_BASE}/getUpdates", params={"offset": offset, "timeout": 30})
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if message and message.get("text", "").startswith("/start"):
                        chat_id = message["chat"]["id"]
                        await send_webapp_launch_button(chat_id)
            except httpx.HTTPError as e:
                print("Polling error:", e)
                await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(poll_loop())
