# English Classroom Management & High-Security Assessment System

FastAPI + PostgreSQL backend, server-rendered teacher dashboard, and a
Telegram **Mini App** (Web App) for a proctored, timed daily quiz — built
for cloud deployment (Docker / Render).

---

## 1. Architecture at a glance

```
app/
├── main.py            FastAPI entrypoint, mounts routers + static Mini App files
├── config.py           All settings, read from environment (.env)
├── database.py          Async SQLAlchemy engine/session (Postgres in prod, SQLite for local dev)
├── models.py             ORM: students, attendance, lesson_logs, quiz_questions,
│                          quiz_sessions, quiz_answers, gradebook, exam_papers
├── schemas.py              Pydantic request/response models
├── security.py               Telegram initData HMAC verification + teacher session auth
├── dependencies.py             Access-control chain used by every quiz route
├── quiz_engine.py               Builds questions from lesson logs; auto-grades answers
├── telegram_bot.py               Sends the "Open Quiz" button + cheating alerts (httpx, no framework)
├── routers/
│   ├── auth.py                     Teacher login/logout (signed session cookie)
│   ├── admin.py                     Teacher dashboard: students/attendance/lessons/gradebook/examgen
│   └── quiz.py                       Mini App API: access control, answers, focus-loss auto-submit
├── templates/                          Jinja2 teacher dashboard pages
└── static/
    ├── dashboard/style.css              Dashboard CSS
    └── webapp/{quiz.html,quiz.css,quiz.js}   The Telegram Mini App itself

run_bot.py       Long-polling process that replies to /start with the Mini App launch button
seed_demo_data.py  Optional: inserts one demo student + lesson so you can test immediately
Dockerfile / Dockerfile.bot / docker-compose.yml / render.yaml   Deployment
```

Two processes run in production: the **web app** (FastAPI, serves both the
dashboard and the Mini App's API) and the **bot poller** (`run_bot.py`,
only handles `/start`). Both share the same PostgreSQL database.

---

## 2. How the security model actually works

This is the part worth reading carefully, since it's the core requirement.

### 2.1 Identity: Telegram `initData` verification
The Mini App never sends a Telegram user ID directly — that would be
trivially spoofable from browser devtools. Instead, Telegram itself signs a
payload (`initData`) with an HMAC-SHA256 derived from your bot token when
the Mini App is opened. `app/security.py::verify_telegram_init_data()`
re-derives that signature server-side and rejects anything that doesn't
match **or** is older than `TELEGRAM_INITDATA_MAX_AGE_SECONDS`. This was
adversarially tested (tampered payload, wrong bot token, stale timestamp —
all correctly rejected) during development.

### 2.2 Access control chain (`app/dependencies.py::get_verified_student`)
On every quiz request:
1. Verify `initData` signature → get the real Telegram user.
2. Look up a matching, active `Student` row → 403 if not registered.
3. Look up today's `Attendance` row → 403 unless status is exactly `"Present"`.

This runs on **every** quiz API call, not just at Mini App launch, so a
student can't open the app while present and keep using a stale session
after being marked absent retroactively.

### 2.3 The 15-minute deadline is server-owned
`QuizSession.deadline_at` is set once, server-side, when the quiz starts.
The frontend countdown (`quiz.js`) is synced against the server's clock
(`server_time` returned at quiz start) purely for a smooth UI — but every
`/api/quiz/answer` and `/api/quiz/submit` call independently re-checks
`now > deadline_at` against the database. A modified client, a paused
JS timer, or a replayed request cannot extend the deadline.

### 2.4 Anti-cheating: focus-loss auto-submit
`quiz.js` attaches `visibilitychange`, `blur`, and `pagehide` listeners.
The instant any of these fire, it calls `/api/quiz/autosubmit`, which:
- Sets `status = "auto_submitted"`
- **Forces `score = 0`**, even if correct answers were already recorded
- Sets `cheating_flag = True` and stores the reason
- Immediately pushes a Telegram message to `TEACHER_ALERT_CHAT_ID`

This was tested end-to-end: answering a question correctly, then
triggering `autosubmit`, correctly zeroes the score and flags the session.

**Important, honest limitation:** no web technology (JS, CSS, or the
Telegram Mini App platform) can truly *prevent* a screenshot or screen
recording — that capability isn't exposed to web content on iOS, Android,
or desktop. `quiz.css`/`quiz.js` include best-effort deterrents (disabled
text selection/right-click/copy, a faint tracing watermark, blocked
common desktop devtools shortcuts), but the actual security control against
"leaving to look up answers" is the focus-loss detection above, not the
screenshot deterrents. Don't oversell the deterrents to students or in your
own documentation — the real enforcement is the auto-submit + teacher alert.

### 2.5 Teacher dashboard auth
Separate from the above: a single teacher account (bcrypt-hashed password
in `.env`), a signed, `Secure`+`HttpOnly` session cookie (`itsdangerous`),
12-hour expiry. `require_teacher` guards every `/dashboard`, `/students`,
`/attendance`, `/lessons`, `/gradebook`, `/examgen` route.

---

## 3. Local setup

### Requirements
- Python 3.12+, Docker + Docker Compose (recommended), a Telegram bot token from **@BotFather**

### Quick start with Docker Compose (recommended)
```bash
git clone <this project>
cd secure_classroom
cp .env.example .env
# edit .env: set BOT_TOKEN, TEACHER_ALERT_CHAT_ID (optional), WEBAPP_PUBLIC_URL

docker compose up --build
```
- Dashboard: http://localhost:8000 → redirects to `/login`
  (default dev login: `teacher` / `changeme` — **change `TEACHER_PASSWORD_HASH` before real use**)
- Bot: running in the `bot` container, polling for `/start`

### Running without Docker (SQLite, fastest for local dev)
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # leave DATABASE_URL as the sqlite default, or delete that line
uvicorn app.main:app --reload
# in a second terminal:
python run_bot.py
```

### Generate your own teacher password hash
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```
Paste the result into `.env` as `TEACHER_PASSWORD_HASH`.

### Try it immediately with demo data
```bash
python seed_demo_data.py
```
This adds one demo student (Telegram ID `000000001`) marked Present today
with one lesson logged — enough to open `/dashboard` and see it end-to-end.
To actually test the Mini App from your phone, add a **real** student with
your own Telegram numeric ID (get it from `@userinfobot`) via **Students →
Add Student** on the dashboard, mark them Present in **Attendance**, then
message your bot and tap **Open Daily Quiz**.

---

## 4. Cloud deployment (Render)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at the repo — `render.yaml`
   defines a free Postgres database, the web service, and the bot worker.
3. Set the secret env vars Render prompts for: `BOT_TOKEN`,
   `TEACHER_ALERT_CHAT_ID`, `TEACHER_USERNAME`, `TEACHER_PASSWORD_HASH`.
4. After the first deploy, copy the web service's URL (e.g.
   `https://classroom-web.onrender.com`) into `WEBAPP_PUBLIC_URL` for
   **both** services and redeploy — Telegram requires the Mini App to be
   served over HTTPS, which Render provides automatically.
5. In @BotFather: `/mybots` → your bot → **Bot Settings → Menu Button** (or
   just rely on the `/start` message) → set the Web App URL to
   `https://classroom-web.onrender.com/webapp/quiz.html`.

Any other Docker host (Fly.io, Railway, a VPS) works the same way — just
point `DATABASE_URL` at a real PostgreSQL instance and set `WEBAPP_PUBLIC_URL`
to your public HTTPS domain.

---

## 5. Daily teacher workflow

1. **Attendance** page → mark today's Present/Absent (gates quiz access).
2. **Lessons** page → log topic, vocabulary (`word:meaning;word:meaning`),
   grammar (`rule | example sentence`), and a listening sentence.
3. Students present today message the bot and tap **Open Daily Quiz** —
   9 questions (3 Writing, 3 MCQ, 3 Listening) auto-generated from *all*
   lessons logged to date, 15-minute hard deadline.
4. **Gradebook** shows monthly points, quizzes taken, and cheating
   incidents per student.
5. **Exam Generator** → pick a date range (e.g. the whole month) → produces
   a 30-question standardized blueprint exam from every lesson in that
   range, viewable/printable at `/examgen/<id>/view`.

---

## 6. Extending it

- Swap SQLite for Postgres locally too by setting `DATABASE_URL` in `.env` —
  no code changes needed either way (`app/database.py` branches only on the URL scheme).
- Add Alembic migrations for schema changes in production instead of relying
  on `Base.metadata.create_all()` (fine for first deploys, not for later
  schema changes without downtime).
- Swap the bot's long-polling (`run_bot.py`) for a Telegram webhook pointed
  at a new `POST /telegram/webhook` FastAPI route if you want a single
  always-on process instead of two.
