"""Packaged WebUI, transport, and browser-security contract tests."""

from __future__ import annotations

import http.client
import threading

from html.parser import HTMLParser
from pathlib import Path

import inputs.http as http_module

from dispatcher import Dispatcher
from inputs.http import HTTPServer
from storage.database import Database
from webui.service import SECURITY_HEADERS, WebUIService


ROOT = Path(__file__).resolve().parents[1]


class Configuration:
    def __init__(self, data):
        self.data = data

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class Router:
    def route(self, _item):
        raise AssertionError("WebUI assets must not enter notification routing")


class MarkupInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.stylesheets = []
        self.inline_handlers = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "script":
            self.scripts.append(values.get("src"))
        if tag == "link" and values.get("rel") == "stylesheet":
            self.stylesheets.append(values.get("href"))
        self.inline_handlers.extend(
            name for name, _value in attrs if name.casefold().startswith("on")
        )


def enabled_config():
    return Configuration({
        "http": {"enabled": True},
        "api": {"enabled": True},
        "platform": {"enabled": True},
        "webui": {"enabled": True},
    })


def http_request(port, method, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    connection.request(method, path)
    response = connection.getresponse()
    status = response.status
    headers = response.getheaders()
    body = response.read()
    connection.close()
    return status, headers, body


def test_webui_service_is_explicitly_gated_and_has_no_path_mapping():
    service = WebUIService(enabled_config(), root=ROOT)

    assert service.enabled is True
    assert service.response("/").status == 200
    assert service.response("/ui/app.js").content_type.startswith("text/javascript")
    assert service.response("/ui/i18n.js").content_type.startswith("text/javascript")
    assert service.response("/ui/styles.css").content_type.startswith("text/css")
    assert service.response("/ui/icon.png").content_type == "image/png"
    assert service.response("/ui/../config/config.yaml").status == 404
    assert service.response("/api/v2/session") is None
    assert service.response("/home-assistant/events") is None

    unavailable = WebUIService(
        enabled_config(),
        root=ROOT,
        platform_available=False,
    )
    assert unavailable.enabled is False
    assert unavailable.response("/").status == 404

    for section in ("http", "api", "platform", "webui"):
        configuration = enabled_config()
        configuration.data[section]["enabled"] = False
        disabled = WebUIService(configuration, root=ROOT)
        assert disabled.enabled is False
        assert disabled.response("/").status == 404
        assert disabled.response("/ui/app.js").status == 404


def test_webui_is_default_on_but_every_explicit_disable_is_authoritative():
    service = WebUIService(Configuration({}), root=ROOT, platform_available=True)

    assert service.enabled is True
    assert service.response("/").status == 200

    for section in ("http", "api", "platform", "webui"):
        disabled = WebUIService(
            Configuration({section: {"enabled": False}}),
            root=ROOT,
            platform_available=True,
        )
        assert disabled.enabled is False


def test_native_http_serves_get_and_head_with_strict_browser_headers(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(http_module, "config", enabled_config())
    database = Database(tmp_path / "state" / "nowlert.db")
    database.migrate()
    server = HTTPServer(
        ("127.0.0.1", 0),
        Dispatcher(),
        Router(),
        1_048_576,
        "",
        platform_database=database,
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        page = http_request(server.server_port, "GET", "/")
        script = http_request(server.server_port, "GET", "/ui/app.js")
        head = http_request(server.server_port, "HEAD", "/ui/styles.css")
        missing = http_request(server.server_port, "GET", "/ui/missing.js")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    page_headers = dict(page[1])
    assert page[0] == 200
    assert page_headers["Content-Type"] == "text/html; charset=utf-8"
    assert page_headers["Cache-Control"] == "no-store"
    assert page_headers["X-Frame-Options"] == "DENY"
    assert page_headers["X-Content-Type-Options"] == "nosniff"
    assert page_headers["Referrer-Policy"] == "no-referrer"
    assert page_headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in page_headers["Content-Security-Policy"]
    assert script[0] == 200 and script[2]
    assert head[0] == 200 and head[2] == b""
    assert int(dict(head[1])["Content-Length"]) > 0
    assert missing[0] == 404 and missing[2] == b""
    assert set(SECURITY_HEADERS).issubset(set(page[1]))


def test_webui_markup_is_semantic_external_and_complete():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    inspector = MarkupInspector()
    inspector.feed(markup)

    required = {
        "bootstrap-form",
        "bootstrap-token",
        "login-form",
        "app-shell",
        "primary-nav",
        "main-content",
        "view-dashboard",
        "view-sources",
        "view-destinations",
        "view-routes",
        "view-tokens",
        "view-deliveries",
        "view-audit",
        "view-users",
        "view-settings",
        "view-updates",
        "view-data",
        "view-account",
        "configuration-inputs",
        "source-table",
        "notice-composer",
        "notice-panel",
        "history-range",
        "dashboard-flow",
        "dashboard-delivery-chart",
        "dashboard-top-sources",
        "dashboard-top-destinations",
        "dashboard-system-health",
        "health-check-list",
        "backup-settings-form",
        "avatar-form",
        "preferences-form",
        "destination-dialog",
        "route-dialog",
        "token-dialog",
        "preview-dialog",
        "secret-dialog",
        "import-dialog",
    }
    assert required <= inspector.ids
    assert inspector.scripts == [
        "/ui/app.js",
        "/ui/enhancements.js",
        "/ui/qa_patch.js",
        "/ui/routing_v2.js",
        "/ui/i18n.js",
        "/ui/dashboard.js",
    ]
    assert inspector.stylesheets == [
        "/ui/styles.css",
        "/ui/enhancements.css",
        "/ui/qa_patch.css",
        "/ui/professional.css",
    ]
    assert inspector.inline_handlers == []
    assert "<style" not in markup
    assert "javascript:" not in markup.casefold()


def test_webui_uses_same_origin_api_without_unsafe_dom_or_secret_persistence():
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")

    for endpoint in (
        "/bootstrap",
        "/session",
        "/destinations",
        "/routes",
        "/tokens",
        "/deliveries",
        "/audit-events",
        "/users",
        "/preferences",
        "/integrations",
        "/version",
        "/portability/export",
        "/portability/preview",
        "/portability/import",
        "/migrations/v1/preview",
        "/migrations/v1/import",
        "/configuration/inventory",
        "/configuration/migration/preview",
        "/configuration/migration/apply",
        "/configuration/routing-authority",
        "/backups",
        "/backup-settings",
        "/notices",
        "/health-checks",
        "/account/avatar",
        "/metrics/",
        "/account/password",
    ):
        assert endpoint in script
    assert 'const API = "/api/v2"' in script
    assert 'credentials: "same-origin"' in script
    assert 'cache: "no-store"' in script
    assert '["delivered", "success"].includes(item.outcome)' in script
    assert "function destinationTestToast(delivery, outputType)" in script
    assert "Microsoft Teams accepted the test (HTTP 202)." in script
    assert "Delivery is not confirmed; check the channel." in script
    assert 'actionButton("Reset password", "reset-user", item.id)' in script
    assert 'dataset: { action: "toggle-token", id: item.id }' in script
    assert 'dataset: { action: "toggle-input", id: item.name }' in script
    assert 'outputIcon(item.output_type)' in script
    assert 'capitalize(item.priority_name || "normal")' in script
    assert "Promise.allSettled" in script
    assert "state.workspaceErrors.push" in script
    assert 'component: "Workspace"' in script
    assert "const values = await Promise.all" not in script
    assert 'if (!self)' in script
    assert 'headers["X-CSRF-Token"]' in script
    assert "navigator.clipboard.writeText" in script
    assert "textContent" in script
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "localStorage",
        "sessionStorage",
        "eval(",
        "new Function",
    ):
        assert forbidden not in script


def test_webui_keeps_workspace_visible_and_identifies_partial_api_failures():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")

    assert 'id="workspace-alert"' in markup
    assert 'id="workspace-alert-list"' in markup
    assert 'role="alert"' in markup
    for component in (
        "Destinations",
        "Routes",
        "Event API tokens",
        "Delivery history",
        "Configuration inventory",
        "Backup settings",
    ):
        assert f'["{component}", request(' in script
    session_request = script.index('session = await request("/session")')
    session_show = script.index("showApp(session);", session_request)
    workspace_load = script.index("await loadWorkspace();", session_show)
    assert session_request < session_show < workspace_load


def test_production_image_already_packages_webui_and_icon():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY src /nowlert/src" in dockerfile
    assert "COPY assets /nowlert/assets" in dockerfile
    assert (ROOT / "src" / "webui" / "index.html").is_file()
    assert (ROOT / "src" / "webui" / "app.js").is_file()
    assert (ROOT / "src" / "webui" / "styles.css").is_file()
    assert (ROOT / "assets" / "icons" / "nowlert.png").is_file()


def test_v310_management_headers_and_dashboard_analytics_alignment():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "webui" / "professional.css").read_text(encoding="utf-8")

    assert (
        "Configure delivery targets for Discord, Microsoft Teams, Slack, "
        "generic webhooks, MQTT, and ntfy."
    ) in markup
    assert (
        "Review final delivery outcomes, retries, response status, and safe "
        "transport errors for routed events."
    ) in markup
    marker = "/* Nowlert 3.1.0 final management headers and analytics alignment */"
    assert marker in styles
    final_styles = styles[styles.index(marker):]
    assert "#view-dashboard .dashboard-analytics-grid" in final_styles
    assert "> .dashboard-deliveries-panel" in final_styles
    assert "margin-top: 0;" in final_styles


def test_v310_management_descriptions_content_headers_and_ranking_empty_states():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    dashboard = (ROOT / "src" / "webui" / "dashboard.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "webui" / "professional.css").read_text(encoding="utf-8")

    descriptions = (
        "Review built-in integrations, available inputs, and their operational categories.",
        "Connect integrations and inputs to destinations with priorities and event filters.",
        "Review security-relevant actions, health checks, outcomes, and operational details.",
        "Manage local accounts, roles, access state, and password resets.",
        "Configure regional preferences and integration-specific behavior.",
        "Review the running version and any advertised Nowlert update.",
        "Inspect and manage the SMTP, HTTP, and Redfish listeners used to receive events.",
        "Configure backup destinations, schedules, snapshots, and restore operations.",
        "Export, preview, and import portable configuration without exposing credentials.",
        "Manage your profile picture, password, and active account security settings.",
    )
    for copy in descriptions:
        assert copy in markup

    assert 'data-panel-header="destinations"' not in markup
    assert 'class="table-panel professional-resource-panel"' not in markup
    assert '<div id="destination-list" class="resource-grid"></div>' in markup
    assert 'data-panel-header="deliveries"' in markup
    assert ">Delivery attempts<" in markup
    assert ">Source, outcome, response, and time<" in markup

    assert '"No top sources"' in dashboard
    assert '"No top destinations"' in dashboard
    assert 'icon.src = "/ui/brand/nowlert-owl-v3.1.0.png";' in dashboard

    marker = "/* Nowlert 3.1.0 management descriptions and content headers */"
    assert marker in styles
    final_styles = styles[styles.index(marker):]
    assert ".dashboard-ranking-empty img" in final_styles
    assert ".professional-panel-header" in final_styles


def test_v310_menu_navigation_uses_browser_history_and_destinations_stay_a_card_grid():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")
    enhancements = (ROOT / "src" / "webui" / "enhancements.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "webui" / "professional.css").read_text(encoding="utf-8")

    assert 'function navigate(view, historyMode = "push")' in app
    assert 'window.history.pushState({ nowlertView: view }' in app
    assert 'window.addEventListener("popstate", navigateFromHistory)' in app
    assert 'navigate(view, "none")' in app
    assert 'originalNavigate(view, historyMode)' in enhancements
    assert 'originalNavigate(view, "replace")' in enhancements

    assert 'data-panel-header="destinations"' not in markup
    assert 'professional-resource-panel' not in markup
    assert '<div id="destination-list" class="resource-grid"></div>' in markup
    assert 'data-panel-header="deliveries"' in markup

    marker = "/* Nowlert 3.1.0 Destinations card-grid empty state */"
    assert marker in styles
    final_styles = styles[styles.index(marker):]
    assert "background: transparent;" in final_styles
    assert "border: 0;" in final_styles


def test_nce15_regional_i18n_save_boundary():
    script = (ROOT / "src" / "webui" / "i18n.js").read_text(encoding="utf-8")
    app = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")

    for locale in (
        "pt", "es", "fr", "de", "it", "nl", "pl", "cs", "ro",
        "sv", "da", "nb", "fi", "el", "tr", "ru", "uk", "ja", "zh",
    ):
        assert f'"{locale}": [' in script

    assert '"en-GB": "English"' in script
    assert '"en-US": "English"' in script
    assert '"pt-PT": "Português"' in script
    assert '"pt-BR": "Português"' in script
    assert "canonicalAliases" not in script
    assert "select.value = canonicalAliases" not in script

    for forbidden_label in (
        "English — UK",
        "English — US",
        "Português — Portugal",
        "Português — Brasil",
        "English (United Kingdom)",
        "English (United States)",
        "Português (Portugal)",
        "Português (Brasil)",
    ):
        assert forbidden_label not in markup

    assert '<option value="en-GB">English</option>' in markup
    assert '<option value="en-US" hidden>English</option>' in markup
    assert '<option value="pt-PT">Português</option>' in markup
    assert '<option value="pt-BR" hidden>Português</option>' in markup

    assert (
        'const leavingSettings = state.currentView === "settings" && view !== "settings";'
        in script
    )
    assert "if (leavingSettings) renderPreferences();" in script
    assert 'if (view === "settings") renderPreferences();' in script

    save = app.index("async function savePreferences")
    request = app.index('const response = await request("/preferences"', save)
    persisted = app.index("state.preferences = response.preferences;", save)
    assert request < persisted


def test_nce22_nce24_delivery_and_audit_direct_pagination_controls():
    script = (ROOT / "src" / "webui" / "qa_patch.js").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "webui" / "qa_patch.css").read_text(encoding="utf-8")
    platform = (ROOT / "src" / "api" / "platform.py").read_text(encoding="utf-8")

    # Only Delivery History and Audit Log get the extended pager.
    assert 'containerId === "delivery-pagination"' in script
    assert 'containerId === "audit-pagination"' in script
    assert "if (!directNavigation)" in script

    # First / Last navigation.
    assert 'text: "First"' in script
    assert 'text: "Last"' in script
    assert "disabled: page <= 1" in script
    assert "disabled: page >= totalPages" in script

    # Direct page-number navigation and validity constraints.
    assert 'className: "qa-page-number"' in script
    assert 'type: "number"' in script
    assert 'min: "1"' in script
    assert "max: String(totalPages)" in script
    assert "Number.isInteger(value)" in script
    assert "value < 1 || value > totalPages" in script
    assert "pageInput.setAttribute(" in script
    assert '"aria-invalid",' in script
    assert 'requestedPage() === null ? "true" : "false"' in script
    assert 'if (event.key === "Enter")' in script

    # Every paging action finishes at the actual document bottom, after
    # asynchronous layout settles.
    assert "const navigatePage = (targetPage) => {" in script
    assert "function qaScrollPageBottom()" in script
    assert "document.documentElement.scrollHeight" in script
    assert "document.body ? document.body.scrollHeight : 0" in script
    assert "window.requestAnimationFrame" in script
    assert "window.requestAnimationFrame(scroll);" in script
    assert "Promise.resolve(result).then(" in script
    assert 'previous.addEventListener("click", () => navigatePage(page - 1));' in script
    assert 'next.addEventListener("click", () => navigatePage(page + 1));' in script
    assert 'first.addEventListener("click", () => navigatePage(1));' in script
    assert 'last.addEventListener("click", () => navigatePage(totalPages));' in script
    assert "if (requested !== page) navigatePage(requested);" in script

    # Top, pager, and Entries share the bottom row. Bottom still uses
    # true document-bottom scrolling.
    assert "function qaCreateTopShortcut()" in script
    assert 'className: "button secondary small qa-top-shortcut"' in script
    assert 'text: "Top"' in script
    assert 'text: "Bottom"' in script
    assert "function qaArrangePaginationFooter(" in script
    assert 'className: "qa-pagination-left"' in script
    assert "footer.append(label);" in script
    assert 'footer.classList.add("qa-pagination-footer");' in script
    assert "qaScrollPageBottom();" in script
    assert 'data-qa-bottom' in script
    assert ".qa-pagination-footer" in styles
    assert "overflow-anchor: none" in styles

    # Entering Delivery History or Audit Log from another view always starts
    # at the top without changing pagination/page-size state.
    assert "function qaScrollPageTop()" in script
    assert "const qaOriginalNavigate = navigate;" in script
    assert 'navigate = function navigateWithPagedViewTop(view, historyMode = "push") {' in script
    assert "const previousView = state.currentView;" in script
    assert "const currentView = state.currentView;" in script
    assert "previousView !== currentView" in script
    assert 'currentView === "deliveries" || currentView === "audit"' in script
    assert "qaScrollPageTop();" in script

    # NCE-23 Audit entries-per-page persistence remains intact.
    assert 'const QA_AUDIT_PAGE_SIZE_KEY = "nowlert.audit.pageSize";' in script
    assert "qaReadAuditPageSize()" in script
    assert "qaWriteAuditPageSize(qaAuditPageSize);" in script
    assert "/size/${qaAuditPageSize}" in script

    # Delivery History gets the same persisted page-size choices.
    assert 'const QA_DELIVERY_PAGE_SIZE_KEY = "nowlert.delivery.pageSize";' in script
    assert "QA_DELIVERY_PAGE_SIZES = [25, 50, 100, 150, 250, 500]" in script
    assert "qaReadDeliveryPageSize()" in script
    assert "qaWriteDeliveryPageSize(qaDeliveryPageSize);" in script
    assert "/size/${qaDeliveryPageSize}" in script
    assert 'id: "delivery-page-size"' in script

    # Backend accepts the Delivery History selected page size.
    assert "_DELIVERY_PAGE_SIZES = (25, 50, 100, 150, 250, 500)" in platform
    assert "delivery_page_size = re.fullmatch(" in platform
    assert "/api/v2/deliveries/page/" in platform
    assert "int(delivery_page_size.group(2))" in platform
    assert "def _deliveries_page_endpoint(self, method, actor, page, size=None)" in platform

    # Layout remains usable on narrow displays.
    assert ".qa-pagination .qa-page-number" in styles
    assert "@media (max-width: 720px)" in styles



def test_nce28_nce29_audit_context_and_explicit_health_checks():
    markup = (ROOT / "src" / "webui" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "webui" / "app.js").read_text(encoding="utf-8")

    # NCE-28: Audit Log exposes actor, precise action, affected resource,
    # resource identifier, outcome, and safe details.
    assert (
        "<th>Time</th><th>Action</th><th>User</th><th>Resource</th>"
        "<th>Outcome</th><th>Details</th>"
    ) in markup
    assert "function auditActionLabel(value)" in script
    assert "function auditActorLabel(item)" in script
    assert "function auditDetailsText(details)" in script
    assert "item.actor_username" in script
    assert "item.actor_user_id" in script
    assert "item.resource_id" in script
    assert 'text: item.action || "unknown"' in script
    assert 'text: auditDetailsText(item.details)' in script

    # Search includes the newly-visible actor and affected entity context.
    assert "item.actor_username," in script
    assert "item.actor_user_id," in script
    assert "item.resource_id," in script

    # NCE-29: generic workspace loading must not execute a health check.
    assert (
        'health: ["Health checks", request("/health-checks")'
        not in script
    )

    # Health checks remain available only as an explicit user action.
    assert 'action === "run-health-checks"' in script
    assert 'const response = await request("/health-checks");' in script



def test_nce30_nce31_admin_delete_controls():
    script = (ROOT / "src" / "webui" / "app.js").read_text(
        encoding="utf-8"
    )

    assert '"delete-user"' in script
    assert '"delete-backup"' in script

    assert (
        'actionButton("Delete", "delete-user", item.id, "danger")'
        in script
    )
    assert (
        'actionButton("Delete", "delete-backup", item.id, "danger")'
        in script
    )

    assert 'action === "delete-user"' in script
    assert 'action === "delete-backup"' in script

    assert 'await request(`/users/${id}`, { method: "DELETE" });' in script
    assert 'await request(`/backups/${id}`, { method: "DELETE" });' in script

    assert "the user still owns destinations, secrets, or backup destinations" in script
    assert "It cannot be restored after deletion." in script
    assert '"Delete backup"' in script



def test_nce31_nce33_nce34_nce35_development_followups():
    app = (ROOT / "src" / "webui" / "app.js").read_text(
        encoding="utf-8"
    )
    patch = (ROOT / "src" / "webui" / "qa_patch.js").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "src" / "webui" / "qa_patch.css").read_text(
        encoding="utf-8"
    )

    # NCE-31: destructive backup action has an explicit confirmation.
    assert "`Delete state backup ${id}?`" in app
    assert '"Delete backup"' in app
    assert "It cannot be restored after deletion." in app

    # NCE-33: role display uses the same authority as access control and
    # cannot be reset to the static HTML User value by the i18n layer.
    assert "const admin = isAdmin();" in app
    assert (
        'profileRole.textContent = admin ? "Admin" : "User";'
        in app
    )
    assert "delete profileRole.dataset.i18nSource;" in app
    assert (
        'accountRole.textContent = admin ? "Administrator" : "User";'
        in app
    )

    # NCE-34: restore the Stage-approved duplicate/empty badge cleanup.
    assert "function qaNormalizeDeliveryBadges()" in patch
    assert 'text === "—" || seen.has(key)' in patch
    assert "qaNormalizeDeliveryBadges();" in patch

    # NCE-35: direct page box is embedded in Page [n] of N, Go is gone,
    # and Enter remains the explicit direct navigation action.
    assert 'className: "qa-page-status"' in patch
    assert '"Page ",' in patch
    assert "pageInput," in patch
    assert 'text: "Go"' not in patch
    assert 'go.addEventListener(' not in patch
    assert 'pageInput.addEventListener("change"' not in patch
    assert 'if (event.key === "Enter")' in patch

    # Top / pager / Entries are one three-column bottom row.
    assert "function qaArrangePaginationFooter(" in patch
    assert 'className: "qa-pagination-left"' in patch
    assert "footer.append(label);" in patch
    assert (
        "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);"
        in styles
    )
    assert ".qa-pagination-row > .qa-pagination-footer" in styles
