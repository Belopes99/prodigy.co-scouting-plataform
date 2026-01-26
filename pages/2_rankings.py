import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from src.css import load_css
from src.bq_io import get_bq_client
from src.queries import get_match_stats_query, get_player_rankings_query

st.set_page_config(page_title="Rankings Gerais", page_icon="📊", layout="wide")
load_css()

st.title("📊 Rankings Gerais")

# --- 1. CONFIGURATION & SIDEBAR ---
st.divider()

# --- 2. MAIN FILTERS ---
col_filter_1, col_filter_2, col_filter_3, col_filter_4 = st.columns(4)

with col_filter_1:
    subject = st.radio(
        "Analisar:",
        ["Equipes", "Jogadores"],
        index=0,
        horizontal=True
    )

with col_filter_2:
    aggregation_mode = st.radio(
        "Agrupamento:",
        ["Por Temporada", "Histórico"],
        index=0,
        horizontal=True
    )
    
with col_filter_3:
    # Date Range Filter
    # Default: Last 30 days? Or full range? 
    # Let's verify data range first or use reasonable defaults.
    today = datetime.now().date()
    start_default = today - timedelta(days=365) # Last year default
    
    date_range = st.date_input(
        "Período:",
        value=(start_default, today),
        format="DD/MM/YYYY"
    )

with col_filter_4:
    normalization_mode = st.radio(
        "Visualizar dados:",
        ["Totais (Absolutos)", "Por Jogo (Média)"],
        index=0, # Default Totals
        horizontal=True
    )

# --- 3. DATA LOADING ---
PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata"

@st.cache_data(ttl=3600)
def load_team_data():
    client = get_bq_client(project=PROJECT_ID)
    query = get_match_stats_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    # Ensure date is datetime
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    return df

@st.cache_data(ttl=3600)
def load_player_data():
    client = get_bq_client(project=PROJECT_ID)
    query = get_player_rankings_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    # Ensure date is datetime
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    return df

try:
    if subject == "Equipes":
        df_raw = load_team_data()
    else:
        df_raw = load_player_data()
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 4. DATA PROCESSING (Filtering & Aggregation) ---

# 4.1 Date Filter
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    mask = (df_raw["match_date"] >= start_date) & (df_raw["match_date"] <= end_date)
    df_filtered = df_raw[mask].copy()
elif isinstance(date_range, tuple) and len(date_range) == 1:
    # User selected only start date, treat as >= start
    start_date = date_range[0]
    mask = (df_raw["match_date"] >= start_date)
    df_filtered = df_raw[mask].copy()
else:
    df_filtered = df_raw.copy()

if df_filtered.empty:
    st.warning("Nenhum dado encontrado para o período selecionado.")
    st.stop()


# 4.2 Aggregation Logic
if subject == "Equipes":
    # TEAM LOGIC
    if aggregation_mode == "Por Temporada":
        groupby_cols = ["team", "season"]
        # Determine display name base (will append season)
        df_filtered["base_name"] = df_filtered["team"] 
        
    else: # Historico
        groupby_cols = ["team"]
        df_filtered["base_name"] = df_filtered["team"]
        
    df_agg = df_filtered.groupby(groupby_cols)[
        ["goals_for", "goals_against", "total_passes", "successful_passes", "total_shots", "shots_on_target"]
    ].sum().reset_index()
        
    matches = df_filtered.groupby(groupby_cols)["match_id"].nunique().reset_index(name="matches")
    df_agg = pd.merge(df_agg, matches, on=groupby_cols)

    # Display Name Reconstruction
    if "season" in groupby_cols:
        df_agg["display_name"] = df_agg["team"] + " (" + df_agg["season"].astype(str) + ")"
    else:
         df_agg["display_name"] = df_agg["team"]


elif subject == "Jogadores":
    # PLAYER LOGIC
    # Raw cols: player, team, season, match_date, game_id, goals, shots, successful_passes, total_passes
    
    if aggregation_mode == "Por Temporada":
        groupby_cols = ["player", "team", "season"]
    else: 
        groupby_cols = ["player"]

    df_agg = df_filtered.groupby(groupby_cols)[
        ["goals", "shots", "successful_passes", "total_passes"]
    ].sum().reset_index()
    
    # Count matches: distinct game_id per group
    matches = df_filtered.groupby(groupby_cols)["game_id"].nunique().reset_index(name="matches")
    df_agg = pd.merge(df_agg, matches, on=groupby_cols)

    # Display Name Reconstruction
    if "season" in groupby_cols:
        df_agg["display_name"] = df_agg["player"] + " (" + df_agg["team"] + " " + df_agg["season"].astype(str) + ")"
    else:
        df_agg["display_name"] = df_agg["player"]
        
    # Alias for consistency with chart
    df_agg["goals_for"] = df_agg["goals"] 
    df_agg["total_shots"] = df_agg["shots"]


# 4.3 Metrics Calculation (Per Match)
# Basic Per Match (P90 proxy)
df_agg["goals_p90"] = (df_agg["goals_for"] / df_agg["matches"]).fillna(0)
df_agg["shots_p90"] = (df_agg["total_shots"] / df_agg["matches"]).fillna(0)
# Pass Pct is always independent of totals vs p90
df_agg["pass_pct"] = (df_agg["successful_passes"] / df_agg["total_passes"]).fillna(0) * 100

# 4.4 Chart columns setup
if normalization_mode == "Por Jogo (Média)":
    metric_col = "goals_p90"
    metric_label = "Gols por Jogo"
    secondary_col = "shots_p90"
    secondary_label = "Chutes por Jogo"
    text_format = ".2f"
else: # Totals
    metric_col = "goals_for"
    metric_label = "Total de Gols"
    secondary_col = "total_shots"
    secondary_label = "Total de Chutes"
    text_format = ".0f"


# --- 5. VISUALIZATION ---

tab1, tab2 = st.tabs(["📊 Rankings (Gols)", "📋 Dados Detalhados"])

with tab1:
    col_chart_meta, _ = st.columns([1, 3])
    with col_chart_meta:
        st.caption(f"Exibindo **{metric_label}** para top itens.")
    
    top_n = st.slider("Quantidade de itens:", 5, 50, 20)
    
    # Sort by the selected metric
    df_chart = df_agg.sort_values(metric_col, ascending=False).head(top_n)
    
    fig = px.bar(
        df_chart,
        x=metric_col,
        y="display_name",
        orientation='h',
        color="pass_pct", # Auxiliary color
        color_continuous_scale="Viridis",
        text=metric_col,
        labels={
            metric_col: metric_label,
            "display_name": subject[:-1],
            "pass_pct": "Precisão de Passe (%)"
        }
    )
    
    fig.update_layout(yaxis={'categoryorder':'total ascending'}, template="plotly_dark", height=600)
    fig.update_traces(texttemplate='%{text:' + text_format + '}', textposition='outside')
    
    st.plotly_chart(fig, use_container_width=True)


with tab2:
    st.dataframe(
        df_agg.sort_values("goals_for", ascending=False),
        use_container_width=True,
        hide_index=True
    )
