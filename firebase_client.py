"""
firebase_client.py — Data layer: Firestore + Firebase Auth.

Read strategy: one full fetch at startup → cached in st.session_state["_species_df"].
All read operations work on the in-memory DataFrame (zero Firestore reads per click).
Firestore is only touched on:
  - First import
  - Write operations (validate, move, remove, propose, restore)
  - Explicit user refresh
"""

import os
import json
import secrets as _secrets
import string as _string
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests as _requests
import streamlit as st

try:
    import firebase_admin
    from firebase_admin import credentials, firestore, auth as _fb_auth
except ImportError:
    st.error("firebase-admin no instalado. Ejecuta: pip install firebase-admin")
    st.stop()

PROJECT_ROOT = Path(__file__).parent
CREDS_FILE   = PROJECT_ROOT / "firebase-credentials.json"

SPECIES_COL   = "species"
AUDIT_COL     = "audit_log"
PROPOSED_COL  = "proposed_groups"

_SESSION_KEY  = "_species_df"
_PROPOSED_KEY = "_proposed_groups"
_AUTH_URL     = "https://identitytoolkit.googleapis.com/v1"

_AUTH_ERRORS = {
    "EMAIL_NOT_FOUND":             "No existe una cuenta con ese correo.",
    "INVALID_PASSWORD":            "Contraseña incorrecta.",
    "INVALID_LOGIN_CREDENTIALS":   "Correo o contraseña incorrectos.",
    "USER_DISABLED":               "Esta cuenta ha sido deshabilitada.",
    "INVALID_EMAIL":               "Formato de correo inválido.",
    "MISSING_PASSWORD":            "Ingresa tu contraseña.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos fallidos. Intenta más tarde.",
}


# ── Secrets helper (st.secrets → os.environ fallback) ─────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    """Read from st.secrets first (Streamlit Cloud), then os.environ (local .env)."""
    try:
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)


# ── Firebase init ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_db():
    if firebase_admin._apps:
        return firestore.client()

    cred = None
    errors: list[str] = []

    # 1. st.secrets (local .streamlit/secrets.toml y Streamlit Cloud)
    try:
        sa = st.secrets.get("FIREBASE_SERVICE_ACCOUNT")
        if sa:
            # AttrDict → dict plano vía JSON para que Certificate() lo acepte
            sa_dict = json.loads(json.dumps(dict(sa)))
            cred = credentials.Certificate(sa_dict)
    except Exception as e:
        errors.append(f"secrets.toml: {e}")

    # 2. Archivo local firebase-credentials.json
    if cred is None:
        try:
            if CREDS_FILE.exists():
                cred = credentials.Certificate(str(CREDS_FILE))
        except Exception as e:
            errors.append(f"credentials file: {e}")

    # 3. Variable de entorno como JSON string
    if cred is None:
        env_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
        if env_json:
            try:
                cred = credentials.Certificate(json.loads(env_json))
            except Exception as e:
                errors.append(f"env var: {e}")

    if cred is None:
        detail = "\n\n" + " | ".join(errors) if errors else ""
        st.error(
            "❌ Credenciales de Firebase no encontradas." + detail + "\n\n"
            "**Local:** configura `.streamlit/secrets.toml` con `[FIREBASE_SERVICE_ACCOUNT]`.\n\n"
            "**Streamlit Cloud:** agrega los secrets en el dashboard del proyecto."
        )
        st.stop()

    firebase_admin.initialize_app(cred)
    return firestore.client()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _doc_id(taxon: str) -> str:
    return taxon.replace("/", "_").replace(".", "_").replace(" ", "_")[:500]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save_local(df: pd.DataFrame):
    st.session_state[_SESSION_KEY] = df.reset_index(drop=True)


def _invalidate_cache():
    """Invalidate local cache file to force reload from Firestore on next session."""
    cache_path = _get_cache_path()
    if cache_path.exists():
        try:
            cache_path.unlink()
        except Exception:
            pass


def _update_local(taxon: str, updates: dict):
    """Update in-memory cache and invalidate file cache."""
    df = st.session_state.get(_SESSION_KEY)
    if df is None or df.empty:
        return
    mask = df["taxon"] == taxon
    for col, val in updates.items():
        if col not in df.columns:
            df[col] = None
        df.loc[mask, col] = val
    _save_local(df)
    _invalidate_cache()  # Force refresh from Firestore on next session


# ── Import (one-time) ──────────────────────────────────────────────────────────

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
        taxon      = str(row[taxon_col]).strip()
        code       = str(row.get("group_code", "UNCLASSIFIED")).strip()
        group_name = code_to_name.get(code, str(row.get("group_name", "Unclassified")).strip())
        doc_ref = db.collection(SPECIES_COL).document(_doc_id(taxon))
        batch.set(doc_ref, {
            "taxon":            taxon,
            "current_code":     code,
            "current_group":    group_name,
            "original_code":    code,
            "original_group":   group_name,
            "confidence":       str(row.get("confidence", "low")),
            "status":           "pending",
            "last_modified_by": None,
            "last_modified_at": None,
        })
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
    if count % 400 != 0:
        batch.commit()

    if _SESSION_KEY in st.session_state:
        del st.session_state[_SESSION_KEY]
    return count


# ── Reads (local cache + session cache) ────────────────────────────────────────

def _get_cache_path() -> Path:
    """Return path to local cache file (~/.cache/species.csv)."""
    cache_dir = Path.home() / ".cache"
    return cache_dir / "species.csv"


def _load_from_cache_file() -> pd.DataFrame | None:
    """Load species from local cache file if it exists."""
    cache_path = _get_cache_path()
    if cache_path.exists():
        try:
            return pd.read_csv(cache_path)
        except Exception:
            pass
    return None


def _save_to_cache_file(df: pd.DataFrame):
    """Save species DataFrame to local cache file."""
    if df.empty:
        return
    cache_path = _get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)


def load_species(db, force: bool = False) -> pd.DataFrame:
    """
    Load species from local cache first (zero Firestore reads), fallback to Firestore.

    Strategy:
      1. If in session_state and not forced, return cached
      2. If local file exists and not forced, load from file (zero Firestore reads) ✅
      3. Otherwise, fetch from Firestore and save to local cache

    This reduces Firestore reads by ~99% (539K → 600 reads).
    """
    # Check session cache first (loaded this session)
    if not force and _SESSION_KEY in st.session_state:
        return st.session_state[_SESSION_KEY]

    # Try local file cache (most common case — zero Firestore reads)
    if not force:
        df_cached = _load_from_cache_file()
        if df_cached is not None and not df_cached.empty:
            st.session_state[_SESSION_KEY] = df_cached
            return df_cached

    # Fetch from Firestore (only on first install or explicit refresh)
    docs = db.collection(SPECIES_COL).get()
    df = pd.DataFrame([d.to_dict() for d in docs]) if docs else pd.DataFrame()

    # Save to both caches
    _save_to_cache_file(df)
    st.session_state[_SESSION_KEY] = df

    return df


def get_all_species(db) -> pd.DataFrame:
    return load_species(db)


def get_species_for_group(group_code: str, db) -> pd.DataFrame:
    df = load_species(db)
    if df.empty:
        return df
    return df[(df["current_code"] == group_code) & (df["status"] != "removed")].copy()


def get_removed_species(db) -> pd.DataFrame:
    df = load_species(db)
    if df.empty:
        return df
    return df[df["status"] == "removed"].copy()


def get_groups_summary(db) -> dict[str, dict]:
    """Computed entirely from in-memory cache — zero Firestore reads."""
    df = load_species(db)
    if df.empty:
        return {}
    active = df[df["status"] != "removed"]
    summary: dict = {}
    for _, row in active.iterrows():
        code   = row.get("current_code", "UNCLASSIFIED")
        name   = row.get("current_group", "")
        status = row.get("status", "pending")
        if code not in summary:
            summary[code] = {"name": name, "total": 0, "validated": 0, "pending": 0}
        summary[code]["total"] += 1
        if status == "validated":
            summary[code]["validated"] += 1
        else:
            summary[code]["pending"] += 1
    return summary


def load_proposed(db, force: bool = False) -> list[dict]:
    """Load proposed groups. Uses session cache; refresh from Firestore only if forced."""
    if force or _PROPOSED_KEY not in st.session_state:
        docs = db.collection(PROPOSED_COL).get()
        st.session_state[_PROPOSED_KEY] = [d.to_dict() for d in docs]
    return st.session_state[_PROPOSED_KEY]


def get_proposed_groups(db) -> list[dict]:
    return load_proposed(db)


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


# ── Writes (Firestore + in-memory update) ─────────────────────────────────────

def _log(taxon: str, action: str, data: dict, db):
    db.collection(AUDIT_COL).add({"taxon": taxon, "action": action, **data})


def validate_species(taxon: str, expert: str, db):
    now = _now()
    updates = {"status": "validated", "last_modified_by": expert, "last_modified_at": now}
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update(updates)
    _update_local(taxon, updates)
    _log(taxon, "validate", {"expert": expert, "timestamp": now}, db)


def remove_species(taxon: str, current_code: str, expert: str, note: str, db):
    now = _now()
    updates = {"status": "removed", "last_modified_by": expert, "last_modified_at": now}
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update(updates)
    _update_local(taxon, updates)
    _log(taxon, "remove", {
        "from_code": current_code, "note": note, "expert": expert, "timestamp": now,
    }, db)


def move_species(taxon: str, from_code: str, to_code: str, to_name: str, expert: str, note: str, db):
    now = _now()
    updates = {
        "current_code": to_code, "current_group": to_name,
        "status": "validated", "last_modified_by": expert, "last_modified_at": now,
    }
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update(updates)
    _update_local(taxon, updates)
    _log(taxon, "move", {
        "from_code": from_code, "to_code": to_code, "to_name": to_name,
        "note": note, "expert": expert, "timestamp": now,
    }, db)


def restore_species(taxon: str, original_code: str, original_group: str, expert: str, db):
    now = _now()
    updates = {
        "current_code": original_code, "current_group": original_group,
        "status": "pending", "last_modified_by": expert, "last_modified_at": now,
    }
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update(updates)
    _update_local(taxon, updates)
    _log(taxon, "restore", {"expert": expert, "timestamp": now}, db)


def propose_new_group(
    taxon: str, from_code: str,
    group_name: str, group_code: str, description: str,
    expert: str, db,
):
    now = _now()
    prop_code = f"PROP_{group_code.upper()}"
    prop_doc = {
        "group_code":   group_code.upper(),
        "group_name":   group_name,
        "description":  description,
        "proposed_by":  expert,
        "proposed_at":  now,
        "taxon_origin": taxon,
        "from_code":    from_code,
    }
    db.collection(PROPOSED_COL).add(prop_doc)
    if _PROPOSED_KEY in st.session_state:
        st.session_state[_PROPOSED_KEY].insert(0, prop_doc)

    updates = {
        "current_code":  prop_code,
        "current_group": f"[Propuesto] {group_name}",
        "status":        "validated",
        "last_modified_by": expert,
        "last_modified_at": now,
    }
    db.collection(SPECIES_COL).document(_doc_id(taxon)).update(updates)
    _update_local(taxon, updates)
    _log(taxon, "propose_group", {
        "from_code": from_code, "to_code": group_code.upper(),
        "to_name": group_name, "expert": expert, "timestamp": now,
    }, db)


# ── Firebase Auth ──────────────────────────────────────────────────────────────

def _web_api_key() -> str:
    key = _get_secret("FIREBASE_WEB_API_KEY")
    if not key:
        st.error(
            "❌ `FIREBASE_WEB_API_KEY` no configurada.\n\n"
            "**Local:** agrégala a `.env`.\n\n"
            "**Streamlit Cloud:** agrégala en los Secrets del dashboard."
        )
        st.stop()
    return key


def sign_in(email: str, password: str) -> dict:
    resp = _requests.post(
        f"{_AUTH_URL}/accounts:signInWithPassword?key={_web_api_key()}",
        json={"email": email.strip(), "password": password, "returnSecureToken": True},
        timeout=10,
    )
    data = resp.json()
    if "error" in data:
        code = data["error"].get("message", "AUTH_ERROR")
        raise ValueError(_AUTH_ERRORS.get(code, f"Error de autenticación: {code}"))
    return data


def refresh_token(refresh_tok: str) -> dict:
    resp = _requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={_web_api_key()}",
        json={"grant_type": "refresh_token", "refresh_token": refresh_tok},
        timeout=10,
    )
    data = resp.json()
    if "error" in data:
        raise ValueError("Sesión expirada. Por favor inicia sesión nuevamente.")
    return {"idToken": data.get("id_token"), "refreshToken": data.get("refresh_token")}


def expert_name_from_auth(auth: dict) -> str:
    display = (auth.get("displayName") or "").strip()
    if display:
        return display
    email = auth.get("email", "")
    return email.split("@")[0].replace(".", " ").title()


def is_admin(auth: dict) -> bool:
    admin_str = _get_secret("ADMIN_EMAILS")
    admin_emails = [e.strip().lower() for e in admin_str.split(",") if e.strip()]
    return auth.get("email", "").lower() in admin_emails


# ── User management (Admin) ────────────────────────────────────────────────────

def _gen_password(length: int = 12) -> str:
    chars = _string.ascii_letters + _string.digits + "!@#$%"
    return "".join(_secrets.choice(chars) for _ in range(length))


def list_experts() -> list[dict]:
    users, page = [], _fb_auth.list_users()
    while page:
        for u in page.users:
            users.append({
                "uid":            u.uid,
                "email":          u.email or "",
                "display_name":   u.display_name or "",
                "disabled":       u.disabled,
                "email_verified": u.email_verified,
                "created":        u.user_metadata.creation_timestamp,
            })
        page = page.get_next_page()
    return sorted(users, key=lambda u: (u["display_name"] or u["email"]).lower())


def create_expert(email: str, display_name: str) -> str:
    try:
        _fb_auth.get_user_by_email(email)
        raise ValueError(f"Ya existe una cuenta con el correo {email}.")
    except _fb_auth.UserNotFoundError:
        pass
    password = _gen_password()
    _fb_auth.create_user(email=email, display_name=display_name, password=password)
    return password


def update_expert_name(uid: str, display_name: str):
    _fb_auth.update_user(uid, display_name=display_name)


def toggle_expert(uid: str, disable: bool):
    _fb_auth.update_user(uid, disabled=disable)


def delete_expert(uid: str):
    _fb_auth.delete_user(uid)


def send_password_reset(email: str):
    resp = _requests.post(
        f"{_AUTH_URL}/accounts:sendOobCode?key={_web_api_key()}",
        json={"requestType": "PASSWORD_RESET", "email": email},
        timeout=10,
    )
    data = resp.json()
    if "error" in data:
        code = data["error"].get("message", "ERROR")
        raise ValueError(_AUTH_ERRORS.get(code, f"Error: {code}"))
