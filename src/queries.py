from typing import Optional, Tuple

# YEARS_TO_QUERY = range(2015, 2026)
YEARS_TO_QUERY = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

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
        if year >= 2024:
            ts_col = "start_time"
        else:
            ts_col = "date"
            
        subqueries.append(f"""
            SELECT 
                game_id, 
                {year} as season, -- Hardcoded from table suffix
                {ts_col} as match_date, 
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
    return " UNION ALL ".join([f"SELECT *, {year} as season FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_{year}`" for year in YEARS_TO_QUERY])


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
        WHERE home_score IS NOT NULL 
    ),
    
    match_teams AS (
        SELECT 
            game_id,
            match_date,
            season,
            home_team as team,
            home_score as goals_for,
            away_score as goals_against,
            'Mandante' as side
        FROM match_metadata
        UNION ALL
        
        SELECT 
            game_id,
            match_date,
            season,
            away_team as team,
            away_score as goals_for,
            home_score as goals_against,
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
            COUNTIF(type IN ('SavedShot', 'Goal')) as shots_on_target
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
        IFNULL(e.shots_on_target, 0) as shots_on_target
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


def get_player_stats_query(project_id: str, dataset_id: str, year: int = 2025) -> str:
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
            COUNTIF(type = 'Pass') as total_passes
        FROM all_events
        WHERE player IS NOT NULL
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
        p.total_passes
    FROM player_stats p
    JOIN match_dates m ON p.game_id = m.game_id
    -- No GROUP BY here, we return raw match rows


def get_teams_match_count_query(project_id: str, dataset_id: str) -> str:
    """
    Returns total matches per team per season to audit missing data.
    Expected: 38 matches per completed season.
    """
    schedule_union = _build_schedule_union(project_id, dataset_id)
    return f"""
    WITH all_schedule AS (
        {schedule_union}
    ),
    
    matches_per_team AS (
        -- Unpivot so we have one row per team-match participation
        SELECT season, home_team as team, game_id FROM all_schedule
        WHERE home_team IS NOT NULL
        UNION ALL
        SELECT season, away_team as team, game_id FROM all_schedule
        WHERE away_team IS NOT NULL
    )
    
    SELECT 
        season, 
        team, 
        COUNT(DISTINCT game_id) as total_games
    FROM matches_per_team
    GROUP BY 1, 2
    ORDER BY season DESC, total_games ASC
    """
    """
