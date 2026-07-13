"""
seed_demo_data.py
------------------
Optional: inserts a demo student, marks them Present today, and logs a
sample lesson so you can immediately test the Mini App quiz flow end-to-end.

Run:  python seed_demo_data.py
(Requires DATABASE_URL to already be reachable — start Postgres first if
using docker-compose: `docker compose up -d db`.)
"""
import asyncio
import datetime

from app.database import init_models, AsyncSessionLocal
from app.models import Student, Attendance, LessonLog


async def main():
    await init_models()
    async with AsyncSessionLocal() as db:
        student = Student(telegram_id="000000001", full_name="Demo Student",
                           username="demostudent", class_group="Demo")
        db.add(student)
        await db.flush()

        db.add(Attendance(student_id=student.id, date=datetime.date.today(), status="Present"))
        db.add(LessonLog(
            date=datetime.date.today(),
            topic="Present Perfect Tense",
            vocabulary="journey:a trip somewhere;ancient:very old;discover:to find something new",
            grammar="Present perfect for life experience | I have visited Paris twice.",
            listening_text="I have visited Paris twice.",
        ))
        await db.commit()
    print("Seeded 1 demo student (Telegram ID 000000001, marked Present today) and 1 lesson log.")
    print("Replace the demo telegram_id with a real one from @userinfobot to test via the actual bot.")


if __name__ == "__main__":
    asyncio.run(main())
