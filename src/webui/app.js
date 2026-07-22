"use strict";

const API = "/api/v2";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const VIEW_TITLES = {
  dashboard: ["Workspace", "Overview"],
  destinations: ["Outputs", "Destinations"],
  routes: ["Routing", "Routes"],
  tokens: ["Access", "Applications"],
  deliveries: ["Operations", "Delivery history"],
  audit: ["Security", "Audit log"],
  users: ["Administration", "Users"],
  settings: ["Administration", "Settings"],
  data: ["Administration", "Inputs & backups"],
  account: ["Profile", "Account security"],
};
const OUTPUT_NAMES = {
  discord: "Discord",
  teams: "Microsoft Teams",
  slack: "Slack",
  webhook: "Generic webhook",
  mqtt: "MQTT",
  ntfy: "ntfy",
};
const OUTPUT_ICONS = {
  discord: "/ui/icons/discord.svg",
  mqtt: "/ui/icons/mqtt.svg",
  ntfy: "/ui/icons/ntfy.svg",
};
const PRIORITIES = [
  ["critical", "Critical"],
  ["high", "High"],
  ["normal", "Normal"],
  ["low", "Low"],
  ["lowest", "Lowest"],
];
const PT_TRANSLATIONS = {
  "Overview": "Visão geral",
  "Destinations": "Destinos",
  "Routes": "Rotas",
  "Applications": "Aplicações",
  "Delivery history": "Histórico de entregas",
  "Audit log": "Registo de auditoria",
  "Users": "Utilizadores",
  "Settings": "Definições",
  "Data tools": "Ferramentas de dados",
  "Account security": "Segurança da conta",
  "Workspace": "Área de trabalho",
  "Outputs": "Saídas",
  "Routing": "Encaminhamento",
  "Access": "Acesso",
  "Operations": "Operações",
  "Security": "Segurança",
  "Administration": "Administração",
  "Profile": "Perfil",
  "Add destination": "Adicionar destino",
  "Add route": "Adicionar rota",
  "Issue token": "Emitir token",
  "Add user": "Adicionar utilizador",
  "Destinations": "Destinos",
  "Active routes": "Rotas ativas",
  "Recent success": "Sucesso recente",
  "Recent deliveries": "Entregas recentes",
  "View all": "Ver tudo",
  "Source": "Origem",
  "Route": "Rota",
  "Destination": "Destino",
  "Filters": "Filtros",
  "Priority": "Prioridade",
  "Management": "Gestão",
  "Status": "Estado",
  "Time": "Hora",
  "Action": "Ação",
  "Resource": "Recurso",
  "Outcome": "Resultado",
  "Details": "Detalhes",
  "User": "Utilizador",
  "Role": "Função",
  "Last login": "Último início de sessão",
  "Language": "Idioma",
  "Timezone": "Fuso horário",
  "Time format": "Formato horário",
  "Save settings": "Guardar definições",
  "English (United Kingdom)": "Inglês (Reino Unido)",
  "Português (Portugal)": "Português (Portugal)",
  "24-hour": "24 horas",
  "12-hour (AM/PM)": "12 horas (AM/PM)",
  "Change password": "Alterar palavra-passe",
  "Current password": "Palavra-passe atual",
  "New password": "Nova palavra-passe",
  "Confirm new password": "Confirmar nova palavra-passe",
  "Update password": "Atualizar palavra-passe",
  "End session": "Terminar sessão",
  "Sign out": "Terminar sessão",
  "Create backup": "Criar cópia de segurança",
  "Download safe JSON": "Transferir JSON seguro",
  "Preview JSON import": "Pré-visualizar importação JSON",
  "Connected": "Ligado",
  "Offline": "Sem ligação",
  "Enabled": "Ativo",
  "Disabled": "Desativado",
  "Active": "Ativo",
  "Revoked": "Revogado",
  "Preview": "Pré-visualizar",
  "Edit": "Editar",
  "Disable": "Desativar",
  "Enable": "Ativar",
  "Delete": "Eliminar",
  "Reset password": "Repor palavra-passe",
};
const state = {
  user: null,
  csrf: "",
  currentView: "dashboard",
  destinations: [],
  routes: [],
  tokens: [],
  deliveries: [],
  audit: [],
  users: [],
  backups: [],
  configuration: null,
  notices: [],
  metrics: null,
  healthChecks: [],
  backupSettings: null,
  backupLastRun: null,
  historyRange: "1h",
  preferences: { timezone: "Europe/Lisbon", language: "en-GB", time_format: "24" },
  pendingImport: null,
  sessionExpiresAt: null,
  confirmResolve: null,
};

const byId = (id) => document.getElementById(id);

function element(tag, options = {}, children = []) {
  const item = document.createElement(tag);
  if (options.className) item.className = options.className;
  if (options.text !== undefined) item.textContent = String(options.text);
  if (options.title) item.title = options.title;
  if (options.type) item.type = options.type;
  if (options.value !== undefined) item.value = String(options.value);
  if (options.disabled) item.disabled = true;
  if (options.hidden) item.hidden = true;
  for (const [name, value] of Object.entries(options.attributes || {})) {
    item.setAttribute(name, String(value));
  }
  for (const [name, value] of Object.entries(options.dataset || {})) {
    item.dataset[name] = String(value);
  }
  const values = Array.isArray(children) ? children : [children];
  for (const child of values) {
    if (child === null || child === undefined) continue;
    item.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return item;
}

function actionButton(label, action, id, style = "secondary") {
  return element("button", {
    className: `button small ${style}`,
    text: label,
    type: "button",
    dataset: { action, id },
  });
}

function badge(label, style = "") {
  return element("span", { className: `badge ${style}`.trim(), text: label });
}

function initials(name) {
  return String(name || "N").trim().slice(0, 1).toUpperCase() || "N";
}

function avatarElement(user, large = false) {
  if (user && user.avatar_data) {
    return element("img", {
      className: `avatar avatar-image${large ? " large" : ""}`,
      attributes: { src: user.avatar_data, alt: `${user.username} profile picture` },
    });
  }
  return element("span", {
    className: `avatar${large ? " large" : ""}`,
    text: initials(user && user.username),
    attributes: { "aria-hidden": "true" },
  });
}

function applyAvatar(id, user) {
  const current = byId(id);
  const replacement = avatarElement(user, current.classList.contains("large"));
  replacement.id = id;
  current.replaceWith(replacement);
}

function readCsrfCookie() {
  const names = new Set(["__Host-notifinho_csrf", "notifinho_csrf"]);
  for (const pair of document.cookie.split(";")) {
    const [rawName, ...rest] = pair.trim().split("=");
    if (names.has(rawName)) return decodeURIComponent(rest.join("="));
  }
  return "";
}

class APIError extends Error {
  constructor(status, message) {
    super(message || "Request failed");
    this.status = status;
  }
}

async function request(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json" };
  let body;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (!SAFE_METHODS.has(method)) {
    const csrf = state.csrf || readCsrfCookie();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  let response;
  try {
    response = await fetch(`${API}${path}`, {
      method,
      headers,
      body,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (_error) {
    setConnection(false);
    throw new APIError(0, "Notifinho is not reachable.");
  }
  setConnection(true);
  const raw = await response.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (_error) {
      throw new APIError(response.status, "The server returned an invalid response.");
    }
  }
  if (!response.ok) {
    if (response.status === 401 && state.user && path !== "/session") expireSession();
    throw new APIError(response.status, payload && payload.error);
  }
  return payload;
}

function setConnection(connected) {
  const item = byId("connection-state");
  item.textContent = connected ? "Connected" : "Offline";
  item.classList.toggle("success", connected);
  item.classList.toggle("error", !connected);
}

function showError(id, error) {
  const item = byId(id);
  item.textContent = error instanceof APIError ? error.message : "The request could not be completed.";
  item.hidden = false;
}

function clearError(id) {
  const item = byId(id);
  item.textContent = "";
  item.hidden = true;
}

function toast(message, style = "") {
  const item = element("div", { className: `toast ${style}`.trim(), text: message });
  byId("toast-region").append(item);
  window.setTimeout(() => item.remove(), 4200);
}

function empty(container, title, copy) {
  container.replaceChildren(
    element("div", { className: "empty-state" }, [
      element("strong", { text: title }),
      element("span", { text: copy }),
    ]),
  );
}

function formatTime(value) {
  if (value === null || value === undefined || value === "") return "Never";
  const number = Number(value);
  const date = new Date(number < 10_000_000_000 ? number * 1000 : number);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(state.preferences.language || "en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: state.preferences.time_format === "12",
    timeZone: state.preferences.timezone || "Europe/Lisbon",
  }).format(date);
}

function relativeTime(value) {
  if (!value) return "Never";
  const seconds = Number(value) < 10_000_000_000 ? Number(value) : Number(value) / 1000;
  const delta = Math.round(seconds - Date.now() / 1000);
  const formatter = new Intl.RelativeTimeFormat(state.preferences.language || "en-GB", { numeric: "auto" });
  const absolute = Math.abs(delta);
  if (absolute < 60) return formatter.format(delta, "second");
  if (absolute < 3600) return formatter.format(Math.round(delta / 60), "minute");
  if (absolute < 86400) return formatter.format(Math.round(delta / 3600), "hour");
  return formatter.format(Math.round(delta / 86400), "day");
}

function isAdmin() {
  return state.user && state.user.role === "admin";
}

function ownResource(item) {
  return item && state.user && item.owner_user_id === state.user.id;
}

function expireSession() {
  state.user = null;
  state.csrf = "";
  byId("app-shell").hidden = true;
  byId("bootstrap-view").hidden = true;
  byId("login-view").hidden = false;
  byId("login-password").value = "";
  byId("login-error").hidden = true;
  byId("login-username").focus();
}

function showBootstrap(status) {
  state.user = null;
  state.csrf = "";
  byId("app-shell").hidden = true;
  byId("login-view").hidden = true;
  byId("bootstrap-view").hidden = false;
  const fragment = window.location.hash.slice(1);
  if (fragment.startsWith("setup=")) {
    byId("bootstrap-token").value = decodeURIComponent(fragment.slice(6));
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  byId("bootstrap-expiry").textContent = status.expires_at
    ? `This setup token expires ${formatTime(status.expires_at)}.`
    : "The setup token has expired. Restart Notifinho to rotate it, then check the new container output.";
  (byId("bootstrap-token").value ? byId("bootstrap-username") : byId("bootstrap-token")).focus();
}

function showApp(session) {
  state.user = session.user;
  state.sessionExpiresAt = session.expires_at;
  state.csrf = session.csrf_token || readCsrfCookie();
  byId("login-view").hidden = true;
  byId("app-shell").hidden = false;
  byId("users-nav").hidden = !isAdmin();
  byId("settings-nav").hidden = !isAdmin();
  byId("data-nav").hidden = !isAdmin();
  byId("add-destination-button").hidden = !isAdmin();
  byId("add-route-button").hidden = !isAdmin();
  const name = state.user.username;
  const role = state.user.role;
  for (const id of ["profile-avatar", "account-avatar"]) applyAvatar(id, state.user);
  for (const id of ["profile-name", "account-name"]) byId(id).textContent = name;
  byId("profile-role").textContent = role;
  byId("account-role").textContent = role === "admin" ? "Administrator" : "User";
  byId("account-session").textContent = `Session expires ${formatTime(session.expires_at)}`;
}

async function restoreSession() {
  try {
    const session = await request("/session");
    showApp(session);
    await loadWorkspace();
  } catch (error) {
    if (!(error instanceof APIError) || ![401, 404].includes(error.status)) {
      byId("login-error").textContent = error.message || "Notifinho is not reachable.";
      byId("login-error").hidden = false;
    }
    expireSession();
  }
}

async function login(event) {
  event.preventDefault();
  clearError("login-error");
  const submit = event.submitter;
  if (submit) submit.disabled = true;
  try {
    const session = await request("/session", {
      method: "POST",
      body: {
        username: byId("login-username").value.trim(),
        password: byId("login-password").value,
      },
    });
    showApp(session);
    await loadWorkspace();
  } catch (error) {
    showError("login-error", error);
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function bootstrapAdministrator(event) {
  event.preventDefault();
  clearError("bootstrap-error");
  const submit = event.submitter;
  const password = byId("bootstrap-password").value;
  if (password !== byId("bootstrap-confirm").value) {
    showError("bootstrap-error", new APIError(400, "The passwords do not match."));
    return;
  }
  if (submit) submit.disabled = true;
  try {
    const session = await request("/bootstrap", {
      method: "POST",
      body: {
        token: byId("bootstrap-token").value.trim(),
        username: byId("bootstrap-username").value.trim(),
        password,
      },
    });
    byId("bootstrap-token").value = "";
    byId("bootstrap-password").value = "";
    byId("bootstrap-confirm").value = "";
    byId("bootstrap-view").hidden = true;
    showApp(session);
    await loadWorkspace();
  } catch (error) {
    showError("bootstrap-error", error);
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function initialize() {
  try {
    const status = await request("/bootstrap");
    if (status.required) {
      showBootstrap(status);
      return;
    }
  } catch (error) {
    if (!(error instanceof APIError) || error.status !== 404) {
      byId("login-error").textContent = error.message || "Notifinho is not reachable.";
      byId("login-error").hidden = false;
    }
  }
  await restoreSession();
}

async function loadWorkspace() {
  const tasks = {
    destinations: request("/destinations"),
    routes: request("/routes"),
    tokens: request("/tokens"),
    deliveries: request("/deliveries"),
    audit: request("/audit-events"),
    preferences: request("/preferences"),
    notices: request("/notices"),
    metrics: request(`/metrics/${state.historyRange}`),
    health: request("/health-checks"),
  };
  if (isAdmin()) {
    tasks.users = request("/users");
    tasks.backups = request("/backups");
    tasks.configuration = request("/configuration/inventory");
    tasks.backupSettings = request("/backup-settings");
  }
  const keys = Object.keys(tasks);
  const values = await Promise.all(Object.values(tasks));
  const results = Object.fromEntries(keys.map((key, index) => [key, values[index]]));
  state.destinations = results.destinations.destinations;
  state.routes = results.routes.routes;
  state.tokens = results.tokens.tokens;
  state.deliveries = results.deliveries.deliveries;
  state.audit = results.audit.audit_events;
  state.preferences = results.preferences.preferences;
  state.notices = results.notices.notices;
  state.metrics = results.metrics.metrics;
  state.healthChecks = results.health.checks;
  state.users = isAdmin() ? results.users.users : [];
  state.backups = isAdmin() ? results.backups.backups : [];
  state.configuration = isAdmin() ? results.configuration.configuration : null;
  state.backupSettings = isAdmin() ? results.backupSettings.settings : null;
  state.backupLastRun = isAdmin() ? results.backupSettings.last_run : null;
  renderAll();
  const requested = window.location.hash.slice(1);
  navigate(VIEW_TITLES[requested] && (!["users", "settings", "data"].includes(requested) || isAdmin()) ? requested : state.currentView);
}

async function refreshWorkspace() {
  const button = byId("refresh-button");
  button.disabled = true;
  try {
    await loadWorkspace();
    toast("Workspace refreshed.");
  } catch (error) {
    toast(error.message || "Refresh failed.", "error");
  } finally {
    button.disabled = false;
  }
}

function renderAll() {
  renderNotices();
  renderDashboard();
  renderDestinations();
  renderRoutes();
  renderTokens();
  renderDeliveries();
  renderAudit();
  renderUsers();
  renderBackups();
  renderConfiguration();
  renderHealthChecks();
  renderBackupSettings();
  renderPreferences();
  applyLanguage();
}

function applyLanguage() {
  document.documentElement.lang = state.preferences.language || "en-GB";
  for (const item of document.querySelectorAll("body *")) {
    if (item.children.length || ["SCRIPT", "STYLE", "CODE", "PRE"].includes(item.tagName)) continue;
    const current = item.textContent.trim();
    if (!item.dataset.i18nSource && !Object.hasOwn(PT_TRANSLATIONS, current)) continue;
    if (!item.dataset.i18nSource) item.dataset.i18nSource = current;
    const source = item.dataset.i18nSource;
    item.textContent = state.preferences.language === "pt-PT" ? (PT_TRANSLATIONS[source] || source) : source;
  }
}

function navigate(view) {
  if (!VIEW_TITLES[view] || (["users", "settings", "data"].includes(view) && !isAdmin())) view = "dashboard";
  state.currentView = view;
  for (const section of document.querySelectorAll(".view")) {
    section.hidden = section.dataset.page !== view;
  }
  for (const button of document.querySelectorAll("[data-view]")) {
    const active = button.dataset.view === view && button.classList.contains("nav-item");
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  const [kicker, title] = VIEW_TITLES[view];
  byId("page-kicker").textContent = kicker;
  byId("page-title").textContent = title;
  window.history.replaceState(null, "", `#${view}`);
  byId("app-shell").classList.remove("nav-open");
  byId("mobile-menu").setAttribute("aria-expanded", "false");
  byId("main-content").focus({ preventScroll: true });
}

function renderDashboard() {
  const metrics = state.metrics || {};
  byId("metric-sources").textContent = metrics.sources ?? "—";
  byId("metric-destinations").textContent = metrics.destinations ?? "—";
  byId("metric-routes").textContent = metrics.routes ?? "—";
  byId("metric-tokens").textContent = metrics.applications ?? "—";
  byId("metric-success").textContent = metrics.success_percent === null || metrics.success_percent === undefined ? "—" : `${metrics.success_percent}%`;
  byId("metric-success-note").textContent = metrics.requests ? `${metrics.delivered} of ${metrics.requests} delivered` : "No requests in range";
  byId("metric-requests").textContent = metrics.requests ?? "—";
  byId("history-range").value = state.historyRange;
  renderFlow();
  const container = byId("dashboard-deliveries");
  container.replaceChildren();
  if (!state.deliveries.length) {
    empty(container, "No deliveries yet", "Submitted events will appear here after a route matches.");
    return;
  }
  for (const item of state.deliveries.slice(0, 6)) {
    const delivered = ["delivered", "success"].includes(item.outcome);
    const outcome = delivered ? "success" : item.retryable ? "warning" : "danger";
    container.append(element("div", { className: "activity-item" }, [
      element("span", { className: "event-indicator", text: delivered ? "✓" : "!" }),
      element("div", {}, [
        element("strong", { text: item.device_name ? `${item.device_name} · ${item.event_name || item.title}` : item.event_name || item.title || "Untitled event" }),
        element("small", { text: `${friendlyName(item.source)} · ${capitalize(item.severity)} · attempt ${item.attempt_number}` }),
      ]),
      element("div", {}, [badge(item.outcome, outcome), element("small", { text: relativeTime(item.completed_at || item.created_at) })]),
    ]));
  }
}

function renderNotices() {
  const console = byId("notice-console");
  const composer = byId("notice-composer");
  const panel = byId("notice-panel");
  const list = byId("notice-list");
  composer.hidden = !isAdmin();
  panel.hidden = !state.notices.length;
  console.hidden = !isAdmin() && !state.notices.length;
  list.replaceChildren();
  for (const item of state.notices) {
    const status = item.status === "severe" ? "danger" : item.status === "warning" ? "warning" : "information";
    const close = actionButton("×", "dismiss-notice", item.id, "icon-button notice-close");
    close.setAttribute("aria-label", item.persistent ? "This notice clears automatically" : `Close ${item.name}`);
    close.disabled = item.persistent;
    close.title = item.persistent ? "This error or update clears automatically when resolved" : "Close notice";
    list.append(element("div", { className: `notice-item ${status}` }, [
      element("div", {}, [
        element("div", { className: "notice-title" }, [element("strong", { text: item.name }), badge(capitalize(item.status), status)]),
        element("p", { text: item.message }),
        element("small", { text: formatTime(item.created_at) }),
      ]),
      close,
    ]));
  }
}

function capitalize(value) {
  const text = String(value || "");
  return text ? text[0].toUpperCase() + text.slice(1) : "—";
}

function friendlyName(value) {
  const special = { home_assistant: "Home Assistant", hpe_ilo: "HPE iLO", dell_idrac: "Dell iDRAC", xen_orchestra: "Xen Orchestra", unifi_network: "UniFi Network", unifi_protect: "UniFi Protect", unifi_drive: "UniFi Drive" };
  const key = String(value || "").casefold ? String(value || "").casefold() : String(value || "").toLowerCase();
  return special[key] || String(value || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function outputIcon(type) {
  if (OUTPUT_ICONS[type]) return element("img", { className: "output-icon-image", attributes: { src: OUTPUT_ICONS[type], alt: "" } });
  const labels = { teams: "T", slack: "S", webhook: "↗" };
  return element("span", { className: `output-icon-fallback ${type}`, text: labels[type] || String(type || "?").slice(0, 1).toUpperCase(), attributes: { "aria-hidden": "true" } });
}

function sourceInputType(source) {
  const observed = state.deliveries.find((item) => item.source === source && item.input_type);
  return observed ? observed.input_type : "HTTP";
}

function renderFlow() {
  const container = byId("dashboard-flow");
  container.replaceChildren();
  for (const route of state.routes) {
    const destination = state.destinations.find((item) => item.id === route.destination_id);
    const problem = route.enabled && (!destination || !destination.enabled || (!destination.secret_configured && ["discord", "teams", "slack", "webhook"].includes(destination.output_type)));
    const status = !route.enabled ? "disabled" : problem ? "problem" : "active";
    container.append(element("div", { className: `flow-row ${status}` }, [
      element("div", { className: "flow-node source-node" }, [element("strong", { text: route.source === "*" ? "All Sources" : friendlyName(route.source) }), element("small", { text: route.source === "*" ? "HTTP / SMTP" : sourceInputType(route.source) })]),
      element("div", { className: "flow-route" }, [element("span", { className: "flow-arrow", text: "→" }), element("div", {}, [element("strong", { text: route.name }), element("small", { text: filterSummary(route.filters) })]), element("span", { className: "flow-arrow", text: "→" })]),
      element("div", { className: "flow-node destination-node" }, [outputIcon(destination && destination.output_type), element("div", {}, [element("strong", { text: destination ? (OUTPUT_NAMES[destination.output_type] || friendlyName(destination.output_type)) : "Missing destination" }), element("small", { text: destination ? (destination.settings.channel_name || destination.name) : "Configuration error" })])]),
    ]));
  }
  if (!container.children.length) empty(container, "No routing flow", "Create a destination and route to display it here.");
}

function renderDestinations() {
  const container = byId("destination-list");
  container.replaceChildren();
  if (!state.destinations.length) {
    empty(container, "No destinations", "Add an output to preview payloads and receive routed events.");
    return;
  }
  for (const item of state.destinations) {
    const editable = isAdmin();
    const actions = element("div", { className: "resource-actions" }, [
      actionButton("Preview", "preview-destination", item.id),
    ]);
    if (editable) {
      actions.append(
        actionButton("Edit", "edit-destination", item.id),
        actionButton(item.enabled ? "Disable" : "Enable", "toggle-destination", item.id),
        actionButton("Delete", "delete-destination", item.id, "danger"),
      );
    }
    const meta = element("div", { className: "resource-meta" }, [
      badge(item.enabled ? "Enabled" : "Disabled", item.enabled ? "success" : "warning"),
      badge(item.shared ? "Shared" : "Private"),
      badge(item.secret_configured ? "Credentials set" : "No credentials", item.secret_configured ? "success" : "warning"),
    ]);
    container.append(element("article", { className: "resource-card" }, [
      element("div", { className: "resource-heading" }, [
        element("div", { className: "resource-identity" }, [
          element("span", { className: "resource-icon" }, outputIcon(item.output_type)),
          element("div", {}, [element("strong", { text: item.name }), element("small", { text: OUTPUT_NAMES[item.output_type] || friendlyName(item.output_type) })]),
        ]),
      ]),
      meta,
      actions,
    ]));
  }
}

function destinationName(id) {
  const item = state.destinations.find((candidate) => candidate.id === id);
  return item ? item.name : "Unavailable destination";
}

function destinationTypeName(id) {
  const item = state.destinations.find((candidate) => candidate.id === id);
  return item ? (OUTPUT_NAMES[item.output_type] || friendlyName(item.output_type)) : "Unavailable destination";
}

function filterSummary(filters) {
  const parts = [];
  for (const key of ["severities", "statuses", "hosts", "events"]) {
    const values = filters && filters[key];
    if (Array.isArray(values) && values.length) parts.push(`${capitalize(key.replace(/s$/, ""))}: ${values.map(capitalize).join(", ")}`);
  }
  if (parts.length === 1 && filters.severities && filters.severities.length === 1 && filters.severities[0] === "critical") return "Just Critical";
  return parts.join(" · ") || "All Events";
}

function renderRoutes() {
  const body = byId("route-table");
  body.replaceChildren();
  byId("route-empty").hidden = state.routes.length > 0;
  if (!state.routes.length) {
    byId("route-empty").replaceChildren(element("strong", { text: "No routes" }), element("span", { text: "Create a route after adding a destination." }));
    return;
  }
  for (const item of state.routes) {
    const order = element("div", { className: "row-actions order-actions" });
    if (isAdmin()) order.append(actionButton("↑", "move-route-up", item.id), actionButton("↓", "move-route-down", item.id));
    const name = isAdmin()
      ? element("button", { className: "route-name-button", text: item.name, type: "button", dataset: { action: "edit-route", id: item.id } })
      : element("strong", { text: item.name });
    const status = element("button", {
      className: `badge status-button ${item.enabled ? "success" : "warning"}`,
      text: item.enabled ? "Enabled" : "Disabled",
      type: "button",
      disabled: !isAdmin(),
      dataset: { action: "toggle-route", id: item.id },
    });
    body.append(element("tr", {}, [
      element("td", {}, name),
      element("td", { text: item.source === "*" ? "All Sources" : friendlyName(item.source) }),
      element("td", { text: destinationTypeName(item.destination_id) }),
      element("td", {}, element("small", { text: filterSummary(item.filters) })),
      element("td", { text: capitalize(item.priority_name || "normal") }),
      element("td", {}, status),
      element("td", {}, order),
      element("td", {}, isAdmin() ? actionButton("Delete", "delete-route", item.id, "danger") : null),
    ]));
  }
}

function renderTokens() {
  const body = byId("token-table");
  body.replaceChildren();
  byId("token-empty").hidden = state.tokens.length > 0;
  if (!state.tokens.length) {
    byId("token-empty").replaceChildren(element("strong", { text: "No application tokens" }), element("span", { text: "Issue a source-scoped token for an event producer." }));
    return;
  }
  for (const item of state.tokens) {
    const yamlManaged = item.management === "yaml";
    const unavailable = yamlManaged && item.credential_available === false;
    const revoked = Boolean(item.revoked_at);
    const inactive = item.enabled === false || unavailable;
    const actions = element("div", { className: "row-actions" });
    if (!revoked) {
      actions.append(
        actionButton("Delete", "delete-token", item.id, "danger"),
      );
      if (!yamlManaged) actions.prepend(actionButton("Rotate", "rotate-token", item.id));
    }
    body.append(element("tr", {}, [
      element("td", {}, [element("strong", { text: item.name }), element("small", { text: yamlManaged ? `Configured credential · ${item.credential_source}` : `Issued credential · version ${item.version}` })]),
      element("td", { text: item.source_scopes.map(friendlyName).join(", ") || "None" }),
      element("td", { text: `${item.rate_limit_per_minute}/min` }),
      element("td", { text: item.last_used_at ? relativeTime(item.last_used_at) : "Never" }),
      element("td", {}, element("button", {
        className: `badge status-button ${unavailable || revoked ? "danger" : inactive ? "warning" : "success"}`,
        text: unavailable ? "Credential unavailable" : revoked ? "Revoked" : inactive ? "Inactive" : "Active",
        type: "button",
        disabled: unavailable || revoked,
        dataset: { action: "toggle-token", id: item.id },
      })),
      element("td", {}, actions),
    ]));
  }
}

function renderDeliveries() {
  const query = byId("delivery-search").value.trim().toLowerCase();
  const items = state.deliveries.filter((item) => JSON.stringify([item.source, item.title, item.outcome, item.safe_error, item.error_code]).toLowerCase().includes(query));
  const container = byId("delivery-list");
  container.replaceChildren();
  if (!items.length) {
    empty(container, query ? "No matching deliveries" : "No delivery history", query ? "Try a different search." : "Delivery attempts appear after matched events are submitted.");
    return;
  }
  for (const item of items) {
    const delivered = ["delivered", "success"].includes(item.outcome);
    const style = delivered ? "success" : item.retryable ? "warning" : "danger";
    const error = item.safe_error || item.error_code || (delivered ? "Delivery completed" : "No transport error reported");
    const heading = item.device_name
      ? `${item.device_name} · ${item.event_name || item.title || "Event"}`
      : item.event_name || item.title || "Untitled event";
    container.append(element("article", { className: "timeline-item" }, [
      element("span", { className: "event-indicator", text: delivered ? "✓" : "!" }),
      element("div", {}, [
        element("strong", { text: heading }),
        element("small", { text: `${friendlyName(item.source)} · ${item.input_type || "HTTP"}` }),
        element("p", { text: item.event_description || error }),
        element("div", { className: "resource-meta" }, [badge(capitalize(item.severity), style), badge(capitalize(item.event_status || item.outcome), style), badge(`Attempt ${item.attempt_number}`), badge(item.input_type || "HTTP"), item.response_status ? badge(`HTTP ${item.response_status}`) : null]),
      ]),
      element("div", { className: "timeline-meta" }, [element("span", { text: formatTime(item.completed_at || item.created_at) }), item.retryable ? element("small", { text: "Retryable" }) : null]),
    ]));
  }
}

function renderAudit() {
  const query = byId("audit-search").value.trim().toLowerCase();
  const items = state.audit.filter((item) => JSON.stringify([item.action, item.resource_type, item.outcome, item.details]).toLowerCase().includes(query));
  const body = byId("audit-table");
  body.replaceChildren();
  byId("audit-empty").hidden = items.length > 0;
  if (!items.length) {
    byId("audit-empty").replaceChildren(element("strong", { text: query ? "No matching audit events" : "No audit events" }), element("span", { text: query ? "Try a different search." : "Security-relevant activity appears here." }));
    return;
  }
  for (const item of items) {
    const details = item.details && Object.keys(item.details).length ? JSON.stringify(item.details) : "—";
    body.append(element("tr", {}, [
      element("td", { text: formatTime(item.created_at) }),
      element("td", {}, element("strong", { text: item.action })),
      element("td", { text: item.resource_type }),
      element("td", {}, badge(item.outcome, item.outcome === "success" ? "success" : "danger")),
      element("td", {}, element("small", { text: details })),
    ]));
  }
}

function renderUsers() {
  const body = byId("user-table");
  body.replaceChildren();
  if (!isAdmin()) return;
  for (const item of state.users) {
    const self = item.id === state.user.id;
    const actions = element("div", { className: "row-actions" });
    if (!self) {
      actions.append(
        actionButton("Reset password", "reset-user", item.id),
      );
    }
    body.append(element("tr", {}, [
      element("td", {}, element("div", { className: "user-cell" }, [avatarElement(item), element("div", {}, [element("strong", { text: item.username }), element("small", { text: self ? "Current account" : item.id.slice(0, 8) })])])),
      element("td", { text: item.role }),
      element("td", { text: formatTime(item.last_login_at) }),
      element("td", {}, element("button", {
        className: `badge status-button ${item.enabled ? "success" : "danger"}`,
        text: item.enabled ? "Enabled" : "Disabled",
        type: "button",
        disabled: self,
        dataset: { action: "toggle-user", id: item.id },
      })),
      element("td", {}, actions),
    ]));
  }
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function renderBackups() {
  const container = byId("backup-list");
  container.replaceChildren();
  if (!isAdmin()) return;
  if (!state.backups.length) {
    empty(container, "No state backups", "Create a private snapshot before migration or major changes.");
    return;
  }
  for (const item of state.backups) {
    container.append(element("div", { className: "backup-item" }, [
      element("div", {}, [
        element("strong", { text: formatTime(item.created_at) }),
        element("small", { text: `${item.secret_files} secret files · ${formatBytes(item.size_bytes)} · schema ${item.schema_version}` }),
        element("code", { text: item.id }),
      ]),
      actionButton("Restore", "restore-backup", item.id, "danger"),
    ]));
  }
}

function renderConfiguration() {
  if (!isAdmin() || !state.configuration) {
    return;
  }
  const configuration = state.configuration;
  const summary = configuration.summary;
  const sync = configuration.sync || { ready: true, errors: [] };
  byId("configuration-card-title").textContent = sync.ready ? "Configured listeners" : "Inputs require configuration repair";
  byId("configuration-card-copy").textContent = "Click an input status to change it. Restart Notifinho after listener changes.";
  const badges = byId("configuration-summary");
  badges.replaceChildren(
    badge(`${summary.inputs} inputs`),
    badge(`${summary.outputs} destinations`),
    badge(`${summary.routes} routes`),
    badge(sync.ready ? "Synchronized" : "Repair required", sync.ready ? "success" : "danger"),
  );
  const inputs = byId("configuration-inputs");
  inputs.replaceChildren();
  if (!configuration.inputs.length) {
    inputs.append(element("small", { text: "No recognized YAML input sections were detected." }));
  } else {
    for (const item of configuration.inputs) {
      const detail = Object.entries(item.details || {}).map(([key, value]) => `${key} ${value}`).join(" · ");
      inputs.append(element("div", { className: "configuration-input" }, [
        element("div", {}, [element("strong", { text: item.label }), element("small", { text: detail || item.name })]),
        element("button", {
          className: `badge status-button ${item.enabled ? "success" : "warning"}`,
          text: item.enabled ? "Enabled" : "Disabled",
          type: "button",
          dataset: { action: "toggle-input", id: item.name },
        }),
      ]));
    }
  }
  const error = byId("configuration-errors");
  error.textContent = (sync.errors || []).join(" · ");
  error.hidden = !(sync.errors || []).length;
}

function renderHealthChecks() {
  const container = byId("health-check-list");
  container.replaceChildren();
  for (const item of state.healthChecks) {
    container.append(element("div", { className: "health-check" }, [
      element("span", { className: `health-indicator ${item.status}`, text: item.status === "healthy" ? "✓" : "!" }),
      element("div", {}, [element("strong", { text: item.name }), element("small", { text: item.detail })]),
      badge(capitalize(item.status), item.status === "healthy" ? "success" : item.status === "warning" ? "warning" : "danger"),
    ]));
  }
}

function renderBackupSettings() {
  if (!isAdmin() || !state.backupSettings) return;
  const settings = state.backupSettings;
  byId("backup-schedule").value = settings.schedule;
  byId("backup-time").value = settings.time;
  byId("backup-weekday").value = String(settings.weekday);
  byId("backup-day").value = String(settings.day);
  byId("backup-external-enabled").checked = settings.external_enabled;
  byId("backup-external-type").value = settings.external_type;
  byId("backup-external-path").value = settings.external_path;
  byId("backup-last-run").textContent = state.backupLastRun
    ? `Last scheduled run: ${capitalize(state.backupLastRun.outcome || "pending")} · ${formatTime(state.backupLastRun.completed_at || state.backupLastRun.started_at)}`
    : "No scheduled run recorded.";
}

function renderPreferences() {
  if (state.sessionExpiresAt) byId("account-session").textContent = `Session expires ${formatTime(state.sessionExpiresAt)}`;
  if (!isAdmin()) return;
  byId("preference-language").value = state.preferences.language || "en-GB";
  byId("preference-timezone").value = state.preferences.timezone || "Europe/Lisbon";
  byId("preference-time-format").value = state.preferences.time_format || "24";
  document.documentElement.lang = state.preferences.language || "en-GB";
}

async function savePreferences(event) {
  event.preventDefault();
  try {
    const response = await request("/preferences", {
      method: "PUT",
      body: {
        language: byId("preference-language").value,
        timezone: byId("preference-timezone").value.trim(),
        time_format: byId("preference-time-format").value,
      },
    });
    state.preferences = response.preferences;
    await loadWorkspace();
    toast("Regional settings saved.");
  } catch (error) {
    toast(error.message || "Settings could not be saved.", "error");
  }
}

async function saveNotice(event) {
  event.preventDefault();
  try {
    await request("/notices", {
      method: "POST",
      body: {
        name: byId("notice-name").value.trim(),
        message: byId("notice-message").value.trim(),
        status: byId("notice-status").value,
      },
    });
    event.currentTarget.reset();
    await loadWorkspace();
    toast("Notice sent to users.");
  } catch (error) {
    toast(error.message || "Notice could not be sent.", "error");
  }
}

async function changeHistoryRange() {
  state.historyRange = byId("history-range").value;
  try {
    const response = await request(`/metrics/${state.historyRange}`);
    state.metrics = response.metrics;
    renderDashboard();
  } catch (error) {
    toast(error.message || "History could not be loaded.", "error");
  }
}

async function saveBackupSettings(event) {
  event.preventDefault();
  try {
    const response = await request("/backup-settings", {
      method: "PUT",
      body: {
        schedule: byId("backup-schedule").value,
        time: byId("backup-time").value,
        weekday: Number(byId("backup-weekday").value),
        day: Number(byId("backup-day").value),
        external_enabled: byId("backup-external-enabled").checked,
        external_type: byId("backup-external-type").value,
        external_path: byId("backup-external-path").value.trim(),
      },
    });
    state.backupSettings = response.settings;
    renderBackupSettings();
    toast("Backup settings saved.");
  } catch (error) {
    toast(error.message || "Backup settings could not be saved.", "error");
  }
}

async function saveAvatar(event) {
  event.preventDefault();
  const file = byId("avatar-file").files && byId("avatar-file").files[0];
  if (!file) {
    toast("Choose a picture first.", "error");
    return;
  }
  if (file.size > 256 * 1024) {
    toast("Profile pictures must not exceed 256 KiB.", "error");
    return;
  }
  try {
    const imageData = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("The picture could not be read."));
      reader.readAsDataURL(file);
    });
    const response = await request("/account/avatar", { method: "PUT", body: { image_data: imageData } });
    state.user = response.user;
    applyAvatar("profile-avatar", state.user);
    applyAvatar("account-avatar", state.user);
    byId("avatar-file").value = "";
    toast("Profile picture updated.");
  } catch (error) {
    toast(error.message || "Profile picture could not be saved.", "error");
  }
}

function downloadDocument(documentValue) {
  const content = `${JSON.stringify(documentValue, null, 2)}\n`;
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = element("a", {
    attributes: {
      href: url,
      download: `notifinho-platform-${new Date().toISOString().slice(0, 10)}.json`,
    },
  });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function exportPlatform() {
  const response = await request("/portability/export");
  downloadDocument(response.document);
  toast("Safe platform export downloaded.");
}

async function selectedFile(id) {
  const input = byId(id);
  const file = input.files && input.files[0];
  if (!file) throw new Error("Choose a file first.");
  if (file.size < 1 || file.size > 1024 * 1024) {
    throw new Error("Import files must contain 1 to 1048576 bytes.");
  }
  return file.text();
}

async function previewImport(kind) {
  clearError("import-error");
  const portable = kind === "portable";
  const local = kind === "local_yaml";
  try {
    let body = {};
    if (!local) {
      const content = await selectedFile(portable ? "portable-file" : "migration-file");
      if (portable) {
      let documentValue;
      try {
        documentValue = JSON.parse(content);
      } catch (_error) {
        throw new Error("The selected JSON document is invalid.");
      }
      body = { document: documentValue };
      } else {
        body = { yaml: content };
      }
    }
    const endpoint = local
      ? "/configuration/migration/preview"
      : portable ? "/portability/preview" : "/migrations/v1/preview";
    const response = await request(endpoint, { method: "POST", body });
    state.pendingImport = { kind, body, preview: response.preview };
    byId("import-title").textContent = local
      ? "Mounted configuration takeover"
      : portable ? "Platform JSON preview" : "v1.x YAML migration preview";
    byId("import-summary").textContent = response.preview.valid
      ? `${response.preview.summary.destinations} destinations and ${response.preview.summary.routes} routes are ready.${local ? " Applying this creates state and configuration backups, imports credentials server-side, and activates WebUI routing." : ""}`
      : "The document cannot be applied until every reported error is corrected.";
    byId("import-result").textContent = JSON.stringify(response.preview, null, 2);
    byId("import-apply").disabled = !response.preview.valid;
    byId("import-dialog").showModal();
  } catch (error) {
    state.pendingImport = null;
    toast(error.message || "Import preview failed.", "error");
  }
}

async function applyImport() {
  const pending = state.pendingImport;
  if (!pending || !pending.preview.valid) return;
  const accepted = await confirmAction(
    "Apply the previewed import?",
    "Only the unchanged, fingerprinted document will be accepted. This creates new resources and never overwrites existing names.",
    "Apply import",
  );
  if (!accepted) return;
  try {
    const endpoint = pending.kind === "local_yaml"
      ? "/configuration/migration/apply"
      : pending.kind === "portable" ? "/portability/import" : "/migrations/v1/import";
    const body = {
      ...pending.body,
      fingerprint: pending.preview.fingerprint,
      confirm: true,
    };
    const response = await request(endpoint, { method: "POST", body });
    const result = response.migration || response.import;
    state.pendingImport = null;
    byId("import-dialog").close();
    byId("portable-file").value = "";
    byId("migration-file").value = "";
    await loadWorkspace();
    toast(`${pending.kind === "local_yaml" ? "Activated" : "Imported"} ${result.destinations_created} destinations and ${result.routes_created} routes.`);
  } catch (error) {
    showError("import-error", error);
  }
}

async function createBackup() {
  const accepted = await confirmAction(
    "Create a private state backup?",
    "The snapshot stays on this server and includes database authentication material and destination secret files.",
    "Create backup",
  );
  if (!accepted) return;
  await request("/backups", { method: "POST", body: {} });
  await loadWorkspace();
  toast("State backup created.");
}

async function restoreBackup(id) {
  const accepted = await confirmAction(
    "Restore this state backup?",
    `Restore ${id}. Notifinho creates a safety backup first and signs out every browser session. Application-token state returns to the selected snapshot.`,
    "Restore and sign out",
  );
  if (!accepted) return;
  await request(`/backups/${id}/restore`, {
    method: "POST",
    body: { confirmation: id },
  });
  expireSession();
  toast("State restored. Sign in again.");
}

async function setRoutingAuthority(authority) {
  const database = authority === "database";
  const accepted = await confirmAction(
    database ? "Use WebUI routing?" : "Use YAML fallback routing?",
    database
      ? "Legacy SMTP and webhook events will use the destinations and routes managed in this WebUI. A configuration backup is created first."
      : "Legacy SMTP and webhook events will immediately use the original destinations and routes retained in config.yaml. A configuration backup is created first.",
    database ? "Use WebUI routing" : "Use YAML routing",
  );
  if (!accepted) return;
  await request("/configuration/routing-authority", {
    method: "PUT",
    body: {
      authority,
      confirmation: `USE ${authority.toUpperCase()} ROUTING`,
    },
  });
  await loadWorkspace();
  toast(`${database ? "WebUI" : "YAML"} routing is now authoritative.`);
}

function formField(definition, value) {
  const label = element("label", { className: definition.wide ? "wide" : "" });
  label.append(element("span", { text: definition.label }));
  let input;
  if (definition.kind === "select") {
    input = element("select", { dataset: { field: definition.key, valueType: definition.valueType || "string" } });
    for (const choice of definition.choices) input.append(element("option", { value: choice[0], text: choice[1] }));
  } else if (definition.kind === "textarea") {
    input = element("textarea", { dataset: { field: definition.key, valueType: definition.valueType || "string" }, attributes: { rows: definition.rows || 3 } });
  } else {
    input = element("input", {
      type: definition.kind === "password" ? "password" : definition.kind === "number" ? "number" : "text",
      dataset: { field: definition.key, valueType: definition.valueType || "string" },
      attributes: definition.attributes || {},
    });
  }
  if (definition.kind === "checkbox") {
    label.className = "switch-field";
    label.replaceChildren();
    input = element("input", { type: "checkbox", dataset: { field: definition.key, valueType: "boolean" } });
    input.checked = Boolean(value === undefined ? definition.default : value);
    label.append(input, element("span", { text: definition.label }));
    if (definition.help) label.append(element("small", { text: definition.help }));
    return label;
  } else if (value !== undefined && value !== null) {
    input.value = definition.valueType === "json" ? JSON.stringify(value, null, 2) : definition.valueType === "list" && Array.isArray(value) ? value.join(", ") : String(value);
  } else if (definition.default !== undefined) {
    input.value = String(definition.default);
  }
  if (definition.required) input.required = true;
  label.append(input);
  if (definition.help) label.append(element("small", { text: definition.help }));
  return label;
}

function destinationDefinition(type) {
  const adminPrivate = isAdmin() ? [{ key: "allow_private_network", label: "Allow private-network target", kind: "checkbox", default: false }] : [];
  const presentation = { key: "channel_name", label: "Channel / destination label", help: "Shown in Routing Flow (for example #infrastructure)." };
  const definitions = {
    discord: {
      help: "Discord components-v2 formatting with source-aware fallback.",
      settings: [presentation, { key: "components_v2", label: "Use Components v2", kind: "checkbox", default: true }],
      secrets: [{ key: "url", label: "Webhook URL", kind: "password", required: true, wide: true }],
    },
    teams: {
      help: "Microsoft Teams workflow or incoming webhook delivery.",
      settings: [presentation],
      secrets: [{ key: "url", label: "Webhook URL", kind: "password", required: true, wide: true }],
    },
    slack: {
      help: "Slack Block Kit delivery to an official Slack webhook host.",
      settings: [presentation, { key: "include_metadata", label: "Include event metadata", kind: "checkbox", default: true }],
      secrets: [{ key: "url", label: "Slack webhook URL", kind: "password", required: true, wide: true }],
    },
    webhook: {
      help: "Bounded JSON delivery with optional headers, templating, and HMAC signing.",
      settings: [
        presentation,
        { key: "method", label: "Method", kind: "select", choices: [["POST", "POST"], ["PUT", "PUT"], ["PATCH", "PATCH"]], default: "POST" },
        { key: "timeout_seconds", label: "Timeout (seconds)", kind: "number", valueType: "number", default: 15, attributes: { min: 1, max: 30 } },
        { key: "headers", label: "Public headers (JSON)", kind: "textarea", valueType: "json", default: "{}", wide: true },
        { key: "body_template", label: "Optional body template (JSON)", kind: "textarea", valueType: "optional-json", wide: true },
        { key: "sign_hmac", label: "Sign payload with HMAC", kind: "checkbox", default: false },
        ...adminPrivate,
      ],
      secrets: [
        { key: "url", label: "Destination URL", kind: "password", required: true, wide: true },
        { key: "hmac_secret", label: "HMAC secret", kind: "password" },
        { key: "headers", label: "Secret headers (JSON)", kind: "textarea", valueType: "optional-json", wide: true },
      ],
    },
    mqtt: {
      help: "Publish the stable event envelope to a bounded MQTT topic.",
      settings: [
        presentation,
        { key: "host", label: "Broker host", required: true },
        { key: "port", label: "Port", kind: "number", valueType: "number", default: 8883, attributes: { min: 1, max: 65535 } },
        { key: "topic", label: "Topic", required: true, wide: true },
        { key: "qos", label: "QoS", kind: "select", valueType: "number", choices: [["0", "0"], ["1", "1"], ["2", "2"]], default: 1 },
        { key: "keepalive_seconds", label: "Keepalive (seconds)", kind: "number", valueType: "number", default: 60, attributes: { min: 10, max: 300 } },
        { key: "client_id", label: "Client ID" },
        { key: "tls", label: "Use TLS", kind: "checkbox", default: true },
        { key: "retain", label: "Retain messages", kind: "checkbox", default: false },
        ...adminPrivate,
      ],
      secrets: [{ key: "username", label: "Username", kind: "password" }, { key: "password", label: "Password", kind: "password" }],
    },
    ntfy: {
      help: "Publish to a hosted or self-hosted ntfy server.",
      settings: [
        presentation,
        { key: "server", label: "Server URL", required: true, wide: true },
        { key: "topic", label: "Topic", required: true },
        { key: "priority", label: "Priority", kind: "select", choices: [["min", "Minimum"], ["low", "Low"], ["default", "Default"], ["high", "High"], ["max", "Maximum"]], default: "default" },
        { key: "tags", label: "Tags", valueType: "list", help: "Comma-separated" },
        { key: "title", label: "Title template", default: "${title}" },
        { key: "timeout_seconds", label: "Timeout (seconds)", kind: "number", valueType: "number", default: 15, attributes: { min: 1, max: 30 } },
        { key: "include_action", label: "Include safe action link", kind: "checkbox", default: true },
        ...adminPrivate,
      ],
      secrets: [{ key: "token", label: "Access token", kind: "password", wide: true }, { key: "username", label: "Username", kind: "password" }, { key: "password", label: "Password", kind: "password" }],
    },
  };
  return definitions[type];
}

function renderDestinationFields(settings = {}) {
  const type = byId("destination-type").value;
  const definition = destinationDefinition(type);
  byId("destination-help").textContent = definition.help;
  const settingsContainer = byId("destination-settings");
  const secretsContainer = byId("destination-secrets");
  settingsContainer.replaceChildren(...definition.settings.map((field) => formField(field, settings[field.key])));
  secretsContainer.replaceChildren(...definition.secrets.map((field) => formField(field)));
  const editing = Boolean(byId("destination-id").value);
  for (const input of secretsContainer.querySelectorAll("[required]")) input.required = !editing;
}

function openDestination(id = "") {
  const item = state.destinations.find((candidate) => candidate.id === id);
  byId("destination-form").reset();
  clearError("destination-error");
  byId("destination-id").value = item ? item.id : "";
  byId("destination-name").value = item ? item.name : "";
  byId("destination-type").value = item ? item.output_type : "discord";
  byId("destination-name").disabled = false;
  byId("destination-type").disabled = Boolean(item);
  byId("destination-enabled").checked = item ? item.enabled : true;
  byId("destination-shared").checked = item ? item.shared : false;
  byId("destination-shared-field").hidden = !isAdmin();
  byId("destination-dialog-title").textContent = item ? `Edit ${item.name}` : "Add destination";
  byId("destination-submit").textContent = item ? "Save changes" : "Add destination";
  renderDestinationFields(item ? item.settings : {});
  byId("destination-dialog").showModal();
}

function collectFields(container) {
  const result = {};
  for (const input of container.querySelectorAll("[data-field]")) {
    const key = input.dataset.field;
    const type = input.dataset.valueType;
    if (type === "boolean") {
      result[key] = input.checked;
    } else if (type === "number") {
      result[key] = Number(input.value);
    } else if (type === "list") {
      result[key] = splitList(input.value);
    } else if (type === "json" || type === "optional-json") {
      if (!input.value.trim() && type === "optional-json") continue;
      try {
        result[key] = JSON.parse(input.value || "{}");
      } catch (_error) {
        throw new Error(`${input.previousElementSibling.textContent} must contain valid JSON.`);
      }
    } else if (input.value.trim()) {
      result[key] = input.value.trim();
    }
  }
  return result;
}

async function saveDestination(event) {
  event.preventDefault();
  if (event.submitter && event.submitter.value === "cancel") {
    byId("destination-dialog").close();
    return;
  }
  clearError("destination-error");
  const id = byId("destination-id").value;
  try {
    const settings = collectFields(byId("destination-settings"));
    const secret = collectFields(byId("destination-secrets"));
    const payload = {
      name: byId("destination-name").value.trim(),
      settings,
      enabled: byId("destination-enabled").checked,
    };
    if (isAdmin()) payload.shared = byId("destination-shared").checked;
    if (Object.keys(secret).length) payload.secret = secret;
    if (!id) {
      payload.output_type = byId("destination-type").value;
    }
    await request(id ? `/destinations/${id}` : "/destinations", { method: id ? "PATCH" : "POST", body: payload });
    byId("destination-dialog").close();
    await loadWorkspace();
    toast(id ? "Destination updated." : "Destination added.");
  } catch (error) {
    showError("destination-error", error);
  }
}

function splitList(value) {
  return [...new Set(String(value || "").split(",").map((item) => item.trim()).filter(Boolean))];
}

function setRouteOptions(selected = "") {
  const select = byId("route-destination");
  select.replaceChildren();
  for (const item of state.destinations.filter((candidate) => candidate.enabled || candidate.id === selected)) {
    select.append(element("option", { value: item.id, text: `${item.name} (${OUTPUT_NAMES[item.output_type] || item.output_type})` }));
  }
  if (selected) select.value = selected;
}

function openRoute(id = "") {
  if (!state.destinations.length) {
    toast("Add a destination before creating a route.", "error");
    navigate("destinations");
    return;
  }
  const item = state.routes.find((candidate) => candidate.id === id);
  byId("route-form").reset();
  clearError("route-error");
  byId("route-id").value = item ? item.id : "";
  byId("route-name").value = item ? item.name : "";
  byId("route-source").value = item ? item.source : "";
  byId("route-priority").value = item ? (item.priority_name || "normal") : "normal";
  byId("route-enabled").checked = item ? item.enabled : true;
  setRouteOptions(item ? item.destination_id : "");
  for (const key of ["severities", "statuses"]) {
    const selected = new Set(item && item.filters[key] ? item.filters[key] : []);
    for (const option of byId(`route-${key}`).options) option.selected = selected.has(option.value);
  }
  for (const key of ["hosts", "events"]) byId(`route-${key}`).value = item && item.filters[key] ? item.filters[key].join(", ") : "";
  byId("route-dialog-title").textContent = item ? `Edit ${item.name}` : "Add route";
  byId("route-dialog").showModal();
}

async function saveRoute(event) {
  event.preventDefault();
  if (event.submitter && event.submitter.value === "cancel") {
    byId("route-dialog").close();
    return;
  }
  clearError("route-error");
  const id = byId("route-id").value;
  const filters = {};
  for (const key of ["severities", "statuses"]) {
    const values = [...byId(`route-${key}`).selectedOptions].map((option) => option.value);
    if (values.length) filters[key] = values;
  }
  for (const key of ["hosts", "events"]) {
    const values = splitList(byId(`route-${key}`).value);
    if (values.length) filters[key] = values;
  }
  try {
    await request(id ? `/routes/${id}` : "/routes", {
      method: id ? "PATCH" : "POST",
      body: {
        name: byId("route-name").value.trim(),
        source: byId("route-source").value.trim(),
        destination_id: byId("route-destination").value,
        priority: byId("route-priority").value,
        enabled: byId("route-enabled").checked,
        filters,
      },
    });
    byId("route-dialog").close();
    await loadWorkspace();
    toast(id ? "Route updated." : "Route added.");
  } catch (error) {
    showError("route-error", error);
  }
}

function openToken() {
  byId("token-form").reset();
  byId("token-rate").value = 60;
  clearError("token-error");
  byId("token-dialog").showModal();
}

async function saveToken(event) {
  event.preventDefault();
  if (event.submitter && event.submitter.value === "cancel") {
    byId("token-dialog").close();
    return;
  }
  clearError("token-error");
  try {
    const response = await request("/tokens", {
      method: "POST",
      body: {
        name: byId("token-name").value.trim(),
        source_scopes: splitList(byId("token-sources").value),
        rate_limit_per_minute: Number(byId("token-rate").value),
      },
    });
    byId("token-dialog").close();
    revealSecret(response.value, response.token.name);
    await loadWorkspace();
  } catch (error) {
    showError("token-error", error);
  }
}

function revealSecret(value, name) {
  byId("secret-title").textContent = `${name} token`;
  byId("secret-value").textContent = value;
  byId("secret-dialog").showModal();
}

function openUser(id = "") {
  const item = state.users.find((candidate) => candidate.id === id);
  const dialog = byId("user-dialog");
  const form = byId("user-form");
  form.reset();
  clearError("user-error");
  form.dataset.mode = item ? "reset" : "create";
  form.dataset.id = item ? item.id : "";
  byId("user-name").value = item ? item.username : "";
  byId("user-name").disabled = Boolean(item);
  byId("user-role").closest("label").hidden = Boolean(item);
  dialog.querySelector("h2").textContent = item ? `Reset ${item.username}` : "Add user";
  form.querySelector(".button.primary").textContent = item ? "Reset password" : "Create user";
  dialog.showModal();
}

async function saveUser(event) {
  event.preventDefault();
  if (event.submitter && event.submitter.value === "cancel") {
    byId("user-dialog").close();
    return;
  }
  clearError("user-error");
  const form = byId("user-form");
  try {
    if (form.dataset.mode === "reset") {
      await request(`/users/${form.dataset.id}/password`, { method: "PUT", body: { password: byId("user-password").value } });
      toast("Password reset and active sessions revoked.");
    } else {
      await request("/users", { method: "POST", body: { username: byId("user-name").value.trim(), password: byId("user-password").value, role: byId("user-role").value } });
      toast("User created.");
    }
    byId("user-dialog").close();
    await loadWorkspace();
  } catch (error) {
    showError("user-error", error);
  }
}

function openPreview(id) {
  const item = state.destinations.find((candidate) => candidate.id === id);
  if (!item) return;
  byId("preview-form").reset();
  byId("preview-destination-id").value = id;
  byId("preview-title").textContent = `Preview ${item.name}`;
  const route = state.routes.find((candidate) => candidate.destination_id === id && candidate.source !== "*");
  byId("preview-source").value = route ? route.source : "home_assistant";
  byId("preview-result").hidden = true;
  byId("test-button").hidden = !isAdmin();
  clearError("preview-error");
  byId("preview-dialog").showModal();
}

function sampleEvent() {
  return {
    schema: "notifinho.event.v1",
    source: byId("preview-source").value.trim(),
    title: byId("preview-event-title").value.trim(),
    message: byId("preview-message").value.trim(),
    severity: byId("preview-severity").value,
    status: "active",
    metadata: { host: "webui-safe-preview" },
  };
}

async function runPreview(event) {
  event.preventDefault();
  const action = event.submitter && event.submitter.value;
  if (action === "cancel") {
    byId("preview-dialog").close();
    return;
  }
  if (!action) return;
  clearError("preview-error");
  const destinationId = byId("preview-destination-id").value;
  if (action === "test") {
    const accepted = await confirmAction("Send a real test delivery?", "This contacts the configured destination using the safe sample event.", "Send test");
    if (!accepted) return;
  }
  try {
    const response = await request(`/destinations/${destinationId}/${action}`, { method: "POST", body: { event: sampleEvent() } });
    const result = byId("preview-result");
    const selectedDestination = state.destinations.find((candidate) => candidate.id === destinationId);
    const outputType = response.preview ? response.preview.output_type : selectedDestination && selectedDestination.output_type;
    result.textContent = `${OUTPUT_NAMES[outputType] || friendlyName(outputType)} preview\n\n${JSON.stringify(response, null, 2)}`;
    result.hidden = false;
    if (action === "test") {
      const delivery = response.result || {};
      const detail = delivery.response_status ? `HTTP ${delivery.response_status}` : delivery.error_code || "No status returned";
      toast(delivery.success ? `Test delivery sent successfully (${detail}).` : `Test delivery failed (${detail}).`, delivery.success ? "success" : "error");
    } else {
      toast("Preview generated.");
    }
  } catch (error) {
    showError("preview-error", error);
  }
}

function confirmAction(title, message, acceptLabel = "Confirm") {
  byId("confirm-title").textContent = title;
  byId("confirm-message").textContent = message;
  byId("confirm-accept").textContent = acceptLabel;
  byId("confirm-dialog").showModal();
  return new Promise((resolve) => {
    state.confirmResolve = resolve;
  });
}

function resolveConfirm(value) {
  byId("confirm-dialog").close();
  if (state.confirmResolve) state.confirmResolve(value);
  state.confirmResolve = null;
}

async function resourceAction(action, id) {
  try {
    if (action === "dismiss-notice") {
      await request(`/notices/${id}/dismiss`, { method: "POST", body: {} });
      state.notices = state.notices.filter((item) => item.id !== id);
      renderNotices();
      return;
    } else if (action === "run-health-checks") {
      const response = await request("/health-checks");
      state.healthChecks = response.checks;
      renderHealthChecks();
      toast("Health checks completed.");
      return;
    } else if (action === "remove-avatar") {
      const response = await request("/account/avatar", { method: "DELETE" });
      state.user = response.user;
      applyAvatar("profile-avatar", state.user);
      applyAvatar("account-avatar", state.user);
      toast("Profile picture removed.");
      return;
    } else if (action === "export-platform") {
      await exportPlatform();
      return;
    } else if (action === "preview-portable") {
      await previewImport("portable");
      return;
    } else if (action === "preview-migration") {
      await previewImport("v1_yaml");
      return;
    } else if (action === "preview-local-migration") {
      await previewImport("local_yaml");
      return;
    } else if (action === "use-yaml-routing") {
      await setRoutingAuthority("yaml");
      return;
    } else if (action === "use-database-routing") {
      await setRoutingAuthority("database");
      return;
    } else if (action === "apply-import") {
      await applyImport();
      return;
    } else if (action === "create-backup") {
      await createBackup();
      return;
    } else if (action === "restore-backup") {
      await restoreBackup(id);
      return;
    } else if (action === "toggle-destination") {
      const item = state.destinations.find((candidate) => candidate.id === id);
      await request(`/destinations/${id}`, { method: "PATCH", body: { enabled: !item.enabled } });
      toast(`Destination ${item.enabled ? "disabled" : "enabled"}.`);
    } else if (action === "delete-destination") {
      const accepted = await confirmAction("Delete destination?", "Deletion is permanent and is rejected while a route still uses this destination.", "Delete");
      if (!accepted) return;
      await request(`/destinations/${id}`, { method: "DELETE" });
      toast("Destination deleted.");
    } else if (action === "toggle-route") {
      const item = state.routes.find((candidate) => candidate.id === id);
      await request(`/routes/${id}`, { method: "PATCH", body: { enabled: !item.enabled } });
      toast(`Route ${item.enabled ? "disabled" : "enabled"}.`);
    } else if (action === "move-route-up" || action === "move-route-down") {
      const item = state.routes.find((candidate) => candidate.id === id);
      const current = PRIORITIES.findIndex(([value]) => value === item.priority_name);
      const next = Math.max(0, Math.min(PRIORITIES.length - 1, current + (action === "move-route-up" ? -1 : 1)));
      if (current === next) return;
      await request(`/routes/${id}`, { method: "PATCH", body: { priority: PRIORITIES[next][0] } });
      toast(`Route priority changed to ${PRIORITIES[next][1]}.`);
    } else if (action === "delete-route") {
      const accepted = await confirmAction("Delete route?", "Events will stop using this route immediately.", "Delete");
      if (!accepted) return;
      await request(`/routes/${id}`, { method: "DELETE" });
      toast("Route deleted.");
    } else if (action === "rotate-token") {
      const accepted = await confirmAction("Rotate application token?", "The current value stops working immediately.", "Rotate");
      if (!accepted) return;
      const response = await request(`/tokens/${id}/rotate`, { method: "POST", body: {} });
      revealSecret(response.value, response.token.name);
    } else if (action === "revoke-token") {
      const accepted = await confirmAction("Revoke application token?", "Revocation is immediate and cannot be undone.", "Revoke");
      if (!accepted) return;
      await request(`/tokens/${id}/revoke`, { method: "POST", body: {} });
      toast("Token revoked.");
    } else if (action === "toggle-token") {
      const item = state.tokens.find((candidate) => candidate.id === id);
      await request(`/tokens/${id}`, { method: "PATCH", body: { enabled: item.enabled === false } });
      toast(`Application ${item.enabled === false ? "enabled" : "disabled"}.`);
    } else if (action === "delete-token") {
      const accepted = await confirmAction("Delete application credential?", "The credential stops working immediately and cannot be recovered.", "Delete");
      if (!accepted) return;
      await request(`/tokens/${id}`, { method: "DELETE" });
      toast("Application credential deleted.");
    } else if (action === "toggle-input") {
      const item = state.configuration.inputs.find((candidate) => candidate.name === id);
      await request(`/configuration/inputs/${id}`, { method: "PATCH", body: { enabled: !item.enabled } });
      toast(`Input ${item.enabled ? "disabled" : "enabled"}. Restart Notifinho to apply listener changes.`);
    } else if (action === "toggle-user") {
      const item = state.users.find((candidate) => candidate.id === id);
      const accepted = await confirmAction(`${item.enabled ? "Disable" : "Enable"} ${item.username}?`, item.enabled ? "Disabling the account revokes every active session." : "The user will be able to sign in again.", item.enabled ? "Disable" : "Enable");
      if (!accepted) return;
      await request(`/users/${id}`, { method: "PATCH", body: { enabled: !item.enabled } });
      toast(`User ${item.enabled ? "disabled" : "enabled"}.`);
    }
    await loadWorkspace();
  } catch (error) {
    toast(error.message || "The action failed.", "error");
  }
}

async function changePassword(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  if (form.get("new_password") !== form.get("confirm_password")) {
    toast("New password confirmation does not match.", "error");
    return;
  }
  const accepted = await confirmAction("Change password and sign out?", "Every active session for this account will be revoked.", "Change password");
  if (!accepted) return;
  try {
    await request("/account/password", { method: "PUT", body: { current_password: form.get("current_password"), new_password: form.get("new_password") } });
    expireSession();
    toast("Password changed. Sign in again.");
  } catch (error) {
    toast(error.message || "Password change failed.", "error");
  }
}

async function logout() {
  try {
    await request("/session", { method: "DELETE" });
  } catch (_error) {
    // The browser still clears local state if the session already expired.
  }
  expireSession();
}

async function copySecret() {
  try {
    await navigator.clipboard.writeText(byId("secret-value").textContent);
    toast("Token copied.");
  } catch (_error) {
    toast("Copy was blocked. Select the token and copy it manually.", "error");
  }
}

async function handleClick(event) {
  const target = event.target.closest("button");
  if (!target) return;
  if (target.dataset.view) {
    navigate(target.dataset.view);
    return;
  }
  if (target.dataset.closeDialog) {
    byId(target.dataset.closeDialog).close();
    return;
  }
  const action = target.dataset.action;
  const id = target.dataset.id || "";
  if (action === "new-destination") openDestination();
  else if (action === "edit-destination") openDestination(id);
  else if (action === "preview-destination") openPreview(id);
  else if (action === "new-route") openRoute();
  else if (action === "edit-route") openRoute(id);
  else if (action === "new-token") openToken();
  else if (action === "new-user") openUser();
  else if (action === "reset-user") openUser(id);
  else if (action) await resourceAction(action, id);
}

function bindEvents() {
  byId("bootstrap-form").addEventListener("submit", bootstrapAdministrator);
  byId("login-form").addEventListener("submit", login);
  byId("destination-form").addEventListener("submit", saveDestination);
  byId("destination-type").addEventListener("change", () => renderDestinationFields());
  byId("route-form").addEventListener("submit", saveRoute);
  byId("token-form").addEventListener("submit", saveToken);
  byId("user-form").addEventListener("submit", saveUser);
  byId("preview-form").addEventListener("submit", runPreview);
  byId("password-form").addEventListener("submit", changePassword);
  byId("preferences-form").addEventListener("submit", savePreferences);
  byId("notice-form").addEventListener("submit", saveNotice);
  byId("backup-settings-form").addEventListener("submit", saveBackupSettings);
  byId("avatar-form").addEventListener("submit", saveAvatar);
  byId("history-range").addEventListener("change", changeHistoryRange);
  byId("logout-button").addEventListener("click", logout);
  byId("copy-secret").addEventListener("click", copySecret);
  byId("refresh-button").addEventListener("click", refreshWorkspace);
  byId("delivery-search").addEventListener("input", renderDeliveries);
  byId("audit-search").addEventListener("input", renderAudit);
  byId("confirm-cancel").addEventListener("click", () => resolveConfirm(false));
  byId("confirm-accept").addEventListener("click", () => resolveConfirm(true));
  byId("confirm-dialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    resolveConfirm(false);
  });
  byId("secret-dialog").addEventListener("close", () => {
    byId("secret-value").textContent = "";
  });
  byId("import-dialog").addEventListener("close", () => {
    state.pendingImport = null;
    byId("import-result").textContent = "";
    byId("portable-file").value = "";
    const migrationFile = byId("migration-file");
    if (migrationFile) migrationFile.value = "";
    clearError("import-error");
  });
  byId("mobile-menu").addEventListener("click", () => {
    const shell = byId("app-shell");
    const open = shell.classList.toggle("nav-open");
    byId("mobile-menu").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", handleClick);
  window.addEventListener("hashchange", () => {
    const view = window.location.hash.slice(1);
    if (state.user && VIEW_TITLES[view]) navigate(view);
  });
}

bindEvents();
initialize();
