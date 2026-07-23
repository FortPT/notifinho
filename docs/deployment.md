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
mkdir -p logs/emails secrets state external-backups
id -u
id -g
chmod 600 .env config/config.yaml
chmod 700 logs logs/emails secrets state external-backups
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
NOTIFINHO_EXTERNAL_BACKUP_DIR=/mnt/notifinho-backups
```

Use a versioned image tag for production. Upgrade only after validating the
same image in development, then change `NOTIFINHO_IMAGE`, pull, and redeploy.

## v2.3.3 WebUI corrective upgrade

v2.3.3 keeps platform schema 6 and does not migrate `config.yaml` or SQLite
state. Stop the container and copy the complete configuration, state, log, and
secrets mounts before changing the image from `2.3.2` to `2.3.3`.

After deployment, force-refresh the browser once, verify F5 on several pages,
run Check for updates, send one source-aware destination test, remove one safe
inactive source, and validate both 12-hour and 24-hour scheduled backup entry.

Complete the
[v2.3.3 acceptance checklist](v2.3.3-acceptance-checklist.md) before production.

## v2.3.2 corrective upgrade

v2.3.2 keeps platform schema 6. Stop the container and copy the complete
configuration, state, log, and secrets mounts before changing the image from
`2.3.1` to `2.3.2`.

For direct NFS/SMB mounting, render and deploy the production definition with
the managed-backup override:

```bash
docker compose \
  -f compose.production.yaml \
  -f compose.managed-backups.yaml \
  config

docker compose \
  -f compose.production.yaml \
  -f compose.managed-backups.yaml \
  up -d
```

The override runs as root and adds `DAC_OVERRIDE`, `FOWNER`, and `SYS_ADMIN`
after the base service drops every capability. These are required to access
existing UID-owned bind mounts, apply the platform state mode, and perform the
remote mount. Managed NFS backup mounts add `nolock`, so NFSv3 does not need
`rpc.statd` runtime files below the read-only `/run`.

Complete the
[v2.3.2 acceptance checklist](v2.3.2-acceptance-checklist.md) before production.

## v2.3.1 corrective WebUI upgrade

v2.3.1 keeps platform schema 6. Stop the container, copy the complete
configuration and state mounts, then change only the image from `2.3.0` to
`2.3.1`.

For trusted-LAN HTTP login:

```yaml
platform:
  secure_cookies: false
webui:
  public_url: ""
  enforce_https: false
```

For reverse-proxied HTTPS:

```yaml
platform:
  secure_cookies: true
webui:
  public_url: "https://notifinho.example.com"
  enforce_https: true
```

Saving an NFS or SMB destination enables managed mounts automatically. Start
the service with both Compose files when using that feature:

```bash
docker compose \
  -f compose.production.yaml \
  -f compose.managed-backups.yaml \
  up -d
```

Complete the
[v2.3.1 acceptance checklist](v2.3.1-acceptance-checklist.md) before production.

## v2.3.0 WebUI and backup-destination upgrade

Stop the existing container and copy the complete configuration and state
mounts before changing the image. v2.3.0 creates a schema-5 SQLite snapshot
before schema 6. A v2.2.1 image cannot open schema-6 platform state.

The safest NFS/SMB arrangement remains a host-mounted share bound into the
container. Create a Local target in the WebUI whose path is inside that bounded
mount; Notifinho retains its non-root identity, read-only root filesystem, and
dropped capabilities.

Application-managed NFS/SMB mounts are opt-in. They require the mount helpers
packaged in the image, `platform.backups.managed_mounts: true`, and the
managed-mount override:

```bash
docker compose \
  -f compose.production.yaml \
  -f compose.managed-backups.yaml \
  config

docker compose \
  -f compose.production.yaml \
  -f compose.managed-backups.yaml \
  up -d
```

The v2.3.2 override runs the service as root with `DAC_OVERRIDE`, `FOWNER`, and
`SYS_ADMIN`. Use it only on a dedicated trusted host. Prefer a read/write share
restricted to the Notifinho host and backup path. SMB secrets are encrypted in
private state and remain write-only, but moving mount authority into the
container increases impact if the application is compromised.

For enforced HTTPS entry, set `webui.public_url` to the external HTTPS URL and
`webui.enforce_https: true`. The reverse proxy supplies TLS; Notifinho redirects
only browser WebUI requests and does not manufacture an HTTPS endpoint.

After deployment, complete the
[v2.3.0 acceptance checklist](v2.3.0-acceptance-checklist.md).

## v2.2.0 operational upgrade

Before changing the image, stop the existing container and copy the complete
configuration and state mounts. v2.2.0 creates a schema-4 SQLite snapshot before
schema 5. The unified YAML remains compatible with v2.1.0, but a v2.1.0 image
cannot open schema-5 platform state.

After deployment, verify notices, all five Overview ranges, every configured
route in Routing Flow, destination preview/test delivery, application status,
profile pictures, health checks, and input toggles. Run one real source event
and confirm one delivery record with device, event, source, status, attempt,
and input fields.

For external backup storage, mount NFS or SMB on the Docker host using the
host's normal credential controls, then bind that directory into the container:

```yaml
volumes:
  - /mnt/notifinho-backups:/notifinho/external-backups
```

Set the WebUI external path to `/notifinho/external-backups`. The container
does not need `SYS_ADMIN`, mount privileges, or network-share credentials.

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

v2.2.0 upgrades platform state to schema 5. A v2.1.0 image rejects schema 5.
For rollback, stop Notifinho, restore the complete pre-upgrade configuration
and state directories, pin `fortpt/notifinho:2.1.0`, and then start the stack.

v2.3.0 upgrades platform state to schema 6. Rollback to v2.2.1 requires the
complete pre-v2.3.0 state and configuration copy; never hand-edit the schema
marker.
