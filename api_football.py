import requests
import streamlit as st

API_FOOTBALL_URL = "https://v3.football.api-sports.io"  # v3


def _api_football_request(endpoint, params, api_key):
    headers = {"x-apisports-key": api_key}
    resp = requests.get(
        f"{API_FOOTBALL_URL}/{endpoint}",
        params=params,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors") and len(data["errors"]) > 0:
        errors = data["errors"]
        if isinstance(errors, dict):
            msg = next(iter(errors.values()))
        elif isinstance(errors, list):
            msg = errors[0]
        else:
            msg = str(errors)
        msg = str(msg).replace(api_key, "***") if api_key else str(msg)
        raise Exception(f"API-Football error: {msg}")
    return data.get("response", [])


@st.cache_data(ttl=86400)
def fetch_injuries(league_id, season, date_str, api_key):
    return _api_football_request(
        "injuries",
        {"league": league_id, "season": season, "date": date_str},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_fixtures_by_date(league_id, season, date_str, api_key):
    """Get all fixtures for a league on a given date."""
    return _api_football_request(
        "fixtures",
        {"league": league_id, "season": season, "date": date_str},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_fixture_events(fixture_id, api_key):
    """Get events (goals, subs, cards) for a fixture."""
    return _api_football_request(
        "fixtures/events",
        {"fixture": fixture_id},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_fixture_lineups(fixture_id, api_key):
    """Get lineups (starting XI + bench) for a fixture."""
    return _api_football_request(
        "fixtures/lineups",
        {"fixture": fixture_id},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_player_sidelined(player_id, api_key):
    """Get sidelined (injury history) for a player — includes start/end dates."""
    return _api_football_request(
        "sidelined",
        {"player": player_id},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_upcoming_fixtures(league_id, season, from_date, to_date, api_key):
    """Get upcoming fixtures for a league within a date range."""
    return _api_football_request(
        "fixtures",
        {"league": league_id, "season": season, "from": from_date, "to": to_date},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_predictions(fixture_id, api_key):
    """Get predictions for a fixture."""
    return _api_football_request(
        "predictions",
        {"fixture": fixture_id},
        api_key,
    )


@st.cache_data(ttl=86400)
def fetch_odds(sport_key, api_key):
    """Fetch h2h odds from The Odds API and return win probabilities per team.

    Returns dict: {home_team: {home_pct, draw_pct, away_pct, away_team}, ...}
    Each match produces two entries (one per team).
    """
    resp = requests.get(
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
        params={
            "apiKey": api_key,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
        },
        timeout=30,
    )
    resp.raise_for_status()
    events = resp.json()

    matches = []
    for event in events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        commence = event.get("commence_time", "")

        # Average odds across all bookmakers for stability
        home_odds_list, draw_odds_list, away_odds_list = [], [], []
        for bk in event.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        home_odds_list.append(outcome["price"])
                    elif outcome["name"] == away:
                        away_odds_list.append(outcome["price"])
                    elif outcome["name"] == "Draw":
                        draw_odds_list.append(outcome["price"])

        if not home_odds_list or not away_odds_list or not draw_odds_list:
            continue

        # Average decimal odds → implied probabilities → normalize (remove vig)
        avg_home = sum(home_odds_list) / len(home_odds_list)
        avg_draw = sum(draw_odds_list) / len(draw_odds_list)
        avg_away = sum(away_odds_list) / len(away_odds_list)

        imp_home = 1 / avg_home
        imp_draw = 1 / avg_draw
        imp_away = 1 / avg_away
        total = imp_home + imp_draw + imp_away

        home_pct = round(imp_home / total * 100, 1)
        draw_pct = round(imp_draw / total * 100, 1)
        away_pct = round(imp_away / total * 100, 1)

        matches.append({
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "home_pct": home_pct,
            "draw_pct": draw_pct,
            "away_pct": away_pct,
        })

    return matches
