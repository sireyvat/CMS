"""app/routers/auth.py -- Teacher dashboard login/logout (session cookie)."""
from fastapi import APIRouter, Form, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Teacher
from app.security import verify_teacher_credentials, create_teacher_session_token, get_password_hash

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if not verify_teacher_credentials(username, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    
    token = create_teacher_session_token(username) 
    
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

# --- បន្ថែមមុខងារនេះបណ្តោះអាសន្នដើម្បីបង្កើត Admin ---
@router.get("/emergency-admin")
async def create_emergency_admin(db: Session = Depends(get_db)):
    # ពិនិត្យថាមាន admin រួចឬនៅ
    existing_admin = db.query(Teacher).filter(Teacher.username == "admin").first()
    if existing_admin:
        return {"message": "Admin already exists!"}
    
    # បង្កើត admin ថ្មី
    new_admin = Teacher(username="admin", password=get_password_hash("password123"))
    db.add(new_admin)
    db.commit()
    return {"message": "Admin account created! Username: admin, Password: password123"}
# ----------------------------------------------------

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("teacher_session")
    return response
