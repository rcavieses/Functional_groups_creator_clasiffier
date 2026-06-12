#!/usr/bin/env python3
"""
Reclassify species that were in removed groups (DC, DL, DR).

Steps:
  1. Extract the 403 DC/DL/DR species from species_classified.csv
  2. Find their taxonomy in final_taxonomy_occ.csv
  3. Run classify_species with claude-sonnet-4-6
  4. Merge results back into species_classified.csv
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

# Force Sonnet 4.6 for this run
os.environ["CLAUDE_MODEL"] = "claude-sonnet-4-6"

import pandas as pd

DATA_DIR    = PROJECT_ROOT / "data"
OUTPUT_DIR  = PROJECT_ROOT / "output"
CLASSIFIED  = OUTPUT_DIR / "species_classified.csv"
TAXONOMY    = DATA_DIR / "final_taxonomy_occ.csv"
TEMP_INPUT  = DATA_DIR / "_reclass_input.csv"
TEMP_OUTPUT = OUTPUT_DIR / "_reclass_output.csv"

REMOVED_CODES = {"DC", "DL", "DR"}


def main():
    # ── 1. Extract species to reclassify ─────────────────────────────────────
    classified_df = pd.read_csv(CLASSIFIED)
    mask = classified_df["group_code"].isin(REMOVED_CODES)
    to_reclass = classified_df[mask]["species_name"].dropna().str.strip().unique()
    print(f"[1/4] Species to reclassify: {len(to_reclass)}")

    # ── 2. Build temp input with taxonomy where available ────────────────────
    taxonomy_df = pd.read_csv(TAXONOMY)
    # Normalize species column name
    tax_species_col = "species" if "species" in taxonomy_df.columns else taxonomy_df.columns[-1]
    taxonomy_df[tax_species_col] = taxonomy_df[tax_species_col].str.strip()

    tax_lookup = taxonomy_df.drop_duplicates(subset=[tax_species_col]).set_index(tax_species_col)

    rows = []
    found, missing = 0, 0
    for sp in to_reclass:
        if sp in tax_lookup.index:
            row = tax_lookup.loc[sp].to_dict()
            row["species"] = sp
            rows.append(row)
            found += 1
        else:
            rows.append({"species": sp})
            missing += 1

    temp_df = pd.DataFrame(rows)
    # Ensure species column is first
    cols = ["species"] + [c for c in temp_df.columns if c != "species"]
    temp_df = temp_df[cols]
    temp_df.to_csv(TEMP_INPUT, index=False)
    print(f"[2/4] Temp input saved: {found} with taxonomy, {missing} name-only")

    # ── 3. Run classifier ────────────────────────────────────────────────────
    print(f"[3/4] Running classify_species.py with claude-sonnet-4-6 …")
    sys.path.insert(0, str(PROJECT_ROOT / "classifier"))

    from classify_species import classify_all
    classify_all(
        input_csv=TEMP_INPUT,
        output_csv=TEMP_OUTPUT,
        batch_size=25,
        resume=False,
        by_genus=False,
        workers=1,
        include_reasoning=True,
        streaming=False,
        provider="anthropic",
        rerun_low=False,
    )

    # ── 4. Merge back into species_classified.csv ────────────────────────────
    print("[4/4] Merging results back …")
    new_df = pd.read_csv(TEMP_OUTPUT)
    # Normalize key column
    if "species_name" not in new_df.columns and "genus_name" not in new_df.columns:
        new_df.rename(columns={new_df.columns[0]: "species_name"}, inplace=True)

    new_lookup = new_df.set_index("species_name")

    updated = 0
    for idx, row in classified_df.iterrows():
        sp = row.get("species_name", "")
        if row["group_code"] in REMOVED_CODES and sp in new_lookup.index:
            new_row = new_lookup.loc[sp]
            classified_df.at[idx, "group_code"]  = new_row["group_code"]
            classified_df.at[idx, "group_name"]  = new_row["group_name"]
            classified_df.at[idx, "confidence"]  = new_row["confidence"]
            updated += 1

    classified_df.to_csv(CLASSIFIED, index=False)
    print(f"    Updated {updated} / {len(to_reclass)} species in {CLASSIFIED.name}")

    # Clean up temp files
    TEMP_INPUT.unlink(missing_ok=True)
    TEMP_OUTPUT.unlink(missing_ok=True)

    print("\n✓ Reclassification complete.")


if __name__ == "__main__":
    main()
