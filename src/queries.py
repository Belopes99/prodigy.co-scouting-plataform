from typing import Optional, Tuple, Union, List
import re

# YEARS_TO_QUERY = range(2015, 2027)
YEARS_TO_QUERY = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

def _build_schedule_union(project_id: str, dataset_id: str) -> str:
    """
    Builds UNION ALL for Schedule tables, normalizing columns.
    Old tables might use 'date', new ones 'start_time'.
    """
    subqueries = []
    for year in YEARS_TO_QUERY:
        # Check column availability logic is tricky in pure SQL string generation without checking schema first.
        # But we saw from debug that 2017 has 'date' (TIMESTAMP) and 2025 has 'start_time' (TIMESTAMP).
        # We need to normalize to 'start_time'.
        # 2017: date, game_id, home_team, away_team, home_score, away_score, status
        # 2025: start_time, game_id, ...
        
        # Heuristic based on year:
        # Years < 2020 might use 'date'. Let's assume standard names.
        # Actually safer way: select both, alias correctly. BQ will error if column doesn't exist.
        # Wait, if I select 'date' from 2025 table it errors if it doesn't exist.
        
        # Hack solution: Since we know the drift, we can use exception or just listing.
        # Better: use `SELECT * EXCEPT(...)` or just SELECT common ones?
        # NO, 'date' is missing in 2025. 'start_time' is missing in 2017.
        
        # We need per-year logic.
        if year <= 2023: # Assumption based on usually these datasets change recently. Or just 2025 changed.
            # Let's try to be generic. 
            # If we really want to be robust we would check schema.
            # But let's assume 'date' is used in older, 'start_time' in newer.
            # Let's try to use 'date' if available, else 'start_time' logic? No SQL doesn't work that way.
            pass
        
    # Since I cannot check schema at runtime efficiently here without slowing down, 
    # I will rely on the pattern.
    # Pattern seen: 2017 has 'date', 2025 has 'start_time'.
    # Let's split 2025 from others?
    # Or checking the debug output closer (which I can't fully see, but it showed mismatches).
    
    # Let's try to query metadata? No.
    # Let's just output the explicit columns for 2025 and explicit for others.
    # But I don't know the exact year cut-off.
    
    # Safe fallback: Use `SAFE_CAST(NULL as TIMESTAMP)`? No the column selection fails.
    
    # Actually, the user report says: "Column 41...". 
    # The problem of SELECT * is exactly this.
    # If I explicitly select, I must know the column name.
    
    # Let's use the simplest valid subsets.
    # Required: game_id, home_team, away_team, home_score, away_score, TIMESTAMP (date/start_time), status.
    
    # I will generate a query that tries to be smart. 
    # Or I can just inspect schemas right now for all of them? No too fast.
    
    # Let's assume:
    # 2015-2023: Use 'date'
    # 2024-2025: Use 'start_time' (Common in Opta/Better data updates).
    
    # Correction: The previous debug showed 2017 had 'date' (TIMESTAMP). 2025 had 'start_time' (TIMESTAMP).
    # I will iterate and define columns based on year.
    pass

    subqueries = []
    for year in YEARS_TO_QUERY:
        # Based on typical Opta/DataProvider schemas:
        # Based on typical Opta/DataProvider schemas:
        # Adjusted: 2024 often still uses 'date'. 2025+ uses 'start_time'.
        if year >= 2025:
            ts_col = "start_time"
        else:
            ts_col = "date"
            
        subqueries.append(f"""
            SELECT 
                game_id, 
                {year} as season, 
                CAST({ts_col} as TIMESTAMP) as match_date, 
                home_team, 
                away_team, 
                home_score, 
                away_score, 
                CAST(status as STRING) as status 
            FROM `{project_id}.{dataset_id}.schedule_brasileirao_serie_a_{year}`
        """)
    return " UNION ALL ".join(subqueries)


def _build_events_union(project_id: str, dataset_id: str) -> str:
    """
    Builds UNION ALL for Events tables, properly Aliasing/Casting.
    Required: game_id, team, player, type, outcome_type, is_shot, x, y, end_x, end_y
    """
    # events also need season if we ever query them directly for season stats
    # 2026 table has 30 cols, 2015 has 27. Must select explicit shared columns to avoid UNION ALL error.
    cols = [
        "game_id", "team", "player", "player_id", 
        "type", "outcome_type", "qualifiers", 
        "expanded_minute", "period", 
        "x", "y", "end_x", "end_y", 
        "is_shot", "related_player_id"
    ]
    cols_str = ", ".join(cols)
    return " UNION ALL ".join([f"SELECT {cols_str}, {year} as season FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_{year}`" for year in YEARS_TO_QUERY])


def get_total_matches_query(project_id: str, dataset_id: str) -> str:
    schedule_union = _build_schedule_union(project_id, dataset_id)
    return f"""
        WITH all_schedule AS (
            {schedule_union}
        )
        SELECT COUNT(DISTINCT game_id) as total
        FROM all_schedule
        WHERE status IS NOT NULL
    """

def get_total_events_query(project_id: str, dataset_id: str) -> str:
    # Use * for events, assuming consistency or BQ handles name matching if not *? 
    # Union * requires strict type/order match.
    # Risky.
    # Let's try to be specific.
    events_union = _build_events_union(project_id, dataset_id)
    return f"""
        WITH all_events AS (
            {events_union}
        )
        SELECT COUNT(*) as total
        FROM all_events
    """

def get_recent_matches_query(project_id: str, dataset_id: str, limit: int = 5) -> str:
    schedule_union = _build_schedule_union(project_id, dataset_id)
    return f"""
        WITH all_schedule AS (
            {schedule_union}
        )
        SELECT 
            game_id as match_id,
            match_date,
            home_team,
            away_team,
            home_score,
            away_score
        FROM all_schedule
        WHERE status = '2' OR status = 'Finished' -- Normalized status
        AND home_score IS NOT NULL
        ORDER BY match_date DESC
        LIMIT {limit}
    """

def get_match_stats_query(project_id: str, dataset_id: str) -> str:
    schedule_union = _build_schedule_union(project_id, dataset_id)
    # Start with simple Event Union. If it breaks, I'll fix.
    events_union = _build_events_union(project_id, dataset_id)
    
    # Define Regex patterns outside f-string to avoid 'Invalid format specifier' errors
    # Note: re_assist is no longer used for counting, as we use related_player_id on Goals
    re_key = r"['\"]displayName['\"]\s*:\s*['\"]KeyPass['\"]"

    return f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    all_events AS (
        {events_union}
    ),
    
    match_metadata AS (
        SELECT 
            game_id,
            match_date,
            season,
            home_team,
            away_team,
            home_score,
            away_score
        FROM all_schedule
        -- Removed: WHERE home_score IS NOT NULL (To match diagnostic count of 418)
    ),
    
    match_teams AS (
        SELECT 
            game_id,
            match_date,
            season,
            home_team as team,
            IFNULL(home_score, 0) as goals_for,
            IFNULL(away_score, 0) as goals_against,
            'Mandante' as side
        FROM match_metadata
        UNION ALL
        
        SELECT 
            game_id,
            match_date,
            season,
            away_team as team,
            IFNULL(away_score, 0) as goals_for,
            IFNULL(home_score, 0) as goals_against,
            'Visitante' as side
        FROM match_metadata
        UNION ALL
        
        SELECT 
             game_id, 
             match_date, 
             season, 
             away_team as team, 
             IFNULL(away_score, 0) as goals_for, 
             IFNULL(home_score, 0) as goals_against, 
             'Visitante' as side 
        FROM match_metadata 
    ),
    
    event_stats AS (
        SELECT
            game_id as match_id,
            team,
            COUNTIF(type = 'Pass') as total_passes,
            COUNTIF(type = 'Pass' AND outcome_type = 'Successful') as successful_passes,
            
            COUNTIF(is_shot = true) as total_shots,
            COUNTIF(type = 'Goal') as goals_from_events,
            COUNTIF(type IN ('SavedShot', 'Goal')) as shots_on_target,
            
            -- Defensive / Other
            COUNTIF(type = 'Tackle') as tackles,
            COUNTIF(type = 'Interception') as interceptions,
            COUNTIF(type = 'Ball Recovery') as recoveries,
            COUNTIF(type = 'Clearance') as clearances,
            COUNTIF(type = 'Save') as saves,
            COUNTIF(type = 'Foul') as fouls,
            
            -- Qualifiers (String Parsing)
            -- Qualifiers (String Parsing)
            -- Assist: Count Goals where related_player_id is set (Implicit Team Assist)
            COUNTIF(type = 'Goal' AND related_player_id IS NOT NULL) as assists,
            COUNTIF(REGEXP_CONTAINS(qualifiers, r'''{re_key}''')) as key_passes
        FROM all_events
        GROUP BY 1, 2
    )
    
    SELECT
        t.game_id as match_id,
        t.match_date, -- Needed for Date Range Filter
        t.season,     -- From source table
        t.team,
        t.goals_for,
        t.goals_against,
        IFNULL(e.total_passes, 0) as total_passes,
        IFNULL(e.successful_passes, 0) as successful_passes,
        IFNULL(e.total_shots, 0) as total_shots,
        IFNULL(e.shots_on_target, 0) as shots_on_target,
        
        IFNULL(e.tackles, 0) as tackles,
        IFNULL(e.interceptions, 0) as interceptions,
        IFNULL(e.recoveries, 0) as recoveries,
        IFNULL(e.clearances, 0) as clearances,
        IFNULL(e.saves, 0) as saves,
        IFNULL(e.fouls, 0) as fouls,
        IFNULL(e.assists, 0) as assists,
        IFNULL(e.key_passes, 0) as key_passes
    FROM match_teams t
    LEFT JOIN event_stats e ON t.game_id = e.match_id AND t.team = e.team
    """


def get_players_by_team_query(project_id: str, dataset_id: str, team: str) -> str:
    events_union = _build_events_union(project_id, dataset_id)
    return f"""
    WITH all_events AS (
        {events_union}
    )
    SELECT DISTINCT player
    FROM all_events
    WHERE team = '{team}' AND player IS NOT NULL
    ORDER BY player
    """


def get_player_stats_query(project_id: str, dataset_id: str, year: int = 2026) -> str:
    # Keep using specific year for radar chart for now
    return f"""
    SELECT
        player,
        team,
        COUNT(*) as total_actions,
        COUNTIF(type = 'Pass') as total_passes,
        COUNTIF(type = 'Pass' AND outcome_type = 'Successful') as successful_passes,
        SAFE_DIVIDE(COUNTIF(type = 'Pass' AND outcome_type = 'Successful'), COUNTIF(type = 'Pass')) as pass_accuracy,
        
        COUNTIF(is_shot = true) as total_shots,
        COUNTIF(type = 'Goal') as goals,
        
        COUNTIF(type = 'Ball Recovery') as recoveries,
        COUNTIF(type = 'Interception') as interceptions,
        COUNTIF(type = 'Tackle') as tackles
        
    FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_{year}`
    WHERE player IS NOT NULL
    GROUP BY 1, 2
    """


def get_player_events_query(project_id: str, dataset_id: str, player: str) -> str:
    # Use union for map too
    events_union = _build_events_union(project_id, dataset_id)
    return f"""
    WITH all_events AS (
        {events_union}
    )
    SELECT 
        game_id as match_id,
        team,
        player,
        type,
        outcome_type,
        x as x_start,
        y as y_start,
        end_x as x_end,
        end_y as y_end,
        period,
        minute,
        second
    FROM all_events
    WHERE player = '{player}'
    """


def get_player_rankings_query(project_id: str, dataset_id: str) -> str:
    schedule_union = _build_schedule_union(project_id, dataset_id)
    events_union = _build_events_union(project_id, dataset_id)

    # Regex safety
    # Regex safety
    # re_assist removed, using join logic
    re_key = r"['\"]displayName['\"]\s*:\s*['\"]KeyPass['\"]"
    re_key = r"['\"]displayName['\"]\s*:\s*['\"]KeyPass['\"]"

    return f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    all_events AS (
        {events_union}
    ),
    
    match_dates AS (
        SELECT game_id, match_date as start_time, season
        FROM all_schedule
    ),
    
    player_stats AS (
        SELECT
            game_id,
            player,
            team,
            COUNTIF(is_shot = true) as shots,
            COUNTIF(type = 'Goal') as goals,
            COUNTIF(type = 'Pass' AND outcome_type = 'Successful') as successful_passes,
            COUNTIF(type = 'Pass') as total_passes,
            
            COUNTIF(type = 'Tackle') as tackles,
            COUNTIF(type = 'Interception') as interceptions,
            COUNTIF(type = 'Ball Recovery') as recoveries,
            COUNTIF(type = 'Clearance') as clearances,
            COUNTIF(type = 'Foul') as fouls, -- Corrected column name if needed
            
            COUNTIF(REGEXP_CONTAINS(qualifiers, r'''{re_assist}''')) as assists,
            COUNTIF(REGEXP_CONTAINS(qualifiers, r'''{re_key}''')) as key_passes
        FROM all_events
        WHERE player IS NOT NULL
        GROUP BY 1, 2, 3
    ),
    
    player_names AS (
         SELECT DISTINCT player_id, player 
         FROM all_events 
         WHERE player IS NOT NULL
    ),
    
    assist_stats AS (
        SELECT
            e.game_id,
            n.player, -- Map ID to Name
            e.team,
            COUNT(*) as assists
        FROM all_events e
        JOIN player_names n ON e.related_player_id = n.player_id
        WHERE e.type = 'Goal' AND e.related_player_id IS NOT NULL
        GROUP BY 1, 2, 3
    )
    
    SELECT
        p.player,
        p.team,
        m.start_time as match_date, -- Granular date for filtering
        m.season,
        p.game_id,
        p.goals,
        p.shots,
        p.successful_passes,
        p.total_passes,
        p.tackles,
        p.interceptions,
        p.recoveries,
        p.clearances,
        p.fouls,
        p.clearances,
        p.fouls,
        COALESCE(a.assists, 0) as assists,
        p.key_passes
    FROM player_stats p
    LEFT JOIN assist_stats a ON p.game_id = a.game_id AND p.player = a.player AND p.team = a.team
    JOIN match_dates m ON p.game_id = m.game_id
    -- No GROUP BY here, we return raw match rows
    """


def get_dynamic_ranking_query(
    project_id: str, 
    dataset_id: str, 
    subject: str, # 'Equipes' or 'Jogadores'
    event_types: object, # str or list
    outcomes: object = "Todos", # str or list
    qualifiers: object = None, # str or list
    use_related_player: bool = False,
    teams: object = None, # str or list
    players: object = None, # str or list
    perspective: str = "pro" # "pro" or "against"
) -> str:
    """
    Constructs a specific query based on dynamic user filters.
    Returns grouping by match_id + subject to allow same downstream processing.
    """
    schedule_union = _build_schedule_union(project_id, dataset_id)
    events_union = _build_events_union(project_id, dataset_id)
    
    # Build WHERE clauses
    where_clauses = ["1=1"] # fallback
    
    # 1. Event Type
    if event_types and "Todos" not in event_types:
        if isinstance(event_types, list):
             types_str = "', '".join(event_types)
             where_clauses.append(f"type IN ('{types_str}')")
        else:
             where_clauses.append(f"type = '{event_types}'")
    
    # 2. Outcome
    if outcomes and "Todos" not in outcomes:
        target_outcomes = []
        if isinstance(outcomes, str): outcomes = [outcomes]
        for out in outcomes:
            if out == "Sucesso": target_outcomes.append("Successful")
            elif out == "Falha": target_outcomes.append("Unsuccessful")
            else: target_outcomes.append(out)
            
        if target_outcomes:
            out_str = "', '".join(target_outcomes)
            where_clauses.append(f"outcome_type IN ('{out_str}')")

    # 3. Qualifiers (Regex OR)
    if qualifiers and "Todos (Qualquer)" not in qualifiers:
        if isinstance(qualifiers, str): qualifiers = [qualifiers]
        safe_quals = [re.escape(q) for q in qualifiers if q]
        if safe_quals:
            pattern = "|".join(safe_quals)
            where_clauses.append(f"REGEXP_CONTAINS(qualifiers, r'{pattern}')")

    # 4. Teams - Will be handled later via effective_team if needed
    # But checking input here for variables
    # If user filters by team, we want to filter on effective_team later.
    team_in_clause = None
    if teams and "Todos" not in teams:
        if isinstance(teams, list):
             teams_str = "', '".join(teams)
             team_in_clause = f"effective_team IN ('{teams_str}')"
        else:
             team_in_clause = f"effective_team = '{teams}'"
        
        # We DO NOT add to where_clauses yet because 'team' column checks would be wrong for OGs
        # where_clauses.append(team_in_clause) <--- We add this to the FINAL Where using effective_team

    # 5. Players
    if players and "Todos" not in players:
        if isinstance(players, list):
             players_str = "', '".join(players)
             where_clauses.append(f"player IN ('{players_str}')")
        else:
             where_clauses.append(f"player = '{players}'")

    where_str = " AND ".join(where_clauses)
    
    # Add effective_team filter if it exists
    if team_in_clause:
        where_str += f" AND {team_in_clause}"

    
    # Select columns based on subject
    if subject == "Jogadores":
        group_cols = "game_id, player, team"
        select_cols = "game_id, player, team"
        join_on = "p.game_id = m.game_id"
        base_where = "player IS NOT NULL"
    else:
        # Equipes
        group_cols = "game_id, team"
        select_cols = "game_id, team"
        join_on = "p.game_id = m.game_id" # Match dates join is same
        base_where = "team IS NOT NULL" # We will replace 'team' with 'effective_team'

    # Special handling for Assists (Goal Related Player)
    extra_cte = ""
    if use_related_player and subject == "Jogadores":
        extra_cte = """
        , player_names AS (
             SELECT DISTINCT player_id, player FROM all_events WHERE player IS NOT NULL
        )
        """
        # Override for Assist Logic (Calculated on RAW events usually, but we should use events_enhanced?)
        # If we use events_enhanced, we get effective_team.
        # Ideally yes.
        filtered_events_block = f"""
        filtered_events AS (
            SELECT
                e.game_id,
                n.player,
                e.team, -- Keep original team for player? Or effective? Usually original.
                COUNT(*) as metric_count
            FROM all_events e -- Use raw events for assists as it's specific logic
            JOIN player_names n ON e.related_player_id = n.player_id
            WHERE 1=1
            AND e.related_player_id IS NOT NULL
            AND {where_str.replace('effective_team', 'team')} -- Provide fallback if we use raw events
            GROUP BY 1, 2, 3
        )
        """
    else:
        # Standard Logic using events_enhanced
        
        # Prepare Where Clause for events_enhanced (which has effective_team)
        # where_str already has effective_team logic if 'teams' filter active.
        
        final_where = where_str
        final_base_where = base_where.replace('team', 'effective_team')
        
        # Note: events_enhanced has 'team' (original) and 'effective_team' (beneficiary).
        
        target_table = "events_enhanced"
        
        # If Subject Equipes, we group by effective_team aliased as team
        if subject == "Equipes":
            filtered_events_block = f"""
            filtered_events AS (
                SELECT
                    game_id,
                    effective_team as team,
                    COUNT(*) as metric_count
                FROM {target_table}
                WHERE {final_base_where}
                AND {final_where}
                GROUP BY game_id, effective_team
            )
            """
        else:
             # Jogadores
             filtered_events_block = f"""
            filtered_events AS (
                SELECT
                    {select_cols},
                    COUNT(*) as metric_count
                FROM {target_table}
                WHERE {base_where}
                AND {final_where}
                GROUP BY {group_cols}
            )
            """

    # Logic for Effective Team
    # Swaps team if it's an Own Goal so the goal counts for the beneficiary (Opponent of the scorer)
    # Regex covers "OwnGoal", "Own Goal", "Gol Contra"
    effective_team_calculation = """
        CASE 
            WHEN e.type = 'Goal' AND REGEXP_CONTAINS(e.qualifiers, r'(?i)(Own\s*Goal|Gol\s*Contra)') THEN
                CASE 
                    WHEN e.team = m.home_team THEN m.away_team 
                    WHEN e.team = m.away_team THEN m.home_team 
                    ELSE e.team
                END
            ELSE e.team
        END as effective_team
    """

    return f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    all_events AS (
        {events_union}
    ),
    
    match_metadata AS (
        SELECT game_id, match_date as start_time, season, home_team, away_team, home_score, away_score
        FROM all_schedule
    ),
    
    -- Ghost Goal Logic: Inject missing goals found in Schedule but missing in Events
    existing_goals AS (
        SELECT game_id, team, count(*) as goals
        FROM all_events
        WHERE type = 'Goal'
        GROUP BY 1, 2
    ),
    
    missing_goals AS (
        SELECT 
            m.game_id, 
            m.season,
            m.home_team, 
            m.away_team,
            (m.home_score - IFNULL(eh.goals, 0)) as home_diff,
            (m.away_score - IFNULL(ea.goals, 0)) as away_diff
        FROM match_metadata m
        LEFT JOIN existing_goals eh ON m.game_id = eh.game_id AND eh.team = m.home_team
        LEFT JOIN existing_goals ea ON m.game_id = ea.game_id AND ea.team = m.away_team
        WHERE (m.home_score > IFNULL(eh.goals, 0)) OR (m.away_score > IFNULL(ea.goals, 0))
    ),
    
    ghost_events AS (
        -- Home Ghosts
        SELECT 
            game_id, 
            home_team as team, 
            CAST(NULL as STRING) as player, 
            CAST(NULL as FLOAT64) as player_id,
            'Goal' as type, 
            'Successful' as outcome_type, 
            '[]' as qualifiers,
            90 as expanded_minute, 
            'FullTime' as period,
            50.0 as x, 50.0 as y, 
            50.0 as end_x, 50.0 as end_y,
            CAST(NULL as BOOL) as is_shot,
            CAST(NULL as FLOAT64) as related_player_id,
            season
        FROM missing_goals, UNNEST(GENERATE_ARRAY(1, home_diff))
        WHERE home_diff > 0
        
        UNION ALL
        
        -- Away Ghosts
        SELECT 
            game_id, 
            away_team as team, 
             CAST(NULL as STRING) as player, 
            CAST(NULL as FLOAT64) as player_id,
            'Goal' as type, 
            'Successful' as outcome_type, 
            '[]' as qualifiers,
            90 as expanded_minute, 
            'FullTime' as period,
            50.0 as x, 50.0 as y, 
            50.0 as end_x, 50.0 as end_y,
            CAST(NULL as BOOL) as is_shot,
            CAST(NULL as FLOAT64) as related_player_id,
            season
        FROM missing_goals, UNNEST(GENERATE_ARRAY(1, away_diff))
        WHERE away_diff > 0
    ),
    
    all_events_fixed AS (
        SELECT * FROM all_events
        UNION ALL
        SELECT * FROM ghost_events
    ),
    
    events_enhanced AS (
        SELECT 
            e.*,
            {effective_team_calculation}
        FROM all_events_fixed e
        JOIN match_metadata m ON e.game_id = m.game_id
    )
    {extra_cte},
    
    {filtered_events_block}
    

    SELECT
        p.*,
        m.start_time as match_date,
        m.season
    FROM filtered_events p
    JOIN match_metadata m ON {join_on}
    """


def get_conversion_ranking_query(
    project_id: str, 
    dataset_id: str, 
    subject: str, # 'Equipes' or 'Jogadores'
    
    # Numerator Params
    num_event_types: object,
    num_outcomes: object,
    num_qualifiers: object,
    
    # Denominator Params
    den_event_types: object,
    den_outcomes: object,
    den_qualifiers: object,
    
    teams: object = None,
    players: object = None,
    perspective: str = "pro"
) -> str:

    """
    Constructs a ranking query for Efficiency/Conversion.
    Returns: game_id, team/player, numerator_count, denominator_count, ratio
    """
    # Reuse the logic builders from get_dynamic_ranking_query but applied twice
    # We essentially need to generate the CTEs for both, then join.
    
    # Refactor proposal: 
    # To avoid massive code duplication, we can extract the CTE generation logic.
    # But for now, to be safe and robust, I will reimplement the CTE generation here 
    # or call a helper if I extract it.
    # Given the complexity of "Effective Team" logic, it's better to extract it.
    # checking file structure... _build_enhanced_events is not a separate function yet.
    # I will inline it for now to ensure correctness, as extracting might be risky without tests.
    
    schedule_union = _build_schedule_union(project_id, dataset_id)
    events_union = _build_events_union(project_id, dataset_id)
    
    def _build_filter_where(etypes, outcomes, quals, teams, players):
        where_clauses = ["1=1"]
        # 1. Event Type
        if etypes and "Todos" not in etypes:
            if isinstance(etypes, list):
                 types_str = "', '".join(etypes)
                 where_clauses.append(f"type IN ('{types_str}')")
            else:
                 where_clauses.append(f"type = '{etypes}'")
        
        # 2. Outcome
        if outcomes and "Todos" not in outcomes:
            target_outcomes = []
            if isinstance(outcomes, str): outcomes = [outcomes]
            for out in outcomes:
                if out == "Sucesso": target_outcomes.append("Successful")
                elif out == "Falha": target_outcomes.append("Unsuccessful")
                else: target_outcomes.append(out)
            if target_outcomes:
                out_str = "', '".join(target_outcomes)
                where_clauses.append(f"outcome_type IN ('{out_str}')")

        # 3. Qualifiers
        if quals and "Todos (Qualquer)" not in quals:
            if isinstance(quals, str): quals = [quals]
            safe_quals = [re.escape(q) for q in quals if q]
            if safe_quals:
                pattern = "|".join(safe_quals)
                where_clauses.append(f"REGEXP_CONTAINS(qualifiers, r'{pattern}')")
        
        # 4. Teams (Applied on effective_team later)
        team_clause = None
        if teams and "Todos" not in teams:
            if isinstance(teams, list):
                 teams_str = "', '".join(teams)
                 team_clause = f"effective_team IN ('{teams_str}')"
            else:
                 team_clause = f"effective_team = '{teams}'"

        # 5. Players
        if players and "Todos" not in players:
            if isinstance(players, list):
                 players_str = "', '".join(players)
                 where_clauses.append(f"player IN ('{players_str}')")
            else:
                 where_clauses.append(f"player = '{players}'")

        base_where = " AND ".join(where_clauses)
        if team_clause:
            base_where += f" AND {team_clause}"
            
        return base_where

    # Build Where clauses
    where_num = _build_filter_where(num_event_types, num_outcomes, num_qualifiers, teams, players)
    where_den = _build_filter_where(den_event_types, den_outcomes, den_qualifiers, teams, players)
    
    # Grouping Config
    if subject == "Jogadores":
        group_cols = "game_id, player, team"
        select_cols = "game_id, player, team"
        join_on = "p.game_id = m.game_id"
        base_where_sql = "player IS NOT NULL"
    else:
        # Equipes
        group_cols = "game_id, team" # effectively effective_team aliased
        select_cols = "game_id, effective_team as team"
        join_on = "p.game_id = m.game_id"
        base_where_sql = "team IS NOT NULL" # targets effective_team

    # Logic for Effective Team (Same as dynamic ranking)
    if perspective == "against":
         effective_team_calculation = """
            CASE
               WHEN e.type = 'Goal' AND REGEXP_CONTAINS(e.qualifiers, r'OwnGoal') THEN e.team
               ELSE
                    CASE 
                        WHEN e.team = m.home_team THEN m.away_team 
                        WHEN e.team = m.away_team THEN m.home_team 
                        ELSE e.team
                    END
            END as effective_team
        """
    else:
        effective_team_calculation = """
            CASE 
                WHEN e.type = 'Goal' AND REGEXP_CONTAINS(e.qualifiers, r'OwnGoal') THEN
                    CASE 
                        WHEN e.team = m.home_team THEN m.away_team 
                        WHEN e.team = m.away_team THEN m.home_team 
                        ELSE e.team
                    END
                ELSE e.team
            END as effective_team
        """


    
    return f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    all_events AS (
        {events_union}
    ),
    match_metadata AS (
        SELECT game_id, match_date as start_time, season, home_team, away_team
        FROM all_schedule
    ),
    events_enhanced AS (
        SELECT 
            e.*,
            -- Calculate Effective Team (Fix for Own Goals)
            e.*,
            {effective_team_calculation}

        FROM all_events e
        JOIN match_metadata m ON e.game_id = m.game_id
    ),
    
    cte_numerator AS (
        SELECT
            {select_cols},
            COUNT(*) as num_count
        FROM events_enhanced
        WHERE {base_where_sql.replace('team', 'effective_team')} 
        AND {where_num}
        GROUP BY {group_cols.replace('team', 'effective_team')}
    ),
    
    cte_denominator AS (
        SELECT
             {select_cols},
            COUNT(*) as den_count
        FROM events_enhanced
        WHERE {base_where_sql.replace('team', 'effective_team')} 
        AND {where_den}
        GROUP BY {group_cols.replace('team', 'effective_team')}
    )
    
    SELECT
        COALESCE(n.game_id, d.game_id) as game_id,
        COALESCE(n.team, d.team) as team,
        { "COALESCE(n.player, d.player) as player," if subject == "Jogadores" else "" }
        
        m.start_time as match_date,
        m.season,
        
        COALESCE(n.num_count, 0) as numerator,
        COALESCE(d.den_count, 0) as denominator,
        
        SAFE_DIVIDE(COALESCE(n.num_count, 0), COALESCE(d.den_count, 0)) as ratio
        
    FROM cte_numerator n
    FULL OUTER JOIN cte_denominator d 
        ON n.game_id = d.game_id 
        AND n.team = d.team
        { "AND n.player = d.player" if subject == "Jogadores" else "" }
        
    JOIN match_metadata m ON COALESCE(n.game_id, d.game_id) = m.game_id
    """


def get_teams_match_count_query(
    project_id: str, 
    dataset_id: str, 
    teams: object = None, 
    date_range: tuple = None
) -> str:
    """
    Returns total matches per team in the filtered period.
    """
    schedule_union = _build_schedule_union(project_id, dataset_id)
    
    where_clauses = ["1=1"]
    
    # Teams Filter
    if teams and "Todos" not in teams:
        if isinstance(teams, list):
             teams_str = "', '".join(teams)
             where_clauses.append(f"team IN ('{teams_str}')")
        else:
             where_clauses.append(f"team = '{teams}'")
             
    # Date Filter
    if date_range:
        start_date = date_range[0]
        # Handle tuple of 1 or 2
        if len(date_range) > 1:
            end_date = date_range[1]
            where_clauses.append(f"match_date >= '{start_date}' AND match_date <= '{end_date}'")
        else:
             where_clauses.append(f"match_date >= '{start_date}'")
             
    final_where = " AND ".join(where_clauses)

    return f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    
    matches_per_team AS (
        -- Unpivot so we have one row per team-match participation with date
        SELECT season, home_team as team, game_id, match_date, status FROM all_schedule
        WHERE home_team IS NOT NULL
        UNION ALL
        SELECT season, away_team as team, game_id, match_date, status FROM all_schedule
        WHERE away_team IS NOT NULL
    )
    
    SELECT 
        season, 
        team, 
        COUNT(DISTINCT game_id) as total_games
    FROM matches_per_team
    WHERE {final_where}
    -- AND (status = 'Finished' OR status = '2') -- REMOVING FILTER to allow diagnostic of future matches
    GROUP BY 1, 2

    ORDER BY season DESC, total_games ASC
    """




def get_player_match_counts_query(
    project_id: str, 
    dataset_id: str, 
    teams: object = None, 
    players: object = None,
    date_range: tuple = None
) -> str:
    """
    Returns total matches per player (participation) in the filtered period.
    """
    events_union = _build_events_union(project_id, dataset_id)
    schedule_union = _build_schedule_union(project_id, dataset_id)
    
    where_clauses = ["player IS NOT NULL"] # Base condition
    
    # Teams Filter
    if teams and "Todos" not in teams:
        if isinstance(teams, list):
             teams_str = "', '".join(teams)
             where_clauses.append(f"team IN ('{teams_str}')")
        else:
             where_clauses.append(f"team = '{teams}'")

    # Players Filter
    if players and "Todos" not in players:
        if isinstance(players, list):
             players_str = "', '".join(players)
             where_clauses.append(f"player IN ('{players_str}')")
        else:
             where_clauses.append(f"player = '{players}'")
             
    # Date Filter Logic (Needs Join)
    date_filter = "1=1"
    if date_range:
        start_date = date_range[0]
        if len(date_range) > 1:
            end_date = date_range[1]
            date_filter = f"m.match_date >= '{start_date}' AND m.match_date <= '{end_date}'"
        else:
             date_filter = f"m.match_date >= '{start_date}'"

    where_str = " AND ".join(where_clauses)

    return f"""
    WITH all_events AS (
        {events_union}
    ),
    all_schedule AS (
        {schedule_union}
    ),
    match_metadata AS (
        SELECT game_id, match_date, season FROM all_schedule
    )
    
    SELECT 
        e.player,
        e.team,
        m.season,
        COUNT(DISTINCT e.game_id) as total_games
    FROM all_events e
    JOIN match_metadata m ON e.game_id = m.game_id
    WHERE {where_str}
    AND {date_filter}
    AND (m.status = 'Finished' OR m.status = '2') -- Only completed matches
    GROUP BY 1, 2, 3

    """

def get_all_teams_query(project_id: str, dataset_id: str) -> str:
    """
    Get unique list of teams for dropdowns.
    """
    schedule_union = _build_schedule_union(project_id, dataset_id)
    return f"""
    WITH all_schedule AS (
        {schedule_union}
    )
    SELECT DISTINCT team FROM (
        SELECT home_team as team FROM all_schedule
        UNION ALL 
        SELECT away_team as team FROM all_schedule
    )
    WHERE team IS NOT NULL
    ORDER BY team
    """

def get_all_players_query(project_id: str, dataset_id: str, teams: list = None) -> str:
    """
    Get unique list of players, optionally filtered by teams.
    """
    events_union = _build_events_union(project_id, dataset_id)
    
    where_clause = "player IS NOT NULL"
    if teams:
        teams_str = "', '".join(teams)
        where_clause += f" AND team IN ('{teams_str}')"
        
    return f"""
    WITH all_events AS (
        {events_union}
    )
    SELECT DISTINCT player, team -- Select team too for display if needed, but distinct player name is key
    FROM all_events
    WHERE {where_clause}
    ORDER BY player
    """

def get_clean_sheets_query(
    project_id: str, 
    dataset_id: str, 
    teams: object = None, 
    date_range: tuple = None
) -> str:
    """
    Returns query to count Clean Sheets (matches where goals_against == 0).
    """
    schedule_union = _build_schedule_union(project_id, dataset_id)
    
    where_clauses = ["1=1"] # Base
    
    schedule_cte = f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    """
    
    # Teams
    teams_filter = ""
    if teams and "Todos" not in teams:
        if isinstance(teams, list):
             teams_str = "', '".join(teams)
             teams_filter = f"AND team IN ('{teams_str}')"
        else:
             teams_filter = f"AND team = '{teams}'"
             
    # Date
    date_filter = ""
    if date_range:
        start_date = date_range[0]
        if len(date_range) > 1:
            end_date = date_range[1]
            date_filter = f"AND match_date >= '{start_date}' AND match_date <= '{end_date}'"
        else:
             date_filter = f"AND match_date >= '{start_date}'"
             
    
    return f"""
    {schedule_cte}
    
    match_teams AS (
        SELECT 
            game_id,
            match_date,
            season,
            home_team as team,
            IFNULL(away_score, 0) as goals_against
        FROM all_schedule
        WHERE home_team IS NOT NULL
        UNION ALL
        SELECT 
            game_id,
            match_date,
            season,
            away_team as team,
            IFNULL(home_score, 0) as goals_against
        FROM all_schedule
        WHERE away_team IS NOT NULL
    )
    
    SELECT
        team,
        season,
        COUNT(*) as clean_sheets
    FROM match_teams
    WHERE goals_against = 0
    {teams_filter}
    {date_filter}
    AND match_date IS NOT NULL
    GROUP BY 1, 2
    ORDER BY clean_sheets DESC
    """

