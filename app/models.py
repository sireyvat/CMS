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

# --- បានបន្ថែម Class Teacher នៅទីនេះ ---
class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
# -------------------------------------

class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # 'Present' | 'Absent'
    marked_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped["Student"] = relationship(back_populates="attendance")

# ... (កូដផ្សេងៗទៀតនៅដដែល)
