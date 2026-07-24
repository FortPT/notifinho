"""Ordered SQLite schema migrations for persistent v2 platform state."""

from __future__ import annotations


MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "platform foundation",
        (
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                username_normalized TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                failed_login_count INTEGER NOT NULL DEFAULT 0
                    CHECK (failed_login_count >= 0),
                locked_until INTEGER,
                last_login_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                csrf_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                idle_expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                CHECK (expires_at > created_at),
                CHECK (idle_expires_at > created_at)
            )
            """,
            "CREATE INDEX sessions_user_id ON sessions(user_id)",
            "CREATE INDEX sessions_expiry ON sessions(expires_at, idle_expires_at)",
            """
            CREATE TABLE api_tokens (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK (role IN ('admin', 'application')),
                source_scopes TEXT NOT NULL DEFAULT '[]',
                rate_limit_per_minute INTEGER NOT NULL DEFAULT 60
                    CHECK (rate_limit_per_minute BETWEEN 1 AND 10000),
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                last_used_at INTEGER,
                revoked_at INTEGER,
                UNIQUE (owner_user_id, name_normalized)
            )
            """,
            """
            CREATE TABLE secret_records (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                kind TEXT NOT NULL,
                file_name TEXT NOT NULL UNIQUE,
                value_sha256 TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE (owner_user_id, name_normalized)
            )
            """,
            """
            CREATE TABLE destinations (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                output_type TEXT NOT NULL,
                secret_id TEXT REFERENCES secret_records(id) ON DELETE RESTRICT,
                settings_json TEXT NOT NULL DEFAULT '{}',
                shared INTEGER NOT NULL DEFAULT 0 CHECK (shared IN (0, 1)),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE (owner_user_id, name_normalized)
            )
            """,
            """
            CREATE TABLE routes (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                destination_id TEXT NOT NULL
                    REFERENCES destinations(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                source TEXT NOT NULL,
                filters_json TEXT NOT NULL DEFAULT '{}',
                priority INTEGER NOT NULL DEFAULT 100,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE (owner_user_id, name_normalized)
            )
            """,
            "CREATE INDEX routes_source ON routes(source, enabled, priority)",
            """
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                outcome TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL
            )
            """,
            "CREATE INDEX audit_events_created_at ON audit_events(created_at)",
        ),
    ),
    (
        2,
        "user routing and delivery foundation",
        (
            "ALTER TABLE api_tokens ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE api_tokens ADD COLUMN updated_at INTEGER",
            "UPDATE api_tokens SET updated_at = created_at WHERE updated_at IS NULL",
            """
            CREATE TABLE delivery_attempts (
                id TEXT PRIMARY KEY,
                delivery_id TEXT NOT NULL,
                owner_user_id TEXT NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                route_id TEXT REFERENCES routes(id) ON DELETE SET NULL,
                destination_id TEXT REFERENCES destinations(id) ON DELETE SET NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                severity TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (
                    outcome IN ('delivered', 'failed', 'retry_scheduled')
                ),
                attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
                retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0, 1)),
                response_status INTEGER,
                error_code TEXT,
                safe_error TEXT,
                created_at INTEGER NOT NULL,
                completed_at INTEGER NOT NULL,
                UNIQUE (delivery_id, attempt_number)
            )
            """,
            """
            CREATE INDEX delivery_attempts_owner_created
            ON delivery_attempts(owner_user_id, created_at DESC)
            """,
            """
            CREATE INDEX delivery_attempts_destination_created
            ON delivery_attempts(destination_id, created_at DESC)
            """,
        ),
    ),
    (
        3,
        "secure first-run bootstrap",
        (
            """
            CREATE TABLE bootstrap_tokens (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER,
                CHECK (expires_at > created_at)
            )
            """,
            """
            CREATE UNIQUE INDEX bootstrap_tokens_active
            ON bootstrap_tokens((consumed_at IS NULL))
            WHERE consumed_at IS NULL
            """,
        ),
    ),
    (
        4,
        "unified YAML configuration mirror",
        (
            "ALTER TABLE destinations ADD COLUMN configuration_key TEXT",
            "ALTER TABLE routes ADD COLUMN configuration_key TEXT",
            """
            CREATE UNIQUE INDEX destinations_configuration_key
            ON destinations(configuration_key)
            WHERE configuration_key IS NOT NULL
            """,
            """
            CREATE UNIQUE INDEX routes_configuration_key
            ON routes(configuration_key)
            WHERE configuration_key IS NOT NULL
            """,
        ),
    ),
    (
        5,
        "v2.2 operations and presentation",
        (
            "ALTER TABLE users ADD COLUMN avatar_data TEXT",
            "ALTER TABLE api_tokens ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))",
            "ALTER TABLE delivery_attempts ADD COLUMN input_type TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE delivery_attempts ADD COLUMN device_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE delivery_attempts ADD COLUMN event_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE delivery_attempts ADD COLUMN event_description TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE delivery_attempts ADD COLUMN event_status TEXT NOT NULL DEFAULT ''",
            """
            CREATE TABLE application_usage (
                application_name TEXT PRIMARY KEY,
                last_used_at INTEGER NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 1 CHECK (request_count >= 1)
            )
            """,
            """
            CREATE TABLE notices (
                id TEXT PRIMARY KEY,
                created_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('information', 'warning', 'severe')
                ),
                kind TEXT NOT NULL CHECK (
                    kind IN ('announcement', 'system_error', 'update')
                ),
                system_key TEXT UNIQUE,
                persistent INTEGER NOT NULL DEFAULT 0 CHECK (persistent IN (0, 1)),
                created_at INTEGER NOT NULL,
                resolved_at INTEGER
            )
            """,
            "CREATE INDEX notices_active_created ON notices(resolved_at, created_at DESC)",
            """
            CREATE TABLE notice_dismissals (
                notice_id TEXT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                dismissed_at INTEGER NOT NULL,
                PRIMARY KEY (notice_id, user_id)
            )
            """,
            """
            CREATE TABLE backup_schedule_runs (
                period_key TEXT PRIMARY KEY,
                started_at INTEGER NOT NULL,
                completed_at INTEGER,
                outcome TEXT,
                backup_id TEXT,
                external_path TEXT
            )
            """,
        ),
    ),
    (
        6,
        "v2.3 WebUI operations and managed backup targets",
        (
            "ALTER TABLE users ADD COLUMN first_login_at INTEGER",
            """
            UPDATE users
            SET first_login_at = COALESCE(last_login_at, created_at)
            WHERE last_login_at IS NOT NULL
            """,
            "ALTER TABLE notices ADD COLUMN updated_at INTEGER",
            "UPDATE notices SET updated_at = created_at WHERE updated_at IS NULL",
            """
            CREATE TABLE backup_targets (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL UNIQUE,
                target_type TEXT NOT NULL CHECK (target_type IN ('local', 'nfs', 'smb')),
                host TEXT NOT NULL DEFAULT '',
                remote_path TEXT NOT NULL DEFAULT '',
                share_name TEXT NOT NULL DEFAULT '',
                local_path TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL DEFAULT '',
                secret_id TEXT REFERENCES secret_records(id) ON DELETE RESTRICT,
                mount_options TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                mounted_at INTEGER,
                last_test_at INTEGER,
                last_test_outcome TEXT,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """,
            "CREATE INDEX backup_targets_type_name ON backup_targets(target_type, name_normalized)",
        ),
    ),

    (
        7,
        "v2.4 integrations and route inputs",
        (
            "ALTER TABLE routes ADD COLUMN input_type TEXT NOT NULL DEFAULT ''",
            """
            CREATE TABLE integration_categories (
                integration_source TEXT PRIMARY KEY,
                category TEXT NOT NULL CHECK (
                    category IN (
                        'virtualization', 'monitoring', 'storage',
                        'networking', 'hardware', 'automation',
                        'containers', 'security', 'generic'
                    )
                ),
                updated_at INTEGER NOT NULL
            )
            """,
        ),
    ),
)


LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]
