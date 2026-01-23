import streamlit as st
import pandas as pd
from src.ui_filters import render_sidebar_globals
from src.css import load_css
from src.bq_io import get_bq_client
from src.queries import get_total_matches_query, get_total_events_query, get_recent_matches_query

st.set_page_config(
    page_title="Prodigy.co Scouting",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load CSS Styles
load_css()

# Render Global Sidebar (Project Config)
globals_ = render_sidebar_globals()

# --- HERO SECTION ---
st.markdown("""
<div style="text-align: center; margin-bottom: 40px;">
    <h1 style="font-size: 3.5rem; margin-bottom: 0.5rem; background: linear-gradient(to right, #58a6ff, #238636); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        Prodigy.co Scouting
    </h1>
    <p style="font-size: 1.2rem; color: #8b949e;">High Performance Football Analytics Platform</p>
</div>
""", unsafe_allow_html=True)

# --- METRICS SECTION ---
# Fetch Metrics from BigQuery
# Default Params
PROJECT_ID = "prodigy-scouting-platform" # Hardcoded fallback or get from secrets via bq_io logic? 
# Actually get_bq_client handles auth, but we need project_id for string queries.
# Let's verify how we usually get it. In 1_eventos.py we hardcoded. Ideally we unify.
PROJECT_ID = "betterbet-448216" # FIXED based on user's known project id from previous context 
DATASET_ID = "events_data"

client = get_bq_client(project=PROJECT_ID)

# Use columns for layout
col1, col2, col3 = st.columns(3)

with col1:
    try:
        df_matches = client.query(get_total_matches_query(PROJECT_ID, DATASET_ID)).to_dataframe()
        total_matches = df_matches["total"].iloc[0]
        st.metric("Total de Partidas", total_matches)
    except Exception:
        st.metric("Total de Partidas", "--")

with col2:
    try:
        df_events = client.query(get_total_events_query(PROJECT_ID, DATASET_ID)).to_dataframe()
        total_events = df_events["total"].iloc[0]
        # Format millions/thousands
        if total_events > 1_000_000:
            fmt_events = f"{total_events/1_000_000:.2f}M"
        else:
            fmt_events = f"{total_events/1_000:.1f}K"
        st.metric("Eventos Registrados", fmt_events)
    except Exception:
        st.metric("Eventos Registrados", "--")

with col3:
    st.metric("Competições", "Brasileirão 2025") # Static for now

st.divider()

# --- NAVIGATION SECTION ---
st.subheader("Ferramentas de Análise")

nav_col1, nav_col2 = st.columns(2)

with nav_col1:
    st.markdown("""
    <a href="/eventos" target="_self" class="nav-card">
        <div style="font-size: 3rem; margin-bottom: 10px;">⚽</div>
        <h3>Análise de Eventos</h3>
        <p>Mapas de passes, chutes, finalizações e ações defensivas com filtros avançados.</p>
    </a>
    """, unsafe_allow_html=True)

with nav_col2:
    st.markdown("""
    <a href="/equipes" target="_self" class="nav-card">
        <div style="font-size: 3rem; margin-bottom: 10px;">📊</div>
        <h3>Comparativo de Equipes</h3>
        <p>Rankings, scatter plots e tabelas de performance (Geral vs Temporada).</p>
    </a>
    """, unsafe_allow_html=True)

st.divider()

# --- RECENT ACTIVITY SECTION ---
st.subheader("Atividade Recente")
try:
    df_recent = client.query(get_recent_matches_query(PROJECT_ID, DATASET_ID)).to_dataframe()
    # Format Date
    if not df_recent.empty:
        df_recent["match_date"] = pd.to_datetime(df_recent["match_date"]).dt.strftime('%d/%m/%Y')
        df_recent = df_recent.rename(columns={
            "match_date": "Data",
            "home_team": "Mandante",
            "away_team": "Visitante",
            "home_score": "Gols (M)",
            "away_score": "Gols (V)"
        })
        st.dataframe(
            df_recent[["Data", "Mandante", "Gols (M)", "Gols (V)", "Visitante"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhuma partida recente encontrada.")
except Exception as e:
    st.warning("Não foi possível carregar as partidas recentes.")

# --- FOOTER / CHECK ---
st.markdown("---")
# Simple check icon
if client:
    st.markdown(f"<small style='color: #238636;'>✅ Conectado ao BigQuery ({PROJECT_ID})</small>", unsafe_allow_html=True)
else:
     st.markdown(f"<small style='color: #da3633;'>❌ Desconectado</small>", unsafe_allow_html=True)
