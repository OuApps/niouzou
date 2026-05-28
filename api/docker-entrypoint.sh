#!/bin/sh
# When the API image runs under docker-compose.yml, the Miniflux API key is
# dropped into /secrets/miniflux_api_key by the one-shot `miniflux_bootstrap`
# service. Promote it to the MINIFLUX_API_KEY env var that pydantic-settings
# expects, then exec the actual command.
#
# An env-supplied MINIFLUX_API_KEY (e.g. on Railway) always wins — we only
# fall back to the file when the variable is unset or empty.
set -e

if [ -z "$MINIFLUX_API_KEY" ] && [ -s /secrets/miniflux_api_key ]; then
    MINIFLUX_API_KEY="$(cat /secrets/miniflux_api_key)"
    export MINIFLUX_API_KEY
fi

exec "$@"
