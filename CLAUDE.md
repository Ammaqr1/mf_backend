# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FastAPI + async SQLAlchemy backend for a mutual-fund tracker (CAMS statement import, NAV lookup via mfapi.in, cookie-based JWT auth). There is no README, test suite, or linter config. `mf_backend/` has its own `.git` (nested inside the outer `mf-central` repo).

## Environment / commands

- Python venv lives in `venv/` (gitignore lists `.venv`, so `venv/` is not ignored — don't commit it).
- Required `.env` vars: `DATABASE_URL`, `FRONTEND_ORIGINS`, `JWT_SECRET_KEY` (app fails at import without `JWT_SECRET_KEY`; `main.py` crashes if `FRONTEND_ORIGINS` is unset).
- `requirements.txt` only lists the PDF-extraction deps (pdfplumber, pymupdf, pytesseract, Pillow). The app also needs fastapi, sqlalchemy[asyncio], asyncpg, alembic, python-dotenv, PyJWT, pwdlib, bcrypt, cuid2, requests — install these manually.
- Run the API: `uvicorn app.main:app --reload` from the parent directory of a folder named `app` (see import note below).
- Migrations (Alembic, config in `db/alembic.ini`, script_location `db/migrations`): `alembic -c db/alembic.ini upgrade head`, `alembic -c db/alembic.ini revision --autogenerate -m "msg"`. `migrations/env.py` reads `DATABASE_URL` and swaps `postgresql` → `postgresql+asyncpg`. It imports only `Base, Credentials` from `schema`, so autogenerate must see all models via `Base.metadata`.
- `python db/create_tables.py [reset]` — legacy `create_all`/`drop_all` helper using a *sync* engine that no longer exists in `db/db.py` (the sync engine is commented out), and it requires an argv. Prefer Alembic.

## Architecture

Layered: `api/v1/endpoints` (routes) → `services` (business logic, owns commit/rollback) → `db/queries` (SQLAlchemy statements) → `db/schema.py` (models). `schemas/` holds Pydantic request/response models; `core/` holds cross-cutting concerns.

- `main.py`: builds the app, CORS (credentials on, headers `Content-Type`/`X-CSRF-Token`), installs `core/csrf.py` as HTTP middleware, mounts `api/v1/router.py` at `/api/v1`. Add new routers in `api/v1/router.py`.
- Auth: access token (JWT HS256, 15 min) is read from the `access_token` cookie in `core/dependecies.py:get_current_user` (note the filename typo — keep it when importing). Refresh tokens (7 days) are stored hashed in a DB table with token-family revocation for reuse detection (`db/queries/refresh_token.py`, `services/auth_service.py`). Passwords: `pwdlib` recommended hasher for new hashes; `verify_password` also accepts legacy bcrypt (`$2…`) hashes.
- CSRF: no token — `core/csrf.py` rejects non-safe methods whose `Origin` header is missing or not in `FRONTEND_ORIGINS` (or the API's own origin, for Swagger).
- DB: `db/db.py` exposes `engine`, `SessionLocal`, `get_db` (FastAPI dependency), `close_db`. Fully async; `expire_on_commit=False`. IDs are 24-char cuid2 strings (`generate_cuid` in `schema.py`). Models: `Credentials` (login account), `User`, `MutualFundHolding`, `MutualFundTransaction`.
- Statement import pipeline (standalone scripts, not wired into the API yet): `pdf.py` parses a CAMS consolidated statement PDF into users/schemes/transactions, using `mf_api.py` to resolve scheme codes/NAV via mfapi.in (matched by ISIN) and normalising scheme categories. `testing.py` is scratch.

## Gotchas

- **Inconsistent import roots.** Package code (`main.py`, `api/`, `core/`, `services/`) imports as `app.core...`, `app.db...` — the project directory is expected to be importable as `app` (the folder is named `mf_backend` on disk). But `db/aqueries.py`, `db/create_tables.py`, `migrations/env.py`, and `pdf.py` use bare imports (`from schema import ...`, `from db import ...`), which only work when run with `db/` (or the root) on `sys.path`. `pdf.py` also imports `Session` from `db` and `queries.create_user/create_scheme`, which don't exist anymore (the DB layer moved to async `SessionLocal`/`db/queries/`). Check which style a file uses before adding imports.
- `db/aqueries.py` is an older monolithic async query module that overlaps with `db/queries/credentials.py` (different signature: it hashes the password itself, whereas the newer `create_credential` takes `password_hash`). New code should use `db/queries/*`.
- `main.py` passes `origin` (a raw string from env) to `allow_origins`/`allowed_origins`; CORS expects a list and `csrf.py` does `set(...)` over it, which would split a string into characters. Parse `FRONTEND_ORIGINS` into a list when touching this.
