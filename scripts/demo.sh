#!/usr/bin/env bash
set -euo pipefail
# Fault injection is an explicit demo-only mode. Restore afterwards.
trap 'if [ -f .env.bak ]; then mv .env.bak .env; docker compose up -d api verifier provider-stub classifier-worker; fi' EXIT
sed -i.bak 's/ENABLE_FAULTS=false/ENABLE_FAULTS=true/' .env
docker compose up -d --wait --force-recreate api verifier provider-stub classifier-worker
docker compose --profile tools run --rm toolbox python -m tools.demo
mv .env.bak .env
docker compose up -d --wait --force-recreate api verifier provider-stub classifier-worker
