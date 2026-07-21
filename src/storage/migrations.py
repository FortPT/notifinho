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
)


LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]
