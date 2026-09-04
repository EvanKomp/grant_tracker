/* Grant Tracker — List view: all tasks per project (incl. archived), grant
   details, and PDF export. Uses helpers from board.js. */

function fmtMoney(v) {
  if (v == null) return "—";
  return "$" + v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

async function loadListView() {
  const { projects } = await api("GET", "/api/projects/all");
  const sel = document.getElementById("list-project");
  const prev = sel.value;
  sel.innerHTML = projects.map((p) =>
    `<option value="${p.id}">${esc(p.name)}${p.archived ? " (archived)" : ""}</option>`
  ).join("");
  if (prev && projects.some((p) => String(p.id) === prev)) sel.value = prev;

  const since = document.getElementById("export-since");
  if (!since.value) since.value = `${new Date().getFullYear()}-01-01`;

  await loadListTasks();
}

async function loadListTasks() {
  const box = document.getElementById("list-table");
  const pid = document.getElementById("list-project").value;
  if (!pid) {
    box.innerHTML = `<div class="empty-board">No projects yet.</div>`;
    return;
  }
  const { tasks } = await api("GET", `/api/projects/${pid}/tasks`);
  renderListTable(tasks);
}

function renderListTable(tasks) {
  const box = document.getElementById("list-table");
  box.innerHTML = "";
  if (!tasks.length) {
    box.appendChild(el(`<div class="empty-board">No tasks in this project yet.</div>`));
    return;
  }

  // open tasks first (soonest deadline on top), then submitted, newest first
  tasks.sort((a, b) => {
    if (a.completed !== b.completed) return a.completed - b.completed;
    if (!a.completed) return a.deadline < b.deadline ? -1 : 1;
    return a.completed_at > b.completed_at ? -1 : 1;
  });

  const wrap = el(`
    <div class="list-card">
      <table class="grant-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>FOA description</th>
            <th>Submitted</th>
            <th class="num">Applied for</th>
            <th class="num">Awarded</th>
            <th></th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>`);
  const tbody = wrap.querySelector("tbody");

  for (const t of tasks) {
    const isGrant = t.task_type === "grant";
    const submitted = t.completed
      ? fmtDate(t.completed_at.slice(0, 10)) + ", " + t.completed_at.slice(0, 4)
      : `<span class="chip">open · due ${fmtDate(t.deadline)}</span>`;
    const row = el(`
      <tr>
        <td>${esc(t.title)}${isGrant ? "" : ' <span class="type-tag">other</span>'}</td>
        <td class="foa-cell">${t.foa_description
          ? esc(t.foa_description) : '<span class="muted">—</span>'}</td>
        <td>${submitted}</td>
        <td class="num">${isGrant ? fmtMoney(t.amount_applied) : "—"}</td>
        <td class="num">${isGrant ? fmtMoney(t.amount_awarded) : "—"}</td>
        <td><button class="ghost-btn" title="Edit task">✎</button></td>
      </tr>`);
    row.querySelector("button").onclick = () =>
      openTaskForm(null, t, () => { refresh(); loadListTasks(); });
    tbody.appendChild(row);
  }
  box.appendChild(wrap);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("list-project").onchange = loadListTasks;
  document.getElementById("export-pdf").onclick = () => {
    const pid = document.getElementById("list-project").value;
    const since = document.getElementById("export-since").value;
    if (!pid) { toast("No project selected"); return; }
    if (!since) { toast("Pick a start date for the export"); return; }
    window.open(`/report?project_id=${pid}&since=${since}`, "_blank");
  };
});
