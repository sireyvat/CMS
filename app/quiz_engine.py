"""
app/quiz_engine.py
-------------------
Builds the 3-section daily quiz (Writing / MCQ / Listening) from lesson logs,
and grades submitted answers. Pure functions + small async DB helpers —
no FastAPI/Telegram concerns here, so it's easy to unit test and reuse for
both the daily quiz and the monthly Exam Paper Generator.
"""
import random
import re
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LessonLog, QuizQuestion


# ---------------------------------------------------------------------------
# Parsing helpers for the teacher's free-text lesson fields
# ---------------------------------------------------------------------------
def parse_vocabulary(vocab_field: str):
    pairs = []
    for chunk in (vocab_field or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            word, meaning = chunk.split(":", 1)
            pairs.append((word.strip(), meaning.strip()))
        else:
            pairs.append((chunk, ""))
    return pairs


def parse_grammar(grammar_field: str):
    if "|" in (grammar_field or ""):
        rule, example = grammar_field.split("|", 1)
        return rule.strip(), example.strip()
    return (grammar_field or "").strip(), ""


def _blank_out(sentence: str, word: str) -> str:
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    blanked = pattern.sub("_____", sentence, count=1)
    return blanked if blanked != sentence else f"_____ ({sentence})"


# ---------------------------------------------------------------------------
# Question builders — persisted so grading is server-side and reproducible
# ---------------------------------------------------------------------------
async def _make_writing_question(db: AsyncSession, lesson: LessonLog) -> QuizQuestion | None:
    rule, example = parse_grammar(lesson.grammar)
    pairs = parse_vocabulary(lesson.vocabulary)
    if example:
        words = [w.strip(string.punctuation) for w in example.split() if len(w.strip(string.punctuation)) > 3]
        if words:
            target = random.choice(words)
            qtext = f"Writing — Fill in the blank ({rule or lesson.topic}):\n{_blank_out(example, target)}"
            q = QuizQuestion(lesson_id=lesson.id, section="writing", question_text=qtext,
                              correct_answer=target, points=10)
            db.add(q)
            await db.flush()
            return q
    if pairs:
        word, meaning = random.choice(pairs)
        qtext = f"Writing — Use the word '{word}' correctly in your own sentence about: {lesson.topic}."
        # Free-response writing question: graded leniently (word must appear) since sentences vary.
        q = QuizQuestion(lesson_id=lesson.id, section="writing", question_text=qtext,
                          correct_answer=word, points=10)
        db.add(q)
        await db.flush()
        return q
    return None


async def _make_mcq_question(db: AsyncSession, lesson: LessonLog, all_lessons: list[LessonLog]) -> QuizQuestion | None:
    pairs = parse_vocabulary(lesson.vocabulary)
    if not pairs:
        return None
    word, meaning = random.choice(pairs)
    if not meaning:
        return None
    # Build distractors from other lessons' vocabulary meanings
    distractor_pool = []
    for l in all_lessons:
        if l.id == lesson.id:
            continue
        for w, m in parse_vocabulary(l.vocabulary):
            if m and m.lower() != meaning.lower():
                distractor_pool.append(m)
    distractors = random.sample(distractor_pool, k=min(3, len(distractor_pool))) if distractor_pool else []
    while len(distractors) < 3:
        distractors.append(f"None of the above ({len(distractors)+1})")
    options = distractors + [meaning]
    random.shuffle(options)
    qtext = f"Multiple Choice — What does '{word}' mean?"
    q = QuizQuestion(lesson_id=lesson.id, section="mcq", question_text=qtext,
                      correct_answer=meaning, options=options, points=10)
    db.add(q)
    await db.flush()
    return q


async def _make_listening_question(db: AsyncSession, lesson: LessonLog) -> QuizQuestion | None:
    text = (lesson.listening_text or "").strip()
    if not text:
        pairs = parse_vocabulary(lesson.vocabulary)
        text = pairs[0][0] if pairs else ""
    if not text:
        return None
    qtext = "Listening — Play the audio and type exactly what you hear."
    # audio_text is synthesized to speech on-demand by the /quiz/audio/{question_id} endpoint,
    # so we never store large binary blobs in the questions table.
    q = QuizQuestion(lesson_id=lesson.id, section="listening", question_text=qtext,
                      correct_answer=text, audio_text=text, points=10)
    db.add(q)
    await db.flush()
    return q


SECTION_BUILDERS = {
    "writing": _make_writing_question,
    "mcq": _make_mcq_question,
    "listening": _make_listening_question,
}


async def _lessons_in_range(db: AsyncSession, start_date, end_date) -> list[LessonLog]:
    result = await db.execute(
        select(LessonLog).where(LessonLog.date >= start_date, LessonLog.date <= end_date)
    )
    return list(result.scalars().all())


async def build_question_set(db: AsyncSession, lessons: list[LessonLog], target_count: int) -> list[int]:
    """Cycles Writing / MCQ / Listening evenly across the given lesson pool. Returns question IDs."""
    if not lessons:
        return []
    sections = ["writing", "mcq", "listening"]
    fail_counts = {s: 0 for s in sections}
    max_fails = 3
    question_ids: list[int] = []
    attempts, max_attempts = 0, target_count * 10

    while len(question_ids) < target_count and attempts < max_attempts:
        attempts += 1
        active = [s for s in sections if fail_counts[s] < max_fails] or sections
        section = active[len(question_ids) % len(active)]
        lesson = random.choice(lessons)
        builder = SECTION_BUILDERS[section]
        q = await builder(db, lesson, lessons) if section == "mcq" else await builder(db, lesson)
        if q:
            question_ids.append(q.id)
            fail_counts[section] = 0
        else:
            fail_counts[section] += 1
    return question_ids


async def build_daily_quiz(db: AsyncSession, quiz_date, target_count: int) -> list[int]:
    """Retrieval practice: pulls from ALL lessons up to and including quiz_date, not just today."""
    lessons = await _lessons_in_range(db, "1970-01-01", quiz_date)
    return await build_question_set(db, lessons, target_count)


async def build_exam_paper(db: AsyncSession, start_date, end_date, target_count: int) -> list[int]:
    """Monthly mock/blueprint exam: pulls ONLY from lessons logged within the given date range."""
    lessons = await _lessons_in_range(db, start_date, end_date)
    return await build_question_set(db, lessons, target_count)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text)


def grade_answer(question: QuizQuestion, student_answer: str) -> tuple[bool, int]:
    correct = _normalize(question.correct_answer)
    given = _normalize(student_answer)

    if question.section == "mcq":
        is_correct = given == correct
        return is_correct, (question.points if is_correct else 0)

    if question.section == "writing" and question.correct_answer:
        # Free writing: award full credit if the required word/phrase appears anywhere
        # in the student's sentence (they're graded on usage, not exact match).
        is_correct = correct in given.split() or correct in given
        return is_correct, (question.points if is_correct else 0)

    # Listening / exact-writing fallback with partial credit for near misses
    is_correct = bool(given) and given == correct
    if not is_correct and given and correct:
        overlap = len(set(given.split()) & set(correct.split()))
        if overlap and overlap / max(len(correct.split()), 1) >= 0.6:
            return True, max(1, question.points - 2)
    return is_correct, (question.points if is_correct else 0)
