# Nuevo Algoritmo: Bottom-Up Functional Group Creation

**Enfoque:** Características de especie → Clustering → Grupos funcionales  
**Objetivo:** Más eficiente, menos tokens, más realista

---

## 📊 Cambios en la Estructura de Datos

### Antes (JSON con descripciones largas)
```json
{
  "group_id": "FG01",
  "group_name": "Small Pelagic Fish...",
  "description": "Small schooling pelagic fish...",
  "characteristics": { "habitat": "pelagic", ... }
}
```
**Problema:** Descripciones redundantes, muchos tokens por grupo

### Ahora (CSV tabular con atributos estructurados)

**initial_groups.csv:**
```
group_id | group_name | description | habitat | trophic_level | size_class
FG01     | Small Pelagic Fish | ... | pelagic | planktivore | small
FG02     | Large Pelagic Predators | ... | pelagic | carnivore | large
```

**species_list_extended.csv:**
```
species_name | group_id | group_name | habitat | trophic_level | size_class | taxonomic_affinity
bacillaria paxillifera | FG01 | ... | pelagic | producer | very_small | Bacillariophyceae
acanthurus nigricans | FG03 | ... | pelagic | herbivore | medium | Acanthuridae
```

**Ventaja:** Estructura clara, fácil de procesar, sin redundancia.

---

## 🔄 Flujo del Nuevo Algoritmo

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PHASE 1: SPECIES CHARACTERIZATION (Bottom-Up)           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Input: species_list_extended.csv (empty characteristics)   │
│                                                               │
│  For each species:                                           │
│    - Extract taxonomic clues from scientific name           │
│    - Infer habitat (marine/terrestrial/freshwater)          │
│    - Infer trophic level (from taxonomy/morphology)         │
│    - Infer size class (from known species data)             │
│    - Infer taxonomic_affinity (family/order)                │
│                                                               │
│  Output: species_list_extended.csv (filled characteristics) │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. PHASE 2: CHARACTERISTIC VALIDATION (LLM Light-Touch)    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Input: species_list_extended.csv (auto-filled)             │
│                                                               │
│  For batches of ~50 species:                                │
│    - Present species name + auto-inferred characteristics   │
│    - Ask LLM: "Are these characteristics correct? Suggest" │
│    - LLM validates/corrects (minimal token usage)           │
│                                                               │
│  Output: species_list_extended.csv (LLM-validated)          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. PHASE 3: CLUSTERING (Automated - No LLM)                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Algorithm: Hierarchical clustering + K-means               │
│  Features: habitat + trophic_level + size_class             │
│  Distance metric: Jaccard/Hamming (categorical data)        │
│                                                               │
│  Create provisional groups based on characteristics         │
│                                                               │
│  Output: provisional_groups.csv (auto-clustered)            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. PHASE 4: COMPARISON WITH INITIAL_GROUPS                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Compare:                                                    │
│    - provisional_groups vs initial_groups                  │
│    - Metrics: homogeneity, completeness, V-measure         │
│    - Identify inconsistencies                               │
│                                                               │
│  Output: comparison_report.txt                              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. PHASE 5: REFINEMENT (LLM-Assisted - Heavy-Lifting)      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Where provisional_groups differ from initial_groups:       │
│    - Ask LLM ecological justification (only edge cases)     │
│    - Merge/split groups if needed                            │
│    - Validate functional coherence                           │
│                                                               │
│  Output: optimized_groups.json                              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 PHASE 1: Species Characterization (Heuristic)

### Objective:
Auto-fill characteristics for each species using knowledge bases + parsing.

### Approach:

#### 1a. Taxonomic Parsing
```python
def infer_characteristics_from_taxonomy(species_name: str, taxonomic_affinity: str = None) -> dict:
    """
    Infer characteristics from scientific name and known taxonomy.
    
    Examples:
    - "bacillaria paxillifera" → diatom → pelagic, producer, very_small
    - "acanthurus nigricans" → surgeonfish → herbivore, reef, medium
    - "balaenoptera musculus" → whale → large, pelagic, carnivore
    """
    
    # Known patterns/keywords in scientific names indicating traits
    pelagic_keywords = ["bacillaria", "ceratium", "chaetoceros", "copepoda", "fish"]
    demersal_keywords = ["amphora", "bivalvia", "holothurian", "echinoid", "crab"]
    producer_keywords = ["bacillaria", "diatom", "algae", "phytoplankton"]
    filter_key_words = ["bivalvia", "copepod", "pteropod", "siphonophore"]
    carnivore_keywords = ["acanthurus", "haemulid", "serranid", "shark", "dolphin"]
    
    # Extract genus from species name
    genus = species_name.split()[0].lower()
    
    # Infer from known databases (pre-populated)
    if genus in TAXONOMY_DB:
        return TAXONOMY_DB[genus]
    
    # Infer from keyword matching
    characteristics = {}
    for keyword in pelagic_keywords:
        if keyword in species_name:
            characteristics["habitat"] = "pelagic"
            break
    
    # [Similar logic for other characteristics]
    
    return characteristics
```

#### 1b. Knowledge Base Lookup
Create a `TAXONOMY_DB` dictionary of known species:

```python
TAXONOMY_DB = {
    "bacillaria": {
        "habitat": "pelagic",
        "trophic_level": "producer",
        "size_class": "very_small",
        "taxonomic_affinity": "Bacillariophyceae"
    },
    "acanthurus": {
        "habitat": "pelagic",
        "trophic_level": "herbivore",
        "size_class": "medium",
        "taxonomic_affinity": "Acanthuridae"
    },
    # ... [hundreds of entries]
}
```

**Source:** Compile from initial_groups.json, literature, OBIS/GBIF databases.

### Output:
`species_list_extended.csv` with auto-filled characteristics (confidence: ~40-60% accuracy)

---

## 🤖 PHASE 2: LLM Validation (Single-Pass, Minimal Tokens)

### Approach:

**Batch size:** 50 species  
**Prompt type:** Validation only, no generation

#### Prompt Structure (Super Compact):
```
SPECIES CHARACTERISTICS - VALIDATION REQUEST

Species | Inferred Habitat | Inferred Trophic | Inferred Size | Correct?
bacillaria paxillifera | pelagic | producer | very_small | ?
acanthurus nigricans | pelagic | herbivore | medium | ?
...

INSTRUCTION:
Check each Species characteristics. If incorrect, suggest correction.
ONLY list species with ERRORS.

Response format:
```json
{
  "corrections": [
    {"species": "acanthurus nigricans", "habitat": "reef", "reason": "..."},
    {"species": "...", "trophic_level": "...", "reason": "..."}
  ],
  "validated_count": 48,
  "error_count": 2
}
```

**Token Estimate:**
- 50 species × 30 chars = 1,500 chars
- JSON response + corrections = ~500 chars
- **Total: ~500 tokens per batch** (vs. 2,500 in current approach)

### Output:
Updated `species_list_extended.csv` with LLM-corrected characteristics

---

## 🔂 PHASE 3: Clustering (Automated, Zero Tokens)

### Algorithm:

```python
from scipy.cluster.hierarchy import dendrogram, linkage, fcluster
from sklearn.preprocessing import LabelEncoder

def cluster_species_by_characteristics(species_df: pd.DataFrame, n_clusters: int = 20) -> pd.DataFrame:
    """
    Cluster species based on habitat, trophic_level, size_class similarity.
    """
    
    # Encode categorical features
    encoder_habitat = LabelEncoder()
    encoder_trophic = LabelEncoder()
    encoder_size = LabelEncoder()
    
    X = np.column_stack([
        encoder_habitat.fit_transform(species_df['habitat']),
        encoder_trophic.fit_transform(species_df['trophic_level']),
        encoder_size.fit_transform(species_df['size_class'])
    ])
    
    # Hierarchical clustering (Ward linkage)
    linkage_matrix = linkage(X, method='ward', metric='euclidean')
    
    # Cut dendrogram to get clusters
    cluster_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust')
    
    # Assign cluster IDs to species
    species_df['provisional_group_id'] = cluster_labels
    
    return species_df
```

**Output:** `provisional_groups.json` with auto-created group IDs

**Token Cost:** 0 (no LLM calls)

---

## ⚖️ PHASE 4: Comparison with Initial Groups

### Metrics to Compare:

```python
from sklearn.metrics import homogeneity_score, completeness_score, v_measure_score

def compare_with_initial_groups(provisional_groups: list[dict], initial_groups: list[dict]) -> dict:
    """
    Compare clustering results against expert-defined initial groups.
    """
    
    # Create label arrays
    y_provisional = [species.get("provisional_group_id") for species in species_list]
    y_initial = [species.get("group_id") for species in species_list]
    
    # Metrics
    homogeneity = homogeneity_score(y_initial, y_provisional)
    completeness = completeness_score(y_initial, y_provisional)
    v_measure = v_measure_score(y_initial, y_provisional)
    
    # Generate report
    return {
        "homogeneity": homogeneity,  # 0 = different, 1 = same clustering
        "completeness": completeness,
        "v_measure": v_measure,
        "interpretation": "..."
    }
```

**Interpretation:**
- **V-measure > 0.8:** Excellent agreement (use provisional_groups)
- **V-measure 0.6-0.8:** Good agreement (minor adjustments needed)
- **V-measure < 0.6:** Significant differences (need Phase 5 refinement)

---

## 🎯 PHASE 5: Refinement (Selective LLM)

### When to use LLM:

Only when:
1. Species assigned different groups (provisional vs initial)
2. Group coherence metrics < threshold
3. Edge cases / ambiguous characteristics

### Prompt (Focused, Economic):

```
FUNCTIONAL GROUP REFINEMENT

Provisional Grouping:
- Group A: acanthurus nigricans, acanthurus triostegus, acanthurus xanthopterus
  Characteristics: [pelagic, herbivore, medium]

Initial Groups expectation:
- Should be in: FG03 (Demersal Reef Predators) [demersal, carnivore, medium-large]

QUESTION: Are these species better suited for:
A) Group A (by similarity to each other)
B) FG03 (by initial expert classification)
C) A new group (explain why)

Keep response SHORT: max 2 sentences + JSON decision.
```

**Token Cost:** Only for mismatches (~5-10% of species)

---

## 📊 Example Workflow

### Input Data:
- 850 species (from species_list.csv)
- 8 reference groups (from initial_groups.csv)

### Phase 1 Output:
```
species_name | habitat | trophic_level | size_class | taxonomic_affinity | confidence
bacillaria paxillifera | pelagic | producer | very_small | Bacillariophyceae | 0.95
acanthurus nigricans | pelagic | herbivore | medium | Acanthuridae | 0.85
```

### Phase 2 Processing:
- 850 species ÷ 50 per batch = 17 batches
- Validation requests: ~200 corrections
- **Total tokens used: ~8,500 tokens** (vs. ~42,500 in old system)

### Phase 3 Output:
```
provisional_group_1: [species_1, species_2, ..., species_45]  (pelagic, carnivore, large)
provisional_group_2: [species_46, species_47, ..., species_92] (benthic, filter_feeder, mediim)
...
```

### Phase 4 Metrics:
```
V-measure: 0.82 → Good agreement with initial_groups
Homogeneity: 0.79
Completeness: 0.85
```

### Phase 5 Action:
Only refine 8-12 species (1.4%) that are borderline

---

## 💾 Token Efficiency Comparison

| Process | Old System | New System | Reduction |
|---|---|---|---|
| Species Characterization | 0 | 0 | - |
| LLM Classification | 25,000 | 8,500 | **66% ↓** |
| Group Creation | 12,000 | 0 | **100% ↓** |
| LLM Refinement | 8,000 | 2,000 | **75% ↓** |
| **TOTAL** | **45,000** | **10,500** | **77% ↓** |

---

## 🔧 Implementation Plan

### Files to Create:
1. `species_characteristics.py` - Taxonomic inference + LLM validation
2. `clustering.py` - Automated clustering algorithm
3. `phase_comparison.py` - Comparison with initial groups
4. `phase_refinement.py` - Selective LLM refinement
5. `NEW_ALGORITHM.py` - Main orchestrator

### Data Files:
1. ✅ `initial_groups.csv` - Created
2. ✅ `species_list_extended.csv` - Created
3. `taxonomy_db.json` - Knowledge base (to populate)
4. `provisional_groups.json` - Clustering output
5. `comparison_report.txt` - Validation results
6. `optimized_groups.json` - Final refined groups

### Configuration:
```python
# In config.py
PHASE_1_CONFIDENCE_MIN = 0.60  # Auto-fill if > 60% confident
PHASE_2_BATCH_SIZE = 50        # Validation batch size
PHASE_3_N_CLUSTERS = 20-25     # Target number of groups
PHASE_4_VMEASURE_THRESHOLD = 0.70  # When to trigger Phase 5
PHASE_5_LLM_ENABLED = True     # Enable selective refinement
```

---

## ✅ Advantages of This Approach

1. **Token Efficiency:** 77% reduction
2. **Transparency:** Each decision documented (heuristic/LLM/clustering)
3. **Realistic:** Bottom-up from species → characteristic-driven grouping
4. **Validation:** Uses initial_groups as reference (not replacement)
5. **Scalability:** Can handle thousands of species
6. **Debuggability:** Easy to inspect why species grouped together

---

## ⚠️ Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Heuristic inferences wrong | Phase 2 LLM validation catches errors |
| Clustering oversimplified | Phase 5 allows manual refinement |
| Loses expert knowledge | Comparison with initial_groups preserves it |
| Can't cluster if few characteristics | Add more descriptors (feeding_mechanism, depth_range, etc.) |

---

## 🚀 Ready for Implementation?

This approach is:
- ✅ Efficient (low token usage)
- ✅ Realistic (data-driven)
- ✅ Replicable (algorithmic)
- ✅ Auditable (transparent decisions)

Next step: Implement Phase 1 & 2, test on sample species.
