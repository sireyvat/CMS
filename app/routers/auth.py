"""app/routers/auth.py -- Teacher dashboard login/logout (session cookie)."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.security import verify_teacher_credentials, create_teacher_session_token

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    # ១. ផ្ទៀងផ្ទាត់ Username និង Password
    if not verify_teacher_credentials(username, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    
    # ២. បង្កើត Token ដោយបញ្ជូន username ចូលទៅជាមួយ (កែត្រង់នេះ!)
    token = create_teacher_session_token(username) 
    
    # ៣. កំណត់ Cookie និងបញ្ជូនទៅកាន់ Dashboard
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="teacher_session", 
        value=token, 
        httponly=True, 
        samesite="lax", 
        secure=True, 
        max_age=60 * 60 * 12
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("teacher_session")
    return response
