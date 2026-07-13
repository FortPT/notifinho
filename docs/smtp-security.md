# SMTP security

Notifinho can protect its SMTP listener with explicit STARTTLS and SMTP AUTH.
Both features are disabled by default so existing deployments remain compatible.

## Threat model

Without TLS, SMTP message content and credentials can be observed or modified by
anyone able to intercept traffic between the sender and Notifinho. SMTP AUTH by
itself does not protect credentials because the built-in `LOGIN` and `PLAIN`
mechanisms encode credentials but do not encrypt them.

Notifinho therefore never exposes or accepts SMTP AUTH before TLS. Authentication
requires STARTTLS support and uses TLS 1.2 or newer.

TLS and authentication do not replace network controls. Continue restricting the
published SMTP port to trusted appliance addresses with host and network
firewalls.

## Backward-compatible default

An existing configuration containing only:

```yaml
smtp:
  host: "0.0.0.0"
  port: 8025
```

continues to operate without TLS or authentication.

Security is activated only when `smtp.tls.enabled` or `smtp.auth.enabled` is
explicitly enabled.

## Secure enablement defaults

When TLS is enabled, `require_starttls` defaults to `true`. A sender must upgrade
the session before `MAIL`, `RCPT`, or `DATA`.

When authentication is enabled, `required` defaults to `true`. A sender must
authenticate before submitting mail.

Explicit `false` overrides are available for controlled migrations, but they
reduce protection and should not be used as the final configuration.

## STARTTLS configuration

Mount a certificate and private key into the container, then configure:

```yaml
smtp:
  host: "0.0.0.0"
  port: 8025

  tls:
    enabled: true
    certfile: "/notifinho/config/tls/cert.pem"
    keyfile: "/notifinho/config/tls/key.pem"
```

The effective behavior is equivalent to:

```yaml
    require_starttls: true
```

For a temporary TLS-available-but-optional migration:

```yaml
    require_starttls: false
```

That override permits plaintext mail and should be removed after all senders
have been migrated.

## SMTP AUTH configuration

Notifinho supports the `LOGIN` and `PLAIN` mechanisms provided by `aiosmtpd`.
They are advertised only after STARTTLS.

One fixed SMTP service account is supported:

```yaml
smtp:
  tls:
    enabled: true
    certfile: "/notifinho/config/tls/cert.pem"
    keyfile: "/notifinho/config/tls/key.pem"

  auth:
    enabled: true
    username: "notifinho"
    password_env: "NOTIFINHO_SMTP_PASSWORD"
    password_file: ""
```

Authentication is required by default when enabled. A temporary optional-auth
migration can explicitly set:

```yaml
    required: false
```

Do not use optional authentication as a permanent deployment mode.

## Password from an environment variable

The configuration stores the name of an environment variable, never the
password itself:

```yaml
smtp:
  auth:
    enabled: true
    username: "notifinho"
    password_env: "NOTIFINHO_SMTP_PASSWORD"
    password_file: ""
```

Docker Compose or Portainer stack example:

```yaml
services:
  notifinho:
    image: fortpt/notifinho:latest
    environment:
      NOTIFINHO_SMTP_PASSWORD: "${NOTIFINHO_SMTP_PASSWORD}"
    volumes:
      - ./config:/notifinho/config
      - ./config/tls:/notifinho/config/tls:ro
      - ./logs:/notifinho/logs
    ports:
      - "8025:8025"
      - "18080:8080"
```

Define `NOTIFINHO_SMTP_PASSWORD` through the deployment environment or
Portainer environment-variable interface. Do not commit it to the repository.

## Password from a Docker secret or mounted file

Set `password_env` to an empty string and configure `password_file`:

```yaml
smtp:
  auth:
    enabled: true
    username: "notifinho"
    password_env: ""
    password_file: "/run/secrets/notifinho_smtp_password"
```

Docker Swarm secret example:

```yaml
services:
  notifinho:
    image: fortpt/notifinho:latest
    secrets:
      - notifinho_smtp_password
    volumes:
      - ./config:/notifinho/config
      - ./config/tls:/notifinho/config/tls:ro
      - ./logs:/notifinho/logs

secrets:
  notifinho_smtp_password:
    external: true
```

For standalone Docker or Portainer, mount a root-owned, read-only file at the
configured path instead. Confirm the container user can read it before rollout.

Exactly one usable source must be configured when authentication is enabled:
`password_env` or `password_file`. Startup fails when both or neither are usable.
A single trailing LF or CRLF is removed from a file-based secret because Docker
secret files commonly end with a newline. Other spaces are preserved.

## Certificates

The configured certificate must match the hostname used by sending appliances.
Use a certificate issued by an authority the appliances trust whenever possible.

A self-signed certificate can be used for controlled testing, but each sender
must explicitly trust it or support certificate-verification exceptions. Avoid
turning off certificate verification globally.

Recommended permissions:

```bash
chmod 644 config/tls/cert.pem
chmod 600 config/tls/key.pem
```

Restrict access to the private key and include certificate renewal in normal
operations.

The certificate and key under `tests/fixtures/tls` are synthetic test fixtures.
They must never be used for deployment.

## Startup validation

Notifinho fails startup when an enabled security mode is incomplete, including:

- authentication enabled without TLS;
- missing certificate or private key;
- unreadable certificate or private key;
- empty SMTP username;
- missing or empty password environment variable;
- missing, unreadable, or empty password file;
- both password sources configured;
- invalid boolean settings.

Errors identify the invalid setting but never include password values or AUTH
payloads.

## Sender compatibility

Before production rollout, confirm each appliance supports:

- explicit STARTTLS on the configured SMTP port;
- TLS 1.2 or newer;
- certificate hostname and trust validation;
- SMTP AUTH `LOGIN` or `PLAIN` after STARTTLS;
- the configured service-account username and password.

Some infrastructure appliances support STARTTLS but cannot authenticate, while
others authenticate but cannot trust a private certificate authority. Validate
each sender independently.

## Rollout procedure

1. Keep firewall allowlisting in place.
2. Mount the certificate and private key.
3. Enable TLS in Notifinho and leave authentication disabled.
4. Restart the container and verify `STARTTLS` is advertised.
5. Configure and test STARTTLS on every sender.
6. Configure the SMTP username and one password source.
7. Enable authentication in Notifinho.
8. Restart and test every sender through the normal parser, router, and output
   path.
9. Review logs for delivery failures without enabling protocol-level credential
   logging.

For a phased rollout, explicit optional overrides can be used briefly. Document
the deadline for removing them.

## Rollback

To restore the legacy listener:

```yaml
smtp:
  host: "0.0.0.0"
  port: 8025

  tls:
    enabled: false

  auth:
    enabled: false
```

Restart the container, restore the previous sender settings, and retain firewall
restrictions. Certificate and secret mounts may remain present while their
features are disabled.

## What is not included

The SMTP security feature does not add:

- implicit SMTPS;
- multiple SMTP accounts;
- mutual TLS;
- rate limiting;
- account lockout;
- certificate provisioning or renewal;
- generic authentication for HTTP or output integrations.
