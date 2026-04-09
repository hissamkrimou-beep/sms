import json
import os
import re
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from api_football import (
    fetch_injuries, fetch_fixtures_by_date, fetch_fixture_events,
    fetch_fixture_lineups, fetch_upcoming_fixtures, fetch_predictions,
    fetch_odds,
)
from sorare_api import (
    fetch_team_players_with_scores, fetch_start_odds,
    fetch_fixtures, fetch_fixture_games,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ── thresholds ─────────────────────────────────────────────────────────────
BOOSTED_MIN_SCORE = 67
BOOSTED_MIN_DELTA = 10
REDUCED_MIN_AVG = 48
REDUCED_MIN_DELTA = 12
U23_PREV_WINDOW = 5
STALENESS_DAYS = 14
PLAYER_MATCH_WORD_RATIO = 0.5

# ── helpers ─────────────────────────────────────────────────────────────────

@st.cache_data
def _load_json(name):
    with open(DATA_DIR / name) as f:
        return json.load(f)


def _last_monday():
    """Return the most recent Monday (today if today is Monday)."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def _weekend_dates(monday):
    """Return (saturday, sunday) before the given Monday."""
    saturday = monday - timedelta(days=2)
    sunday = monday - timedelta(days=1)
    return saturday, sunday


def _normalize(name):
    """Lowercase, strip accents, remove FC/CF/SC/AFC suffixes."""
    name = name or ""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    name = re.sub(r"\b(fc|cf|sc|afc)\b", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


def _slugify(name):
    name = _normalize(name)
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def _match_team_to_sorare(team_name, licensed_slugs, overrides):
    """Try to match an API-Football team name to a Sorare slug."""
    # 1. Exact override
    if team_name in overrides:
        return overrides[team_name]

    # 2. Slugify and search — prefer exact slug match, then prefix
    slug_candidate = _slugify(team_name)
    # Exact slug contained
    for slug in licensed_slugs:
        if slug_candidate == slug:
            return slug
    # Slug starts with candidate (but candidate must be long enough to avoid false matches)
    if len(slug_candidate) >= 5:
        for slug in licensed_slugs:
            if slug.startswith(slug_candidate):
                return slug

    # 3. Normalized word-level match
    norm_words = _normalize(team_name).split()
    if norm_words:
        for slug in licensed_slugs:
            slug_readable = slug.replace("-", " ")
            # All meaningful words (3+ chars) from the team name appear in the slug
            long_words = [w for w in norm_words if len(w) >= 3]
            if long_words and all(w in slug_readable for w in long_words):
                return slug

    return None


def _match_player_name(api_name, sorare_players):
    """Match an API-Football player name to a Sorare player dict.
    Uses word-boundary matching to avoid false positives on short names."""
    api_lower = (api_name or "").lower().strip()
    if not api_lower:
        return None

    # Build regex-safe words from API name for matching
    api_words = [w for w in re.split(r"[\s.\-]+", api_lower) if len(w) >= 2]

    best_match = None
    best_score = 0

    for p in sorare_players:
        last = (p.get("lastName") or "").lower().strip()
        first = (p.get("firstName") or "").lower().strip()

        if not last:
            continue

        score = 0

        # Exact full name match (best)
        full = f"{first} {last}".strip()
        if full == api_lower or api_lower == full:
            return p

        # Last name word-boundary match (avoid "lee" matching "leeroy")
        if last and len(last) >= 2:
            pattern = r"(?:^|[\s.\-])" + re.escape(last) + r"(?:$|[\s.\-])"
            if re.search(pattern, api_lower):
                score += 3
                # Bonus if first name also matches
                if first and len(first) >= 2:
                    first_pattern = r"(?:^|[\s.\-])" + re.escape(first) + r"(?:$|[\s.\-])"
                    if re.search(first_pattern, api_lower):
                        score += 2

        # Check if API name words appear as word boundaries in Sorare name
        if score == 0 and api_words:
            sorare_full = f"{first} {last}"
            matched_words = sum(1 for w in api_words if w in sorare_full)
            if matched_words >= 1 and matched_words >= len(api_words) * PLAYER_MATCH_WORD_RATIO:
                score += matched_words

        if score > best_score:
            best_score = score
            best_match = p

    return best_match


# API-Football pos (G/D/M/F) → Sorare position mapping
_POS_MAP = {"G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Forward"}
_POS_REVERSE = {v: k for k, v in _POS_MAP.items()}


def _player_display_name(p):
    first = p.get("firstName") or ""
    last = p.get("lastName") or ""
    return f"{first} {last}".strip() or p.get("slug", "?")


# ── score helpers ───────────────────────────────────────────────────────────

def _extract_scores(player):
    raw = player.get("so5Scores") or []
    scores = []
    for n in raw:
        if n.get("score") is not None and n.get("game"):
            scores.append({"score": n["score"], "date": n["game"]["date"]})
    scores.sort(key=lambda x: x["date"], reverse=True)
    return scores


def _avg(scores, n):
    """Average of the last N scores where the player actually played (score > 0)."""
    played = [s["score"] for s in scores if s["score"] > 0]
    vals = played[:n]
    return sum(vals) / len(vals) if vals else 0


def _weighted_avg(scores, n):
    """Weighted average of the last N scores (most recent counts double)."""
    played = [s["score"] for s in scores if s["score"] > 0]
    vals = played[:n]
    if not vals:
        return 0
    # First element (most recent) gets weight 2, rest get weight 1
    weights = [2] + [1] * (len(vals) - 1)
    return sum(v * w for v, w in zip(vals, weights)) / sum(weights)


def _parse_score_date(date_str):
    """Parse a score date string (ISO 8601) to a date object."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        return None


def _total_mins_l5(player):
    """Sum of minsPlayed over the last 5 so5Scores."""
    raw = player.get("so5Scores") or []
    entries = []
    for n in raw:
        if n.get("game"):
            mins = 0
            pgs = n.get("playerGameStats") or {}
            if pgs.get("minsPlayed"):
                mins = pgs["minsPlayed"]
            entries.append({"date": n["game"]["date"], "mins": mins})
    entries.sort(key=lambda x: x["date"], reverse=True)
    return sum(e["mins"] for e in entries[:5])


# ── recommendation scoring ─────────────────────────────────────────────────

def _normalize_scores(values):
    """Min-max normalize a list of values to 0-100."""
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mn == mx:
        return [50.0] * len(values)
    return [(v - mn) / (mx - mn) * 100 for v in values]


def _build_predictions_lookup(predictions, all_players, licensed_teams, config, overrides):
    """Build a lookup that maps API-Football names, Sorare slugs, Sorare club names,
    slugified names, and normalized names to win probabilities."""
    lookup = dict(predictions)  # start with Odds API names

    # For each Odds API team name, store normalized + slugified variants
    for name, pct in predictions.items():
        lookup.setdefault(_normalize(name), pct)
        lookup.setdefault(_slugify(name), pct)

    # For each Odds API team name, find corresponding Sorare slug
    for league_cfg in config.get("leagues", []):
        league_slugs = licensed_teams.get(league_cfg.get("licensed_teams_key", ""), [])
        for name, pct in predictions.items():
            sorare_slug = _match_team_to_sorare(name, league_slugs, overrides)
            if sorare_slug:
                lookup.setdefault(sorare_slug, pct)

    # Also map Sorare club display names
    seen_clubs = set()
    for p in all_players:
        club = p.get("activeClub") or {}
        club_name = club.get("name", "")
        team_slug = p.get("_team_slug", "")
        if club_name and club_name not in seen_clubs and team_slug in lookup:
            lookup.setdefault(club_name, lookup[team_slug])
            lookup.setdefault(_normalize(club_name), lookup[team_slug])
            lookup.setdefault(_slugify(club_name), lookup[team_slug])
            seen_clubs.add(club_name)

    return lookup


def _start_odds_multiplier(start_odds):
    """Convert startOdds (0-1) to a score multiplier.

    < 0.5   → excluded (returns 0)
    0.5-0.79 → penalized (linear 0.3 → 1.0)
    >= 0.79  → no penalty (returns 1.0)
    """
    if start_odds is None:
        return 1.0  # no data → no penalty
    if start_odds < 0.5:
        return 0.0  # excluded
    if start_odds >= 0.79:
        return 1.0
    # Linear interpolation: 0.5 → 0.3, 0.79 → 1.0
    t = (start_odds - 0.5) / (0.79 - 0.5)
    return 0.3 + t * 0.7


def _freshness_multiplier(latest_score_date, reference_date):
    """Score multiplier based on how recently the player last played.

    0-7 days   → 1.0  (no penalty)
    8-14 days  → 0.8  (slight penalty)
    15-21 days → 0.5  (moderate penalty)
    22+ days   → 0.2  (heavy penalty)
    """
    if latest_score_date is None or reference_date is None:
        return 0.5  # no data → moderate penalty
    days_ago = (reference_date - latest_score_date).days
    if days_ago <= 7:
        return 1.0
    if days_ago <= 14:
        return 0.8
    if days_ago <= 21:
        return 0.5
    return 0.2


def _compute_reco_scores(candidates, supply_lookup, predictions_lookup, start_odds_lookup=None, reference_date=None):
    """Compute recommendation score for each candidate dict.

    Each candidate must have keys: slug, team_name, _league.
    Enriches each candidate in-place with score fields.
    Returns the list sorted by score descending (excludes players < 50% start odds).
    """
    if not candidates:
        return candidates

    if start_odds_lookup is None:
        start_odds_lookup = {}

    # Build slug → Sorare player lookup from all_players in session
    all_players = st.session_state.get("lm_players", [])
    slug_to_player = {p.get("slug"): p for p in all_players if p.get("slug")}
    # Build player UUID → slug mapping
    uuid_to_slug = {}
    for p in all_players:
        pid = (p.get("id") or "").replace("Player:", "")
        if pid and p.get("slug"):
            uuid_to_slug[pid] = p["slug"]

    # Map start_odds_lookup (UUID-keyed) to slug-keyed
    slug_start_odds = {}
    for uuid, odds in start_odds_lookup.items():
        slug = uuid_to_slug.get(uuid)
        if slug:
            slug_start_odds[slug] = odds

    raw_form = []
    raw_odds = []

    for c in candidates:
        slug = c.get("slug", "")
        player = slug_to_player.get(slug)

        # Resolve position if missing
        if not c.get("position") and player:
            c["position"] = player.get("position", "")

        # Form: weighted L5 / L40 ratio (most recent match counts double)
        if player:
            scores = _extract_scores(player)
            l5 = _avg(scores, 5)
            l40 = _avg(scores, 40)
            wl5 = _weighted_avg(scores, 5)
            form = wl5 / l40 if l40 > 0 else 0
            c["_latest_score_date"] = _parse_score_date(scores[0]["date"]) if scores else None
        else:
            l5 = 0
            l40 = 0
            form = 0
            c["_latest_score_date"] = None
        c["_l5_avg"] = round(l5, 1)
        c["_l40_avg"] = round(l40, 1)
        c["_form"] = round(form, 2)
        raw_form.append(form)

        # Minutes played L5
        c["_mins_l5"] = _total_mins_l5(player) if player else 0

        # Win probability — try team_name, _team_slug, slugified, normalized, activeClub
        team = c.get("team_name", "")
        odds = predictions_lookup.get(team, 0)
        if odds == 0:
            odds = predictions_lookup.get(_normalize(team), 0)
        if odds == 0:
            odds = predictions_lookup.get(_slugify(team), 0)
        if odds == 0:
            p = slug_to_player.get(slug)
            if p:
                odds = predictions_lookup.get(p.get("_team_slug", ""), 0)
                if odds == 0:
                    club_name = (p.get("activeClub") or {}).get("name", "")
                    if club_name:
                        odds = predictions_lookup.get(club_name, 0)
                        if odds == 0:
                            odds = predictions_lookup.get(_slugify(club_name), 0)
        # Last resort: prefix match on slugified team name
        if odds == 0 and team:
            team_sl = _slugify(team)
            if len(team_sl) >= 5:
                for key, val in predictions_lookup.items():
                    if key.startswith(team_sl) or team_sl.startswith(key):
                        odds = val
                        break
        c["_win_prob"] = odds
        raw_odds.append(odds)

        # Supply ratios — SR and Unique separately
        supply_data = supply_lookup.get(slug, {})
        sr_left = supply_data.get("super_rare_left_sales", 0) or 0
        sr_total = supply_data.get("super_rare_sales_total", 0) or 0
        sr_ratio = sr_left / sr_total if sr_total > 0 else 0
        c["_sr_supply"] = round(sr_ratio, 2)

        u_available = int(supply_data.get("available_unique_supply", 0) or 0)
        c["_u_supply"] = "Disponible" if u_available >= 1 else "Vendu"

        # Start odds from SorareInside
        c["_start_odds"] = slug_start_odds.get(slug)

    # Normalize
    norm_form = _normalize_scores(raw_form)
    norm_odds = _normalize_scores(raw_odds)

    for i, c in enumerate(candidates):
        base_score = norm_form[i] * 0.5 + norm_odds[i] * 0.5
        start_mult = _start_odds_multiplier(c["_start_odds"])
        fresh_mult = _freshness_multiplier(c.get("_latest_score_date"), reference_date)
        c["_start_mult"] = round(start_mult, 2)
        c["_fresh_mult"] = round(fresh_mult, 2)
        c["_score_reco"] = round(base_score * start_mult * fresh_mult, 1)

    # Exclude players with < 50% start odds or not in form (wL5/L40 < 1)
    candidates = [c for c in candidates if c.get("_start_mult", 1) > 0]
    candidates = [c for c in candidates if c.get("_form", 0) >= 1.0]
    candidates.sort(key=lambda x: x.get("_score_reco", 0), reverse=True)
    return candidates


# ── data loading ────────────────────────────────────────────────────────────

def _load_all_players(league_cfg, licensed_teams, api_key, progress_bar, progress_offset, progress_total):
    """Fetch players+scores for every team in a league. Returns flat list."""
    team_slugs = licensed_teams.get(league_cfg["licensed_teams_key"], [])
    all_players = []
    for i, slug in enumerate(team_slugs):
        try:
            players = fetch_team_players_with_scores(slug, api_key)
            for p in players:
                # Skip players who transferred away
                active_slug = (p.get("activeClub") or {}).get("slug", "")
                if active_slug and active_slug != slug:
                    continue
                p["_team_slug"] = slug
                p["_league"] = league_cfg["name"]
                all_players.append(p)
        except Exception as e:
            st.warning(f"Erreur chargement {slug}: {e}")
        if progress_total > 0:
            progress_bar.progress(min((progress_offset + i + 1) / progress_total, 1.0))
    return all_players


def _load_injuries_for_dates(league_cfg, all_dates, api_key):
    """Fetch injuries across multiple dates.
    Track first/last date each player appears as injured.
    A player is 'new' if they appear on the latest dates but NOT on the earliest."""
    # Track per-player: first seen date, last seen date, injury data
    player_dates = {}  # name → {"first": date, "last": date, "inj": inj_data}
    sorted_dates = sorted(all_dates)
    for d in sorted_dates:
        try:
            injuries = fetch_injuries(
                league_cfg["api_football_id"],
                league_cfg["season"],
                d,
                api_key,
            )
            for inj in injuries:
                name = inj.get("player", {}).get("name", "")
                if not name:
                    continue
                if name not in player_dates:
                    player_dates[name] = {"first": d, "last": d, "inj": inj}
                else:
                    player_dates[name]["last"] = d
        except Exception as e:
            st.warning(f"Erreur blessures {league_cfg['name']} ({d}): {e}")

    if not player_dates:
        st.caption(f"{league_cfg['name']}: donnees blessures indisponibles via API-Football")

    # Split dates into "old" (first week) and "recent" (last 3 days)
    mid_date = sorted_dates[7] if len(sorted_dates) > 7 else sorted_dates[0]
    recent_cutoff = sorted_dates[-4] if len(sorted_dates) > 3 else sorted_dates[0]

    new_injuries = []
    for name, info in player_dates.items():
        # New injury = first appeared AFTER the first week
        # (players injured from day 1 are long-term, not new)
        if info["first"] <= mid_date:
            continue
        inj = info["inj"]
        inj["_sidelined_start"] = info["first"]
        inj["_last_seen"] = info["last"]
        # Still active if last seen on a recent date
        inj["_still_active"] = info["last"] >= recent_cutoff
        new_injuries.append(inj)

    return new_injuries


def _load_substitutions_and_lineups(league_cfg, dates, api_key):
    """Fetch fixtures + events + lineups across multiple dates.
    Returns (subs_list, lineups_by_team_name, red_cards, fixture_dates)."""
    subs = []
    red_cards = []
    fixture_dates = set()  # all dates that had fixtures
    # lineups_by_team: {"Team Name": [{"name": ..., "pos": "D"}, ...]}
    lineups_by_team = {}
    seen_fixtures = set()
    for d in dates:
        try:
            fixtures = fetch_fixtures_by_date(
                league_cfg["api_football_id"],
                league_cfg["season"],
                d,
                api_key,
            )
        except Exception as e:
            st.warning(f"Erreur fixtures {league_cfg['name']} ({d}): {e}")
            continue

        for fix in fixtures:
            fixture_id = fix.get("fixture", {}).get("id")
            if not fixture_id or fixture_id in seen_fixtures:
                continue
            seen_fixtures.add(fixture_id)
            fixture_dates.add(d)

            # Events (substitutions + red cards)
            try:
                events = fetch_fixture_events(fixture_id, api_key)
            except Exception as e:
                st.warning(f"Erreur events fixture {fixture_id}: {e}")
                events = []

            # Lineups (starting XI)
            try:
                lineup_data = fetch_fixture_lineups(fixture_id, api_key)
                for team_lineup in lineup_data:
                    team_name = team_lineup.get("team", {}).get("name", "")
                    if not team_name:
                        continue
                    starters = []
                    for entry in team_lineup.get("startXI", []):
                        p = entry.get("player", {})
                        starters.append({
                            "name": p.get("name", ""),
                            "id": p.get("id"),
                            "pos": p.get("pos", ""),  # G, D, M, F
                        })
                    # Keep only the most recent lineup per team (dates are sorted ascending)
                    lineups_by_team[team_name] = {
                        "starters": starters,
                        "_league": league_cfg["name"],
                        "_date": d,
                    }
            except Exception as e:
                st.warning(f"Erreur lineups fixture {fixture_id}: {e}")

            for ev in events:
                ev_type = ev.get("type")
                team_info = ev.get("team", {})

                if ev_type == "subst":
                    player_out = ev.get("player", {})
                    player_in = ev.get("assist", {})
                    subs.append({
                        "player_out_name": player_out.get("name") or "?",
                        "player_out_id": player_out.get("id"),
                        "player_in_name": player_in.get("name") or "?",
                        "player_in_id": player_in.get("id"),
                        "team_name": team_info.get("name") or "?",
                        "team_id": team_info.get("id"),
                        "minute": int(ev.get("time", {}).get("elapsed") or 0),
                        "fixture_id": fixture_id,
                        "_league": league_cfg["name"],
                    })

                elif ev_type == "Card" and ev.get("detail") in ("Red Card", "Second Yellow card"):
                    player_info = ev.get("player", {})
                    player_name = player_info.get("name") or "?"
                    t_name = team_info.get("name") or "?"
                    red_cards.append({
                        "player_name": player_name,
                        "team_name": t_name,
                        "minute": int(ev.get("time", {}).get("elapsed") or 0),
                        "fixture_id": fixture_id,
                        "_date": d,
                        "_league": league_cfg["name"],
                    })

    return subs, lineups_by_team, red_cards, fixture_dates


# ── secrets helper ──────────────────────────────────────────────────────────

def _get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, "")


# ── page ────────────────────────────────────────────────────────────────────

st.header("League Monitor")

_default_sorare = _get_secret("SORARE_API_KEY")
_default_af = _get_secret("API_FOOTBALL_KEY")
_default_odds = _get_secret("ODDS_API_KEY")
with st.sidebar:
    sorare_key = st.text_input("Sorare API Key", value=_default_sorare, type="password")
    af_key = st.text_input("API-Football Key", value=_default_af, type="password")
    odds_key = st.text_input("The Odds API Key", value=_default_odds, type="password")
    si_key = st.text_input("SorareInside API Key", value=_get_secret("SORAREINSIDE_API_KEY"), type="password")
    selected_date = st.date_input("Date analyse (lundi)", value=_last_monday(), key="lm_date")

    # Auto-compute 3 weeks range (all days, not just weekends)
    earliest = selected_date - timedelta(days=21)  # 3 full weeks back from Monday
    all_days = [earliest + timedelta(days=i) for i in range((selected_date - earliest).days + 1)]
    st.caption(f"Blessures : {earliest.strftime('%d/%m')} — {selected_date.strftime('%d/%m')} (3 sem.) · Cartons rouges GK : derniere journee")

    st.divider()
    uploaded_csv = st.file_uploader("Player Extract CSV", type="csv", key="lm_csv_upload")
    if uploaded_csv is not None:
        try:
            df_supply = pd.read_csv(uploaded_csv)
            if "sport" in df_supply.columns:
                df_supply = df_supply[df_supply["sport"] == "football"]
            if "player_slug" in df_supply.columns:
                df_supply = df_supply.drop_duplicates(subset="player_slug", keep="last")
                st.session_state["lm_supply"] = df_supply.set_index("player_slug").to_dict("index")
                st.caption(f"{len(st.session_state['lm_supply'])} joueurs charges")
            else:
                st.error("Colonne 'player_slug' introuvable dans le CSV.")
                st.session_state.pop("lm_supply", None)
        except Exception as e:
            st.error(f"Erreur lecture CSV: {e}")
            st.session_state.pop("lm_supply", None)

config = _load_json("league_monitor_config.json")
league_names = [lg["name"] for lg in config["leagues"]]
overrides = config.get("team_name_overrides", {})

selected_leagues = st.multiselect("Ligues", league_names, default=league_names)
selected_cfgs = [lg for lg in config["leagues"] if lg["name"] in selected_leagues]

if st.button("Charger", type="primary"):
    if not sorare_key:
        st.error("Sorare API Key requise.")
        st.stop()
    if not af_key:
        st.error("API-Football Key requise.")
        st.stop()
    if not selected_cfgs:
        st.warning("Selectionnez au moins une ligue.")
        st.stop()

    licensed_teams = _load_json("licensed_teams.json")

    # All dates across 3 weeks
    query_dates = sorted(set(d.strftime("%Y-%m-%d") for d in all_days))
    # Count total work for progress bar
    total_teams = sum(
        len(licensed_teams.get(c["licensed_teams_key"], []))
        for c in selected_cfgs
    )
    n_leagues = len(selected_cfgs)
    # injuries (n_leagues steps) + subs (n_leagues steps) + teams
    total_work = total_teams + n_leagues * 2

    progress = st.progress(0)

    # Fetch injuries (across weekend) — filtered by sidelined start date
    all_injuries = []
    for i, cfg in enumerate(selected_cfgs):
        injuries = _load_injuries_for_dates(cfg, query_dates, af_key)
        for inj in injuries:
            inj["_league"] = cfg["name"]
        all_injuries.extend(injuries)
        progress.progress(min((i + 1) / total_work, 1.0))

    # Fetch substitutions + lineups + red cards (across 3 weeks)
    all_subs = []
    all_lineups = {}  # team_name → {starters, _league}
    all_red_cards = []
    all_fixture_dates = set()
    for i, cfg in enumerate(selected_cfgs):
        subs, lineups, red_cards, fx_dates = _load_substitutions_and_lineups(cfg, query_dates, af_key)
        all_subs.extend(subs)
        all_lineups.update(lineups)
        all_red_cards.extend(red_cards)
        all_fixture_dates.update(fx_dates)
        progress.progress(min((n_leagues + i + 1) / total_work, 1.0))

    # Compute last matchday: most recent fixture date + nearby dates (within 3 days)
    if all_fixture_dates:
        sorted_dates = sorted(all_fixture_dates, reverse=True)
        latest = sorted_dates[0]
        last_matchday = {latest}
        for d in sorted_dates[1:]:
            if (date.fromisoformat(latest) - date.fromisoformat(d)).days <= 3:
                last_matchday.add(d)
            else:
                break
    else:
        last_matchday = set()

    # Fetch Sorare players
    all_players = []
    offset = n_leagues * 2
    for cfg in selected_cfgs:
        players = _load_all_players(cfg, licensed_teams, sorare_key, progress, offset, total_work)
        all_players.extend(players)
        offset += len(licensed_teams.get(cfg["licensed_teams_key"], []))

    # Fetch win probabilities from The Odds API (bookmaker odds)
    team_predictions = {}  # team_name → win_probability (%)
    upcoming_matches = []  # list of match dicts for display

    n_fixtures_pred = 0
    if odds_key:
        for cfg in selected_cfgs:
            sport_key = cfg.get("odds_api_sport")
            if not sport_key:
                continue
            try:
                matches = fetch_odds(sport_key, odds_key)
                # Sort by date so first match per team wins
                sorted_matches = sorted(matches, key=lambda x: x.get("commence_time", ""))
                for m in sorted_matches:
                    home = m["home_team"]
                    away = m["away_team"]
                    # Keep first (nearest) match per team
                    if home not in team_predictions:
                        team_predictions[home] = m["home_pct"]
                    if away not in team_predictions:
                        team_predictions[away] = m["away_pct"]
                    n_fixtures_pred += 1

                    commence = m.get("commence_time", "")
                    upcoming_matches.append({
                        "Ligue": cfg["name"],
                        "Date": commence[:16].replace("T", " ") if commence else "",
                        "Domicile": home,
                        "% Dom": f"{m['home_pct']:.0f}%",
                        "Nul": f"{m['draw_pct']:.0f}%",
                        "% Ext": f"{m['away_pct']:.0f}%",
                        "Exterieur": away,
                    })
            except Exception as e:
                st.warning(f"Erreur odds {cfg['name']}: {e}")

    if n_fixtures_pred > 0:
        st.caption(f"Probas chargees pour {n_fixtures_pred} matchs via bookmakers ({len(team_predictions)} equipes)")
    else:
        st.caption("Aucune proba chargee (cle Odds API manquante ou pas de matchs a venir)")

    # Fetch start odds from SorareInside
    # Find the fixture containing the next games for the selected leagues
    start_odds_lookup = {}
    if si_key:
        try:
            # Map licensed_teams_key to Sorare competition slugs
            comp_slug_map = {
                "J1 100 Year Vision League": "j1-100-year-vision-league",
                "K League 1": "k-league-1",
                "Major League Soccer": "mlspa",
            }
            target_comp_slugs = set()
            for cfg in selected_cfgs:
                cs = comp_slug_map.get(cfg["licensed_teams_key"])
                if cs:
                    target_comp_slugs.add(cs)

            if target_comp_slugs:
                # Find the fixture with the most games from our leagues
                # (fixtures are returned future-first, so reverse to check nearest first)
                fixtures = fetch_fixtures(api_key=sorare_key, count=5)
                best_fx_slug = ""
                best_game_ids = []
                for fx in reversed(fixtures):
                    fx_data = fetch_fixture_games(fx["slug"], api_key=sorare_key)
                    fx_game_ids = []
                    for g in fx_data.get("games", []):
                        comp_slug = (g.get("competition") or {}).get("slug", "")
                        if comp_slug in target_comp_slugs:
                            gid = (g.get("id") or "").replace("Game:", "")
                            if gid:
                                fx_game_ids.append(gid)
                    if len(fx_game_ids) > len(best_game_ids):
                        best_game_ids = fx_game_ids
                        best_fx_slug = fx["slug"]
                target_game_ids = best_game_ids
                if target_game_ids:
                    st.caption(f"SorareInside: {len(target_game_ids)} matchs trouves dans {best_fx_slug}")

                if target_game_ids:
                    start_odds_lookup = fetch_start_odds(target_game_ids, si_key)
                    st.caption(f"Titularisation chargee pour {len(start_odds_lookup)} joueurs via SorareInside")
        except Exception as e:
            st.warning(f"Erreur SorareInside: {e}")

    progress.empty()

    st.session_state["lm_injuries"] = all_injuries
    st.session_state["lm_subs"] = all_subs
    st.session_state["lm_lineups"] = all_lineups
    st.session_state["lm_players"] = all_players
    st.session_state["lm_red_cards"] = all_red_cards
    st.session_state["lm_last_matchday"] = last_matchday
    st.session_state["lm_predictions"] = team_predictions
    st.session_state["lm_upcoming"] = upcoming_matches
    st.session_state["lm_start_odds"] = start_odds_lookup
    st.session_state["lm_loaded"] = True

# ── Display tabs ────────────────────────────────────────────────────────────

if st.session_state.get("lm_loaded"):
    all_injuries = st.session_state["lm_injuries"]
    all_subs = st.session_state["lm_subs"]
    all_lineups = st.session_state.get("lm_lineups", {})
    all_players = st.session_state["lm_players"]
    all_red_cards = st.session_state.get("lm_red_cards", [])
    last_matchday = st.session_state.get("lm_last_matchday", set())
    raw_predictions = st.session_state.get("lm_predictions", {})
    supply_lookup = st.session_state.get("lm_supply", {})
    licensed_teams = _load_json("licensed_teams.json")
    has_supply = bool(supply_lookup)
    staleness_cutoff = selected_date - timedelta(days=STALENESS_DAYS)
    predictions = _build_predictions_lookup(raw_predictions, all_players, licensed_teams, config, overrides)

    # Build player lookup by team (shared across tabs)
    players_by_team = {}
    for p in all_players:
        players_by_team.setdefault(p.get("_team_slug", ""), []).append(p)

    # Build slug-keyed start odds lookup (used for U23 filtering and reco scoring)
    _raw_start_odds = st.session_state.get("lm_start_odds", {})
    _uuid_to_slug = {}
    for p in all_players:
        pid = (p.get("id") or "").replace("Player:", "")
        if pid and p.get("slug"):
            _uuid_to_slug[pid] = p["slug"]
    slug_start_odds = {_uuid_to_slug[uid]: odds for uid, odds in _raw_start_odds.items() if uid in _uuid_to_slug}

    # ── Helper: find replacement for an injured player ──────────────────

    def _find_replacement(inj_name, team_name, league_name, position_filter=None):
        """Find replacement for an injured/expelled player.
        Returns (replacement_name, replacement_slug, fiabilite)."""
        replacement = ""
        replacement_slug = ""
        fiabilite = ""
        cfg = next((c for c in config["leagues"] if c["name"] == league_name), None)
        if not cfg:
            return replacement, replacement_slug, fiabilite

        league_slugs = licensed_teams.get(cfg["licensed_teams_key"], [])
        sorare_team_slug = _match_team_to_sorare(team_name, league_slugs, overrides)
        team_players = players_by_team.get(sorare_team_slug, [])

        # Method 1: confirmed sub (must match league AND team)
        inj_normalized = _normalize(inj_name)
        team_normalized = _normalize(team_name)
        for sub in all_subs:
            if sub["_league"] != league_name:
                continue
            if _normalize(sub.get("team_name", "")) != team_normalized:
                continue
            sub_out_normalized = _normalize(sub["player_out_name"])
            if inj_normalized == sub_out_normalized:
                replacement = sub["player_in_name"]
                fiabilite = "Confirme"
                break
            # Fallback: last-name match — require BOTH last names to match AND have 4+ chars
            inj_words = inj_normalized.split()
            sub_words = sub_out_normalized.split()
            if (inj_words and sub_words
                    and len(inj_words[-1]) >= 4
                    and inj_words[-1] == sub_words[-1]):
                replacement = sub["player_in_name"]
                fiabilite = "Confirme"
                break

        # Method 2: probable (lineup-based) if no confirmed sub
        if not replacement and team_players:
            sorare_injured = _match_player_name(inj_name, team_players)
            if sorare_injured:
                inj_position = sorare_injured.get("position", "")
                af_pos = _POS_REVERSE.get(inj_position, "")
                if position_filter:
                    af_pos = position_filter
                if af_pos:
                    lineup_info = all_lineups.get(team_name)
                    if lineup_info:
                        inj_scores = _extract_scores(sorare_injured)
                        inj_starts = sum(1 for s in inj_scores[:10] if s["score"] > 0)
                        if inj_starts >= 3:
                            same_pos = [s for s in lineup_info["starters"] if s["pos"] == af_pos]
                            best_conf = 0
                            for starter in same_pos:
                                sr = _match_player_name(starter["name"], team_players)
                                if not sr or sr["slug"] == sorare_injured["slug"]:
                                    continue
                                sr_starts = sum(1 for s in _extract_scores(sr)[:10] if s["score"] > 0)
                                conf = inj_starts - sr_starts
                                if conf > best_conf:
                                    best_conf = conf
                                    replacement = starter["name"]
                                    fiabilite = "Probable"

        # Resolve slug for replacement
        if replacement and team_players:
            matched_repl = _match_player_name(replacement, team_players)
            if matched_repl:
                replacement_slug = matched_repl.get("slug", "")

        return replacement, replacement_slug, fiabilite

    # ══════════════════════════════════════════════════════════════════════
    # Phase 1: Collect all data & reco candidates BEFORE rendering tabs
    # ══════════════════════════════════════════════════════════════════════

    reco_candidates = []

    # ── Injured players data (non-GK) ──────────────────────────────────
    injury_rows = []
    for inj in all_injuries:
        player = inj.get("player", {})
        team = inj.get("team", {})
        inj_name = player.get("name") or "?"
        team_name = team.get("name") or "?"
        league_name = inj["_league"]

        # Check if GK → skip (goes to GK tab)
        cfg = next((c for c in config["leagues"] if c["name"] == league_name), None)
        is_gk = False
        inj_slug = ""
        if cfg:
            league_slugs = licensed_teams.get(cfg["licensed_teams_key"], [])
            sorare_team_slug = _match_team_to_sorare(team_name, league_slugs, overrides)
            team_players = players_by_team.get(sorare_team_slug, [])
            matched = _match_player_name(inj_name, team_players)
            if matched:
                inj_slug = matched.get("slug", "")
                if matched.get("position") == "Goalkeeper":
                    is_gk = True
        if is_gk:
            continue

        # Skip long-term injuries: if injured player has 0 starts in L10, replacement is already established
        inj_is_longterm = False
        if matched:
            inj_starts = sum(1 for s in _extract_scores(matched)[:10] if s["score"] > 0)
            inj_is_longterm = inj_starts == 0

        replacement, repl_slug, fiabilite = _find_replacement(inj_name, team_name, league_name)

        # Only recommend replacement if:
        # - injured player is not a long-term absence (replacement already established)
        # - replacement is not already a regular starter (< 5 starts in L10)
        skip_reco = inj_is_longterm
        if not skip_reco and repl_slug:
            repl_player = next((tp for tp in players_by_team.get(sorare_team_slug, []) if tp.get("slug") == repl_slug), None)
            if repl_player:
                repl_starts = sum(1 for s in _extract_scores(repl_player)[:10] if s["score"] > 0)
                skip_reco = repl_starts >= 5

        if repl_slug and not skip_reco:
            reco_candidates.append({
                "slug": repl_slug,
                "player_name": replacement,
                "team_name": team_name,
                "position": "",
                "raison": f"Remplacant blesse ({fiabilite.lower()})",
                "_league": league_name,
            })

        statut = "Actif" if inj.get("_still_active") else "Retour ?"
        injury_rows.append({
            "Ligue": league_name,
            "Joueur": inj_name,
            "Slug": inj_slug,
            "Equipe": team_name,
            "Type": player.get("type", ""),
            "Raison": player.get("reason", ""),
            "Depuis": inj.get("_sidelined_start", ""),
            "Statut": statut,
            "Remplacant": replacement,
            "_repl_slug": repl_slug,
            "Fiabilite": fiabilite,
        })

    # ── GK data (injured + red cards) ──────────────────────────────────
    gk_rows = []

    for inj in all_injuries:
        player = inj.get("player", {})
        team = inj.get("team", {})
        inj_name = player.get("name") or "?"
        team_name = team.get("name") or "?"
        league_name = inj["_league"]

        cfg = next((c for c in config["leagues"] if c["name"] == league_name), None)
        if not cfg:
            continue
        league_slugs = licensed_teams.get(cfg["licensed_teams_key"], [])
        sorare_team_slug = _match_team_to_sorare(team_name, league_slugs, overrides)
        team_players = players_by_team.get(sorare_team_slug, [])
        matched = _match_player_name(inj_name, team_players)
        if not matched or matched.get("position") != "Goalkeeper":
            continue

        other_gks = [tp for tp in team_players if tp.get("position") == "Goalkeeper" and tp.get("slug") != matched.get("slug")]
        replacement_name = ""
        replacement_slug = ""
        if other_gks:
            best_gk = max(other_gks, key=lambda g: sum(1 for s in _extract_scores(g)[:10] if s["score"] > 0))
            replacement_name = _player_display_name(best_gk)
            replacement_slug = best_gk.get("slug", "")

        repl_gk_is_regular = False
        if replacement_slug and other_gks:
            repl_gk = next((g for g in other_gks if g.get("slug") == replacement_slug), None)
            if repl_gk:
                repl_gk_starts = sum(1 for s in _extract_scores(repl_gk)[:10] if s["score"] > 0)
                repl_gk_is_regular = repl_gk_starts >= 5

        if replacement_slug and not repl_gk_is_regular:
            reco_candidates.append({
                "slug": replacement_slug,
                "player_name": replacement_name,
                "team_name": team_name,
                "position": "Goalkeeper",
                "raison": "Remplacant GK (blessure)",
                "_league": league_name,
            })

        statut = "Actif" if inj.get("_still_active") else "Retour ?"
        gk_rows.append({
            "Ligue": league_name,
            "Gardien": inj_name,
            "Slug": matched.get("slug", ""),
            "Equipe": team_name,
            "Cause": "Blessure",
            "Detail": player.get("reason", ""),
            "Depuis": inj.get("_sidelined_start", ""),
            "Statut": statut,
            "Remplacant GK": replacement_name,
            "_repl_slug": replacement_slug,
        })

    for rc in all_red_cards:
        if rc.get("_date") not in last_matchday:
            continue
        league_name = rc["_league"]
        team_name = rc["team_name"]
        cfg = next((c for c in config["leagues"] if c["name"] == league_name), None)
        if not cfg:
            continue

        league_slugs = licensed_teams.get(cfg["licensed_teams_key"], [])
        sorare_team_slug = _match_team_to_sorare(team_name, league_slugs, overrides)
        team_players = players_by_team.get(sorare_team_slug, [])

        matched = _match_player_name(rc["player_name"], team_players)
        if not matched or matched.get("position") != "Goalkeeper":
            continue

        replacement_name = "—"
        replacement_slug = ""
        first_sub_in = ""
        rc_minute = rc.get("minute") or 0
        for sub in all_subs:
            if sub.get("fixture_id") != rc["fixture_id"]:
                continue
            if sub["team_name"] != rc["team_name"]:
                continue
            sub_minute = sub.get("minute") or 0
            if sub_minute < rc_minute:
                continue
            if not first_sub_in:
                first_sub_in = sub["player_in_name"]
            sub_match = _match_player_name(sub["player_in_name"], team_players)
            if sub_match and sub_match.get("position") == "Goalkeeper":
                replacement_name = _player_display_name(sub_match)
                replacement_slug = sub_match.get("slug", "")
                break

        if replacement_name == "—" and first_sub_in:
            fallback_match = _match_player_name(first_sub_in, team_players)
            if fallback_match:
                replacement_name = _player_display_name(fallback_match)
                replacement_slug = fallback_match.get("slug", "")
            else:
                replacement_name = first_sub_in

        rc_repl_is_regular = False
        if replacement_slug:
            rc_repl = next((tp for tp in team_players if tp.get("slug") == replacement_slug), None)
            if rc_repl:
                rc_repl_starts = sum(1 for s in _extract_scores(rc_repl)[:10] if s["score"] > 0)
                rc_repl_is_regular = rc_repl_starts >= 5

        if replacement_slug and not rc_repl_is_regular:
            reco_candidates.append({
                "slug": replacement_slug,
                "player_name": replacement_name,
                "team_name": team_name,
                "position": "Goalkeeper",
                "raison": "Remplacant GK (carton rouge)",
                "_league": league_name,
            })

        gk_rows.append({
            "Ligue": league_name,
            "Gardien": rc["player_name"],
            "Slug": matched.get("slug", ""),
            "Equipe": team_name,
            "Cause": "Carton rouge",
            "Detail": f"Min. {rc['minute']}",
            "Depuis": rc.get("_date", ""),
            "Statut": "Suspendu",
            "Remplacant GK": replacement_name,
            "_repl_slug": replacement_slug,
        })

    # ── U23 data ───────────────────────────────────────────────────────
    u23_rows = []
    for p in all_players:
        if (p.get("age") or 99) > 23:
            continue
        scores = _extract_scores(p)
        if len(scores) < 1:
            continue
        latest_score = scores[0]["score"]
        latest_date = _parse_score_date(scores[0]["date"])
        if latest_score <= 0:
            continue
        prev_scores = [s["score"] for s in scores[1:U23_PREV_WINDOW + 1]]
        if any(s > 0 for s in prev_scores):
            continue
        slug = p.get("slug", "")
        club = p.get("activeClub") or {}
        team_name = club.get("name") or p.get("_team_slug", "")

        # Check start odds: skip U23 with < 50% chance of starting
        u23_start_odds = slug_start_odds.get(slug)
        if u23_start_odds is not None and u23_start_odds < 0.5:
            continue

        u23_rows.append({
            "Joueur": _player_display_name(p),
            "Slug": slug,
            "Ligue": p.get("_league", ""),
            "Equipe": team_name,
            "Age": p.get("age", ""),
            "Position": p.get("position", ""),
            "Score": round(latest_score, 1),
            "Dernier match": latest_date.strftime("%d/%m/%Y") if latest_date else "?",
            "_slug": slug,
            "_recent": latest_date is not None and latest_date >= staleness_cutoff,
        })
        reco_candidates.append({
            "slug": slug,
            "player_name": _player_display_name(p),
            "team_name": team_name,
            "position": p.get("position", ""),
            "raison": "Nouveau U23",
            "_league": p.get("_league", ""),
        })

    u23_rows.sort(key=lambda x: x["Score"], reverse=True)

    # ── Boosted data ───────────────────────────────────────────────────
    boosted_rows = []
    seen_boosted = set()
    for p in all_players:
        slug = p.get("slug", "")
        if slug in seen_boosted:
            continue
        scores = _extract_scores(p)
        if not scores:
            continue
        latest = scores[0]["score"]
        latest_date = _parse_score_date(scores[0]["date"])
        avg10 = _avg(scores, 10)
        if latest > BOOSTED_MIN_SCORE and latest >= avg10 + BOOSTED_MIN_DELTA:
            seen_boosted.add(slug)
            club = p.get("activeClub") or {}
            team_name = club.get("name") or p.get("_team_slug", "")
            boosted_rows.append({
                "Joueur": _player_display_name(p),
                "Slug": slug,
                "Ligue": p.get("_league", ""),
                "Equipe": team_name,
                "Position": p.get("position", ""),
                "Dernier Score": round(latest, 1),
                "Moy L10": round(avg10, 1),
                "Delta": f"+{round(latest - avg10, 1)}",
                "Dernier match": latest_date.strftime("%d/%m/%Y") if latest_date else "?",
                "_slug": slug,
                "_recent": latest_date is not None and latest_date >= staleness_cutoff,
            })
            reco_candidates.append({
                "slug": slug,
                "player_name": _player_display_name(p),
                "team_name": team_name,
                "position": p.get("position", ""),
                "raison": "Boosted",
                "_league": p.get("_league", ""),
            })

    boosted_rows.sort(key=lambda x: x["Dernier Score"], reverse=True)

    # ── Reduced data ───────────────────────────────────────────────────
    reduced_rows = []
    seen_reduced = set()
    for p in all_players:
        slug = p.get("slug", "")
        if slug in seen_reduced:
            continue
        scores = _extract_scores(p)
        if not scores:
            continue
        latest = scores[0]["score"]
        latest_date = _parse_score_date(scores[0]["date"])
        avg10 = _avg(scores, 10)
        if avg10 > REDUCED_MIN_AVG and latest <= avg10 - REDUCED_MIN_DELTA:
            seen_reduced.add(slug)
            club = p.get("activeClub") or {}
            reduced_rows.append({
                "Joueur": _player_display_name(p),
                "Slug": slug,
                "Ligue": p.get("_league", ""),
                "Equipe": club.get("name") or p.get("_team_slug", ""),
                "Position": p.get("position", ""),
                "Dernier Score": round(latest, 1),
                "Moy L10": round(avg10, 1),
                "Delta": round(latest - avg10, 1),
                "Dernier match": latest_date.strftime("%d/%m/%Y") if latest_date else "?",
                "_recent": latest_date is not None and latest_date >= staleness_cutoff,
            })

    reduced_rows.sort(key=lambda x: x["Dernier Score"])

    # ══════════════════════════════════════════════════════════════════════
    # Phase 2: Compute reco scores for ALL players in supply CSV
    # ══════════════════════════════════════════════════════════════════════

    # Build raison lookup from special candidates (merge multiple reasons)
    raison_by_slug = {}
    for c in reco_candidates:
        if c["slug"]:
            existing = raison_by_slug.get(c["slug"], "")
            if not existing:
                raison_by_slug[c["slug"]] = c["raison"]
            elif c["raison"] not in existing:
                raison_by_slug[c["slug"]] = f"{existing} + {c['raison']}"

    # Build full candidate list: every player in selected leagues that's in the CSV
    all_reco = []
    seen_reco_slugs = set()
    for p in all_players:
        slug = p.get("slug", "")
        if not slug or slug in seen_reco_slugs or slug not in supply_lookup:
            continue
        seen_reco_slugs.add(slug)
        club = p.get("activeClub") or {}
        all_reco.append({
            "slug": slug,
            "player_name": _player_display_name(p),
            "team_name": club.get("name") or p.get("_team_slug", ""),
            "position": p.get("position", ""),
            "raison": raison_by_slug.get(slug, "—"),
            "_league": p.get("_league", ""),
        })

    score_by_slug = {}
    start_odds_lookup = st.session_state.get("lm_start_odds", {})
    if has_supply and all_reco:
        all_reco = _compute_reco_scores(all_reco, supply_lookup, predictions, start_odds_lookup, selected_date)
        for c in all_reco:
            score_by_slug[c["slug"]] = c.get("_score_reco", 0)

    # ══════════════════════════════════════════════════════════════════════
    # Phase 3: Render tabs with scores
    # ══════════════════════════════════════════════════════════════════════

    upcoming_matches = st.session_state.get("lm_upcoming", [])

    tab1, tab_gk, tab3, tab4, tab5, tab_matches, tab_reco, tab_reco_gk, tab_checks = st.tabs([
        "Joueurs Blesses",
        "Goalkeepers",
        "Nouveaux U23",
        "Boosted",
        "Reduced",
        "Prochains Matchs",
        "Reco Joueurs",
        "Reco GK",
        "Checks",
    ])

    # ── Tab 1: Injured Players ─────────────────────────────────────────

    with tab1:
        if not injury_rows:
            st.info("Aucun joueur blesse (hors gardiens) trouve sur la periode.")
        else:
            df = pd.DataFrame(injury_rows).sort_values("Depuis", ascending=False)
            if has_supply:
                df["Score reco"] = df["_repl_slug"].map(lambda s: score_by_slug.get(s, ""))
            df = df.drop(columns=["_repl_slug"])
            for league in df["Ligue"].unique():
                st.subheader(league)
                st.dataframe(
                    df[df["Ligue"] == league].drop(columns=["Ligue"]),
                    use_container_width=True,
                    hide_index=True,
                )

    # ── Tab GK: Goalkeepers ────────────────────────────────────────────

    with tab_gk:
        if not gk_rows:
            st.info("Aucun gardien blesse ou expulse.")
        else:
            df_gk = pd.DataFrame(gk_rows)
            if has_supply:
                df_gk["Score reco"] = df_gk["_repl_slug"].map(lambda s: score_by_slug.get(s, ""))
            df_gk = df_gk.drop(columns=["_repl_slug"])
            for league in df_gk["Ligue"].unique():
                st.subheader(league)
                st.dataframe(
                    df_gk[df_gk["Ligue"] == league].drop(columns=["Ligue"]),
                    use_container_width=True,
                    hide_index=True,
                )

    # ── Tab 3: New U23 ─────────────────────────────────────────────────

    with tab3:
        if not u23_rows:
            st.info("Aucun nouveau joueur U23 detecte.")
        else:
            n_stale = sum(1 for r in u23_rows if not r.get("_recent", True))
            if n_stale:
                st.warning(f"{n_stale} joueur(s) avec dernier match > {STALENESS_DAYS}j — donnees potentiellement obsoletes")
            df_u23 = pd.DataFrame(u23_rows)
            if has_supply:
                df_u23["Score reco"] = df_u23["_slug"].map(lambda s: score_by_slug.get(s, ""))
            df_u23 = df_u23.drop(columns=["_slug", "_recent"])
            st.dataframe(df_u23, use_container_width=True, hide_index=True)

    # ── Tab 4: Boosted Players ─────────────────────────────────────────

    with tab4:
        if not boosted_rows:
            st.info("Aucun joueur boosted detecte.")
        else:
            n_stale = sum(1 for r in boosted_rows if not r.get("_recent", True))
            if n_stale:
                st.warning(f"{n_stale} joueur(s) avec dernier match > {STALENESS_DAYS}j — donnees potentiellement obsoletes")
            st.metric("Joueurs boosted", len(boosted_rows))
            df_boosted = pd.DataFrame(boosted_rows)
            if has_supply:
                df_boosted["Score reco"] = df_boosted["_slug"].map(lambda s: score_by_slug.get(s, ""))
            df_boosted = df_boosted.drop(columns=["_slug", "_recent"])
            st.dataframe(df_boosted, use_container_width=True, hide_index=True)

    # ── Tab 5: Reduced Players ─────────────────────────────────────────

    with tab5:
        if not reduced_rows:
            st.info("Aucun joueur reduced detecte.")
        else:
            n_stale = sum(1 for r in reduced_rows if not r.get("_recent", True))
            if n_stale:
                st.warning(f"{n_stale} joueur(s) avec dernier match > {STALENESS_DAYS}j — donnees potentiellement obsoletes")
            st.metric("Joueurs reduced", len(reduced_rows))
            df_reduced = pd.DataFrame(reduced_rows).drop(columns=["_recent"])
            st.dataframe(df_reduced, use_container_width=True, hide_index=True)

    # ── Tab Matches: Prochains Matchs ────────────────────────────────────

    with tab_matches:
        if not upcoming_matches:
            st.info("Aucun match a venir trouve (7 prochains jours).")
        else:
            df_matches = pd.DataFrame(upcoming_matches).sort_values("Date")
            for league in df_matches["Ligue"].unique():
                st.subheader(league)
                st.dataframe(
                    df_matches[df_matches["Ligue"] == league].drop(columns=["Ligue"]),
                    use_container_width=True,
                    hide_index=True,
                )

    # ── Tab Reco: Recommandations Joueurs ────────────────────────────

    reco_field = [c for c in all_reco if c.get("position") != "Goalkeeper"]
    reco_gk = [c for c in all_reco if c.get("position") == "Goalkeeper"]

    with tab_reco:
        if not has_supply:
            st.info("Uploadez un Player Extract CSV dans la sidebar pour activer les recommandations.")
        elif not reco_field:
            st.info("Aucun joueur de champ trouve.")
        else:
            top200 = reco_field[:200]
            reco_rows = []
            for c in top200:
                so = c.get("_start_odds")
                reco_rows.append({
                    "Joueur": c["player_name"],
                    "Slug": c.get("slug", ""),
                    "Equipe": c["team_name"],
                    "Position": c.get("position", ""),
                    "Raison": c["raison"],
                    "Forme": c.get("_form", ""),
                    "L5": c.get("_l5_avg", ""),
                    "L40": c.get("_l40_avg", ""),
                    "Proba victoire": f"{c['_win_prob']:.0f}%" if c.get("_win_prob") else "N/A",
                    "Titulaire %": f"{so * 100:.0f}%" if so is not None else "N/A",
                    "SR supply": c.get("_sr_supply", ""),
                    "U supply": c.get("_u_supply", ""),
                    "Score reco": c.get("_score_reco", 0),
                })
            st.metric("Top 200", f"{len(reco_rows)} / {len(reco_field)} joueurs de champ")
            st.dataframe(pd.DataFrame(reco_rows), use_container_width=True, hide_index=True)

    # ── Tab Reco GK: Recommandations Gardiens ────────────────────────

    with tab_reco_gk:
        if not has_supply:
            st.info("Uploadez un Player Extract CSV dans la sidebar pour activer les recommandations.")
        elif not reco_gk:
            st.info("Aucun gardien trouve.")
        else:
            # Flag "Nouveau titulaire GK": < 90 mins L5 + startOdds >= 50%
            new_starters = []
            regular_gk = []
            for c in reco_gk:
                so = c.get("_start_odds")
                mins = c.get("_mins_l5", 0)
                if mins < 90 and so is not None and so >= 0.5:
                    c["raison"] = "Nouveau titulaire GK"
                    new_starters.append(c)
                else:
                    regular_gk.append(c)

            # New starters on top, sorted by startOdds desc
            new_starters.sort(key=lambda x: x.get("_start_odds", 0), reverse=True)
            sorted_gk = new_starters + regular_gk

            def _gk_row(c):
                so = c.get("_start_odds")
                return {
                    "Joueur": c["player_name"],
                    "Slug": c.get("slug", ""),
                    "Equipe": c["team_name"],
                    "Raison": c["raison"],
                    "Min L5": c.get("_mins_l5", 0),
                    "Forme": c.get("_form", ""),
                    "L5": c.get("_l5_avg", ""),
                    "L40": c.get("_l40_avg", ""),
                    "Proba victoire": f"{c['_win_prob']:.0f}%" if c.get("_win_prob") else "N/A",
                    "Titulaire %": f"{so * 100:.0f}%" if so is not None else "N/A",
                    "SR supply": c.get("_sr_supply", ""),
                    "U supply": c.get("_u_supply", ""),
                    "Score reco": c.get("_score_reco", 0),
                }

            if new_starters:
                st.subheader(f"Nouveaux titulaires ({len(new_starters)})")
                st.dataframe(pd.DataFrame([_gk_row(c) for c in new_starters]), use_container_width=True, hide_index=True)

            st.subheader(f"Tous les gardiens ({len(sorted_gk)})")
            st.dataframe(pd.DataFrame([_gk_row(c) for c in sorted_gk]), use_container_width=True, hide_index=True)

    # ── Tab Checks: Sanity Checks ────────────────────────────────────

    with tab_checks:
        st.subheader("Verification des donnees")

        checks = []

        # 1. Config season check
        current_year = date.today().year
        season_issues = [cfg for cfg in selected_cfgs if cfg.get("season") and cfg["season"] != current_year]
        if season_issues:
            for cfg in season_issues:
                checks.append(("warning", f"Saison {cfg['name']}", f"Configuree a {cfg['season']}, annee courante {current_year}"))
        else:
            checks.append(("ok", "Saisons config", f"Toutes a {current_year}"))

        # 2. Players with no scores
        n_total = len(all_players)
        n_no_scores = sum(1 for p in all_players if not _extract_scores(p))
        if n_no_scores > 0:
            checks.append(("warning", "Joueurs sans scores", f"{n_no_scores}/{n_total} joueurs n'ont aucun score Sorare"))
        else:
            checks.append(("ok", "Scores joueurs", f"{n_total} joueurs tous avec scores"))

        # 3. Win probability coverage
        unique_teams = {p.get("_team_slug") for p in all_players if p.get("_team_slug")}
        teams_with_pred = sum(1 for t in unique_teams if predictions.get(t, 0) > 0)
        pct_pred = (teams_with_pred / len(unique_teams) * 100) if unique_teams else 0
        level = "ok" if pct_pred >= 80 else "warning"
        checks.append((level, "Probas victoire", f"{teams_with_pred}/{len(unique_teams)} equipes couvertes ({pct_pred:.0f}%)"))

        # 4. Start odds coverage (SorareInside)
        n_start_odds = len(_raw_start_odds)
        if n_start_odds == 0:
            checks.append(("warning", "Start odds", "Aucune donnee de titularisation chargee"))
        else:
            checks.append(("ok", "Start odds", f"{n_start_odds} joueurs avec proba titularisation"))

        # 5. SorareInside comp_slug_map coverage
        si_mapped = {"J1 100 Year Vision League", "K League 1", "Major League Soccer"}
        configured_keys = [cfg["licensed_teams_key"] for cfg in selected_cfgs]
        unmapped_si = [k for k in configured_keys if k not in si_mapped]
        if unmapped_si:
            checks.append(("warning", "SorareInside mapping", f"Ligues sans mapping start odds : {', '.join(unmapped_si)}"))
        else:
            checks.append(("ok", "SorareInside mapping", f"Toutes les ligues selectionnees sont mappees"))

        # 6. Injury matching rate
        total_inj = len(injury_rows) + len(gk_rows)
        matched_inj = sum(1 for r in injury_rows if r.get("Slug")) + sum(1 for r in gk_rows if r.get("Slug"))
        if total_inj > 0:
            pct_inj = matched_inj / total_inj * 100
            level = "ok" if pct_inj >= 80 else "warning"
            checks.append((level, "Matching blessures", f"{matched_inj}/{total_inj} blessures matchees sur Sorare ({pct_inj:.0f}%)"))
        else:
            checks.append(("ok", "Matching blessures", "Aucune blessure detectee"))

        # 7. Score freshness across all players
        stale_count = 0
        for p in all_players:
            sc = _extract_scores(p)
            if sc:
                d = _parse_score_date(sc[0]["date"])
                if d and d < staleness_cutoff:
                    stale_count += 1
        if stale_count > 0:
            checks.append(("warning", "Fraicheur scores", f"{stale_count}/{n_total} joueurs avec dernier match > {STALENESS_DAYS}j"))
        else:
            checks.append(("ok", "Fraicheur scores", f"Tous les joueurs ont joue recemment (< {STALENESS_DAYS}j)"))

        # 8. Unmatched Odds API teams
        unmatched_teams = []
        if raw_predictions:
            all_league_slugs = []
            for cfg in selected_cfgs:
                all_league_slugs.extend(licensed_teams.get(cfg["licensed_teams_key"], []))
            for team_name in raw_predictions:
                matched_slug = _match_team_to_sorare(team_name, all_league_slugs, overrides)
                if not matched_slug:
                    unmatched_teams.append(team_name)
            if unmatched_teams:
                checks.append(("warning", "Matching equipes Odds API", f"{len(unmatched_teams)}/{len(raw_predictions)} equipes non matchees"))
            else:
                checks.append(("ok", "Matching equipes Odds API", f"{len(raw_predictions)} equipes toutes matchees"))

        # Display all checks
        for level, label, detail in checks:
            icon = ":white_check_mark:" if level == "ok" else ":warning:"
            st.markdown(f"{icon} **{label}** — {detail}")

        # Detail: unmatched teams
        if unmatched_teams:
            with st.expander(f"Equipes non matchees ({len(unmatched_teams)})"):
                st.caption("Ces equipes de l'Odds API n'ont pas de correspondance Sorare. "
                           "Ajoutez-les dans team_name_overrides du config JSON.")
                for t in sorted(unmatched_teams):
                    st.code(f'"{t}": ""', language="json")
