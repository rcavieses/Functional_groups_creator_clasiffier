#!/usr/bin/env python3
"""Query species in Labile Detritus (DL) and Refractory Detritus (DR) groups."""

import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent / ".env")

AZURE_SERVER = "gocfg.database.windows.net"
AZURE_DB = "free-sql-db-5085999"
AZURE_USER = "rcavieses"
AZURE_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

def get_engine():
    from urllib.parse import quote_plus
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{AZURE_SERVER},1433;"
        f"Database={AZURE_DB};"
        f"Uid={AZURE_USER};"
        f"Pwd={AZURE_PASSWORD};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}")

engine = get_engine()

with engine.connect() as conn:
    df = pd.read_sql(
        "SELECT taxon, original_group, original_code, current_group, current_code, status "
        "FROM species WHERE current_code IN ('DL', 'DR') ORDER BY current_code, taxon",
        conn
    )

print(f"\nTotal especies en DL/DR: {len(df)}\n")
print(df.to_string(index=False))

print("\n--- Conteo por grupo ---")
print(df.groupby(['current_code', 'current_group']).size().reset_index(name='count').to_string(index=False))
