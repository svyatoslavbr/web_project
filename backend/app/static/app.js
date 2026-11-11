const state = { token: null };
const $ = (id) => document.getElementById(id);

function setMessage(text) { $("message").textContent = text; }

function readToken() { try { return localStorage.getItem("token"); } catch { return null; } }

function saveToken(token) {
  try {
    if (token) { localStorage.setItem("token", token); } else { localStorage.removeItem("token"); }
  } catch {}
}

function setToken(token) { state.token = token; saveToken(token); showSections(Boolean(token)); }

function showSections(loggedIn) {
  $("auth").hidden = loggedIn;
  $("new-task").hidden = !loggedIn;
  $("tasks-section").hidden = !loggedIn;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) { headers["Authorization"] = `Bearer ${state.token}`; }
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if ((response.status === 401 || response.status === 403) && state.token) { setToken(null); }
    const detail = Array.isArray(data.detail) ? data.detail.map((item) => item.msg).join("; ") : data.detail;
    throw new Error(detail || `Помилка ${response.status}`);
  }
  return data;
}

async function register() {
  try {
    await api("/auth/register", { method: "POST", body: JSON.stringify({ email: $("email").value, password: $("password").value }) });
    setMessage("Реєстрацію виконано, тепер увійдіть.");
  } catch (error) { setMessage(error.message); }
}

async function login() {
  try {
    const data = await api("/auth/login", { method: "POST", body: JSON.stringify({ email: $("email").value, password: $("password").value }) });
    setToken(data.access_token);
    setMessage("Вхід виконано.");
    await loadTasks();
  } catch (error) { setMessage(error.message); }
}

function logout() { setToken(null); renderTasks([]); setMessage("Ви вийшли з системи."); }

function updateFields() {
  const generated = $("kind").value === "linear_generated";
  $("generated-fields").hidden = !generated;
  $("json-fields").hidden = generated;
}

function buildPayload() {
  const kind = $("kind").value;
  if (kind === "linear_generated") {
    const n = Number($("n").value);
    const seed = Number($("seed").value || 0);
    if (!Number.isInteger(n) || n < 2 || n > 5000) { throw new Error("Кількість невідомих має бути від 2 до 5000."); }
    return { kind, data: { n, seed } };
  }
  const matrix = JSON.parse($("matrix").value);
  const vector = JSON.parse($("vector").value);
  if (!Array.isArray(matrix) || matrix.length < 1 || matrix.length > 1000) { throw new Error("Матриця має містити від 1 до 1000 рядків."); }
  if (matrix.some((row) => !Array.isArray(row) || row.length !== matrix.length)) { throw new Error("Матриця має бути квадратною."); }
  if (!Array.isArray(vector) || vector.length !== matrix.length) { throw new Error("Довжина вектора має дорівнювати розміру матриці."); }
  return { kind, data: { matrix, vector } };
}

async function submitTask() {
  try {
    const payload = buildPayload();
    await api("/tasks", { method: "POST", body: JSON.stringify(payload) });
    setMessage("Задачу поставлено в чергу.");
    await loadTasks();
  } catch (error) { setMessage(error.message); }
}

async function cancelTask(id) {
  try { await api(`/tasks/${id}/cancel`, { method: "POST" }); await loadTasks(); }
  catch (error) { setMessage(error.message); }
}

function resultText(task) {
  if (task.kind === "linear_system") { return `x = ${JSON.stringify(task.result.x.slice(0, 10))}`; }
  return `max_error = ${task.result.max_error}, iterations = ${task.result.iterations}`;
}

function taskItem(task) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = `#${task.id} ${task.kind}: ${task.status}`;
  const bar = document.createElement("progress");
  bar.max = 100;
  bar.value = task.progress;
  const stage = document.createElement("div");
  stage.textContent = `${task.progress}% - ${task.stage}`;
  item.append(title, bar, stage);
  if (task.status === "queued" && task.queue_position !== null) {
    const queue = document.createElement("div");
    queue.textContent = `Місце в черзі: ${task.queue_position}, орієнтовно ${Math.round(task.eta_seconds)} с`;
    item.append(queue);
  }
  if (task.result) { const result = document.createElement("div"); result.textContent = resultText(task); item.append(result); }
  if (task.error) { const error = document.createElement("div"); error.textContent = `Помилка: ${task.error}`; item.append(error); }
  if (task.status === "queued" || task.status === "running") {
    const cancel = document.createElement("button");
    cancel.textContent = "Скасувати";
    cancel.addEventListener("click", () => cancelTask(task.id));
    item.append(cancel);
  }
  return item;
}

function renderTasks(tasks) { $("tasks").replaceChildren(...tasks.map(taskItem)); }

async function loadTasks() {
  if (!state.token) { return; }
  try { renderTasks(await api("/tasks")); }
  catch (error) { setMessage(error.message); }
}

$("login").addEventListener("click", login);
$("register").addEventListener("click", register);
$("logout").addEventListener("click", logout);
$("submit").addEventListener("click", submitTask);
$("kind").addEventListener("change", updateFields);

const saved = readToken();
if (saved) { setToken(saved); loadTasks(); } else { showSections(false); }
setInterval(loadTasks, 1000);
