#!/usr/bin/env python3
"""
Add taxonomic levels (family, order, class, phylum, kingdom) to species table.
Loads data from final_taxonomy_occ.csv
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

load_dotenv()

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
TAXONOMY_CSV = DATA_DIR / "final_taxonomy_occ.csv"

# Azure credentials
AZURE_SERVER = os.getenv("AZURE_SQL_SERVER", "gocfg.database.windows.net")
AZURE_DB = os.getenv("AZURE_SQL_DATABASE", "free-sql-db-5085999")
AZURE_USER = os.getenv("AZURE_SQL_USER", "rcavieses")
AZURE_PASSWORD = os.getenv("AZURE_SQL_PASSWORD", "")

def get_engine():
    """Create SQLAlchemy engine."""
    if not AZURE_PASSWORD:
        raise ValueError("AZURE_SQL_PASSWORD not set")

    return create_engine(
        f"mssql+pymssql://{quote_plus(AZURE_USER)}:{quote_plus(AZURE_PASSWORD)}"
        f"@{AZURE_SERVER}:1433/{AZURE_DB}?tds_version=7.4",
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"timeout": 30, "login_timeout": 30},
    )

def add_taxonomy_columns(engine):
    """Add family, order, class, phylum, kingdom columns if not present."""
    print("[1/3] Adding taxonomy columns...")

    columns_to_add = [
        ("family", "NVARCHAR(255)"),
        ("order_taxon", "NVARCHAR(255)"),  # avoid 'order' reserved keyword
        ("class_taxon", "NVARCHAR(255)"),  # avoid 'class' reserved keyword
        ("phylum", "NVARCHAR(255)"),
        ("kingdom", "NVARCHAR(255)"),
    ]

    def retry_add_columns(attempt=1):
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                # Check which columns already exist
                result = conn.execute(
                    text("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='species'")
                )
                existing = {row[0].lower() for row in result}

                # Add missing columns
                for col_name, col_type in columns_to_add:
                    if col_name.lower() not in existing:
                        sql = f"ALTER TABLE species ADD {col_name} {col_type}"
                        print(f"  Adding column: {col_name}")
                        conn.execute(text(sql))
                    else:
                        print(f"  Column {col_name} already exists")

            print("[OK] Columns ready")
        except Exception as e:
            if attempt < 4:
                print(f"  Retry {attempt}/3 (waiting 20s)...")
                time.sleep(20)
                retry_add_columns(attempt + 1)
            else:
                raise

    retry_add_columns()

def load_taxonomy_data(engine):
    """Load taxonomy data from CSV and update species table."""
    print("\n[2/3] Loading taxonomy data...")

    if not TAXONOMY_CSV.exists():
        raise FileNotFoundError(f"Taxonomy CSV not found: {TAXONOMY_CSV}")

    # Read taxonomy CSV
    # Expected columns: kingdom, class, phylum, order, family, genus, species
    df_tax = pd.read_csv(TAXONOMY_CSV)
    print(f"  Loaded {len(df_tax)} taxonomy records")
    print(f"  Columns: {list(df_tax.columns)}")

    # Rename genus+species to match 'taxon' in species table
    df_tax["full_name"] = df_tax["genus"] + " " + df_tax["species"]

    # Read current species table
    df_species = pd.read_sql("SELECT taxon FROM species", engine)
    print(f"  Found {len(df_species)} species in database")

    # Build update records
    updates = []
    no_matches = []

    for _, sp_row in df_species.iterrows():
        taxon = sp_row["taxon"]

        # Find taxonomy record that contains this taxon
        # First try exact match on full_name, then on genus+species
        tax_match = df_tax[df_tax["full_name"] == taxon]

        if tax_match.empty:
            # Try partial match on species column
            tax_match = df_tax[df_tax["species"] == taxon]

        if tax_match.empty:
            no_matches.append(taxon)
            continue

        row = tax_match.iloc[0]
        updates.append({
            "taxon": taxon,
            "family": str(row["family"]) if pd.notna(row["family"]) else None,
            "order_taxon": str(row["order"]) if pd.notna(row["order"]) else None,
            "class_taxon": str(row["class"]) if pd.notna(row["class"]) else None,
            "phylum": str(row["phylum"]) if pd.notna(row["phylum"]) else None,
            "kingdom": str(row["kingdom"]) if pd.notna(row["kingdom"]) else None,
        })

    print(f"  Prepared {len(updates)} updates")

    # Batch insert into temp table and merge
    def retry_update(attempt=1):
        try:
            # Create temp table with updates and merge
            df_updates = pd.DataFrame(updates)

            # Write to temporary table
            df_updates.to_sql("#temp_taxonomy", con=engine, if_exists="replace", index=False)
            print(f"  Temp table created with {len(df_updates)} records")

            # Merge temp table into species
            with engine.begin() as conn:
                conn.execute(text("""
                    MERGE species s
                    USING #temp_taxonomy t
                    ON s.taxon = t.taxon
                    WHEN MATCHED THEN
                        UPDATE SET
                            s.family = t.family,
                            s.order_taxon = t.order_taxon,
                            s.class_taxon = t.class_taxon,
                            s.phylum = t.phylum,
                            s.kingdom = t.kingdom;
                """))

            print(f"[OK] Updated {len(updates)} species with taxonomy data")
            if no_matches:
                print(f"[WARN] {len(no_matches)} species had no taxonomy match")

        except Exception as e:
            if attempt < 4:
                print(f"  Retry {attempt}/3 (waiting 20s)...")
                time.sleep(20)
                retry_update(attempt + 1)
            else:
                raise

    retry_update()

def verify_data(engine):
    """Verify taxonomy data was loaded."""
    print("\n[3/3] Verifying data...")

    result = pd.read_sql(
        "SELECT TOP 10 taxon, family, order_taxon, class_taxon, phylum, kingdom FROM species WHERE family IS NOT NULL",
        engine
    )

    print(f"\nSample records with taxonomy data:")
    print(result.to_string(index=False))

    # Stats
    stats = pd.read_sql(
        """SELECT
            COUNT(*) as total,
            SUM(CASE WHEN family IS NOT NULL THEN 1 ELSE 0 END) as with_family,
            SUM(CASE WHEN order_taxon IS NOT NULL THEN 1 ELSE 0 END) as with_order,
            SUM(CASE WHEN class_taxon IS NOT NULL THEN 1 ELSE 0 END) as with_class,
            SUM(CASE WHEN phylum IS NOT NULL THEN 1 ELSE 0 END) as with_phylum,
            SUM(CASE WHEN kingdom IS NOT NULL THEN 1 ELSE 0 END) as with_kingdom
        FROM species""",
        engine
    )

    print("\n[STATS] Statistics:")
    print(stats.to_string(index=False))

def main():
    print("\n" + "="*70)
    print("ADD TAXONOMIC LEVELS TO SPECIES TABLE")
    print("="*70)

    engine = get_engine()

    try:
        add_taxonomy_columns(engine)
        load_taxonomy_data(engine)
        verify_data(engine)

        print("\n" + "="*70)
        print("[OK] SUCCESS: Taxonomy data loaded")
        print("="*70)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        raise

if __name__ == "__main__":
    main()
