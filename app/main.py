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

from app.database import init_models
from app.routers import auth, admin, quiz

app = FastAPI(title="English Classroom Management & High-Security Assessment System")


@app.on_event("startup")
async def on_startup():
    await init_models()


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(quiz.router)

# Telegram Mini App static assets (quiz.html / quiz.js / quiz.css)
app.mount("/webapp", StaticFiles(directory="app/static/webapp"), name="webapp")
# Dashboard static assets (css)
app.mount("/static", StaticFiles(directory="app/static/dashboard"), name="dashboard_static")


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


# បន្ថែមនៅក្នុង app/main.py
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}
