# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (`main`) | ✅ |
| older tags | ❌ — please upgrade |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

To report a security issue responsibly:

1. Email **nomi25home@gmail.com** with the subject line `[SECURITY] garage-storage — <brief description>`.
2. Include:
   - A clear description of the vulnerability and its potential impact.
   - Steps to reproduce (proof-of-concept if possible).
   - Any suggested remediation.
3. You will receive an acknowledgement within **72 hours**.
4. If confirmed, a fix will be prioritised and a patched release issued within a reasonable timeframe (target: 14 days for critical issues).
5. You will be credited in the release notes unless you prefer to remain anonymous.

## Scope

This project is a self-hosted homelab application. Typical concerns include:

- Unauthenticated API endpoints allowing data exfiltration or modification.
- Path traversal or arbitrary file read/write via photo upload endpoints.
- SQL injection in search or filter parameters.
- Stored XSS in item names, categories, or tags rendered in the UI.

## Out of Scope

- Vulnerabilities that require physical access to the host machine.
- Issues in upstream dependencies (report directly to those maintainers; open a Dependabot PR here as well).
- Denial-of-service against a self-hosted instance with no rate limiting (by design for homelab use).
