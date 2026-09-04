# Grant Tracker

A small local work/time management board for a freelance grant writer:
projects as columns, tasks with deadlines, prioritized todos, per-project
clock in/out, and a retrospective timeline of when work happened.

## Setup (once)

```bash
pip3 install -r requirements.txt
```

## Run

```bash
python3 app.py
```

This starts a local server and opens http://127.0.0.1:5001 in your browser.
All data is stored in `grants.db` next to `app.py` — back it up by copying
that one file.

## Using it

- **+ New project** adds a column (each gets its own pastel color).
- **+ Add task** inside a column; every task has a deadline. Click a task
  to expand its todos; todos have a priority (High/Med/Low) and an optional
  deadline.
- **All todos** below the tasks is the project's combined todo list, sorted
  by priority.
- **Clock in** at the bottom of a column starts a timer and dims the other
  projects. **Clock out** asks for an optional note; any todos you checked
  while clocked in are recorded with that session (todos checked while not
  clocked in count toward the project's most recent session).
- **Clear completed** tidies checked todos off the board; they stay in the
  session history.
- **Timeline** (top nav) shows past weeks with a bar for each work session,
  placed at the time of day it happened. Click a bar to see the note and
  the todos checked during it. Below the grid, **Week totals** lists hours
  per project for that week.
- Projects can optionally have an **hourly rate** (set it when creating a
  project, or later via the ✎ button in the column header). When set, the
  week totals also show earnings in light grey next to the hours.
- Tasks are usually grant applications, so each task has a type: **grant**
  (the default) or **other**. Grant tasks can carry an FOA description, an
  amount applied for, and an amount awarded — editable from the task's ✎
  dialog on the board or from the List tab.
- **List** (top nav) shows every task for a chosen project — including
  archived projects and completed tasks — with FOA description, submission
  date (when the task was completed), and the applied/awarded amounts.
  **Export PDF** opens a print-ready report of all grants submitted since a
  date you pick; use the browser print dialog's "Save as PDF".

## Tests

```bash
pip3 install pytest
python3 -m pytest
```
