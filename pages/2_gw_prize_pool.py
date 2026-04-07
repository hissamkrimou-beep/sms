import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from sorare_api import fetch_fixture_games

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# ── Load config ──────────────────────────────────────────────────────────────

@st.cache_data
def load_licensed_teams():
    with open(os.path.join(DATA_DIR, "licensed_teams.json")) as f:
        return json.load(f)

@st.cache_data
def load_pp_categories():
    with open(os.path.join(DATA_DIR, "pp_categories.json")) as f:
        return json.load(f)

LICENSED_TEAMS = load_licensed_teams()
PP_CATEGORIES = load_pp_categories()

# Build a flat set of all licensed slugs for quick lookup
ALL_LICENSED_SLUGS = set()
for slugs in LICENSED_TEAMS.values():
    ALL_LICENSED_SLUGS.update(slugs)

# Build league lookup: team slug -> league name
SLUG_TO_LEAGUE = {}
for league, slugs in LICENSED_TEAMS.items():
    for s in slugs:
        SLUG_TO_LEAGUE[s] = league

# Map API competition slugs to our league names (must match keys in licensed_teams.json)
COMP_SLUG_TO_LEAGUE = {
    "premier-league-gb-eng": "Premier League",
    "laliga-es": "LALIGA EA Sports",
    "bundesliga-de": "Bundesliga",
    "ligue-1-fr": "Ligue 1",
    "serie-a-it": "Serie A",
    "mlspa": "Major League Soccer",
    "j1-100-year-vision-league": "J1 100 Year Vision League",
    "k-league-1": "K League 1",
    "jupiler-pro-league": "Jupiler Pro League",
    "eredivisie": "VriendenLoterij Eredivisie",
    "bundesliga-at": "Austrian Bundesliga",
    "superliga-dk": "Danish Superliga",
    "primeira-liga-pt": "Primeira Liga",
    "premiership-gb-sct": "Scottish Premiership",
    "spor-toto-super-lig": "Süper Lig",
    "2-bundesliga": "2. Bundesliga",
    "ligue-2-fr": "Ligue 2 BKT",
    "eliteserien-no": "Eliteserien",
    "1-hnl": "SuperSport HNL",
}


def get_licensed_teams_playing(games):
    """From a list of games, return set of licensed team slugs that are playing."""
    playing = set()
    for g in games:
        home = g["homeTeam"]["slug"]
        away = g["awayTeam"]["slug"]
        if home in ALL_LICENSED_SLUGS:
            playing.add(home)
        if away in ALL_LICENSED_SLUGS:
            playing.add(away)
    return playing


def get_licensed_teams_by_league_games(games):
    """For standalone: return teams playing in their OWN league's matches only.

    Returns a dict: league_name -> set of licensed team slugs playing in that league.
    """
    teams_by_league = {}
    for g in games:
        comp_slug = g["competition"]["slug"]
        league = COMP_SLUG_TO_LEAGUE.get(comp_slug)
        if not league:
            continue
        if league not in teams_by_league:
            teams_by_league[league] = set()
        for team_slug in [g["homeTeam"]["slug"], g["awayTeam"]["slug"]]:
            if team_slug in ALL_LICENSED_SLUGS:
                teams_by_league[league].add(team_slug)
    return teams_by_league


def count_standalone(teams_by_league, comp_config):
    """Count licensed teams playing in their own league for a standalone competition."""
    count = 0
    for league in comp_config["leagues"]:
        count += len(teams_by_league.get(league, set()))
    return count


def count_cross_league(all_playing, comp_config):
    """Count licensed teams from relevant leagues playing ANY match."""
    leagues = comp_config["leagues"]
    if leagues == ["ALL"]:
        return len(all_playing)
    count = 0
    for slug in all_playing:
        league = SLUG_TO_LEAGUE.get(slug)
        if league and league in leagues:
            count += 1
    return count


def determine_category(count, thresholds, comp_config):
    """Determine the prize pool category based on team count and thresholds.

    Returns (category_name, status) where status is 'OPEN' or 'CLOSED'.
    Applies the 50% rule when count < 10.
    """
    # Count total licensed teams for this competition
    leagues = comp_config["leagues"]
    if leagues == ["ALL"]:
        total_licensed = len(ALL_LICENSED_SLUGS)
    else:
        total_licensed = 0
        for league in leagues:
            total_licensed += len(LICENSED_TEAMS.get(league, []))

    # Rule 1: >= 10 teams playing
    if count >= 10:
        for cat_name in ["cat4", "cat3", "cat2", "cat1"]:
            if cat_name not in thresholds:
                continue
            low, high = thresholds[cat_name]
            if high is None and count >= low:
                return cat_name.upper(), "OPEN"
            if high is not None and low <= count <= high:
                return cat_name.upper(), "OPEN"
        # Fallback: lowest category
        lowest = sorted(thresholds.keys())[0]
        return lowest.upper(), "OPEN"

    # Rule 2: 50% rule - if >= 50% of total licensed teams play
    if total_licensed > 0 and count >= total_licensed * 0.5:
        lowest = sorted(thresholds.keys())[0]
        return lowest.upper(), "OPEN"

    return "-", "CLOSED"


# ── UI ───────────────────────────────────────────────────────────────────────

CAT_SORT_ORDER = {"CAT4": 0, "CAT3": 1, "CAT2": 2, "CAT1": 3, "-": 4}

st.title("GW Prize Pool Categories")

# Calendar CSS: compact buttons styled as day cells
st.markdown("""
<style>
    .day-btn div[data-testid="stButton"] button {
        height: 38px !important;
        min-height: 38px !important;
        padding: 2px 0 !important;
        font-size: 14px !important;
        border-radius: 6px !important;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar: API key
def _get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        import os
        return os.getenv(key, "")

api_key = st.sidebar.text_input("Sorare API Key (optionnel)", value=_get_secret("SORARE_API_KEY"), type="password")
api_key = api_key.strip() or None


# ── GW helpers ───────────────────────────────────────────────────────────

MONTH_ABBR = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "may", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "oct", 11: "nov", 12: "dec",
}

MONTH_NAMES_FR = {
    1: "Janvier", 2: "Fevrier", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Aout", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Decembre",
}

GW_COLOR_A = "#DBEAFE"  # blue-100
GW_COLOR_B = "#D1FAE5"  # green-100
GW_TEXT_A = "#1E40AF"   # blue-800
GW_TEXT_B = "#065F46"   # green-800
GW_SEL = "#818CF8"      # indigo-400


def build_gw_slug(start_date, end_date):
    if start_date.month == end_date.month:
        return f"football-{start_date.day}-{end_date.day}-{MONTH_ABBR[start_date.month]}-{start_date.year}"
    else:
        return f"football-{start_date.day}-{MONTH_ABBR[start_date.month]}-{end_date.day}-{MONTH_ABBR[end_date.month]}-{start_date.year}"


def generate_gw_calendar(anchor_date, num_past=15, num_future=20):
    d = anchor_date
    while d.weekday() not in (1, 4):
        d -= timedelta(days=1)
    gws = []
    start = d
    for _ in range(num_past):
        if start.weekday() == 4:
            prev_start = start - timedelta(days=3)
        else:
            prev_start = start - timedelta(days=4)
        gws.append((prev_start, start))
        start = prev_start
    gws.reverse()
    start = d
    for _ in range(num_future):
        if start.weekday() == 1:
            end = start + timedelta(days=3)
        else:
            end = start + timedelta(days=4)
        gws.append((start, end))
        start = end
    return gws


def find_gw_for_date(target, gws):
    for start, end in gws:
        if start <= target < end:
            return start, end
    return None, None


gws = generate_gw_calendar(date.today())


def gw_index(d):
    """Return (gw_start, gw_end, index) for a date."""
    for i, (gs, ge) in enumerate(gws):
        if gs <= d < ge:
            return gs, ge, i
    return None, None, -1


# ── Session state ────────────────────────────────────────────────────────

if "cal_month" not in st.session_state:
    st.session_state.cal_month = date.today().month
if "cal_year" not in st.session_state:
    st.session_state.cal_year = date.today().year
if "selected_gw" not in st.session_state:
    st.session_state.selected_gw = None


def go_prev_month():
    d = date(st.session_state.cal_year, st.session_state.cal_month, 1) - timedelta(days=1)
    st.session_state.cal_year = d.year
    st.session_state.cal_month = d.month


def go_next_month():
    if st.session_state.cal_month == 12:
        st.session_state.cal_month = 1
        st.session_state.cal_year += 1
    else:
        st.session_state.cal_month += 1


def select_day(day_date):
    gs, ge, _ = gw_index(day_date)
    if gs:
        st.session_state.selected_gw = build_gw_slug(gs, ge)


# ── Calendar rendering ───────────────────────────────────────────────────

import calendar as cal_mod

col_prev, col_title, col_next = st.columns([1, 4, 1])
with col_prev:
    st.button("◀", on_click=go_prev_month, use_container_width=True)
with col_title:
    st.markdown(
        f"<h3 style='text-align:center;margin:0;padding:4px 0'>"
        f"{MONTH_NAMES_FR[st.session_state.cal_month]} {st.session_state.cal_year}</h3>",
        unsafe_allow_html=True,
    )
with col_next:
    st.button("▶", on_click=go_next_month, use_container_width=True)

year = st.session_state.cal_year
month = st.session_state.cal_month
weeks = cal_mod.monthcalendar(year, month)
today = date.today()

# Pre-compute GW info for every day in the month
day_gw_info = {}
for week in weeks:
    for day in week:
        if day == 0:
            continue
        d = date(year, month, day)
        gs, ge, idx = gw_index(d)
        day_gw_info[day] = (gs, ge, idx)

# Build the GW info bar for hover display
selected_slug = st.session_state.selected_gw
selected_gw_start = None
selected_gw_end = None
if selected_slug:
    for gs, ge in gws:
        if build_gw_slug(gs, ge) == selected_slug:
            selected_gw_start = gs
            selected_gw_end = ge
            break

# Header row
header = st.columns(7)
for i, name in enumerate(["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]):
    header[i].markdown(
        f"<div style='text-align:center;font-size:12px;color:#888;padding:2px 0'>{name}</div>",
        unsafe_allow_html=True,
    )

# Calendar grid
for week in weeks:
    cols = st.columns(7)
    for i, day in enumerate(week):
        with cols[i]:
            if day == 0:
                st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
                continue

            d = date(year, month, day)
            gs, ge, idx = day_gw_info[day]
            is_today = d == today
            is_selected_gw = gs == selected_gw_start if gs else False

            # Color indicator bar above button
            if idx == -1:
                bar_color = "transparent"
            else:
                bar_color = GW_COLOR_A if idx % 2 == 0 else GW_COLOR_B
                if is_selected_gw:
                    bar_color = GW_SEL

            st.markdown(
                f"<div style='background:{bar_color};height:4px;border-radius:2px;margin-bottom:2px'></div>",
                unsafe_allow_html=True,
            )

            label = str(day)
            btn_type = "primary" if (is_selected_gw or is_today) else "secondary"
            st.button(
                label, key=f"d_{year}_{month}_{day}",
                on_click=select_day, args=(d,),
                use_container_width=True,
                type=btn_type,
            )

# Legend
st.markdown(
    f"<div style='display:flex;gap:16px;font-size:12px;color:#888;margin:4px 0 8px'>"
    f"<span><span style='display:inline-block;width:12px;height:12px;background:{GW_COLOR_A};border-radius:2px;vertical-align:middle'></span> GW paire</span>"
    f"<span><span style='display:inline-block;width:12px;height:12px;background:{GW_COLOR_B};border-radius:2px;vertical-align:middle'></span> GW impaire</span>"
    f"<span><span style='display:inline-block;width:12px;height:12px;background:{GW_SEL};border-radius:2px;vertical-align:middle'></span> Selectionnee</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# Show selected GW info
if not selected_slug:
    st.info("Cliquez sur un jour pour charger la GW correspondante.")
    st.stop()

if not selected_gw_start:
    st.warning(f"GW introuvable pour le slug : {selected_slug}")
    st.stop()

selected_label = f"{selected_gw_start.strftime('%a %d %b')} → {selected_gw_end.strftime('%a %d %b %Y')}"
st.caption(f"**{selected_label}** — `{selected_slug}`")

with st.spinner("Chargement des matchs..."):
    try:
        fixture_data = fetch_fixture_games(selected_slug, api_key=api_key)
    except Exception as e:
        st.error(f"Erreur API : {e}")
        st.stop()

games = fixture_data["games"]
all_playing = get_licensed_teams_playing(games)
teams_by_league = get_licensed_teams_by_league_games(games)

st.info(f"**{len(games)}** matchs — **{len(all_playing)}** equipes sous licence jouent")

# ── Build results table ──────────────────────────────────────────────
results = []

for comp_type in ["standalone", "cross_league"]:
    for comp_name, comp_config in PP_CATEGORIES[comp_type].items():
        if comp_type == "standalone":
            count = count_standalone(teams_by_league, comp_config)
        else:
            count = count_cross_league(all_playing, comp_config)
        cat, status = determine_category(count, comp_config["thresholds"], comp_config)
        results.append({
            "Competition": comp_name,
            "Type": "Standalone" if comp_type == "standalone" else "Cross-League",
            "Equipes sous licence": count,
            "Categorie": cat,
            "Statut": status,
        })

# Sort: OPEN first, then by category descending (CAT4 > CAT3 > CAT2 > CAT1)
results.sort(key=lambda r: (
    0 if r["Statut"] == "OPEN" else 1,
    CAT_SORT_ORDER.get(r["Categorie"], 99),
))

# Display table
st.subheader("Resultats")

for r in results:
    cols = st.columns([3, 2, 2, 1, 1])
    cols[0].write(r["Competition"])
    cols[1].write(r["Type"])
    cols[2].write(str(r["Equipes sous licence"]))
    cols[3].write(r["Categorie"])
    if r["Statut"] == "OPEN":
        cols[4].success("OPEN")
    else:
        cols[4].error("CLOSED")

# ── Detail expander: games by competition ────────────────────────────
st.subheader("Detail des matchs")

games_by_comp = {}
for g in games:
    comp = g["competition"]["displayName"]
    if comp not in games_by_comp:
        games_by_comp[comp] = []
    games_by_comp[comp].append(g)

for comp_name, comp_games in sorted(games_by_comp.items()):
    with st.expander(f"{comp_name} ({len(comp_games)} matchs)"):
        for g in comp_games:
            home = g["homeTeam"]
            away = g["awayTeam"]
            home_licensed = "✓" if home["slug"] in ALL_LICENSED_SLUGS else "✗"
            away_licensed = "✓" if away["slug"] in ALL_LICENSED_SLUGS else "✗"
            st.write(
                f"{home_licensed} **{home['name']}** vs **{away['name']}** {away_licensed}"
            )
