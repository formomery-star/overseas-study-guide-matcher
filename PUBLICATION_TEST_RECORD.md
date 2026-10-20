# Candidate test record — 2026-10-20

- Scope: staged public source candidate only; no real student data or production institution database was used.
- Command: `python -m unittest discover -s tests -v` from `webapp/`.
- Result: **10/10 passed** using the existing local project Python environment.
- Coverage: submission receipt privacy; encrypted payload and attachment storage; admin authorization/CSRF; deletion; input and file type validation; numeric rejection; renderer failure isolation; renderer timeout isolation; database snapshot digest using synthetic manifest fixtures.
- Environment note: a fresh candidate virtual environment could not download pinned dependencies during this run because package-index TLS connections ended unexpectedly. The tests were then executed with the already-installed project environment. A clean external install remains to be verified.
- Not covered: real-school matching, production catalog correctness, report contents or PDF layout, FastAPI stage 1 acceptance, cloud/local production deployment, or live chat access to intake data.
