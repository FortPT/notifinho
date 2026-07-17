# Home Assistant

Home Assistant automations can submit authenticated events to
`POST /home-assistant/events`. The request must follow the
`notifinho.home_assistant.v1` schema and use either the global HTTP secret or a
v1.9 source-scoped token.

```yaml
api:
  enabled: true
  tokens:
    home_assistant:
      enabled: true
      role: application
      sources: [home_assistant]
      token_env: NOTIFINHO_HOME_ASSISTANT_TOKEN
      rate_limit_per_minute: 120

routing:
  home_assistant:
    outputs:
      - output: discord
        target: home_assistant
```

Store the scoped token in `secrets.yaml`:

```yaml
notifinho_home_assistant_token: "PASTE_SOURCE_SCOPED_TOKEN_HERE"
```

Define one reusable transport in Home Assistant. It forwards event data; card
presentation remains Notifinho's responsibility:

```yaml
rest_command:
  notifinho_event:
    url: "https://notifinho.local.example/home-assistant/events"
    method: POST
    headers:
      X-Notifinho-Token: !secret notifinho_home_assistant_token
      Content-Type: application/json
    payload: >-
      {
        "schema": "notifinho.home_assistant.v1",
        "event_type": {{ event_type | default("automation", true) | string | to_json }},
        "component": {{ component | default("", true) | string | to_json }},
        "title": {{ title | default("Home Assistant event", true) | string | to_json }},
        "message": {{ message | default("No details were provided.", true) | to_json }},
        "severity": {{ severity | default("information", true) | string | to_json }},
        "status": {{ status | default("active", true) | string | to_json }},
        "category": {{ category | default("automation", true) | string | to_json }},
        "entity_id": {{ entity_id | default("", true) | string | to_json }},
        "device": {{ device | default("", true) | string | to_json }},
        "area": {{ area | default("", true) | string | to_json }},
        "tags": {{ tags | default([], true) | to_json }},
        "link": {{ link | default("", true) | string | to_json }},
        "timestamp": {{ utcnow().isoformat().replace("+00:00", "Z") | to_json }}
      }
```

The following generic automation forwards Home Assistant errors without
embedding presentation rules for individual integrations:

```yaml
alias: "Notifinho - General errors"
description: Forwards selected Home Assistant errors to Notifinho

triggers:
  - trigger: event
    event_type: system_log_event
    event_data:
      level: ERROR

conditions:
  - condition: template
    value_template: >-
      {% set details = (
        (trigger.event.data.name | default('', true) | string)
        ~ ' '
        ~ (trigger.event.data.source | default('', true) | string)
        ~ ' '
        ~ (trigger.event.data.message | default('', true) | string)
      ) | lower %}
      {{ 'notifinho' not in details and 'rest_command' not in details }}

actions:
  - variables:
      event_message: >-
        {% set messages = trigger.event.data.message | default([], true) %}
        {% if messages is string %}
          {{ messages }}
        {% elif messages | count > 0 %}
          {{ messages[0] }}
        {% else %}
          No error details were provided.
        {% endif %}

  - action: rest_command.notifinho_event
    data:
      event_type: system_log
      component: "{{ trigger.event.data.name | default('homeassistant', true) }}"
      title: Home Assistant error
      message: "{{ event_message }}"
      severity: error
      status: active
      category: system_error
      entity_id: ""
      device: ""
      area: ""
      tags:
        - home-assistant
        - error

mode: queued
max: 20
```

The parser derives a concise event summary, service, device or entity,
endpoint, and retry interval when those details are present. Discord and Teams
formatters present them as separate fields. Internal Python paths and verbose
object representations are not placed on the card. Explicit device, entity,
area, and title values still take priority for purpose-built automations.

Keep deployment-specific exclusions in the Home Assistant condition rather
than in Notifinho's generic parser. For example, a site may suppress a known
lab-only integration by adding another `and '<integration>' not in details`
clause. Those exclusions should not be copied into the shared example.

Tokens must remain in Home Assistant secrets or another protected mechanism.
Titles, messages, entity IDs, tags, links, and payload sizes are bounded. Links
must be HTTP(S) and cannot contain embedded credentials. Verify a harmless
automation before enabling operational alerts.
