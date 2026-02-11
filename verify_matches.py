
import sys
import os
import pandas as pd
from datetime import date
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from src.bq_io import get_bq_client
from src.queries import get_teams_match_count_query

PROJECT_ID = "betterbet-467621"
DATASET_ID = "betterdata"

def run_debug():
    client = get_bq_client(project=PROJECT_ID)
    
    # Test params
    teams = ["Sport Recife"]
    date_range = (date(2023, 1, 1), date(2025, 12, 31)) # Broad ranger
    
    print(f"Running Match Count Query for {teams} in {date_range}...")
    
    q = get_teams_match_count_query(PROJECT_ID, DATASET_ID, teams, date_range)
    print("Query sample:")
    print(q[:500])
    
    df = client.query(q).to_dataframe()
    
    print("\n--- Match Counts (Raw) ---")
    print(df)
    
    if not df.empty:
        total = df["total_games"].sum()
        print(f"\nTotal Games (Sum across seasons): {total}")
        
    # Simulate Historical Aggregation Issue
    print("\n--- Simulation: Historical Merge ---")
    df_agg_mock = pd.DataFrame({"team": ["Sport Recife"], "metrics": [100]})
    
    print("Agg DF (Mock):")
    print(df_agg_mock)
    
    # Incorrect Merge (Current Code)
    merged_incorrect = pd.merge(df_agg_mock, df, on="team", how="left")
    print("\nIncorrect Merge Result (Duplicates expected if multiple seasons):")
    print(merged_incorrect)
    
    # Correct Merge
    df_grouped = df.groupby("team")["total_games"].sum().reset_index()
    merged_correct = pd.merge(df_agg_mock, df_grouped, on="team", how="left")
    print("\nCorrect Merge Result:")
    print(merged_correct)

if __name__ == "__main__":
    run_debug()
