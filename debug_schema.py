import tomllib
from google.cloud import bigquery
from google.oauth2 import service_account

try:
    with open(".streamlit/secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
    
    info = secrets["gcp_service_account"]
    
    # We know this is the working project from previous steps
    project_id = "betterbet-467621" # or info.get("project_id") if it matches
    
    credentials = service_account.Credentials.from_service_account_info(info)
    client = bigquery.Client(credentials=credentials, project=project_id)
    
    table_id = f"{project_id}.betterdata.schedule_brasileirao_serie_a_2025"
    print(f"Inspecting table: {table_id}")
    
    table = client.get_table(table_id)
    print("\n--- SCHEMA ---")
    for s in table.schema:
        print(f"{s.name} ({s.field_type})")
        
except Exception as e:
    print(f"ERROR: {e}")
