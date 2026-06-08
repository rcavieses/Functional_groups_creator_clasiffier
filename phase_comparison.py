"""
phase_comparison.py - Phase 4: Compare with Initial Groups
===========================================================

Compare provisional clustering results against expert-defined initial groups.
Use metrics (homogeneity, completeness, v-measure) to assess agreement.

Determines if Phase 5 refinement is needed.
"""

import pandas as pd
import json
from pathlib import Path
from typing import Dict, List, Tuple

from sklearn.metrics import homogeneity_score, completeness_score, v_measure_score, adjusted_rand_score
from sklearn.preprocessing import LabelEncoder

from config import DATA_DIR, OUTPUT_DIR


# ═══════════════════════════════════════════════════════════════════════
# LOAD & PREPARE DATA
# ═══════════════════════════════════════════════════════════════════════


def load_initial_groups(initial_groups_csv: Path = None) -> Dict[str, str]:
    """
    Load initial expert-defined groups into mapping dict.
    
    Returns: {species_name: group_id}
    """
    
    initial_groups_csv = initial_groups_csv or DATA_DIR / "initial_groups.csv"
    
    if not initial_groups_csv.exists():
        print(f"⚠️  Initial groups file not found: {initial_groups_csv}")
        return {}
    
    # Read initial groups CSV to get schema (handle quoted fields with embedded commas)
    groups_df = pd.read_csv(initial_groups_csv, on_bad_lines='skip')
    print(f"Loaded {len(groups_df)} initial groups from {initial_groups_csv.name}")
    
    return groups_df


def map_species_to_groups(
    species_df: pd.DataFrame,
    initial_groups_df: pd.DataFrame
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Map species to their expected initial groups.
    
    Returns:
        - Updated species_df with 'initial_group_id' column
        - List of unmatched species
    """
    
    # For now, we create a mapping based on characteristics
    # In production, you'd have a pre-populated CSV with assignments
    
    species_df['initial_group_id'] = 'UNKNOWN'
    unmatched = []
    
    # Simple heuristic mapping (this would be improved with actual data)
    mapping_rules = {
        ('pelagic', 'planktivore', 'small'): 'FG01',
        ('pelagic', 'carnivore', 'large'): 'FG02',
        ('benthic', 'filter_feeder', 'small'): 'FG04',
        ('pelagic', 'filter_feeder', 'very_large'): 'FG05',
        ('benthic', 'detritivore', 'medium'): 'FG06',
        ('benthic', 'omnivore', 'small'): 'FG07',
    }
    
    for idx, row in species_df.iterrows():
        key = (row['habitat'], row['trophic_level'], row['size_class'])
        group_id = mapping_rules.get(key, 'UNKNOWN')
        species_df.at[idx, 'initial_group_id'] = group_id
        
        if group_id == 'UNKNOWN':
            unmatched.append(row['species_name'])
    
    return species_df, unmatched


# ═══════════════════════════════════════════════════════════════════════
# COMPARISON METRICS
# ═══════════════════════════════════════════════════════════════════════


def calculate_clustering_metrics(
    species_df: pd.DataFrame
) -> Dict[str, float]:
    """
    Calculate clustering agreement metrics between provisional and initial groups.
    
    Metrics:
    - Homogeneity (0-1): Clusters contain only samples of a single label
    - Completeness (0-1): Samples of the same label are in the same cluster
    - V-Measure (0-1): Harmonic mean of homogeneity and completeness
    - Adjusted Rand Index (-1 to 1): Random-adjusted pair-wise comparison
    """
    
    print("[Phase 4] Calculating clustering agreement metrics...")
    
    # Get label encodings
    encoder_prov = LabelEncoder()
    encoder_init = LabelEncoder()
    
    y_provisional = encoder_prov.fit_transform(species_df['provisional_group_id'].astype(str))
    y_initial = encoder_init.fit_transform(species_df['initial_group_id'].astype(str))
    
    # Calculate metrics
    homogeneity = homogeneity_score(y_initial, y_provisional)
    completeness = completeness_score(y_initial, y_provisional)
    v_measure = v_measure_score(y_initial, y_provisional)
    adj_rand = adjusted_rand_score(y_initial, y_provisional)
    
    return {
        'homogeneity': round(homogeneity, 3),
        'completeness': round(completeness, 3),
        'v_measure': round(v_measure, 3),
        'adjusted_rand_index': round(adj_rand, 3),
    }


def interpret_metrics(metrics: Dict[str, float]) -> str:
    """Interpret clustering metrics and recommend action."""
    
    v_measure = metrics['v_measure']
    
    if v_measure >= 0.85:
        interpretation = "EXCELLENT - Provisional groups match initial groups very well"
        recommendation = "✅ Use provisional groups directly"
    elif v_measure >= 0.70:
        interpretation = "GOOD - Reasonable agreement with some differences"
        recommendation = "⚠️  Consider Phase 5 refinement for edge cases"
    elif v_measure >= 0.50:
        interpretation = "MODERATE - Significant differences exist"
        recommendation = "🔧 Phase 5 refinement recommended"
    else:
        interpretation = "POOR - Major differences in clustering approach"
        recommendation = "❌ May need to adjust n_clusters or features"
    
    return f"{interpretation}\n  → {recommendation}"


# ═══════════════════════════════════════════════════════════════════════
# DISCREPANCY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════


def identify_discrepancies(
    species_df: pd.DataFrame,
    max_examples: int = 20
) -> List[Dict]:
    """
    Identify species where provisional and initial groups differ.
    """
    
    print("[Phase 4] Identifying discrepancies...")
    
    mismatches = species_df[
        species_df['provisional_group_id'].astype(str) != species_df['initial_group_id'].astype(str)
    ]
    
    discrepancies = []
    
    for idx, row in mismatches.head(max_examples).iterrows():
        discrepancies.append({
            'species_name': row['species_name'],
            'provisional_group': f"PROV_{row['provisional_group_id']:02d}",
            'initial_group': row['initial_group_id'],
            'habitat': row['habitat'],
            'trophic_level': row['trophic_level'],
            'size_class': row['size_class'],
            'reason': 'Characteristic-based vs expert assignment differ'
        })
    
    return discrepancies


# ═══════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════


def generate_comparison_report(
    species_df: pd.DataFrame,
    metrics: Dict[str, float],
    discrepancies: List[Dict],
    output_path: Path = None
) -> Path:
    """
    Generate comprehensive comparison report.
    """
    
    output_path = output_path or OUTPUT_DIR / "phase4_comparison_report.txt"
    
    with open(output_path, "w", encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("PHASE 4: COMPARISON WITH INITIAL GROUPS\n")
        f.write("=" * 70 + "\n\n")
        
        # Summary
        f.write("SUMMARY\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total species analyzed: {len(species_df)}\n")
        f.write(f"Provisional groups: {species_df['provisional_group_id'].nunique()}\n")
        f.write(f"Initial groups: {species_df['initial_group_id'].nunique()}\n")
        f.write(f"Matches: {len(species_df[species_df['provisional_group_id'].astype(str) == species_df['initial_group_id'].astype(str)])}\n")
        f.write(f"Discrepancies: {len(species_df[species_df['provisional_group_id'].astype(str) != species_df['initial_group_id'].astype(str)])}\n\n")
        
        # Metrics
        f.write("CLUSTERING AGREEMENT METRICS\n")
        f.write("-" * 70 + "\n")
        f.write(f"Homogeneity:         {metrics['homogeneity']:.3f}  (0=bad, 1=perfect)\n")
        f.write(f"Completeness:        {metrics['completeness']:.3f}  (0=bad, 1=perfect)\n")
        f.write(f"V-Measure:           {metrics['v_measure']:.3f}  (0=bad, 1=perfect)\n")
        f.write(f"Adjusted Rand Index: {metrics['adjusted_rand_index']:.3f}  (-1=bad, 1=perfect)\n\n")
        
        # Interpretation
        f.write("INTERPRETATION & RECOMMENDATION\n")
        f.write("-" * 70 + "\n")
        f.write(interpret_metrics(metrics) + "\n\n")
        
        # Discrepancies
        if discrepancies:
            f.write("EXAMPLE DISCREPANCIES (first 20)\n")
            f.write("-" * 70 + "\n")
            for i, disc in enumerate(discrepancies, 1):
                f.write(f"\n{i}. {disc['species_name']}\n")
                f.write(f"   Provisional: {disc['provisional_group']}\n")
                f.write(f"   Expected:    {disc['initial_group']}\n")
                f.write(f"   Characteristics: {disc['habitat']}, {disc['trophic_level']}, {disc['size_class']}\n")
        
        f.write("\n" + "=" * 70 + "\n")
    
    print(f"✅ Report saved: {output_path.name}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def run_phase4_comparison(
    species_csv: Path = None,
    initial_groups_csv: Path = None
) -> Dict:
    """
    Execute Phase 4: Compare with initial groups.
    
    Returns:
        Dictionary with metrics and recommendations
    """
    
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  PHASE 4: COMPARISON WITH INITIAL GROUPS                 ║")
    print("║  Assess agreement using clustering metrics                ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Load data
    species_csv = species_csv or OUTPUT_DIR / "species_list_clustered.csv"
    species_df = pd.read_csv(species_csv)
    print(f"Loaded {len(species_df)} species from {species_csv.name}")
    
    initial_groups_csv = initial_groups_csv or DATA_DIR / "initial_groups.csv"
    initial_groups_df = load_initial_groups(initial_groups_csv)
    
    # Map to initial groups
    species_df, unmatched = map_species_to_groups(species_df, initial_groups_df)
    
    # Calculate metrics
    metrics = calculate_clustering_metrics(species_df)
    
    # Identify discrepancies
    discrepancies = identify_discrepancies(species_df)
    
    # Generate report
    generate_comparison_report(species_df, metrics, discrepancies)
    
    # Summary
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  METRICS SUMMARY                                         ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f" ║  V-Measure (overall):     {metrics['v_measure']:.3f}                            ║")
    print(f" ║  Homogeneity:             {metrics['homogeneity']:.3f}                            ║")
    print(f" ║  Completeness:            {metrics['completeness']:.3f}                            ║")
    print("╠════════════════════════════════════════════════════════════╣")
    
    if metrics['v_measure'] < 0.70:
        print(" ║  ⚠️  LOW AGREEMENT - Phase 5 refinement recommended      ║")
    elif metrics['v_measure'] < 0.85:
        print(" ║  ✓ GOOD AGREEMENT - Check edge cases in Phase 5          ║")
    else:
        print(" ║  ✅ EXCELLENT AGREEMENT - Use provisional groups         ║")
    print(" ╚════════════════════════════════════════════════════════════╝")
    
    return {
        'metrics': metrics,
        'discrepancies': discrepancies,
        'need_phase5': metrics['v_measure'] < 0.85,
        'species_with_assignments': species_df
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 4: Comparison with Initial Groups")
    parser.add_argument("--species", type=str, help="Path to clustered species CSV")
    parser.add_argument("--initial-groups", type=str, help="Path to initial groups CSV")
    
    args = parser.parse_args()
    
    species_path = Path(args.species) if args.species else None
    initial_path = Path(args.initial_groups) if args.initial_groups else None
    
    run_phase4_comparison(species_csv=species_path, initial_groups_csv=initial_path)
