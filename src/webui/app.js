"use strict";

const API = "/api/v2";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const VIEW_TITLES = {
  dashboard: "Overview",
  sources: "Sources",
  destinations: "Destinations",
  routes: "Routes",
  tokens: "Applications",
  deliveries: "Delivery history",
  audit: "Audit log",
  users: "Users",
  settings: "Settings",
  updates: "Updates",
  inputs: "Inputs",
  backups: "Backups",
  data: "Data tools",
  account: "Account security",
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
const SOURCE_ICONS = {
  xen_orchestra: "/ui/source-icons/xen-orchestra.png",
  xo: "/ui/source-icons/xen-orchestra.png",
  xenorchestra: "/ui/source-icons/xen-orchestra.png",
  redfish: "/ui/source-icons/redfish.jpg",
  restful: "/ui/source-icons/rest-api.svg",
  rest_api: "/ui/source-icons/rest-api.svg",
  grafana: "/ui/source-icons/grafana.png",
  portainer: "/ui/source-icons/portainer.png",
  proxmox: "/ui/source-icons/proxmox.png",
  qnap: "/ui/source-icons/qnap.png",
  synology: "/ui/source-icons/synology.png",
  truenas: "/ui/source-icons/truenas.png",
  unifi_network: "/ui/source-icons/unifi-network.png",
  unifi_protect: "/ui/source-icons/unifi-protect.png",
  unifi_drive: "/ui/source-icons/unifi-drive.png",
  zabbix: "/ui/source-icons/zabbix.png",
  supermicro: "/ui/source-icons/supermicro.png",
  hpe_ilo: "/ui/source-icons/hpe-ilo.png",
  dell_idrac: "/ui/source-icons/dell-idrac.png",
  home_assistant: "/ui/source-icons/home-assistant.png",
};
const GENERIC_SOURCE_ICON = "/ui/source-icons/notifinho.png";
const PRIORITIES = [
  ["critical", "Critical"],
  ["high", "High"],
  ["normal", "Normal"],
  ["low", "Low"],
  ["lowest", "Lowest"],
];
const SOURCE_TRANSPORTS = {
  xen_orchestra: "SMTP", xo: "SMTP", xenorchestra: "SMTP", zabbix: "SMTP", qnap: "SMTP", truenas: "SMTP",
  redfish: "REST API", restful: "REST API", rest_api: "REST API",
  grafana: "HTTP", proxmox: "HTTP API", portainer: "HTTP API",
  home_assistant: "Home Assistant API",
  unifi_network: "UniFi API", unifi_protect: "UniFi API", unifi_drive: "UniFi API",
  supermicro: "Supermicro Redfish", hpe_ilo: "HPE iLO Redfish",
  dell_idrac: "Dell iDRAC Redfish", alfa: "Redfish", synology: "Synology API",
};
const SOURCE_CATEGORIES = {
  virtualization: { key: "virtualization", label: "Virtualization" },
  monitoring: { key: "monitoring", label: "Monitoring" },
  storage: { key: "storage", label: "Storage" },
  networking: { key: "networking", label: "Networking" },
  hardware: { key: "hardware", label: "Hardware" },
  automation: { key: "automation", label: "Automation" },
  containers: { key: "containers", label: "Containers" },
  security: { key: "security", label: "Security" },
  generic: { key: "generic", label: "Generic" },
};
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
  backupTargets: [],
  sourceCategories: {},
  removedSources: [],
  integrations: [],
  routeSourceOptions: [],
  versionStatus: null,
  managedMounts: false,
  configuration: null,
  notices: [],
  metrics: null,
  healthChecks: [],
  backupSettings: null,
  backupLastRun: null,
  workspaceErrors: [],
  historyRange: "1h",
  auditPageSize: 25,
  avatarEditor: { image: null, scale: 1, x: 0, y: 0, dragging: false, pointerX: 0, pointerY: 0 },
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

function readCsrfCookie(mode = "") {
  const names = mode === "secure"
    ? ["__Host-notifinho_csrf", "notifinho_csrf"]
    : ["notifinho_csrf", "__Host-notifinho_csrf"];
  for (const pair of document.cookie.split(";")) {
    const [rawName, ...rest] = pair.trim().split("=");
    if (names.includes(rawName)) return decodeURIComponent(rest.join("="));
  }
  return "";
}

class APIError extends Error {
  constructor(status, message, path = "", code = "", reference = "") {
    const details = [];
    if (status) details.push(`HTTP ${status}`);
    if (path) details.push(`${API}${path}`);
    if (reference) details.push(`reference ${reference}`);
    super(`${message || "Request failed"}${details.length ? ` (${details.join(" · ")})` : ""}`);
    this.status = status;
    this.path = path;
    this.code = code;
    this.reference = reference;
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
    throw new APIError(0, "Notifinho is not reachable.", path, "network_error");
  }
  const raw = await response.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (_error) {
      throw new APIError(response.status, "The server returned an invalid response.", path, "invalid_response");
    }
  }
  if (!response.ok) {
    if (response.status === 401 && state.user && path !== "/session") expireSession();
    throw new APIError(response.status, payload && payload.error, path, payload && payload.code, payload && payload.reference);
  }
  return payload;
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
  state.csrf = session.csrf_token || readCsrfCookie(session.cookie_mode);
  byId("login-view").hidden = true;
  byId("app-shell").hidden = false;
  byId("users-nav").hidden = !isAdmin();
  byId("settings-nav").hidden = !isAdmin();
  byId("inputs-nav").hidden = !isAdmin();
  byId("backups-nav").hidden = !isAdmin();
  byId("data-nav").hidden = !isAdmin();
  byId("add-destination-button").hidden = !isAdmin();
  byId("add-route-button").hidden = !isAdmin();
  byId("restart-header-button").hidden = !isAdmin();
  const name = state.user.username;
  const role = state.user.role;
  for (const id of ["profile-avatar", "account-avatar"]) applyAvatar(id, state.user);
  for (const id of ["profile-name", "account-name"]) byId(id).textContent = name;
  byId("profile-role").textContent = role;
  byId("account-role").textContent = role === "admin" ? "Administrator" : "User";
  byId("account-session").textContent = `Session expires ${formatTime(session.expires_at)}`;
}

async function restoreSession() {
  let session;
  try {
    session = await request("/session");
  } catch (error) {
    expireSession();
    if (!(error instanceof APIError) || ![401, 404].includes(error.status)) {
      byId("login-error").textContent = error.message || "Notifinho is not reachable.";
      byId("login-error").hidden = false;
    }
    return;
  }
  showApp(session);
  try {
    await loadWorkspace();
  } catch (error) {
    if (!(error instanceof APIError) || error.status !== 401) {
      state.workspaceErrors = [{
        component: "Workspace",
        message: error.message || "Request failed",
      }];
      renderWorkspaceErrors();
    }
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
    integrations: ["Integrations", request("/integrations"), (value) => {
      state.integrations = value.integrations || [];
      state.routeSourceOptions = value.route_options || [];
    }],
    destinations: ["Destinations", request("/destinations"), (value) => { state.destinations = value.destinations; }],
    routes: ["Routes", request("/routes"), (value) => { state.routes = value.routes; }],
    tokens: ["Applications", request("/tokens"), (value) => { state.tokens = value.tokens; }],
    deliveries: ["Delivery history", request("/deliveries"), (value) => { state.deliveries = value.deliveries; }],
    audit: ["Audit log", request("/audit-events"), (value) => { state.audit = value.audit_events; }],
    preferences: ["Regional settings", request("/preferences"), (value) => { state.preferences = value.preferences; }],
    notices: ["Notices", request("/notices"), (value) => { state.notices = value.notices; }],
    metrics: ["Overview metrics", request(`/metrics/${state.historyRange}`), (value) => { state.metrics = value.metrics; }],
    health: ["Health checks", request("/health-checks"), (value) => { state.healthChecks = value.checks; }],
    version: ["Version status", request("/version"), (value) => { state.versionStatus = value.version; }],
  };
  if (isAdmin()) {
    tasks.users = ["Users", request("/users"), (value) => { state.users = value.users; }];
    tasks.backups = ["Backups", request("/backups"), (value) => { state.backups = value.backups; }];
    tasks.backupTargets = ["Backup destinations", request("/backup-targets"), (value) => {
      state.backupTargets = value.targets;
      state.managedMounts = value.managed_mounts;
    }];
    tasks.configuration = ["Configuration inventory", request("/configuration/inventory"), (value) => { state.configuration = value.configuration; }];
    tasks.backupSettings = ["Backup settings", request("/backup-settings"), (value) => {
      state.backupSettings = value.settings;
      state.backupLastRun = value.last_run;
    }];
  }
  const entries = Object.values(tasks);
  const settled = await Promise.allSettled(entries.map(([, promise]) => promise));
  state.workspaceErrors = [];
  for (let index = 0; index < settled.length; index += 1) {
    const result = settled[index];
    const [label, , apply] = entries[index];
    if (result.status === "fulfilled") {
      apply(result.value);
      continue;
    }
    if (result.reason instanceof APIError && result.reason.status === 401) {
      throw result.reason;
    }
    state.workspaceErrors.push({
      component: label,
      message: result.reason && result.reason.message ? result.reason.message : "Request failed",
    });
  }
  if (!isAdmin()) {
    state.users = [];
    state.backups = [];
    state.backupTargets = [];
    state.managedMounts = false;
    state.configuration = null;
    state.backupSettings = null;
    state.backupLastRun = null;
  }
  renderAll();
  const requested = window.location.hash.slice(1);
  navigate(VIEW_TITLES[requested] && (!["users", "settings", "inputs", "backups", "data"].includes(requested) || isAdmin()) ? requested : state.currentView);
}

function renderAll() {
  renderWorkspaceErrors();
  renderNotices();
  renderDashboard();
  renderSources();
  renderDestinations();
  renderRoutes();
  renderTokens();
  renderDeliveries();
  renderAudit();
  renderUsers();
  renderBackups();
  renderBackupTargets();
  renderConfiguration();
  renderHealthChecks();
  renderBackupSettings();
  renderUpdates();
  renderPreferences();
  applyLanguage();
}

function renderWorkspaceErrors() {
  const alert = byId("workspace-alert");
  const list = byId("workspace-alert-list");
  list.replaceChildren();
  for (const failure of state.workspaceErrors) {
    list.append(element("li", {
      text: `${failure.component}: ${failure.message}`,
    }));
  }
  alert.hidden = state.workspaceErrors.length === 0;
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
  if (!VIEW_TITLES[view] || (["users", "settings", "inputs", "backups", "data"].includes(view) && !isAdmin())) view = "dashboard";
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
  byId("page-title").textContent = VIEW_TITLES[view];
  closeProfileMenu();
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
    const actions = element("div", { className: "notice-actions" });
    if (item.persistent) {
      const target = item.kind === "update" ? "updates" : "audit";
      actions.append(actionButton("Resolve", "open-notice-target", target, item.kind === "update" ? "primary" : "danger"));
    } else {
      const close = actionButton("×", "dismiss-notice", item.id, "icon-button notice-close");
      close.setAttribute("aria-label", `Close ${item.name}`);
      close.title = "Close notice";
      actions.append(close);
    }
    if (isAdmin() && item.kind === "announcement") {
      actions.prepend(actionButton("Edit", "edit-notice", item.id));
    }
    list.append(element("div", { className: `notice-item ${status}` }, [
      element("div", {}, [
        element("div", { className: "notice-title" }, [element("strong", { text: item.name }), badge(capitalize(item.status), status)]),
        element("p", { text: item.message }),
        element("small", { text: formatTime(item.created_at) }),
      ]),
      actions,
    ]));
  }
}

function beginNoticeEdit(id) {
  const item = state.notices.find((candidate) => candidate.id === id);
  if (!item || item.kind !== "announcement" || !isAdmin()) return;
  byId("notice-id").value = item.id;
  byId("notice-name").value = item.name;
  byId("notice-message").value = item.message;
  byId("notice-status").value = item.status;
  byId("notice-submit").textContent = "Update notice";
  byId("notice-name").focus();
}

function capitalize(value) {
  const text = String(value || "");
  return text ? text[0].toUpperCase() + text.slice(1) : "—";
}

function integrationBySource(value) {
  const key = String(value || "").toLowerCase();
  return state.integrations.find((item) => item.id === key || (item.sources || []).includes(key)) || null;
}

function inputLabel(value) {
  const labels = { smtp: "SMTP", http: "HTTP", redfish: "Redfish" };
  return labels[String(value || "").toLowerCase()] || String(value || "Any input").toUpperCase();
}

function routeSourceDescriptor(source, inputType = "") {
  if (source === "*") {
    const input = inputLabel(inputType || "http");
    return { integration: "Generic", input, label: `Generic (${input})` };
  }
  const item = integrationBySource(source);
  const integration = item ? item.name : friendlyName(source);
  const input = inputLabel(inputType || "");
  return { integration, input, label: inputType ? `${integration} (${input})` : integration };
}

function friendlyName(value) {
  const item = integrationBySource(value);
  if (item) return item.name;
  const special = { home_assistant: "Home Assistant", hpe_ilo: "HPE iLO", dell_idrac: "Dell iDRAC", xen_orchestra: "Xen Orchestra", xo: "Xen Orchestra", xenorchestra: "Xen Orchestra", redfish: "Redfish", restful: "RESTful API", rest_api: "REST API", unifi_network: "UniFi Network", unifi_protect: "UniFi Protect", unifi_drive: "UniFi Drive" };
  const key = String(value || "").toLowerCase();
  return special[key] || String(value || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function outputIcon(type) {
  if (OUTPUT_ICONS[type]) return element("img", { className: "output-icon-image", attributes: { src: OUTPUT_ICONS[type], alt: "" } });
  const labels = { teams: "T", slack: "S", webhook: "↗" };
  return element("span", { className: `output-icon-fallback ${type}`, text: labels[type] || String(type || "?").slice(0, 1).toUpperCase(), attributes: { "aria-hidden": "true" } });
}

function sourceIcon(source) {
  const key = String(source || "").toLowerCase();
  return element("img", {
    className: "source-product-icon",
    attributes: {
      src: SOURCE_ICONS[key] || GENERIC_SOURCE_ICON,
      alt: "",
      loading: "lazy",
    },
    dataset: { sourceKey: key },
  });
}

function sourceInputType(source, routeInput = "") {
  if (routeInput) return inputLabel(routeInput);
  const observed = state.deliveries.find((item) => item.source === source && item.input_type);
  if (observed && observed.input_type) return inputLabel(observed.input_type);
  const integration = integrationBySource(source);
  if (integration && integration.inputs.length === 1) return integration.inputs[0].name;
  return integration ? integration.inputs.map((item) => item.name).join(", ") : "HTTP";
}

function sourceCategory(source) {
  const item = integrationBySource(source);
  const key = item ? item.category : "generic";
  return SOURCE_CATEGORIES[key] || SOURCE_CATEGORIES.generic;
}

function sourceIsActive(source) {
  return state.routes.some((route) =>
    route.enabled && (route.source === source || route.source === "*"));
}

function renderFlow() {
  const container = byId("dashboard-flow");
  container.replaceChildren();
  for (const route of state.routes) {
    const destination = state.destinations.find((item) => item.id === route.destination_id);
    const problem = route.enabled && (!destination || !destination.enabled || (!destination.secret_configured && ["discord", "teams", "slack", "webhook"].includes(destination.output_type)));
    const status = !route.enabled ? "disabled" : problem ? "problem" : "active";
    const descriptor = routeSourceDescriptor(route.source, route.input_type);
    const integration = integrationBySource(route.source);
    const iconKey = route.source === "*" ? "generic" : integration ? integration.icon_key : route.source;
    const category = route.source === "*" ? SOURCE_CATEGORIES.generic : sourceCategory(route.source);
    const arrow = status === "problem" ? "×" : "➜";
    container.append(element("div", { className: `flow-row ${status}` }, [
      element("div", { className: `flow-node source-node category-${category.key}` }, [sourceIcon(iconKey), element("div", {}, [element("strong", { text: descriptor.integration }), element("small", { text: descriptor.input })])]),
      element("div", { className: "flow-route" }, [element("span", { className: "flow-arrow", text: arrow }), element("div", {}, [element("strong", { text: route.name }), element("small", { text: filterSummary(route.filters) })]), element("span", { className: "flow-arrow delayed", text: arrow })]),
      element("div", { className: "flow-node destination-node" }, [outputIcon(destination && destination.output_type), element("div", {}, [element("strong", { text: destination ? (OUTPUT_NAMES[destination.output_type] || friendlyName(destination.output_type)) : "Missing destination" }), element("small", { text: destination ? (destination.settings.channel_name || destination.name) : "Configuration error" })])]),
    ]));
  }
  if (!container.children.length) empty(container, "No routing flow", "Create a destination and route to display it here.");
}

function discoveredSources() {
  return state.integrations.map((item) => item.id);
}

function renderSources() {
  const body = byId("source-table");
  body.replaceChildren();
  byId("source-empty").hidden = state.integrations.length > 0;
  if (!state.integrations.length) {
    byId("source-empty").replaceChildren(
      element("strong", { text: "No integrations available" }),
      element("span", { text: "The built-in integration catalogue could not be loaded." }),
    );
    return;
  }
  for (const integration of state.integrations) {
    const category = SOURCE_CATEGORIES[integration.category] || SOURCE_CATEGORIES.generic;
    const select = element("select", {
      dataset: { integrationCategory: integration.id },
      disabled: !isAdmin(),
      attributes: { "aria-label": `Category for ${integration.name}` },
    });
    for (const item of Object.values(SOURCE_CATEGORIES)) {
      select.append(element("option", { value: item.key, text: item.label }));
    }
    select.value = category.key;
    const details = element("details", { className: "integration-inputs" }, [
      element("summary", { text: `${integration.inputs.length} input${integration.inputs.length === 1 ? "" : "s"} available` }),
      element("div", { className: "integration-input-list" }, integration.inputs.map((item) =>
        element("div", { className: "integration-input-row" }, [
          badge(item.name),
          element("span", { text: `${integration.name} events received through ${item.name}` }),
        ])
      )),
    ]);
    body.append(element("tr", {}, [
      element("td", {}, [element("div", { className: "source-identity" }, [sourceIcon(integration.icon_key || integration.id), element("div", {}, [element("strong", { text: integration.name }), element("small", { text: "Built-in integration" })])])]),
      element("td", {}, details),
      element("td", {}, select),
    ]));
  }
}

async function saveSourceCategory(event) {
  const select = event.target.closest("[data-integration-category]");
  if (!select || !isAdmin()) return;
  const integrationId = select.dataset.integrationCategory;
  select.disabled = true;
  try {
    const response = await request("/integrations", {
      method: "PUT",
      body: { source: integrationId, category: select.value },
    });
    state.integrations = response.integrations || [];
    state.routeSourceOptions = response.route_options || [];
    renderSources();
    renderFlow();
    const integration = integrationBySource(integrationId);
    toast(`${integration ? integration.name : friendlyName(integrationId)} moved to ${SOURCE_CATEGORIES[select.value].label}.`);
  } catch (error) {
    renderSources();
    toast(error.message || "Integration category could not be saved.", "error");
  }
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
        actionButton("Send test", "test-destination-card", item.id, "primary"),
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
          element("div", {}, [element("strong", { text: item.name }), element("small", { text: `${OUTPUT_NAMES[item.output_type] || friendlyName(item.output_type)} · ${item.settings.channel_name || "Channel not labelled"}` })]),
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
    const descriptor = routeSourceDescriptor(item.source, item.input_type);
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
      element("td", { text: descriptor.integration }),
      element("td", { text: descriptor.input }),
      element("td", { text: destinationTypeName(item.destination_id) }),
      element("td", {}, element("small", { text: filterSummary(item.filters) })),
      element("td", { text: capitalize(item.priority_name || "normal") }),
      element("td", {}, status),
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
  const items = state.deliveries.filter((item) => JSON.stringify([item.source, item.device_name, item.event_name, item.title, item.outcome, item.safe_error, item.error_code]).toLowerCase().includes(query));
  const container = byId("delivery-list");
  container.replaceChildren();
  if (!items.length) {
    empty(container, query ? "No matching deliveries" : "No delivery history", query ? "Try a different search." : "Delivery attempts appear after matched events are submitted.");
    return;
  }
  for (const item of items) {
    const delivered = ["delivered", "success"].includes(item.outcome);
    const semantic = String(item.event_status || item.severity || item.outcome || "").toLowerCase();
    const semanticFailure = ["error", "failure", "failed", "critical", "severe"].includes(semantic);
    const semanticInformation = ["information", "info", "informational"].includes(semantic);
    const style = semanticFailure ? "danger" : semanticInformation ? "information" : delivered ? "success" : item.retryable ? "warning" : "danger";
    const error = item.safe_error || item.error_code || (delivered ? "Delivery completed" : "No transport error reported");
    const heading = item.device_name
      ? `${item.device_name} • ${item.event_name || item.title || "Event"}`
      : `${friendlyName(item.source)} • ${item.event_name || item.title || "Untitled event"}`;
    const statusText = capitalize(item.event_status || item.severity || item.outcome);
    container.append(element("article", { className: `timeline-item ${style}` }, [
      element("span", { className: "event-indicator", text: semanticFailure ? "!" : semanticInformation ? "i" : delivered ? "✓" : "!" }),
      element("div", {}, [
        element("strong", { text: heading }),
        element("small", { className: "delivery-context", text: `${friendlyName(item.source)} • ${semanticFailure ? "🚨" : "✓"} ${statusText}${item.device_name ? ` • 📍 ${item.device_name}` : ""}` }),
        element("p", { className: "event-description", text: item.event_description || error }),
        element("div", { className: "resource-meta" }, [badge(delivered ? "Delivered" : capitalize(item.outcome), delivered ? "success" : "danger"), badge(capitalize(item.severity), style), badge(statusText, style), badge(`Attempt ${item.attempt_number}`), badge(`Input ${item.input_type || sourceInputType(item.source)}`), item.response_status ? badge(`Destination HTTP ${item.response_status}`) : null]),
      ]),
      element("div", { className: "timeline-meta" }, [element("span", { text: formatTime(item.completed_at || item.created_at) }), item.retryable ? element("small", { text: "Retryable" }) : null]),
    ]));
  }
}

function renderAudit() {
  const query = byId("audit-search").value.trim().toLowerCase();
  const items = state.audit.filter((item) => JSON.stringify([item.action, item.resource_type, item.outcome, item.details]).toLowerCase().includes(query)).slice(0, state.auditPageSize);
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

function renderBackupTargets() {
  const body = byId("backup-target-table");
  if (!body) return;
  body.replaceChildren();
  for (const item of state.backupTargets) {
    const outcome = item.last_test_outcome;
    const status = !item.enabled ? "Disabled" : outcome === "success" ? "Writable" : outcome === "failed" ? "Test failed" : "Not tested";
    const style = !item.enabled ? "warning" : outcome === "success" ? "success" : outcome === "failed" ? "danger" : "warning";
    const location = item.type === "local"
      ? item.local_path
      : item.type === "nfs" ? item.remote_path : `${item.share_name}${item.remote_path ? `/${item.remote_path}` : ""}`;
    const actions = element("div", { className: "row-actions" }, [
      actionButton("Test", "test-backup-target", item.id),
      actionButton("Edit", "edit-backup-target", item.id),
      actionButton("Delete", "delete-backup-target", item.id, "danger"),
    ]);
    body.append(element("tr", {}, [
      element("td", {}, badge(item.type.toUpperCase())),
      element("td", {}, [element("strong", { text: item.name }), item.last_error ? element("small", { text: item.last_error }) : null]),
      element("td", { text: item.host || "—" }),
      element("td", {}, element("code", { text: location })),
      element("td", {}, badge(status, style)),
      element("td", {}, actions),
    ]));
  }
  if (!state.backupTargets.length) {
    body.append(element("tr", {}, element("td", { text: "No backup destinations configured", attributes: { colspan: "6" } })));
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
  const target = byId("backup-target");
  target.replaceChildren(element("option", { value: "", text: "Local state only" }));
  for (const item of state.backupTargets) {
    target.append(element("option", { value: item.id, text: `${item.name} (${item.type.toUpperCase()})` }));
  }
  target.value = settings.target_id || "";
  byId("backup-managed-mounts").checked = settings.managed_mounts === true;
  const [hourText, minuteText] = String(settings.time || "02:00").split(":");
  const hour = Number(hourText);
  const scheduled = state.preferences.time_format === "12"
    ? `${hour % 12 || 12}:${minuteText} ${hour < 12 ? "AM" : "PM"}`
    : `${hourText}:${minuteText}`;
  byId("backup-time-display").textContent = `Scheduled time: ${scheduled}`;
  byId("backup-last-run").textContent = state.backupLastRun
    ? `Last scheduled run: ${capitalize(state.backupLastRun.outcome || "pending")} · ${formatTime(state.backupLastRun.completed_at || state.backupLastRun.started_at)}`
    : "No scheduled run recorded.";
}

function renderUpdates() {
  const version = state.versionStatus || {};
  byId("running-version").textContent = version.running || "—";
  byId("available-version").textContent = version.available || "Not advertised";
  byId("update-status").textContent = version.update_available
    ? `Version ${version.available} is available. Review the release notes and deploy the versioned image.`
    : "Notifinho is up to date with the advertised version.";
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
  const form = event.currentTarget;
  try {
    const id = byId("notice-id").value;
    const response = await request(id ? `/notices/${id}` : "/notices", {
      method: id ? "PATCH" : "POST",
      body: {
        name: byId("notice-name").value.trim(),
        message: byId("notice-message").value.trim(),
        status: byId("notice-status").value,
      },
    });
    const notice = response.notice;
    const current = state.notices.findIndex((item) => item.id === notice.id);
    if (current >= 0) state.notices[current] = notice;
    else state.notices.unshift(notice);
    form.reset();
    byId("notice-id").value = "";
    byId("notice-submit").textContent = "Send notice";
    renderNotices();
    toast(id ? "Notice updated." : "Notice sent to users.");
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
        target_id: byId("backup-target").value,
        managed_mounts: byId("backup-managed-mounts").checked,
        external_enabled: false,
        external_type: "nfs",
        external_path: "",
      },
    });
    state.backupSettings = response.settings;
    renderBackupSettings();
    toast("Backup settings saved.");
  } catch (error) {
    toast(error.message || "Backup settings could not be saved.", "error");
  }
}

function updateBackupTargetFields() {
  const type = byId("backup-target-type").value;
  for (const item of document.querySelectorAll(".backup-remote-field")) item.hidden = type === "local";
  for (const item of document.querySelectorAll(".backup-nfs-field")) item.hidden = type !== "nfs";
  for (const item of document.querySelectorAll(".backup-smb-field")) item.hidden = type !== "smb";
  for (const item of document.querySelectorAll(".backup-local-field")) item.hidden = type !== "local";
  byId("backup-target-host").required = type !== "local";
  byId("backup-target-remote-path").required = type === "nfs";
  byId("backup-target-share").required = type === "smb";
  byId("backup-target-local-path").required = type === "local";
}

function openBackupTarget(id = "") {
  const item = state.backupTargets.find((candidate) => candidate.id === id);
  byId("backup-target-form").reset();
  clearError("backup-target-error");
  byId("backup-target-id").value = item ? item.id : "";
  byId("backup-target-name").value = item ? item.name : "";
  byId("backup-target-type").value = item ? item.type : "local";
  byId("backup-target-enabled").checked = item ? item.enabled : true;
  byId("backup-target-host").value = item ? item.host : "";
  byId("backup-target-remote-path").value = item && item.type === "nfs" ? item.remote_path : "";
  byId("backup-target-share").value = item ? item.share_name : "";
  byId("backup-target-smb-path").value = item && item.type === "smb" ? item.remote_path : "";
  byId("backup-target-local-path").value = item && item.type === "local" ? item.local_path : "";
  byId("backup-target-username").value = item ? item.username : "";
  byId("backup-target-domain").value = item ? item.domain : "";
  byId("backup-target-options").value = item ? item.mount_options : "";
  byId("backup-target-password").value = "";
  byId("backup-target-dialog-title").textContent = item ? `Edit ${item.name}` : "Add backup destination";
  updateBackupTargetFields();
  byId("backup-target-dialog").showModal();
}

async function saveBackupTarget(event) {
  event.preventDefault();
  if (event.submitter && event.submitter.value === "cancel") {
    byId("backup-target-dialog").close();
    return;
  }
  clearError("backup-target-error");
  const id = byId("backup-target-id").value;
  const type = byId("backup-target-type").value;
  try {
    if (type !== "local" && !state.managedMounts) {
      const current = state.backupSettings || {
        schedule: "disabled",
        time: "02:00",
        weekday: 0,
        day: 1,
        target_id: "",
        external_enabled: false,
        external_type: "nfs",
        external_path: "",
      };
      const settings = await request("/backup-settings", {
        method: "PUT",
        body: { ...current, managed_mounts: true },
      });
      state.backupSettings = settings.settings;
      state.managedMounts = true;
    }
    await request(id ? `/backup-targets/${id}` : "/backup-targets", {
      method: id ? "PATCH" : "POST",
      body: {
        name: byId("backup-target-name").value.trim(),
        type,
        host: byId("backup-target-host").value.trim(),
        remote_path: type === "nfs" ? byId("backup-target-remote-path").value.trim() : byId("backup-target-smb-path").value.trim(),
        share_name: byId("backup-target-share").value.trim(),
        local_path: byId("backup-target-local-path").value.trim(),
        username: byId("backup-target-username").value.trim(),
        domain: byId("backup-target-domain").value.trim(),
        password: byId("backup-target-password").value,
        mount_options: byId("backup-target-options").value.trim(),
        enabled: byId("backup-target-enabled").checked,
      },
    });
    byId("backup-target-dialog").close();
    await loadWorkspace();
    toast(type === "local"
      ? (id ? "Backup destination updated." : "Backup destination added.")
      : "Remote backup destination saved with automatic managed mounting enabled.");
  } catch (error) {
    showError("backup-target-error", error);
  }
}

async function runBackupNow() {
  const response = await request("/backups/run", {
    method: "POST",
    body: { target_id: byId("backup-target").value },
  });
  await loadWorkspace();
  toast(response.run.outcome === "success" ? "Backup completed." : "Backup failed.", response.run.outcome === "success" ? "success" : "error");
}

async function restartPlatform(event) {
  event.preventDefault();
  if (event.submitter && event.submitter.value === "cancel") {
    byId("restart-dialog").close();
    return;
  }
  clearError("restart-error");
  try {
    await request("/reboot", {
      method: "POST",
      body: { reason: byId("restart-reason").value.trim() },
    });
    byId("restart-dialog").close();
    toast("Restart accepted. Notifinho will be briefly unavailable.", "success");
  } catch (error) {
    showError("restart-error", error);
  }
}

async function saveAvatar(event) {
  event.preventDefault();
  if (!state.avatarEditor.image) {
    toast("Choose a picture first.", "error");
    return;
  }
  try {
    const imageData = byId("avatar-canvas").toDataURL("image/png");
    const response = await request("/account/avatar", { method: "PUT", body: { image_data: imageData } });
    state.user = response.user;
    applyAvatar("profile-avatar", state.user);
    applyAvatar("account-avatar", state.user);
    byId("avatar-file").value = "";
    byId("avatar-editor").hidden = true;
    if (state.avatarEditor.image && typeof state.avatarEditor.image.close === "function") {
      state.avatarEditor.image.close();
    }
    state.avatarEditor.image = null;
    toast("Profile picture updated.");
  } catch (error) {
    toast(error.message || "Profile picture could not be saved.", "error");
  }
}

async function loadAvatarEditor() {
  const file = byId("avatar-file").files && byId("avatar-file").files[0];
  if (!file) return;
  const supportedType = ["image/png", "image/jpeg", "image/webp"].includes(file.type);
  const supportedExtension = !file.type && /\.(?:png|jpe?g|webp)$/i.test(file.name);
  if ((!supportedType && !supportedExtension) || file.size > 10 * 1024 * 1024) {
    toast("Choose a PNG, JPEG, or WebP image up to 10 MiB.", "error");
    byId("avatar-file").value = "";
    return;
  }
  let image;
  if (state.avatarEditor.image && typeof state.avatarEditor.image.close === "function") {
    state.avatarEditor.image.close();
  }
  if ("createImageBitmap" in window) {
    try {
      image = await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch (_error) {
      image = null;
    }
  }
  if (!image) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("The picture could not be read."));
      reader.readAsDataURL(file);
    });
    image = new Image();
    image.decoding = "async";
    image.src = dataUrl;
    try {
      await image.decode();
    } catch (_error) {
      await new Promise((resolve, reject) => {
        if (image.complete && image.naturalWidth) {
          resolve();
          return;
        }
        image.onload = resolve;
        image.onerror = () => reject(new Error("The picture could not be decoded as PNG, JPEG, or WebP."));
      });
    }
  }
  state.avatarEditor.image = image;
  state.avatarEditor.scale = 1;
  byId("avatar-zoom").value = "1";
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const base = Math.max(256 / width, 256 / height);
  state.avatarEditor.x = (256 - width * base) / 2;
  state.avatarEditor.y = (256 - height * base) / 2;
  byId("avatar-editor").hidden = false;
  drawAvatarEditor();
}

function drawAvatarEditor() {
  const image = state.avatarEditor.image;
  if (!image) return;
  const canvas = byId("avatar-canvas");
  const context = canvas.getContext("2d");
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const base = Math.max(canvas.width / width, canvas.height / height);
  const scale = base * state.avatarEditor.scale;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.save();
  context.beginPath();
  context.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2, 0, Math.PI * 2);
  context.clip();
  context.drawImage(image, state.avatarEditor.x, state.avatarEditor.y, width * scale, height * scale);
  context.restore();
}

function zoomAvatarEditor() {
  const image = state.avatarEditor.image;
  if (!image) return;
  const previous = state.avatarEditor.scale;
  const next = Number(byId("avatar-zoom").value);
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const base = Math.max(256 / width, 256 / height);
  const centerX = (128 - state.avatarEditor.x) / (base * previous);
  const centerY = (128 - state.avatarEditor.y) / (base * previous);
  state.avatarEditor.scale = next;
  state.avatarEditor.x = 128 - centerX * base * next;
  state.avatarEditor.y = 128 - centerY * base * next;
  drawAvatarEditor();
}

function moveAvatarEditor(event) {
  if (!state.avatarEditor.dragging) return;
  state.avatarEditor.x += event.clientX - state.avatarEditor.pointerX;
  state.avatarEditor.y += event.clientY - state.avatarEditor.pointerY;
  state.avatarEditor.pointerX = event.clientX;
  state.avatarEditor.pointerY = event.clientY;
  drawAvatarEditor();
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
    const migrationFile = byId("migration-file");
    if (migrationFile) migrationFile.value = "";
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
  const presentation = { key: "channel_name", label: "Channel / destination" };
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
  const originalType = byId("destination-original-type").value;
  const typeChanged = editing && originalType && originalType !== type;
  for (const input of secretsContainer.querySelectorAll("[required]")) input.required = !editing || typeChanged;
  if (typeChanged) byId("destination-help").textContent += " New credentials are required because the destination type changed.";
}
function openDestination(id = "") {
  const item = state.destinations.find((candidate) => candidate.id === id);
  byId("destination-form").reset();
  clearError("destination-error");
  byId("destination-id").value = item ? item.id : "";
  byId("destination-original-type").value = item ? item.output_type : "";
  byId("destination-name").value = item ? item.name : "";
  byId("destination-type").value = item ? item.output_type : "discord";
  byId("destination-name").disabled = false;
  byId("destination-type").disabled = false;
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
  const submit = byId("destination-submit");
  const name = byId("destination-name").value.trim();
  const duplicate = state.destinations.find((item) => item.id !== id && item.name.trim().toLowerCase() === name.toLowerCase());
  if (duplicate) {
    showError("destination-error", new APIError(409, `A destination named "${name}" already exists. Choose another name.`, id ? `/destinations/${id}` : "/destinations", "resource_conflict"));
    return;
  }
  submit.disabled = true;
  try {
    const settings = collectFields(byId("destination-settings"));
    const secret = collectFields(byId("destination-secrets"));
    const payload = {
      name,
      output_type: byId("destination-type").value,
      settings,
      enabled: byId("destination-enabled").checked,
    };
    if (isAdmin()) payload.shared = byId("destination-shared").checked;
    if (Object.keys(secret).length) payload.secret = secret;
    await request(id ? `/destinations/${id}` : "/destinations", { method: id ? "PATCH" : "POST", body: payload });
    byId("destination-dialog").close();
    await loadWorkspace();
    toast(id ? "Destination updated." : "Destination added.");
  } catch (error) {
    showError("destination-error", error);
  } finally {
    submit.disabled = false;
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

function setRouteSourceOptions(selectedSource = "", selectedInput = "") {
  const select = byId("route-source");
  select.replaceChildren();
  const currentValue = `${selectedSource}::${selectedInput}`;
  for (const option of state.routeSourceOptions) {
    const value = `${option.source}::${option.input_type}`;
    select.append(element("option", { value, text: option.label }));
  }
  if (selectedSource && ![...select.options].some((option) => option.value === currentValue)) {
    const descriptor = routeSourceDescriptor(selectedSource, selectedInput);
    select.append(element("option", { value: currentValue, text: `${descriptor.label} (legacy)` }));
  }
  if (selectedSource) select.value = currentValue;
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
  setRouteSourceOptions(item ? item.source : "zabbix", item ? item.input_type : "smtp");
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
  const [source, inputType] = byId("route-source").value.split("::", 2);
  try {
    await request(id ? `/routes/${id}` : "/routes", {
      method: id ? "PATCH" : "POST",
      body: {
        name: byId("route-name").value.trim(),
        source,
        input_type: inputType,
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

function cardSampleEvent(destination) {
  return {
    schema: "notifinho.event.v1",
    source: "notifinho",
    title: `${destination.name} test delivery`,
    message: `This is a safe Notifinho test for the ${OUTPUT_NAMES[destination.output_type] || friendlyName(destination.output_type)} destination "${destination.name}".`,
    severity: "information",
    status: "active",
    provider: "Notifinho",
    metadata: { host: destination.name, component: "Destination test" },
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
  try {
    const response = await request(`/destinations/${destinationId}/${action}`, { method: "POST", body: { event: sampleEvent() } });
    const result = byId("preview-result");
    const selectedDestination = state.destinations.find((candidate) => candidate.id === destinationId);
    const outputType = response.preview ? response.preview.output_type : selectedDestination && selectedDestination.output_type;
    result.textContent = `${OUTPUT_NAMES[outputType] || friendlyName(outputType)} preview\n\n${JSON.stringify(response, null, 2)}`;
    result.hidden = false;
    if (action === "test") {
      const delivery = response.result || {};
      const detail = delivery.response_status ? `HTTP ${delivery.response_status}` : delivery.safe_error || delivery.error_code || "No status returned";
      toast(delivery.success ? `Test delivery sent successfully (${detail}).` : `Test delivery failed (${detail}).`, delivery.success ? "success" : "error");
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
    } else if (action === "edit-notice") {
      beginNoticeEdit(id);
      return;
    } else if (action === "open-notice-target") {
      navigate(id === "updates" ? "updates" : "audit");
      return;
    } else if (action === "logout") {
      await logout();
      return;
    } else if (action === "run-health-checks") {
      const response = await request("/health-checks");
      state.healthChecks = response.checks;
      const audit = await request("/audit-events");
      state.audit = audit.audit_events;
      renderHealthChecks();
      renderAudit();
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
    } else if (action === "run-backup-now") {
      await runBackupNow();
      return;
    } else if (action === "test-backup-target") {
      const response = await request(`/backup-targets/${id}/test`, { method: "POST", body: {} });
      const index = state.backupTargets.findIndex((item) => item.id === id);
      if (index >= 0) state.backupTargets[index] = response.target;
      renderBackupTargets();
      toast(response.target.last_test_outcome === "success" ? "Backup destination is writable." : response.target.last_error || "Backup destination test failed.", response.target.last_test_outcome === "success" ? "success" : "error");
      return;
    } else if (action === "delete-backup-target") {
      const accepted = await confirmAction("Delete backup destination?", "The destination record and stored credential are removed. Existing backup files are not deleted.", "Delete");
      if (!accepted) return;
      await request(`/backup-targets/${id}`, { method: "DELETE" });
      await loadWorkspace();
      toast("Backup destination removed.");
      return;
    } else if (action === "restart-platform") {
      byId("restart-form").reset();
      clearError("restart-error");
      byId("restart-dialog").showModal();
      return;
    } else if (action === "restore-backup") {
      await restoreBackup(id);
      return;
    } else if (action === "toggle-destination") {
      const item = state.destinations.find((candidate) => candidate.id === id);
      await request(`/destinations/${id}`, { method: "PATCH", body: { enabled: !item.enabled } });
      toast(`Destination ${item.enabled ? "disabled" : "enabled"}.`);
    } else if (action === "test-destination-card") {
      const destination = state.destinations.find((candidate) => candidate.id === id);
      if (!destination) return;
      const response = await request(`/destinations/${id}/test`, {
        method: "POST",
        body: { event: cardSampleEvent(destination) },
      });
      const delivery = response.result || {};
      const detail = delivery.response_status ? `HTTP ${delivery.response_status}` : delivery.safe_error || delivery.error_code || "No status returned";
      toast(delivery.success ? `Test delivery sent successfully (${detail}).` : `Test delivery failed (${detail}).`, delivery.success ? "success" : "error");
      return;
    } else if (action === "delete-destination") {
      const accepted = await confirmAction("Delete destination?", "Deletion is permanent and is rejected while a route still uses this destination.", "Delete");
      if (!accepted) return;
      await request(`/destinations/${id}`, { method: "DELETE" });
      toast("Destination deleted.");
    } else if (action === "toggle-route") {
      const item = state.routes.find((candidate) => candidate.id === id);
      await request(`/routes/${id}`, { method: "PATCH", body: { enabled: !item.enabled } });
      toast(`Route ${item.enabled ? "disabled" : "enabled"}.`);
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

function toggleProfileMenu() {
  const menu = byId("profile-menu-popover");
  const open = menu.hidden;
  menu.hidden = !open;
  byId("profile-menu-button").setAttribute("aria-expanded", String(open));
  if (open) menu.querySelector("button").focus();
}

function closeProfileMenu() {
  const menu = byId("profile-menu-popover");
  if (!menu) return;
  menu.hidden = true;
  byId("profile-menu-button").setAttribute("aria-expanded", "false");
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
  if (!target) {
    if (!event.target.closest(".profile-menu")) closeProfileMenu();
    return;
  }
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
  if (action === "toggle-profile-menu") toggleProfileMenu();
  else if (action === "new-destination") openDestination();
  else if (action === "edit-destination") openDestination(id);
  else if (action === "preview-destination") openPreview(id);
  else if (action === "new-route") openRoute();
  else if (action === "edit-route") openRoute(id);
  else if (action === "new-token") openToken();
  else if (action === "new-user") openUser();
  else if (action === "reset-user") openUser(id);
  else if (action === "new-backup-target") openBackupTarget();
  else if (action === "edit-backup-target") openBackupTarget(id);
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
  byId("backup-target-form").addEventListener("submit", saveBackupTarget);
  byId("backup-target-type").addEventListener("change", updateBackupTargetFields);
  byId("restart-form").addEventListener("submit", restartPlatform);
  byId("avatar-form").addEventListener("submit", saveAvatar);
  byId("avatar-file").addEventListener("change", () => loadAvatarEditor().catch((error) => toast(error.message, "error")));
  byId("avatar-zoom").addEventListener("input", zoomAvatarEditor);
  byId("avatar-canvas").addEventListener("pointerdown", (event) => {
    state.avatarEditor.dragging = true;
    state.avatarEditor.pointerX = event.clientX;
    state.avatarEditor.pointerY = event.clientY;
    byId("avatar-canvas").setPointerCapture(event.pointerId);
  });
  byId("avatar-canvas").addEventListener("pointermove", moveAvatarEditor);
  byId("avatar-canvas").addEventListener("pointerup", () => { state.avatarEditor.dragging = false; });
  byId("avatar-canvas").addEventListener("pointercancel", () => { state.avatarEditor.dragging = false; });
  byId("history-range").addEventListener("change", changeHistoryRange);
  byId("copy-secret").addEventListener("click", copySecret);
  byId("source-table").addEventListener("change", saveSourceCategory);
  byId("delivery-search").addEventListener("input", renderDeliveries);
  byId("audit-search").addEventListener("input", renderAudit);
  byId("audit-page-size").addEventListener("change", () => {
    state.auditPageSize = Number(byId("audit-page-size").value);
    renderAudit();
  });
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
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("profile-menu-popover").hidden) {
      closeProfileMenu();
      byId("profile-menu-button").focus();
    }
  });
  window.addEventListener("hashchange", () => {
    const view = window.location.hash.slice(1);
    if (state.user && VIEW_TITLES[view]) navigate(view);
  });
}

bindEvents();
initialize();
