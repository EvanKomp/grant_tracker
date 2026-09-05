"""Grant Tracker — local work/time management for a freelance grant writer.

Run with:  python3 app.py   (serves http://127.0.0.1:5001 and opens a browser)
Data lives in grants.db next to this file.
"""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

PALETTE = [
    "#C9B8E8",  # lavender
    "#B5CDA3",  # sage
    "#F6C6A8",  # peach
    "#A8C8E1",  # powder
    "#E8B4C8",  # rose
    "#EDE3A2",  # butter
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    color      TEXT    NOT NULL,
    rate       REAL,
    archived   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id),
    title        TEXT    NOT NULL,
    deadline     TEXT    NOT NULL,
    task_type    TEXT    NOT NULL DEFAULT 'grant',
    foa_description TEXT,
    amount_applied  REAL,
    amount_awarded  REAL,
    completed    INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS work_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS todos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id),
    text       TEXT    NOT NULL,
    deadline   TEXT,
    priority   INTEGER NOT NULL DEFAULT 2,
    checked    INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT,
    session_id INTEGER REFERENCES work_sessions(id),
    cleared    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_session
    ON work_sessions((1)) WHERE ended_at IS NULL;
"""


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def create_app(db_path):
    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path)

    with sqlite3.connect(app.config["DB_PATH"]) as init_db:
        init_db.executescript(SCHEMA)
        # migrate databases created before these columns existed
        migrations = {
            "projects": {"rate": "REAL"},
            "tasks": {
                "task_type": "TEXT NOT NULL DEFAULT 'grant'",
                "foa_description": "TEXT",
                "amount_applied": "REAL",
                "amount_awarded": "REAL",
            },
        }
        for table, columns in migrations.items():
            existing = {
                row[1] for row in init_db.execute(f"PRAGMA table_info({table})")
            }
            for col, ddl in columns.items():
                if col not in existing:
                    init_db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def error(msg, code=400):
        return jsonify({"error": msg}), code

    def ok():
        return jsonify({"ok": True})

    def active_session(db):
        return db.execute(
            "SELECT * FROM work_sessions WHERE ended_at IS NULL"
        ).fetchone()

    def todo_project_id(db, todo_id):
        row = db.execute(
            "SELECT t.project_id FROM todos td JOIN tasks t ON t.id = td.task_id"
            " WHERE td.id = ?",
            (todo_id,),
        ).fetchone()
        return row["project_id"] if row else None

    # ---------- pages ----------

    @app.get("/")
    def index():
        return render_template("index.html")

    # ---------- state ----------

    @app.get("/api/state")
    def state():
        db = get_db()
        projects = []
        for p in db.execute(
            "SELECT * FROM projects WHERE archived = 0 ORDER BY created_at, id"
        ).fetchall():
            tasks = []
            for t in db.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND completed = 0"
                " ORDER BY deadline, created_at, id",
                (p["id"],),
            ).fetchall():
                todos = [
                    dict(td)
                    for td in db.execute(
                        "SELECT * FROM todos WHERE task_id = ? AND cleared = 0"
                        " ORDER BY created_at, id",
                        (t["id"],),
                    ).fetchall()
                ]
                tasks.append({**dict(t), "todos": todos})
            projects.append({**dict(p), "tasks": tasks})
        active = active_session(db)
        return jsonify(
            {
                "projects": projects,
                "active_session": dict(active) if active else None,
                "today": date.today().isoformat(),
            }
        )

    # ---------- projects ----------

    def valid_money(value):
        return value is None or (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0
        )

    @app.post("/api/projects")
    def create_project():
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return error("Project name is required")
        rate = data.get("rate")
        if not valid_money(rate):
            return error("Rate must be a non-negative number")
        db = get_db()
        used = {
            r["color"]
            for r in db.execute(
                "SELECT color FROM projects WHERE archived = 0"
            ).fetchall()
        }
        color = next(
            (c for c in PALETTE if c not in used),
            PALETTE[
                db.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
                % len(PALETTE)
            ],
        )
        db.execute(
            "INSERT INTO projects (name, color, rate, created_at) VALUES (?, ?, ?, ?)",
            (name, color, rate, now_iso()),
        )
        db.commit()
        return ok()

    @app.patch("/api/projects/<int:project_id>")
    def edit_project(project_id):
        data = request.json or {}
        db = get_db()
        if "name" in data:
            name = data["name"].strip()
            if not name:
                return error("Project name cannot be empty")
            db.execute(
                "UPDATE projects SET name = ? WHERE id = ?", (name, project_id)
            )
        if "rate" in data:
            if not valid_money(data["rate"]):
                return error("Rate must be a non-negative number")
            db.execute(
                "UPDATE projects SET rate = ? WHERE id = ?",
                (data["rate"], project_id),
            )
        db.commit()
        return ok()

    @app.post("/api/projects/<int:project_id>/archive")
    def archive_project(project_id):
        db = get_db()
        active = active_session(db)
        if active and active["project_id"] == project_id:
            return error("Clock out before archiving this project", 409)
        db.execute("UPDATE projects SET archived = 1 WHERE id = ?", (project_id,))
        db.commit()
        return ok()

    @app.post("/api/projects/<int:project_id>/clear_checked")
    def clear_checked(project_id):
        db = get_db()
        db.execute(
            "UPDATE todos SET cleared = 1 WHERE checked = 1 AND cleared = 0"
            " AND task_id IN (SELECT id FROM tasks WHERE project_id = ?)",
            (project_id,),
        )
        db.commit()
        return ok()

    # ---------- tasks ----------

    @app.post("/api/tasks")
    def create_task():
        data = request.json or {}
        title = data.get("title", "").strip()
        deadline = data.get("deadline", "").strip()
        project_id = data.get("project_id")
        if not (title and deadline and project_id):
            return error("Task needs a project, title, and deadline")
        task_type = data.get("task_type", "grant")
        if task_type not in ("grant", "other"):
            return error("task_type must be 'grant' or 'other'")
        if task_type == "other":
            foa, applied, awarded = None, None, None
        else:
            foa = (data.get("foa_description") or "").strip() or None
            applied = data.get("amount_applied")
            awarded = data.get("amount_awarded")
            if not (valid_money(applied) and valid_money(awarded)):
                return error("Amounts must be non-negative numbers")
        db = get_db()
        db.execute(
            "INSERT INTO tasks (project_id, title, deadline, task_type,"
            " foa_description, amount_applied, amount_awarded, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, title, deadline, task_type, foa, applied, awarded,
             now_iso()),
        )
        db.commit()
        return ok()

    @app.patch("/api/tasks/<int:task_id>")
    def edit_task(task_id):
        data = request.json or {}
        db = get_db()
        if "title" in data:
            title = data["title"].strip()
            if not title:
                return error("Title cannot be empty")
            db.execute("UPDATE tasks SET title = ? WHERE id = ?", (title, task_id))
        if "deadline" in data:
            deadline = data["deadline"].strip()
            if not deadline:
                return error("Tasks must have a deadline")
            db.execute(
                "UPDATE tasks SET deadline = ? WHERE id = ?", (deadline, task_id)
            )
        if "task_type" in data:
            if data["task_type"] not in ("grant", "other"):
                return error("task_type must be 'grant' or 'other'")
            db.execute(
                "UPDATE tasks SET task_type = ? WHERE id = ?",
                (data["task_type"], task_id),
            )
            if data["task_type"] == "other":
                data = {**data, "foa_description": None,
                        "amount_applied": None, "amount_awarded": None}
        if "foa_description" in data:
            foa = (data["foa_description"] or "").strip() or None
            db.execute(
                "UPDATE tasks SET foa_description = ? WHERE id = ?", (foa, task_id)
            )
        for field in ("amount_applied", "amount_awarded"):
            if field in data:
                if not valid_money(data[field]):
                    return error("Amounts must be non-negative numbers")
                db.execute(
                    f"UPDATE tasks SET {field} = ? WHERE id = ?",
                    (data[field], task_id),
                )
        db.commit()
        return ok()

    @app.post("/api/tasks/<int:task_id>/complete")
    def complete_task(task_id):
        db = get_db()
        db.execute(
            "UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?",
            (now_iso(), task_id),
        )
        db.commit()
        return ok()

    @app.delete("/api/tasks/<int:task_id>")
    def delete_task(task_id):
        db = get_db()
        db.execute("DELETE FROM todos WHERE task_id = ?", (task_id,))
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        db.commit()
        return ok()

    # ---------- todos ----------

    @app.post("/api/todos")
    def create_todo():
        data = request.json or {}
        text = data.get("text", "").strip()
        task_id = data.get("task_id")
        if not (text and task_id):
            return error("Todo needs a task and text")
        priority = data.get("priority", 2)
        if priority not in (1, 2, 3):
            return error("Priority must be 1, 2, or 3")
        deadline = (data.get("deadline") or "").strip() or None
        db = get_db()
        db.execute(
            "INSERT INTO todos (task_id, text, deadline, priority, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (task_id, text, deadline, priority, now_iso()),
        )
        db.commit()
        return ok()

    @app.patch("/api/todos/<int:todo_id>")
    def edit_todo(todo_id):
        data = request.json or {}
        db = get_db()
        if "text" in data:
            text = data["text"].strip()
            if not text:
                return error("Todo text cannot be empty")
            db.execute("UPDATE todos SET text = ? WHERE id = ?", (text, todo_id))
        if "deadline" in data:
            deadline = (data["deadline"] or "").strip() or None
            db.execute(
                "UPDATE todos SET deadline = ? WHERE id = ?", (deadline, todo_id)
            )
        if "priority" in data:
            if data["priority"] not in (1, 2, 3):
                return error("Priority must be 1, 2, or 3")
            db.execute(
                "UPDATE todos SET priority = ? WHERE id = ?",
                (data["priority"], todo_id),
            )
        db.commit()
        return ok()

    @app.delete("/api/todos/<int:todo_id>")
    def delete_todo(todo_id):
        db = get_db()
        db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        db.commit()
        return ok()

    @app.post("/api/todos/<int:todo_id>/check")
    def check_todo(todo_id):
        db = get_db()
        project_id = todo_project_id(db, todo_id)
        if project_id is None:
            return error("Todo not found", 404)
        active = active_session(db)
        if active and active["project_id"] == project_id:
            session_id = active["id"]
        else:
            # Checked outside a matching session: credit the most recent
            # clock-in on this project (per user preference).
            row = db.execute(
                "SELECT id FROM work_sessions WHERE project_id = ?"
                " AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            session_id = row["id"] if row else None
        db.execute(
            "UPDATE todos SET checked = 1, checked_at = ?, session_id = ?"
            " WHERE id = ?",
            (now_iso(), session_id, todo_id),
        )
        db.commit()
        return ok()

    @app.post("/api/todos/<int:todo_id>/uncheck")
    def uncheck_todo(todo_id):
        db = get_db()
        db.execute(
            "UPDATE todos SET checked = 0, checked_at = NULL, session_id = NULL"
            " WHERE id = ?",
            (todo_id,),
        )
        db.commit()
        return ok()

    # ---------- clock ----------

    @app.post("/api/clock_in")
    def clock_in():
        project_id = (request.json or {}).get("project_id")
        if not project_id:
            return error("project_id is required")
        db = get_db()
        if active_session(db):
            return error("Already clocked in", 409)
        try:
            db.execute(
                "INSERT INTO work_sessions (project_id, started_at) VALUES (?, ?)",
                (project_id, now_iso()),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return error("Already clocked in", 409)
        return ok()

    @app.post("/api/clock_out")
    def clock_out():
        db = get_db()
        active = active_session(db)
        if not active:
            return error("Not clocked in", 409)
        description = ((request.json or {}).get("description") or "").strip() or None
        db.execute(
            "UPDATE work_sessions SET ended_at = ?, description = ? WHERE id = ?",
            (now_iso(), description, active["id"]),
        )
        db.commit()
        return ok()

    # ---------- list view / report ----------

    @app.get("/api/projects/all")
    def all_projects():
        db = get_db()
        return jsonify(
            {
                "projects": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id, name, color, archived FROM projects"
                        " ORDER BY archived, name COLLATE NOCASE"
                    ).fetchall()
                ]
            }
        )

    @app.get("/api/projects/<int:project_id>/tasks")
    def project_tasks(project_id):
        db = get_db()
        if not db.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone():
            return error("Project not found", 404)
        tasks = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM tasks WHERE project_id = ?"
                " ORDER BY completed_at DESC, deadline",
                (project_id,),
            ).fetchall()
        ]
        return jsonify({"tasks": tasks})

    def fmt_money(v):
        if v is None:
            return "—"
        return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"

    def fmt_day(iso_str):
        d = datetime.fromisoformat(iso_str)
        return f"{d.strftime('%b')} {d.day}, {d.year}"

    @app.get("/report")
    def report():
        project_id = request.args.get("project_id", type=int)
        try:
            since = date.fromisoformat(request.args.get("since", ""))
        except ValueError:
            return "since must be YYYY-MM-DD", 400
        db = get_db()
        project = db.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not project:
            return "Project not found", 404
        grants = db.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND task_type = 'grant'"
            " AND completed = 1 AND completed_at >= ? ORDER BY completed_at",
            (project_id, since.isoformat()),
        ).fetchall()
        rows = [
            {
                "title": g["title"],
                "foa": g["foa_description"] or "—",
                "submitted": fmt_day(g["completed_at"]),
                "applied": fmt_money(g["amount_applied"]),
                "awarded": fmt_money(g["amount_awarded"]),
            }
            for g in grants
        ]
        return render_template(
            "report.html",
            project=project,
            since=fmt_day(since.isoformat()),
            rows=rows,
            total_applied=fmt_money(
                sum(g["amount_applied"] or 0 for g in grants)),
            total_awarded=fmt_money(
                sum(g["amount_awarded"] or 0 for g in grants)),
            generated=fmt_day(date.today().isoformat()),
        )

    # ---------- timeline ----------

    @app.get("/api/timeline")
    def timeline():
        start_str = request.args.get("start", "")
        try:
            week_start = date.fromisoformat(start_str)
        except ValueError:
            return error("start must be YYYY-MM-DD")
        week_end = week_start + timedelta(days=7)
        db = get_db()
        sessions = []
        for s in db.execute(
            "SELECT ws.*, p.name AS project_name, p.color, p.rate"
            " FROM work_sessions ws"
            " JOIN projects p ON p.id = ws.project_id"
            " WHERE ws.started_at < ?"
            " AND (ws.ended_at IS NULL OR ws.ended_at >= ?)"
            " ORDER BY ws.started_at",
            (week_end.isoformat(), week_start.isoformat()),
        ).fetchall():
            checked = [
                dict(row)
                for row in db.execute(
                    "SELECT td.text, t.title AS task_title FROM todos td"
                    " JOIN tasks t ON t.id = td.task_id"
                    " WHERE td.session_id = ? AND td.checked = 1"
                    " ORDER BY td.checked_at, td.id",
                    (s["id"],),
                ).fetchall()
            ]
            sessions.append({**dict(s), "checked_todos": checked})
        return jsonify({"sessions": sessions})

    return app


if __name__ == "__main__":
    import os
    import threading
    import webbrowser

    application = create_app(Path(__file__).parent / "grants.db")
    # The Mac launcher (Grant Tracker.app) opens the browser itself once the
    # server answers, so it sets this to avoid a second tab.
    if not os.environ.get("GRANT_TRACKER_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5001")).start()
    application.run(port=5001, debug=False)
