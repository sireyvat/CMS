"""
app/main.py
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
    asyncio.create_task(startup_tasks())

# ២. បង្កើត Route សម្រាប់ Render Health Check (ដាក់នៅទីនេះដើម្បីល្បឿន)
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

# ៣. Routes
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(quiz.router)

# ៤. Static Assets
app.mount("/webapp", StaticFiles(directory="app/static/webapp"), name="webapp")
app.mount("/static", StaticFiles(directory="app/static/dashboard"), name="dashboard_static")

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")
