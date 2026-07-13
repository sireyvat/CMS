"""
app/routers/quiz.py
--------------------
Telegram Mini App API. Every route re-verifies the Telegram initData on
every call (never trusts a cached session id alone for identity) and every
time-sensitive route re-checks the SERVER-side deadline stored on the
QuizSession row — the frontend countdown is a UX nicety only, never the
source of truth.
"""
import datetime
import io

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_verified_student
from app.models import QuizSession, QuizQuestion, QuizAnswer, Gradebook
from app.quiz_engine import build_daily_quiz, grade_answer
from app.schemas import QuizAccessRequest, QuizAnswerIn, QuizAutoSubmitIn, QuizSubmitIn
from app.config import settings
from app.telegram_bot import notify_teacher_cheating

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(dt: datetime.datetime) -> datetime.datetime:
    """Some drivers (e.g. SQLite/aiosqlite) return naive datetimes even for
    TIMESTAMP WITH TIME ZONE columns. We always write UTC, so if tzinfo is
    missing we can safely assume UTC. PostgreSQL round-trips tzinfo correctly,
    so this is a no-op in production."""
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


async def _get_owned_session(db: AsyncSession, session_id: int, student_id: int) -> QuizSession:
    result = await db.execute(select(QuizSession).where(QuizSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.student_id != student_id:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    return session


async def _finalize_score(db: AsyncSession, session: QuizSession):
    result = await db.execute(select(QuizAnswer).where(QuizAnswer.session_id == session.id))
    answers = result.scalars().all()
    session.score = sum(a.points for a in answers)

    month = session.quiz_date.strftime("%Y-%m")
    gb_result = await db.execute(
        select(Gradebook).where(Gradebook.student_id == session.student_id, Gradebook.month == month)
    )
    gradebook = gb_result.scalar_one_or_none()
    if not gradebook:
        gradebook = Gradebook(student_id=session.student_id, month=month, total_points=0, quizzes_taken=0, cheating_incidents=0)
        db.add(gradebook)
    gradebook.total_points += session.score
    gradebook.quizzes_taken += 1
    if session.cheating_flag:
        gradebook.cheating_incidents += 1


# ---------------------------------------------------------------------------
# 1. Access control + quiz start
# ---------------------------------------------------------------------------
@router.post("/access")
async def start_quiz(payload: QuizAccessRequest, db: AsyncSession = Depends(get_db)):
    """
    Access Control chain: valid Telegram signature -> registered student ->
    marked Present today. Reuses today's in-progress session if one already
    exists (so a page reload doesn't grant extra time).
    """
    student = await get_verified_student(payload.init_data, db)
    today = datetime.date.today()

    existing = await db.execute(
        select(QuizSession).where(QuizSession.student_id == student.id, QuizSession.quiz_date == today)
    )
    session = existing.scalar_one_or_none()

    if session and session.status != "in_progress":
        return {
            "status": session.status,
            "message": "You have already completed today's quiz.",
            "score": session.score,
        }

    if not session:
        question_ids = await build_daily_quiz(db, today, settings.DAILY_QUIZ_QUESTION_COUNT)
        if not question_ids:
            raise HTTPException(status_code=409, detail="No lesson content available yet for today's quiz.")
        now = _utcnow()
        session = QuizSession(
            student_id=student.id, quiz_date=today, question_ids=question_ids,
            started_at=now, deadline_at=now + datetime.timedelta(seconds=settings.QUIZ_TIME_LIMIT_SECONDS),
            status="in_progress",
        )
        db.add(session)
        await db.flush()

    await db.commit()
    await db.refresh(session)

    q_result = await db.execute(select(QuizQuestion).where(QuizQuestion.id.in_(session.question_ids)))
    questions_by_id = {q.id: q for q in q_result.scalars().all()}
    ordered_questions = [questions_by_id[qid] for qid in session.question_ids if qid in questions_by_id]

    return {
        "session_id": session.id,
        "server_time": _utcnow().isoformat(),
        "deadline_at": _aware(session.deadline_at).isoformat(),
        "questions": [
            {
                "id": q.id,
                "section": q.section,
                "question_text": q.question_text,
                "options": q.options,
                "has_audio": q.section == "listening",
            }
            for q in ordered_questions
        ],
    }


# ---------------------------------------------------------------------------
# 2. Listening audio (generated on demand, never exposes the answer text in a filename/URL)
# ---------------------------------------------------------------------------
@router.get("/audio/{question_id}")
async def get_question_audio(question_id: int, db: AsyncSession = Depends(get_db)):
    from gtts import gTTS

    result = await db.execute(select(QuizQuestion).where(QuizQuestion.id == question_id, QuizQuestion.section == "listening"))
    question = result.scalar_one_or_none()
    if not question or not question.audio_text:
        raise HTTPException(status_code=404, detail="Audio not available")

    buf = io.BytesIO()
    gTTS(text=question.audio_text, lang="en").write_to_fp(buf)
    buf.seek(0)
    return Response(content=buf.read(), media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# 3. Answer submission (graded immediately, deadline re-checked server-side)
# ---------------------------------------------------------------------------
@router.post("/answer")
async def submit_answer(payload: QuizAnswerIn, db: AsyncSession = Depends(get_db)):
    student = await get_verified_student(payload.init_data, db)
    session = await _get_owned_session(db, payload.session_id, student.id)

    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="This quiz session is no longer active.")
    if _utcnow() > _aware(session.deadline_at):
        session.status = "expired"
        session.submitted_at = _utcnow()
        await _finalize_score(db, session)
        await db.commit()
        raise HTTPException(status_code=410, detail="Time is up — quiz has been auto-finalized.")

    q_result = await db.execute(select(QuizQuestion).where(QuizQuestion.id == payload.question_id))
    question = q_result.scalar_one_or_none()
    if not question or question.id not in session.question_ids:
        raise HTTPException(status_code=404, detail="Question not part of this session")

    is_correct, points = grade_answer(question, payload.answer)

    existing = await db.execute(
        select(QuizAnswer).where(QuizAnswer.session_id == session.id, QuizAnswer.question_id == question.id)
    )
    answer_row = existing.scalar_one_or_none()
    if answer_row:
        answer_row.student_answer, answer_row.is_correct, answer_row.points = payload.answer, is_correct, points
    else:
        db.add(QuizAnswer(session_id=session.id, question_id=question.id,
                           student_answer=payload.answer, is_correct=is_correct, points=points))

    await db.commit()
    return {"is_correct": is_correct, "points": points}


# ---------------------------------------------------------------------------
# 4. Focus-loss / anti-cheating auto-submit
# ---------------------------------------------------------------------------
@router.post("/autosubmit")
async def auto_submit(payload: QuizAutoSubmitIn, db: AsyncSession = Depends(get_db)):
    """
    Called the INSTANT the frontend detects tab switch / minimize / blur.
    Per spec: score is forced to 0 and a 'Cheating Detected' flag is raised
    and pushed to the teacher, regardless of how many correct answers were
    already recorded.
    """
    student = await get_verified_student(payload.init_data, db)
    session = await _get_owned_session(db, payload.session_id, student.id)

    if session.status != "in_progress":
        return {"status": session.status}  # already finalized, ignore duplicate beacons

    session.status = "auto_submitted"
    session.submitted_at = _utcnow()
    session.cheating_flag = True
    session.cheating_reason = payload.reason
    session.score = 0  # forced to zero per spec, overriding any correct answers already given

    month = session.quiz_date.strftime("%Y-%m")
    gb_result = await db.execute(
        select(Gradebook).where(Gradebook.student_id == session.student_id, Gradebook.month == month)
    )
    gradebook = gb_result.scalar_one_or_none()
    if not gradebook:
        gradebook = Gradebook(student_id=session.student_id, month=month, total_points=0, quizzes_taken=0, cheating_incidents=0)
        db.add(gradebook)
    gradebook.quizzes_taken += 1
    gradebook.cheating_incidents += 1

    await db.commit()
    await notify_teacher_cheating(student, session, payload.reason)
    return {"status": "auto_submitted", "cheating_flag": True}


# ---------------------------------------------------------------------------
# 5. Normal, on-time submit
# ---------------------------------------------------------------------------
@router.post("/submit")
async def submit_quiz(payload: QuizSubmitIn, db: AsyncSession = Depends(get_db)):
    student = await get_verified_student(payload.init_data, db)
    session = await _get_owned_session(db, payload.session_id, student.id)

    if session.status != "in_progress":
        return {"status": session.status, "score": session.score}

    session.status = "submitted"
    session.submitted_at = _utcnow()
    await _finalize_score(db, session)
    await db.commit()
    return {"status": "submitted", "score": session.score}
