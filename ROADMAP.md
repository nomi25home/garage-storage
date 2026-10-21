# Kapaat Roadmap

This document outlines the core post-v1.0.0 developmental milestones for Kapaat, prioritizing operational flexibility, multi-user concurrency, and data durability.

## Shipped in v1.1.0

### ✅ 1. Unified Browser-Driven Backups
*   **Delivered:** `/api/backup/download` endpoint + navbar button.
*   Hot-copies the live SQLite database via `sqlite3.backup()`, bundles all `photos/` assets, and streams a compressed `.zip` to the browser. One click from the navbar.

### ✅ 2. Transparent Database Storage Encryption
*   **Delivered:** Optional SQLCipher support via `DB_ENCRYPTION_KEY` env var.
*   When set, the app swaps in `pysqlcipher3` at runtime for AES-256 on-disk encryption. Requires `ENABLE_SQLCIPHER=1` Docker build arg. Falls back to plain SQLite with a printed warning if the library is absent.

## Active Phase: Schema & Sync Reliability (P2)

### 3. Structural Version Control (Migrations)
*   **Target:** Schema upgrade runner logic.
*   **Scope:** Abstract table setups into a custom historical version registry table, terminating raw, brittle `ALTER TABLE` startup commands.

### 4. Deterministic Webhook Sync Mapping
*   **Target:** Conflict handling routines for `/api/sync-row`.
*   **Scope:** Explicitly codify append-only protections to guarantee data mutations in the browser can never be silently stomped by asynchronous Google Sheets automation sync steps.
