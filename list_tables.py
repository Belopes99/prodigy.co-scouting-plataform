from google.cloud import bigquery
import os
import streamlit as st

# Setup auth similar to bq_io
try:
    if "gcp_service_account" in st.secrets:
        from google.oauth2 import service_account
        info = dict(st.secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(info)
        client = bigquery.Client(credentials=credentials, project="betterbet-467621")
    else:
        client = bigquery.Client(project="betterbet-467621")

    dataset_id = "betterdata"
    tables = client.list_tables(dataset_id) 

    print("Tables in {}:".format(dataset_id))
    for table in tables:
        if "2026" in table.table_id:
            print(f"- {table.table_id}")

except Exception as e:
    print(f"Error: {e}")
