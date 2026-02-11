from __future__ import annotations

from typing import List, Tuple, Optional
import io
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
from google.cloud import bigquery

# from src.ui_filters import render_sidebar_globals (Removed)
from src.bq_io import get_bq_client
from src.css import load_css
from src.plots import plot_events_plotly

# Carrega CSS Premium
load_css()

# =========================================
# CONFIG BQ
# =========================================

PROJECT = "betterbet-467621"
DATASET = "betterdata"

EVENTS_PREFIX = "eventos_brasileirao_serie_a"
SCHEDULE_PREFIX = "schedule_brasileirao_serie_a"

# Fundo do PNG exportado (para não “sumir” no download)
EXPORT_BG = "#0e1117"

# =========================================
# PITCH CONFIG
# =========================================

PITCH_LENGTH = 105.0  # metros
PITCH_WIDTH = 68.0    # metros

# =========================================
# SQL HELPERS
# =========================================


def fq_table(prefix: str, year: int) -> str:
    return f"`{PROJECT}.{DATASET}.{prefix}_{int(year)}`"


def _union_schedule_years(years: List[int]) -> str:
    parts = []
    for y in years:
        parts.append(f"SELECT home_team, away_team FROM {fq_table(SCHEDULE_PREFIX, y)}")
    return "\nUNION ALL\n".join(parts)


@st.cache_data(ttl=3600)
def load_teams_for_years(years: Tuple[int, ...]) -> List[str]:
    years_list = list(years)
    sql = f"""
    WITH s AS (
      {_union_schedule_years(years_list)}
    )
    SELECT DISTINCT team
    FROM (
      SELECT home_team AS team FROM s
      UNION DISTINCT
      SELECT away_team AS team FROM s
    )
    WHERE team IS NOT NULL
    ORDER BY team
    """
    df = run_query(sql)
    return df["team"].dropna().astype(str).tolist()


def union_sql(prefix: str, years: Tuple[int, ...], select_clause: str) -> str:
    return "\nUNION ALL\n".join(
        f"{select_clause} FROM {fq_table(prefix, y)}" for y in years
    )


def run_query(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    client = get_bq_client(project=PROJECT)
    cfg = bigquery.QueryJobConfig(query_parameters=params or [])
    return client.query(sql, job_config=cfg).to_dataframe()


@st.cache_data(ttl=3600)
def detect_match_id_col(prefix: str, year: int) -> str:
    client = get_bq_client(project=PROJECT)
    table_id = f"{PROJECT}.{DATASET}.{prefix}_{int(year)}"
    schema = client.get_table(table_id).schema
    cols = [f.name for f in schema]

    candidates = [
        "game_id", "gameId",
        "match_id", "matchId", "matchID",
        "fixture_id", "fixtureId",
        "id", "Id",
    ]

    for c in candidates:
        if c in cols:
            return c

    for c in cols:
        lc = c.lower()
        if "game" in lc and "id" in lc:
            return c
        if "match" in lc and "id" in lc:
            return c
        if "fixture" in lc and "id" in lc:
            return c

    raise ValueError(
        f"Não consegui detectar a coluna de ID da partida em {table_id}. Colunas: {cols}"
    )


# =========================================
# HELPER FUNCTIONS REMOVED (Legacy Matplotlib code removed for Plotly upgrade)
# =========================================

# (Coordinates helpers kept if needed)
def _scale_series_to_0_100(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    vv = s.dropna()
    if len(vv) > 0 and (vv.between(0, 1).mean() > 0.95):
        return s * 100.0
    return s


def apply_attack_orientation(
    df: pd.DataFrame,
    focus_teams: Tuple[str, ...],
    x_col: str = "x_plot",
    y_col: str = "y_plot",
    endx_col: str = "end_x_plot",
    endy_col: str = "end_y_plot",
) -> pd.DataFrame:
    out = df.copy()

    if "team" not in out.columns:
        return out

    L = PITCH_LENGTH
    W = PITCH_WIDTH

    teams_set = set(map(str, focus_teams))
    mask_opp = ~out["team"].astype(str).isin(teams_set)

    if x_col in out.columns:
        out.loc[mask_opp, x_col] = L - out.loc[mask_opp, x_col]
    if y_col in out.columns:
        out.loc[mask_opp, y_col] = W - out.loc[mask_opp, y_col]

    if endx_col in out.columns and endy_col in out.columns:
        out.loc[mask_opp, endx_col] = L - out.loc[mask_opp, endx_col]
        out.loc[mask_opp, endy_col] = W - out.loc[mask_opp, endy_col]

    return out


# =========================================
# FILTER HELPERS
# =========================================


def match_label(row: pd.Series) -> str:
    dt = row.get("start_time", None)
    try:
        dt = pd.to_datetime(dt, errors="coerce", utc=True)
        dt_str = dt.tz_convert("America/Sao_Paulo").strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else "sem data"
    except Exception:
        dt_str = "sem data"
    return f"{dt_str} • {row.get('home_team','?')} vs {row.get('away_team','?')} • match_id={int(row['match_id'])}"


def infer_opponents(df_matches: pd.DataFrame, teams: Tuple[str, ...]) -> List[str]:
    if df_matches.empty:
        return []

    teams_set = set(teams)
    opps = set()

    for r in df_matches.itertuples(index=False):
        if getattr(r, "home_team", None) in teams_set and pd.notna(getattr(r, "away_team", None)):
            opps.add(str(r.away_team))
        if getattr(r, "away_team", None) in teams_set and pd.notna(getattr(r, "home_team", None)):
            opps.add(str(r.home_team))

    return sorted(opps)


# =========================================
# LOADERS (cached)
# =========================================


@st.cache_data(ttl=900)
def load_matches(
    years: Tuple[int, ...],
    teams: Tuple[str, ...],
    home_away: Tuple[str, ...],
    sched_match_id_col: str,
) -> pd.DataFrame:
    schedule_union = union_sql(
        SCHEDULE_PREFIX,
        years,
        f"SELECT {sched_match_id_col} AS match_id, start_time, home_team, away_team",
    )

    where = ["(home_team IN UNNEST(@teams) OR away_team IN UNNEST(@teams))"]
    params = [bigquery.ArrayQueryParameter("teams", "STRING", list(teams))]

    if home_away:
        clauses = []
        if "Home" in home_away:
            clauses.append("(home_team IN UNNEST(@teams))")
        if "Away" in home_away:
            clauses.append("(away_team IN UNNEST(@teams))")
        if clauses:
            where.append("(" + " OR ".join(clauses) + ")")

    sql = f"""
    WITH s AS (
      {schedule_union}
    )
    SELECT match_id, start_time, home_team, away_team
    FROM s
    WHERE {" AND ".join(where)}
    ORDER BY start_time DESC
    """

    df = run_query(sql, params)

    if "start_time" in df.columns:
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce", utc=True)

    df["match_id"] = pd.to_numeric(df["match_id"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["match_id"])
    df["match_id"] = df["match_id"].astype("int64")

    return df


@st.cache_data(ttl=900)
def load_event_types(
    years: Tuple[int, ...],
    teams: Tuple[str, ...],
    match_ids: Tuple[int, ...],
    events_match_id_col: str,
) -> List[str]:
    events_union = union_sql(
        EVENTS_PREFIX,
        years,
        f"SELECT {events_match_id_col} AS match_id, team, type",
    )

    where = ["type IS NOT NULL", "team IN UNNEST(@teams)"]
    params = [bigquery.ArrayQueryParameter("teams", "STRING", list(teams))]

    if match_ids:
        where.append("match_id IN UNNEST(@match_ids)")
        params.append(bigquery.ArrayQueryParameter("match_ids", "INT64", [int(x) for x in match_ids]))

    sql = f"""
    WITH e AS ({events_union})
    SELECT DISTINCT type
    FROM e
    WHERE {" AND ".join(where)}
    ORDER BY type
    """

    df = run_query(sql, params)
    return df["type"].dropna().astype(str).tolist()


@st.cache_data(ttl=900)
def load_outcomes(
    years: Tuple[int, ...],
    teams: Tuple[str, ...],
    match_ids: Tuple[int, ...],
    event_types: Tuple[str, ...],
    events_match_id_col: str,
) -> List[str]:
    events_union = union_sql(
        EVENTS_PREFIX,
        years,
        f"SELECT {events_match_id_col} AS match_id, team, type, outcome_type",
    )

    where = ["outcome_type IS NOT NULL", "team IN UNNEST(@teams)"]
    params = [bigquery.ArrayQueryParameter("teams", "STRING", list(teams))]

    if match_ids:
        where.append("match_id IN UNNEST(@match_ids)")
        params.append(bigquery.ArrayQueryParameter("match_ids", "INT64", [int(x) for x in match_ids]))

    if event_types:
        where.append("type IN UNNEST(@types)")
        params.append(bigquery.ArrayQueryParameter("types", "STRING", list(event_types)))

    sql = f"""
    WITH e AS ({events_union})
    SELECT DISTINCT outcome_type
    FROM e
    WHERE {" AND ".join(where)}
    ORDER BY outcome_type
    """

    df = run_query(sql, params)
    return df["outcome_type"].dropna().astype(str).tolist()


@st.cache_data(ttl=900)
def load_players(
    years: Tuple[int, ...],
    teams: Tuple[str, ...],
    match_ids: Tuple[int, ...],
    event_types: Tuple[str, ...],
    events_match_id_col: str,
) -> pd.DataFrame:
    events_union = union_sql(
        EVENTS_PREFIX,
        years,
        f"""
        SELECT
          {events_match_id_col} AS match_id,
          team,
          type,
          CAST(player_id AS INT64) AS player_id,
          CAST(player AS STRING) AS player_name
        """,
    )

    where = ["player_id IS NOT NULL", "team IN UNNEST(@teams)"]
    params = [bigquery.ArrayQueryParameter("teams", "STRING", list(teams))]

    if match_ids:
        where.append("match_id IN UNNEST(@match_ids)")
        params.append(bigquery.ArrayQueryParameter("match_ids", "INT64", [int(x) for x in match_ids]))

    if event_types:
        where.append("type IN UNNEST(@types)")
        params.append(bigquery.ArrayQueryParameter("types", "STRING", list(event_types)))

    sql = f"""
    WITH e AS ({events_union})
    SELECT
      player_id,
      ANY_VALUE(player_name) AS player_name
    FROM e
    WHERE {" AND ".join(where)}
    GROUP BY player_id
    ORDER BY player_name, player_id
    """

    df = run_query(sql, params)
    if df.empty:
        return df

    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["player_id"]).copy()
    df["player_id"] = df["player_id"].astype("int64")
    df["player_name"] = df["player_name"].fillna("").astype(str).str.strip()

    return df


@st.cache_data(ttl=300)
def load_events_filtered(
    years: Tuple[int, ...],
    teams: Tuple[str, ...],
    match_ids: Tuple[int, ...],
    minute_range: Tuple[int, int],
    event_types: Tuple[str, ...],
    outcomes: Tuple[str, ...],
    player_ids: Tuple[int, ...],
    limit_rows: int,
    events_match_id_col: str,
) -> pd.DataFrame:
    events_union = union_sql(
        EVENTS_PREFIX,
        years,
        f"""
        SELECT
          {events_match_id_col} AS match_id,
          expanded_minute,
          type,
          outcome_type,
          team,
          CAST(player_id AS INT64) AS player_id,
          CAST(player AS STRING) AS player,
          x, y, end_x, end_y, qualifiers
        """,
    )

    where = [
        "team IN UNNEST(@teams)",
        "expanded_minute BETWEEN @m0 AND @m1",
    ]

    params: list = [
        bigquery.ArrayQueryParameter("teams", "STRING", list(teams)),
        bigquery.ScalarQueryParameter("m0", "INT64", int(minute_range[0])),
        bigquery.ScalarQueryParameter("m1", "INT64", int(minute_range[1])),
        bigquery.ScalarQueryParameter("lim", "INT64", int(limit_rows)),
    ]

    if match_ids:
        where.append("match_id IN UNNEST(@match_ids)")
        params.append(bigquery.ArrayQueryParameter("match_ids", "INT64", [int(x) for x in match_ids]))

    if event_types:
        where.append("type IN UNNEST(@types)")
        params.append(bigquery.ArrayQueryParameter("types", "STRING", list(event_types)))

    if outcomes:
        where.append("outcome_type IN UNNEST(@outs)")
        params.append(bigquery.ArrayQueryParameter("outs", "STRING", list(outcomes)))

    if player_ids:
        where.append("player_id IN UNNEST(@pids)")
        params.append(bigquery.ArrayQueryParameter("pids", "INT64", [int(x) for x in player_ids]))

    sql = f"""
    WITH e AS ({events_union})
    SELECT *
    FROM e
    WHERE {" AND ".join(where)}
    LIMIT @lim
    """

    df = run_query(sql, params)

    # Parse qualifiers if present
    if not df.empty and "qualifiers" in df.columns:
        import ast

        def parse_quals(q_str):
            try:
                # Se for nulo ou vazio
                if pd.isna(q_str) or not q_str:
                    return []
                # Tenta converter string python/json para lista
                # O CSV mostra aspas simples: [{'type':...}] -> python syntax
                raw_list = ast.literal_eval(q_str)
                if not isinstance(raw_list, list):
                    return []
                
                # Extrai apenas os displayNames
                # Exemplo structure: {'type': {'displayName': 'Zone'}, 'value': 'Back'}
                tags = []
                for item in raw_list:
                    t = item.get("type", {})
                    dn = t.get("displayName")
                    if dn:
                        tags.append(dn)
                return tags
            except Exception:
                return []

        # Aplica a conversão
        df["kv_qualifiers"] = df["qualifiers"].apply(parse_quals)

    return df


# =========================================
# PAGE
# =========================================

# =========================================
# PAGE
# =========================================

st.set_page_config(page_title="Eventos", layout="wide")
load_css() # Re-inject CSS

st.title("Eventos • Análise Interativa")

with st.sidebar:
    if st.button("🔄 Limpar Cache (Atualizar Dados)"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

# --- FILTROS DE DADOS (Topo da página) ---
c_y, c_t = st.columns([1, 3])

with c_y:
    all_years = list(range(2015, 2027))
    years_sel = st.multiselect("Temporada(s)", all_years, default=[2026])
    if not years_sel:
        years_sel = [2026] # Fallback visual
    
    # Ordena e converte para tupla para cache
    years_t = tuple(sorted(set(int(y) for y in years_sel)))

with c_t:
    teams_all = load_teams_for_years(years_t)
    teams_sel = st.multiselect("Time(s)", teams_all, default=teams_all[:1] if teams_all else [])

if not years_sel or not teams_sel:
    st.info("👆 Selecione Temporada e Time para começar.")
    st.stop()

teams_t = tuple(sorted(set(str(t) for t in teams_sel)))

try:
    SCHED_MATCH_ID_COL = detect_match_id_col(SCHEDULE_PREFIX, years_t[0])
    EVENTS_MATCH_ID_COL = detect_match_id_col(EVENTS_PREFIX, years_t[0])
except Exception as e:
    st.error(f"Erro ao detectar schema: {str(e)}")
    st.stop()

st.divider()
st.subheader("Filtros de Jogo & Eventos")

c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.0])

with c1:
    minute_range = st.slider("Minutos", 0, 120, (0, 120))

with c2:
    home_away = st.multiselect("Home/Away", ["Home", "Away"], default=["Home", "Away"])

with c3:
    match_mode = st.radio("Partidas", ["Todas", "Escolher (multi)"], horizontal=True)

with c4:
    limit_rows = st.number_input("Limite de eventos", 10_000, 500_000, 200_000, 10_000)

df_matches = load_matches(years_t, teams_t, tuple(home_away), SCHED_MATCH_ID_COL)

if df_matches.empty:
    st.warning("Nenhuma partida encontrada com esses filtros globais + Home/Away.")
    st.stop()

opponents_all = infer_opponents(df_matches, teams_t)
opponents = st.multiselect("Time adversário (opcional)", opponents_all, default=[])

if opponents:
    teams_set = set(teams_t)
    opp_set = set(opponents)

    def ok(r: pd.Series) -> bool:
        ht, at = r["home_team"], r["away_team"]
        return ((ht in teams_set and at in opp_set) or (at in teams_set and ht in opp_set))

    df_matches_eff = df_matches[df_matches.apply(ok, axis=1)].copy()
else:
    df_matches_eff = df_matches.copy()

df_matches_eff["label"] = df_matches_eff.apply(match_label, axis=1)
label_map = dict(zip(df_matches_eff["match_id"].astype("int64"), df_matches_eff["label"]))

match_universe = df_matches_eff["match_id"].dropna().astype("int64").tolist()
match_ids_selected: List[int] = []

if match_mode.startswith("Escolher"):
    match_ids_selected = st.multiselect(
        "Selecione match_id(s)",
        options=match_universe,
        default=match_universe[:1] if match_universe else [],
        format_func=lambda mid: label_map.get(int(mid), str(mid)),
    )

match_ids_effective = tuple(match_ids_selected) if match_ids_selected else tuple(match_universe)

event_types_all = load_event_types(years_t, teams_t, match_ids_effective, EVENTS_MATCH_ID_COL)
default_types = ["Pass"] if "Pass" in event_types_all else (event_types_all[:1] if event_types_all else [])
event_types = st.multiselect("Tipo(s) de evento", event_types_all, default=default_types)

outcomes_all = load_outcomes(years_t, teams_t, match_ids_effective, tuple(event_types), EVENTS_MATCH_ID_COL)
outcomes = st.multiselect("Outcome (opcional)", outcomes_all, default=[])

df_players = load_players(years_t, teams_t, match_ids_effective, tuple(event_types), EVENTS_MATCH_ID_COL)
player_options = [
    f"{r.player_name} ({r.player_id})" if r.player_name else f"({r.player_id})"
    for r in df_players.itertuples(index=False)
]
selected_players = st.multiselect("Jogador(es) (opcional)", options=player_options, default=[])

player_ids_sel: List[int] = []
for lab in selected_players:
    try:
        player_ids_sel.append(int(lab.split("(")[-1].split(")")[0]))
    except Exception:
        pass

df_events = load_events_filtered(
    years=years_t,
    teams=teams_t,
    match_ids=match_ids_effective,
    minute_range=(int(minute_range[0]), int(minute_range[1])),
    event_types=tuple(event_types),
    outcomes=tuple(outcomes),
    player_ids=tuple(player_ids_sel),

    limit_rows=int(limit_rows),
    events_match_id_col=EVENTS_MATCH_ID_COL,
)

# =========================================
# FILTRO DE QUALIFIERS (PÓS-QUERY)
# =========================================
if "kv_qualifiers" in df_events.columns and not df_events.empty:
    # Coletar todos os qualifiers únicos da amostra atual
    all_quals = set()
    for q_list in df_events["kv_qualifiers"]:
        all_quals.update(q_list)
    
    sorted_quals = sorted(all_quals)
    
    # Checkbox para habilitar o filtro (para não poluir se não quiser usar)
    # ou direto um multiselect. O multiselect vazio = sem filtro é melhor.
    selected_quals = st.multiselect("Filtrar por Qualifiers (Tags)", sorted_quals, default=[])

    if selected_quals:
        # Se selecionado "BigChance", mantemos linhas que tenham "BigChance"
        # Lógica: OR ou AND? Normalmente usuario quer ver "Cruzamentos" (contem Cross).
        # Se marcar "Cross" e "BigChance", quer eventos que sejam AMBOS? Ou um OU outro?
        # Geralmente OR é mais permissivo, mas para drill-down exato, AND é poderoso.
        # Vamos de "Contém pelo menos um dos selecionados" (OR logic) é mais comum para discovery.
        # Mas para scouting específico ("Chute de cabeça"), seria Shot AND Head.
        
        # Vamos implementar lógica: "Events must have ALL selected tags" (AND) 
        # para permitir queries como "Chute" + "Cabeça" + "BigChance".
        
        filter_set = set(selected_quals)
        
        def check_tags(row_tags):
            return filter_set.issubset(set(row_tags))

        df_events = df_events[df_events["kv_qualifiers"].apply(check_tags)]


st.divider()
st.subheader("Resultados")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Temporadas", ", ".join(map(str, years_t)))
k2.metric("Times", ", ".join(teams_t))
k3.metric("Partidas (c/ filtro)", f"{df_events['match_id'].nunique()} / {len(match_ids_effective)}")
k4.metric("Eventos retornados", f"{len(df_events):,}".replace(",", "."))

if df_events.empty:
    st.warning("Nenhum evento retornado. Ajuste filtros.")
    st.stop()

cols_pref = ["match_id", "expanded_minute", "type", "outcome_type", "team", "player_id", "player", "x", "y", "end_x", "end_y"]
cols_show = [c for c in cols_pref if c in df_events.columns] + [c for c in df_events.columns if c not in cols_pref]
st.dataframe(df_events[cols_show].head(500), use_container_width=True)

st.divider()
st.subheader("Mapa de eventos (campo)")

g1, g2, g3 = st.columns([1.2, 1.2, 1.0])

with g1:
    draw_arrows = st.checkbox(
        "Desenhar Setas (Ponto Final do Evento)",
        value=("end_x" in df_events.columns and "end_y" in df_events.columns),
    )

with g2:
    color_by_outcome = st.checkbox(
        "Colorir por Sucesso do Evento",
        value=("outcome_type" in df_events.columns),
    )

with g3:
    sample_n = st.number_input("Amostra p/ plot", min_value=200, max_value=20000, value=3000, step=200)

    highlight_qualifier = None
    if "kv_qualifiers" in df_events.columns and not df_events.empty:
        # Tenta reusar sorted_quals se definido anteriormente
        opts = []
        if 'sorted_quals' in locals():
            opts = sorted_quals
        else:
            all_q = set()
            for q_list in df_events["kv_qualifiers"]:
                all_q.update(q_list)
            opts = sorted(all_q)
        
        if opts:
            highlight_qualifier = st.selectbox("Destacar Qualifier (Opcional)", ["Nenhum"] + opts, index=0)
            if highlight_qualifier == "Nenhum":
                highlight_qualifier = None

    # New Highlight Type
    highlight_type = st.selectbox("Destacar Tipo (Opcional)", ["Nenhum"] + list(event_types), index=0)
    if highlight_type == "Nenhum":
        highlight_type = None

with st.expander("Estilo do mapa (campo)", expanded=False):
    c1s, c2s = st.columns(2)

    with c1s:
        pitch_line_color = st.color_picker("Cor das linhas do campo", "#9aa0a6")
        transparent_bg = st.checkbox("Fundo transparente", value=True)
        if transparent_bg:
            fig_bg = "none"
        else:
            fig_bg = st.color_picker("Cor de fundo (figura)", "#0e1117")

    with c2s:
        event_color = st.color_picker("Cor dos eventos (geral)", "#c9cdd1")
        ok_color = st.color_picker("Cor Successful", "#7CFC98")
        bad_color = st.color_picker("Cor Unsuccessful", "#FF6B6B")
        highlight_color = st.color_picker("Cor Destaque (Highlight)", "#FFD700")

    st.divider()
    color_strategy = st.selectbox(
        "Estratégia de Cores",
        ["Resultado (Sucesso/Falha)", "Tipo de Evento", "Equipe", "Jogador", "Cor Única"],
        index=0
    )

    clean_layer_colors = {}

    if color_strategy == "Tipo de Evento":
        if not event_types:
            st.info("Selecione pelo menos um Tipo de Evento nos filtros acima.")
        else:
            for etype in event_types:
                st.markdown(f"**{etype}**")
                c1, c2, c3 = st.columns(3)
                clean_layer_colors[etype] = {
                    "base": c1.color_picker(f"Base", event_color, key=f"base_{etype}"),
                    "ok": c2.color_picker(f"Sucesso", ok_color, key=f"ok_{etype}"),
                    "bad": c3.color_picker(f"Falha", bad_color, key=f"bad_{etype}")
                }
    
    elif color_strategy == "Equipe":
        if not teams_t:
            st.info("Selecione Times nos filtros.")
        else:
            for team_name in teams_t:
                st.markdown(f"**{team_name}**")
                c1, c2, c3 = st.columns(3)
                clean_layer_colors[team_name] = {
                    "base": c1.color_picker(f"Base", event_color, key=f"base_{team_name}"),
                    "ok": c2.color_picker(f"Sucesso", ok_color, key=f"ok_{team_name}"),
                    "bad": c3.color_picker(f"Falha", bad_color, key=f"bad_{team_name}")
                }

    elif color_strategy == "Jogador":
        # Extract names from selected_players strings like "Hulk (123)"
        if not selected_players:
            st.info("Selecione Jogadores nos filtros para customizar cores.")
        else:
            for p_str in selected_players:
                st.markdown(f"**{p_str}**")
                c1, c2, c3 = st.columns(3)
                # Map using the full string as key for simplicity
                clean_layer_colors[p_str] = {
                    "base": c1.color_picker(f"Base", event_color, key=f"base_{p_str}"),
                    "ok": c2.color_picker(f"Sucesso", ok_color, key=f"ok_{p_str}"),
                    "bad": c3.color_picker(f"Falha", bad_color, key=f"bad_{p_str}")
                }


style = {
    "pitch_line_color": pitch_line_color,
    "fig_bg": fig_bg,
    "event_color": event_color,
    "ok_color": ok_color,
    "bad_color": bad_color,
    "highlight_color": highlight_color,
}

needed = {"x", "y"}
if not needed.issubset(df_events.columns):
    st.warning("Este dataset não tem colunas x/y para desenhar o mapa.")
    st.stop()

plot_df = df_events.copy()

for c in ["x", "y", "end_x", "end_y"]:
    if c in plot_df.columns:
        plot_df[c] = pd.to_numeric(plot_df[c], errors="coerce")

plot_df = plot_df.dropna(subset=["x", "y"])

if len(plot_df) > int(sample_n):
    # Smart Sampling: Se houver destaque, priorizar esses eventos
    has_hq = highlight_qualifier and "kv_qualifiers" in plot_df.columns
    has_ht = highlight_type and "type" in plot_df.columns

    if has_hq or has_ht:
        def is_priority(row):
            p = False
            if has_hq: p = p or (highlight_qualifier in row["kv_qualifiers"])
            if has_ht: p = p or (row["type"] == highlight_type)
            return p
        
        # Filtra prioritários
        priority_mask = plot_df.apply(is_priority, axis=1)
        priority_df = plot_df[priority_mask]
        background_df = plot_df[~priority_mask]
        
        n_priority = len(priority_df)
        limit = int(sample_n)
        
        
        if n_priority >= limit:
            # Temos mais destaques que o limite -> amostra dos destaques
            plot_df = priority_df.sample(limit, random_state=42)
        else:
            # Temos espaço para todos os destaques + fundo
            n_remaining = limit - n_priority
            # Garante que não tiramos mais do que existe no fundo
            if len(background_df) > n_remaining:
                background_sampled = background_df.sample(n_remaining, random_state=42)
                plot_df = pd.concat([priority_df, background_sampled])
            else:
                # Se sobrar espaço (caso raro onde len total > limit mas logica falha), pega tudo
                plot_df = pd.concat([priority_df, background_df])
    else:
        # Sem destaque, sample aleatório simples
        plot_df = plot_df.sample(int(sample_n), random_state=42)

# Converte coords do dataset (0..100) para o campo real (105x68)
plot_df["x_plot"] = _scale_series_to_0_100(plot_df["x"]) * (PITCH_LENGTH / 100.0)
plot_df["y_plot"] = _scale_series_to_0_100(plot_df["y"]) * (PITCH_WIDTH / 100.0)

if "end_x" in plot_df.columns and "end_y" in plot_df.columns:
    plot_df["end_x_plot"] = _scale_series_to_0_100(plot_df["end_x"]) * (PITCH_LENGTH / 100.0)
    plot_df["end_y_plot"] = _scale_series_to_0_100(plot_df["end_y"]) * (PITCH_WIDTH / 100.0)

plot_df = apply_attack_orientation(plot_df, focus_teams=teams_t)

# =========================================
# PLOTLY (PREMIUM)
# =========================================

# Tema de cores unificado
theme_colors = {
    "pitch_line_color": pitch_line_color,
    "fig_bg": fig_bg if not transparent_bg else "rgba(0,0,0,0)",
    "event_color": event_color,
    "ok_color": ok_color,
    "bad_color": bad_color,
    "highlight_color": highlight_color,
}

# =========================================
# LAYOUT MAPA + ESTATÍSTICAS
# =========================================

c_map, c_stats = st.columns([3, 1])

with c_map:
    # Gera o gráfico
    # Gera o gráfico
    try:
        fig_plotly = plot_events_plotly(
            df=plot_df,
            pitch_length=PITCH_LENGTH,
            pitch_width=PITCH_WIDTH,
            color_outcome=bool(color_by_outcome),
            draw_arrows=bool(draw_arrows),
            highlight_qualifier=highlight_qualifier,
            highlight_type=highlight_type, # NEW
            theme_colors=theme_colors,
            color_strategy=color_strategy,
            layer_colors=clean_layer_colors
        )
    except TypeError:
        # Fallback for stale cache (module not reloaded yet)
        if highlight_type:
             st.warning("⚠️ Cache desatualizado: O destaque de Tipo não pôde ser aplicado. Por favor, limpe o cache e recarregue a página (Sidebar > Limpar Cache).")
        
        fig_plotly = plot_events_plotly(
            df=plot_df,
            pitch_length=PITCH_LENGTH,
            pitch_width=PITCH_WIDTH,
            color_outcome=bool(color_by_outcome),
            draw_arrows=bool(draw_arrows),
            highlight_qualifier=highlight_qualifier,
            # highlight_type omitted
            theme_colors=theme_colors,
            color_strategy=color_strategy,
            layer_colors=clean_layer_colors
        )
    st.plotly_chart(fig_plotly, use_container_width=True, theme=None)

with c_stats:
    st.markdown("### Estatísticas da Amostra")
    
    total = len(plot_df)
    st.metric("Total de Eventos", f"{total}")
    
    st.divider()
    
    # 1. Por Outcome
    if "outcome_type" in plot_df.columns:
        succ = plot_df[plot_df["outcome_type"] == "Successful"]
        fail = plot_df[plot_df["outcome_type"] != "Successful"]
        
        c_s, c_f = st.columns(2)
        with c_s:
            st.metric("Sucesso", f"{len(succ)}")
        with c_f:
            st.metric("Falha", f"{len(fail)}")
            
        rate = (len(succ) / total * 100) if total > 0 else 0
        st.progress(rate / 100, text=f"Taxa de Acerto: {rate:.1f}%")
        
    st.divider()

    # 2. Por Qualifier (Destaque)
    if highlight_qualifier and "kv_qualifiers" in plot_df.columns:
        def has_qa(tags):
            return highlight_qualifier in tags
        n_high = plot_df["kv_qualifiers"].apply(has_qa).sum()
        
        st.metric(f"Com '{highlight_qualifier}'", f"{n_high}")
        
    elif not highlight_qualifier:
        st.info("Selecione um Qualifier para ver a contagem específica.")
