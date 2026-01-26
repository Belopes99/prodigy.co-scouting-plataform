import streamlit as st
import pandas as pd
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.bq_io import get_bq_client
from src.queries import get_teams_match_count_query
from src.css import load_css

st.set_page_config(page_title="Diagnóstico de Dados", page_icon="🔧", layout="wide")
load_css()

st.title("🔧 Diagnóstico de Integridade de Dados")
st.markdown("""
Esta ferramenta verifica se todas as equipes possuem **38 jogos** por temporada.
Se houver menos, significa que há jogos faltando na base de dados.
""")

st.divider()

# --- CONFIG ---
PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata"

@st.cache_data(ttl=60)
def load_audit_data():
    client = get_bq_client(project=PROJECT_ID)
    query = get_teams_match_count_query(PROJECT_ID, DATASET_ID)
    df = client.query(query).to_dataframe()
    return df

try:
    with st.spinner("Auditando base de dados..."):
        df = load_audit_data()
except Exception as e:
    st.error(f"Erro ao auditar dados: {e}")
    st.stop()

if df.empty:
    st.info("Nenhum dado encontrado.")
    st.stop()

# --- LOGIC ---
# Highlight logic
def highlight_rows(row):
    # Rule: If season is completed (<= 2024 for example), it MUST be 38.
    # If 2025 (current), it can be anything.
    # Let's assume 2024 passed.
    
    season = row['season']
    games = row['total_games']
    
    current_season = 2025 # Or dynamic
    
    if season < current_season and games != 38:
        return ['background-color: #551111'] * len(row)
    elif season < current_season and games == 38:
        return ['background-color: #113311'] * len(row)
    return [''] * len(row)

st.subheader("Relatório de Jogos por Equipe/Temporada")

# Filter options
seasons = sorted(df['season'].unique(), reverse=True)
sel_season = st.multiselect("Filtrar Temporadas", seasons, default=seasons[:1])

if sel_season:
    df_show = df[df['season'].isin(sel_season)]
else:
    df_show = df

# Metrics
c1, c2 = st.columns(2)
problems = df_show[ (df_show['season'] < 2025) & (df_show['total_games'] != 38) ]
c1.metric("Registros Analisados", len(df_show))
c2.metric("Inconsistências Encontradas (< 2025)", len(problems), delta_color="inverse")

if not problems.empty:
    st.warning(f"⚠️ Atenção! Encontradas {len(problems)} equipes com número de jogos diferente de 38 em temporadas passadas.")

st.dataframe(
    df_show.style.apply(highlight_rows, axis=1),
    use_container_width=True,
    height=800
)
