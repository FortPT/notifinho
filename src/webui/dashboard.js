"use strict";

/* Nowlert 3.1.0 dashboard analytics, built from existing platform data. */
(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const WINDOWS = {
    "10m": { seconds: 600, buckets: 10, label: "10 minutes" },
    "1h": { seconds: 3600, buckets: 12, label: "1 hour" },
    "1d": { seconds: 86400, buckets: 12, label: "1 day" },
    "1m": { seconds: 31 * 86400, buckets: 15, label: "1 month" },
    "1y": { seconds: 366 * 86400, buckets: 12, label: "1 year" },
  };

  function node(tag, className = "", text = "") {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== "") item.textContent = String(text);
    return item;
  }

  function svgNode(tag, attributes = {}) {
    const item = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) {
      item.setAttribute(name, String(value));
    }
    return item;
  }

  function attemptTime(item) {
    const value = Number(item.completed_at || item.created_at || 0);
    return value < 10_000_000_000 ? value : Math.floor(value / 1000);
  }

  function latestAttempts() {
    const latest = new Map();
    for (const item of state.deliveries || []) {
      const key = item.delivery_id || item.id;
      const current = latest.get(key);
      if (!current || Number(item.attempt_number || 0) >= Number(current.attempt_number || 0)) {
        latest.set(key, item);
      }
    }
    return [...latest.values()];
  }

  function attemptsForRange() {
    const spec = WINDOWS[state.historyRange] || WINDOWS["1h"];
    const since = Math.floor(Date.now() / 1000) - spec.seconds;
    return latestAttempts().filter((item) => attemptTime(item) >= since);
  }

  function bucketLabel(timestamp, range) {
    const date = new Date(timestamp * 1000);
    const options = range === "1y"
      ? { month: "short" }
      : range === "1m"
        ? { day: "2-digit", month: "short" }
        : range === "1d"
          ? { hour: "2-digit", minute: "2-digit" }
          : { hour: "2-digit", minute: "2-digit" };
    return new Intl.DateTimeFormat(state.preferences.language || "en-GB", {
      ...options,
      hour12: state.preferences.time_format === "12",
      timeZone: state.preferences.timezone || "Europe/Lisbon",
    }).format(date);
  }

  function renderChart() {
    const container = byId("dashboard-delivery-chart");
    const summary = byId("dashboard-chart-summary");
    if (!container || !summary) return;
    container.replaceChildren();
    summary.replaceChildren();

    const spec = WINDOWS[state.historyRange] || WINDOWS["1h"];
    const now = Math.floor(Date.now() / 1000);
    const bucketSeconds = Math.max(1, Math.ceil(spec.seconds / spec.buckets));
    const start = now - spec.seconds;
    const buckets = Array.from({ length: spec.buckets }, (_, index) => ({
      start: start + index * bucketSeconds,
      delivered: 0,
      failed: 0,
    }));
    const attempts = attemptsForRange();
    for (const item of attempts) {
      const index = Math.min(
        buckets.length - 1,
        Math.max(0, Math.floor((attemptTime(item) - start) / bucketSeconds)),
      );
      if (["delivered", "success"].includes(item.outcome)) buckets[index].delivered += 1;
      else buckets[index].failed += 1;
    }

    const width = 760;
    const height = 270;
    const padding = { top: 18, right: 18, bottom: 42, left: 44 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const maximum = Math.max(1, ...buckets.map((item) => item.delivered + item.failed));
    const svg = svgNode("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": `Delivery history for ${spec.label}`,
      preserveAspectRatio: "none",
    });
    const defs = svgNode("defs");
    const gradient = svgNode("linearGradient", {
      id: "dashboard-amber-gradient",
      x1: "0%",
      y1: "0%",
      x2: "0%",
      y2: "100%",
    });
    gradient.append(
      svgNode("stop", { offset: "0%", "stop-color": "#ffcf4c" }),
      svgNode("stop", { offset: "100%", "stop-color": "#d9a629" }),
    );
    defs.append(gradient);
    svg.append(defs);

    for (let line = 0; line <= 4; line += 1) {
      const y = padding.top + (plotHeight * line) / 4;
      svg.append(svgNode("line", {
        class: "chart-grid-line",
        x1: padding.left,
        y1: y,
        x2: width - padding.right,
        y2: y,
      }));
      const value = Math.round(maximum * (1 - line / 4));
      const label = svgNode("text", {
        class: "chart-axis-label",
        x: padding.left - 10,
        y: y + 4,
        "text-anchor": "end",
      });
      label.textContent = String(value);
      svg.append(label);
    }

    const slot = plotWidth / buckets.length;
    const barWidth = Math.max(8, Math.min(34, slot * 0.56));
    buckets.forEach((bucket, index) => {
      const x = padding.left + index * slot + (slot - barWidth) / 2;
      const deliveredHeight = (bucket.delivered / maximum) * plotHeight;
      const failedHeight = (bucket.failed / maximum) * plotHeight;
      const baseline = padding.top + plotHeight;
      if (bucket.delivered + bucket.failed === 0) {
        svg.append(svgNode("rect", {
          class: "chart-zero-bar",
          x,
          y: baseline - 3,
          width: barWidth,
          height: 3,
          rx: 2,
        }));
      } else {
        if (bucket.delivered > 0) {
          svg.append(svgNode("rect", {
            class: "chart-bar-delivered",
            x,
            y: baseline - deliveredHeight,
            width: barWidth,
            height: Math.max(2, deliveredHeight),
            rx: 4,
          }));
        }
        if (bucket.failed > 0) {
          svg.append(svgNode("rect", {
            class: "chart-bar-failed",
            x,
            y: baseline - deliveredHeight - failedHeight,
            width: barWidth,
            height: Math.max(2, failedHeight),
            rx: 4,
          }));
        }
      }
      if (index % Math.max(1, Math.ceil(buckets.length / 6)) === 0 || index === buckets.length - 1) {
        const label = svgNode("text", {
          class: "chart-bucket-label",
          x: x + barWidth / 2,
          y: height - 14,
          "text-anchor": "middle",
        });
        label.textContent = bucketLabel(bucket.start, state.historyRange);
        svg.append(label);
      }
    });
    container.append(svg);

    const delivered = attempts.filter((item) => ["delivered", "success"].includes(item.outcome)).length;
    const failed = Math.max(0, attempts.length - delivered);
    const keyDelivered = node("span", "dashboard-chart-key delivered", `${delivered} delivered`);
    const keyFailed = node("span", "dashboard-chart-key failed", `${failed} failed`);
    const note = node(
      "span",
      "",
      attempts.length
        ? `${attempts.length} final delivery outcome${attempts.length === 1 ? "" : "s"} available in recent history.`
        : `No delivery outcomes are available for ${spec.label}.`,
    );
    summary.append(keyDelivered, keyFailed, note);
  }

  function renderRanking(containerId, entries, emptyTitle, emptyCopy) {
    const container = byId(containerId);
    if (!container) return;
    container.replaceChildren();
    if (!entries.length) {
      const emptyState = node("div", "dashboard-ranking-empty");
      const icon = node("img");
      icon.src = "/ui/brand/nowlert-owl-v3.1.0.png";
      icon.alt = "";
      icon.setAttribute("aria-hidden", "true");
      emptyState.append(
        icon,
        node("strong", "", emptyTitle),
        node("span", "", emptyCopy),
      );
      container.append(emptyState);
      return;
    }
    const maximum = Math.max(...entries.map((item) => item.count), 1);
    for (const entry of entries.slice(0, 4)) {
      const row = node("div", "dashboard-ranking-row");
      const heading = node("div", "dashboard-ranking-heading");
      const name = node("strong", "", entry.name);
      name.title = entry.name;
      heading.append(name, node("span", "", entry.count));
      const track = node("div", "dashboard-ranking-track");
      const percentage = Math.max(5, Math.round((entry.count / maximum) * 100));
      const bucket = Math.max(5, Math.min(100, Math.round(percentage / 5) * 5));
      const fill = node("span", `dashboard-ranking-fill width-${bucket}`);
      track.append(fill);
      row.append(heading, track);
      container.append(row);
    }
  }

  function renderRankings() {
    const attempts = attemptsForRange();
    const sources = new Map();
    const destinations = new Map();
    const destinationNames = new Map(
      (state.destinations || []).map((item) => [item.id, item.name || friendlyName(item.output_type)]),
    );
    for (const item of attempts) {
      const source = friendlyName(item.source);
      sources.set(source, (sources.get(source) || 0) + 1);
      const destination = destinationNames.get(item.destination_id) || "Unresolved destination";
      destinations.set(destination, (destinations.get(destination) || 0) + 1);
    }
    const sorted = (map) => [...map.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
    renderRanking(
      "dashboard-top-sources",
      sorted(sources),
      "No top sources",
      "Source activity will appear after events are delivered.",
    );
    renderRanking(
      "dashboard-top-destinations",
      sorted(destinations),
      "No top destinations",
      "Destination activity will appear after events are delivered.",
    );
  }

  function renderHealth() {
    const container = byId("dashboard-system-health");
    if (!container) return;
    container.replaceChildren();
    const checks = state.healthChecks || [];
    const errors = checks.filter((item) => item.status === "error");
    const warnings = checks.filter((item) => item.status === "warning");
    const status = errors.length ? "error" : warnings.length ? "warning" : checks.length ? "healthy" : "warning";
    const title = errors.length
      ? "Attention required"
      : warnings.length
        ? "Review recommended"
        : checks.length
          ? "All systems operational"
          : "Health status unavailable";
    const detail = errors.length
      ? `${errors.length} health check${errors.length === 1 ? "" : "s"} failed.`
      : warnings.length
        ? `${warnings.length} health warning${warnings.length === 1 ? "" : "s"} detected.`
        : checks.length
          ? `${checks.length} operational checks are healthy.`
          : "Run the health checks from the Audit Log.";
    const summary = node("div", "dashboard-health-summary");
    const icon = node("span", `dashboard-health-icon ${status === "healthy" ? "" : status}`.trim(), status === "healthy" ? "✓" : status === "warning" ? "!" : "×");
    const copy = node("div");
    copy.append(node("strong", "", title), node("small", "", detail));
    summary.append(icon, copy);
    container.append(summary);

    const list = node("div", "dashboard-health-checks");
    for (const check of checks.slice(0, 5)) {
      const row = node("div", "dashboard-health-check");
      const name = node("span", "", check.name || friendlyName(check.key));
      name.title = check.detail || "";
      row.append(name, node("span", `dashboard-health-status ${check.status}`, check.status));
      list.append(row);
    }
    container.append(list);
  }

  function renderProfessionalDashboard() {
    renderChart();
    renderRankings();
    renderHealth();
  }

  const baseRenderDashboard = renderDashboard;
  renderDashboard = function renderDashboardWithAnalytics() {
    baseRenderDashboard();
    renderProfessionalDashboard();
  };

  function renderSystemNotices() {
    const noticeConsole = byId("notice-console");
    const panel = byId("notice-panel");
    const list = byId("notice-list");
    if (!noticeConsole || !panel || !list) return;

    const notices = (state.notices || []).filter(
      (item) => item.kind !== "announcement",
    );

    panel.hidden = !notices.length;
    noticeConsole.hidden = !notices.length;
    list.replaceChildren();

    for (const item of notices) {
      const status = item.status === "severe"
        ? "danger"
        : item.status === "warning"
          ? "warning"
          : "information";
      const actions = element("div", { className: "notice-actions" });

      if (item.persistent) {
        const target = item.kind === "update" ? "updates" : "audit";
        actions.append(
          actionButton(
            "Resolve",
            "open-notice-target",
            target,
            item.kind === "update" ? "primary" : "danger",
          ),
        );
      } else {
        const close = actionButton(
          "×",
          "dismiss-notice",
          item.id,
          "icon-button notice-close",
        );
        close.setAttribute("aria-label", `Close ${item.name}`);
        close.title = "Close notice";
        actions.append(close);
      }

      list.append(element("div", { className: `notice-item ${status}` }, [
        element("div", {}, [
          element("div", { className: "notice-title" }, [
            element("strong", { text: item.name }),
            badge(capitalize(item.status), status),
          ]),
          element("p", { text: item.message }),
          element("small", { text: formatTime(item.created_at) }),
        ]),
        actions,
      ]));
    }
  }

  renderNotices = renderSystemNotices;

  const adminNoticeComposer = byId("notice-composer");
  if (adminNoticeComposer) adminNoticeComposer.remove();
})();
