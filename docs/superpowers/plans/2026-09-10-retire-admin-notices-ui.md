# Retire Administrator Notices UI Implementation Plan

> **Required execution sub-skill:** Use `test-driven-development` for each behavior change and `verification-before-completion` before marking the pull request ready.

**Goal:** Remove administrator-authored announcements from the Nowlert CE WebUI while preserving genuine system error/update notices and the existing backend/database notice contract for compatibility.

**Architecture:** Keep `NoticeStore`, `/api/v2/notices`, persisted notice rows, dismissals, and system notice synchronization unchanged. Change only the product presentation layer so announcement authoring is no longer exposed and `kind=announcement` records are not rendered. System notices continue to use the existing notice panel and dismissal/persistence semantics.

**Tech Stack:** Python/pytest contract tests, static HTML, vanilla JavaScript WebUI, existing Nowlert `/api/v2` notice API.

---

## Task 1: Lock the intended WebUI contract with failing tests

**Files:**
- Modify: `tests/test_webui.py`

**Step 1: Update the semantic markup contract**

Remove `notice-composer` from the required element IDs while keeping `notice-panel` required for system notices.

Add explicit negative assertions that the shipped markup does not contain the administrator announcement authoring controls:

```python
assert 'id="notice-composer"' not in markup
assert 'id="notice-form"' not in markup
assert 'id="notice-name"' not in markup
assert 'id="notice-message"' not in markup
assert 'id="notice-status"' not in markup
assert 'id="notice-submit"' not in markup
```

**Step 2: Add a JavaScript contract for system-only notice rendering**

In `test_webui_uses_same_origin_api_without_unsafe_dom_or_secret_persistence`, keep `/notices` as a required endpoint because system notices still use it. Add assertions that:

```python
assert 'item.kind !== "announcement"' in script
assert 'byId("notice-form").addEventListener' not in script
assert 'function saveNotice(' not in script
assert 'function beginNoticeEdit(' not in script
assert 'action === "edit-notice"' not in script
assert 'action === "resolve-notice"' not in script
```

**Step 3: Run the focused test and confirm RED**

Run:

```bash
pytest -q tests/test_webui.py
```

Expected: failure because the administrator composer and announcement actions still exist.

## Task 2: Remove administrator announcement authoring markup

**Files:**
- Modify: `src/webui/index.html`

**Step 1: Remove only the composer**

Delete the `article#notice-composer` block, including the hidden notice ID, name/status/message controls, and submit button.

Keep:

```html
<section id="notice-console" class="notice-console" hidden>
  <article id="notice-panel" class="panel notice-panel" hidden>
    ...
  </article>
</section>
```

This preserves the surface used by genuine system error/update notices.

**Step 2: Do not add replacement announcement UI**

No new banner, admin composer, product-news card, or dashboard message is introduced in this PR.

## Task 3: Make WebUI notice rendering system-only

**Files:**
- Modify: `src/webui/app.js`

**Step 1: Filter announcement records before rendering**

Inside `renderNotices()`, derive a system-only list:

```javascript
const notices = state.notices.filter((item) => item.kind !== "announcement");
```

Use `notices`, rather than `state.notices`, to decide whether the console/panel is visible and to populate the list.

Do not change the server response or persisted records.

**Step 2: Remove composer-specific rendering state**

Remove references to `notice-composer` and any admin-only composer visibility logic from `renderNotices()`.

**Step 3: Remove administrator announcement mutation UI functions**

Delete the WebUI-only functions used to create/edit administrator announcements, including `saveNotice()` and `beginNoticeEdit()`.

Remove `edit-notice` and `resolve-notice` branches from `resourceAction()` if they exist only for administrator-authored announcements.

Keep `dismiss-notice` and `open-notice-target` behavior for system notices.

**Step 4: Remove form event registration**

Delete the `notice-form` submit listener from WebUI initialization.

## Task 4: Verify focused behavior and prevent collateral changes

**Files:**
- Verify: `src/webui/index.html`
- Verify: `src/webui/app.js`
- Verify: `tests/test_webui.py`

**Step 1: Run focused WebUI tests**

```bash
pytest -q tests/test_webui.py
```

Expected: PASS.

**Step 2: Run JavaScript syntax checks used by CI**

```bash
node --check src/webui/app.js
node --check src/webui/dashboard.js
```

Expected: PASS.

**Step 3: Run notice/API regression coverage**

```bash
pytest -q tests/test_platform_api.py -k notices
```

Expected: PASS, proving the backend notice compatibility contract and system update lifecycle remain intact.

**Step 4: Run the complete test suite**

```bash
pytest -q
```

Expected: PASS.

**Step 5: Confirm the diff is presentation-only**

```bash
git diff --check
git diff development...HEAD -- src/webui/index.html src/webui/app.js tests/test_webui.py docs/superpowers/plans/2026-09-10-retire-admin-notices-ui.md
```

Confirm there are no changes to `src/storage/notices.py`, migrations, notification routing, destinations, deterministic formatters, or delivery logic.

## Task 5: Open focused pull request

Create a pull request from `feat/retire-admin-notices-ui` into `development` with a summary stating:

- administrator announcement composer removed from Dashboard;
- `announcement` notice records no longer render in the WebUI;
- system error/update notices remain visible;
- `/api/v2/notices`, NoticeStore, database schema, dismissals, and synchronization remain unchanged for compatibility;
- no routing, delivery, destination, or notification presentation behavior changed.

Keep the PR isolated from the subsequent Routing Architecture V2 and Dashboard V2 work.
