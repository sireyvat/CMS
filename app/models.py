"""
app/models.py
-------------
PostgreSQL schema (works on SQLite too for local dev) covering:
students, attendance, lesson_logs, quiz_questions, quiz_sessions,
quiz_answers, gradebook, exam_papers.
"""
import datetime
from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, ForeignKey, Text, JSON, Float, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    class_group: Mapped[str] = mapped_column(String(80), default="General")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attendance: Mapped[list["Attendance"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    sessions: Mapped[list["QuizSession"]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # 'Present' | 'Absent'
    marked_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped["Student"] = relationship(back_populates="attendance")


class LessonLog(Base):
    __tablename__ = "lesson_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    vocabulary: Mapped[str] = mapped_column(Text, default="")       # "word:meaning;word:meaning"
    grammar: Mapped[str] = mapped_column(Text, default="")           # "rule | example sentence"
    listening_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    questions: Mapped[list["QuizQuestion"]] = relationship(back_populates="lesson", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson_logs.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(20), nullable=False)   # writing | mcq | listening
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)   # MCQ choices
    audio_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # text fed to TTS at request time
    points: Mapped[int] = mapped_column(Integer, default=10)

    lesson: Mapped["LessonLog"] = relationship(back_populates="questions")


class QuizSession(Base):
    """One attempt at a daily quiz. Server owns the deadline — never trust the client's clock."""
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    quiz_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    question_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # in_progress | submitted | auto_submitted | expired
    score: Mapped[int] = mapped_column(Integer, default=0)
    cheating_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    cheating_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="sessions")
    answers: Mapped[list["QuizAnswer"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_answer_once_per_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"))
    student_answer: Mapped[str] = mapped_column(Text, default="")
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    points: Mapped[int] = mapped_column(Integer, default=0)
    answered_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["QuizSession"] = relationship(back_populates="answers")


class Gradebook(Base):
    __tablename__ = "gradebook"
    __table_args__ = (UniqueConstraint("student_id", "month", name="uq_gradebook_student_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    quizzes_taken: Mapped[int] = mapped_column(Integer, default=0)
    cheating_incidents: Mapped[int] = mapped_column(Integer, default=0)


class ExamPaper(Base):
    __tablename__ = "exam_papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    range_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    range_end: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    question_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
