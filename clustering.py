"""
clustering.py - Phase 3: Automated Species Clustering
======================================================

Cluster species based on functional characteristics using:
- Hierarchical clustering (Ward linkage)
- Categorical distance metrics
- Automatic group generation (no LLM required)

Output: provisional functional groups without any LLM overhead.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import json

from scipy.cluster.hierarchy import dendrogram, linkage, fcluster
from scipy.spatial.distance import pdist, squareform
from sklearn.preprocessing import LabelEncoder

from config import OUTPUT_DIR


# ═══════════════════════════════════════════════════════════════════════
# CATEGORICAL DISTANCE METRIC
# ═══════════════════════════════════════════════════════════════════════


def categorical_distance(x, y):
    """
    Calculate Hamming distance for categorical features.
    Used for habitat, trophic_level, size_class (all categorical).
    """
    return np.sum(x != y) / len(x)


# ═══════════════════════════════════════════════════════════════════════
# CLUSTERING
# ═══════════════════════════════════════════════════════════════════════


def cluster_species(
    species_df: pd.DataFrame,
    n_clusters: int = 20,
    features: List[str] = None,
) -> pd.DataFrame:
    """
    Cluster species based on functional characteristics.

    Parameters
    ----------
    species_df : pd.DataFrame
        DataFrame with species and characteristics columns
    n_clusters : int
        Target number of clusters/groups
    features : List[str]
        Features to use for clustering
        (default: ['habitat', 'trophic_level', 'size_class'])

    Returns
    -------
    pd.DataFrame
        Updated species_df with 'provisional_group_id' column
    """
    
    if features is None:
        features = ['habitat', 'trophic_level', 'size_class']
    
    print(f"[Phase 3] Clustering {len(species_df)} species into ~{n_clusters} groups...")
    print(f"         Using features: {features}")
    
    # Validate that features exist and have data
    for feature in features:
        if feature not in species_df.columns:
            raise ValueError(f"Feature '{feature}' not found in species_df")
        
        na_count = species_df[feature].isna().sum()
        if na_count > 0:
            print(f"  ⚠️  Warning: {na_count} missing values in '{feature}' (will use 'unknown')")
            species_df[feature] = species_df[feature].fillna('unknown')
    
    # Extract feature matrix
    X = species_df[features].values
    
    # Encode categorical features
    encoders = {}
    X_encoded = np.zeros_like(X, dtype=int)
    
    for col_idx, feature in enumerate(features):
        encoder = LabelEncoder()
        X_encoded[:, col_idx] = encoder.fit_transform(X[:, col_idx])
        encoders[feature] = encoder
    
    # Calculate pairwise distances (Hamming for categorical)
    print("  Calculating pairwise distances...")
    distances = pdist(X_encoded, metric='hamming')
    distance_matrix = squareform(distances)
    
    # Hierarchical clustering (Ward)
    print("  Performing hierarchical clustering...")
    linkage_matrix = linkage(distances, method='ward', metric='euclidean')
    
    # Cut dendrogram to get clusters
    cluster_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust')
    
    # Assign cluster IDs
    species_df['provisional_group_id'] = cluster_labels
    
    print(f"[Phase 3] Clustering complete. Created {len(species_df['provisional_group_id'].unique())} groups")
    
    return species_df


def generate_provisional_groups(species_df: pd.DataFrame) -> List[Dict]:
    """
    Create provisional group definitions from clustered species.

    Parameters
    ----------
    species_df : pd.DataFrame
        Clustered species DataFrame with 'provisional_group_id' column

    Returns
    -------
    List[Dict]
        Provisional group dictionaries
    """
    
    print("[Phase 3] Generating provisional group definitions...")
    
    provisional_groups = []
    
    for group_id in sorted(species_df['provisional_group_id'].unique()):
        group_species = species_df[species_df['provisional_group_id'] == group_id]
        species_list = group_species['species_name'].tolist()
        
        # Get dominant characteristics
        habitat_dominant = group_species['habitat'].mode()
        habitat = habitat_dominant.values[0] if len(habitat_dominant) > 0 else "unknown"
        
        trophic_dominant = group_species['trophic_level'].mode()
        trophic = trophic_dominant.values[0] if len(trophic_dominant) > 0 else "unknown"
        
        size_dominant = group_species['size_class'].mode()
        size = size_dominant.values[0] if len(size_dominant) > 0 else "unknown"
        
        tax_dominant = group_species['taxonomic_affinity'].mode()
        taxonomy = tax_dominant.values[0] if len(tax_dominant) > 0 else "unknown"
        
        # Create group
        group = {
            "group_id": f"PROV_{group_id:02d}",
            "group_name": f"Functional Group {group_id}: {habitat} {trophic}",
            "description": f"Species cluster with {habitat} habitat, {trophic} trophic role, {size} size",
            "characteristics": {
                "habitat": habitat,
                "trophic_level": trophic,
                "size_class": size,
                "taxonomic_affinity": taxonomy
            },
            "species": species_list,
            "species_count": len(species_list),
            "dominant_characteristics": {
                "habitat": habitat,
                "trophic_level": trophic,
                "size_class": size
            }
        }
        
        provisional_groups.append(group)
    
    print(f"[Phase 3] Generated {len(provisional_groups)} provisional groups")
    
    return provisional_groups


# ═══════════════════════════════════════════════════════════════════════
# SAVE & EXPORT
# ═══════════════════════════════════════════════════════════════════════


def save_provisional_groups(
    species_df: pd.DataFrame,
    provisional_groups: List[Dict],
    output_dir: Path = None
) -> Tuple[Path, Path]:
    """
    Save clustering results to files.

    Returns
    -------
    Tuple[Path, Path]
        Paths to (species_CSV, groups_JSON)
    """
    
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    
    # Save species with provisional groups
    species_path = output_dir / "species_list_clustered.csv"
    species_df.to_csv(species_path, index=False)
    print(f"✅ Species with clusters: {species_path.name}")
    
    # Save provisional groups
    groups_path = output_dir / "provisional_groups.json"
    with open(groups_path, "w") as f:
        json.dump(provisional_groups, f, indent=2)
    print(f"✅ Provisional groups: {groups_path.name}")
    
    return species_path, groups_path


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def run_clustering(
    species_csv: Path = None,
    n_clusters: int = 20,
    features: List[str] = None,
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Execute Phase 3: Cluster species into functional groups.

    Parameters
    ----------
    species_csv : Path
        Path to characterized species CSV
    n_clusters : int
        Target number of groups
    features : List[str]
        Features to cluster on

    Returns
    -------
    Tuple[pd.DataFrame, List[Dict]]
        (clustered_species_df, provisional_groups)
    """
    
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  PHASE 3: AUTOMATED CLUSTERING                           ║")
    print("║  No LLM required - Pure algorithmic                       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    # Load species
    species_csv = species_csv or OUTPUT_DIR / "species_list_characterized.csv"
    species_df = pd.read_csv(species_csv)
    print(f"Loaded {len(species_df)} species from {species_csv.name}")
    
    # Cluster
    species_df = cluster_species(species_df, n_clusters=n_clusters, features=features)
    
    # Generate group definitions
    provisional_groups = generate_provisional_groups(species_df)
    
    # Save results
    save_provisional_groups(species_df, provisional_groups)
    
    # Summary
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║  CLUSTERING SUMMARY                                      ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f" ║  Total species:         {len(species_df):<35}║")
    print(f" ║  Provisional groups:    {len(provisional_groups):<35}║")
    avg_per_group = len(species_df) / len(provisional_groups) if len(provisional_groups) > 0 else 0
    print(f" ║  Avg species/group:     {avg_per_group:<34.1f}║")
    
    # Show group sizes
    group_sizes = sorted([g['species_count'] for g in provisional_groups], reverse=True)
    print(f" ║  Group size range:      {min(group_sizes)}-{max(group_sizes):<29}║")
    print(" ╚════════════════════════════════════════════════════════════╝")
    
    return {
        'species_df': species_df,
        'provisional_groups': provisional_groups,
        'n_groups': len(provisional_groups),
        'tokens_used': 0
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 3: Species Clustering")
    parser.add_argument("--species", type=str, help="Path to characterized species CSV")
    parser.add_argument("--n-clusters", type=int, default=20, help="Target number of groups")
    
    args = parser.parse_args()
    
    species_path = Path(args.species) if args.species else None
    run_clustering(species_csv=species_path, n_clusters=args.n_clusters)
