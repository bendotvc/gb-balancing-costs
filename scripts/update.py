#!/usr/bin/env python3
"""Rebuild data/daily.csv from NESO's "Daily Balancing Costs" dataset.

NESO publishes one half-hourly file per financial year. This script asks
NESO's data portal (a CKAN API) to sum each file to one row per day, then
writes every day from START_FY onward to data/daily.csv and a small
data/meta.json. Standard library only, so it runs anywhere with Python 3.9+.

If NESO can't be reached or returns something unexpected, the script exits
non-zero and leaves the existing files untouched, so the site keeps showing
the last good data.
"""
import csv
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("NESO_BASE", "https://api.neso.energy/api/3/action/")
DATASET_ID = "d13d78fc-60d9-4f4d-87b6-e25a20f669c0"  # Daily BSUoS Cost Data
START_FY = int(os.environ.get("START_FY", "2021"))   # first financial year (April start) to include
OUT = Path(__file__).resolve().parent.parent / "data"

# NESO column -> our column
CATS = {
    "Constraints": "constraints",
    "Positive Reserve": "positive_reserve",
    "Negative Reserve": "negative_reserve",
    "Energy Imbalance": "energy_imbalance",
    "Frequency Control": "frequency_control",
    "Other": "other",
}
COLUMNS = ["date", "total", *CATS.values(), "settlement_periods"]


def get(action, params):
    url = BASE + action + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gb-balancing-costs-site/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = json.load(r)
            if not body.get("success"):
                raise RuntimeError(f"NESO API error: {body.get('error')}")
            return body["result"]
        except Exception as e:  # network blips, 5xx, rate limits
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{action} failed after retries: {last}")


def yearly_resources():
    """Every 'Daily Balancing Costs YYYY-YYYY' file from START_FY on, oldest first."""
    pkg = get("package_show", {"id": DATASET_ID})
    found = []
    for r in pkg["resources"]:
        m = re.fullmatch(r"Daily Balancing Costs (\d{4})-(\d{4})", (r.get("name") or "").strip())
        if m and int(m.group(1)) >= START_FY and r.get("datastore_active"):
            found.append((int(m.group(1)), r["id"], r["name"]))
    if not found:
        raise RuntimeError("No yearly resources found — has NESO renamed the files?")
    return sorted(found)


def daily_rows(resource_id):
    sums = ", ".join(f'SUM("{src}") AS "{dst}"' for src, dst in CATS.items())
    sql = (f'SELECT "SETT_DATE"::date AS "date", {sums}, COUNT(*) AS "n" '
           f'FROM "{resource_id}" GROUP BY 1 ORDER BY 1')
    res = get("datastore_search_sql", {"sql": sql})
    out = []
    for rec in res["records"]:
        vals = {dst: float(rec[dst] or 0) for dst in CATS.values()}
        row = {"date": str(rec["date"])[:10]}
        row["total"] = round(sum(vals.values()))
        row.update({k: round(v) for k, v in vals.items()})
        row["settlement_periods"] = int(rec["n"])
        out.append(row)
    return out


def main():
    resources = yearly_resources()
    by_date = {}
    for fy, rid, name in resources:
        rows = daily_rows(rid)
        print(f"{name}: {len(rows)} days", file=sys.stderr)
        for row in rows:
            by_date[row["date"]] = row  # a later file wins if NESO ever overlaps years
    days = [by_date[d] for d in sorted(by_date)]

    # Sanity checks before overwriting good data
    if len(days) < 365:
        raise RuntimeError(f"Only {len(days)} days returned — refusing to overwrite.")
    old = OUT / "daily.csv"
    if old.exists():
        with old.open() as f:
            old_n = sum(1 for _ in f) - 1
        if len(days) < old_n - 7:
            raise RuntimeError(f"New data has {len(days)} days vs {old_n} before — refusing to overwrite.")

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(days)
    text = buf.getvalue()
    if old.exists() and old.read_text() == text:
        print(f"No change: still {len(days)} days to {days[-1]['date']}", file=sys.stderr)
        return

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "daily.csv.tmp"
    tmp.write_text(text)
    tmp.replace(old)

    meta = {
        "source": "NESO Data Portal — Daily Balancing Services Use of System (BSUoS) Cost Data",
        "source_url": "https://www.neso.energy/data-portal/daily-balancing-costs-balancing-services-use-system",
        "first_date": days[0]["date"],
        "latest_date": days[-1]["date"],
        "days": len(days),
        "files": [name for _, _, name in resources],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Wrote {len(days)} days, {days[0]['date']} to {days[-1]['date']}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Update failed, keeping existing data: {e}", file=sys.stderr)
        sys.exit(1)
