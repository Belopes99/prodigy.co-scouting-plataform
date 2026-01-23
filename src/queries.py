from typing import Optional, Tuple

def get_total_matches_query(project_id: str, dataset_id: str) -> str:
    """
    Retorna query para contar total de partidas únicas.
    """
    # Assumindo que a tabela de eventos é eventos_{ano} e precisamos agregar.
    # Por enquanto, vamos pegar apenas de 2025 ou fazer um UNION se tiver mais anos.
    # Para simplificar, vamos contar de 2025.
    return f"""
        SELECT COUNT(DISTINCT match_id) as total
        FROM `{project_id}.{dataset_id}.events_bra_2025`
    """

def get_total_events_query(project_id: str, dataset_id: str) -> str:
    """
    Retorna query para contar total de eventos.
    """
    return f"""
        SELECT COUNT(*) as total
        FROM `{project_id}.{dataset_id}.events_bra_2025`
    """

def get_recent_matches_query(project_id: str, dataset_id: str, limit: int = 5) -> str:
    """
    Retorna query para as últimas partidas processadas.
    """
    return f"""
        SELECT 
            DISTINCT match_id,
            match_date,
            home_team,
            away_team,
            home_score,
            away_score
        FROM `{project_id}.{dataset_id}.events_bra_2025`
        ORDER BY match_date DESC
        LIMIT {limit}
    """

def get_match_stats_query(project_id: str, dataset_id: str) -> str:
    """
    Retorna estatísticas AGREGADAS por partida e time.
    Isso serve de base para o Ranking (Geral ou Por Temporada).
    """
    return f"""
    WITH match_teams AS (
        SELECT 
            match_id,
            match_date,
            home_team as team,
            home_score as goals_for,
            away_score as goals_against,
            'Mandante' as side
        FROM `{project_id}.{dataset_id}.events_bra_2025`
        GROUP BY 1,2,3,4,5
        
        UNION ALL
        
        SELECT 
            match_id,
            match_date,
            away_team as team,
            away_score as goals_for,
            home_score as goals_against,
            'Visitante' as side
        FROM `{project_id}.{dataset_id}.events_bra_2025`
        GROUP BY 1,2,3,4,5
    ),
    
    event_stats AS (
        SELECT
            match_id,
            team,
            COUNTIF(type = 'Pass') as total_passes,
            COUNTIF(type = 'Pass' AND outcome_type = 'Successful') as successful_passes,
            COUNTIF(type IN ('Missed Shots', 'Saved Shot', 'Goal', 'Shot on Post')) as total_shots,
            COUNTIF(type = 'Goal') as goals_from_events, -- Check consistency with score
            COUNTIF(type IN ('Saved Shot', 'Goal', 'Shot on Post')) as shots_on_target
        FROM `{project_id}.{dataset_id}.events_bra_2025`
        GROUP BY 1, 2
    )
    
    SELECT
        t.match_id,
        EXTRACT(YEAR FROM t.match_date) as season,
        t.team,
        t.goals_for,
        t.goals_against,
        e.total_passes,
        e.successful_passes,
        e.total_shots,
        e.shots_on_target
    FROM match_teams t
    LEFT JOIN event_stats e ON t.match_id = e.match_id AND t.team = e.team
    """
