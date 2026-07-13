#!/usr/bin/env bash
# cloud_session_setup.sh — bootstrap a Claude Code *cloud* session for niouzou.
#
# Wired to the SessionStart hook (matcher: startup|resume) in
# .claude/settings.json. Makes a freshly-cloned cloud container "Railway-ready"
# and ready to build/test: it installs the Railway CLI, installs this repo's
# dependencies (api = uv, pwa = npm), and scopes the Railway CLI to the niouzou
# project so `railway logs` / `railway run` work with no extra flags.
#
# Constraints baked in (learned on the Claude Code cloud base image):
#   - the base image ships the toolchain (uv, Python 3.13, Node 22, npm) but
#     NOT the project deps nor the Railway CLI;
#   - the network proxy BLOCKS GitHub release downloads (403) → never install an
#     interpreter over the network (no `uv python install`, no `nvm install`);
#     use the runtimes already in the image. `UV_PYTHON_DOWNLOADS=never` enforces
#     that for uv (system Python 3.13 is already present);
#   - the hook re-runs on every session with no cache between sessions → the
#     script stays idempotent and fast (skips installs that are already done).
#
# Best-effort by design: a flaky registry must warn, never block startup. So no
# `set -e` around the installs, and it always ends with `exit 0`.

# --- cloud-only -------------------------------------------------------------
# No-op on the maintainer's local machine (only runs in Claude Code on the web).
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# All chatter goes to stderr so nothing pollutes the session context (SessionStart
# hook stdout is fed to the model). Failures print the captured output, indented.
log()  { printf '[cloud-setup] %s\n' "$*" >&2; }
warn() { printf '[cloud-setup] warn: %s\n' "$*" >&2; }

log "starting (project: $PROJECT_DIR)"

# --- 1. Railway CLI ---------------------------------------------------------
# Not in the base image → install from npm. Skip if already present (fast resume).
if command -v railway >/dev/null 2>&1; then
  log "railway CLI present ($(railway --version 2>/dev/null || echo '?'))"
else
  log "installing railway CLI…"
  if out=$(npm i -g @railway/cli 2>&1); then
    log "railway CLI installed ($(railway --version 2>/dev/null || echo '?'))"
  else
    warn "railway CLI install failed — install manually: npm i -g @railway/cli"
    printf '%s\n' "$out" | sed 's/^/    /' >&2
  fi
fi

# --- 2. Project dependencies ------------------------------------------------
# API — Python via uv (uv.lock present). `--frozen` mirrors CI and skips
# resolution; the `dev` group (pytest/respx/…) is a default group so it comes in
# too. `UV_PYTHON_DOWNLOADS=never` pins to the image's system Python 3.13 so a
# proxy 403 can never turn this into an interpreter download. The `embeddings`
# extra (torch) is deliberately NOT installed — tests never load the real model.
if [ -f "$PROJECT_DIR/api/uv.lock" ]; then
  log "api: uv sync --frozen (dev group, system Python 3.13)…"
  if out=$(cd "$PROJECT_DIR/api" && UV_PYTHON_DOWNLOADS=never uv sync --frozen 2>&1); then
    log "api: deps installed"
  else
    warn "api: uv sync failed — retry with: (cd api && uv sync)"
    printf '%s\n' "$out" | sed 's/^/    /' >&2
  fi
fi

# PWA — Node via npm (package-lock.json present). `npm ci` = clean, lockfile-exact
# install (matches CI). Guard on node_modules so a resume in the same container
# is a fast no-op instead of a full reinstall.
if [ -f "$PROJECT_DIR/pwa/package-lock.json" ]; then
  if [ -d "$PROJECT_DIR/pwa/node_modules" ]; then
    log "pwa: node_modules present — skipping npm ci"
  else
    log "pwa: npm ci…"
    if out=$(cd "$PROJECT_DIR/pwa" && npm ci 2>&1); then
      log "pwa: deps installed"
    else
      warn "pwa: npm ci failed — retry with: (cd pwa && npm ci)"
      printf '%s\n' "$out" | sed 's/^/    /' >&2
    fi
  fi
fi

# --- 3. Railway project scope ----------------------------------------------
# niouzou / production / api  (confirmed via `railway list --json`).
RAILWAY_PROJECT_ID="add9f76f-4054-4827-bc50-ca3af4f8b46a"
RAILWAY_ENVIRONMENT="production"
RAILWAY_SERVICE="api"

# Only link with an ACCOUNT token (RAILWAY_API_TOKEN): the CLI is authed but not
# scoped to any project. With a PROJECT token (RAILWAY_TOKEN) the CLI auto-scopes
# to that project → calling `link` would return Unauthorized, so skip it.
if command -v railway >/dev/null 2>&1; then
  if [ -n "${RAILWAY_TOKEN:-}" ]; then
    log "RAILWAY_TOKEN (project token) set — CLI auto-scoped, skipping link"
  elif [ -n "${RAILWAY_API_TOKEN:-}" ]; then
    log "linking railway → niouzou/${RAILWAY_ENVIRONMENT}/${RAILWAY_SERVICE}…"
    if out=$(railway link \
               --project "$RAILWAY_PROJECT_ID" \
               --environment "$RAILWAY_ENVIRONMENT" \
               --service "$RAILWAY_SERVICE" 2>&1); then
      log "railway linked (niouzou/${RAILWAY_ENVIRONMENT}/${RAILWAY_SERVICE})"
    else
      warn "railway link failed — use explicit -p/-e/-s flags on railway commands"
      printf '%s\n' "$out" | sed 's/^/    /' >&2
    fi
  else
    log "no Railway token in env — skipping link (set RAILWAY_API_TOKEN to enable)"
  fi
fi

log "done"
exit 0
