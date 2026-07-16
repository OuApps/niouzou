# Niouzou API image. The same image serves three roles, selected via `command`:
#   - the FastAPI app          (default CMD below)
#   - the one-shot `migrate`   (alembic upgrade head)
#   - the cron jobs            (python -m niouzou.crons.<job>)
# See docker-compose.yml at the repo root.
#
# Plain COPY (no BuildKit `--mount`) so the image builds on the legacy builder
# too — self-hosters shouldn't need buildx installed.

# --- Build stage: resolve & install dependencies with uv ----------------------
FROM python:3.13-slim AS builder

# lxml (via newspaper4k) has no cp314 wheel yet, so it compiles from source and
# needs the libxml2/libxslt headers + a C toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# uv is copied from its official image rather than pip-installed: faster and
# pinned to a known-good release.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install third-party deps first, in their own layer keyed on the lockfiles, so
# the (slow) dependency install is cached and only rebuilt when pyproject.toml /
# uv.lock change — not on every source edit. --no-dev keeps test-only packages
# (pytest, respx...) out of the image. --frozen fails loudly if the lock is stale.
COPY pyproject.toml uv.lock ./
# --extra embeddings pulls sentence-transformers + torch (E16): the worker
# computes article embeddings locally. Self-hosters who want a slimmer image
# can drop the flag — the app degrades to Classic scoring only.
RUN uv sync --frozen --no-install-project --no-dev --extra embeddings

# Then add the project source and install the package itself into the venv.
COPY . /app
RUN uv sync --frozen --no-dev --extra embeddings

# --- Runtime stage: slim image with just the venv + app -----------------------
FROM python:3.13-slim AS runtime

# Shared libs the compiled lxml links against at runtime, plus an unprivileged
# user to run as.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser
WORKDIR /app

# Bring over the fully-built /app (source + .venv) from the builder.
COPY --from=builder --chown=appuser:appuser /app /app

# Put the venv on PATH so `uvicorn`, `alembic`, `python` resolve directly,
# without needing `uv run`.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser
EXPOSE 8000

# Default role: serve the API. Overridden by the migrate and cron services.
# --proxy-headers + --forwarded-allow-ips=* let uvicorn trust the reverse
# proxy's X-Forwarded-Proto / -Host so absolute URLs are rebuilt with the
# public https scheme and host instead of the internal http://…:8000. Exec form
# (no shell) means "*" is a literal arg, not a glob. Railway overrides this via
# railway.toml's startCommand, but self-hosters running the image directly (or
# behind their own proxy) get the correct behaviour out of the box.
CMD ["uvicorn", "niouzou.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
