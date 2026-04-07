import os
from pathlib import Path

import streamlit as st

# Load .env locally (ignored on cloud where file doesn't exist)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

st.set_page_config(page_title="Sorare Tools", layout="centered")


def _get_secret(key):
    """Read from st.secrets (Streamlit Cloud) or os.environ (.env local)."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, "")


# Pre-fill widget keys — works both locally (.env) and on cloud (st.secrets)
for widget_key, secret_key in [
    ("lm_sorare_key", "SORARE_API_KEY"),
    ("lm_af_key", "API_FOOTBALL_KEY"),
    ("lm_odds_key", "ODDS_API_KEY"),
    ("pp_sorare_key", "SORARE_API_KEY"),
    ("dl_sorare_key", "SORARE_API_KEY"),
]:
    val = _get_secret(secret_key)
    if val and not st.session_state.get(widget_key):
        st.session_state[widget_key] = val

mission_page = st.Page("pages/1_mission_generator.py", title="Mission Generator", icon=":material/edit_note:")
prize_pool_page = st.Page("pages/2_gw_prize_pool.py", title="GW Prize Pool", icon=":material/emoji_events:")
league_monitor_page = st.Page("pages/3_league_monitor.py", title="League Monitor", icon=":material/monitoring:")
deadlines_page = st.Page("pages/4_deadlines.py", title="Deadlines", icon=":material/schedule:")
promo_page = st.Page("pages/5_promo_generator.py", title="Promo Generator", icon=":material/sell:")

pg = st.navigation([mission_page, prize_pool_page, league_monitor_page, deadlines_page, promo_page])
pg.run()
