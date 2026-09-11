"use strict";

const routingV2LegacyRenderRoutes = renderRoutes;

function routingV2AssignmentSummary(capability) {
  const assignments = capability.assignments || [];
  if (!assignments.length) {
    return element("div", { className: "resource-meta" }, [
      badge("Not configured", "warning"),
      element("small", { text: "No destinations assigned" }),
    ]);
  }

  const meta = element("div", { className: "resource-meta" }, [
    badge("Configured", "success"),
    badge(`${assignments.length} destination${assignments.length === 1 ? "" : "s"}`),
  ]);
  for (const assignment of assignments) {
    meta.append(element("span", {
      className: "badge",
      text: `${destinationName(assignment.destination_id)} · ${assignment.enabled ? "Enabled" : "Disabled"}`,
    }));
  }
  return meta;
}

function renderRouteCapabilityCatalogue() {
  const container = byId("route-capability-catalogue");
  if (!container) return;
  container.replaceChildren();

  const capabilities = (state.routeSourceOptions || []).filter(
    (capability) => !capability.admin_only || isAdmin(),
  );
  if (!capabilities.length) {
    empty(
      container,
      "No route capabilities",
      "Nowlert did not return any supported routing capabilities.",
    );
    return;
  }

  for (const capability of capabilities) {
    const assignments = capability.assignments || [];
    const integration = capability.source === "*"
      ? "Fallback"
      : friendlyName(capability.source);
    const notes = [];
    if (capability.admin_only) notes.push(badge("Administrator only", "warning"));
    if (capability.generic) notes.push(badge("Fallback", "warning"));

    container.append(element("article", {
      className: `resource-card route-capability-card ${assignments.length ? "configured" : "unconfigured"}`,
      dataset: { capabilityId: capability.id },
    }, [
      element("div", { className: "resource-heading" }, [
        element("div", { className: "resource-identity" }, [
          element("span", { className: "resource-icon" }, sourceIcon(
            capability.source === "*" ? "generic" : capability.source,
          )),
          element("div", {}, [
            element("strong", { text: capability.label || integration }),
            element("small", {
              text: `${integration} · ${inputLabel(capability.input_type)}`,
            }),
          ]),
        ]),
      ]),
      routingV2AssignmentSummary(capability),
      notes.length ? element("div", { className: "resource-meta" }, notes) : null,
    ]));
  }
}

renderRoutes = function renderRoutesWithCapabilityCatalogue() {
  routingV2LegacyRenderRoutes();
  renderRouteCapabilityCatalogue();
};
