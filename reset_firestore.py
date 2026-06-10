#!/usr/bin/env python3
"""
reset_firestore.py — Borrar datos viejos e importar nuevos (sin dependencias Streamlit)

Uso:
    python3 reset_firestore.py
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# Cargar variables de entorno
load_dotenv(Path(__file__).parent / ".env")

PROJECT_ROOT = Path(__file__).parent
CREDS_FILE = PROJECT_ROOT / "firebase-credentials.json"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

CLASSIFIED_CSV = OUTPUT_DIR / "species_classified.csv"
GROUPS_CSV = DATA_DIR / "functional_groups_final.csv"
SPECIES_COL = "species"
AUDIT_COL = "audit_log"


def get_db():
    """Inicializar Firebase (versión sin Streamlit)."""
    if firebase_admin._apps:
        return firestore.client()

    cred = None

    # 1. Intentar archivo local
    if CREDS_FILE.exists():
        cred = credentials.Certificate(str(CREDS_FILE))
        print(f"  Usando credenciales de: {CREDS_FILE}")

    # 2. Intentar variable de entorno
    if cred is None:
        env_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
        if env_json:
            try:
                cred = credentials.Certificate(json.loads(env_json))
                print("  Usando credenciales de variable FIREBASE_SERVICE_ACCOUNT")
            except Exception as e:
                print(f"  Error cargando desde env: {e}")

    if cred is None:
        raise FileNotFoundError(
            f"Credenciales no encontradas.\n"
            f"Opciones:\n"
            f"  1. {CREDS_FILE}\n"
            f"  2. Variable FIREBASE_SERVICE_ACCOUNT"
        )

    firebase_admin.initialize_app(cred)
    return firestore.client()


def _doc_id(taxon: str) -> str:
    return taxon.replace("/", "_").replace(".", "_").replace(" ", "_")[:500]


def clear_species_collection(db):
    """Borrar todos los registros de la colección species."""
    print("[1/3] Borrando registros viejos de Firestore…")

    docs = db.collection(SPECIES_COL).stream()
    deleted = 0
    batch = db.batch()

    for doc in docs:
        batch.delete(doc.reference)
        deleted += 1
        if deleted % 100 == 0:
            print(f"  Borrados: {deleted}")
            batch.commit()
            batch = db.batch()

    if deleted % 100 != 0:
        batch.commit()

    print(f"✅ {deleted:,} registros borrados")
    return deleted


def import_new_species(db):
    """Importar nuevas especies desde CSV."""
    print("\n[2/3] Importando nuevas clasificaciones…")

    if not CLASSIFIED_CSV.exists():
        raise FileNotFoundError(f"CSV no encontrado: {CLASSIFIED_CSV}")

    if not GROUPS_CSV.exists():
        raise FileNotFoundError(f"Grupos no encontrados: {GROUPS_CSV}")

    # Cargar datos
    df = pd.read_csv(CLASSIFIED_CSV)
    groups_df = pd.read_csv(GROUPS_CSV)

    code_to_name = dict(zip(
        groups_df["Code"].str.strip(),
        groups_df["Functional_Group"].str.strip(),
    ))

    # Detectar columna de taxón
    taxon_col = "species_name" if "species_name" in df.columns else "genus_name"
    print(f"  Usando columna: {taxon_col}")

    # Importar con batch
    batch = db.batch()
    count = 0

    for _, row in df.iterrows():
        taxon = str(row[taxon_col]).strip()
        code = str(row.get("group_code", "UNCLASSIFIED")).strip()
        group_name = code_to_name.get(code, str(row.get("group_name", "Unclassified")).strip())

        doc_ref = db.collection(SPECIES_COL).document(_doc_id(taxon))
        batch.set(doc_ref, {
            "taxon": taxon,
            "current_code": code,
            "current_group": group_name,
            "original_code": code,
            "original_group": group_name,
            "confidence": str(row.get("confidence", "low")),
            "status": "pending",
            "last_modified_by": None,
            "last_modified_at": None,
        })
        count += 1

        if count % 400 == 0:
            print(f"  Importados: {count}")
            batch.commit()
            batch = db.batch()

    if count % 400 != 0:
        batch.commit()

    print(f"✅ {count:,} especies importadas")
    return count


def main():
    print("\n" + "=" * 60)
    print("RESET FIRESTORE - Borrar viejos datos e importar nuevos")
    print("=" * 60 + "\n")

    try:
        db = get_db()
        print("✅ Conectado a Firebase\n")

        # Step 1: Borrar viejos
        clear_species_collection(db)

        # Step 2: Importar nuevos
        n = import_new_species(db)

        # Summary
        print("\n" + "=" * 60)
        print("✅ FIRESTORE ACTUALIZADO EXITOSAMENTE")
        print("=" * 60)
        print(f"""
Resumen:
  • Nuevas especies importadas: {n:,}
  • CSV fuente: {CLASSIFIED_CSV}
  • Estado: Todos en "pending"

Próximos pasos:
  1. Abre Streamlit Cloud
  2. Haz refresh en el navegador (Ctrl+Shift+R)
  3. Debería mostrar {n:,} taxa activos

  O ejecuta localmente:
  streamlit run app.py
""")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
