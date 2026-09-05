# Grant Tracker

A small local work/time management board for a freelance grant writer:
projects as columns, tasks with deadlines, prioritized todos, per-project
clock in/out, and a retrospective timeline of when work happened.

## Mac: run it with a double-click (no Terminal needed)

1. Get the `grant_tracking` folder onto the Mac — clone it with
   [GitHub Desktop](https://desktop.github.com/), or use GitHub's
   **Code → Download ZIP** and unzip it. Put the folder wherever you like
   (Documents is fine), but keep everything inside it together.
2. Open the folder and double-click **Grant Tracker**. The first time, a
   window says it is setting things up; this takes a minute or two and
   needs an internet connection (it installs the app's Python packages into
   a private `.venv` folder inside `grant_tracking`). After that, opening
   it just starts the app and opens it in your browser.
3. Optional: drag **Grant Tracker** onto the Dock so it's one click away.
   Keep the original inside the folder — the Dock icon is a shortcut to it.

To quit: double-click **Grant Tracker** again and choose **Stop Grant
Tracker**. (Closing the browser tab doesn't stop the app; it just keeps
running quietly until you stop it or restart the Mac.)

Things macOS may ask on the first launch:

- **"Grant Tracker needs Python 3"** — Python isn't installed. Click
  **Download Python**, run the installer that downloads (keep clicking
  Continue), then double-click Grant Tracker again. Any Python 3.9 or newer
  works, including the one from python.org or Homebrew.
- **"GrantTracker would like to access files in your Documents folder"**
  (it may say "Python" instead) — click **OK** / **Allow**. The app reads and
  writes its files inside the `grant_tracking` folder, and macOS asks once
  when that folder is in Documents, Desktop or Downloads. The setup window
  waits until you answer. If you click Don't Allow by mistake, turn it on in
  **System Settings → Privacy & Security → Files and Folders**.
- **"Apple could not verify Grant Tracker is free of malware"** — this only
  happens when the folder came from a downloaded ZIP (the app is not signed
  with an Apple developer certificate). Click **Done**, open
  **System Settings → Privacy & Security**, scroll down to the message
  about Grant Tracker and click **Open Anyway**, then double-click it once
  more. Folders cloned with GitHub Desktop don't trigger this.

If something goes wrong, the app shows a dialog with a **Show Log** button.
Logs live in `~/Library/Logs/Grant Tracker/`.

## Terminal setup (alternative)

```bash
pip3 install -r requirements.txt
python3 app.py
```

This starts a local server and opens http://127.0.0.1:5001 in your browser.

## Your data

All data is stored in `grants.db` next to `app.py`. It is created the first
time the app starts, and backing it up means copying that one file. Deleting
it starts you over with an empty board.

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
