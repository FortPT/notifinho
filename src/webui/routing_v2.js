"use strict";

const routingV2LegacyRenderRoutes = renderRoutes;

function routingV2CanManageAssignment(assignment) {
  const route = (state.routes || []).find((item) => item.id === assignment.route_id);
  return Boolean(isAdmin() || (route && state.user && route.owner_user_id === state.user.id));
}

function routingV2AssignmentActions(assignment) {
  if (!routingV2CanManageAssignment(assignment)) return null;

  const toggleAction = assignment.enabled
    ? "disable-route-assignment"
    : "enable-route-assignment";
  return element("div", { className: "button-row routing-v2-assignment-actions" }, [
    element("button", {
      className: "button small secondary",
      text: assignment.enabled ? "Disable" : "Enable",
      type: "button",
      dataset: { routeId: assignment.route_id },
      attributes: { "data-routing-v2-action": toggleAction },
    }),
    element("button", {
      className: "button small danger",
      text: "Remove assignment",
      type: "button",
      dataset: { routeId: assignment.route_id },
      attributes: { "data-routing-v2-action": "remove-route-assignment" },
    }),
  ]);
}

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
    meta.append(element("div", { className: "routing-v2-assignment-row" }, [
      element("span", {
        className: "badge",
        text: `${destinationName(assignment.destination_id)} · ${assignment.enabled ? "Enabled" : "Disabled"}`,
      }),
      routingV2AssignmentActions(assignment),
    ]));
  }
  return meta;
}

function routingV2AvailableDestinations(capability) {
  const assigned = new Set(
    (capability.assignments || []).map((assignment) => assignment.destination_id),
  );
  return (state.destinations || []).filter((destination) => !assigned.has(destination.id));
}

function routingV2AssignmentControl(capability) {
  const available = routingV2AvailableDestinations(capability);
  const assignments = capability.assignments || [];

  if (!available.length) {
    return element("div", { className: "resource-meta" }, [
      element("small", {
        text: state.destinations.length
          ? "All available destinations are already assigned."
          : "Create a destination before assigning this route.",
      }),
    ]);
  }

  const select = element("select", {
    className: "routing-v2-destination-select",
    dataset: { routingV2Destination: capability.id },
    attributes: { "aria-label": `Destination for ${capability.label}` },
  });
  for (const destination of available) {
    select.append(element("option", {
      value: destination.id,
      text: `${destination.name}${destination.enabled ? "" : " (disabled)"}`,
    }));
  }

  const button = element("button", {
    className: "button small primary",
    text: assignments.length ? "Add destination" : "Assign destination",
    type: "button",
    dataset: { capabilityId: capability.id },
    attributes: { "data-routing-v2-action": "assign-route-capability" },
  });

  return element("div", { className: "button-row routing-v2-assignment-control" }, [
    select,
    button,
  ]);
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
      routingV2AssignmentControl(capability),
    ]));
  }
}

async function routingV2AssignDestination(target) {
  const capabilityId = target.dataset.capabilityId || "";
  const card = target.closest(".route-capability-card");
  const select = card && card.querySelector("[data-routing-v2-destination]");
  const destinationId = select ? select.value : "";
  if (!capabilityId || !destinationId) {
    toast("Choose a destination to assign.", "error");
    return;
  }

  await request("/route-assignments", {
    method: "POST",
    body: {
      capability_id: capabilityId,
      destination_id: destinationId,
      enabled: true,
    },
  });
  await loadWorkspace();
  toast("Destination assigned to route.");
}

async function routingV2SetAssignmentEnabled(routeId, enabled) {
  await request(`/routes/${routeId}`, {
    method: "PATCH",
    body: { enabled },
  });
  await loadWorkspace();
  toast(`Route assignment ${enabled ? "enabled" : "disabled"}.`);
}

async function routingV2RemoveAssignment(routeId) {
  const confirmed = await confirmAction(
    "Remove assignment",
    "Remove this destination from the route capability? Existing delivery history is kept.",
    "Remove",
  );
  if (!confirmed) return;

  await request(`/routes/${routeId}`, {
    method: "DELETE",
  });
  await loadWorkspace();
  toast("Route assignment removed.");
}

async function routingV2HandleClick(event) {
  const target = event.target.closest("[data-routing-v2-action]");
  if (!target) return;

  const action = target.getAttribute("data-routing-v2-action");
  const routeId = target.dataset.routeId || "";
  target.disabled = true;
  try {
    if (action === "assign-route-capability") {
      await routingV2AssignDestination(target);
    } else if (action === "enable-route-assignment") {
      await routingV2SetAssignmentEnabled(routeId, true);
    } else if (action === "disable-route-assignment") {
      await routingV2SetAssignmentEnabled(routeId, false);
    } else if (action === "remove-route-assignment") {
      await routingV2RemoveAssignment(routeId);
    }
  } catch (error) {
    toast(error.message || "Route assignment could not be updated.", "error");
  } finally {
    target.disabled = false;
  }
}

function routingV2DisableLegacyCreation() {
  const addRouteButton = byId("add-route-button");
  if (addRouteButton) addRouteButton.remove();
}

renderRoutes = function renderRoutesWithCapabilityCatalogue() {
  routingV2LegacyRenderRoutes();
  renderRouteCapabilityCatalogue();
};

routingV2DisableLegacyCreation();
document.addEventListener("click", routingV2HandleClick);
