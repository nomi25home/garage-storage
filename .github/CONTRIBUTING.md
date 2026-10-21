# Contributing

Thanks for your interest in improving nomi25home Storage! This document explains how to contribute effectively.

## Getting started locally

```bash
git clone https://github.com/nomi25home/garage-storage.git
cd garage-storage
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in BASE_URL at minimum
uvicorn app:app --reload --port 8096
```

Open [http://localhost:8096](http://localhost:8096). The SQLite database is created automatically on first run at the path set by `DB_PATH` (default: `/data/garage_inventory.db` — override in your `.env` if needed for local dev).

## Reporting bugs

1. Search [existing issues](https://github.com/nomi25home/garage-storage/issues) first.
2. Open a new issue using the **Bug report** template.
3. Include: steps to reproduce, expected vs actual behaviour, browser/OS, and any relevant console errors.

## Suggesting features

Open a [Feature request](https://github.com/nomi25home/garage-storage/issues/new) issue before writing code. Briefly describe the use-case and proposed approach. This avoids wasted effort if the direction doesn't fit the project.

## Submitting a Pull Request

1. **Fork** the repo and create a feature branch off `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. **Keep changes focused** — one feature or fix per PR. Unrelated cleanups belong in a separate PR.
3. **Test your change** manually against a local instance before opening the PR.
4. **Update `CHANGELOG.md`** — add a line under `[Unreleased]` describing what changed.
5. **Open the PR** against `main`. Fill in the description with *what* changed and *why*.

### PR checklist

- [ ] `app.py` changes do not introduce hardcoded secrets, IPs, or personal URLs
- [ ] New configuration values are exposed via environment variables and documented in `.env.example`
- [ ] Template changes are tested in both light and dark mode at mobile and desktop widths
- [ ] No new runtime dependencies added without discussion (keep the image lean)

## Code style

- Python: follow PEP 8; keep functions small and single-purpose.
- JavaScript: vanilla ES2020+, no build step, no frameworks.
- HTML/CSS: inline styles are acceptable in the Jinja template for component-scoped rules; global rules go in the `<style>` block.

## Commit messages

Use the conventional format: `type: short summary` (e.g. `feat: add room filter`, `fix: bin edit modal typo`, `docs: update README`). No period at the end.
