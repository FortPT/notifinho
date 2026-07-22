# Container deployment

Notifinho keeps development and production Compose definitions separate:

- `docker-compose.yml` builds the checked-out source and publishes development
  ports `8026` and `18082`;
- `compose.production.yaml` runs a versioned published image on production
  ports `8025` and `18080` by default.

Do not run both definitions with the same container name or host ports.

## Development checkout

Create the private configuration once and keep it outside Git:

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

Build and start the development service:

```bash
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml ps
docker logs --tail 100 notifinho-dev
```

Expected listeners are host TCP `8026` for SMTP and host TCP `18082` for the
optional HTTP input. The HTTP listener starts only when `http.enabled` is true
in the private configuration.

## Production host preparation

Copy the environment template, create writable bind-mount directories, and
record the deployment user's numeric identity:

```bash
cp .env.example .env
mkdir -p logs/emails secrets state
id -u
id -g
chmod 600 .env config/config.yaml
chmod 700 logs logs/emails secrets state
```

Set `NOTIFINHO_UID` and `NOTIFINHO_GID` in `.env` to the values printed by
`id`. The production service uses that identity instead of container root.
Files mounted below `/run/secrets` must be readable by this identity and mode
`0600` when used as API-token or SMTP-password sources.

The writable `state` mount contains the v2 SQLite database and owner-scoped
secret files. Platform state and the WebUI are enabled by default and can be
disabled explicitly. See the [platform-state guide](platform-state.md) before
creating local accounts. Private state snapshots also live in this mount; configure
`platform.backup_retention`, include the mount in encrypted off-host backups,
and read the [data-portability guide](data-portability.md) before restore or
v1.x migration.

Validate and start the production definition:

```bash
docker compose -f compose.production.yaml config
docker compose -f compose.production.yaml pull
docker compose -f compose.production.yaml up -d
docker compose -f compose.production.yaml ps
docker logs --tail 100 notifinho
```

The production definition drops Linux capabilities, prevents privilege
escalation, uses a read-only root filesystem, provides a bounded temporary
filesystem, and writes only to the configured `config`, `logs`, and secrets
mounts.

## Portainer stacks

Replace relative paths in `.env` with absolute host paths, for example:

```dotenv
NOTIFINHO_CONFIG_DIR=/docker/notifinho/config
NOTIFINHO_LOG_DIR=/docker/notifinho/logs
NOTIFINHO_SECRETS_DIR=/docker/notifinho/secrets
NOTIFINHO_STATE_DIR=/docker/notifinho/state
```

Use a versioned image tag for production. Upgrade only after validating the
same image in development, then change `NOTIFINHO_IMAGE`, pull, and redeploy.

## v2.1.0 unified-configuration upgrade

Stop the existing container and copy the complete configuration and state
mounts before changing the image. v2.1.0 automatically creates a schema-3
SQLite snapshot before schema 4 and an atomic YAML backup before converting the
v2.0.2 authority marker. The host-level offline copy remains the recovery
boundary for a complete image rollback.

After signing in, verify that Destinations and Routes each show one YAML-backed
list without fallback duplicates. The Overview flow map must include every
enabled route. Edit one harmless display field in the WebUI and confirm the
same value in the host `config.yaml`; then edit it back in the file and refresh
the WebUI. Run one real source event and confirm one destination delivery and a
`delivered` history outcome.

## Reverse proxy boundary

Port `8080` is HTTP and may be published through Nginx Proxy Manager. Publishing
the container port remains an explicit deployment choice; restrict the proxy or
firewall to approved senders. Port `8025` is SMTP and must not be sent through
an HTTP reverse proxy.

The platform API uses a short-lived first-run token printed to container output
to create the first administrator in the browser. Its four components remain
independently controllable through `http.enabled`, `api.enabled`,
`platform.enabled`, and `webui.enabled`. Keep
`platform.secure_cookies: true`, publish `/api/v2` only through HTTPS, disable
proxy caching, preserve duplicate `Set-Cookie` response headers, and apply
request/body limits. Do not rewrite `Authorization`, `Cookie`, or
`X-CSRF-Token`. See the [platform API guide](platform-api.md) before enabling
the endpoint outside isolated development and the [WebUI guide](webui.md) for
the browser security boundary.

## Rollback

Set `NOTIFINHO_IMAGE` back to the previously validated version, then run:

```bash
docker compose -f compose.production.yaml pull
docker compose -f compose.production.yaml up -d
docker logs --tail 100 notifinho
```

Configuration and logs remain on the host. Review release-specific migration
notes before rolling back across a configuration or data-schema change.

v2.1.0 upgrades platform state to schema 4. A v2.0.2 image rejects schema 4.
For rollback, stop Notifinho, restore the complete pre-upgrade configuration
and state directories, pin `fortpt/notifinho:2.0.2`, and then start the stack.
