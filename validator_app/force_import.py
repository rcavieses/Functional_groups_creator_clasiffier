"""
force_import.py — Importa el CSV clasificado a Firestore directamente desde terminal.
Útil cuando la importación automática de la app no se dispara.

Uso:
    cd Functional_groups_creator_clasiffier
    python validator_app/force_import.py
"""

import sys
from pathlib import Path

# firebase_client.py está en la raíz del proyecto (un nivel arriba de validator_app/)
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from firebase_client import get_db, is_imported, import_classifications

DATA_DIR      = Path(__file__).parent.parent / "data"
OUTPUT_DIR    = Path(__file__).parent.parent / "output"
CLASSIFIED_CSV = OUTPUT_DIR / "species_classified.csv"
GROUPS_CSV     = DATA_DIR  / "functional_groups_final.csv"

if __name__ == "__main__":
    print("Conectando a Firebase...")
    db = get_db()

    if is_imported(db):
        resp = input("Ya hay datos en Firestore. ¿Reimportar de todas formas? [s/N]: ")
        if resp.strip().lower() != "s":
            print("Cancelado.")
            sys.exit(0)

    if not CLASSIFIED_CSV.exists():
        print(f"ERROR: No se encontró {CLASSIFIED_CSV}")
        sys.exit(1)

    print(f"Importando {CLASSIFIED_CSV}...")
    n = import_classifications(CLASSIFIED_CSV, GROUPS_CSV, db)
    print(f"✅ {n:,} taxa importados a Firestore.")
