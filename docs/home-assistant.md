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

Example Home Assistant configuration:

```yaml
rest_command:
  notifinho_event:
    url: "http://notifinho.local:8080/home-assistant/events"
    method: POST
    headers:
      authorization: "Bearer {{ token }}"
      content-type: "application/json"
    payload: >-
      {"schema":"notifinho.home_assistant.v1",
       "title":{{ title | tojson }},
       "message":{{ message | tojson }},
       "severity":{{ severity | default('information') | tojson }},
       "status":{{ status | default('active') | tojson }},
       "category":"automation",
       "timestamp":"{{ now().isoformat() }}",
       "entity_id":{{ entity_id | default('') | tojson }},
       "tags":["home-assistant"]}
```

Store the token in Home Assistant secrets or another protected mechanism and
pass it to the command without logging it. Titles, messages, entity IDs, tags,
links, and payload sizes are bounded. Links must be HTTP(S) and cannot contain
embedded credentials. This contract is fixture-validated; verify a harmless
automation before enabling operational alerts.

