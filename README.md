# Overseas Study Guide — Public Source Candidate

## Contribute data and code

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Claim a school/program/year/field through the data-gap Issue template, submit an evidence-backed JSON proposal, and open a PR. The offline validator rejects malformed proposals, stale field hashes and conflicting evidence IDs. Passing checks means **awaiting maintainer review**, not verified facts or deployment.

See [data release and rollback](docs/DATA_RELEASE.md) for the maintainer-only review/staging workflow. Contributions cannot modify the live database directly. The included example is synthetic. Server synchronization remains a separate production acceptance step.

This is a **source-code preview**, not a production-ready service or a claim that the recommendation model is complete. It contains the Flask/Waitress intake service, report-pipeline source modules, and synthetic manifest fixtures. The production institution/program/evidence database, real student forms, reports, review records, release archives, and credentials are deliberately excluded.

## Current verified boundary

- The current intake implementation is Flask + Waitress (`webapp/app.py`), not the planned FastAPI communication-only stage.
- The included local test suite exercises intake validation, encrypted storage boundaries, admin authorization, and injected rendering failures. All 10 included webapp tests passed on 2026-10-20.
- The synthetic catalog JSON files are hash/manifest fixtures only; they contain no usable university/program records. Report generation requires a separately obtained, properly licensed catalog and an independently verified output-template release.
- The public source snapshot still contains historical preview gates. Current product requirements use the approved full illustrated format without a fixed page count, Western and Asian sections, and explicit unknown fields. Those production changes are not claimed to be included in this older public snapshot. This repository includes no student report.
- No production server, cloud deployment, or chat-to-inbox connector is included or claimed.

## Run the intake tests

From `webapp/` with Python 3.11+:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The tests set ephemeral credentials and use temporary storage. Never reuse these test values in a deployment.

## Run locally (development only)

Create isolated local secrets, then start the service:

```powershell
python setup_secrets.py
waitress-serve --listen=127.0.0.1:8080 app:app
```

Open `http://127.0.0.1:8080/`. The data directory defaults to `webapp/data/`, which is ignored by Git. Do not expose the development server to the public internet. Production deployment requires a security review, HTTPS reverse proxy, a licensed verified catalog, data retention policy, and completed template acceptance.

## License

MIT. See `LICENSE`.

## Repository scope

See `PUBLICATION_SCOPE.md`. This candidate is not an exact copy of the working package. Before public publication, review the staged file list and rerun the privacy/secret scan; publish only this candidate directory.

