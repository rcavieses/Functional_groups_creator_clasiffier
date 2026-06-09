"""
main_new_algorithm.py - Complete 5-Phase Bottom-Up Orchestrator
================================================================

Main workflow that orchestrates all 5 phases:

Phase 1: Heuristic species characterization (genus lookup + keyword inference)
Phase 2: LLM validation of characteristics (~500 tokens/batch)
Phase 3: Automated hierarchical clustering (zero LLM tokens)
Phase 4: Comparison with expert groups (clustering metrics)
Phase 5: Selective LLM refinement for edge cases (~200 tokens per case)

Total estimated cost reduction: 77% vs original top-down batch approach.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from config import OUTPUT_DIR, DATA_DIR

# Import phase modules
from species_characteristics import process_species_characteristics
from clustering import run_clustering
from phase_comparison import run_phase4_comparison
from phase_refinement import run_phase5_refinement


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════


def print_phase_header(phase_num: int, phase_name: str):
    """Print formatted phase header."""
    
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print(f"║  PHASE {phase_num}: {phase_name:<50}║")
    print("╚" + "═" * 68 + "╝")


def print_workflow_header():
    """Print workflow header."""
    
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║  " + "BOTTOM-UP FUNCTIONAL GROUPS CLASSIFICATION".center(64) + "  ║")
    print("║  " + "5-Phase Algorithm Orchestrator".center(64) + "  ║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def print_workflow_footer(results: Dict):
    """Print workflow completion summary."""
    
    total_tokens = 0
    for phase_result in [
        results.get('phase1_2', {}),
        results.get('phase3', {}),
        results.get('phase4', {}),
        results.get('phase5', {})
    ]:
        if isinstance(phase_result, dict):
            total_tokens += phase_result.get('tokens_used', 0)
    
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║  WORKFLOW COMPLETE".ljust(69) + "║")
    print("╠" + "═" * 68 + "╣")
    print(f"║  Total tokens used: {total_tokens:,}".ljust(69) + "║")
    print(f"║  Species processed: {results.get('total_species', 'N/A')}".ljust(69) + "║")
    print(f"║  Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(69) + "║")
    print("╚" + "═" * 68 + "╝")


# ═══════════════════════════════════════════════════════════════════════
# VALIDATION & ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════════


def validate_input_files() -> bool:
    """Validate that required input files exist."""
    
    print("Validating input files...")
    
    required_files = [
        DATA_DIR / "species_list.csv",
        DATA_DIR / "initial_groups.csv",
        DATA_DIR / "taxonomy_db.json",
    ]
    
    missing = []
    for file in required_files:
        if not file.exists():
            missing.append(file.name)
    
    if missing:
        print(f"❌ Missing input files: {', '.join(missing)}")
        return False
    
    print("✅ All input files present")
    return True


def validate_phase_output(phase_num: int, output_files: list) -> bool:
    """Validate that phase output was created."""
    
    for file_path in output_files:
        if not isinstance(file_path, Path):
            file_path = Path(file_path) if file_path else None
        
        if file_path and not file_path.exists():
            print(f"❌ Phase {phase_num} output missing: {file_path.name}")
            return False
    
    return True


# ═══════════════════════════════════════════════════════════════════════
# MAIN WORKFLOW
# ═══════════════════════════════════════════════════════════════════════


def run_complete_workflow(
    species_csv: Optional[Path] = None,
    skip_phase5: bool = False,
    use_llm_phase2: bool = True,
    n_clusters: int = 20
) -> Dict:
    """
    Execute complete 5-phase bottom-up workflow.
    
    Args:
        species_csv: Path to input species list (default: species_list.csv)
        skip_phase5: Skip Phase 5 refinement even if agreement is low
        use_llm_phase2: Use LLM in Phase 2 (set False to skip validation)
        n_clusters: Target number of clusters (default: 20, same as initial groups)
    
    Returns:
        Dictionary with results from all phases
    """
    
    print_workflow_header()
    
    # Validate inputs
    if not validate_input_files():
        print("\n❌ Workflow failed: missing input files")
        return {'success': False}
    
    results = {}
    
    try:
        # ─────────────────────────────────────────────────────────────
        # PHASE 1 & 2: HEURISTIC INFERENCE + LLM VALIDATION
        # ─────────────────────────────────────────────────────────────
        
        print_phase_header(1, "Heuristic Species Characterization")
        print_phase_header(2, "LLM Validation (Compact Prompts)")
        
        phase12_result = process_species_characteristics(
            species_csv=species_csv,
            use_llm=use_llm_phase2,
            confidence_threshold=0.60
        )
        
        results['phase1_2'] = phase12_result
        characterized_csv = OUTPUT_DIR / "species_list_characterized.csv"
        
        if not validate_phase_output(2, [characterized_csv]):
            print("❌ Phase 1-2 output validation failed")
            return {'success': False}
        
        # ─────────────────────────────────────────────────────────────
        # PHASE 3: AUTOMATED CLUSTERING
        # ─────────────────────────────────────────────────────────────
        
        print_phase_header(3, "Automated Hierarchical Clustering")
        
        phase3_result = run_clustering(
            species_csv=characterized_csv,
            n_clusters=n_clusters,
            features=['habitat', 'trophic_level', 'size_class', 'taxonomic_affinity']
        )
        
        results['phase3'] = phase3_result
        clustered_csv = OUTPUT_DIR / "species_list_clustered.csv"
        
        if not validate_phase_output(3, [clustered_csv]):
            print("❌ Phase 3 output validation failed")
            return {'success': False}
        
        # ─────────────────────────────────────────────────────────────
        # PHASE 4: COMPARISON WITH EXPERT GROUPS
        # ─────────────────────────────────────────────────────────────
        
        print_phase_header(4, "Comparison with Initial Groups")
        
        phase4_result = run_phase4_comparison(
            species_csv=clustered_csv,
            initial_groups_csv=DATA_DIR / "initial_groups.csv"
        )
        
        results['phase4'] = phase4_result
        comparison_report = OUTPUT_DIR / "phase4_comparison_report.txt"
        
        if not validate_phase_output(4, [comparison_report]):
            print("❌ Phase 4 output validation failed")
            return {'success': False}
        
        # ─────────────────────────────────────────────────────────────
        # PHASE 5: SELECTIVE LLM REFINEMENT (CONDITIONAL)
        # ─────────────────────────────────────────────────────────────
        
        v_measure = phase4_result.get('metrics', {}).get('v_measure', 0)
        need_refinement = v_measure < 0.85 and not skip_phase5
        
        if need_refinement:
            print_phase_header(5, "Selective LLM Refinement (Edge Cases)")
            
            phase5_result = run_phase5_refinement(
                species_csv=clustered_csv,
                comparison_results=phase4_result,
                skip_if_high_agreement=True
            )
            
            results['phase5'] = phase5_result
            refinement_report = OUTPUT_DIR / "phase5_refinement_report.txt"
            
            if not validate_phase_output(5, [refinement_report]):
                print("⚠️  Phase 5 completed with warnings (optional phase)")
        
        else:
            print_phase_header(5, "Selective LLM Refinement (Skipped)")
            print(f"✅ Skipped: V-Measure = {v_measure:.3f} (>= 0.85 threshold)")
            results['phase5'] = {'skipped': True, 'reason': 'high_agreement'}
        
        # ─────────────────────────────────────────────────────────────
        # FINAL RESULTS
        # ─────────────────────────────────────────────────────────────
        
        # Load final species dataframe
        final_csv = OUTPUT_DIR / "species_list_refined.csv"
        if not final_csv.exists():
            final_csv = OUTPUT_DIR / "species_list_clustered.csv"
        
        final_df = pd.read_csv(final_csv)
        results['total_species'] = len(final_df)
        results['final_species_csv'] = final_csv
        results['success'] = True
        
        # Summary statistics
        print("\n")
        print("╔" + "═" * 68 + "╗")
        print("║  FINAL SUMMARY".ljust(69) + "║")
        print("╠" + "═" * 68 + "╣")
        print(f"║  Total species classified: {len(final_df)}".ljust(69) + "║")
        print(f"║  Functional groups: {final_df['provisional_group_id'].nunique()}".ljust(69) + "║")
        print(f"║  V-Measure (Phase 4): {v_measure:.3f}".ljust(69) + "║")
        print(f"║  Final output: {final_csv.name}".ljust(69) + "║")
        print("╚" + "═" * 68 + "╝")
        
        print_workflow_footer(results)
        
        return results
    
    except Exception as e:
        print(f"\n❌ Workflow failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════


def main():
    """Command-line interface."""
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description="5-Phase Bottom-Up Functional Groups Classification",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--species",
        type=str,
        help="Path to input species CSV (default: species_list.csv)"
    )
    
    parser.add_argument(
        "--skip-phase5",
        action="store_true",
        help="Skip Phase 5 refinement even if agreement is low"
    )
    
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM validation in Phase 2 (use heuristic only)"
    )
    
    parser.add_argument(
        "--clusters",
        type=int,
        default=20,
        help="Target number of clusters (default: 20)"
    )
    
    args = parser.parse_args()
    
    species_path = Path(args.species) if args.species else None
    
    results = run_complete_workflow(
        species_csv=species_path,
        skip_phase5=args.skip_phase5,
        use_llm_phase2=not args.no_llm,
        n_clusters=args.clusters
    )
    
    sys.exit(0 if results.get('success', False) else 1)


if __name__ == "__main__":
    main()
