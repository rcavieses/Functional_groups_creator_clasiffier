#!/usr/bin/env python3
"""
Remove detritus groups and Carrion from the DB.

Steps executed in order:
  1. Move DL / DR species  -> UNCLASSIFIED  (groups DR, DL deleted from CSV)
  2. Move DC species       -> UNCLASSIFIED  (group  DC deleted from CSV)
  3. Delete DL / DR / DC from group_descriptions, group_ratings, group_proposals
  4. Log every move in audit_log
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent / ".env")

AZURE_SERVER   = "gocfg.database.windows.net"
AZURE_DB       = "free-sql-db-5085999"
AZURE_USER     = "rcavieses"
AZURE_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

REMOVED_CODES  = ("DL", "DR", "DC")


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

    # ── Query affected species ────────────────────────────────────────────────
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT taxon, current_code, current_group FROM species "
                "WHERE current_code IN ('DL','DR','DC')"
            )
        ).fetchall()

    print(f"\nEspecies a mover a UNCLASSIFIED: {len(rows)}")
    for r in rows:
        print(f"  [{r.current_code}] {r.taxon}")

    if not rows:
        print("No hay especies en DL/DR/DC. Continuando con limpieza de tablas auxiliares.")

    # ── Apply changes in a single transaction ────────────────────────────────
    with engine.begin() as conn:
        # 1. Move species -> UNCLASSIFIED
        for r in rows:
            conn.execute(
                text("""UPDATE species
                        SET current_code='UNCLASSIFIED', current_group='Unclassified',
                            status='pending'
                        WHERE taxon=:taxon"""),
                {"taxon": r.taxon},
            )
            conn.execute(
                text("""INSERT INTO audit_log
                            (taxon, action, expert, from_code, to_code, to_name, note)
                        VALUES (:taxon, 'move', 'system', :from_code,
                                'UNCLASSIFIED', 'Unclassified',
                                'Group removed (DL/DR/DC eliminated) - pending reclassification')"""),
                {"taxon": r.taxon, "from_code": r.current_code},
            )

        # 2. Clean auxiliary tables
        for table in ("group_descriptions", "group_ratings", "group_proposals"):
            result = conn.execute(
                text(f"DELETE FROM {table} WHERE group_code IN ('DL','DR','DC')")
            )
            print(f"  Deleted {result.rowcount} rows from {table}")

    print("\nMigración completada:")
    print(f"  - {len(rows)} especies movidas a UNCLASSIFIED")
    print("  - Entradas DL/DR/DC eliminadas de tablas auxiliares")
    print("  - Los expertos deben reclasificarlas en la página 'Validar Especies'")


if __name__ == "__main__":
    main()
