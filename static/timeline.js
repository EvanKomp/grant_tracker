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
      <button class="soft-btn" data-act="close">Close</button>
    </div>`);
  c.querySelector('[data-act="close"]').onclick = closeModal;
}

document.addEventListener("DOMContentLoaded", () => {
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
