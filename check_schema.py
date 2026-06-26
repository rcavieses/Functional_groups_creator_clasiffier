#!/usr/bin/env python3
"""Check current species table schema."""

import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from urllib.parse import quote_plus

# Load env vars
load_dotenv()

# Connection params
server = os.getenv("AZURE_SQL_SERVER", "gocfg.database.windows.net")
database = os.getenv("AZURE_SQL_DATABASE", "free-sql-db-5085999")
user = os.getenv("AZURE_SQL_USER", "rcavieses")
password = os.getenv("AZURE_SQL_PASSWORD")

if not password:
    print("❌ AZURE_SQL_PASSWORD not set")
    exit(1)

# Create engine
engine = create_engine(
    f"mssql+pymssql://{quote_plus(user)}:{quote_plus(password)}"
    f"@{server}:1433/{database}?tds_version=7.4",
    pool_pre_ping=True,
    pool_recycle=1800,
)

# Inspect schema
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"Tables: {tables}\n")

if "species" in tables:
    columns = inspector.get_columns("species")
    print("Species table columns:")
    for col in columns:
        print(f"  - {col['name']}: {col['type']}")
else:
    print("species table not found")

# Check first few rows
try:
    df = pd.read_sql("SELECT TOP 5 * FROM species", engine)
    print("\nFirst 5 rows:")
    print(df.to_string())
except Exception as e:
    print(f"Error reading species: {e}")
