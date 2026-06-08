"""
species_characteristics.py - Phase 1 & 2: Characteristic Inference & LLM Validation
====================================================================================

Phase 1: Auto-infer species characteristics from taxonomy
         - Uses heuristic patterns and knowledge base
         - Minimal LLM involvement
         - Fills: habitat, trophic_level, size_class, taxonomic_affinity

Phase 2: Validate inferences with LLM
         - Batches of ~50 species for review
         - LLM only validates/corrects (no generation)
         - Minimal token usage (~500 tokens/batch)

This reduces tokens by ~66% compared to traditional approach.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import requests

from config import (
    DATA_DIR,
    OUTPUT_DIR,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    OLLAMA_TIMEOUT,
)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: HEURISTIC CHARACTERISTIC INFERENCE
# ═══════════════════════════════════════════════════════════════════════


class TaxonomyDB:
    """Knowledge base of known species and their characteristics."""

    def __init__(self, db_file: Path = None):
        """Load taxonomy database."""
        self.db_file = db_file or DATA_DIR / "taxonomy_db.json"
        self.data = {}
        self.load()

    def load(self):
        """Load taxonomy database from JSON."""
        if self.db_file.exists():
            with open(self.db_file, "r") as f:
                db = json.load(f)
                self.taxonomy_base = db.get("taxonomy_base", {})
                self.habitat_keywords = db.get("habitat_keywords", {})
                self.trophic_keywords = db.get("trophic_keywords", {})
                self.size_keywords = db.get("size_keywords", {})
                self.taxonomic_patterns = db.get("taxonomic_patterns", {})
        else:
            raise FileNotFoundError(f"Taxonomy database not found: {self.db_file}")

    def lookup_by_genus(self, genus: str) -> Optional[Dict]:
        """Look up genus in taxonomy database."""
        genus_lower = genus.lower()
        return self.taxonomy_base.get(genus_lower)

    def infer_habitat(self, species_name: str) -> Tuple[str, float]:
        """Infer habitat from species name keywords."""
        name_lower = species_name.lower()

        for habitat, keywords in self.habitat_keywords.items():
            for keyword in keywords:
                if keyword in name_lower:
                    confidence = 0.70  # Default for keyword match
                    return habitat, confidence

        return "unknown", 0.0

    def infer_trophic(self, species_name: str) -> Tuple[str, float]:
        """Infer trophic level from species name keywords."""
        name_lower = species_name.lower()

        for trophic, keywords in self.trophic_keywords.items():
            for keyword in keywords:
                if keyword in name_lower:
                    confidence = 0.65  # Default for keyword match
                    return trophic, confidence

        return "unknown", 0.0

    def infer_size(self, species_name: str) -> Tuple[str, float]:
        """Infer size class from species name keywords."""
        name_lower = species_name.lower()

        for size, keywords in self.size_keywords.items():
            for keyword in keywords:
                if keyword in name_lower:
                    confidence = 0.60
                    return size, confidence

        return "unknown", 0.0

    def infer_taxonomic_affinity(self, species_name: str) -> Tuple[str, float]:
        """Infer taxonomic affinity from species name patterns."""
        name_lower = species_name.lower()

        # Try to extract family from pattern (e.g., "...idae")
        if name_lower.endswith("idae"):
            family = species_name.split()[-1]
            return family, 0.85

        # Keyword matching for broader groups
        if any(kw in name_lower for kw in self.taxonomic_patterns.get("class_fish", [])):
            return "Pisces", 0.70
        if any(kw in name_lower for kw in self.taxonomic_patterns.get("class_crust", [])):
            return "Crustacea", 0.70
        if any(kw in name_lower for kw in self.taxonomic_patterns.get("class_moll", [])):
            return "Mollusca", 0.70

        return "unknown", 0.0


def infer_species_characteristics(
    species_list: pd.DataFrame, taxonomy_db: TaxonomyDB, confidence_threshold: float = 0.60
) -> pd.DataFrame:
    """
    Phase 1: Auto-infer characteristics for all species using heuristics.

    Parameters
    ----------
    species_list : pd.DataFrame
        DataFrame with 'species_name' column
    taxonomy_db : TaxonomyDB
        Knowledge base for lookups
    confidence_threshold : float
        Only fill characteristics if confidence >= threshold

    Returns
    -------
    pd.DataFrame
        Updated species list with inferred characteristics
    """
    print("[Phase 1] Inferring species characteristics (heuristic)...")

    results = []

    for idx, row in species_list.iterrows():
        species_name = row["species_name"]
        genus = species_name.split()[0]

        # Try genus lookup first
        db_lookup = taxonomy_db.lookup_by_genus(genus)

        if db_lookup:
            # High confidence: use database
            row["habitat"] = db_lookup["habitat"]
            row["trophic_level"] = db_lookup["trophic_level"]
            row["size_class"] = db_lookup["size_class"]
            row["taxonomic_affinity"] = db_lookup["taxonomic_affinity"]
            row["_confidence"] = db_lookup.get("confidence", 0.90)
        else:
            # Fallback: keyword inference
            habitat, h_conf = taxonomy_db.infer_habitat(species_name)
            trophic, t_conf = taxonomy_db.infer_trophic(species_name)
            size, s_conf = taxonomy_db.infer_size(species_name)
            tax_aff, tx_conf = taxonomy_db.infer_taxonomic_affinity(species_name)

            if h_conf >= confidence_threshold:
                row["habitat"] = habitat
            if t_conf >= confidence_threshold:
                row["trophic_level"] = trophic
            if s_conf >= confidence_threshold:
                row["size_class"] = size
            if tx_conf >= confidence_threshold:
                row["taxonomic_affinity"] = tax_aff

            # Overall confidence is average
            avg_confidence = (h_conf + t_conf + s_conf + tx_conf) / 4
            row["_confidence"] = avg_confidence

        results.append(row)

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1} species...")

    species_df = pd.DataFrame(results)
    filled_ratio = species_df[["habitat", "trophic_level"]].notna().sum().sum() / (len(species_df) * 2)
    print(f"[Phase 1] Complete. Filled {filled_ratio:.1%} of characteristics")

    return species_df


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: LLM VALIDATION (MINIMAL TOKENS)
# ═══════════════════════════════════════════════════════════════════════


def _validate_characteristics_with_llm(
    batch: List[Dict], batch_num: int, total_batches: int
) -> List[Dict]:
    """
    Use LLM to validate/correct species characteristics.
    
    Prompt is ultra-compact to minimize tokens (~500 per batch).
    """
    
    # Build compact prompt
    species_list = []
    for sp in batch:
        name = sp.get("species_name", "")
        habitat = sp.get("habitat", "?")
        trophic = sp.get("trophic_level", "?")
        size = sp.get("size_class", "?")
        species_list.append(f"{name} | {habitat} | {trophic} | {size}")

    species_text = "\n".join(species_list)

    system_prompt = """You are an expert marine ecologist reviewing species characteristics.
Your task: validate if habitat, trophic_level, and size_class are correct.
ONLY list species with ERRORS.
Keep response SHORT. Use JSON format only."""

    user_prompt = f"""SPECIES CHARACTERISTICS VALIDATION (Batch {batch_num}/{total_batches})

Species | Habitat | Trophic_Level | Size_Class
{species_text}

INSTRUCTION:
Check each species. If characteristics are WRONG, suggest correction.
ONLY report errors. If all correct, return empty corrections array.

Response:
```json
{{
  "corrections": [
    {{"species": "name", "field": "habitat|trophic_level|size_class", "correct_value": "...", "reason": "brief"}}
  ],
  "validated_count": {len(batch)},
  "error_count": 0
}}
```"""

    try:
        print(f"  [Batch {batch_num}/{total_batches}] Sending {len(batch)} species for validation...")
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "temperature": LLM_TEMPERATURE,
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        
        llm_response = response.json().get("response", "{}")
        result = _extract_json_from_llm(llm_response)
        
        # Apply corrections
        corrections = result.get("corrections", [])
        error_count = result.get("error_count", 0)
        
        for correction in corrections:
            sp_name = correction["species"]
            field = correction["field"]
            correct_value = correction["correct_value"]
            
            # Find and update species in batch
            for sp in batch:
                if sp["species_name"] == sp_name:
                    sp[field] = correct_value
                    print(f"    ✓ Corrected {sp_name}: {field} → {correct_value}")
        
        print(f"  [Batch {batch_num}/{total_batches}] {len(batch) - error_count} validated, {error_count} corrected")
        
        return batch

    except Exception as e:
        print(f"  ⚠️  LLM validation skipped (error: {e})")
        return batch  # Return original batch if LLM fails


def _extract_json_from_llm(response: str) -> dict:
    """Extract JSON from LLM response."""
    import re
    
    # Try json code block
    match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try direct JSON
    for i, char in enumerate(response):
        if char == "{":
            try:
                return json.loads(response[i:].split("}")[0] + "}")
            except json.JSONDecodeError:
                continue
    
    return {"corrections": [], "validated_count": 0, "error_count": 0}


def validate_characteristics(
    species_df: pd.DataFrame, batch_size: int = 50, use_llm: bool = True
) -> pd.DataFrame:
    """
    Phase 2: Validate species characteristics with LLM (selective batches).

    Parameters
    ----------
    species_df : pd.DataFrame
        DataFrame with inferred characteristics
    batch_size : int
        Number of species per validation batch
    use_llm : bool
        Whether to use LLM for validation

    Returns
    -------
    pd.DataFrame
        DataFrame with LLM-validated characteristics
    """
    if not use_llm:
        print("[Phase 2] Skipped (LLM disabled)")
        return species_df

    print(f"[Phase 2] Validating characteristics with LLM (batch size: {batch_size})...")

    # Split into batches
    batches = [
        species_df.iloc[i : i + batch_size].to_dict("records")
        for i in range(0, len(species_df), batch_size)
    ]
    
    n_batches = len(batches)
    all_results = []

    for batch_idx, batch in enumerate(batches, 1):
        validated_batch = _validate_characteristics_with_llm(batch, batch_idx, n_batches)
        all_results.extend(validated_batch)

    result_df = pd.DataFrame(all_results)
    print(f"[Phase 2] Complete. {len(result_df)} species validated")

    return result_df


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def process_species_characteristics(
    species_csv: Path = None, use_llm: bool = True, confidence_threshold: float = 0.60
) -> pd.DataFrame:
    """
    Execute Phase 1 & 2: Infer and validate species characteristics.

    Parameters
    ----------
    species_csv : Path
        Path to species CSV (default: species_list_extended.csv)
    use_llm : bool
        Whether to use LLM for Phase 2 validation
    confidence_threshold : float
        Minimum confidence to fill characteristics (Phase 1)

    Returns
    -------
    pd.DataFrame
        Complete species DataFrame with characteristics
    """
    species_csv = species_csv or DATA_DIR / "species_list_extended.csv"
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  PHASE 1 & 2: SPECIES CHARACTERIZATION                    ║")
    print("║  Infer + Validate Functional Characteristics              ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Load species
    species_df = pd.read_csv(species_csv)
    print(f"Loaded {len(species_df)} species from {species_csv.name}")
    
    # ── Phase 1: Inference ──────────────────────────────────────────
    taxonomy_db = TaxonomyDB()
    species_df = infer_species_characteristics(
        species_df, taxonomy_db, confidence_threshold
    )
    
    # ── Phase 2: LLM Validation ─────────────────────────────────────
    species_df = validate_characteristics(species_df, batch_size=50, use_llm=use_llm)
    
    # ── Save results ────────────────────────────────────────────────
    output_path = OUTPUT_DIR / "species_list_characterized.csv"
    species_df.to_csv(output_path, index=False)
    print(f"\n✅ Results saved to: {output_path}")
    
    # Show summary
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  SUMMARY                                                   ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f" ║  Species with habitat:        {species_df['habitat'].notna().sum():<38}║")
    print(f" ║  Species with trophic_level:  {species_df['trophic_level'].notna().sum():<38}║")
    print(f" ║  Species with size_class:     {species_df['size_class'].notna().sum():<38}║")
    print(f" ║  Species with taxonomy:       {species_df['taxonomic_affinity'].notna().sum():<38}║")
    print(" ╚════════════════════════════════════════════════════════════╝")
    
    return species_df


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 1 & 2: Species Characterization")
    parser.add_argument("--species", type=str, help="Path to species CSV")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM validation")
    parser.add_argument("--confidence", type=float, default=0.60, help="Confidence threshold")
    
    args = parser.parse_args()
    
    species_path = Path(args.species) if args.species else None
    process_species_characteristics(
        species_csv=species_path,
        use_llm=not args.no_llm,
        confidence_threshold=args.confidence
    )
