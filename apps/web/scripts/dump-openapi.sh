#!/bin/sh
# Regenerates apps/web/openapi.json from the FastAPI code (no running server needed).
# Then run `pnpm --filter @agentic/web gen:client` to rebuild the typed client in src/client.
set -eu
cd "$(dirname "$0")/../../.."
uv run --frozen python -c '
import json
from agentic_api.main import create_app
from agentic_api.settings import Settings

print(json.dumps(create_app(Settings(environment="test")).openapi(), indent=2))
' > apps/web/openapi.json
echo "wrote apps/web/openapi.json"
