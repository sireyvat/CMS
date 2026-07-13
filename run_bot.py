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
import os
import sys
import httpx
import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.telegram_bot import send_webapp_launch_button, set_bot_commands, API_BASE

# បង្កើត Web Server ក្លែងក្លាយដើម្បីដោះស្រាយបញ្ហា Port Check របស់ Render Free Plan
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Bot is running successfully", "mode": "Free Plan Web Worker"}

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

async def main():
    # ចាប់យក Port ដែល Render ផ្ដល់ឱ្យ (លំនាំដើមគឺ 10000 ឬ 8000)
    port = int(os.environ.get("PORT", 8000))
    
    # កំណត់រចនាសម្ព័ន្ធដំណើរការ Web Server (Uvicorn)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    
    # ដំណើរការទាំង Web Server ក្លែងក្លាយ និង Polling Loop របស់ Bot ទន្ទឹមគ្នាក្នុងពេលតែមួយ
    await asyncio.gather(
        server.serve(),
        poll_loop()
    )

if __name__ == "__main__":
    # បើដំណើរការលើ Windows ត្រូវកំណត់ Event Loop Policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    # រត់មុខងារ main() តែមួយគត់ដើម្បីដំណើរការទាំង Web Server ផង និង Bot ផងទន្ទឹមគ្នា
    asyncio.run(main())