# GB balancing costs

A small public website showing the daily cost of balancing Great Britain's
electricity grid, built from NESO's published *Daily Balancing Costs* data
(1 April 2021 onward). It updates itself: every morning a GitHub Action asks
NESO's data portal for the latest figures, commits any new days and
republishes the site.

## What's here

| Path | What it is |
| --- | --- |
| `index.html` | The site: headline figures, daily and monthly charts, financial-year table, every day in a sortable table, CSV download. |
| `data/daily.csv` | One row per day, in pounds, by NESO cost category. Created and rewritten by the updater. |
| `data/meta.json` | Date range, which NESO files were used, and when new data last arrived. |
| `scripts/update.py` | The updater. Standard-library Python; sums NESO's half-hourly files to days via the portal's SQL API. Finds new financial-year files automatically. |
| `.github/workflows/update.yml` | Runs the updater daily at 07:17 UTC (and on demand), commits changes, deploys to GitHub Pages. |

## Refreshing by hand

The site refreshes itself every morning. To force a refresh, go to
**Actions → Update NESO data and publish → Run workflow**.

## Good to know

- **NESO publishes new days roughly weekly**, not daily, so the latest date on
  the site usually trails today by a few days to a week. The site shows the
  latest NESO date at the top and turns its status dot amber if the data is
  over two weeks old.
- **NESO revises recent figures** as costs are reconciled; the updater re-reads
  every year's file each run, so revisions flow through automatically.
- **If NESO is down**, the updater keeps the existing data and the site stays up.
  It also refuses to overwrite the data if NESO returns far fewer days than
  before.
- **Change the start year** by setting `START_FY` in the workflow's env
  (e.g. `2017` to include NESO's data back to April 2017).
- GitHub pauses scheduled workflows in repos with no activity for 60 days;
  the weekly data commits keep it active.
- To test locally: `python scripts/update.py`, then `python -m http.server`
  and open http://localhost:8000.

Data: [NESO Data Portal — Daily Balancing Services Use of System (BSUoS) Cost Data](https://www.neso.energy/data-portal/daily-balancing-costs-balancing-services-use-system).
