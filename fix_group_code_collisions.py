#!/usr/bin/env python3
"""
Fix functional-group code collisions in data/functional_groups_final.csv and the
Azure SQL `species` table.

Root cause: three codes were reused by two different functional groups in the
CSV (last row wins when the app builds {code: name}), so species got the wrong
group name displayed everywhere:
  DOL -> "Dolphins" (row 14) and "Dolphinfish" (row 37)         -> real dolphins showed as "Dolphinfish"
  SUR -> "Surgeonfish" (row 51) and "Sea Urchins" (row 77)      -> surgeonfish showed as "Sea Urchins"
  COR -> "Corvinas" (row 58) and "Corals and Anemones" (row 84) -> corvinas showed as "Corals and Anemones"

Additionally, Orcinus orca was lumped into "Toothed Whales" (TWH); an expert
requested it be split into its own group ("Orca debería ser un grupo funcional
aparte").

This script (idempotent):
  1. Reassigns the wrongly-labeled species to new codes (DPF, SEU, CNA, ORC)
     that match the already-corrected data/functional_groups_final.csv.
  2. Fixes current_group text for the species that keep their original code.
  3. Seeds group_descriptions for the new codes.
  4. Logs every change in audit_log.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent / ".env")

AZURE_SERVER = "gocfg.database.windows.net"
AZURE_DB = "free-sql-db-5085999"
AZURE_USER = "rcavieses"
AZURE_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

# (old_code, match_column, match_values, new_code, new_name, note)
RECLASSIFICATIONS = [
    (
        "DOL", "family",
        ["Coryphaenidae", "Carangidae", "Nematistiidae", "Nomeidae"],
        "DPF", "Dolphinfish",
        "Code DOL was shared by Dolphins/Dolphinfish; fish species split out to DPF",
    ),
    (
        "SUR", "family",
        ["Acanthuridae"],
        None, "Surgeonfish",  # keeps code SUR, only the display name was wrong
        "Code SUR incorrectly displayed as 'Sea Urchins'; fixed to 'Surgeonfish'",
    ),
    (
        "SUR", "genus",
        ["Agassizia", "Arbacia", "Astropyga", "Brissopsis", "Centrostephanus",
         "Dendraster", "Diadema", "Echinometra", "Encope", "Eucidaris",
         "Hesperocidaris", "Lanthonia", "Lovenia", "Lytechinus", "Mellita",
         "Metalia", "Spatangus", "Strongylocentrotus", "Toxopneustes", "Tripneustes"],
        "SEU", "Sea Urchins",
        "Code SUR was shared by Surgeonfish/Sea Urchins; urchins split out to SEU",
    ),
    (
        "COR", "genus",
        ["Cynoscion"],
        None, "Corvinas",  # keeps code COR, only the display name was wrong
        "Code COR incorrectly displayed as 'Corals and Anemones'; fixed to 'Corvinas'",
    ),
    (
        "COR", "order_taxon",
        ["Actiniaria", "Zoantharia"],
        "CNA", "Corals and Anemones",
        "Code COR was shared by Corvinas/Corals and Anemones; anemones split out to CNA",
    ),
    (
        "TWH", "genus",
        ["Orcinus"],
        "ORC", "Orcas",
        "Orcinus orca split out of Toothed Whales into its own group, per expert request",
    ),
]

# Any remaining species still tagged COR that aren't Cynoscion or Actiniaria/Zoantharia
# order are coral/anemone genera -> also move to CNA.
CATCH_ALL = ("COR", "CNA", "Corals and Anemones")

NEW_DESCRIPTIONS = {
    "DPF": "Coryphaena hippurus (mahi-mahi / dolphinfish), and other large pelagic fish",
    "SEU": "Pencil urchin (Eucidaris thouarsii), Purple urchin (Strongylocentrotus purpuratus), other sea urchins",
    "CNA": "Corals (various species), anemones, cnidarians",
    "ORC": "Killer whale / orca (Orcinus orca), apex predator feeding on marine mammals, fish, and sea turtles",
}


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
    total_changed = 0

    with engine.begin() as conn:
        for old_code, col, values, new_code, new_name, note in RECLASSIFICATIONS:
            placeholders = ", ".join(f":v{i}" for i in range(len(values)))
            params = {f"v{i}": v for i, v in enumerate(values)}
            params["old_code"] = old_code

            rows = conn.execute(
                text(
                    f"SELECT taxon, current_code, current_group FROM species "
                    f"WHERE current_code = :old_code AND {col} IN ({placeholders})"
                ),
                params,
            ).fetchall()

            target_code = new_code or old_code
            print(f"\n[{old_code} -> {target_code}] {new_name} ({len(rows)} especies) — {note}")

            for r in rows:
                conn.execute(
                    text(
                        "UPDATE species SET current_code=:new_code, current_group=:new_name "
                        "WHERE taxon=:taxon"
                    ),
                    {"new_code": target_code, "new_name": new_name, "taxon": r.taxon},
                )
                conn.execute(
                    text(
                        """INSERT INTO audit_log
                               (taxon, action, expert, from_code, to_code, to_name, note)
                           VALUES (:taxon, 'move', 'system', :from_code, :to_code, :to_name, :note)"""
                    ),
                    {
                        "taxon": r.taxon,
                        "from_code": r.current_code,
                        "to_code": target_code,
                        "to_name": new_name,
                        "note": note,
                    },
                )
                total_changed += 1

        # Catch-all: anything still under COR that isn't Cynoscion belongs to Corals/Anemones
        old_code, new_code, new_name = CATCH_ALL
        rows = conn.execute(
            text(
                "SELECT taxon, current_code, current_group FROM species "
                "WHERE current_code = :old_code AND (genus IS NULL OR genus != 'Cynoscion')"
            ),
            {"old_code": old_code},
        ).fetchall()
        print(f"\n[{old_code} -> {new_code}] {new_name} catch-all ({len(rows)} especies)")
        for r in rows:
            conn.execute(
                text(
                    "UPDATE species SET current_code=:new_code, current_group=:new_name "
                    "WHERE taxon=:taxon"
                ),
                {"new_code": new_code, "new_name": new_name, "taxon": r.taxon},
            )
            conn.execute(
                text(
                    """INSERT INTO audit_log
                           (taxon, action, expert, from_code, to_code, to_name, note)
                       VALUES (:taxon, 'move', 'system', :from_code, :to_code, :to_name,
                               'Code COR catch-all cleanup: remaining coral/anemone genera moved to CNA')"""
                ),
                {"taxon": r.taxon, "from_code": r.current_code, "to_code": new_code, "to_name": new_name},
            )
            total_changed += 1

        # Seed descriptions for the new codes
        for code, desc in NEW_DESCRIPTIONS.items():
            conn.execute(
                text(
                    """MERGE group_descriptions AS target
                       USING (SELECT :group_code AS group_code) AS source ON target.group_code = source.group_code
                       WHEN MATCHED THEN UPDATE SET description = :description, updated_by = 'system', updated_at = GETDATE()
                       WHEN NOT MATCHED THEN INSERT (group_code, description, updated_by) VALUES (:group_code, :description, 'system');"""
                ),
                {"group_code": code, "description": desc},
            )

    print(f"\nMigración completada: {total_changed} especies reclasificadas.")
    print("Códigos nuevos creados: DPF (Dolphinfish), SEU (Sea Urchins), CNA (Corals and Anemones), ORC (Orcas)")


if __name__ == "__main__":
    main()
