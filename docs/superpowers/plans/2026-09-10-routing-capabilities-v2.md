# Routing Capabilities V2 Implementation Plan

> **Execution discipline:** use test-driven-development for each behavior change and verification-before-completion before the PR is marked ready.

## Goal

Make Nowlert's built-in integration/input catalogue the user-facing routing authority. Users should no longer invent a route from scratch. They see every supported route capability, select one, and assign one or more configured destinations. Filtering is intentionally removed from the normal routing workflow and will become a separate first-class feature later.

## Compatibility architecture

Do **not** replace the existing `routes` table in this slice. Existing rows and IDs are referenced by delivery history, portability, upgrades, rollback, and older APIs. Reinterpret persisted route rows as **destination assignments** to a built-in route capability:

`built-in route capability (source + input_type) -> persisted assignment -> destination`

The existing storage contract remains readable/writable for compatibility. New WebUI-created assignments use deterministic system-generated names and empty filters. Existing legacy route names and filters remain preserved in storage and continue to affect matching until the future Filters/Policies migration.

Wildcard fallback capabilities remain administrator-only and fallback-only.

## Task 1: Add a stable capability identity to the catalogue

**Files:**
- Modify: `src/integrations/catalog.py`
- Modify/add focused catalogue tests.

Every `route_options()` item gets a stable `id`, derived from source and input type, for example:

- `xo:smtp`
- `zabbix:http`
- `fallback:smtp`

The ID is presentation/API identity only; persisted source/input columns remain authoritative for compatibility.

Tests must verify:
- IDs are unique;
- every built-in integration/input combination is exposed;
- fallback IDs are explicit and remain `generic=true`;
- existing `source`, `input_type`, `label`, and compatibility semantics remain unchanged.

## Task 2: Expose assignment state without inventing new route resources

**Files:**
- Modify: `src/api/platform.py`
- Add focused API tests.

Extend the existing route catalogue response so each capability can be correlated with the user's persisted routes/assignments. Prefer an additive response contract rather than a breaking endpoint replacement.

Required user-facing information per capability:
- stable capability ID;
- source/integration;
- input type;
- display label/icon/category metadata already available through integrations;
- whether the capability is fallback/admin-only;
- zero or more assigned destinations represented by persisted route IDs;
- enabled state per assignment.

Do not expose destination secrets or credential data.

## Task 3: Provide assignment-oriented creation semantics

**Files:**
- Modify: `src/api/platform.py` and/or a small helper module if needed.
- Keep `src/storage/routes.py` behavior compatible unless a narrowly-scoped helper is necessary.
- Add API tests first.

Add a WebUI-oriented additive operation that accepts:

```json
{
  "capability_id": "zabbix:http",
  "destination_id": "...",
  "enabled": true
}
```

The server resolves the capability against the built-in catalogue and creates the existing persisted route row with:
- `source` and `input_type` from the capability, never arbitrary browser values;
- deterministic display name derived from capability + destination, collision-safe;
- default `priority=normal` / existing numeric equivalent;
- `filters={}`;
- existing ownership/sharing checks;
- existing wildcard admin restriction.

The old `/routes` CRUD contract remains available for upgrade/import/backward compatibility in this slice.

Reject:
- unknown capability IDs;
- regular-user fallback assignments;
- inaccessible/missing destinations;
- duplicate capability→destination assignment for the same owner.

## Task 4: Convert Routes WebUI into a capability catalogue

**Files:**
- Modify: `src/webui/index.html`, `src/webui/app.js`, and/or a dedicated late-loaded routing module if this avoids expanding legacy patch layers.
- Update WebUI tests first.

Replace the current `Add route` workflow with a catalogue-first screen:

- all supported route capabilities are visible even when unconfigured;
- each row/card shows integration, input, assignment/configuration state, assigned destination(s), and enabled/disabled state;
- configured and unconfigured capabilities are visually distinct;
- selecting an unconfigured capability opens an assignment flow to choose an existing destination;
- provide a direct `Create destination` path when no suitable destination exists;
- configured capability can add another destination, preserving fan-out;
- assignment can be enabled/disabled or removed;
- normal UI does not expose route name, numeric priority, or filter controls;
- fallback capabilities are segregated and administrator-only.

Do not add Filters UI in this PR.

## Task 5: Preserve legacy filtered routes safely

**Files:**
- Add regression tests around `src/storage/routes.py` and WebUI rendering.

An upgraded installation may already contain filters. Those filters must:
- continue to participate in deterministic matching;
- never be silently erased by an unrelated enable/disable action;
- be identified in the new UI as `Legacy filter attached` (read-only indicator only);
- not be editable from the new routing catalogue.

The future Filters/Policies migration will convert these intentionally.

## Task 6: Documentation and verification

Update `docs/platform-routing.md` to explain:
- system-owned route capabilities;
- user-owned destinations;
- persisted assignments;
- compatibility meaning of legacy route rows;
- fallback behavior;
- filters deferred to the future policy model.

Verification gates:

```bash
python -m pytest -q
python -m compileall -q src tests
node --check src/webui/app.js
node --check <any new routing JS module>
git diff --check
```

Then require the normal CI production Compose validation and production image build.

## Non-goals

This PR must not:
- redesign the Dashboard;
- redesign deterministic notification cards;
- migrate filters into a new table yet;
- break old `/routes` consumers;
- rewrite delivery matching semantics;
- change destination credential storage;
- remove existing route IDs referenced by delivery history.
