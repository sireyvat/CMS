"""
app/dependencies.py
--------------------
Reusable FastAPI `Depends` functions. Keeping auth logic here (instead of
copy-pasted in every router) is what makes it safe to reason about: every
quiz endpoint that needs "who is this student" goes through
`get_verified_student`, and every dashboard endpoint that needs
"is this the teacher" goes through `require_teacher`.
"""
import datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Student, Attendance
from app.security import verify_telegram_init_data, InitDataInvalid, read_teacher_session_token


async def get_verified_student(
    init_data: str,
    db: AsyncSession,
) -> Student:
    """
    Full access-control chain required by spec:
      1. initData must be cryptographically valid (really from Telegram, for this bot).
      2. The Telegram user must correspond to a registered Student.
      3. That student's Attendance for TODAY must be 'Present'.
    Any failure -> 403. This function is the single choke point quiz routes rely on.
    """
    try:
        tg_user = verify_telegram_init_data(init_data)
    except InitDataInvalid as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Telegram session: {e}")

    telegram_id = str(tg_user["id"])
    result = await db.execute(select(Student).where(Student.telegram_id == telegram_id))
    student = result.scalar_one_or_none()
    if not student or not student.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="You are not registered in this class. Ask your teacher to add you.")

    today = datetime.date.today()
    att_result = await db.execute(
        select(Attendance).where(Attendance.student_id == student.id, Attendance.date == today)
    )
    attendance = att_result.scalar_one_or_none()
    if not attendance or attendance.status != "Present":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="Access denied: you are not marked Present for today's class.")

    return student


async def require_teacher(request: Request) -> bool:
    token = request.cookies.get("teacher_session")
    if not token or not read_teacher_session_token(token):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return True
