import streamlit as st
import pandas as pd
import plotly.express as px
from src.ui_filters import render_sidebar_globals
from src.css import load_css
from src.bq_io import get_bq_client
from src.queries import get_match_stats_query

st.set_page_config(page_title="Ranking de Equipes", page_icon="📊", layout="wide")
load_css()
globals_ = render_sidebar_globals()

st.title("📊 Comparativo de Equipes")

# --- 1. DATA LOADING ---
PROJECT_ID = "betterbet-448216"
DATASET_ID = "events_data"

@st.cache_data(ttl=3600)
def load_data():
    client = get_bq_client(project=PROJECT_ID)
    query = get_match_stats_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 2. FILTERS & AGGREGATION ---
with st.sidebar:
    st.header("Configuração de Análise")
    
    # Mode: Season vs General
    mode = st.radio(
        "Modo de Comparação:",
        ["Por Temporada (Ex: 2024 vs 2025)", "Histórico Geral (Agregado)"],
        index=0
    )
    
    # Competition (Mocked for now as we only have 1 dataset ideally)
    # If we had 'competition' col, we would filter here.
    
    if mode.startswith("Por Temporada"):
        # Group by Team AND Season
        groupby_cols = ["team", "season"]
        df["team_display"] = df["team"] + " (" + df["season"].astype(str) + ")"
    else:
        # Group by Team only
        groupby_cols = ["team"]
        df["team_display"] = df["team"]

# Calculate Aggregates
# Sums
agg_sums = df.groupby(groupby_cols)[
    ["goals_for", "goals_against", "total_passes", "successful_passes", "total_shots", "shots_on_target"]
].sum().reset_index()

# Counts (Matches played)
agg_counts = df.groupby(groupby_cols)["match_id"].nunique().reset_index(name="matches")

# Merge
df_agg = pd.merge(agg_sums, agg_counts, on=groupby_cols)

# Metrics Calculation (Per 90 / Rates)
df_agg["goals_for_p90"] = df_agg["goals_for"] / df_agg["matches"]
df_agg["goals_against_p90"] = df_agg["goals_against"] / df_agg["matches"]
df_agg["shots_p90"] = df_agg["total_shots"] / df_agg["matches"]
df_agg["shots_on_target_pct"] = (df_agg["shots_on_target"] / df_agg["total_shots"]).fillna(0) * 100
df_agg["pass_completion_pct"] = (df_agg["successful_passes"] / df_agg["total_passes"]).fillna(0) * 100

# Create Display Column logic again if lost after merge
if "season" in df_agg.columns:
    df_agg["team_display"] = df_agg["team"] + " " + df_agg["season"].astype(str)
else:
    df_agg["team_display"] = df_agg["team"]

# --- 3. UI LAYOUT ---

tab1, tab2 = st.tabs(["🌎 Visão Geral (Gráficos)", "📋 Tabela Detalhada"])

with tab1:
    col_a, col_b = st.columns(2)
    
    # Scatter 1: Offensive Efficiency
    with col_a:
        st.subheader("Eficiência Ofensiva")
        fig_off = px.scatter(
            df_agg,
            x="shots_p90",
            y="goals_for_p90",
            text="team_display",
            size="matches",
            color="pass_completion_pct",
            color_continuous_scale="Viridis",
            labels={
                "shots_p90": "Chutes por Jogo",
                "goals_for_p90": "Gols por Jogo",
                "pass_completion_pct": "Precisão Passe %",
                "matches": "Jogos"
            },
            hover_data=["team", "season"] if "season" in df_agg.columns else ["team"]
        )
        fig_off.update_traces(textposition='top center')
        fig_off.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_off, use_container_width=True)
        st.caption("Eixo X: Volume de Jogo (Chutes) | Eixo Y: Eficácia (Gols) | Cor: Qualidade Técnica")

    # Scatter 2: Defensive Solidity
    with col_b:
        st.subheader("Solidez Defensiva")
        fig_def = px.scatter(
            df_agg,
            x="shots_p90", # Should be Shots Conceded, but we don't have it easily in query yet without self-join or complex logic.
                           # Workaround: Use Goals Against vs Matches for now, or assume avg stats.
                           # Let's stick to Goals Against vs Goals For for "Balance"
            y="goals_against_p90",
            text="team_display",
            size="matches",
            color="goals_for_p90",
            color_continuous_scale="RdBu", # Red (Attack) to Blue (Defense)? Or divergent. 
            labels={
                "shots_p90": "Chutes (Criados) - *Proxy*", # Imperfect
                "goals_against_p90": "Gols Sofridos por Jogo",
                "goals_for_p90": "Gols Feitos"
            }
        )
        # Actually a better chart: "Goal Difference"
        df_agg["goal_diff"] = df_agg["goals_for"] - df_agg["goals_against"]
        fig_bal = px.bar(
            df_agg.sort_values("goal_diff", ascending=True),
            x="goal_diff",
            y="team_display",
            orientation='h',
            color="goal_diff",
            color_continuous_scale="RdBu",
            title="Saldo de Gols Global"
        )
        fig_bal.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_bal, use_container_width=True)

with tab2:
    st.subheader("Ranking Estatístico")
    
    # Format for display
    display_cols = ["team_display", "matches", "goals_for", "goals_against", "shots_p90", "pass_completion_pct"]
    column_config = {
        "team_display": st.column_config.TextColumn("Equipe"),
        "matches": st.column_config.NumberColumn("Jogos"),
        "goals_for": st.column_config.ProgressColumn("Gols Pró", format="%d", min_value=0, max_value=int(df_agg["goals_for"].max())),
        "goals_against": st.column_config.NumberColumn("Gols Contra"),
        "shots_p90": st.column_config.NumberColumn("Chutes/Jogo", format="%.1f"),
        "pass_completion_pct": st.column_config.ProgressColumn("Passe %", format="%.1f%%", min_value=0, max_value=100),
    }
    
    st.dataframe(
        df_agg[display_cols].sort_values("goals_for", ascending=False),
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=600
    )
