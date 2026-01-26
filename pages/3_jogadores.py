import streamlit as st
import pandas as pd
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.bq_io import get_bq_client
from src.css import load_css
from src.queries import get_players_by_team_query, get_player_stats_query, get_player_events_query
from src.plots import plot_events_plotly, plot_radar_chart

st.set_page_config(page_title="Análise de Jogadores", page_icon="🏃", layout="wide")
load_css()

st.title("🏃 Análise Individual de Jogadores")

# --- DATA LOADING ---
PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata" 

@st.cache_data(ttl=3600)
def load_teams():
    # Reuse valid team logic or just distinct from player query
    # Simple list for now or reusing query from queries.py if exists?
    # Let's simple query
    client = get_bq_client(project=PROJECT_ID)
    q = f"SELECT DISTINCT team FROM `{PROJECT_ID}.{DATASET_ID}.eventos_brasileirao_serie_a_2025` ORDER BY team"
    try:
        df = client.query(q).to_dataframe()
        return df["team"].tolist()
    except Exception as e:
        st.error(f"Erro ao carregar times: {e}")
        return []

@st.cache_data(ttl=3600)
def load_players(team):
    client = get_bq_client(project=PROJECT_ID)
    query = get_players_by_team_query(PROJECT_ID, DATASET_ID, team)
    df = client.query(query).to_dataframe()
    return df["player"].tolist()

@st.cache_data(ttl=600)
def load_player_stats(player):
    # This query fetches stats for ALL players (or we filter inside the function if efficient)
    # The query I wrote returns all players.
    client = get_bq_client(project=PROJECT_ID)
    query = get_player_stats_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    
    # Filter for specific player
    # (Not most efficient for big data, but OK for now)
    player_stats = df[df["player"] == player]
    return player_stats

@st.cache_data(ttl=600)
def load_player_events(player):
    client = get_bq_client(project=PROJECT_ID)
    query = get_player_events_query(PROJECT_ID, DATASET_ID, player)
    df = client.query(query).to_dataframe()
    return df

# --- FILTERS ---
col_filt1, col_filt2 = st.columns(2)

teams = load_teams()
if not teams:
    st.stop()

with col_filt1:
    sel_team = st.selectbox("Selecione a Equipe", teams)

players = load_players(sel_team)
with col_filt2:
    sel_player = st.selectbox("Selecione o Jogador", players if players else [])

if not sel_player:
    st.info("Selecione um jogador para visualizar a análise.")
    st.stop()

# --- MAIN CONTENT ---
st.divider()

# Load Data
df_stats = load_player_stats(sel_player)
df_events = load_player_events(sel_player)

if df_stats.empty:
    st.warning("Sem estatísticas disponíveis para este jogador.")
else:
    # --- METRICS & RADAR ---
    col_metrics, col_radar = st.columns([1, 1])

    with col_metrics:
        st.subheader("Métricas de Desempenho")
        
        row = df_stats.iloc[0]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ações Totais", int(row["total_actions"]))
        c2.metric("Gols", int(row["goals"]))
        c3.metric("Chutes", int(row["total_shots"]))
        
        c4, c5, c6 = st.columns(3)
        acc = row["pass_accuracy"]
        c4.metric("Passes Certos", int(row["successful_passes"]))
        c5.metric("Precisão Passe", f"{acc*100:.1f}%" if pd.notna(acc) else "N/A")
        c6.metric("Bolas Recup.", int(row["recoveries"]))
        
        c7, c8, c9 = st.columns(3)
        c7.metric("Interceptações", int(row["interceptions"]))
        c8.metric("Desarmes", int(row["tackles"]))
        
    with col_radar:
        st.subheader("Radar de Atributos (Beta)")
        # Normalize/Prepare radar data
        cats = ["Passes", "Precisão", "Chutes", "Gols", "Defesa (Rec+Int+Des)"]
        
        # Simple simple values scaling for visuals (NOT REAL PERCENTILES YET)
        # Ideally we compare vs League Max. For now just plotting raw/semi-scaled.
        # Let's just plot 'Values' directly but careful with scale.
        # Radar charts suck with mixed units.
        # Just demo implementation now.
        
        defense_sum = row["recoveries"] + row["interceptions"] + row["tackles"]
        vals = [
            row["total_passes"], 
            (row["pass_accuracy"] or 0) * 100, # 0-100 scale
            row["total_shots"] * 5, # Scale up to be visible?
            row["goals"] * 10,
            defense_sum * 2
        ]
        
        fig_radar = plot_radar_chart(sel_player, cats, vals)
        st.plotly_chart(fig_radar, use_container_width=True)

st.divider()

# --- EVENT MAPS ---
st.subheader(f"Mapa de Calor e Eventos: {sel_player}")

# Event Filter
c_types = sorted(df_events["type"].unique())
sel_types = st.multiselect("Filtrar Tipos de Evento", c_types, default=[t for t in c_types if t in ["Pass", "Shot", "Goal"]])

if sel_types:
    df_plot = df_events[df_events["type"].isin(sel_types)].copy()
    
    # Pre-process coords for plotting (0-100 logic from 1_eventos.py needed?)
    # The `plot_events_plotly` expects 0-100 range and converts to pitch dims (105x68).
    # If data is 0-100, we just map. If 0-1, we *100.
    # In 1_eventos.py we used `_scale_series_to_0_100`.
    # Let's apply basic logic here.
    
    # COORD FIX
    for col in ["x_start", "y_start", "x_end", "y_end"]:
        if col in df_plot.columns:
            if df_plot[col].max() <= 1.0:
                 df_plot[col] = df_plot[col] * 100
    
    # Rename for plot function compatibility (it expects "x_plot", "y_plot", "end_x_plot")
    df_plot = df_plot.rename(columns={
        "x_start": "x_plot",
        "y_start": "y_plot",
        "x_end": "end_x_plot",
        "y_end": "end_y_plot"
    })
    
    # Calculate expanded_minute if missing
    if "expanded_minute" not in df_plot.columns:
        df_plot["expanded_minute"] = df_plot["minute"] # Simple fallback

    fig_map = plot_events_plotly(
        df_plot,
        color_strategy="Tipo de Evento", # Simple color by type
        draw_arrows=True,
        theme_colors={"fig_bg": "#0e1117", "pitch_line_color": "#c9cdd1"}
    )
    st.plotly_chart(fig_map, use_container_width=True)
else:
    st.info("Selecione tipos de evento para visualizar.")
