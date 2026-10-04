"""Data access for the MCP server.

Default backend is the local JSON fixture (fictional data, safe to demo).
Set AKILI_DATA=sheets to read a Google Sheet with the same four tabs instead.
"""
import json
import os
import time
from functools import lru_cache
from pathlib import Path

BACKEND = os.environ.get("AKILI_DATA", "fixture")
FIXTURE = Path(os.environ.get("AKILI_FIXTURE", Path(__file__).resolve().parent.parent / "fixtures" / "demo_data.json"))
CACHE_TTL = 30  # seconds, protects you from Sheets API rate limits

# Tab columns: action_items(client, owner, item, due YYYY-MM-DD, status)
#              deals(client, deal, stage, updated)
#              meetings(client, date, title, summary)
#              sprints(client, sprint, target, result)


@lru_cache(maxsize=1)
def _sheet():
    import gspread

    gc = gspread.service_account(filename=os.environ["GOOGLE_SA_JSON"])
    return gc.open_by_key(os.environ["AKILI_SHEET_ID"])


_cache: dict = {}


def tab_rows(tab: str) -> list[dict]:
    hit = _cache.get(tab)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    if BACKEND == "sheets":
        rows = _sheet().worksheet(tab).get_all_records()
    else:
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))[tab]
    _cache[tab] = (time.time(), rows)
    return rows


def norm(name: str) -> str:
    return str(name).strip().lower().replace(" ", "")


def all_clients() -> set[str]:
    return {norm(r["client"]) for r in tab_rows("deals")}


def for_client(tab: str, client: str) -> list[dict]:
    return [r for r in tab_rows(tab) if norm(r.get("client", "")) == client]


def is_open(row: dict) -> bool:
    return str(row.get("status", "")).strip().lower() not in {"done", "closed", "complete"}
