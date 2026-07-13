"""
app/main.py
-----------
FastAPI application entrypoint.

Run locally:   uvicorn app.main:app --reload
Run in Docker: see Dockerfile / docker-compose.yml
"""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import asyncio

from app.database import init_models
from app.routers import auth, admin, quiz

app = FastAPI(title="English Classroom Management & High-Security Assessment System")

# ១. បង្កើតមុខងារសម្រាប់ Startup ដាច់ដោយឡែក
async def startup_tasks():
    try:
        await init_models()
    except Exception as e:
        print(f"Startup error: {e}")

@app.on_event("startup")
async def on_startup():
    # ប្រើ asyncio.create_task ដើម្បីកុំឱ្យ Database ឃាំង (Block) ដំណើរការ Startup របស់ App
    asyncio.create_task(startup_tasks())

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(quiz.router)

# 2. បង្កើត Route នេះឱ្យនៅខាងលើគេដើម្បីល្បឿន
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

# Telegram Mini App static assets
app.mount("/webapp", StaticFiles(directory="app/static/webapp"), name="webapp")
# Dashboard static assets
app.mount("/static", StaticFiles(directory="app/static/dashboard"), name="dashboard_static")

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")
