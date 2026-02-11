import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.css import load_css
from src.bq_io import get_bq_client
from src.queries import (
    get_all_teams_query, 
    get_all_players_query, 
    get_player_rankings_query,
    get_match_stats_query,
    get_clean_sheets_query
)

st.set_page_config(page_title="Comparativo", page_icon="🆚", layout="wide")
load_css()

st.title("🆚 Comparativo Head-to-Head")

PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata"

# --- 1. CONFIGURATION ---
col_conf1, col_conf2 = st.columns(2)

with col_conf1:
    mode = st.radio("Comparar:", ["Jogadores", "Equipes"], horizontal=True)

with col_conf2:
    period_mode = st.radio("Período:", ["Temporada Atual (2026)", "Histórico (Todas)"], horizontal=True)


# --- 2. SELECTION ---
client = get_bq_client(project=PROJECT_ID)

@st.cache_data(ttl=3600)
def load_teams():
    q = get_all_teams_query(PROJECT_ID, DATASET_ID)
    return client.query(q).to_dataframe()["team"].tolist()

all_teams = load_teams()

if mode == "Equipes":
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        team_a = st.selectbox("Equipe A", all_teams, index=0)
    with col_sel2:
        # Try to select a different one by default
        idx_b = 1 if len(all_teams) > 1 else 0
        team_b = st.selectbox("Equipe B", all_teams, index=idx_b)

elif mode == "Jogadores":
    # Helper to filter players
    col_filter1, col_filter2 = st.columns(2)
    
    with col_filter1:
        st.markdown("##### Jogador A")
        team_filter_a = st.selectbox("Filtrar Time (A)", ["Todos"] + all_teams, index=0)
        
        @st.cache_data(ttl=300)
        def load_players(team=None):
            t_param = [team] if team and team != "Todos" else None
            q = get_all_players_query(PROJECT_ID, DATASET_ID, t_param)
            return client.query(q).to_dataframe()["player"].unique().tolist()
            
        players_a = load_players(team_filter_a)
        player_a = st.selectbox("Selecionar Jogador A", players_a)

    with col_filter2:
        st.markdown("##### Jogador B")
        team_filter_b = st.selectbox("Filtrar Time (B)", ["Todos"] + all_teams, index=0)
        players_b = load_players(team_filter_b)
        player_b = st.selectbox("Selecionar Jogador B", players_b)

st.divider()

# --- 3. DATA FETCHING ---

@st.cache_data(ttl=300)
def get_data(mode, period_mode):
    if mode == "Jogadores":
        query = get_player_rankings_query(PROJECT_ID, DATASET_ID)
    else:
        query = get_match_stats_query(PROJECT_ID, DATASET_ID)
    
    df = client.query(query).to_dataframe()
    
    # Filter Period
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    if "season" in df.columns:
        df["season"] = df["season"].astype(int)

    if period_mode == "Temporada Atual (2026)":
        if "season" in df.columns:
            df = df[df["season"] == 2026]
    
    return df

df_raw = get_data(mode, period_mode)

if df_raw.empty:
    st.warning("Sem dados para o período selecionado.")
    st.stop()


# --- 4. DATA PROCESSING ---

stats_a = {}
stats_b = {}
label_a = ""
label_b = ""

if mode == "Jogadores":
    if not player_a or not player_b:
        st.stop()
        
    df_a = df_raw[df_raw["player"] == player_a]
    df_b = df_raw[df_raw["player"] == player_b]
    
    label_a = player_a
    label_b = player_b
    
    # Metrics to Agg
    metrics = {
        "Gols": "goals",
        "Assists": "assists",
        "Chutes": "shots",
        "Passes Certos": "successful_passes",
        "Passes Totais": "total_passes",
        "Desarmes": "tackles",
        "Intercept": "interceptions",
        "Recup": "recoveries"
    }
    
    # helper
    def calc_stats(df, label):
        if df.empty: return {k: 0 for k in metrics}
        res = {}
        for k, col in metrics.items():
            res[k] = df[col].sum()
        
        # Derived
        res["Jogos"] = df["game_id"].nunique()
        res["Passes %"] = (res["Passes Certos"] / res["Passes Totais"] * 100) if res["Passes Totais"] > 0 else 0
        return res

    stats_a = calc_stats(df_a, label_a)
    stats_b = calc_stats(df_b, label_b)

else:
    # Equipes
    if not team_a or not team_b:
        st.stop()
        
    df_a = df_raw[df_raw["team"] == team_a]
    df_b = df_raw[df_raw["team"] == team_b]
    
    label_a = team_a
    label_b = team_b
    
    metrics = {
        "Gols Pró": "goals_for",
        "Gols Contra": "goals_against",
        "Finalizações": "total_shots",
        "No Alvo": "shots_on_target",
        "Passes Certos": "successful_passes",
        "Posse (Simulada via Passes)": "total_passes", # Proxy
        "Desarmes": "tackles",
        "Intercept": "interceptions"
    }
    
    def calc_stats_team(df, label):
        if df.empty: return {k: 0 for k in metrics}
        res = {}
        for k, col in metrics.items():
            res[k] = df[col].sum()
            
        res["Jogos"] = df["match_id"].nunique()
        
        # Clean Sheets special fetch (since local logic in this page mimics 3_rankings)
        # We can just count rows where goals_against == 0 if using get_match_stats_query
        # get_match_stats_query sums events but has goals_against from matches
        # but rows are per match? Yes.
        clean_sheets = len(df[df["goals_against"] == 0])
        res["Clean Sheets"] = clean_sheets
        
        return res

    stats_a = calc_stats_team(df_a, label_a)
    stats_b = calc_stats_team(df_b, label_b)


# --- 5. VISUALIZATION ---

# Radar Chart preparation
# Needs normalization. We calculate max of both to normalize.

# Define Radar Dimensions
if mode == "Jogadores":
    radar_metrics = ["Gols", "Assists", "Chutes", "Passes %", "Desarmes", "Recup"]
else:
    radar_metrics = ["Gols Pró", "Finalizações", "No Alvo", "Passes Certos", "Desarmes", "Clean Sheets"]

# Normalized
vals_a = []
vals_b = []
ranges = []

for m in radar_metrics:
    val_a = stats_a.get(m, 0)
    val_b = stats_b.get(m, 0)
    
    # Per Game Normalization for fairness if game count differs significantly?
    # Or strict total comparison?
    # Usually "Per 90" is best. Let's do Per Game.
    games_a = max(1, stats_a.get("Jogos", 1))
    games_b = max(1, stats_b.get("Jogos", 1))
    
    # Exceptions: % metrics require no divisor
    if "%" in m:
        v_a_norm = val_a
        v_b_norm = val_b
    else:
        v_a_norm = val_a / games_a
        v_b_norm = val_b / games_b
        
    vals_a.append(v_a_norm)
    vals_b.append(v_b_norm)
    
    # Determine max for axis
    mx = max(v_a_norm, v_b_norm)
    if mx == 0: mx = 1
    ranges.append(mx * 1.1) 


# Plot Radar
fig = go.Figure()

fig.add_trace(go.Scatterpolar(
    r=[v / r for v, r in zip(vals_a, ranges)], # Scaled 0-1 relative to max in this comparison
    theta=radar_metrics,
    fill='toself',
    name=f"{label_a} (norm)",
    marker=dict(color='#1f77b4')
))

fig.add_trace(go.Scatterpolar(
    r=[v / r for v, r in zip(vals_b, ranges)],
    theta=radar_metrics,
    fill='toself',
    name=f"{label_b} (norm)",
    marker=dict(color='#ff7f0e')
))

fig.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 1])
    ),
    showlegend=True,
    title=f"Comparativo (Normalizado por Jogo) - {label_a} vs {label_b}"
)


col_main1, col_main2 = st.columns([1, 1])

with col_main1:
    st.plotly_chart(fig, use_container_width=True)

with col_main2:
    st.subheader("Dados Absolutos")
    
    # Create comparison table
    all_metrics_keys = list(stats_a.keys())
    # Sort: Jogos first
    if "Jogos" in all_metrics_keys:
        all_metrics_keys.remove("Jogos")
        all_metrics_keys = ["Jogos"] + all_metrics_keys
        
    data = []
    for k in all_metrics_keys:
        va = stats_a[k]
        vb = stats_b[k]
        
        # Format
        if isinstance(va, float): fa = f"{va:.1f}"
        else: fa = str(va)
        
        if isinstance(vb, float): fb = f"{vb:.1f}"
        else: fb = str(vb)
        
        # Diff
        diff = ""
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
             d_val = va - vb
             if d_val > 0: diff = f"🔺 {label_a} (+{d_val:.1f})"
             elif d_val < 0: diff = f"🔻 {label_b} (+{abs(d_val):.1f})"
             else: diff = "="
             
        data.append({
            "Métrica": k,
            label_a: fa,
            label_b: fb,
            "Diferença": diff
        })
        
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
