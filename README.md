# Steel Tip 01 Manager

INF2003 Group 26. Singles 501 tournament management with a MariaDB relational model and MongoDB leg evidence. The browser application supports players, tournaments, divisions, registrations, fixtures, scoring, immutable corrections, per-leg ratings, review decisions, analytics and reconciliation.

## Start with the offline demo

Requires Python 3.9 or later. Python 3.12 is recommended. No third-party Python package is needed for this mode.

1. Extract this entire ZIP into a normal folder.
2. Open a terminal in the extracted folder.
3. Run `python -m app.server` or double-click `START_DEMO.bat` on Windows.
4. Wait for the first 500-leg seed to finish. The terminal shows a preparation message and prints the local URL once the app is ready.
5. Open http://127.0.0.1:8000. Under **Insights**, the fresh fixture shows 19 of 500 legs flagged and 20 of 1,000 rated player results above the limit.

| Username | Demo password | Rights |
|---|---|---|
| organiser | demo-organiser-26 | Master records, verification, reviews, reconciliation |
| scorer | demo-scorer-26 | Create and edit own drafts; cannot verify |
| viewer | demo-viewer-26 | Read records and accepted evidence |

The prominent demo banner is intentional. This mode stores JSON in `runtime/` and does **not** run MariaDB or MongoDB. Use the database mode for the assessed DBMS demonstration. Demo credentials are only used in offline mode. Close the terminal with Ctrl+C to stop the server. Another port: `python -m app.server --port 8765`.

## Run with database servers already installed on Windows

Use `START_NATIVE_DATABASE_APP.bat` and follow `START_HERE_NATIVE.md`. This route installs the Python dependencies, prompts for database administrator credentials locally, initialises the project schemas and connects to 127.0.0.1. It does not need Docker or mongosh. Keep your existing MariaDB and MongoDB servers running. The native route is new and still needs a full live run with your administrator credentials; setup unit checks and schema synchronisation checks are included.

## Run the actual MariaDB and MongoDB application with Docker

Prerequisites: Docker Desktop with Linux containers and Docker Compose v2, Python 3.10+ for generating configuration, an internet connection for the initial image and package downloads, and at least 4 GB free RAM. The application image uses Python 3.12; the supplied images are MariaDB 11.4 and MongoDB 8.0. These are selected compatibility targets, not claims about the latest releases.

1. Run `python configure.py`. This creates fresh random passwords in an ignored `.env` and preserves an existing `.env`.
2. Open `.env` locally. Use ORGANISER_PASSWORD, SCORER_PASSWORD and VIEWER_PASSWORD with the corresponding lowercase usernames. Keep this file private and out of the submission ZIP.
3. Run `docker compose up --build -d`. First use downloads the images and Python packages; MariaDB creates tables and restricted accounts, and MongoDB creates validators, indexes and its application role.
4. Inspect `docker compose logs --tail 30 app`. The first 500-leg seed must finish before the web server starts.
5. Open http://127.0.0.1:8000. The banner must say **Database mode**, and `/api/health` must identify mode `live`.
6. Visit Database lab. Run Compare accepted totals and Run reconciliation. Both must pass before recording your assessed demonstration.

`START_DATABASE_APP.bat` wraps steps 1 and 3. No database ports are published. Only the web port is bound to 127.0.0.1. This package is intended for local demonstration, not direct internet hosting.

Stop while retaining data with `docker compose down`. Start again with `docker compose up -d`. Named volumes retain both databases. Database initialisation scripts run only for new volumes. If initialisation fails, inspect the database logs and correct the cause; do not delete volumes containing work you need. To start an independent fresh test stack without disturbing existing data, use a separate extracted copy and `docker compose -p steeltip26-test ...` with a different local web port in that copy's compose file.

For an empty database without the synthetic fixture, change the app command in compose.yaml to `["python","-m","app.server","--live","--no-seed"]` before its first start. The organiser, scorer and viewer accounts are still created. For native databases, install requirements into a virtual environment, initialise the supplied SQL and MongoDB schemas with administrator accounts, set the same environment variables as compose, and run `python -m app.server --live`. The container route avoids manual native configuration and is the supported reproducible route.

## Demonstrate the workflows

1. **Players**: add a synthetic player, edit their name, delete the unused record. A player already referenced by a registration is archived instead of deleted. Email is optional. Mark real practice records `consented` only after obtaining permission.
2. **Tournaments**: add a tournament and divisions; set cap and tolerance to nonnegative values with no more than four decimal places. Referenced tournaments are archived.
3. **Registrations**: register each player in a division and record declared rating. Duplicate player/division pairs are rejected. Deleting a registration used by a match is rejected.
4. **Matches**: create a fixture between two players already registered in the same division. Add a positive, unused leg number. Identities of fixtures are retained; create another fixture if participants change.
5. **Scoring**: create a draft for a leg. Select the board segment and multiplier for each actual dart. Use Not thrown for darts after a checkout or bust. Add visits in order; the interface alternates players. Undo removes the last unsaved visit. Load synthetic example deliberately replaces unsaved visits with a generated practice sequence.
6. **Validate and save**: validate the complete sequence, save the draft, then verify as organiser. Scorers may save only their own drafts and cannot approve. An abandoned leg may be stored, but is excluded from ratings.
7. **Corrections**: open New correction from a verified leg. It copies accepted visits into a new draft. Edit and save it, then verify. The earlier revision remains in MongoDB, accepted summaries switch atomically in MariaDB, and earlier reviews become superseded. A frozen interrupted draft offers Retry acceptance using its original version. Do not start competing corrections to resolve an orphan; check reconciliation and retry its original frozen draft.
8. **Reviews**: replay the flagged evidence, then choose confirmed or dismissed and supply a reason. A flag alone does not establish deliberate sandbagging. Historical superseded decisions remain in the database and audit records.
9. **Database lab**: compare current accepted totals, run read-only reconciliation and inspect per-leg division rankings and recent audit events. SQL examples are in `sql/queries.sql`; the MongoDB pipeline is `app/storage.py: pipeline`.

## Rating and scoring policy

Each player starts at 501. Straight-in, double-out. Visits have one to three actual darts; players alternate. Busts occur below zero, at remaining one, or on zero without a double. The entire visit earns zero and remaining score returns to its starting value. Misses and all actual darts before a bust count. Extra darts after a bust or checkout, unfinished short visits, impossible board combinations and post-checkout visits are rejected. Double bull is legal; triple bull is not.

Each eligible player's rating is `3 × credited points / actual darts` for that individual completed verified leg. Compare the exact rational value against cap plus tolerance; equality is not a breach. Display rounding never determines flags. Unplayed, abandoned and zero-dart results are excluded. There is no average across legs or minimum sample count. SQL analytics totals are a comparison workload and do not replace this rating policy.

## Verification and reproduction

The Python and frontend regression logs are in `docs/`. The application service accepted 500 legs with isolated MariaDB 12.3.3 and authenticated MongoDB 9.0.4. SQL summaries and both MongoDB pipelines agreed for 100 players. A deliberate interruption after MongoDB insertion left the original SQL result current. Retrying the same correction published once, retained both replays and cleared the orphan. See `docs/live-workflow-verification.json`.

The recorded test used MariaDB Connector/C 3.4.10 through a test adapter and PyMongo 4.18.3. The default FastAPI/PyMySQL and Docker entry points are available for reproducing the test on the demonstration machine.

Run `python -m unittest tests.test_application tests.test_native_setup tests.test_recovery_diagnostics -v`. Run `node tests/test_frontend.cjs` for frontend regression (Node is a developer dependency only). Against the running offline demo, run `python -m scripts.http_smoke --url http://127.0.0.1:8000`.

On a DISPOSABLE live installation: `docker compose exec -e STEELTIP_LIVE_TESTS=1 app python -m unittest tests.test_live -v`. Native settings can also supply the environment before the same opt-in suite. These are deliberate writes/rejection tests; do not run them on real tournament data.

On a fresh disposable stack, run `docker compose exec app python -m scripts.benchmark_live`, then copy `/app/docs/live-benchmark.json` from the container. The benchmark checks equality at 100 and 500 legs, records median and p95 from 60 measured warm reads, and measures throughput with four concurrent clients. It also compares compound-index revision lookup to a scan. Run it before the correction test and pause other writes while timing.

Then run `docker compose exec -e STEELTIP_LIVE_TESTS=1 app python -m scripts.verify_live_workflow` to inject and retry one correction on the disposable fixture. The check expects 500 original revisions and changes one leg as part of the test.

The optional Windows `python -m scripts.verify_mongodb_standalone` reproduces the new Mongo checks using a fresh private server on33318 with authentication enabled. It requires MongoDB9 at its standard installation path and runtime fixtures created by running the offline demo first. It does not use the user's27017server. The script intentionally refuses an occupied test port.

## Data and source map

`data/synthetic_dataset.json` contains 100 synthetic players, 5 tournaments, 10 divisions, 100 registrations, 50 matches and 500 legal completed legs. Regenerate the fixture and second-seed summary with `python -m app.dataset`. The ordinary-play fixture produces 19 flagged legs (3.8%) and 20 flagged player results (2.0%). `data/public_league_reference.csv` contains three published league-leading averages for scale. Run `python -m scripts.verify_review_workload` for the separate 5% deliberate omission experiment. A rating flag asks for human review.

Fresh databases and fresh offline extractions load the revised fixture. An existing installation keeps the fixture and real records already stored. To see the revised numbers immediately, run the offline app from a fresh extraction or create a separate disposable Compose project using the instructions above.

| Location | Purpose |
|---|---|
| app/scoring.py | Scoring, exact threshold comparison, evidence digest |
| app/service.py | CRUD, authorisation, acceptance, reviews and reconciliation |
| app/storage.py | MariaDB/MongoDB adapters, offline adapters, aggregation |
| app/api.py and app/server.py | Shared API dispatch, FastAPI live server, offline server |
| sql/ | Schema, view, integrity constraints, grants and complex queries |
| mongo/init.js | Collection validators, indexes and restricted application role |
| web/ | Responsive browser interface without external assets |
| tests/ | Domain/workflow tests and explicit live checks |
| docs/ | Diagrams and database verification results |

The final report and presentation are in the separate course submission pack.

## Security and recovery

Server-side roles enforce all writes. Passwords use salted PBKDF2; session tokens are random and only their hashes persist. Tokens expire after eight hours and are invalidated on logout. SQL values are parameterised; table and column names are allowlisted. User-controlled text is escaped in the browser. MongoDB application credentials cannot update or delete revisions; MariaDB application credentials cannot edit revisions, result snapshots or audit events. Root administrators can still modify data, so this is not tamperproof storage.

Cross-store acceptance uses MongoDB insertion before one MariaDB transaction. The leg is locked before its base revision is checked. A failure can leave MongoDB orphan evidence; retry the same frozen draft. Reconciliation never silently accepts or deletes evidence. Read operations reject accepted evidence that is missing, has a mismatched digest, or has altered derived results. If evidence is missing, stop approval and comparison, restore it from backup and rerun reconciliation. Keep MariaDB and MongoDB backups from a coordinated stopped-write point; no automated backup/restore guarantee is claimed.

## Troubleshooting

- Python command missing: install Python 3.10+ and enable its PATH option, or use `py -3` in the commands.
- Port already used: stop the process you own or select another demo port. For live mode change only the host side of `127.0.0.1:8000:8000`.
- Docker unavailable: start Docker Desktop with Linux containers. The offline demo is useful for UI/workflow review but does not fulfil a real-DBMS demonstration.
- Image or package download fails: retry on a network allowed to reach Docker Hub and PyPI. Do not mistake this for a scoring error.
- App is not ready: initial seed happens before server startup; check app/database logs and wait for completion. Restart safely; seeding resumes accepted legs and retains evidence.
- Login fails in live mode: use passwords from the `.env` used on first user creation, not the demo passwords. Changing `.env` does not silently reset existing account hashes.
- Mongo validation/index or permission errors: inspect initialisation logs and run the live tests in a disposable stack before editing access grants.

## Submission

Use the final report PDF, presentation PPTX and a real team-recorded MP4 of no more than 10 minutes. All five members are on the report and slide covers. The 9:25 presentation plan follows background and dataset, relational design and demo, NoSQL design and demo, comparison, and performance. The two demonstration segments total 3:35. Submit source, data and this manual together in one ZIP. Complete peer review individually. The stated deadline is 29 November 2026 at 11:30 pm Singapore.

## SteelTip1.1 additions

The sports-themed interface adds Insights with a current-rating histogram and synthetic review-burden warning. Database lab can read actual live versions, SQL EXPLAIN, accepted counts, index metadata and all-field total parity. `RESET_WEBSITE_PASSWORD.bat` provides local administrator recovery after forgotten passwords or a re-extracted installation. Startup detects a configured organiser-password mismatch instead of implying a changed settings file resets a stored hash. Preserve runtime/native-settings.json when upgrading; see START_HERE_NATIVE.md.

The revised report has ten body pages in Calibri 12 and a crow’s-foot ER diagram. The 14-slide PPTX includes named presenters, the updated findings and timed speaker notes.

For a same-Wi-Fi phone demonstration, see PHONE_DEMO.md and START_PHONE_LAN.bat.
