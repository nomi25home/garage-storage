# Kapaat Roadmap

This document outlines the core post-v1.0.0 developmental milestones for Kapaat, prioritizing operational flexibility, multi-user concurrency, and data durability.

## Active Phase: Hardening & Data Portability (P2)

### 1. Unified Browser-Driven Backups
*   **Target:** `/api/backup/download` endpoint.
*   **Scope:** Build a Python routine that hot-copies the live SQLite database, bundles the `photos/` media assets, compresses them into a single `.zip` matrix, and streams it safely to the client web UI.

### 2. Transparent Database Storage Encryption
*   **Target:** SQLCipher runtime implementation.
*   **Scope:** Add support for a `DB_ENCRYPTION_KEY` variable inside `.env`. If detected, wrap the SQLite connector layer with SQLCipher to handle on-disk block encryption for enhanced household asset privacy.

### 3. Structural Version Control (Migrations)
*   **Target:** Schema upgrade runner logic.
*   **Scope:** Abstract table setups into a custom historical version registry table, terminating raw, brittle `ALTER TABLE` startup commands.

### 4. Deterministic Webhook Sync Mapping
*   **Target:** Conflict handling routines for `/api/sync-row`.
*   **Scope:** Explicitly codify append-only protections to guarantee data mutations in the browser can never be silently stomped by asynchronous Google Sheets automation sync steps.
