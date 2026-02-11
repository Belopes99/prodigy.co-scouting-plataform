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
from src.queries import (
    get_match_stats_query, 
    get_player_rankings_query, 
    get_dynamic_ranking_query, 
    get_all_teams_query, 
    get_all_players_query, 
    get_conversion_ranking_query,
    get_teams_match_count_query,
    get_player_match_counts_query
)




st.set_page_config(page_title="Rankings Pró (A Favor)", page_icon="📈", layout="wide")
load_css()

st.title("📈 Rankings Pró (A Favor)")


PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata"


# --- 1. MAIN CONFIGURATION ---
col_filter_1, col_filter_2, col_filter_3, col_filter_4 = st.columns(4)

with col_filter_1:
    subject = st.radio("Analisar:", ["Equipes", "Jogadores"], index=0, horizontal=True)
    analysis_type = st.radio("Tipo de Análise:", ["Volume Total", "Eficiência/Conversão"], index=0, horizontal=True)

with col_filter_2:
    aggregation_mode = st.radio("Agrupamento:", ["Por Temporada", "Histórico"], index=0, horizontal=True)

with col_filter_3:
    st.info("Filtro de Periodo carregado dinamicamente abaixo.")

with col_filter_4:
    top_n = st.number_input("Top N:", 1, 100, 10)
    normalization_mode = st.radio("Visualizar:", ["Total", "Por Jogo"], index=0, horizontal=True, label_visibility="collapsed")

st.divider()

# --- 2. SCOPE FILTERS (Hierarchical) ---
# Filter first by Team, then by Player (if applicable)

col_scope_1, col_scope_2 = st.columns(2)

# Load Teams
@st.cache_data(ttl=3600)
def load_team_list():
    client = get_bq_client(project=PROJECT_ID)
    q = get_all_teams_query(PROJECT_ID, DATASET_ID)
    df = client.query(q).to_dataframe()
    return df["team"].tolist()

ALL_TEAMS = load_team_list()

# Load Players (Dynamic based on team selection)
@st.cache_data(ttl=300)
def load_player_list(selected_teams=None):
    client = get_bq_client(project=PROJECT_ID)
    teams_param = selected_teams if selected_teams else None
    q = get_all_players_query(PROJECT_ID, DATASET_ID, teams_param)
    df = client.query(q).to_dataframe()
    return df["player"].unique().tolist() 

with col_scope_1:
    sel_teams = st.multiselect("Filtrar Equipes (Opcional)", ALL_TEAMS, default=[], help="Deixe vazio para ver todas.")

with col_scope_2:
    sel_players = []
    if subject == "Jogadores":
        # Hierarchical: Filter players by selected teams
        available_players = load_player_list(sel_teams)
        sel_players = st.multiselect("Filtrar Jogadores (Opcional)", available_players, default=[], help="Deixe vazio para ver todos.")
    else:
        st.write("") 

st.divider()

st.markdown("##### 🛠️ Configurar Filtros")

# Lists for filtering
# (Team loader moved to top)

EVENT_TYPES = [
    "Pass", 
    "Goal", 
    "SavedShot", 
    "MissedShots", 
    "ShotOnPost", 
    "BallRecovery", 
    "Tackle", 
    "Interception", 
    "Foul", 
    "Save", 
    "Clearance", 
    "TakeOn", 
    "Aerial", 
    "Error", 
    "Challenge", 
    "Dispossessed",
    "BlockedPass",
    "Smother",
    "KeeperPickup"
]

OUTCOMES = ["Sucesso", "Falha"]
QUALIFIERS = ["KeyPass", "Assisted", "BigChanceCreated", "LeadingToGoal", "LeadingToAttempt", "Head", "Cross", "Corner", "FreeKick", "Penalty", "Throughball", "Longball", "Chipped", "LayOff", "Volley", "OwnGoal", "Red", "Yellow"]



# --- CONFIG FILTERS ---

if analysis_type == "Volume Total":
    # STANDARD MODE - Single Set of Filters
    
    col_c1, col_c2, col_c3, col_c4 = st.columns([1.5, 1.5, 2, 0.5])
    
    with col_c1:
        sel_types = st.multiselect("Tipos de Evento", EVENT_TYPES, default=["Goal"])
    with col_c2:
        sel_outcomes = st.multiselect("Resultados", OUTCOMES, default=[])
    with col_c3:
        sel_qualifiers = st.multiselect("Qualificadores (Tags)", QUALIFIERS, default=[])

    with col_c4: 
        st.write("")
        st.write("")
        is_goal_context = sel_types and "Goal" in sel_types
        has_assisted_tag = sel_qualifiers and "Assisted" in sel_qualifiers
        
        if is_goal_context:
            default_val = True if has_assisted_tag else False
            chk_key = f"rel_chk_{is_goal_context}_{has_assisted_tag}"
            use_related = st.checkbox("Rank de Assistências", value=default_val, key=chk_key)
        else:
            use_related = False

    # Mock variables for Conversion Mode logic
    num_types, num_out, num_qual = sel_types, sel_outcomes, sel_qualifiers
    den_types, den_out, den_qual = [], [], []

else:
    # CONVERSION MODE - Dual Set
    use_related = False # Disable related logic for conversion for now (complexity)
    
    st.info("💡 Modo Conversão: Defina o Numerador (o que conta como sucesso) e o Denominador (o total de tentativas).")
    
    c_num, c_den = st.columns(2)
    
    with c_num:
        st.markdown("#### 🟢 Numerador (Sucesso)")
        num_types = st.multiselect("Eventos (Num)", EVENT_TYPES, default=["Goal"])
        num_out = st.multiselect("Resultados (Num)", OUTCOMES, default=[])
        num_qual = st.multiselect("Tags (Num)", QUALIFIERS, default=[])

    with c_den:
        st.markdown("#### 🔵 Denominador (Base)")
        den_types = st.multiselect("Eventos (Den)", EVENT_TYPES, default=["Goal", "MissedShots", "SavedShot", "ShotOnPost"])
        den_out = st.multiselect("Resultados (Den)", OUTCOMES, default=[])
        den_qual = st.multiselect("Tags (Den)", QUALIFIERS, default=[])
    
    # Map to existing vars for compatibility where needed, though we will branch logic
    sel_types = num_types 
    sel_outcomes = num_out
    sel_qualifiers = num_qual



# --- 3. DATA LOADING & UNIFICATION ---
# (Constants moved to top)

# Dynamic Loader

@st.cache_data(ttl=300) 
def load_dynamic_data(subj, etypes, outs, quals, use_rel, teams, players, a_type, d_types=None, d_outs=None, d_quals=None):
    client = get_bq_client(project=PROJECT_ID)
    
    if a_type == "Volume Total":
        query = get_dynamic_ranking_query(PROJECT_ID, DATASET_ID, subj, etypes, outs, quals, use_rel, teams, players, perspective="pro")
    else:
        # Conversion
        query = get_conversion_ranking_query(
            PROJECT_ID, DATASET_ID, subj,
            etypes, outs, quals,
            d_types, d_outs, d_quals,
            teams, players, perspective="pro"
        )


    df = client.query(query).to_dataframe()

    if "match_date" in df.columns:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    return df


try:
    # Prepare params
    q_types = sel_types if sel_types else "Todos"
    q_outcomes = sel_outcomes if sel_outcomes else "Todos"
    q_qualifiers = sel_qualifiers if sel_qualifiers else "Todos (Qualquer)"
    
    # Check for empty selection prevention?
    # Pass teams and players
    q_teams = sel_teams if sel_teams else None
    q_players = sel_players if sel_players else None
    
    # Validation for conversion
    if analysis_type == "Eficiência/Conversão":
        if not num_types or not den_types:
             st.warning("Selecione eventos para Numerador e Denominador.")
             st.stop()
             
        df_raw = load_dynamic_data(
            subject, num_types, num_out, num_qual, False, q_teams, q_players,
            analysis_type, den_types, den_out, den_qual
        )
    else:
        # Standard
        if not sel_types and not sel_outcomes and not sel_qualifiers and not sel_teams:
            st.info("Selecione pelo menos um filtro acima.")
            # st.stop() # Allowing empty to load all? Maybe heavy.
            pass

        df_raw = load_dynamic_data(
            subject, q_types, q_outcomes, q_qualifiers, use_related, q_teams, q_players,
            analysis_type
        )


    
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()


# --- 4. DATE FILTER WITH DYNAMIC DEFAULTS ---
with col_filter_3:
    # Determine min/max from data for default
    if not df_raw.empty and "match_date" in df_raw.columns:
        # Ensure datetime
        if not pd.api.types.is_datetime64_any_dtype(df_raw["match_date"]):
            df_raw["match_date"] = pd.to_datetime(df_raw["match_date"], errors="coerce")
        
        
        # Normalize to date object (removes time/timezone issues for comparison)
        # Handle NaT/NaN to avoid float comparison errors
        df_raw = df_raw.dropna(subset=["match_date"])
        df_raw["match_date"] = df_raw["match_date"].dt.date
            
        if not df_raw.empty:
            min_date = df_raw["match_date"].min()
            max_date = df_raw["match_date"].max()
        else:
            min_date = datetime.now().date() - timedelta(days=365)
            max_date = datetime.now().date()
    else:
        # Fallback if empty
        min_date = datetime.now().date() - timedelta(days=365)
        max_date = datetime.now().date()
        
    # Ensure current date_range (if set previously in session state) is valid
    # But this is a fresh render.
    
    date_range = st.date_input(
        "Período (Filtro):",
        value=(min_date, max_date),
        format="DD/MM/YYYY"
    )

# 4.0 Normalize IDs (Critical for Dynamic vs Standard Queries)
# Apply even if empty to ensure columns exist for downstream
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
        "metric_count": "sum", # Standard mode
        "numerator": "sum", # Conversion mode
        "denominator": "sum" # Conversion mode
    }
    
    # Filter known columns only (safe check)
    valid_cols = [c for c in agg_dict.keys() if c in df_filtered.columns]
    agg_dict_final = {k: agg_dict[k] for k in valid_cols}
    
    df_agg = df_filtered.groupby(groupby_cols).agg(agg_dict_final).reset_index()
        
    df_agg = df_filtered.groupby(groupby_cols).agg(agg_dict_final).reset_index()
        
    # matches = df_filtered.groupby(groupby_cols)["match_id"].nunique().reset_index(name="matches")
    # df_agg = pd.merge(df_agg, matches, on=groupby_cols)

    # --- TRUE MATCH COUNT LOGIC ---
    # Fetch total matches played by the team in the filtered period
    matches_query = get_teams_match_count_query(PROJECT_ID, DATASET_ID, q_teams, date_range)
    df_matches = client.query(matches_query).to_dataframe()
    
    # Merge matches (Left join to keep agg rows, or inner? Left is safer if stats exist but no match log?)
    # Actually, if stats exist, match log MUST exist.
    # We join on team and season (if applicable)
    join_cols = ["team"]
    if "season" in groupby_cols:
        join_cols.append("season")
        # Match data already has season, so straightforward merge
        df_agg = pd.merge(df_agg, df_matches, on=join_cols, how="left")
    else:
        # Historical Mode: metrics are aggregated by Team.
        # Match data is by Team/Season. We must SUM total_games for the team across the period.
        if not df_matches.empty:
            df_matches_grouped = df_matches.groupby("team")["total_games"].sum().reset_index()
            df_agg = pd.merge(df_agg, df_matches_grouped, on="team", how="left")
        else:
            df_agg["total_games"] = 0 # Will be filled by event count fallback

    
    # Fallback: If total_games is NaN (missing schedule), use event count as backup
    # But event count is 'matches' from stats. Let's calculate it too for reference.
    event_matches = df_filtered.groupby(groupby_cols)["match_id"].nunique().reset_index(name="matches_with_event")
    df_agg = pd.merge(df_agg, event_matches, on=groupby_cols, how="left")
    
    df_agg["matches"] = df_agg["total_games"].fillna(df_agg["matches_with_event"])


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
        "metric_count": "sum",
        "numerator": "sum",
        "denominator": "sum"
    }
    
    # Filter known columns only (safe check)
    valid_cols = [c for c in agg_dict.keys() if c in df_filtered.columns]
    agg_dict_final = {k: agg_dict[k] for k in valid_cols}

    df_agg = df_filtered.groupby(groupby_cols).agg(agg_dict_final).reset_index()
    
    # Count matches: distinct game_id per group
    df_agg = df_filtered.groupby(groupby_cols).agg(agg_dict_final).reset_index()
    
    # --- TRUE MATCH COUNT LOGIC (PLAYERS) ---
    # Fetch total matches played (participation)
    # Note: get_player_match_counts_query needs logic update to return 'team' col correctly if grouped?
    # Yes, it returns player, team, season, total_games.
    
    matches_query = get_player_match_counts_query(PROJECT_ID, DATASET_ID, q_teams, q_players, date_range)
    df_matches = client.query(matches_query).to_dataframe()
    
    join_cols = ["player", "team"] # Basic join
    if "season" in groupby_cols:
        join_cols.append("season")
        
    # Careful: If aggregating ONLY by player (Historico across teams), we sum total_games?
    # Or join on player only?
    if aggregation_mode == "Histórico":
        # Sum total_games per player across teams/seasons
        df_matches_grouped = df_matches.groupby("player")["total_games"].sum().reset_index()
        df_agg = pd.merge(df_agg, df_matches_grouped, on="player", how="left")
    else:
        # Join on full key
        df_agg = pd.merge(df_agg, df_matches, on=join_cols, how="left")

    event_matches = df_filtered.groupby(groupby_cols)["game_id"].nunique().reset_index(name="matches_with_event")
    df_agg = pd.merge(df_agg, event_matches, on=groupby_cols, how="left")
    
    df_agg["matches"] = df_agg["total_games"].fillna(df_agg["matches_with_event"])


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
# 4.3 Metrics Mapping
# 4.3 Metrics Calculation (Standard) vs Conversion Ratio
if analysis_type == "Eficiência/Conversão":
    base_col = "ratio_pct"
    df_agg["ratio_val"] = (df_agg["numerator"] / df_agg["denominator"]).fillna(0)
    df_agg["ratio_pct"] = df_agg["ratio_val"] * 100
    
    # Label
    # Simplify label construction
    n_lab = num_types[0] if num_types else "N"
    d_lab = den_types[0] if den_types else "D"
    if len(num_types) > 1: n_lab += "+"
    if len(den_types) > 1: d_lab += "+"
    
    base_label = f"Conversão ({n_lab} / {d_lab})"
    metric_label = f"{base_label} (%)"
    text_format = ".1f"
    metric_col = "display_metric"
    df_agg[metric_col] = df_agg["ratio_pct"]

else:
    # Standard Logic
    base_col = "metric_count"
    
    # Construct label from selections
    type_label = ", ".join(sel_types) if sel_types else "Todos Eventos"
    team_label = f" ({', '.join(sel_teams)})" if sel_teams else "" 
    player_label = f" ({', '.join(sel_players)})" if sel_players else ""
    out_label = f" ({', '.join(sel_outcomes)})" if sel_outcomes else ""
    qual_label = f" [{', '.join(sel_qualifiers)}]" if sel_qualifiers else ""
    rel_label = " (Assistências)" if use_related else ""
    
    base_label = f"{type_label}{qual_label}{out_label}{rel_label}{team_label}{player_label}"
    
    if len(base_label) > 50:
        base_label = base_label[:47] + "..."
    
    if normalization_mode == "Por Jogo":
        df_agg["display_metric"] = (df_agg[base_col] / df_agg["matches"]).fillna(0)
        metric_label = f"{base_label} / Jogo"
        text_format = ".2f"
    else:
        df_agg["display_metric"] = df_agg[base_col]
        metric_label = f"Total {base_label}"
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
    
    # Customization Controls
    with st.expander("🎨 Personalizar Rótulos (Imagem)", expanded=False):
        c_cust1, c_cust2, c_cust3 = st.columns(3)
        with c_cust1:
            custom_metric_label = st.text_input("Título do Eixo X (Métrica):", value=metric_label)
        with c_cust2:
            custom_subject_label = st.text_input("Título do Eixo Y (Participante):", value=subject[:-1])
        with c_cust3:
            custom_legend_label = st.text_input("Legenda de Cor/Valor:", value=base_label)

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
                metric_col: custom_metric_label,
                "display_name": custom_subject_label,
                metric_col: custom_metric_label,
                "display_name": custom_subject_label,
                "matches": "Jogos Disputados (Total)",
                "matches_with_event": "Jogos com o Evento",

                base_col: custom_legend_label,
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
