#!/usr/bin/env python3
"""
Migrar datos del CSV clasificado a Azure SQL Server
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine

load_dotenv(Path(__file__).parent / ".env")

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
CLASSIFIED_CSV = OUTPUT_DIR / "species_classified.csv"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"

# Credenciales Azure
AZURE_SERVER = "gocfg.database.windows.net"
AZURE_DB = "free-sql-db-2951059"
AZURE_USER = "cloudSAa6de9d39"
AZURE_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

def get_azure_engine():
    """Crear conexión a Azure SQL"""
    connection_string = (
        f"mssql+pyodbc://{AZURE_USER}:{AZURE_PASSWORD}"
        f"@{AZURE_SERVER}/{AZURE_DB}"
        f"?driver=ODBC+Driver+17+for+SQL+Server"
        f"&Encrypt=yes&TrustServerCertificate=no&Connection+Timeout=30"
    )
    return create_engine(connection_string)

def migrate():
    print("\n" + "="*60)
    print("MIGRAR CSV → AZURE SQL SERVER")
    print("="*60 + "\n")

    # Paso 1: Leer del CSV local
    print("[1/3] Leyendo datos del CSV…")

    if not CLASSIFIED_CSV.exists():
        raise FileNotFoundError(f"CSV no encontrado: {CLASSIFIED_CSV}")
    if not GROUPS_CSV.exists():
        raise FileNotFoundError(f"Grupos no encontrados: {GROUPS_CSV}")

    df_classified = pd.read_csv(CLASSIFIED_CSV)
    df_groups = pd.read_csv(GROUPS_CSV)

    print(f"✅ {len(df_classified)} especies cargadas del CSV")

    # Paso 2: Preparar datos
    print("\n[2/3] Preparando datos…")

    code_to_name = dict(zip(
        df_groups["Code"].str.strip(),
        df_groups["Functional_Group"].str.strip(),
    ))

    taxon_col = "species_name" if "species_name" in df_classified.columns else "genus_name"

    species_records = []
    for _, row in df_classified.iterrows():
        taxon = str(row[taxon_col]).strip()
        code = str(row.get("group_code", "UNCLASSIFIED")).strip()
        group_name = code_to_name.get(code, str(row.get("group_name", "Unclassified")).strip())

        species_records.append({
            "taxon": taxon,
            "current_code": code,
            "current_group": group_name,
            "original_code": code,
            "original_group": group_name,
            "confidence": str(row.get("confidence", "low")).strip(),
            "status": "pending",
            "reasoning": str(row.get("reasoning", "")).strip() if "reasoning" in row else None,
            "last_modified_by": None,
            "last_modified_at": None,
        })

    df = pd.DataFrame(species_records)
    print(f"✅ {len(df)} registros preparados")

    # Paso 3: Insertar en Azure SQL
    print("\n[3/3] Insertando en Azure SQL…")
    engine = get_azure_engine()

    df.to_sql("species", con=engine, if_exists="append", index=False)
    print(f"✅ {len(df)} registros insertados en Azure SQL")

    print("\n" + "="*60)
    print("✅ MIGRACIÓN COMPLETADA")
    print("="*60)

if __name__ == "__main__":
    if not AZURE_PASSWORD:
        print("❌ Error: Define AZURE_SQL_PASSWORD en .env")
        exit(1)
    
    migrate()
