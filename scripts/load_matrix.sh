#!/usr/bin/env bash
set -euo pipefail
# Fixed SLO: docs/SLO.md. Locust users each wait for completion before re-submission.
mkdir -p results/load
for workers in 1 3; do
  docker compose up -d --wait --scale classifier-worker="$workers" api classifier-worker
  for clients in 1 10 30; do
    docker compose --profile load run --rm locust --host http://api:8000 --headless -u "$clients" -r 10 -t "${LOAD_DURATION:-40s}" --stop-timeout 180 --csv "/results/load/w${workers}-u${clients}" --csv-full-history --only-summary
  done
done
