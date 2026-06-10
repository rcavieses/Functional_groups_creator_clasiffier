"""
update_firestore.py — Limpiar e importar nuevas clasificaciones a Firestore

Uso:
    python update_firestore.py

Este script:
1. Elimina todos los registros existentes de especies
2. Re-importa las clasificaciones del CSV actualizado
3. Preserva el audit log
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from firebase_client import (
    get_db,
    import_classifications,
    SPECIES_COL,
)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
CLASSIFIED_CSV = OUTPUT_DIR / "species_classified.csv"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"


def clear_species_collection(db):
    """Delete all documents in the species collection."""
    print("[1/3] Eliminando registros existentes de Firestore…")
    docs = db.collection(SPECIES_COL).stream()
    deleted = 0

    batch = db.batch()
    for doc in docs:
        batch.delete(doc.reference)
        deleted += 1
        if deleted % 100 == 0:
            print(f"  Eliminados: {deleted}")
            batch.commit()
            batch = db.batch()

    if deleted % 100 != 0:
        batch.commit()

    print(f"✅ {deleted} registros eliminados")
    return deleted


def main():
    if not CLASSIFIED_CSV.exists():
        print(f"❌ Archivo no encontrado: {CLASSIFIED_CSV}")
        print(f"   Primero ejecuta: python classifier/classify_species.py --input data/final_taxonomy_occ.csv --provider anthropic --no-reasoning")
        sys.exit(1)

    if not GROUPS_CSV.exists():
        print(f"❌ Archivo no encontrado: {GROUPS_CSV}")
        sys.exit(1)

    db = get_db()

    try:
        clear_species_collection(db)

        print("\n[2/3] Importando nuevas clasificaciones a Firestore…")
        n = import_classifications(CLASSIFIED_CSV, GROUPS_CSV, db)
        print(f"✅ {n:,} especies importadas exitosamente")

        print("\n[3/3] Actualizacion completada")
        print(f"""
╭─────────────────────────────────────────────────────────╮
│  ✅ Firestore actualizado correctamente                 │
├─────────────────────────────────────────────────────────┤
│  Registros importados: {n:,}
│  CSV fuente: {CLASSIFIED_CSV}
│  Estado: Todos los registros en "pending"               │
│  Próximo paso: Abre la app con `streamlit run app.py`  │
╰─────────────────────────────────────────────────────────╯
""")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
