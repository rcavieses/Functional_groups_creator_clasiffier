"""
classify_species.py - Classify species/genera into functional groups using LLM
===============================================================================

Usage:
    python classify_species.py --input data/final_taxonomy_occ.csv --by-genus
    python classify_species.py --input my_species.csv --provider anthropic
    python classify_species.py --input my_species.csv --workers 3 --no-reasoning

Options:
    --provider       LLM backend: 'ollama' (local, default) or 'anthropic' (Claude API).
    --by-genus       Classify unique genera instead of species (53% fewer LLM calls).
                     Requires a 'genus' column in the input CSV.
    --workers N      Parallel requests (default: 1). For Ollama, requires OLLAMA_NUM_PARALLEL>1.
    --no-reasoning   Skip reasoning field — shorter responses, faster inference.
    --batch-size N   Taxa per LLM call (default: 25; try 10 for better accuracy).
    --no-resume      Ignore existing output and reclassify everything.
    --rerun-low      Re-classify only taxa with low confidence from a previous run.
                     High/medium taxa are kept as-is. Use with reasoning enabled (default).

Input CSV:
    Must have a species/genus column (auto-detected: species_name, species, name,
    taxon, scientific_name, or the first column). If it also has taxonomy columns
    (class, order, family), they are included in the prompt to improve accuracy.

Output CSV columns:
    species_name (or genus_name), group_code, group_name, confidence[, reasoning]
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from config import (
    DATA_DIR,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    LLM_STREAMING,
    OLLAMA_TIMEOUT,
    OUTPUT_DIR,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
)

FINAL_GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"
DEFAULT_OUTPUT = OUTPUT_DIR / "species_classified.csv"
DEFAULT_BATCH_SIZE = 25


# ─── Data loading ──────────────────────────────────────────────────────────────


def load_groups(csv_path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Functional groups file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    missing = {"Functional_Group", "Code"} - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} missing columns: {missing}")
    code_to_name = dict(zip(df["Code"].str.strip(), df["Functional_Group"].str.strip()))
    print(f"[Groups] {len(df)} functional groups loaded.")
    return df, code_to_name


def build_groups_context(groups_df: pd.DataFrame) -> str:
    lines = []
    for _, row in groups_df.iterrows():
        code = str(row.get("Code", "")).strip()
        name = str(row.get("Functional_Group", "")).strip()
        comp = str(row.get("Species_Composition", "")).strip()
        if len(comp) > 70:
            comp = comp[:67] + "..."
        lines.append(f"{code} | {name} | {comp}")
    return "\n".join(lines)


def load_input(csv_path: Path, by_genus: bool) -> tuple[pd.DataFrame, str, list[str]]:
    """
    Load and prepare input CSV. Returns (work_df, taxon_col, tax_cols).
    In by_genus mode, deduplicates to unique genera keeping best taxonomy info.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Input file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    if by_genus and "genus" in df.columns:
        taxon_col = "genus"
    else:
        candidates = ["species_name", "species", "name", "taxon", "scientific_name"]
        taxon_col = next((c for c in candidates if c in df.columns), df.columns[0])

    tax_cols = [c for c in ["class", "order", "family"] if c in df.columns]

    if by_genus and taxon_col == "genus":
        work_df = (
            df.dropna(subset=["genus"])
            .drop_duplicates(subset=["genus"])
            [["genus"] + tax_cols]
            .reset_index(drop=True)
        )
        print(f"[Input] {len(df)} rows → {len(work_df)} unique genera (by-genus mode)")
    else:
        cols = [taxon_col] + tax_cols
        work_df = df[cols].copy()
        work_df = work_df.dropna(subset=[taxon_col])
        work_df[taxon_col] = work_df[taxon_col].str.strip()
        work_df = work_df[work_df[taxon_col] != ""].drop_duplicates(subset=[taxon_col]).reset_index(drop=True)
        print(f"[Input] {len(work_df)} unique taxa loaded from '{taxon_col}' column")

    return work_df, taxon_col, tax_cols


# ─── LLM interaction ───────────────────────────────────────────────────────────


def _extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _fallback_batch(taxa: list[str]) -> list[dict]:
    return [
        {"taxon": t, "code": "UNCLASSIFIED", "confidence": "low", "reasoning": "LLM error."}
        for t in taxa
    ]


def _build_prompt(groups_context: str, taxon_lines: list[str], include_reasoning: bool) -> tuple[str, str]:
    """Split prompt into (system, user) for structured provider calls."""
    reasoning_field = ', "reasoning": "<one sentence>"' if include_reasoning else ""
    system = (
        "You are a marine ecologist for the Gulf of California ecosystem (ATLANTIS model).\n"
        "Classify each taxon into the ONE best-matching functional group using taxonomy as primary signal.\n\n"
        f"FUNCTIONAL GROUPS (Code | Name | Key composition):\n{groups_context}"
    )
    user = (
        "TAXA TO CLASSIFY (taxonomy in brackets when available):\n"
        + "\n".join(taxon_lines)
        + "\n\nRules:\n"
        "- Use class/order/family as primary signal, species name as secondary.\n"
        "- For non-marine or terrestrial taxa, choose the ecologically closest group.\n"
        "- confidence: high=certain, medium=likely, low=uncertain.\n\n"
        "Respond ONLY with valid JSON, no extra text:\n"
        f'{{"classifications": [{{"taxon": "<name>", "code": "<CODE>", "confidence": "high|medium|low"{reasoning_field}}}]}}'
    )
    return system, user


def _call_ollama(system: str, user: str, batch_num: int, streaming: bool) -> str:
    prompt = f"{system}\n\n{user}"
    resp = requests.post(
        OLLAMA_API_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": streaming, "temperature": LLM_TEMPERATURE},
        timeout=OLLAMA_TIMEOUT,
        stream=streaming,
    )
    resp.raise_for_status()

    if not streaming:
        return resp.json().get("response", "")

    print(f"\n  ── Batch {batch_num} output ──────────────────────────")
    full_text = []
    for line in resp.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        token = chunk.get("response", "")
        print(token, end="", flush=True)
        full_text.append(token)
        if chunk.get("done"):
            break
    print()
    return "".join(full_text)


def _call_claude(system: str, user: str, batch_num: int, streaming: bool) -> str:
    """Call Claude API. Uses prompt caching on the groups context (system block)."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed — run: pip install anthropic")
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set — add it to .env or set the environment variable")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    # cache_control on system: groups context is identical across batches → cache hits after first call
    system_block = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    if not streaming:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system_block,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    print(f"\n  ── Batch {batch_num} output ──────────────────────────")
    full_text = []
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_block,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_text.append(text)
    print()
    return "".join(full_text)


def classify_batch(
    batch_df: pd.DataFrame,
    taxon_col: str,
    tax_cols: list[str],
    groups_context: str,
    batch_num: int,
    total_batches: int,
    include_reasoning: bool,
    streaming: bool,
    provider: str,
) -> list[dict]:
    # Build taxon lines — include taxonomy context when available
    lines = []
    for i, (_, row) in enumerate(batch_df.iterrows(), 1):
        name = str(row[taxon_col]).strip()
        if tax_cols:
            tax_parts = [
                f"{col}:{row[col]}"
                for col in tax_cols
                if pd.notna(row.get(col)) and str(row.get(col)).strip().lower() not in ("na", "nan", "")
            ]
            suffix = f" [{', '.join(tax_parts)}]" if tax_parts else ""
        else:
            suffix = ""
        lines.append(f"{i}. {name}{suffix}")

    system, user = _build_prompt(groups_context, lines, include_reasoning)

    try:
        if provider == "anthropic":
            raw = _call_claude(system, user, batch_num, streaming)
        else:
            raw = _call_ollama(system, user, batch_num, streaming)

        result = _extract_json(raw)
        classifications = result.get("classifications", [])
        if not classifications and isinstance(result, list):
            classifications = result

        classified_map = {c.get("taxon", "").strip().lower(): c for c in classifications}
        output = []
        for _, row in batch_df.iterrows():
            name = str(row[taxon_col]).strip()
            entry = classified_map.get(name.lower(), {})
            output.append({
                "taxon": name,
                "code": entry.get("code", entry.get("group_code", "UNCLASSIFIED")),
                "confidence": entry.get("confidence", "low"),
                "reasoning": entry.get("reasoning", ""),
            })
        return output

    except requests.exceptions.ConnectionError:
        print(f"  [Batch {batch_num}] ERROR: Cannot connect to Ollama — run: ollama serve")
        return _fallback_batch(batch_df[taxon_col].tolist())
    except Exception as e:
        print(f"  [Batch {batch_num}] ERROR: {type(e).__name__}: {e}")
        return _fallback_batch(batch_df[taxon_col].tolist())


# ─── Main classification pipeline ─────────────────────────────────────────────


def classify_all(
    input_csv: Path,
    output_csv: Path,
    batch_size: int,
    resume: bool,
    by_genus: bool,
    workers: int,
    include_reasoning: bool,
    streaming: bool,
    provider: str,
    rerun_low: bool = False,
) -> pd.DataFrame:
    groups_df, code_to_name = load_groups(FINAL_GROUPS_CSV)
    groups_context = build_groups_context(groups_df)
    work_df, taxon_col, tax_cols = load_input(input_csv, by_genus)

    out_key = "genus_name" if (by_genus and taxon_col == "genus") else "species_name"

    # Resume / rerun-low: determine which taxa to skip
    already_done: set[str] = set()
    all_results: list[dict] = []
    if (resume or rerun_low) and output_csv.exists():
        existing_df = pd.read_csv(output_csv)
        existing_key = None
        for k in ("species_name", "genus_name"):
            if k in existing_df.columns:
                existing_key = k
                break
        if existing_key and existing_key != out_key:
            print(
                f"[Warning] Existing output uses key '{existing_key}' but current mode expects '{out_key}'. "
                f"Ignoring old output and starting fresh. Use --no-resume to suppress this warning."
            )
        elif out_key in existing_df.columns:
            if rerun_low:
                # Keep high/medium confidence; re-classify low-confidence taxa
                conf_col = existing_df["confidence"] if "confidence" in existing_df.columns else pd.Series(dtype=str)
                keep_df = existing_df[conf_col != "low"]
                already_done = set(keep_df[out_key].dropna().str.strip())
                all_results = keep_df.to_dict("records")
                n_rerun = int((conf_col == "low").sum())
                print(f"[Rerun-low] {len(already_done)} taxa kept (high/medium) | "
                      f"{n_rerun} low-confidence taxa will be re-classified with reasoning.")
            else:
                already_done = set(existing_df[out_key].dropna().str.strip())
                all_results = existing_df.to_dict("records")
                print(f"[Resume] {len(already_done)} taxa already classified, skipping.")

    pending_df = work_df[~work_df[taxon_col].isin(already_done)].reset_index(drop=True)
    if pending_df.empty:
        print("[Done] All taxa already classified.")
        return pd.DataFrame(all_results)

    total = len(pending_df)
    batches = [pending_df.iloc[i: i + batch_size] for i in range(0, total, batch_size)]
    total_batches = len(batches)

    if streaming and workers > 1:
        print("[Warning] streaming + workers > 1 will interleave output. Consider --workers 1 with --stream.")

    mode_label = "genus" if (by_genus and taxon_col == "genus") else "species"
    model_info = CLAUDE_MODEL if provider == "anthropic" else OLLAMA_MODEL
    print(f"[Classify] mode: {mode_label} | {total} taxa | {total_batches} batches × {batch_size} | "
          f"provider: {provider} | model: {model_info} | workers: {workers} | "
          f"reasoning: {include_reasoning} | stream: {streaming}\n")

    completed = 0
    t_start = time.time()

    def process(args: tuple[int, pd.DataFrame, bool]) -> tuple[int, list[dict], float]:
        idx, batch_df, stream = args
        t0 = time.time()
        results = classify_batch(
            batch_df, taxon_col, tax_cols, groups_context,
            idx, total_batches, include_reasoning, stream, provider,
        )
        return idx, results, time.time() - t0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(process, (i + 1, b, streaming)) for i, b in enumerate(batches)]
        for future in as_completed(futures):
            batch_idx, results, elapsed = future.result()
            completed += len(results)

            for entry in results:
                code = entry["code"]
                row: dict = {
                    out_key: entry["taxon"],
                    "group_code": code,
                    "group_name": code_to_name.get(code, "Unclassified"),
                    "confidence": entry["confidence"],
                }
                if include_reasoning:
                    row["reasoning"] = entry["reasoning"]
                all_results.append(row)

            pd.DataFrame(all_results).to_csv(output_csv, index=False)

            elapsed_total = time.time() - t_start
            rate = completed / elapsed_total if elapsed_total > 0 else 1
            eta = (total - completed) / rate
            print(f"  Batch {batch_idx}/{total_batches} — {elapsed:.1f}s | "
                  f"{completed}/{total} taxa done | ETA: {eta:.0f}s")

    result_df = pd.DataFrame(all_results)
    result_df.to_csv(output_csv, index=False)
    _print_summary(result_df, out_key, output_csv, include_reasoning)
    return result_df


def _print_summary(df: pd.DataFrame, key_col: str, output_csv: Path, include_reasoning: bool) -> None:
    n = len(df)
    if n == 0:
        return
    unclass = (df["group_code"] == "UNCLASSIFIED").sum()
    high = (df["confidence"] == "high").sum()
    med = (df["confidence"] == "medium").sum()
    low_c = (df["confidence"] == "low").sum()

    print("\n" + "=" * 60)
    print("CLASSIFICATION SUMMARY")
    print("=" * 60)
    print(f"  Classified      : {n - unclass} / {n}")
    print(f"  Unclassified    : {unclass}")
    print(f"  Confidence high : {high} ({high / n:.0%})")
    print(f"  Confidence med  : {med} ({med / n:.0%})")
    print(f"  Confidence low  : {low_c} ({low_c / n:.0%})")
    print(f"  Saved to        : {output_csv}")

    top = (
        df[df["group_code"] != "UNCLASSIFIED"]
        .groupby(["group_code", "group_name"]).size()
        .reset_index(name="count").sort_values("count", ascending=False)
    )
    print("\n  Top groups:")
    for _, row in top.head(10).iterrows():
        print(f"    {row['group_code']:<6} {row['group_name']:<35} — {row['count']}")


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Classify species/genera into functional groups using a local or cloud LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local Ollama (default) — fastest with no API cost
  python classify_species.py --input data/final_taxonomy_occ.csv --by-genus --no-reasoning

  # Claude Haiku via Anthropic API (~$0.62 with prompt caching, by-genus mode)
  python classify_species.py --input data/final_taxonomy_occ.csv --by-genus --provider anthropic --no-reasoning

  # Second pass: re-classify only low-confidence taxa WITH reasoning
  python classify_species.py --input data/final_taxonomy_occ.csv --by-genus --provider anthropic --rerun-low

  # Parallel requests (Ollama with OLLAMA_NUM_PARALLEL=3)
  python classify_species.py --input data/final_taxonomy_occ.csv --by-genus --workers 3

  # Standard species-level classification
  python classify_species.py --input data/my_species.csv --batch-size 10
        """,
    )
    parser.add_argument("--input", "-i", type=Path, required=True,
                        help="Input CSV with species or genus names.")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output CSV path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--batch-size", "-b", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Taxa per LLM call (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--by-genus", action="store_true",
                        help="Classify unique genera instead of species (~53%% fewer LLM calls). "
                             "Requires a 'genus' column in the input CSV.")
    parser.add_argument("--workers", "-w", type=int, default=1,
                        help="Parallel Ollama requests (default: 1). Increase only if Ollama "
                             "is configured with OLLAMA_NUM_PARALLEL > 1.")
    parser.add_argument("--no-reasoning", action="store_true",
                        help="Skip reasoning field — shorter LLM responses, faster inference.")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore existing output and reclassify everything.")
    parser.add_argument("--rerun-low", action="store_true",
                        help="Re-classify only taxa with low confidence from the existing output. "
                             "High and medium confidence taxa are kept unchanged. "
                             "Reasoning is enabled by default for this mode.")
    parser.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama",
                        help="LLM provider: 'ollama' (local, default) or 'anthropic' (Claude API). "
                             "For Anthropic, set ANTHROPIC_API_KEY in .env. "
                             f"Default Claude model: {CLAUDE_MODEL} (override with CLAUDE_MODEL in .env).")
    parser.add_argument("--stream", action="store_true", default=LLM_STREAMING,
                        help="Stream model output token by token (default: from config LLM_STREAMING). "
                             "Not recommended with --workers > 1.")
    parser.add_argument("--no-stream", dest="stream", action="store_false",
                        help="Disable streaming (wait for full response before printing).")

    args = parser.parse_args()

    try:
        classify_all(
            input_csv=args.input,
            output_csv=args.output,
            batch_size=args.batch_size,
            resume=not args.no_resume,
            by_genus=args.by_genus,
            workers=args.workers,
            include_reasoning=not args.no_reasoning,
            streaming=args.stream,
            provider=args.provider,
            rerun_low=args.rerun_low,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress saved to output file.")
        sys.exit(0)


if __name__ == "__main__":
    main()
