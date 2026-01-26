from typing import Optional, Tuple

def get_total_matches_query(project_id: str, dataset_id: str) -> str:
    """
    Retorna query para contar total de partidas únicas (usando schedule).
    """
    return f"""
        SELECT COUNT(DISTINCT game_id) as total
        FROM `{project_id}.{dataset_id}.schedule_brasileirao_serie_a_2025`
        WHERE status IS NOT NULL -- Filtro opcional para jogos validos
    """

def get_total_events_query(project_id: str, dataset_id: str) -> str:
    """
    Retorna query para contar total de eventos.
    """
    return f"""
        SELECT COUNT(*) as total
        FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_2025`
    """

def get_recent_matches_query(project_id: str, dataset_id: str, limit: int = 5) -> str:
    """
    Retorna query para as últimas partidas processadas (usando schedule).
    """
    return f"""
        SELECT 
            game_id as match_id,
            start_time as match_date,
            home_team,
            away_team,
            home_score,
            away_score
        FROM `{project_id}.{dataset_id}.schedule_brasileirao_serie_a_2025`
        WHERE status = 2 -- Assuming 2 is 'Finished', or just order by time
        AND home_score IS NOT NULL
        ORDER BY start_time DESC
        LIMIT {limit}
    """

def get_match_stats_query(project_id: str, dataset_id: str) -> str:
    """
    Retorna estatísticas AGREGADAS por partida e time.
    Isso serve de base para o Ranking (Geral ou Por Temporada).
    """
    return f"""
    WITH match_metadata AS (
        SELECT 
            game_id,
            start_time as match_date,
            home_team,
            away_team,
            home_score,
            away_score
        FROM `{project_id}.{dataset_id}.schedule_brasileirao_serie_a_2025`
        WHERE home_score IS NOT NULL 
    ),
    
    match_teams AS (
        SELECT 
            game_id,
            match_date,
            home_team as team,
            home_score as goals_for,
            away_score as goals_against,
            'Mandante' as side
        FROM match_metadata
        
        UNION ALL
        
        SELECT 
            game_id,
            match_date,
            away_team as team,
            away_score as goals_for,
            home_score as goals_against,
            'Visitante' as side
        FROM match_metadata
    ),
    
    event_stats AS (
        SELECT
            game_id,
            team,
            COUNTIF(type = 'Pass') as total_passes,
            COUNTIF(type = 'Pass' AND outcome_type = 'Successful') as successful_passes,
            COUNTIF(type IN ('Missed Shots', 'Saved Shot', 'Goal', 'Shot on Post')) as total_shots,
            COUNTIF(type = 'Goal') as goals_from_events,
            COUNTIF(type IN ('Saved Shot', 'Goal', 'Shot on Post')) as shots_on_target
        FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_2025`
        GROUP BY 1, 2
    )
    
    SELECT
        t.game_id as match_id,
        EXTRACT(YEAR FROM t.match_date) as season,
        t.team,
        t.goals_for,
        t.goals_against,
        IFNULL(e.total_passes, 0) as total_passes,
        IFNULL(e.successful_passes, 0) as successful_passes,
        IFNULL(e.total_shots, 0) as total_shots,
        IFNULL(e.shots_on_target, 0) as shots_on_target
    FROM match_teams t
    LEFT JOIN event_stats e ON t.game_id = e.game_id AND t.team = e.team
    """


def get_players_by_team_query(project_id: str, dataset_id: str, team: str) -> str:
    """
    Lista jogadores que atuaram pelo time.
    """
    return f"""
    SELECT DISTINCT player
    FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_2025`
    WHERE team = '{team}' AND player IS NOT NULL
    ORDER BY player
    """


def get_player_stats_query(project_id: str, dataset_id: str, year: int = 2025) -> str:
    """
    Retorna estatísticas AGREGADAS por jogador para radar charts.
    """
    return f"""
    SELECT
        player,
        team,
        COUNT(*) as total_actions,
        COUNTIF(type = 'Pass') as total_passes,
        COUNTIF(type = 'Pass' AND outcome_type = 'Successful') as successful_passes,
        SAFE_DIVIDE(COUNTIF(type = 'Pass' AND outcome_type = 'Successful'), COUNTIF(type = 'Pass')) as pass_accuracy,
        
        COUNTIF(type IN ('Missed Shots', 'Saved Shot', 'Goal', 'Shot on Post')) as total_shots,
        COUNTIF(type = 'Goal') as goals,
        
        COUNTIF(type = 'Ball Recovery') as recoveries,
        COUNTIF(type = 'Interception') as interceptions,
        COUNTIF(type = 'Tackle') as tackles
        
    FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_2025`
    WHERE player IS NOT NULL
    GROUP BY 1, 2
    """


def get_player_events_query(project_id: str, dataset_id: str, player: str) -> str:
    """
    Retorna eventos brutos de um jogador para plotagem de mapa.
    """
    return f"""
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
    FROM `{project_id}.{dataset_id}.eventos_brasileirao_serie_a_2025`
    WHERE player = '{player}'
    """
