/* Grant Tracker — shared helpers + board view. Loaded before timeline.js. */

// ---------- shared helpers ----------

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).error || msg; } catch (e) { /* keep statusText */ }
    toast(msg);
    throw new Error(msg);
  }
  return res.json();
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtDate(iso) { // "2026-09-04" -> "Sep 4"
  const [, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}`;
}

function fmtTime(dt) { // Date -> "2:05 pm"
  let h = dt.getHours();
  const ampm = h >= 12 ? "pm" : "am";
  h = h % 12 || 12;
  return `${h}:${String(dt.getMinutes()).padStart(2, "0")} ${ampm}`;
}

function fmtDuration(ms) {
  const mins = Math.round(ms / 60000);
  const h = Math.floor(mins / 60), m = mins % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

let toastTimer = null;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}

// ---------- modal ----------

const modal = document.getElementById("modal");
const modalContent = document.getElementById("modal-content");

function openModal(html) {
  modalContent.innerHTML = html;
  if (!modal.open) modal.showModal(); // may replace an already-open dialog
  return modalContent;
}

function closeModal() { modal.close(); }

modal.addEventListener("click", (e) => {
  if (e.target === modal) modal.close(); // click on backdrop
});

function confirmDialog(title, message, confirmLabel, onConfirm, danger = true) {
  const c = openModal(`
    <h3>${esc(title)}</h3>
    <p>${esc(message)}</p>
    <div class="dialog-actions">
      <button class="soft-btn" data-act="cancel">Cancel</button>
      <button class="${danger ? "danger-btn" : "primary-btn"}" data-act="ok">${esc(confirmLabel)}</button>
    </div>`);
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  c.querySelector('[data-act="ok"]').onclick = () => { closeModal(); onConfirm(); };
}

// ---------- state ----------

let state = { projects: [], active_session: null, today: "" };
const expandedTasks = new Set();

async function refresh() {
  state = await api("GET", "/api/state");
  renderBoard();
}

// ---------- board rendering ----------

const PRI_LABEL = { 1: "H", 2: "M", 3: "L" };

function todoSortKey(a, b) {
  if (a.checked !== b.checked) return a.checked - b.checked;
  if (a.priority !== b.priority) return a.priority - b.priority;
  const ad = a.deadline || "9999", bd = b.deadline || "9999";
  if (ad !== bd) return ad < bd ? -1 : 1;
  return a.created_at < b.created_at ? -1 : 1;
}

function deadlineChip(deadline) {
  let cls = "", note = "";
  if (deadline < state.today) { cls = "overdue"; note = " · overdue"; }
  else if (deadline === state.today) { cls = "due-today"; note = " · today"; }
  return `<span class="chip ${cls}">${fmtDate(deadline)}${note}</span>`;
}

function renderBoard() {
  const container = document.getElementById("columns");
  container.innerHTML = "";
  if (!state.projects.length) {
    container.appendChild(el(
      `<div class="empty-board">No projects yet — add your first with
       <strong>+ New project</strong> above.</div>`));
    return;
  }
  for (const p of state.projects) container.appendChild(renderColumn(p));
}

function renderColumn(p) {
  const active = state.active_session;
  const isActive = active && active.project_id === p.id;
  const col = el(`
    <div class="column ${active && !isActive ? "inactive" : ""}">
      <div class="column-accent" style="background:${esc(p.color)}"></div>
      <div class="column-header">
        <h2>${esc(p.name)}</h2>
        <span class="col-actions">
          <button class="ghost-btn edit-project-btn" title="Edit project">✎</button>
          <button class="ghost-btn archive-btn">Archive</button>
        </span>
      </div>
      <div class="column-body">
        <div class="task-list"></div>
        <button class="ghost-btn add-task-btn">+ Add task</button>
        <div class="agg-section"></div>
        <div class="clock-footer"></div>
      </div>
    </div>`);

  col.querySelector(".edit-project-btn").onclick = () => openProjectForm(p);
  col.querySelector(".archive-btn").onclick = () => confirmArchive(p);
  col.querySelector(".add-task-btn").onclick = () => openTaskForm(p);

  const list = col.querySelector(".task-list");
  if (!p.tasks.length) {
    list.appendChild(el(`<div class="muted">No open tasks.</div>`));
  } else {
    for (const t of p.tasks) list.appendChild(renderTask(p, t));
  }

  renderAggregated(p, col.querySelector(".agg-section"));
  renderClockFooter(p, col.querySelector(".clock-footer"));
  return col;
}

function renderTask(p, t) {
  const expanded = expandedTasks.has(t.id);
  const card = el(`
    <div class="task-card">
      <div class="task-head">
        <button class="chevron">${expanded ? "▾" : "▸"}</button>
        <span class="task-title">${esc(t.title)}</span>
        ${deadlineChip(t.deadline)}
        <span class="task-actions">
          <button class="ghost-btn edit-btn" title="Edit task">✎</button>
          <button class="ghost-btn done-btn" title="Complete task">✓</button>
        </span>
      </div>
    </div>`);

  const toggle = () => {
    expandedTasks.has(t.id) ? expandedTasks.delete(t.id) : expandedTasks.add(t.id);
    renderBoard();
  };
  card.querySelector(".chevron").onclick = toggle;
  card.querySelector(".task-title").onclick = toggle;
  card.querySelector(".edit-btn").onclick = () => openTaskForm(p, t);
  card.querySelector(".done-btn").onclick = () => confirmDialog(
    "Complete task",
    `Mark “${t.title}” complete? It leaves the board; its history is kept.`,
    "Complete",
    async () => { await api("POST", `/api/tasks/${t.id}/complete`); refresh(); },
    false);

  if (expanded) {
    const box = el(`<div class="task-todos"></div>`);
    const todos = [...t.todos].sort(todoSortKey);
    if (!todos.length) box.appendChild(el(`<div class="muted">No todos yet.</div>`));
    for (const td of todos) box.appendChild(renderTodo(td));
    const addBtn = el(`<button class="ghost-btn">+ Add todo</button>`);
    addBtn.onclick = () => openTodoForm(t);
    box.appendChild(addBtn);
    card.appendChild(box);
  }
  return card;
}

function renderTodo(td, taskTitle) {
  const row = el(`
    <div class="todo-row ${td.checked ? "checked" : ""}">
      <input type="checkbox" ${td.checked ? "checked" : ""}>
      <span class="pri pri-${td.priority}">${PRI_LABEL[td.priority]}</span>
      <span class="todo-text">${esc(td.text)}${taskTitle
        ? ` <span class="agg-task-hint">— ${esc(taskTitle)}</span>` : ""}</span>
      ${td.deadline ? deadlineChip(td.deadline) : ""}
      <button class="ghost-btn edit-btn" title="Edit todo">✎</button>
    </div>`);
  row.querySelector("input").onchange = async (e) => {
    await api("POST", `/api/todos/${td.id}/${e.target.checked ? "check" : "uncheck"}`);
    refresh();
  };
  row.querySelector(".edit-btn").onclick = () => openTodoForm(null, td);
  return row;
}

function renderAggregated(p, box) {
  const todos = p.tasks.flatMap((t) =>
    t.todos.map((td) => ({ ...td, taskTitle: t.title }))
  ).sort(todoSortKey);
  const anyChecked = todos.some((td) => td.checked);

  const header = el(`
    <div class="agg-header">
      <h3>All todos</h3>
      ${anyChecked ? '<button class="ghost-btn clear-btn">Clear completed</button>' : ""}
    </div>`);
  box.appendChild(header);
  if (anyChecked) {
    header.querySelector(".clear-btn").onclick = async () => {
      await api("POST", `/api/projects/${p.id}/clear_checked`);
      refresh();
    };
  }
  if (!todos.length) {
    box.appendChild(el(`<div class="muted">Nothing to do — add todos to a task.</div>`));
    return;
  }
  for (const td of todos) box.appendChild(renderTodo(td, td.taskTitle));
}

// ---------- clock ----------

let tickInterval = null;

function renderClockFooter(p, box) {
  const active = state.active_session;
  if (active && active.project_id === p.id) {
    box.appendChild(el(`<span class="timer" id="active-timer">0:00:00</span>`));
    const edit = el(`<button class="ghost-btn" title="Fix the start time">✎</button>`);
    edit.onclick = () => openSessionForm(active); // defined in timeline.js
    box.appendChild(edit);
    const out = el(`<button class="clock-out-btn">Clock out</button>`);
    out.onclick = openClockOutModal;
    box.appendChild(out);
    startTick();
  } else {
    const btn = el(
      `<button class="clock-in-btn" style="background:${esc(p.color)}"
        ${active ? "disabled" : ""}>Clock in</button>`);
    btn.onclick = async () => {
      await api("POST", "/api/clock_in", { project_id: p.id });
      refresh();
    };
    box.appendChild(btn);
  }
}

function startTick() {
  clearInterval(tickInterval);
  const update = () => {
    const elTimer = document.getElementById("active-timer");
    if (!elTimer || !state.active_session) { clearInterval(tickInterval); return; }
    const ms = Date.now() - new Date(state.active_session.started_at).getTime();
    const s = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(s / 3600),
          m = String(Math.floor((s % 3600) / 60)).padStart(2, "0"),
          sec = String(s % 60).padStart(2, "0");
    elTimer.textContent = `${h}:${m}:${sec}`;
  };
  update();
  tickInterval = setInterval(update, 1000);
}

function openClockOutModal() {
  const c = openModal(`
    <h3>Clock out</h3>
    <label for="co-desc">What did you work on? (optional)</label>
    <textarea id="co-desc" placeholder="e.g. Drafted the budget narrative"></textarea>
    <div class="dialog-actions">
      <button class="soft-btn" data-act="cancel">Keep working</button>
      <button class="primary-btn" data-act="ok">Clock out</button>
    </div>`);
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  c.querySelector('[data-act="ok"]').onclick = async () => {
    const description = c.querySelector("#co-desc").value;
    closeModal();
    await api("POST", "/api/clock_out", { description });
    refresh();
  };
  c.querySelector("#co-desc").focus();
}

// ---------- forms ----------

function openProjectForm(project) {
  const editing = !!project;
  const c = openModal(`
    <h3>${editing ? "Edit project" : "New project"}</h3>
    <label for="pf-name">Project name</label>
    <input id="pf-name" placeholder="e.g. Riverside Arts Grant"
      value="${editing ? esc(project.name) : ""}">
    <label for="pf-rate">Hourly rate in $ (optional)</label>
    <input id="pf-rate" type="number" min="0" step="0.01" placeholder="e.g. 85"
      value="${editing && project.rate != null ? esc(project.rate) : ""}">
    <div class="dialog-actions">
      <button class="soft-btn" data-act="cancel">Cancel</button>
      <button class="primary-btn" data-act="ok">${editing ? "Save" : "Create"}</button>
    </div>`);
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  const submit = async () => {
    const name = c.querySelector("#pf-name").value.trim();
    if (!name) { toast("Project name is required"); return; }
    const rateStr = c.querySelector("#pf-rate").value.trim();
    const rate = rateStr === "" ? null : Number(rateStr);
    if (rate !== null && (Number.isNaN(rate) || rate < 0)) {
      toast("Rate must be a non-negative number");
      return;
    }
    closeModal();
    if (editing) await api("PATCH", `/api/projects/${project.id}`, { name, rate });
    else await api("POST", "/api/projects", { name, rate });
    refresh();
  };
  c.querySelector('[data-act="ok"]').onclick = submit;
  c.querySelector("#pf-name").addEventListener("keydown",
    (e) => { if (e.key === "Enter") submit(); });
  c.querySelector("#pf-name").focus();
}

function confirmArchive(p) {
  confirmDialog(
    "Archive project",
    `Archive “${p.name}”? It disappears from the board; its tasks, todos, and ` +
    `time history are kept and still show on the timeline.`,
    "Archive",
    async () => { await api("POST", `/api/projects/${p.id}/archive`); refresh(); });
}

function openTaskForm(p, task, onSave = refresh) {
  const editing = !!task;
  const type = editing ? task.task_type : "grant";
  const c = openModal(`
    <h3>${editing ? "Edit task" : `New task — ${esc(p.name)}`}</h3>
    <label for="tf-title">Title</label>
    <input id="tf-title" value="${editing ? esc(task.title) : ""}">
    <label for="tf-deadline">Deadline</label>
    <input id="tf-deadline" type="date" value="${editing ? esc(task.deadline) : ""}">
    <label for="tf-type">Type</label>
    <select id="tf-type">
      <option value="grant" ${type === "grant" ? "selected" : ""}>Grant</option>
      <option value="other" ${type === "other" ? "selected" : ""}>Other</option>
    </select>
    <div id="tf-grant-fields" ${type === "other" ? "hidden" : ""}>
      <label for="tf-foa">FOA description</label>
      <textarea id="tf-foa" placeholder="Funding opportunity, program, agency…"
        >${editing ? esc(task.foa_description || "") : ""}</textarea>
      <label for="tf-applied">Amount applied for in $ (optional)</label>
      <input id="tf-applied" type="number" min="0" step="0.01"
        value="${editing && task.amount_applied != null ? esc(task.amount_applied) : ""}">
      <label for="tf-awarded">Amount awarded in $ (optional)</label>
      <input id="tf-awarded" type="number" min="0" step="0.01"
        value="${editing && task.amount_awarded != null ? esc(task.amount_awarded) : ""}">
    </div>
    <div class="dialog-actions">
      ${editing ? '<button class="ghost-btn" data-act="delete">Delete task</button>' : ""}
      <span class="spacer"></span>
      <button class="soft-btn" data-act="cancel">Cancel</button>
      <button class="primary-btn" data-act="ok">${editing ? "Save" : "Add task"}</button>
    </div>`);
  c.querySelector("#tf-type").onchange = (e) => {
    c.querySelector("#tf-grant-fields").hidden = e.target.value === "other";
  };
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  c.querySelector('[data-act="ok"]').onclick = async () => {
    const title = c.querySelector("#tf-title").value.trim();
    const deadline = c.querySelector("#tf-deadline").value;
    if (!title || !deadline) { toast("Title and deadline are required"); return; }
    const task_type = c.querySelector("#tf-type").value;
    const money = (sel) => {
      const v = c.querySelector(sel).value.trim();
      return v === "" ? null : Number(v);
    };
    const body = { title, deadline, task_type };
    if (task_type === "grant") {
      body.foa_description = c.querySelector("#tf-foa").value.trim() || null;
      body.amount_applied = money("#tf-applied");
      body.amount_awarded = money("#tf-awarded");
      for (const amt of [body.amount_applied, body.amount_awarded]) {
        if (amt !== null && (Number.isNaN(amt) || amt < 0)) {
          toast("Amounts must be non-negative numbers");
          return;
        }
      }
    }
    closeModal();
    if (editing) await api("PATCH", `/api/tasks/${task.id}`, body);
    else await api("POST", "/api/tasks", { ...body, project_id: p.id });
    onSave();
  };
  if (editing) {
    c.querySelector('[data-act="delete"]').onclick = () => confirmDialog(
      "Delete task",
      `Delete “${task.title}” and all its todos? This cannot be undone.`,
      "Delete",
      async () => { await api("DELETE", `/api/tasks/${task.id}`); onSave(); });
  }
  c.querySelector("#tf-title").focus();
}

function openTodoForm(task, todo) {
  const editing = !!todo;
  const c = openModal(`
    <h3>${editing ? "Edit todo" : `New todo — ${esc(task.title)}`}</h3>
    <label for="df-text">Todo</label>
    <input id="df-text" value="${editing ? esc(todo.text) : ""}">
    <label for="df-priority">Priority</label>
    <select id="df-priority">
      <option value="1">High</option>
      <option value="2" selected>Medium</option>
      <option value="3">Low</option>
    </select>
    <label for="df-deadline">Deadline (optional)</label>
    <input id="df-deadline" type="date" value="${editing ? esc(todo.deadline || "") : ""}">
    <div class="dialog-actions">
      ${editing ? '<button class="ghost-btn" data-act="delete">Delete todo</button>' : ""}
      <span class="spacer"></span>
      <button class="soft-btn" data-act="cancel">Cancel</button>
      <button class="primary-btn" data-act="ok">${editing ? "Save" : "Add todo"}</button>
    </div>`);
  if (editing) c.querySelector("#df-priority").value = String(todo.priority);
  c.querySelector('[data-act="cancel"]').onclick = closeModal;
  c.querySelector('[data-act="ok"]').onclick = async () => {
    const text = c.querySelector("#df-text").value.trim();
    if (!text) { toast("Todo text is required"); return; }
    const body = {
      text,
      priority: Number(c.querySelector("#df-priority").value),
      deadline: c.querySelector("#df-deadline").value || null,
    };
    closeModal();
    if (editing) await api("PATCH", `/api/todos/${todo.id}`, body);
    else await api("POST", "/api/todos", { ...body, task_id: task.id });
    refresh();
  };
  if (editing) {
    c.querySelector('[data-act="delete"]').onclick = () => confirmDialog(
      "Delete todo",
      `Delete “${todo.text}”? This cannot be undone.`,
      "Delete",
      async () => { await api("DELETE", `/api/todos/${todo.id}`); refresh(); });
  }
  c.querySelector("#df-text").focus();
}

// ---------- view switching ----------

function switchView(name) {
  for (const view of ["board", "timeline", "list"]) {
    document.getElementById(`${view}-view`).hidden = name !== view;
    document.getElementById(`nav-${view}`).classList.toggle("active", name === view);
  }
  if (name === "timeline") loadTimelineWeek(); // defined in timeline.js
  if (name === "list") loadListView();         // defined in list.js
}

function applyHash() {
  const name = location.hash.slice(1);
  switchView(name === "timeline" || name === "list" ? name : "board");
}

function quitApp() {
  confirmDialog(
    "Quit Grant Tracker",
    "This stops the app on this computer. Everything is saved; start it again " +
    "any time by double-clicking Grant Tracker (or running python3 app.py).",
    "Quit",
    async () => {
      await api("POST", "/api/quit");
      clearInterval(tickInterval);
      document.querySelector("main").innerHTML =
        `<div class="empty-board">Grant Tracker has stopped. You can close this tab.</div>`;
    },
    false);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("quit-btn").onclick = quitApp;
  document.getElementById("new-project-btn").onclick = () => openProjectForm();
  for (const view of ["board", "timeline", "list"]) {
    document.getElementById(`nav-${view}`).onclick = () => {
      location.hash = `#${view}`;
    };
  }
  window.addEventListener("hashchange", applyHash);
  refresh().then(applyHash);
});
