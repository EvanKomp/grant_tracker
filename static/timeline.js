/* Grant Tracker — retrospective timeline view. Uses helpers from board.js. */

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HOUR_LABELS = ["12am", "3am", "6am", "9am", "12pm", "3pm", "6pm", "9pm"];
const DAY_MS = 24 * 60 * 60 * 1000;

function mondayOf(d) {
  const m = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  m.setDate(m.getDate() - ((m.getDay() + 6) % 7)); // getDay(): Sun=0
  return m;
}

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-` +
         `${String(d.getDate()).padStart(2, "0")}`;
}

let timelineWeekStart = mondayOf(new Date());

async function loadTimelineWeek() {
  const data = await api("GET", `/api/timeline?start=${isoDate(timelineWeekStart)}`);
  renderTimeline(data.sessions);
}

function renderTimeline(sessions) {
  const weekEnd = new Date(timelineWeekStart.getTime() + 6 * DAY_MS);
  document.getElementById("week-label").textContent =
    `${fmtDate(isoDate(timelineWeekStart))} – ${fmtDate(isoDate(weekEnd))}, ` +
    `${weekEnd.getFullYear()}`;
  document.getElementById("week-next").disabled =
    timelineWeekStart >= mondayOf(new Date());

  const grid = document.getElementById("timeline-grid");
  grid.innerHTML = "";

  const ruler = el(`<div class="tl-ruler"></div>`);
  for (const label of HOUR_LABELS) ruler.appendChild(el(`<span>${label}</span>`));
  grid.appendChild(ruler);

  const todayIso = isoDate(new Date());
  const now = new Date();
  const tracks = [];

  for (let i = 0; i < 7; i++) {
    const day = new Date(timelineWeekStart.getTime());
    day.setDate(day.getDate() + i);
    const row = el(`
      <div class="tl-row ${isoDate(day) === todayIso ? "today" : ""}">
        <span class="tl-day-label">${DAY_NAMES[i]} ${fmtDate(isoDate(day))}</span>
        <div class="tl-track"></div>
      </div>`);
    grid.appendChild(row);
    tracks.push({ start: day, track: row.querySelector(".tl-track") });
  }

  let anyBars = false;
  for (const s of sessions) {
    const sStart = new Date(s.started_at);
    const sEnd = s.ended_at ? new Date(s.ended_at) : now;
    for (const { start: dayStart, track } of tracks) {
      const dayEnd = new Date(dayStart.getTime() + DAY_MS);
      const segStart = Math.max(sStart.getTime(), dayStart.getTime());
      const segEnd = Math.min(sEnd.getTime(), dayEnd.getTime());
      if (segStart >= segEnd) continue;
      anyBars = true;
      const left = ((segStart - dayStart.getTime()) / DAY_MS) * 100;
      const width = ((segEnd - segStart) / DAY_MS) * 100;
      const bar = el(
        `<div class="tl-bar" style="left:${left}%;width:${width}%;
          background:${esc(s.color)}" title="${esc(s.project_name)}"></div>`);
      bar.onclick = () => openSessionPopup(s);
      track.appendChild(bar);
    }
  }

  if (!anyBars) {
    grid.appendChild(el(`<div class="tl-empty">No work recorded this week.</div>`));
  } else {
    grid.appendChild(renderWeekTotals(sessions, now));
  }
}

function renderWeekTotals(sessions, now) {
  const weekStartMs = timelineWeekStart.getTime();
  const weekEndMs = weekStartMs + 7 * DAY_MS;
  const byProject = new Map();
  for (const s of sessions) {
    const sStart = new Date(s.started_at).getTime();
    const sEnd = (s.ended_at ? new Date(s.ended_at) : now).getTime();
    const ms = Math.min(sEnd, weekEndMs) - Math.max(sStart, weekStartMs);
    if (ms <= 0) continue;
    const row = byProject.get(s.project_id)
      || { name: s.project_name, color: s.color, rate: s.rate, ms: 0 };
    row.ms += ms;
    byProject.set(s.project_id, row);
  }

  const box = el(`<div class="tl-summary"><h3>Week totals</h3></div>`);
  const sumRow = (dotStyle, name, ms, earned, cls = "") =>
    el(`
      <div class="tl-sum-row ${cls}">
        <span class="session-dot" style="${dotStyle}"></span>
        <span class="tl-sum-name">${esc(name)}</span>
        <span class="tl-sum-hours">${fmtDuration(ms)}</span>
        <span class="tl-earned">${earned != null
          ? `$${Math.round(earned).toLocaleString()}` : ""}</span>
      </div>`);

  const rows = [...byProject.values()].sort((a, b) => b.ms - a.ms);
  let totalMs = 0, totalEarned = 0;
  for (const r of rows) {
    const earned = r.rate != null ? (r.ms / 3600000) * r.rate : null;
    totalMs += r.ms;
    totalEarned += earned || 0;
    box.appendChild(sumRow(`background:${esc(r.color)}`, r.name, r.ms, earned));
  }
  if (rows.length > 1) {
    box.appendChild(sumRow("visibility:hidden", "Total", totalMs,
      totalEarned > 0 ? totalEarned : null, "total"));
  }
  return box;
}

function openSessionPopup(s) {
  const start = new Date(s.started_at);
  const end = s.ended_at ? new Date(s.ended_at) : null;
  const times = end
    ? `${fmtTime(start)} – ${fmtTime(end)} (${fmtDuration(end - start)})`
    : `${fmtTime(start)} – now (still clocked in)`;
  const todoItems = s.checked_todos.length
    ? `<ul class="session-todos">${s.checked_todos.map((t) =>
        `<li>${esc(t.text)} <span class="task-ref">— ${esc(t.task_title)}</span></li>`
      ).join("")}</ul>`
    : `<div class="muted">No todos checked during this session.</div>`;
  const c = openModal(`
    <div class="session-head">
      <span class="session-dot" style="background:${esc(s.color)}"></span>
      <h3 style="margin:0">${esc(s.project_name)}</h3>
    </div>
    <div class="session-times">${fmtDate(s.started_at.slice(0, 10))} · ${times}</div>
    <div class="session-desc">${s.description
      ? esc(s.description) : '<span class="muted">No description.</span>'}</div>
    ${todoItems}
    <div class="dialog-actions">
      <button class="ghost-btn" data-act="edit">Edit</button>
      <span class="spacer"></span>
      <button class="soft-btn" data-act="close">Close</button>
    </div>`);
  c.querySelector('[data-act="close"]').onclick = closeModal;
  c.querySelector('[data-act="edit"]').onclick = () => openSessionForm(s);
}

// ---------- editing / adding work sessions ----------

// Re-render whatever is showing after a session changed (board timer and
// timeline bars both depend on sessions).
function afterSessionChange() {
  refresh();
  if (!document.getElementById("timeline-view").hidden) loadTimelineWeek();
}

function projectOptions(projects, selectedId) {
  return projects.map((p) =>
    `<option value="${p.id}" ${p.id === selectedId ? "selected" : ""}>` +
    `${esc(p.name)}${p.archived ? " (archived)" : ""}</option>`).join("");
}

// session: a work_sessions row (from the timeline or state.active_session),
// or null to add a past session by hand.
async function openSessionForm(session) {
  const editing = !!session;
  const stillOpen = editing && !session.ended_at;
  const { projects } = await api("GET", "/api/projects/all");
  if (!projects.length) { toast("Create a project first"); return; }

  let start, end;
  if (editing) {
    start = session.started_at.slice(0, 16);
    end = session.ended_at ? session.ended_at.slice(0, 16) : "";
  } else {
    // default to 9–10 am on today (if the shown week is this week) or Monday
    const today = new Date();
    const day = mondayOf(today).getTime() === timelineWeekStart.getTime()
      ? today : timelineWeekStart;
    start = `${isoDate(day)}T09:00`;
    end = `${isoDate(day)}T10:00`;
  }

  const c = openModal(`
    <h3>${editing ? "Edit work session" : "Add work session"}</h3>
    <label for="sf-project">Project</label>
    <select id="sf-project">${projectOptions(projects, editing ? session.project_id : projects[0].id)}</select>
    <label for="sf-start">Start</label>
    <input id="sf-start" type="datetime-local" value="${start}">
    <label for="sf-end">End${stillOpen ? " (leave blank to stay clocked in)" : ""}</label>
    <input id="sf-end" type="datetime-local" value="${end}">
    <label for="sf-desc">What was worked on (optional)</label>
    <textarea id="sf-desc">${editing ? esc(session.description || "") : ""}</textarea>
    <div class="dialog-actions">
      ${editing ? '<button class="ghost-btn" data-act="delete">Delete session</button>' : ""}
      <span class="spacer"></span>
      <button class="soft-btn" data-act="cancel">Cancel</button>
      <button class="primary-btn" data-act="ok">${editing ? "Save" : "Add session"}</button>
    </div>`);
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  c.querySelector('[data-act="ok"]').onclick = async () => {
    const body = {
      project_id: Number(c.querySelector("#sf-project").value),
      started_at: c.querySelector("#sf-start").value,
      ended_at: c.querySelector("#sf-end").value || null,
      description: c.querySelector("#sf-desc").value,
    };
    if (!body.started_at) { toast("Start is required"); return; }
    if (!body.ended_at && !stillOpen) { toast("End is required"); return; }
    try {
      if (editing) await api("PATCH", `/api/sessions/${session.id}`, body);
      else await api("POST", "/api/sessions", body);
    } catch (e) {
      return; // api() already showed the reason; keep the form open to fix it
    }
    closeModal();
    afterSessionChange();
  };
  if (editing) {
    c.querySelector('[data-act="delete"]').onclick = () => confirmDialog(
      "Delete work session",
      stillOpen
        ? "Delete the session you are clocked into? You will no longer be clocked in."
        : "Delete this work session? Its hours disappear from the timeline and " +
          "exports; todos checked during it are kept but no longer tied to it.",
      "Delete",
      async () => {
        await api("DELETE", `/api/sessions/${session.id}`);
        afterSessionChange();
      });
  }
  c.querySelector("#sf-start").focus();
}

// ---------- hours export ----------

async function openHoursExport() {
  const { projects } = await api("GET", "/api/projects/all");
  if (!projects.length) { toast("No projects yet"); return; }
  const weekEnd = new Date(timelineWeekStart.getTime() + 6 * DAY_MS);
  const c = openModal(`
    <h3>Export hours</h3>
    <label for="hx-project">Project</label>
    <select id="hx-project">${projectOptions(projects, projects[0].id)}</select>
    <label for="hx-since">From</label>
    <input id="hx-since" type="date" value="${isoDate(timelineWeekStart)}">
    <label for="hx-until">To</label>
    <input id="hx-until" type="date" value="${isoDate(weekEnd)}">
    <label class="check-row"><input type="checkbox" id="hx-desc"> Include descriptions</label>
    <label class="check-row"><input type="checkbox" id="hx-todos"> Include todos completed</label>
    <label class="check-row"><input type="checkbox" id="hx-money" checked> Include dollar amounts</label>
    <div class="dialog-actions">
      <button class="soft-btn" data-act="cancel">Cancel</button>
      <button class="primary-btn" data-act="ok">Export PDF</button>
    </div>`);
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  c.querySelector('[data-act="ok"]').onclick = () => {
    const since = c.querySelector("#hx-since").value;
    const until = c.querySelector("#hx-until").value;
    if (!since || !until) { toast("Pick both dates"); return; }
    if (until < since) { toast("The end date is before the start date"); return; }
    const params = new URLSearchParams({
      project_id: c.querySelector("#hx-project").value,
      since, until,
      descriptions: c.querySelector("#hx-desc").checked ? "1" : "0",
      todos: c.querySelector("#hx-todos").checked ? "1" : "0",
      money: c.querySelector("#hx-money").checked ? "1" : "0",
    });
    closeModal();
    window.open(`/hours_report?${params}`, "_blank");
  };
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("session-add").onclick = () => openSessionForm(null);
  document.getElementById("hours-export").onclick = openHoursExport;
  document.getElementById("week-prev").onclick = () => {
    timelineWeekStart = new Date(timelineWeekStart.getTime() - 7 * DAY_MS);
    timelineWeekStart = mondayOf(timelineWeekStart); // guard DST drift
    loadTimelineWeek();
  };
  document.getElementById("week-next").onclick = () => {
    timelineWeekStart = new Date(timelineWeekStart.getTime() + 7 * DAY_MS);
    timelineWeekStart = mondayOf(timelineWeekStart);
    loadTimelineWeek();
  };
});
