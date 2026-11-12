const $ = (id) => document.getElementById(id);

function readToken() { try { return localStorage.getItem("token"); } catch { return null; } }

function row(cells) {
  const tr = document.createElement("tr");
  for (const value of cells) {
    const td = document.createElement("td");
    td.textContent = value === null || value === undefined ? "-" : String(value);
    tr.append(td);
  }
  return tr;
}

function fillTable(id, rows) { $(id).replaceChildren(...rows.map(row)); }

function render(data) {
  $("content").hidden = false;
  $("message").textContent = "";
  $("queue").textContent = `У черзі: ${data.queue.queued}, виконується: ${data.queue.running}`;
  $("users").textContent = `Користувачів: ${data.users_total}`;
  fillTable("statuses", Object.entries(data.tasks_by_status));
  fillTable("workers", data.workers.map((w) => [w.hostname, w.state, w.current_job]));
  fillTable("containers", data.containers.map((c) => [c.name, c.status, c.cpu_percent, c.memory_mb]));
  $("updated").textContent = `Оновлено: ${new Date().toLocaleTimeString("uk-UA")}`;
}

function showError(text) {
  $("content").hidden = true;
  $("message").textContent = text;
}

let loading = false;

async function load() {
  if (loading) { return; }
  const token = readToken();
  if (!token) { showError("Спершу увійдіть на головній сторінці."); return; }
  loading = true;
  try {
    const response = await fetch("/admin/overview", { headers: { Authorization: `Bearer ${token}` } });
    if (response.status === 403) { showError("Доступ лише для адміністратора"); return; }
    if (response.status === 401) { showError("Сесія завершилась, увійдіть знову на головній сторінці."); return; }
    if (!response.ok) { showError(`Помилка ${response.status}`); return; }
    render(await response.json());
  } catch (error) {
    showError(error.message);
  } finally {
    loading = false;
  }
}

load();
setInterval(load, 3000);
