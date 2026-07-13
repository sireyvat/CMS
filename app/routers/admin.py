"""
app/routers/admin.py
---------------------
Server-rendered teacher dashboard. Every route depends on `require_teacher`,
which redirects to /login if the signed session cookie is missing/expired.
"""
import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_teacher
from app.models import Student, Attendance, LessonLog, Gradebook, ExamPaper, QuizQuestion
from app.quiz_engine import build_exam_paper
from app.config import settings

router = APIRouter(dependencies=[Depends(require_teacher)], tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard")
async def dashboard_home(request: Request, db: AsyncSession = Depends(get_db)):
    today = datetime.date.today()
    students_count = (await db.execute(select(func.count(Student.id)))).scalar()
    present_today = (await db.execute(
        select(func.count(Attendance.id)).where(Attendance.date == today, Attendance.status == "Present")
    )).scalar()
    lessons_this_month = (await db.execute(
        select(func.count(LessonLog.id)).where(LessonLog.date >= today.replace(day=1))
    )).scalar()
    cheating_incidents = (await db.execute(select(func.sum(Gradebook.cheating_incidents)))).scalar() or 0

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "today": today, "students_count": students_count,
        "present_today": present_today, "lessons_this_month": lessons_this_month,
        "cheating_incidents": cheating_incidents,
    })


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
@router.get("/students")
async def students_page(request: Request, db: AsyncSession = Depends(get_db)):
    students = (await db.execute(select(Student).order_by(Student.full_name))).scalars().all()
    return templates.TemplateResponse("students.html", {"request": request, "students": students})


@router.post("/students/add")
async def add_student(telegram_id: str = Form(...), full_name: str = Form(...),
                       username: str = Form(""), class_group: str = Form("General"),
                       db: AsyncSession = Depends(get_db)):
    db.add(Student(telegram_id=telegram_id.strip(), full_name=full_name.strip(),
                    username=username.strip() or None, class_group=class_group.strip() or "General"))
    await db.commit()
    return RedirectResponse(url="/students", status_code=303)


@router.post("/students/{student_id}/toggle")
async def toggle_student(student_id: int, db: AsyncSession = Depends(get_db)):
    student = await db.get(Student, student_id)
    if student:
        student.is_active = not student.is_active
        await db.commit()
    return RedirectResponse(url="/students", status_code=303)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
@router.get("/attendance")
async def attendance_page(request: Request, date: str | None = None, db: AsyncSession = Depends(get_db)):
    target_date = datetime.date.fromisoformat(date) if date else datetime.date.today()
    students = (await db.execute(select(Student).where(Student.is_active == True).order_by(Student.full_name))).scalars().all()
    existing = (await db.execute(select(Attendance).where(Attendance.date == target_date))).scalars().all()
    status_by_student = {a.student_id: a.status for a in existing}
    return templates.TemplateResponse("attendance.html", {
        "request": request, "students": students, "status_by_student": status_by_student,
        "target_date": target_date.isoformat(),
    })


@router.post("/attendance/mark")
async def mark_attendance(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    target_date = datetime.date.fromisoformat(form["date"])
    student_ids = [int(sid) for sid in form.getlist("student_id")]
    for sid in student_ids:
        status = form.get(f"status_{sid}", "Absent")
        existing = (await db.execute(
            select(Attendance).where(Attendance.student_id == sid, Attendance.date == target_date)
        )).scalar_one_or_none()
        if existing:
            existing.status = status
        else:
            db.add(Attendance(student_id=sid, date=target_date, status=status))
    await db.commit()
    return RedirectResponse(url=f"/attendance?date={target_date.isoformat()}", status_code=303)


# ---------------------------------------------------------------------------
# Lesson logs
# ---------------------------------------------------------------------------
@router.get("/lessons")
async def lessons_page(request: Request, db: AsyncSession = Depends(get_db)):
    lessons = (await db.execute(select(LessonLog).order_by(LessonLog.date.desc()))).scalars().all()
    return templates.TemplateResponse("lessons.html", {
        "request": request, "lessons": lessons, "today": datetime.date.today().isoformat(),
    })


@router.post("/lessons/add")
async def add_lesson(date: str = Form(...), topic: str = Form(...), vocabulary: str = Form(""),
                      grammar: str = Form(""), listening_text: str = Form(""),
                      db: AsyncSession = Depends(get_db)):
    db.add(LessonLog(date=datetime.date.fromisoformat(date), topic=topic.strip(),
                      vocabulary=vocabulary.strip(), grammar=grammar.strip(),
                      listening_text=listening_text.strip()))
    await db.commit()
    return RedirectResponse(url="/lessons", status_code=303)


@router.post("/lessons/{lesson_id}/delete")
async def delete_lesson(lesson_id: int, db: AsyncSession = Depends(get_db)):
    lesson = await db.get(LessonLog, lesson_id)
    if lesson:
        await db.delete(lesson)
        await db.commit()
    return RedirectResponse(url="/lessons", status_code=303)


# ---------------------------------------------------------------------------
# Gradebook
# ---------------------------------------------------------------------------
@router.get("/gradebook")
async def gradebook_page(request: Request, db: AsyncSession = Depends(get_db)):
    month = datetime.date.today().strftime("%Y-%m")
    rows = (await db.execute(
        select(Gradebook, Student).join(Student, Student.id == Gradebook.student_id)
        .where(Gradebook.month == month).order_by(Gradebook.total_points.desc())
    )).all()
    return templates.TemplateResponse("gradebook.html", {
        "request": request, "rows": rows, "month": month,
    })


# ---------------------------------------------------------------------------
# Exam Paper Generator
# ---------------------------------------------------------------------------
@router.get("/examgen")
async def examgen_page(request: Request, db: AsyncSession = Depends(get_db)):
    papers = (await db.execute(select(ExamPaper).order_by(ExamPaper.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("examgen.html", {
        "request": request, "papers": papers, "today": datetime.date.today().isoformat(),
    })


@router.post("/examgen/generate")
async def generate_exam(title: str = Form(...), range_start: str = Form(...), range_end: str = Form(...),
                         db: AsyncSession = Depends(get_db)):
    start_date = datetime.date.fromisoformat(range_start)
    end_date = datetime.date.fromisoformat(range_end)
    question_ids = await build_exam_paper(db, start_date, end_date, settings.EXAM_QUESTION_COUNT)
    paper = ExamPaper(title=title.strip(), range_start=start_date, range_end=end_date, question_ids=question_ids)
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    return RedirectResponse(url=f"/examgen/{paper.id}/view", status_code=303)


@router.get("/examgen/{paper_id}/view")
async def view_exam(paper_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        return RedirectResponse(url="/examgen", status_code=303)
    q_result = await db.execute(select(QuizQuestion).where(QuizQuestion.id.in_(paper.question_ids)))
    by_id = {q.id: q for q in q_result.scalars().all()}
    ordered = [by_id[qid] for qid in paper.question_ids if qid in by_id]
    sections = {"writing": [], "mcq": [], "listening": []}
    for q in ordered:
        sections.setdefault(q.section, []).append(q)
    return templates.TemplateResponse("exam_view.html", {
        "request": request, "paper": paper, "sections": sections,
    })
