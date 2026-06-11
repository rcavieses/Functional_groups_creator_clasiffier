#!/usr/bin/env python3
"""
Merge Labile Detritus (DL) and Refractory Detritus (DR) into Carrion (DC).

Actions:
  1. Move all species with current_code IN ('DL','DR') -> DC / Carrion
  2. Update group_descriptions for DC with the merged description
  3. Delete DL/DR entries from group_descriptions, group_ratings, group_proposals
  4. Log each species move in audit_log
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent / ".env")

AZURE_SERVER  = "gocfg.database.windows.net"
AZURE_DB      = "free-sql-db-5085999"
AZURE_USER    = "rcavieses"
AZURE_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

NEW_DC_DESCRIPTION = (
    "Dead organic matter, carcasses, large particulate organic matter, "
    "refractory particulate organic matter, cohesive small particles, "
    "resistant to decomposition, labile particulate organic matter, "
    "easily degradable small particles"
)


def get_engine():
    from urllib.parse import quote_plus
    return create_engine(
        f"mssql+pymssql://{quote_plus(AZURE_USER)}:{quote_plus(AZURE_PASSWORD)}"
        f"@{AZURE_SERVER}:1433/{AZURE_DB}?tds_version=7.4",
        pool_pre_ping=True,
        connect_args={"timeout": 30, "login_timeout": 30},
    )


def main():
    if not AZURE_PASSWORD:
        print("ERROR: AZURE_SQL_PASSWORD no está configurada en .env")
        return

    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT taxon, current_code, current_group FROM species WHERE current_code IN ('DL','DR')")
        ).fetchall()

    print(f"\nEspecies a mover a Carrion (DC): {len(rows)}")
    for r in rows:
        print(f"  [{r.current_code}] {r.taxon}")

    if not rows:
        print("No hay especies en DL/DR. Continuando con limpieza de tablas auxiliares.")

    with engine.begin() as conn:
        # 1. Move species DL/DR -> DC
        for r in rows:
            conn.execute(
                text("""UPDATE species
                        SET current_code='DC', current_group='Carrion', status='pending'
                        WHERE taxon=:taxon"""),
                {"taxon": r.taxon},
            )
            conn.execute(
                text("""INSERT INTO audit_log (taxon, action, expert, from_code, to_code, to_name, note)
                        VALUES (:taxon, 'move', 'system', :from_code, 'DC', 'Carrion',
                                'DL/DR merged into Carrion (DC) - groups deleted')"""),
                {"taxon": r.taxon, "from_code": r.current_code},
            )

        # 2. Upsert DC description
        conn.execute(
            text("""MERGE group_descriptions AS target
                    USING (SELECT 'DC' AS group_code) AS source ON target.group_code = source.group_code
                    WHEN MATCHED THEN
                        UPDATE SET description=:desc, updated_by='system', updated_at=GETDATE()
                    WHEN NOT MATCHED THEN
                        INSERT (group_code, description, updated_by) VALUES ('DC', :desc, 'system');"""),
            {"desc": NEW_DC_DESCRIPTION},
        )

        # 3. Remove DL/DR from auxiliary tables
        for table in ("group_descriptions", "group_ratings", "group_proposals"):
            col = "group_code"
            result = conn.execute(
                text(f"DELETE FROM {table} WHERE {col} IN ('DL','DR')")
            )
            print(f"  Deleted {result.rowcount} rows from {table}")

    print("\nMigración completada:")
    print(f"  - {len(rows)} especies movidas a DC (Carrion)")
    print("  - group_descriptions de DC actualizada")
    print("  - Entradas DL/DR eliminadas de tablas auxiliares")


if __name__ == "__main__":
    main()
