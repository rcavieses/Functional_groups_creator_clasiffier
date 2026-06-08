"""
classify_species.py - Classify species into existing functional groups using LLM
================================================================================

Usage:
    python classify_species.py --input my_species.csv
    python classify_species.py --input my_species.csv --output results.csv --batch-size 20

The input CSV must have a column with species names (auto-detected: 'species_name',
'species', 'name', or the first column).

Each species is classified into one of the functional groups defined in
data/functional_groups_final.csv. The LLM (Ollama) decides the best group.

Output CSV columns:
    species_name, group_code, group_name, confidence, reasoning
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from config import (
    DATA_DIR,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    OLLAMA_TIMEOUT,
    OUTPUT_DIR,
)

# ─── Constants ─────────────────────────────────────────────────────────────────

FINAL_GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"
DEFAULT_OUTPUT = OUTPUT_DIR / "species_classified.csv"
DEFAULT_BATCH_SIZE = 25

# ─── Helpers ───────────────────────────────────────────────────────────────────


def load_groups(csv_path: Path) -> pd.DataFrame:
    """Load functional groups from CSV (supports functional_groups_final.csv format)."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Functional groups file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    required = {"Functional_Group", "Code"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} is missing columns: {missing}")
    print(f"[Groups] Loaded {len(df)} functional groups from {csv_path.name}")
    return df


def build_groups_context(groups_df: pd.DataFrame) -> str:
    """Build a compact, LLM-friendly list of all functional groups."""
    lines = ["#  | Code | Functional Group               | Key Species / Composition"]
    lines.append("-" * 105)
    for _, row in groups_df.iterrows():
        num = str(row.get("Number", "")).strip()
        code = str(row.get("Code", "")).strip()
        name = str(row.get("Functional_Group", "")).strip()
        composition = str(row.get("Species_Composition", "")).strip()
        # Truncate composition to keep prompt manageable
        if len(composition) > 80:
            composition = composition[:77] + "..."
        lines.append(f"{num:<3} | {code:<4} | {name:<30} | {composition}")
    return "\n".join(lines)


def detect_species_column(df: pd.DataFrame) -> str:
    """Auto-detect which column holds species names."""
    candidates = ["species_name", "species", "name", "taxon", "scientific_name"]
    for col in candidates:
        if col in df.columns:
            return col
    # Fall back to first column
    return df.columns[0]


def load_species(csv_path: Path) -> list[str]:
    """Load species names from input CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Input species file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    col = detect_species_column(df)
    species = df[col].dropna().str.strip().tolist()
    species = [s for s in species if s]
    print(f"[Input] Loaded {len(species)} species from '{col}' column in {csv_path.name}")
    return species


def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response, tolerating markdown fences."""
    # Try json fenced block first
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try first standalone JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def classify_batch(
    species_batch: list[str],
    groups_context: str,
    batch_num: int,
    total_batches: int,
) -> list[dict]:
    """
    Ask the LLM to classify a batch of species into functional groups.

    Returns a list of dicts: {species_name, group_id, group_name, confidence, reasoning}
    """
    numbered_species = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(species_batch))

    prompt = f"""You are an expert marine ecologist for the Gulf of California ecosystem model (ATLANTIS).
Your task: classify each species below into the MOST appropriate functional group from the list provided.

FUNCTIONAL GROUPS:
{groups_context}

SPECIES TO CLASSIFY (Batch {batch_num}/{total_batches}):
{numbered_species}

INSTRUCTIONS:
- Assign each species to the single best-matching group based on ecology, habitat, trophic role, and taxonomy.
- Use your knowledge of marine biology to assign even unfamiliar species.
- For non-marine or ambiguous species, choose the ecologically closest group.
- confidence: "high" (certain), "medium" (likely), or "low" (uncertain).
- reasoning: one concise sentence explaining the assignment.

Respond ONLY with valid JSON, no extra text:
```json
{{
  "classifications": [
    {{
      "species": "<species name>",
      "group_code": "<CODE>",
      "group_name": "<Functional Group name>",
      "confidence": "high|medium|low",
      "reasoning": "<one sentence>"
    }}
  ]
}}
```"""

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": LLM_TEMPERATURE,
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
        result = _extract_json(raw)
        classifications = result.get("classifications", [])

        if not classifications:
            print(f"  [Batch {batch_num}] WARNING: LLM returned empty classifications, retrying parse...")
            # Some models wrap it differently
            classifications = result if isinstance(result, list) else []

        # Normalize: ensure all input species are represented
        classified_names = {c.get("species", "").lower() for c in classifications}
        for name in species_batch:
            if name.lower() not in classified_names:
                classifications.append({
                    "species": name,
                    "group_code": "UNCLASSIFIED",
                    "group_name": "Unclassified",
                    "confidence": "low",
                    "reasoning": "LLM did not return a classification for this species.",
                })

        return classifications

    except requests.exceptions.ConnectionError:
        print(f"  [Batch {batch_num}] ERROR: Cannot connect to Ollama at {OLLAMA_API_URL}")
        print("  Make sure Ollama is running: ollama serve")
        return _fallback_batch(species_batch)
    except Exception as e:
        print(f"  [Batch {batch_num}] ERROR: {e}")
        return _fallback_batch(species_batch)


def _fallback_batch(species_batch: list[str]) -> list[dict]:
    """Return unclassified entries when LLM fails."""
    return [
        {
            "species": name,
            "group_code": "UNCLASSIFIED",
            "group_name": "Unclassified",
            "confidence": "low",
            "reasoning": "Classification skipped due to LLM error.",
        }
        for name in species_batch
    ]


# ─── Main ──────────────────────────────────────────────────────────────────────


def classify_species(
    input_csv: Path,
    output_csv: Path = DEFAULT_OUTPUT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume: bool = True,
) -> pd.DataFrame:
    """
    Classify all species in input_csv into functional groups using the LLM.

    Parameters
    ----------
    input_csv : Path
        CSV file with species names.
    output_csv : Path
        Where to save results.
    batch_size : int
        How many species to send per LLM call.
    resume : bool
        If True and output_csv already exists, skip already-classified species.

    Returns
    -------
    pd.DataFrame
        Results with columns: species_name, group_id, group_name, confidence, reasoning
    """
    groups_df = load_groups(FINAL_GROUPS_CSV)
    groups_context = build_groups_context(groups_df)
    all_species = load_species(input_csv)

    # Resume support: skip already-classified species
    already_done: set[str] = set()
    existing_rows: list[dict] = []
    if resume and output_csv.exists():
        existing_df = pd.read_csv(output_csv)
        already_done = set(existing_df["species_name"].dropna().str.strip().tolist())
        existing_rows = existing_df.to_dict("records")
        print(f"[Resume] {len(already_done)} species already classified, skipping.")

    pending = [s for s in all_species if s not in already_done]
    if not pending:
        print("[Done] All species already classified.")
        return pd.DataFrame(existing_rows)

    print(f"\n[Classify] {len(pending)} species to classify in batches of {batch_size}")
    print(f"[Classify] Using model: {OLLAMA_MODEL}\n")

    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    total_batches = len(batches)
    all_results: list[dict] = list(existing_rows)

    for batch_num, batch in enumerate(batches, start=1):
        print(f"  Batch {batch_num}/{total_batches}: classifying {len(batch)} species...")
        t0 = time.time()
        classifications = classify_batch(batch, groups_context, batch_num, total_batches)
        elapsed = time.time() - t0

        # Build a lookup by species name for this batch
        classified_map = {c.get("species", "").strip().lower(): c for c in classifications}

        for name in batch:
            entry = classified_map.get(name.lower(), {
                "species": name,
                "group_code": "UNCLASSIFIED",
                "group_name": "Unclassified",
                "confidence": "low",
                "reasoning": "Not returned by LLM.",
            })
            all_results.append({
                "species_name": name,
                "group_code": entry.get("group_code", "UNCLASSIFIED"),
                "group_name": entry.get("group_name", "Unclassified"),
                "confidence": entry.get("confidence", "low"),
                "reasoning": entry.get("reasoning", ""),
            })

        # Save checkpoint after every batch
        pd.DataFrame(all_results).to_csv(output_csv, index=False)
        print(f"  Batch {batch_num}/{total_batches} done in {elapsed:.1f}s — checkpoint saved.\n")

    result_df = pd.DataFrame(all_results)
    result_df.to_csv(output_csv, index=False)

    # Summary
    total = len(result_df)
    unclassified = (result_df["group_code"] == "UNCLASSIFIED").sum()
    high_conf = (result_df["confidence"] == "high").sum()
    medium_conf = (result_df["confidence"] == "medium").sum()
    low_conf = (result_df["confidence"] == "low").sum()

    print("=" * 60)
    print(f"CLASSIFICATION SUMMARY")
    print("=" * 60)
    print(f"  Total species classified : {total - unclassified} / {total}")
    print(f"  Unclassified             : {unclassified}")
    print(f"  Confidence — high        : {high_conf} ({high_conf/total:.0%})")
    print(f"  Confidence — medium      : {medium_conf} ({medium_conf/total:.0%})")
    print(f"  Confidence — low         : {low_conf} ({low_conf/total:.0%})")
    print(f"\n  Results saved to: {output_csv}")

    # Group distribution
    group_counts = (
        result_df[result_df["group_code"] != "UNCLASSIFIED"]
        .groupby(["group_code", "group_name"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    print("\n  Top groups assigned:")
    for _, row in group_counts.head(10).iterrows():
        print(f"    {row['group_code']:<5} {row['group_name']:<35} — {row['count']} species")

    return result_df


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Classify species into functional groups using the LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python classify_species.py --input data/new_species.csv
  python classify_species.py --input data/new_species.csv --output output/my_results.csv
  python classify_species.py --input data/new_species.csv --batch-size 15 --no-resume
        """,
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Path to input CSV file with species names.",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to output CSV file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of species per LLM call (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing output and reclassify all species.",
    )

    args = parser.parse_args()

    try:
        classify_species(
            input_csv=args.input,
            output_csv=args.output,
            batch_size=args.batch_size,
            resume=not args.no_resume,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress saved to output file.")
        sys.exit(0)


if __name__ == "__main__":
    main()
