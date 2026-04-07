"""Deadline calculator — shows the registration deadline per Sorare competition."""

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from sorare_api import fetch_fixtures, fetch_fixture_games, fetch_fixture_leaderboards

CET = ZoneInfo("Europe/Paris")


def _compute_deadline(first_match_cet: datetime, cycle_start_day: int) -> datetime:
    """Compute the deadline given the first match datetime (CET) and the cycle
    start day (4=Friday for weekend cycle, 1=Tuesday for midweek cycle).

    Rules (symmetric for both cycles):
    - Match on cycle day (Fri/Tue):
        >= 20:30  → cycle day 19:00
        <  20:30  → cycle day 16:00
    - Match on cycle day + 1 (Sat/Wed):
        <  17:00  → cycle day 19:00
        >= 17:00  → (cycle day + 1) 16:00
    - Match on cycle day + 2 (Sun/Thu):
        <  17:00  → (cycle day + 1) 16:00
        >= 17:00  → (cycle day + 2) 16:00
    """
    match_day = first_match_cet.weekday()
    match_time = first_match_cet.time()

    days_diff = match_day - cycle_start_day
    if days_diff < 0:
        days_diff += 7
    cycle_date = first_match_cet.date() - timedelta(days=days_diff)

    if days_diff == 0:
        if match_time >= dtime(20, 30):
            return datetime.combine(cycle_date, dtime(19, 0), tzinfo=CET)
        else:
            return datetime.combine(cycle_date, dtime(16, 0), tzinfo=CET)
    elif days_diff == 1:
        if match_time < dtime(17, 0):
            return datetime.combine(cycle_date, dtime(19, 0), tzinfo=CET)
        else:
            return datetime.combine(cycle_date + timedelta(days=1), dtime(16, 0), tzinfo=CET)
    elif days_diff == 2:
        if match_time < dtime(17, 0):
            return datetime.combine(cycle_date + timedelta(days=1), dtime(16, 0), tzinfo=CET)
        else:
            return datetime.combine(cycle_date + timedelta(days=2), dtime(16, 0), tzinfo=CET)
    else:
        return datetime.combine(cycle_date, dtime(16, 0), tzinfo=CET)


def _cycle_start_day(first_match_cet: datetime) -> int:
    """Fri/Sat/Sun → Friday cycle (4). Mon/Tue/Wed/Thu → Tuesday cycle (1)."""
    wd = first_match_cet.weekday()
    return 4 if wd in (4, 5, 6) else 1


# ── UI ────────────────────────────────────────────────────────────────────────

st.header("Deadlines")

sorare_key = st.text_input("Sorare API Key", type="password", key="dl_sorare_key")

fixtures = fetch_fixtures(api_key=sorare_key, count=5)

if not fixtures:
    st.warning("Impossible de charger les fixtures.")
    st.stop()

fixture_labels = [f"{f['displayName']}  ({f['slug']})" for f in fixtures]
sel_idx = st.selectbox("Fixture", range(len(fixture_labels)), format_func=lambda i: fixture_labels[i])
selected_fixture = fixtures[sel_idx]

with st.spinner("Chargement des donnees…"):
    fixture_data = fetch_fixture_games(selected_fixture["slug"], api_key=sorare_key)
    games = fixture_data.get("games", [])
    try:
        league_comps = fetch_fixture_leaderboards(selected_fixture["slug"], api_key=sorare_key)
    except Exception as e:
        st.error(f"Erreur leaderboards: {e}")
        league_comps = {}

if not games:
    st.info("Aucun match trouve pour cette fixture.")
    st.stop()

# Index games by competition slug → earliest match datetime (CET)
comp_slug_first_match = {}
for g in games:
    if not g.get("date") or not g.get("competition"):
        continue
    comp_slug = g["competition"]["slug"]
    match_utc = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
    match_cet = match_utc.astimezone(CET)
    if comp_slug not in comp_slug_first_match or match_cet < comp_slug_first_match[comp_slug]:
        comp_slug_first_match[comp_slug] = match_cet

# For each Sorare competition, find the earliest match across its eligible leagues
rows = []
for league_name, comp_slugs in sorted(league_comps.items()):
    if not comp_slugs:
        continue
    first_match = None
    for slug in comp_slugs:
        dt = comp_slug_first_match.get(slug)
        if dt and (first_match is None or dt < first_match):
            first_match = dt
    if first_match is None:
        continue
    cycle_day = _cycle_start_day(first_match)
    deadline = _compute_deadline(first_match, cycle_day)
    rows.append({
        "Competition Sorare": league_name,
        "1er match (CET)": first_match.strftime("%a %d/%m %Hh%M"),
        "Deadline": deadline.strftime("%a %d/%m %Hh%M"),
    })

rows.sort(key=lambda r: r["Deadline"])

if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Aucune competition Sorare trouvee pour cette fixture.")
