"""
firebase_client.py — Firestore data layer for the validation app.

Setup:
  1. Create a Firebase project at console.firebase.google.com
  2. Enable Firestore (Native mode)
  3. Project Settings → Service Accounts → Generate new private key
  4. Save as  Functional_groups_creator_clasiffier/firebase-credentials.json
     OR set FIREBASE_SERVICE_ACCOUNT env var with the JSON content in .env
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    st.error("firebase-admin no instalado. Ejecuta: pip install firebase-admin")
    st.stop()

PROJECT_ROOT = Path(__file__).parent.parent
CREDS_FILE = PROJECT_ROOT / "firebase-credentials.json"

SPECIES_COL = "species"
AUDIT_COL = "audit_log"
PROPOSED_COL = "proposed_groups"


@st.cache_resource
def get_db():
    if not firebase_admin._apps:
        env_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
        if CREDS_FILE.exists():
            cred = credentials.Certificate(str(CREDS_FILE))
        elif env_json:
            cred = credentials.Certificate(json.loads(env_json))
        else:
            st.error(
                "❌ Credenciales de Firebase no encontradas.\n\n"
                "Opciones:\n"
                "- Coloca `firebase-credentials.json` en la carpeta del proyecto\n"
                "- O agrega `FIREBASE_SERVICE_ACCOUNT=<json>` a `.env`"
            )
            st.stop()
        firebase_admin.initialize_app(cred)
    return firestore.client()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _doc_id(taxon: str) -> str:
    return taxon.replace("/", "_").replace(".", "_").replace(" ", "_")[:500]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Import ─────────────────────────────────────────────────────────────────────


def is_imported(db) -> bool:
    return len(db.collection(SPECIES_COL).limit(1).get()) > 0


def import_classifications(classified_csv: Path, groups_csv: Path, db) -> int:
    df = pd.read_csv(classified_csv)
    groups_df = pd.read_csv(groups_csv)
    code_to_name = dict(zip(
        groups_df["Code"].str.strip(),
        groups_df["Functional_Group"].str.strip(),
    ))

    taxon_col = "genus_name" if "genus_name" in df.columns else "species_name"

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
            batch.commit()
            batch = db.batch()

    if count % 400 != 0:
        batch.commit()

    return count


# ── Reads ──────────────────────────────────────────────────────────────────────


def get_all_species(db) -> pd.DataFrame:
    docs = db.collection(SPECIES_COL).get()
    return pd.DataFrame([d.to_dict() for d in docs]) if docs else pd.DataFrame()


def get_species_for_group(group_code: str, db) -> pd.DataFrame:
    docs = db.collection(SPECIES_COL).where("current_code", "==", group_code).get()
    df = pd.DataFrame([d.to_dict() for d in docs]) if docs else pd.DataFrame()
    if not df.empty and "status" in df.columns:
        df = df[df["status"] != "removed"]
    return df


def get_removed_species(db) -> pd.DataFrame:
    docs = db.collection(SPECIES_COL).where("status", "==", "removed").get()
    return pd.DataFrame([d.to_dict() for d in docs]) if docs else pd.DataFrame()


def get_groups_summary(db) -> dict[str, dict]:
    """Full scan → dict[code] = {name, total, validated, pending}"""
    docs = db.collection(SPECIES_COL).get()
    summary: dict = {}
    for d in docs:
        r = d.to_dict()
        code = r.get("current_code", "UNCLASSIFIED")
        name = r.get("current_group", "")
        status = r.get("status", "pending")
        if status == "removed":
            continue
        if code not in summary:
            summary[code] = {"name": name, "total": 0, "validated": 0, "pending": 0}
        summary[code]["total"] += 1
        if status == "validated":
            summary[code]["validated"] += 1
        else:
            summary[code]["pending"] += 1
    return summary


def get_proposed_groups(db) -> list[dict]:
    docs = db.collection(PROPOSED_COL).get()
    return [d.to_dict() for d in docs]


def get_audit_log(db, limit: int = 500) -> pd.DataFrame:
    docs = (
        db.collection(AUDIT_COL)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    rows = [d.to_dict() for d in docs]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M UTC")
    return df


# ── Writes ─────────────────────────────────────────────────────────────────────


def _log(taxon: str, action: str, data: dict, db):
    db.collection(AUDIT_COL).add({"taxon": taxon, "action": action, **data})


def validate_species(taxon: str, expert: str, db):
    now = _now()
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update({
        "status": "validated",
        "last_modified_by": expert,
        "last_modified_at": now,
    })
    _log(taxon, "validate", {"expert": expert, "timestamp": now}, db)


def remove_species(taxon: str, current_code: str, expert: str, note: str, db):
    now = _now()
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update({
        "status": "removed",
        "last_modified_by": expert,
        "last_modified_at": now,
    })
    _log(taxon, "remove", {
        "from_code": current_code, "note": note,
        "expert": expert, "timestamp": now,
    }, db)


def move_species(taxon: str, from_code: str, to_code: str, to_name: str, expert: str, note: str, db):
    now = _now()
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update({
        "current_code": to_code,
        "current_group": to_name,
        "status": "validated",
        "last_modified_by": expert,
        "last_modified_at": now,
    })
    _log(taxon, "move", {
        "from_code": from_code, "to_code": to_code, "to_name": to_name,
        "note": note, "expert": expert, "timestamp": now,
    }, db)


def restore_species(taxon: str, original_code: str, original_group: str, expert: str, db):
    now = _now()
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update({
        "current_code": original_code,
        "current_group": original_group,
        "status": "pending",
        "last_modified_by": expert,
        "last_modified_at": now,
    })
    _log(taxon, "restore", {"expert": expert, "timestamp": now}, db)


def propose_new_group(
    taxon: str, from_code: str,
    group_name: str, group_code: str, description: str,
    expert: str, db,
):
    now = _now()
    prop_code = f"PROP_{group_code.upper()}"
    db.collection(PROPOSED_COL).add({
        "group_code": group_code.upper(),
        "group_name": group_name,
        "description": description,
        "proposed_by": expert,
        "proposed_at": now,
        "taxon_origin": taxon,
        "from_code": from_code,
    })
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update({
        "current_code": prop_code,
        "current_group": f"[Propuesto] {group_name}",
        "status": "validated",
        "last_modified_by": expert,
        "last_modified_at": now,
    })
    _log(taxon, "propose_group", {
        "from_code": from_code,
        "proposed_code": group_code.upper(),
        "proposed_name": group_name,
        "expert": expert,
        "timestamp": now,
    }, db)
