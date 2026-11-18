# SteelTip

SteelTip is a web application for singles 501 darts competitions. It registers players and fixtures, records each dart, validates double-out checkouts, and keeps an audit trail when a leg is corrected. MariaDB stores competition records and official results. MongoDB keeps the ordered scoring evidence and earlier revisions.

## Run the offline demo

1. Download or clone this repository.
2. Double-click `START_DEMO.bat` on Windows, or run `python -m app.server` from the repository root.
3. Wait for the terminal to print the local URL and the offline demo sign-in details. Open the URL in your browser and sign in as the organiser.
4. In **Matches**, open an accepted leg and click **Replay**. Open **Insights** to see the synthetic fixture's rating distribution and review workload.

## Run with MariaDB and MongoDB

With Python and Docker Compose installed, run `python configure.py` to generate your local configuration, then `docker compose up --build`. Open `http://127.0.0.1:8000` and use the organiser sign-in generated in your local `.env` file. Keep that file private. Once SteelTip shows **Database mode**, open **Database lab → Compare accepted totals** to compare both stores.

On Windows with both database servers already installed, run `START_NATIVE_DATABASE_APP.bat` and follow its prompts.

## Source and data

- `app/` and `web/` contain the application and browser interface.
- `sql/` and `mongo/` contain the database schemas and setup scripts.
- `data/synthetic_dataset.json` contains 500 synthetic legs. The review flag prompts an organiser to inspect the evidence.
- `tests/` contains application, native setup, and frontend regression tests.

This is the INF2003 Group 26 application source. The report and presentation are submitted separately.
