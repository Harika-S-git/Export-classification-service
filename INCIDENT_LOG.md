# Development incident log

| Timestamp (UTC) | Symptom | Reproduction | Root cause | Fix | Verification |
|---|---|---|---|---|---|
| 2026-10-09 | Local `python -m pytest -q` failed during collection with `ModuleNotFoundError: No module named 'redis'`. | Run pytest in the existing Anaconda environment before installing project requirements. | Project runtime dependencies were not installed in the interpreter running pytest. Installing pinned requirements also reported conflicts with unrelated preinstalled LangChain packages in that shared environment. | Installed project requirements, including Redis/RQ, then reran tests. Recommended clean virtual environment or Docker for reproducibility rather than relying on the shared Anaconda environment. | User observed `4 passed in 2.27s`; `docker compose config --quiet` returned no errors. This verification predates the added guardrail tests; rerun after pulling latest main. |
