"""Light API tests for the grant tracker. Run with: python3 -m pytest"""
import sqlite3
import sys
from datetime import date, timedelta
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
