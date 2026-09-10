"""Light API tests for the grant tracker. Run with: python3 -m pytest"""
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import PALETTE, create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    application = create_app(tmp_path / "test.db")
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def make_project(client, name="Proj"):
    assert client.post("/api/projects", json={"name": name}).status_code == 200
    return client.get("/api/state").json["projects"][-1]


def make_task(client, project_id, title="Task", deadline="2026-12-01"):
    resp = client.post(
        "/api/tasks",
        json={"project_id": project_id, "title": title, "deadline": deadline},
    )
    assert resp.status_code == 200
    state = client.get("/api/state").json
    project = next(p for p in state["projects"] if p["id"] == project_id)
    return project["tasks"][-1]


def make_todo(client, task_id, text="Todo", priority=2):
    resp = client.post(
        "/api/todos", json={"task_id": task_id, "text": text, "priority": priority}
    )
    assert resp.status_code == 200
    return get_todo_by_text(client, text)


def get_todo_by_text(client, text):
    state = client.get("/api/state").json
    for p in state["projects"]:
        for t in p["tasks"]:
            for td in t["todos"]:
                if td["text"] == text:
                    return td
    return None


def test_color_assignment_cycles_and_reuses(client):
    p1 = make_project(client, "A")
    p2 = make_project(client, "B")
    assert p1["color"] == PALETTE[0]
    assert p2["color"] == PALETTE[1]
    client.post(f"/api/projects/{p1['id']}/archive")
    p3 = make_project(client, "C")
    assert p3["color"] == PALETTE[0]  # freed by archiving A


def test_second_clock_in_conflicts(client):
    p1 = make_project(client, "A")
    p2 = make_project(client, "B")
    assert client.post("/api/clock_in", json={"project_id": p1["id"]}).status_code == 200
    assert client.post("/api/clock_in", json={"project_id": p2["id"]}).status_code == 409
    assert client.post("/api/clock_out", json={}).status_code == 200
    assert client.post("/api/clock_out", json={}).status_code == 409


def test_check_during_matching_session_links(client):
    p = make_project(client)
    t = make_task(client, p["id"])
    td = make_todo(client, t["id"])
    client.post("/api/clock_in", json={"project_id": p["id"]})
    session = client.get("/api/state").json["active_session"]
    client.post(f"/api/todos/{td['id']}/check")
    assert get_todo_by_text(client, "Todo")["session_id"] == session["id"]


def test_check_unclocked_links_to_last_session(client):
    p = make_project(client)
    t = make_task(client, p["id"])
    td1 = make_todo(client, t["id"], "before any session")
    client.post(f"/api/todos/{td1['id']}/check")
    assert get_todo_by_text(client, "before any session")["session_id"] is None

    client.post("/api/clock_in", json={"project_id": p["id"]})
    session = client.get("/api/state").json["active_session"]
    client.post("/api/clock_out", json={"description": "worked"})

    td2 = make_todo(client, t["id"], "after the fact")
    client.post(f"/api/todos/{td2['id']}/check")
    assert get_todo_by_text(client, "after the fact")["session_id"] == session["id"]


def test_check_during_other_projects_session_links_to_own_last(client):
    pa = make_project(client, "A")
    pb = make_project(client, "B")
    ta = make_task(client, pa["id"], "task A")
    tb = make_task(client, pb["id"], "task B")

    client.post("/api/clock_in", json={"project_id": pa["id"]})
    a_session = client.get("/api/state").json["active_session"]
    client.post("/api/clock_out", json={})

    client.post("/api/clock_in", json={"project_id": pb["id"]})
    td = make_todo(client, ta["id"], "A todo during B session")
    client.post(f"/api/todos/{td['id']}/check")
    checked = get_todo_by_text(client, "A todo during B session")
    assert checked["session_id"] == a_session["id"]  # A's last, not B's active


def test_uncheck_unlinks(client):
    p = make_project(client)
    t = make_task(client, p["id"])
    td = make_todo(client, t["id"])
    client.post("/api/clock_in", json={"project_id": p["id"]})
    client.post(f"/api/todos/{td['id']}/check")
    client.post(f"/api/todos/{td['id']}/uncheck")
    after = get_todo_by_text(client, "Todo")
    assert after["checked"] == 0
    assert after["session_id"] is None


def test_clear_checked_hides_from_state_but_not_timeline(client):
    p = make_project(client)
    t = make_task(client, p["id"])
    td = make_todo(client, t["id"], "cleared todo")
    client.post("/api/clock_in", json={"project_id": p["id"]})
    client.post(f"/api/todos/{td['id']}/check")
    client.post("/api/clock_out", json={"description": "session desc"})
    client.post(f"/api/projects/{p['id']}/clear_checked")

    assert get_todo_by_text(client, "cleared todo") is None  # hidden from board
    monday = date.today() - timedelta(days=date.today().weekday())
    timeline = client.get(f"/api/timeline?start={monday.isoformat()}").json
    todos = [td for s in timeline["sessions"] for td in s["checked_todos"]]
    assert {"text": "cleared todo", "task_title": "Task"} in todos


def test_complete_task_removes_from_state(client):
    p = make_project(client)
    t = make_task(client, p["id"])
    make_todo(client, t["id"])
    client.post(f"/api/tasks/{t['id']}/complete")
    state = client.get("/api/state").json
    assert state["projects"][0]["tasks"] == []


def test_archive_blocked_while_clocked_in(client):
    p = make_project(client)
    client.post("/api/clock_in", json={"project_id": p["id"]})
    assert client.post(f"/api/projects/{p['id']}/archive").status_code == 409
    client.post("/api/clock_out", json={})
    assert client.post(f"/api/projects/{p['id']}/archive").status_code == 200


def test_project_rate_roundtrip(client):
    client.post("/api/projects", json={"name": "Rated", "rate": 85})
    p = client.get("/api/state").json["projects"][0]
    assert p["rate"] == 85

    assert client.patch(
        f"/api/projects/{p['id']}", json={"rate": 92.5}
    ).status_code == 200
    assert client.get("/api/state").json["projects"][0]["rate"] == 92.5

    assert client.patch(
        f"/api/projects/{p['id']}", json={"rate": None}
    ).status_code == 200
    assert client.get("/api/state").json["projects"][0]["rate"] is None

    assert client.patch(
        f"/api/projects/{p['id']}", json={"rate": -5}
    ).status_code == 400
    assert client.post(
        "/api/projects", json={"name": "Bad", "rate": "lots"}
    ).status_code == 400


def test_timeline_sessions_carry_project_rate(client):
    client.post("/api/projects", json={"name": "Rated", "rate": 85})
    p = client.get("/api/state").json["projects"][0]
    client.post("/api/clock_in", json={"project_id": p["id"]})
    client.post("/api/clock_out", json={})
    monday = date.today() - timedelta(days=date.today().weekday())
    sessions = client.get(f"/api/timeline?start={monday.isoformat()}").json["sessions"]
    assert sessions[0]["rate"] == 85


def test_grant_fields_roundtrip(client):
    p = make_project(client)
    resp = client.post("/api/tasks", json={
        "project_id": p["id"], "title": "USDA app", "deadline": "2026-12-01",
        "task_type": "grant", "foa_description": "USDA Community Food Projects",
        "amount_applied": 198000,
    })
    assert resp.status_code == 200
    t = client.get("/api/state").json["projects"][0]["tasks"][0]
    assert t["task_type"] == "grant"
    assert t["foa_description"] == "USDA Community Food Projects"
    assert t["amount_applied"] == 198000
    assert t["amount_awarded"] is None

    client.patch(f"/api/tasks/{t['id']}", json={"amount_awarded": 150000.5})
    t = client.get("/api/state").json["projects"][0]["tasks"][0]
    assert t["amount_awarded"] == 150000.5

    # switching to 'other' clears grant fields
    client.patch(f"/api/tasks/{t['id']}", json={"task_type": "other"})
    t = client.get("/api/state").json["projects"][0]["tasks"][0]
    assert t["task_type"] == "other"
    assert t["foa_description"] is None
    assert t["amount_applied"] is None

    assert client.patch(
        f"/api/tasks/{t['id']}", json={"task_type": "banana"}
    ).status_code == 400
    assert client.post("/api/tasks", json={
        "project_id": p["id"], "title": "Bad", "deadline": "2026-12-01",
        "amount_applied": -1,
    }).status_code == 400


def test_all_projects_includes_archived_and_tasks_include_completed(client):
    pa = make_project(client, "Active")
    pb = make_project(client, "Old")
    client.post(f"/api/projects/{pb['id']}/archive")

    projects = client.get("/api/projects/all").json["projects"]
    assert {(p["name"], p["archived"]) for p in projects} == {
        ("Active", 0), ("Old", 1)}

    t = make_task(client, pa["id"], "Submitted grant")
    client.post(f"/api/tasks/{t['id']}/complete")
    tasks = client.get(f"/api/projects/{pa['id']}/tasks").json["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["completed"] == 1
    assert tasks[0]["completed_at"] is not None


def test_report_filters_by_since_date(client):
    p = make_project(client)
    t = make_task(client, p["id"], "Meadowlark education grant")
    client.patch(f"/api/tasks/{t['id']}", json={
        "foa_description": "Youth farm education", "amount_applied": 25000})
    client.post(f"/api/tasks/{t['id']}/complete")

    today = date.today().isoformat()
    resp = client.get(f"/report?project_id={p['id']}&since={today}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Meadowlark education grant" in html
    assert "Youth farm education" in html
    assert "$25,000" in html

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    html = client.get(
        f"/report?project_id={p['id']}&since={tomorrow}").get_data(as_text=True)
    assert "Meadowlark education grant" not in html
    assert "No grants submitted" in html

    assert client.get(f"/report?project_id={p['id']}&since=nope").status_code == 400


def test_timeline_week_filtering_includes_overlap(app, client):
    p = make_project(client)
    with sqlite3.connect(app.config["DB_PATH"]) as db:
        rows = [
            ("2026-08-24T09:00:00", "2026-08-24T11:30:00"),  # in week of Aug 24
            ("2026-08-30T22:00:00", "2026-08-31T01:00:00"),  # spans into Aug 31 week
            ("2026-09-02T14:00:00", "2026-09-02T15:00:00"),  # week of Aug 31 only
        ]
        for start, end in rows:
            db.execute(
                "INSERT INTO work_sessions (project_id, started_at, ended_at)"
                " VALUES (?, ?, ?)",
                (p["id"], start, end),
            )

    week1 = client.get("/api/timeline?start=2026-08-24").json["sessions"]
    assert [s["started_at"] for s in week1] == [
        "2026-08-24T09:00:00", "2026-08-30T22:00:00"]
    week2 = client.get("/api/timeline?start=2026-08-31").json["sessions"]
    assert [s["started_at"] for s in week2] == [
        "2026-08-30T22:00:00", "2026-09-02T14:00:00"]
    assert week2[0]["color"] == p["color"]
    assert week2[0]["project_name"] == p["name"]


# ---------- work session editing ----------

def insert_session(app, project_id, start, end, description=None):
    with sqlite3.connect(app.config["DB_PATH"]) as db:
        cur = db.execute(
            "INSERT INTO work_sessions (project_id, started_at, ended_at, description)"
            " VALUES (?, ?, ?, ?)",
            (project_id, start, end, description),
        )
        return cur.lastrowid


def get_session(app, session_id):
    with sqlite3.connect(app.config["DB_PATH"]) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM work_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def test_edit_session_times_and_description(app, client):
    p = make_project(client)
    sid = insert_session(app, p["id"], "2026-08-24T09:00:00", "2026-08-24T10:00:00")
    resp = client.patch(f"/api/sessions/{sid}", json={
        "started_at": "2026-08-24T08:30",           # datetime-local, no seconds
        "ended_at": "2026-08-24T11:15:00",
        "description": "  budget narrative  ",
    })
    assert resp.status_code == 200
    s = get_session(app, sid)
    assert s["started_at"] == "2026-08-24T08:30:00"
    assert s["ended_at"] == "2026-08-24T11:15:00"
    assert s["description"] == "budget narrative"

    # blank description clears it; untouched fields stay
    client.patch(f"/api/sessions/{sid}", json={"description": ""})
    s = get_session(app, sid)
    assert s["description"] is None
    assert s["started_at"] == "2026-08-24T08:30:00"


def test_edit_session_rejects_bad_input(app, client):
    p = make_project(client)
    sid = insert_session(app, p["id"], "2026-08-24T09:00:00", "2026-08-24T10:00:00")
    bad = [
        {"ended_at": "2026-08-24T08:00"},          # end before start
        {"started_at": "2026-08-24T10:30"},        # start after end
        {"started_at": "yesterday-ish"},
        {"started_at": "2026-08-24T09:00:00+00:00"},  # timezone not allowed
        {"ended_at": None},                        # finished session needs an end
        {"project_id": 999},
        {"project_id": True},
    ]
    for body in bad:
        assert client.patch(f"/api/sessions/{sid}", json=body).status_code == 400, body
    assert client.patch("/api/sessions/4242", json={}).status_code == 404
    assert get_session(app, sid)["started_at"] == "2026-08-24T09:00:00"


def test_sessions_cannot_overlap(app, client):
    pa = make_project(client, "A")
    pb = make_project(client, "B")
    insert_session(app, pa["id"], "2026-08-24T09:00:00", "2026-08-24T11:00:00")
    sid = insert_session(app, pb["id"], "2026-08-24T13:00:00", "2026-08-24T14:00:00")

    resp = client.patch(f"/api/sessions/{sid}", json={"started_at": "2026-08-24T10:30"})
    assert resp.status_code == 400
    assert "Overlaps a A session" in resp.json["error"]
    assert "Aug 24, 2026, 9:00 am – 11:00 am" in resp.json["error"]

    # touching end-to-start is fine
    assert client.patch(
        f"/api/sessions/{sid}", json={"started_at": "2026-08-24T11:00"}
    ).status_code == 200

    # a new manual session overlapping the currently clocked-in one is rejected
    client.post("/api/clock_in", json={"project_id": pa["id"]})
    active = client.get("/api/state").json["active_session"]
    resp = client.post("/api/sessions", json={
        "project_id": pb["id"],
        "started_at": (datetime.fromisoformat(active["started_at"])
                       - timedelta(minutes=5)).isoformat(timespec="seconds"),
        "ended_at": (datetime.fromisoformat(active["started_at"])
                     + timedelta(minutes=5)).isoformat(timespec="seconds"),
    })
    assert resp.status_code == 400
    assert "still clocked in" in resp.json["error"]


def test_add_session_manually(app, client):
    p = make_project(client)
    assert client.post("/api/sessions", json={
        "project_id": p["id"], "started_at": "2026-08-24T09:00",
    }).status_code == 400  # end required
    resp = client.post("/api/sessions", json={
        "project_id": p["id"],
        "started_at": "2026-08-24T09:00",
        "ended_at": "2026-08-24T10:30",
        "description": "forgot to clock in",
    })
    assert resp.status_code == 200
    sessions = client.get("/api/timeline?start=2026-08-24").json["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["started_at"] == "2026-08-24T09:00:00"
    assert sessions[0]["ended_at"] == "2026-08-24T10:30:00"
    assert sessions[0]["description"] == "forgot to clock in"


def test_edit_active_session_start_and_clock_out_by_setting_end(client):
    p = make_project(client)
    client.post("/api/clock_in", json={"project_id": p["id"]})
    active = client.get("/api/state").json["active_session"]
    earlier = (datetime.fromisoformat(active["started_at"])
               - timedelta(minutes=20)).isoformat(timespec="seconds")
    future = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")

    assert client.patch(
        f"/api/sessions/{active['id']}", json={"started_at": future}
    ).status_code == 400
    assert client.patch(
        f"/api/sessions/{active['id']}", json={"started_at": earlier, "ended_at": None}
    ).status_code == 200
    state = client.get("/api/state").json
    assert state["active_session"]["started_at"] == earlier  # still clocked in

    now = datetime.now().isoformat(timespec="seconds")
    assert client.patch(
        f"/api/sessions/{active['id']}", json={"ended_at": now}
    ).status_code == 200
    assert client.get("/api/state").json["active_session"] is None


def test_delete_session_unlinks_todos(app, client):
    p = make_project(client)
    t = make_task(client, p["id"])
    td = make_todo(client, t["id"])
    client.post("/api/clock_in", json={"project_id": p["id"]})
    client.post(f"/api/todos/{td['id']}/check")
    client.post("/api/clock_out", json={})
    sid = get_todo_by_text(client, "Todo")["session_id"]
    assert sid is not None

    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.delete(f"/api/sessions/{sid}").status_code == 404
    after = get_todo_by_text(client, "Todo")
    assert after["checked"] == 1
    assert after["session_id"] is None
    assert get_session(app, sid) is None


def test_change_session_project_unlinks_other_projects_todos(client):
    pa = make_project(client, "A")
    pb = make_project(client, "B")
    ta = make_task(client, pa["id"], "task A")
    tda = make_todo(client, ta["id"], "A todo")
    client.post("/api/clock_in", json={"project_id": pa["id"]})
    client.post(f"/api/todos/{tda['id']}/check")
    client.post("/api/clock_out", json={})
    sid = get_todo_by_text(client, "A todo")["session_id"]

    assert client.patch(
        f"/api/sessions/{sid}", json={"project_id": pb["id"]}
    ).status_code == 200
    assert get_todo_by_text(client, "A todo")["session_id"] is None
    monday = date.today() - timedelta(days=date.today().weekday())
    sessions = client.get(f"/api/timeline?start={monday.isoformat()}").json["sessions"]
    assert sessions[0]["project_name"] == "B"
    assert sessions[0]["checked_todos"] == []


# ---------- hours report ----------

def test_hours_report_blocks_totals_and_options(app, client):
    client.post("/api/projects", json={"name": "Rated", "rate": 80})
    p = client.get("/api/state").json["projects"][0]
    t = make_task(client, p["id"], "Big grant")
    td = make_todo(client, t["id"], "Wrote abstract")
    s1 = insert_session(app, p["id"], "2026-08-24T09:00:00", "2026-08-24T11:30:00",
                        "Budget narrative")
    insert_session(app, p["id"], "2026-08-26T22:00:00", "2026-08-27T00:30:00")
    insert_session(app, p["id"], "2026-09-02T14:00:00", "2026-09-02T15:00:00",
                   "Letters of support")
    insert_session(app, p["id"], "2026-09-20T09:00:00", "2026-09-20T10:00:00")  # after
    with sqlite3.connect(app.config["DB_PATH"]) as db:
        db.execute(
            "UPDATE todos SET checked = 1, checked_at = ?, session_id = ? WHERE id = ?",
            ("2026-08-24T10:00:00", s1, td["id"]),
        )

    base = f"/hours_report?project_id={p['id']}&since=2026-08-24&until=2026-09-06"
    html = client.get(base).get_data(as_text=True)
    assert "Mon Aug 24" in html and "9:00 am – 11:30 am" in html and "2h 30m" in html
    assert "10:00 pm – 12:30 am (Aug 27)" in html         # crosses midnight
    assert "Wed Sep 2" in html
    assert "Sep 20" not in html                            # outside the range
    assert "Week of Aug 24, 2026" in html and "Week of Aug 31, 2026" in html
    assert "3 sessions, 6.00 h" in html and "6h 0m" in html
    assert "$480" in html and "$80/hour" in html
    assert "Budget narrative" not in html                  # options off by default
    assert "Wrote abstract" not in html
    assert "still clocked in" not in html

    html = client.get(base + "&descriptions=1").get_data(as_text=True)
    assert "Budget narrative" in html and "Letters of support" in html
    assert "<th>Description</th>" in html
    assert "Wrote abstract" not in html

    html = client.get(base + "&todos=1").get_data(as_text=True)
    assert "Wrote abstract" in html and "Big grant" in html
    assert "Budget narrative" not in html

    html = client.get(base + "&descriptions=1&todos=1").get_data(as_text=True)
    assert "Description &amp; todos completed" in html

    # a single week has no week rows; an in-progress session gets a footnote
    html = client.get(
        f"/hours_report?project_id={p['id']}&since=2026-08-24&until=2026-08-30"
    ).get_data(as_text=True)
    assert "Week of" not in html and "2 sessions, 5.00 h" in html
    client.post("/api/clock_in", json={"project_id": p["id"]})
    today = date.today().isoformat()
    html = client.get(
        f"/hours_report?project_id={p['id']}&since={today}&until={today}"
    ).get_data(as_text=True)
    assert "No completed work sessions" in html
    assert "still clocked in is not included" in html

    assert client.get(f"/hours_report?project_id={p['id']}&since=nope").status_code == 400
    assert client.get(
        f"/hours_report?project_id={p['id']}&since=2026-09-06&until=2026-09-01"
    ).status_code == 400
    assert client.get("/hours_report?project_id=999&since=2026-09-01").status_code == 404


# ---------- process control ----------

def test_health_identifies_this_process(client):
    import os
    data = client.get("/api/health").json
    assert data == {"app": "grant-tracker", "pid": os.getpid()}


def test_quit_replies_then_runs_hook(app, client):
    import time
    calls = []
    app.config["ON_QUIT"] = lambda: calls.append("quit")
    assert client.post("/api/quit").status_code == 200
    assert calls == []  # not yet: the reply goes out first
    time.sleep(0.6)
    assert calls == ["quit"]


def test_port_helpers():
    import socket
    from app import find_instance, port_is_free

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        port = held.getsockname()[1]
        assert port_is_free(port) is False
        assert find_instance(port) is None  # listening, but not a Grant Tracker
    assert port_is_free(port) is True
