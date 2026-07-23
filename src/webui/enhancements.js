"use strict";


/* Notifinho WebUI runtime polish: persistent views, header actions, source-aware tests,
 * scheduled update checks, and locale-respecting backup time entry.
 */
(() => {
  const VIEW_STORAGE_KEY = "notifinho.active-view";
  const UPDATE_CACHE_KEY = "notifinho.update-status";
  const UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1000;
  const GITHUB_RELEASE_URL = "https://api.github.com/repos/FortPT/notifinho/releases/latest";

  function storageRead(storage, key) {
    try {
      return storage.getItem(key) || "";
    } catch (_error) {
      return "";
    }
  }

  function storageWrite(storage, key, value) {
    try {
      storage.setItem(key, value);
    } catch (_error) {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }

  function normaliseVersion(value) {
    return String(value || "").trim().replace(/^v/i, "");
  }

  function versionKey(value) {
    const match = normaliseVersion(value).match(/^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/);
    return match ? match.slice(1).map(Number) : null;
  }

  function newerVersion(candidate, running) {
    const left = versionKey(candidate);
    const right = versionKey(running);
    if (!left || !right) return false;
    for (let index = 0; index < 3; index += 1) {
      if (left[index] !== right[index]) return left[index] > right[index];
    }
    return false;
  }

  function parseCanonicalTime(value, format) {
    const text = String(value || "").trim();
    if (format === "12") {
      const match = text.match(/^(0?[1-9]|1[0-2]):([0-5][0-9])\s*(AM|PM)$/i);
      if (!match) throw new Error("Use the time format HH:MM AM or HH:MM PM.");
      let hour = Number(match[1]) % 12;
      if (match[3].toUpperCase() === "PM") hour += 12;
      return `${String(hour).padStart(2, "0")}:${match[2]}`;
    }
    const match = text.match(/^([01]?[0-9]|2[0-3]):([0-5][0-9])$/);
    if (!match) throw new Error("Use the 24-hour format HH:MM, for example 14:20.");
    return `${String(Number(match[1])).padStart(2, "0")}:${match[2]}`;
  }

  function displayClockTime(value, format) {
    const match = String(value || "02:00").match(/^([01][0-9]|2[0-3]):([0-5][0-9])$/);
    if (!match) return String(value || "02:00");
    const hour = Number(match[1]);
    if (format !== "12") return `${match[1]}:${match[2]}`;
    return `${String(hour % 12 || 12).padStart(2, "0")}:${match[2]} ${hour < 12 ? "AM" : "PM"}`;
  }

  function routeForDestination(destinationId) {
    return state.routes
      .filter((route) => route.destination_id === destinationId && route.source && route.source !== "*")
      .sort((left, right) => {
        if (Boolean(left.enabled) !== Boolean(right.enabled)) return left.enabled ? -1 : 1;
        return (Number(left.priority) || 100) - (Number(right.priority) || 100);
      })[0] || null;
  }

  function sourceTestSample(source, destination) {
    const systemName = destination.name || friendlyName(source);
    const baseMetadata = {
      host: systemName,
      component: "Destination test",
      severity: "information",
      synthetic: true,
    };
    const samples = {
      supermicro: {
        title: "Supermicro test alert",
        message: "Safe WebUI test: Supermicro hardware monitoring is routed to this destination.",
        category: "hardware",
        metadata: {
          provider: "Supermicro BMC",
          system: systemName,
          sensor: "Power Supply 1",
          registry: "Notifinho.Test.1.0",
          message_id: "Notifinho.1.0.Test",
          recommended_action: "No action is required. This is a safe destination test.",
        },
      },
      hpe_ilo: {
        title: "HPE iLO test alert",
        message: "Safe WebUI test: HPE iLO hardware monitoring is routed to this destination.",
        category: "hardware",
        metadata: { provider: "HPE iLO", system: systemName, sensor: "System Health" },
      },
      dell_idrac: {
        title: "Dell iDRAC test alert",
        message: "Safe WebUI test: Dell iDRAC hardware monitoring is routed to this destination.",
        category: "hardware",
        metadata: { provider: "Dell iDRAC", system: systemName, sensor: "System Board" },
      },
      home_assistant: {
        title: "Home Assistant test alert",
        message: "Safe WebUI test: Home Assistant events are routed to this destination.",
        category: "automation",
        metadata: { device: systemName, entity_id: "sensor.notifinho_test" },
      },
      grafana: {
        title: "Grafana test alert",
        message: "Safe WebUI test: Grafana alerts are routed to this destination.",
        category: "monitoring",
        metadata: { rule: "Notifinho destination test", dashboard: "WebUI validation" },
      },
      portainer: {
        title: "Portainer test alert",
        message: "Safe WebUI test: Portainer events are routed to this destination.",
        category: "containers",
        metadata: { environment: systemName, resource: "notifinho-test" },
      },
      proxmox: {
        title: "Proxmox test alert",
        message: "Safe WebUI test: Proxmox events are routed to this destination.",
        category: "virtualization",
        metadata: { node: systemName, resource: "vm/notifinho-test" },
      },
      unifi_drive: {
        title: "UniFi Drive test alert",
        message: "Safe WebUI test: UniFi Drive events are routed to this destination.",
        category: "storage",
        metadata: { device: systemName, event_type: "destination_test" },
      },
      unifi_network: {
        title: "UniFi Network test alert",
        message: "Safe WebUI test: UniFi Network events are routed to this destination.",
        category: "networking",
        metadata: { device: systemName, event_type: "destination_test" },
      },
      unifi_protect: {
        title: "UniFi Protect test alert",
        message: "Safe WebUI test: UniFi Protect events are routed to this destination.",
        category: "security",
        metadata: { camera: systemName, event_type: "destination_test" },
      },
      zabbix: {
        title: "Zabbix test alert",
        message: "Safe WebUI test: Zabbix monitoring events are routed to this destination.",
        category: "monitoring",
        metadata: { host: systemName, trigger: "Notifinho destination test" },
      },
    };
    const sample = samples[source] || {
      title: `${friendlyName(source)} test alert`,
      message: `Safe WebUI test: ${friendlyName(source)} events are routed to this destination.`,
      category: sourceCategory(source).key,
      metadata: {},
    };
    return {
      schema: "notifinho.event.v1",
      source,
      title: sample.title,
      message: sample.message,
      severity: "information",
      status: "active",
      category: sample.category,
      provider: sample.metadata.provider || friendlyName(source),
      metadata: { ...baseMetadata, ...sample.metadata },
    };
  }

  function cachedUpdateStatus() {
    const raw = storageRead(window.localStorage, UPDATE_CACHE_KEY);
    if (!raw) return null;
    try {
      const value = JSON.parse(raw);
      return value && typeof value === "object" ? value : null;
    } catch (_error) {
      return null;
    }
  }

  function saveUpdateStatus(value) {
    storageWrite(window.localStorage, UPDATE_CACHE_KEY, JSON.stringify(value));
  }

  function updateCheckMetadata() {
    const status = state.versionStatus || {};
    const updatePanel = byId("update-status") && byId("update-status").closest(".update-panel");
    if (!updatePanel) return;
    let metadata = byId("update-check-metadata");
    if (!metadata) {
      metadata = document.createElement("p");
      metadata.id = "update-check-metadata";
      metadata.className = "update-check-metadata";
      updatePanel.append(metadata);
    }
    if (status.check_error) {
      metadata.textContent = `Last update check failed: ${status.check_error}`;
      metadata.classList.add("error");
    } else if (status.checked_at) {
      metadata.textContent = `Last checked ${formatTime(status.checked_at)} · automatic check every 6 hours`;
      metadata.classList.remove("error");
    } else {
      metadata.textContent = "Update status has not been checked against GitHub yet.";
      metadata.classList.remove("error");
    }
  }

  async function checkForUpdates({ manual = false } = {}) {
    const button = byId("platform-check-updates");
    if (button) button.disabled = true;
    try {
      const response = await fetch(GITHUB_RELEASE_URL, {
        method: "GET",
        headers: { Accept: "application/vnd.github+json" },
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
      if (!response.ok) throw new Error(`GitHub returned HTTP ${response.status}`);
      const payload = await response.json();
      const available = normaliseVersion(payload.tag_name || payload.name);
      if (!versionKey(available)) throw new Error("GitHub returned an invalid release version");
      const running = normaliseVersion((state.versionStatus || {}).running);
      state.versionStatus = {
        ...(state.versionStatus || {}),
        running,
        available,
        update_available: newerVersion(available, running),
        checked_at: Date.now(),
        check_source: "github",
        check_error: "",
        release_url: payload.html_url || "",
      };
      saveUpdateStatus(state.versionStatus);
      renderUpdates();
      if (manual) {
        toast(
          state.versionStatus.update_available
            ? `Notifinho ${available} is available.`
            : `Notifinho ${running || ""} is up to date.`,
          state.versionStatus.update_available ? "warning" : "success",
        );
      }
      return state.versionStatus;
    } catch (error) {
      state.versionStatus = {
        ...(state.versionStatus || {}),
        checked_at: Date.now(),
        check_error: error.message || "Update check failed",
      };
      renderUpdates();
      if (manual) toast(state.versionStatus.check_error, "error");
      return state.versionStatus;
    } finally {
      if (button) button.disabled = false;
    }
  }

  function installHeaderMenu() {
    const actions = document.querySelector(".topbar-actions");
    if (!actions || byId("platform-menu")) return;
    const wrapper = document.createElement("div");
    wrapper.id = "platform-menu";
    wrapper.className = "platform-menu";
    wrapper.hidden = true;
    const menuButton = element("button", {
      className: "icon-button platform-menu-button",
      text: "⋮",
      type: "button",
      attributes: {
        "aria-label": "Open system menu",
        "aria-haspopup": "menu",
        "aria-expanded": "false",
      },
    });
    menuButton.id = "platform-menu-button";
    const menu = element("div", {
      className: "platform-menu-popover",
      hidden: true,
      attributes: { role: "menu" },
    });
    menu.id = "platform-menu-popover";
    const updateButton = element("button", {
      type: "button",
      attributes: { role: "menuitem" },
    }, [
      element("span", { text: "↻", attributes: { "aria-hidden": "true" } }),
      element("span", { text: "Check for updates" }),
    ]);
    updateButton.id = "platform-check-updates";
    const restartButton = element("button", {
      type: "button",
      attributes: { role: "menuitem" },
    }, [
      element("span", { text: "⏻", attributes: { "aria-hidden": "true" } }),
      element("span", { text: "Restart Notifinho" }),
    ]);
    restartButton.id = "platform-restart";
    menu.append(updateButton, restartButton);
    wrapper.append(menuButton, menu);
    actions.append(wrapper);

    const closeMenu = () => {
      menu.hidden = true;
      menuButton.setAttribute("aria-expanded", "false");
    };
    menuButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = menu.hidden;
      menu.hidden = !open;
      menuButton.setAttribute("aria-expanded", String(open));
      if (open) menu.querySelector("button").focus();
    });
    byId("platform-check-updates").addEventListener("click", async (event) => {
      event.stopPropagation();
      closeMenu();
      await checkForUpdates({ manual: true });
    });
    byId("platform-restart").addEventListener("click", async (event) => {
      event.stopPropagation();
      closeMenu();
      await resourceAction("restart-platform", "");
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest("#platform-menu")) closeMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !menu.hidden) {
        closeMenu();
        menuButton.focus();
      }
    });
  }

  function syncHeaderMenu() {
    installHeaderMenu();
    const menu = byId("platform-menu");
    if (menu) menu.hidden = !state.user;
    const restart = byId("platform-restart");
    if (restart) restart.hidden = !isAdmin();
  }

  function restorePersistedView() {
    const requested = window.location.hash.slice(1);
    const stored = storageRead(window.sessionStorage, VIEW_STORAGE_KEY);
    if ((!requested || !VIEW_TITLES[requested]) && VIEW_TITLES[stored]) {
      window.history.replaceState(null, "", `#${stored}`);
    }
  }

  restorePersistedView();
  installHeaderMenu();

  const originalNavigate = navigate;
  navigate = function enhancedNavigate(view) {
    const result = originalNavigate(view);
    storageWrite(window.sessionStorage, VIEW_STORAGE_KEY, state.currentView);
    return result;
  };

  const originalShowApp = showApp;
  showApp = function enhancedShowApp(session) {
    const result = originalShowApp(session);
    syncHeaderMenu();
    return result;
  };

  const originalLoadWorkspace = loadWorkspace;
  loadWorkspace = async function enhancedLoadWorkspace() {
    const result = await originalLoadWorkspace();
    syncHeaderMenu();
    const cached = cachedUpdateStatus();
    const running = normaliseVersion((state.versionStatus || {}).running);
    if (cached && normaliseVersion(cached.running) === running) {
      state.versionStatus = { ...(state.versionStatus || {}), ...cached, running };
      renderUpdates();
    }
    const checkedAt = Number((state.versionStatus || {}).checked_at || 0);
    if (!checkedAt || Date.now() - checkedAt >= UPDATE_INTERVAL_MS) {
      window.setTimeout(() => checkForUpdates(), 250);
    }
    return result;
  };

  const originalRenderUpdates = renderUpdates;
  renderUpdates = function enhancedRenderUpdates() {
    originalRenderUpdates();
    updateCheckMetadata();
  };

  const originalRenderBackupSettings = renderBackupSettings;
  renderBackupSettings = function enhancedRenderBackupSettings() {
    originalRenderBackupSettings();
    if (!isAdmin() || !state.backupSettings) return;
    const input = byId("backup-time");
    input.type = "text";
    input.autocomplete = "off";
    const format = state.preferences.time_format === "12" ? "12" : "24";
    input.inputMode = format === "12" ? "text" : "numeric";
    input.value = displayClockTime(state.backupSettings.time, format);
    input.placeholder = format === "12" ? "02:20 PM" : "14:20";
    input.setAttribute("aria-describedby", "backup-time-format-help");
    let help = byId("backup-time-format-help");
    if (!help) {
      help = document.createElement("small");
      help.id = "backup-time-format-help";
      input.closest("label").append(help);
    }
    help.textContent = format === "12" ? "Use HH:MM AM/PM." : "Use 24-hour HH:MM.";
  };

  sourceIsActive = function exactRouteSourceIsActive(source) {
    return state.routes.some((route) => route.enabled && route.source === source);
  };

  cardSampleEvent = function sourceAwareCardSampleEvent(destination) {
    const route = routeForDestination(destination.id);
    return sourceTestSample(route ? route.source : "notifinho", destination);
  };

  const backupTime = byId("backup-time");
  if (backupTime) backupTime.type = "text";
  const backupForm = byId("backup-settings-form");
  if (backupForm) {
    backupForm.addEventListener("submit", (event) => {
      const format = state.preferences.time_format === "12" ? "12" : "24";
      const input = byId("backup-time");
      const displayValue = input.value;
      try {
        input.value = parseCanonicalTime(displayValue, format);
        window.setTimeout(() => {
          if (document.body.contains(input)) input.value = displayClockTime(input.value, format);
        }, 0);
      } catch (error) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toast(error.message || "Backup time is invalid.", "error");
        input.focus();
      }
    }, true);
  }

  window.setInterval(() => {
    if (state.user && document.visibilityState !== "hidden") checkForUpdates();
  }, UPDATE_INTERVAL_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible" || !state.user) return;
    const checkedAt = Number((state.versionStatus || {}).checked_at || 0);
    if (!checkedAt || Date.now() - checkedAt >= UPDATE_INTERVAL_MS) checkForUpdates();
  });
})();
