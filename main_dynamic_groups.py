"""
main_dynamic_groups.py - Dynamic Functional Group Creation via LLM
===================================================================

Approach: Process species in batches. For each batch, the LLM either:
  - Assigns species to an EXISTING group (already created in prior batches)
  - Creates a NEW functional group if none fits

No pre-existing group list required. Groups emerge organically as the
LLM processes species from scratch.

Features:
  - Incremental group building (groups grow batch by batch)
  - Checkpoint/resume support (saves progress after each batch)
  - Compact group summaries to minimize token usage
  - Configurable batch size and study context
"""

import json
import sys
import re
import time
import argparse
import pandas as pd
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from config import (
    DATA_DIR,
    OUTPUT_DIR,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    OLLAMA_TIMEOUT,
    LLM_STREAMING,
)

# ─── Output paths ────────────────────────────────────────────────────
DYNAMIC_GROUPS_JSON = OUTPUT_DIR / "dynamic_groups.json"
DYNAMIC_SPECIES_CSV = OUTPUT_DIR / "species_dynamic_classified.csv"
CHECKPOINT_FILE = OUTPUT_DIR / "dynamic_checkpoint.json"
REPORT_FILE = OUTPUT_DIR / "dynamic_classification_report.txt"

# ─── Default batch size ──────────────────────────────────────────────
DEFAULT_BATCH_SIZE = 25
MAX_GROUP_SUMMARY_PER_PROMPT = 120  # Max groups to include in prompt summary


# ═══════════════════════════════════════════════════════════════════════
# LLM COMMUNICATION
# ═══════════════════════════════════════════════════════════════════════


def call_llm(prompt: str, temperature: float = None) -> dict:
    """
    Call Ollama LLM and return the parsed response.

    Returns dict with keys: response (str), tokens (int), success (bool).
    """
    temp = temperature if temperature is not None else LLM_TEMPERATURE

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": LLM_STREAMING,
        "temperature": temp,
        "options": {"num_predict": LLM_MAX_TOKENS},
    }

    try:
        if LLM_STREAMING:
            # Streaming mode: read tokens as they arrive
            resp = requests.post(
                OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT, stream=True
            )
            resp.raise_for_status()

            full_response = []
            total_tokens = 0

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token_text = chunk.get("response", "")
                    if token_text:
                        full_response.append(token_text)
                        print(token_text, end="", flush=True)
                    if chunk.get("done", False):
                        total_tokens = chunk.get("eval_count", 0)
                except json.JSONDecodeError:
                    continue

            print()  # newline after streaming
            return {
                "response": "".join(full_response),
                "tokens": total_tokens,
                "success": True,
            }
        else:
            # Non-streaming mode
            resp = requests.post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            resp.raise_for_status()
            result = resp.json()
            return {
                "response": result.get("response", ""),
                "tokens": result.get("eval_count", 0),
                "success": True,
            }

    except requests.RequestException as e:
        print(f"\n  ⚠️  LLM call failed: {e}")
        return {"response": "", "tokens": 0, "success": False}


def extract_json_from_response(text: str) -> Optional[dict]:
    """Extract a JSON object from LLM response text."""
    # Strip <think>...</think> blocks (qwen3 reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try ```json ... ``` blocks (greedy to capture full JSON)
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try ``` ... ``` blocks (no json tag)
    match = re.search(r"```\s*([\{\[].*?[\}\]])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find the outermost { ... } using bracket matching
    depth = 0
    start = -1
    last_valid = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    parsed = json.loads(candidate)
                    if "assignments" in parsed:
                        return parsed
                    last_valid = parsed
                except json.JSONDecodeError:
                    pass
                start = -1

    return last_valid


# ═══════════════════════════════════════════════════════════════════════
# GROUP SUMMARY (compact representation for prompts)
# ═══════════════════════════════════════════════════════════════════════


def build_group_summary(groups: Dict[str, dict]) -> str:
    """
    Build a compact summary of existing groups for the LLM prompt.
    Each group is one line to minimize tokens.
    """
    if not groups:
        return "(No groups created yet. You must create new groups for every species.)"

    lines = []
    for gid, g in sorted(groups.items()):
        n_species = len(g.get("species", []))
        line = (
            f"  {gid}: {g['group_name']} | "
            f"habitat={g.get('habitat','?')}, "
            f"trophic={g.get('trophic_level','?')}, "
            f"size={g.get('size_class','?')} | "
            f"{n_species} spp"
        )
        lines.append(line)

    # If too many groups, summarize by category
    if len(lines) > MAX_GROUP_SUMMARY_PER_PROMPT:
        lines = lines[:MAX_GROUP_SUMMARY_PER_PROMPT]
        lines.append(f"  ... ({len(groups) - MAX_GROUP_SUMMARY_PER_PROMPT} more groups)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# PROMPT CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════


def build_classification_prompt(
    species_batch: List[str],
    existing_groups: Dict[str, dict],
    study_context: str,
    batch_num: int,
    total_batches: int,
) -> str:
    """
    Build the prompt for dynamic classification.

    The LLM must:
      1. For each species, decide if an existing group fits
      2. If no group fits, create a new one
      3. Return structured JSON
    """
    group_summary = build_group_summary(existing_groups)
    next_group_num = len(existing_groups) + 1

    species_list_text = "\n".join(f"  {i+1}. {sp}" for i, sp in enumerate(species_batch))

    prompt = f"""/no_think
FUNCTIONAL GROUP CLASSIFICATION (Batch {batch_num}/{total_batches})

CONTEXT: {study_context}

EXISTING FUNCTIONAL GROUPS ({len(existing_groups)} so far):
{group_summary}

SPECIES TO CLASSIFY:
{species_list_text}

TASK:
For each species above:
1. If an EXISTING group is appropriate → assign it
2. If NO existing group fits → CREATE a new group (next ID: FG{next_group_num:02d})

When creating a new group, think at the FUNCTIONAL level:
- Group by ecological role, not individual species
- A group should be able to contain multiple species with similar function
- Use categories: habitat (pelagic/demersal/benthic/terrestrial/freshwater),
  trophic_level (carnivore/herbivore/omnivore/planktivore/filter_feeder/
  primary_producer/decomposer/detritivore/zooplankton/scavenger),
  size_class (very_small/small/small-medium/medium/medium-large/large/very_large)

Respond ONLY with JSON (no extra text):
```json
{{
  "assignments": [
    {{"species": "species name", "group_id": "FG01", "is_new": false}},
    {{"species": "species name", "group_id": "FG{next_group_num:02d}", "is_new": true,
      "new_group": {{
        "group_name": "Short Descriptive Name",
        "description": "Brief ecological description",
        "habitat": "...",
        "trophic_level": "...",
        "size_class": "...",
        "taxonomic_affinity": "Family or higher taxon"
      }}
    }}
  ]
}}
```
"""
    return prompt


# ═══════════════════════════════════════════════════════════════════════
# CHECKPOINT / RESUME
# ═══════════════════════════════════════════════════════════════════════


def save_checkpoint(
    groups: Dict[str, dict],
    assignments: List[dict],
    last_batch: int,
    total_tokens: int,
):
    """Save progress so we can resume if interrupted."""
    checkpoint = {
        "groups": groups,
        "assignments": assignments,
        "last_batch_completed": last_batch,
        "total_tokens": total_tokens,
        "timestamp": datetime.now().isoformat(),
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def load_checkpoint() -> Optional[dict]:
    """Load checkpoint if it exists."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ═══════════════════════════════════════════════════════════════════════
# PROCESS A SINGLE BATCH
# ═══════════════════════════════════════════════════════════════════════


def process_batch(
    species_batch: List[str],
    existing_groups: Dict[str, dict],
    study_context: str,
    batch_num: int,
    total_batches: int,
    max_retries: int = 2,
) -> tuple:
    """
    Process one batch of species through LLM.

    Returns:
        (new_assignments: list[dict], updated_groups: dict, tokens_used: int)
    """
    prompt = build_classification_prompt(
        species_batch, existing_groups, study_context, batch_num, total_batches
    )

    for attempt in range(max_retries + 1):
        result = call_llm(prompt)

        if not result["success"]:
            if attempt < max_retries:
                print(f"  ⚠️  Retry {attempt+1}/{max_retries}...")
                time.sleep(5)
                continue
            print("  ❌ LLM failed after retries. Skipping batch.")
            return [], existing_groups, 0

        parsed = extract_json_from_response(result["response"])

        if parsed and "assignments" in parsed:
            break
        elif attempt < max_retries:
            # Log raw response snippet for diagnostics
            snippet = result["response"][:300].replace("\n", " ")
            print(f"  ⚠️  Could not parse JSON. Retry {attempt+1}/{max_retries}...")
            print(f"      Response preview: {snippet}...")
            time.sleep(3)
        else:
            snippet = result["response"][:500].replace("\n", " ")
            print(f"  ❌ Could not parse LLM response. Skipping batch.")
            print(f"      Response preview: {snippet}")
            return [], existing_groups, result["tokens"]

    # Process assignments
    new_assignments = []
    tokens_used = result["tokens"]

    for assignment in parsed["assignments"]:
        species_name = assignment.get("species", "").strip()
        group_id = assignment.get("group_id", "").strip()
        is_new = assignment.get("is_new", False)

        if not species_name or not group_id:
            continue

        # If LLM created a new group
        if is_new and "new_group" in assignment:
            ng = assignment["new_group"]
            # Avoid overwriting an existing group with the same ID
            if group_id in existing_groups:
                # Assign a new sequential ID
                next_id = len(existing_groups) + 1
                group_id = f"FG{next_id:02d}"

            existing_groups[group_id] = {
                "group_id": group_id,
                "group_name": ng.get("group_name", f"Group {group_id}"),
                "description": ng.get("description", ""),
                "habitat": ng.get("habitat", "unknown"),
                "trophic_level": ng.get("trophic_level", "unknown"),
                "size_class": ng.get("size_class", "unknown"),
                "taxonomic_affinity": ng.get("taxonomic_affinity", ""),
                "species": [],
            }

        # Record assignment
        if group_id in existing_groups:
            existing_groups[group_id].setdefault("species", []).append(species_name)
        else:
            # Group ID referenced doesn't exist — create a placeholder
            existing_groups[group_id] = {
                "group_id": group_id,
                "group_name": f"Group {group_id}",
                "description": "Auto-created placeholder",
                "habitat": "unknown",
                "trophic_level": "unknown",
                "size_class": "unknown",
                "taxonomic_affinity": "",
                "species": [species_name],
            }

        new_assignments.append(
            {
                "species_name": species_name,
                "group_id": group_id,
                "group_name": existing_groups[group_id]["group_name"],
                "is_new_group": is_new,
            }
        )

    return new_assignments, existing_groups, tokens_used


# ═══════════════════════════════════════════════════════════════════════
# SAVE FINAL OUTPUTS
# ═══════════════════════════════════════════════════════════════════════


def save_results(
    groups: Dict[str, dict],
    assignments: List[dict],
    total_tokens: int,
    elapsed: float,
):
    """Save final groups JSON, species CSV, and report."""

    # ── Groups JSON ────────────────────────────────────────────────
    groups_list = []
    for gid, g in sorted(groups.items()):
        groups_list.append(
            {
                "group_id": g["group_id"],
                "group_name": g["group_name"],
                "description": g["description"],
                "habitat": g["habitat"],
                "trophic_level": g["trophic_level"],
                "size_class": g["size_class"],
                "taxonomic_affinity": g["taxonomic_affinity"],
                "species": g.get("species", []),
                "species_count": len(g.get("species", [])),
            }
        )

    with open(DYNAMIC_GROUPS_JSON, "w", encoding="utf-8") as f:
        json.dump(groups_list, f, ensure_ascii=False, indent=2)
    print(f"✅ Groups saved: {DYNAMIC_GROUPS_JSON.name} ({len(groups_list)} groups)")

    # ── Species CSV ────────────────────────────────────────────────
    df = pd.DataFrame(assignments)
    df.to_csv(DYNAMIC_SPECIES_CSV, index=False)
    print(f"✅ Species assignments saved: {DYNAMIC_SPECIES_CSV.name} ({len(df)} species)")

    # ── Report ─────────────────────────────────────────────────────
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("DYNAMIC FUNCTIONAL GROUP CLASSIFICATION REPORT\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        f.write("SUMMARY\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total species classified: {len(assignments)}\n")
        f.write(f"Total functional groups created: {len(groups_list)}\n")
        f.write(f"Total LLM tokens used: {total_tokens:,}\n")
        f.write(f"Elapsed time: {elapsed:.1f} seconds\n\n")

        f.write("FUNCTIONAL GROUPS\n")
        f.write("-" * 70 + "\n")
        for g in groups_list:
            f.write(
                f"\n{g['group_id']}: {g['group_name']} ({g['species_count']} species)\n"
            )
            f.write(f"  Habitat: {g['habitat']}\n")
            f.write(f"  Trophic level: {g['trophic_level']}\n")
            f.write(f"  Size class: {g['size_class']}\n")
            f.write(f"  Taxonomic affinity: {g['taxonomic_affinity']}\n")
            f.write(f"  Description: {g['description']}\n")
            if g["species"]:
                sp_list = ", ".join(g["species"][:10])
                if g["species_count"] > 10:
                    sp_list += f", ... (+{g['species_count'] - 10} more)"
                f.write(f"  Species: {sp_list}\n")

        f.write("\n" + "=" * 70 + "\n")

    print(f"✅ Report saved: {REPORT_FILE.name}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN WORKFLOW
# ═══════════════════════════════════════════════════════════════════════


def run_dynamic_classification(
    species_csv: Optional[Path] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    study_context: str = "",
    resume: bool = True,
) -> Dict:
    """
    Main entry point: classify all species into dynamically created groups.

    Args:
        species_csv: Path to species list CSV (must have 'species_name' column)
        batch_size: Number of species per LLM call
        study_context: Description of the study area / ecosystem
        resume: If True, resume from last checkpoint
    """

    # ── Load species ────────────────────────────────────────────────
    species_csv = species_csv or DATA_DIR / "species_list.csv"
    if not species_csv.exists():
        print(f"❌ Species file not found: {species_csv}")
        return {"success": False}

    species_df = pd.read_csv(species_csv)
    all_species = species_df["species_name"].dropna().tolist()
    total_species = len(all_species)
    print(f"Loaded {total_species} species from {species_csv.name}")

    # ── Default study context ──────────────────────────────────────
    if not study_context:
        study_context = (
            "Marine and coastal ecosystem of the Gulf of California, Mexico. "
            "Includes marine, terrestrial and freshwater organisms. "
            "Species range from microorganisms (diatoms, dinoflagellates) to "
            "large marine mammals, plus terrestrial plants, reptiles, birds "
            "and insects found in the coastal zone."
        )

    # ── Resume from checkpoint? ────────────────────────────────────
    groups: Dict[str, dict] = {}
    assignments: List[dict] = []
    start_batch = 0
    total_tokens = 0

    if resume:
        ckpt = load_checkpoint()
        if ckpt:
            groups = ckpt.get("groups", {})
            assignments = ckpt.get("assignments", [])
            start_batch = ckpt.get("last_batch_completed", 0)
            total_tokens = ckpt.get("total_tokens", 0)

            if start_batch > 0:
                print(
                    f"📌 Resuming from batch {start_batch + 1} "
                    f"({len(assignments)} species already classified, "
                    f"{len(groups)} groups created)"
                )

    # ── Create batches ────────────────────────────────────────────
    batches = []
    for i in range(0, total_species, batch_size):
        batches.append(all_species[i : i + batch_size])

    total_batches = len(batches)

    # ── Header ────────────────────────────────────────────────────
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║  " + "DYNAMIC FUNCTIONAL GROUP CLASSIFICATION".center(64) + "  ║")
    print("║  " + "LLM-Driven Incremental Group Creation".center(64) + "  ║")
    print("║" + " " * 68 + "║")
    print("╠" + "═" * 68 + "╣")
    print(f"║  Species: {total_species}".ljust(69) + "║")
    print(f"║  Batch size: {batch_size}".ljust(69) + "║")
    print(f"║  Total batches: {total_batches}".ljust(69) + "║")
    print(f"║  LLM model: {OLLAMA_MODEL}".ljust(69) + "║")
    print(f"║  Streaming: {'ON' if LLM_STREAMING else 'OFF'}".ljust(69) + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    start_time = time.time()

    # ── Process batches ───────────────────────────────────────────
    for batch_idx in range(start_batch, total_batches):
        batch = batches[batch_idx]
        batch_display = batch_idx + 1

        print(f"\n{'─' * 70}")
        print(
            f"  BATCH {batch_display}/{total_batches} "
            f"({len(batch)} species) | "
            f"Groups so far: {len(groups)}"
        )
        print(f"{'─' * 70}")

        new_assignments, groups, tokens = process_batch(
            species_batch=batch,
            existing_groups=groups,
            study_context=study_context,
            batch_num=batch_display,
            total_batches=total_batches,
        )

        assignments.extend(new_assignments)
        total_tokens += tokens

        classified = len(new_assignments)
        skipped = len(batch) - classified
        if skipped > 0:
            print(f"  ⚠️  {skipped} species not classified in this batch")

        print(
            f"  ✓ Batch {batch_display} done: "
            f"{classified} classified, "
            f"{len(groups)} total groups, "
            f"~{total_tokens:,} tokens used"
        )

        # Save checkpoint after every batch
        save_checkpoint(groups, assignments, batch_display, total_tokens)

    # ── Final save ────────────────────────────────────────────────
    elapsed = time.time() - start_time

    print(f"\n{'═' * 70}")
    print("  SAVING FINAL RESULTS")
    print(f"{'═' * 70}\n")

    save_results(groups, assignments, total_tokens, elapsed)

    # Clean up checkpoint
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("🗑️  Checkpoint removed (classification complete)")

    # ── Final summary ─────────────────────────────────────────────
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║  CLASSIFICATION COMPLETE".ljust(69) + "║")
    print("╠" + "═" * 68 + "╣")
    print(f"║  Total species classified: {len(assignments)}".ljust(69) + "║")
    print(f"║  Functional groups created: {len(groups)}".ljust(69) + "║")
    print(f"║  Total tokens used: {total_tokens:,}".ljust(69) + "║")
    print(f"║  Elapsed time: {elapsed:.1f}s".ljust(69) + "║")
    print(f"║  Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(69) + "║")
    print("╚" + "═" * 68 + "╝")

    return {
        "success": True,
        "total_species": len(assignments),
        "total_groups": len(groups),
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed,
        "groups_file": str(DYNAMIC_GROUPS_JSON),
        "species_file": str(DYNAMIC_SPECIES_CSV),
        "report_file": str(REPORT_FILE),
    }


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Dynamic Functional Group Classification (LLM-driven)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main_dynamic_groups.py
  python main_dynamic_groups.py --batch-size 30
  python main_dynamic_groups.py --species data/species_list.csv --no-resume
  python main_dynamic_groups.py --context "Coral reef ecosystem in the Caribbean"
""",
    )

    parser.add_argument(
        "--species",
        type=str,
        default=None,
        help="Path to species CSV (default: data/species_list.csv)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Species per LLM batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--context",
        type=str,
        default="",
        help="Study area / ecosystem description",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh (ignore any checkpoint)",
    )

    args = parser.parse_args()

    species_path = Path(args.species) if args.species else None

    result = run_dynamic_classification(
        species_csv=species_path,
        batch_size=args.batch_size,
        study_context=args.context,
        resume=not args.no_resume,
    )

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
