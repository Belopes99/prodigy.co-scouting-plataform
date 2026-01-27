import streamlit as st
import pandas as pd
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import plotly.express as px
from datetime import datetime, timedelta

from src.css import load_css
from src.bq_io import get_bq_client
from src.queries import get_match_stats_query, get_player_rankings_query, get_dynamic_ranking_query

st.set_page_config(page_title="Rankings Gerais", page_icon="📊", layout="wide")
load_css()

st.title("📊 Rankings Gerais")

# --- 1. CONFIGURATION & SIDEBAR ---
st.divider()

# --- 2. CONFIGURATION & SIDEBAR ---
col_filter_1, col_filter_2, col_filter_3, col_filter_4, col_filter_5 = st.columns(5)

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

with col_filter_4:
    metric_selection = st.selectbox(
        "Métrica:",
        ["Personalizado 🛠️", "Gols", "Assistências", "Passes Decisivos", "Chutes", "Passes Certos", "Desarmes", "Interceptações", "Recuperações", "Faltas"],
        index=1 # Default Gols
    )

# --- CUSTOM FILTERS (Only if Personalizado) ---
custom_type = "Todos"
custom_outcome = "Todos"
custom_qualifier = ""

if metric_selection == "Personalizado 🛠️":
    st.markdown("##### Configurar Métrica Personalizada")
    row_c1, row_c2, row_c3 = st.columns(3)
    with row_c1:
        custom_type = st.selectbox("Tipo de Evento", 
            ["Pass", "Shot", "Ball Recovery", "Tackle", "Interception", "Foul", "Save", "Goal", "Clearance", "TakeOn", "Aerial"],
            index=0
        )
    with row_c2:
        custom_outcome = st.selectbox("Resultado", ["Todos", "Sucesso", "Falha"], index=0)
    with row_c3:
        custom_qualifier = st.text_input("Qualificador (ex: KeyPass, Head, Cross)", "")


with col_filter_5:
    top_n = st.number_input("Top N:", 1, 100, 10)
    
    normalization_mode = st.radio(
        "Visualizar:",
        ["Total", "Por Jogo"],
        index=0,
        horizontal=True,
        label_visibility="collapsed" 
    )


# --- 3. DATA LOADING ---
PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata"

# Standard Loaders
@st.cache_data(ttl=3600)
def load_team_data():
    client = get_bq_client(project=PROJECT_ID)
    query = get_match_stats_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    return df

@st.cache_data(ttl=3600)
def load_player_data():
    client = get_bq_client(project=PROJECT_ID)
    query = get_player_rankings_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    return df

# Dynamic Loader
@st.cache_data(ttl=300) # Shorter TTL for dynamic
def load_dynamic_data(subj, etype, out, qual):
    client = get_bq_client(project=PROJECT_ID)
    query = get_dynamic_ranking_query(PROJECT_ID, DATASET_ID, subj, etype, out, qual)
    df = client.query(query).to_dataframe()
    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    return df

try:
    if metric_selection == "Personalizado 🛠️":
        # Load specific customized data
        # Mapping outcome UI to query values
        out_map = {"Sucesso": "Successful", "Falha": "Unsuccessful", "Todos": "Todos"}
        df_raw = load_dynamic_data(subject, custom_type, out_map.get(custom_outcome, "Todos"), custom_qualifier)
    else:
        # Load standard pre-aggregated data
        if subject == "Equipes":
            df_raw = load_team_data()
        else:
            df_raw = load_player_data()
            
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()


# --- 4. DATE FILTER WITH DYNAMIC DEFAULTS ---
with col_filter_3:
    # Determine min/max from data for default
    if not df_raw.empty and "match_date" in df_raw.columns:
        min_date = df_raw["match_date"].min()
        max_date = df_raw["match_date"].max()
    else:
        # Fallback if empty
        min_date = datetime.now().date() - timedelta(days=365)
        max_date = datetime.now().date()
        
    date_range = st.date_input(
        "Período:",
        value=(min_date, max_date),
        format="DD/MM/YYYY"
    )

# 4.0 Normalize IDs (Critical for Dynamic vs Standard Queries)
if not df_raw.empty:
    if "game_id" in df_raw.columns and "match_id" not in df_raw.columns:
        df_raw["match_id"] = df_raw["game_id"]
    elif "match_id" in df_raw.columns and "game_id" not in df_raw.columns:
        df_raw["game_id"] = df_raw["match_id"]

# 4.1 Apply Date Filter
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    mask = (df_raw["match_date"] >= start_date) & (df_raw["match_date"] <= end_date)
    df_filtered = df_raw[mask].copy()
elif isinstance(date_range, tuple) and len(date_range) == 1:
    # User selected only start date
    start_date = date_range[0]
    mask = (df_raw["match_date"] >= start_date)
    df_filtered = df_raw[mask].copy()
else:
    df_filtered = df_raw.copy()

if df_filtered.empty:
    st.warning("Nenhum dado encontrado para o período selecionado.")
    # st.stop() # Removed stop to allow changing filters even if empty



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
        
    # Aggregation
    agg_dict = {
        "goals_for": "sum", "goals_against": "sum", 
        "total_passes": "sum", "successful_passes": "sum", 
        "total_shots": "sum", "shots_on_target": "sum",
        "tackles": "sum", "interceptions": "sum", 
        "recoveries": "sum", "clearances": "sum",
        "saves": "sum", "fouls": "sum",
        "assists": "sum", "key_passes": "sum",
        "metric_count": "sum" # For dynamic
    }
    
    # Filter known columns only (safe check)
    valid_cols = [c for c in agg_dict.keys() if c in df_filtered.columns]
    agg_dict_final = {k: agg_dict[k] for k in valid_cols}
    
    df_agg = df_filtered.groupby(groupby_cols).agg(agg_dict_final).reset_index()
        
    matches = df_filtered.groupby(groupby_cols)["match_id"].nunique().reset_index(name="matches")
    df_agg = pd.merge(df_agg, matches, on=groupby_cols)

    # Display Name Reconstruction (Robust)
    if "season" in df_agg.columns:
        df_agg["display_name"] = df_agg["team"] + " (" + df_agg["season"].astype(str) + ")"
    else:
         df_agg["display_name"] = df_agg["team"]


elif subject == "Jogadores":
    # PLAYER LOGIC
    
    if aggregation_mode == "Por Temporada":
        groupby_cols = ["player", "team", "season"]
    else: 
        groupby_cols = ["player"]

    agg_dict = {
        "goals": "sum", "shots": "sum", 
        "successful_passes": "sum", "total_passes": "sum",
        "tackles": "sum", "interceptions": "sum",
        "recoveries": "sum", "clearances": "sum", "fouls": "sum",
        "assists": "sum", "key_passes": "sum",
        "metric_count": "sum" # For dynamic
    }
    
    # Filter known columns only (safe check)
    valid_cols = [c for c in agg_dict.keys() if c in df_filtered.columns]
    agg_dict_final = {k: agg_dict[k] for k in valid_cols}

    df_agg = df_filtered.groupby(groupby_cols).agg(agg_dict_final).reset_index()
    
    # Count matches: distinct game_id per group
    matches = df_filtered.groupby(groupby_cols)["game_id"].nunique().reset_index(name="matches")
    df_agg = pd.merge(df_agg, matches, on=groupby_cols)

    # Display Name Reconstruction (Robust)
    if "season" in df_agg.columns:
        df_agg["display_name"] = df_agg["player"] + " (" + df_agg["team"] + " " + df_agg["season"].astype(str) + ")"
    else:
        df_agg["display_name"] = df_agg["player"]
        
    # Alias for consistency with team cols
    if "goals" in df_agg.columns: df_agg["goals_for"] = df_agg["goals"] 
    if "shots" in df_agg.columns: df_agg["total_shots"] = df_agg["shots"]


# 4.3 Metrics Calculation (Per Match)
# 4.3 Metrics Mapping
if metric_selection == "Personalizado 🛠️":
    # Use the dynamic column
    base_col = "metric_count"
    base_label = f"{custom_type}"
    if custom_qualifier:
        base_label += f" ({custom_qualifier})"
    if custom_outcome != "Todos":
        base_label += f" - {custom_outcome}"
else:
    # Map selection to column
    metric_map = {
        "Gols": {"col": "goals_for", "label": "Gols"},
        "Assistências": {"col": "assists", "label": "Assistências"},
        "Passes Decisivos": {"col": "key_passes", "label": "Passes Decisivos"},
        "Chutes": {"col": "total_shots", "label": "Chutes"},
        "Passes Certos": {"col": "successful_passes", "label": "Passes Certos"},
        "Desarmes": {"col": "tackles", "label": "Desarmes"},
        "Interceptações": {"col": "interceptions", "label": "Interceptações"},
        "Recuperações": {"col": "recoveries", "label": "Recuperações"},
        "Faltas": {"col": "fouls", "label": "Faltas Cometidas"},
    }

    sel_metric = metric_map.get(metric_selection, {"col": "goals_for", "label": "Gols"})
    base_col = sel_metric["col"]
    base_label = sel_metric["label"]

# 4.4 Calc P90/Total
if normalization_mode == "Por Jogo" or normalization_mode == "Por Jogo (Média)": # Handle label change
    df_agg["display_metric"] = (df_agg[base_col] / df_agg["matches"]).fillna(0)
    metric_label = f"{base_label} por Jogo"
    text_format = ".2f"
else: # Totals
    df_agg["display_metric"] = df_agg[base_col]
    metric_label = f"Total de {base_label}"
    text_format = ".0f"

metric_col = "display_metric"


# --- 5. VISUALIZATION ---

# Sort and Limit Globally
df_sorted = df_agg.sort_values(metric_col, ascending=False).head(top_n)

# Tabs
tab1, tab2 = st.tabs(["📊 Rankings (Gols)", "📋 Dados Detalhados"])

with tab1:
    col_chart_meta, _ = st.columns([1, 3])
    with col_chart_meta:
        st.caption(f"Exibindo **{metric_label}** para top {top_n} itens.")
    
    # Check if empty
    if df_sorted.empty:
        st.warning("Sem dados para exibir.")
    else:
        fig = px.bar(
            df_sorted,
            x=metric_col,
            y="display_name",
            orientation='h',
            color=metric_col, # Gradient based on the indicator itself
            color_continuous_scale="Viridis",
            text=metric_col,
            # Add raw data to tooltip (Removing Shots/Passes as requested)
            hover_data={
                "matches": True,
                base_col: True, # Show the raw total of selected metric
                "display_name": False, # Hide duplicate name
                metric_col: ":.2f" if "Por Jogo" in normalization_mode else ":.0f"
            },
            labels={
                metric_col: metric_label,
                "display_name": subject[:-1],
                "matches": "Jogos Disputados",
                base_col: base_label,
                "goals_for": "Total de Gols" # Legacy fallback
            }
        )
        
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, template="plotly_dark", height=600)
        fig.update_traces(texttemplate='%{text:' + text_format + '}', textposition='outside')
        
        st.plotly_chart(fig, use_container_width=True)


with tab2:
    st.dataframe(
        df_sorted,
        use_container_width=True,
        hide_index=True
    )
