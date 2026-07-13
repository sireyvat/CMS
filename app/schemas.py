"""app/schemas.py -- Pydantic I/O models for the API."""
import datetime
from pydantic import BaseModel


class StudentIn(BaseModel):
    telegram_id: str
    full_name: str
    username: str | None = None
    class_group: str = "General"


class StudentOut(StudentIn):
    id: int
    is_active: bool
    model_config = {"from_attributes": True}


class AttendanceIn(BaseModel):
    student_id: int
    date: datetime.date
    status: str  # 'Present' | 'Absent'


class LessonLogIn(BaseModel):
    date: datetime.date
    topic: str
    vocabulary: str = ""
    grammar: str = ""
    listening_text: str = ""


class ExamGenIn(BaseModel):
    title: str
    range_start: datetime.date
    range_end: datetime.date
    question_count: int | None = None


class QuizAccessRequest(BaseModel):
    init_data: str


class QuizAnswerIn(BaseModel):
    init_data: str
    session_id: int
    question_id: int
    answer: str


class QuizAutoSubmitIn(BaseModel):
    init_data: str
    session_id: int
    reason: str  # 'focus_loss' | 'tab_hidden' | 'devtools_detected' etc.


class QuizSubmitIn(BaseModel):
    init_data: str
    session_id: int
