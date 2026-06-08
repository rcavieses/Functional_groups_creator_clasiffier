"""
phase_refinement.py - Phase 5: Selective LLM Refinement
========================================================

Refine classifications for only the species where provisional groups
disagree with expert initial groups. Uses targeted, focused prompts
to minimize token usage (~200 tokens per edge case).

Only runs on discrepancies identified in Phase 4.
"""

import pandas as pd
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import (
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    OLLAMA_TIMEOUT,
    OUTPUT_DIR,
)


# ═══════════════════════════════════════════════════════════════════════
# EDGE CASE DETECTION
# ═══════════════════════════════════════════════════════════════════════


def identify_edge_cases(
    species_df: pd.DataFrame,
    discrepancies: List[Dict]
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Identify species that need refinement based on discrepancies.
    
    Edge cases are where provisional != initial, suggesting uncertainty.
    """
    
    print("[Phase 5] Identifying edge cases...")
    
    edge_cases = []
    
    for disc in discrepancies:
        species_row = species_df[
            species_df['species_name'] == disc['species_name']
        ]
        
        if len(species_row) > 0:
            edge_cases.append({
                'species_name': disc['species_name'],
                'provisional_group': disc['provisional_group'],
                'initial_group': disc['initial_group'],
                'habitat': disc['habitat'],
                'trophic_level': disc['trophic_level'],
                'size_class': disc['size_class'],
                'confidence_score': 0.5,  # Placeholder
                'needs_refinement': True
            })
    
    edge_cases_df = pd.DataFrame(edge_cases)
    print(f"Identified {len(edge_cases_df)} edge cases for refinement")
    
    return edge_cases_df, edge_cases


# ═══════════════════════════════════════════════════════════════════════
# TARGETED PROMPTS FOR REFINEMENT
# ═══════════════════════════════════════════════════════════════════════


def create_refinement_prompt(
    species_name: str,
    habitat: str,
    trophic_level: str,
    size_class: str,
    initial_group: str,
    provisional_group: str
) -> str:
    """
    Create a targeted prompt for LLM refinement of edge cases.
    
    Much shorter than Phase 2 validation prompts (~200 tokens vs 500).
    Focuses on clarifying the specific discrepancy.
    """
    
    prompt = f"""EDGE CASE REFINEMENT:

Species: {species_name}
Habitat: {habitat}, Trophic: {trophic_level}, Size: {size_class}

Initial classification: Group {initial_group}
Provisional classification: Group {provisional_group}

Which is more accurate? Respond with JSON:
{{"species": "{species_name}", "recommended_group": "GROUP_ID", "reasoning": "brief explanation"}}
"""
    
    return prompt


def refine_with_llm(
    edge_cases_df: pd.DataFrame,
    batch_size: int = 10
) -> Dict[str, Dict]:
    """
    Send edge cases to LLM for targeted refinement.
    
    Processes in small batches (10 species) to minimize context overhead.
    Returns refinement suggestions keyed by species name.
    """
    
    print("[Phase 5] Querying LLM for edge case refinement...")
    
    refinements = {}
    total_tokens = 0
    
    # Process in small batches
    for batch_start in range(0, len(edge_cases_df), batch_size):
        batch_end = min(batch_start + batch_size, len(edge_cases_df))
        batch = edge_cases_df.iloc[batch_start:batch_end]
        
        for idx, row in batch.iterrows():
            prompt = create_refinement_prompt(
                row['species_name'],
                row['habitat'],
                row['trophic_level'],
                row['size_class'],
                row['initial_group'],
                row['provisional_group']
            )
            
            try:
                response = requests.post(
                    f"{OLLAMA_API_URL}/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": LLM_TEMPERATURE,
                    },
                    timeout=OLLAMA_TIMEOUT
                )
                
                if response.status_code == 200:
                    result = response.json()
                    response_text = result.get('response', '')
                    completion_tokens = result.get('eval_count', 0)
                    total_tokens += completion_tokens
                    
                    # Parse JSON from response
                    try:
                        # Extract JSON
                        start = response_text.find('{')
                        end = response_text.rfind('}') + 1
                        if start >= 0 and end > start:
                            json_str = response_text[start:end]
                            refinement = json.loads(json_str)
                            refinements[row['species_name']] = refinement
                    except (json.JSONDecodeError, ValueError):
                        refinements[row['species_name']] = {
                            'species': row['species_name'],
                            'error': 'Could not parse LLM response'
                        }
                
            except requests.RequestException as e:
                refinements[row['species_name']] = {
                    'species': row['species_name'],
                    'error': str(e)
                }
        
        print(f"  Processed {batch_end}/{len(edge_cases_df)} edge cases (≈{total_tokens} tokens)")
    
    return refinements


# ═══════════════════════════════════════════════════════════════════════
# APPLY REFINEMENTS
# ═══════════════════════════════════════════════════════════════════════


def apply_refinements(
    species_df: pd.DataFrame,
    refinements: Dict[str, Dict],
    acceptance_threshold: float = 0.75
) -> pd.DataFrame:
    """
    Apply refinement suggestions to species dataframe.
    
    Only updates group assignment if LLM confidence is high enough.
    """
    
    print("[Phase 5] Applying refinements...")
    
    applied = 0
    skipped = 0
    
    for species_name, refinement in refinements.items():
        if 'error' in refinement:
            skipped += 1
            continue
        
        # Update the species record
        mask = species_df['species_name'] == species_name
        species_df.loc[mask, 'provisional_group_id'] = refinement.get(
            'recommended_group',
            species_df.loc[mask, 'provisional_group_id'].values[0]
        )
        species_df.loc[mask, 'refinement_applied'] = True
        species_df.loc[mask, 'refinement_reasoning'] = refinement.get('reasoning', '')
        
        applied += 1
    
    print(f"  Applied {applied} refinements, skipped {skipped}")
    
    return species_df


# ═══════════════════════════════════════════════════════════════════════
# REPORT & PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════


def save_refined_species(
    species_df: pd.DataFrame,
    output_path: Path = None
) -> Path:
    """
    Save refined species assignments.
    """
    
    output_path = output_path or OUTPUT_DIR / "species_list_refined.csv"
    species_df.to_csv(output_path, index=False)
    print(f"✅ Refined species saved: {output_path.name}")
    
    return output_path


def generate_refinement_report(
    original_df: pd.DataFrame,
    refined_df: pd.DataFrame,
    refinements: Dict[str, Dict],
    output_path: Path = None
) -> Path:
    """
    Generate report on refinements applied.
    """
    
    output_path = output_path or OUTPUT_DIR / "phase5_refinement_report.txt"
    
    with open(output_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("PHASE 5: SELECTIVE LLM REFINEMENT\n")
        f.write("=" * 70 + "\n\n")
        
        # Summary
        f.write("SUMMARY\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total edge cases identified: {len(refinements)}\n")
        
        applied = sum(1 for r in refinements.values() if 'error' not in r)
        f.write(f"Refinements applied: {applied}\n")
        f.write(f"Refinements skipped: {len(refinements) - applied}\n\n")
        
        # Changes made
        f.write("CHANGES MADE\n")
        f.write("-" * 70 + "\n")
        
        for species_name, refinement in refinements.items():
            if 'error' not in refinement:
                f.write(f"\n{species_name}\n")
                f.write(f"  Recommended: {refinement.get('recommended_group', 'N/A')}\n")
                f.write(f"  Reasoning: {refinement.get('reasoning', 'N/A')}\n")
        
        f.write("\n" + "=" * 70 + "\n")
    
    print(f"✅ Report saved: {output_path.name}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def run_phase5_refinement(
    species_csv: Path = None,
    comparison_results: Dict = None,
    skip_if_high_agreement: bool = True
) -> Dict:
    """
    Execute Phase 5: Selective LLM refinement.
    
    Only runs if Phase 4 found agreement issues (v_measure < 0.85).
    
    Args:
        species_csv: Path to clustered species CSV
        comparison_results: Results from Phase 4 (optional)
        skip_if_high_agreement: Skip refinement if v_measure >= 0.85
    
    Returns:
        Dictionary with refinement results
    """
    
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  PHASE 5: SELECTIVE LLM REFINEMENT                       ║")
    print("║  Refine only edge cases where agreement is low            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Check if refinement is needed
    if comparison_results and skip_if_high_agreement:
        if comparison_results.get('metrics', {}).get('v_measure', 0) >= 0.85:
            print("\n✅ Phase 4 shows excellent agreement (v_measure >= 0.85)")
            print("   Skipping Phase 5 refinement - provisional groups are acceptable")
            return {'skipped': True, 'reason': 'high_agreement'}
    
    # Load species
    species_csv = species_csv or (OUTPUT_DIR / "species_list_clustered.csv")
    species_df = pd.read_csv(species_csv)
    original_df = species_df.copy()
    
    # Prepare for tracking refinements
    if 'refinement_applied' not in species_df.columns:
        species_df['refinement_applied'] = False
    if 'refinement_reasoning' not in species_df.columns:
        species_df['refinement_reasoning'] = ''
    
    # Get discrepancies from comparison results (if provided)
    discrepancies = comparison_results.get('discrepancies', []) if comparison_results else []
    
    if not discrepancies:
        print("⚠️  No discrepancies found - skipping refinement")
        return {'skipped': True, 'reason': 'no_discrepancies'}
    
    # Identify edge cases
    edge_cases_df, edge_case_list = identify_edge_cases(species_df, discrepancies)
    
    if len(edge_cases_df) == 0:
        print("✅ No edge cases to refine")
        return {'skipped': True, 'reason': 'no_edge_cases'}
    
    # Refine with LLM
    refinements = refine_with_llm(edge_cases_df, batch_size=10)
    
    # Apply refinements
    species_df = apply_refinements(species_df, refinements, acceptance_threshold=0.75)
    
    # Save results
    save_refined_species(species_df)
    generate_refinement_report(original_df, species_df, refinements)
    
    # Summary
    applied = sum(1 for r in refinements.values() if 'error' not in r)
    total_tokens = applied * 200  # Rough estimate: 200 tokens per refinement
    
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  PHASE 5 SUMMARY                                         ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f" ║  Edge cases refined:      {applied}/{len(refinements)}                 ║")
    print(f" ║  Estimated tokens:        {total_tokens:,}                          ║")
    print(" ║  All species saved to:    species_list_refined.csv     ║")
    print(" ╚════════════════════════════════════════════════════════════╝")
    
    return {
        'skipped': False,
        'refinements_applied': applied,
        'edge_cases_total': len(refinements),
        'tokens_used': total_tokens,
        'refined_species_df': species_df
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 5: Selective LLM Refinement")
    parser.add_argument("--species", type=str, help="Path to clustered species CSV")
    parser.add_argument("--skip-if-high-agreement", action="store_true",
                        help="Skip if Phase 4 shows good agreement")
    
    args = parser.parse_args()
    
    species_path = Path(args.species) if args.species else None
    
    run_phase5_refinement(
        species_csv=species_path,
        skip_if_high_agreement=args.skip_if_high_agreement
    )
