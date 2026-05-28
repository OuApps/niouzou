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
RUN uv sync --frozen --no-install-project --no-dev

# Then add the project source and install the package itself into the venv.
COPY . /app
RUN uv sync --frozen --no-dev

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

# Wrapper that promotes /secrets/miniflux_api_key (written by miniflux_bootstrap
# in the self-host compose) into MINIFLUX_API_KEY before exec'ing the command.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default role: serve the API. Overridden by the migrate and cron services.
CMD ["uvicorn", "niouzou.main:app", "--host", "0.0.0.0", "--port", "8000"]
