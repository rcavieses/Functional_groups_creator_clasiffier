"""
sql_client.py — Data layer: Azure SQL Server.
Same public API as firebase_client.py.
"""

import hashlib
import os
import secrets as _secrets
import string as _string
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).parent

_SESSION_KEY = "_species_df"
_PROPOSED_KEY = "_proposed_groups"
_GROUPS_RATINGS_KEY = "_groups_ratings"

_AUTH_ERRORS = {
    "EMAIL_NOT_FOUND": "No existe una cuenta con ese correo.",
    "INVALID_PASSWORD": "Contraseña incorrecta.",
    "USER_DISABLED": "Esta cuenta ha sido deshabilitada.",
}


def _get_secret(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str) -> str:
    salt = _secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{key.hex()}"


def _check_password(password: str, hash_str: str) -> bool:
    try:
        salt, key = hash_str.split(":", 1)
        new_key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return new_key.hex() == key
    except Exception:
        return False


def _gen_password(length: int = 12) -> str:
    chars = _string.ascii_letters + _string.digits + "!@#$%"
    return "".join(_secrets.choice(chars) for _ in range(length))


# ── DB connection ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_db():
    """Return SQLAlchemy engine connected to Azure SQL."""
    from sqlalchemy import create_engine

    server = _get_secret("AZURE_SQL_SERVER", "gocfg.database.windows.net")
    database = _get_secret("AZURE_SQL_DATABASE", "free-sql-db-5085999")
    user = _get_secret("AZURE_SQL_USER", "rcavieses")
    password = _get_secret("AZURE_SQL_PASSWORD", "")

    if not password:
        st.error("❌ `AZURE_SQL_PASSWORD` no configurada.")
        st.stop()

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        f"Uid={user};"
        f"Pwd={password};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}")
    _ensure_tables(engine)
    return engine


def _ensure_tables(engine):
    from sqlalchemy import text

    ddl = [
        """IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
        CREATE TABLE users (
            id INT IDENTITY(1,1) PRIMARY KEY,
            email NVARCHAR(255) UNIQUE NOT NULL,
            display_name NVARCHAR(255),
            password_hash NVARCHAR(255) NOT NULL,
            is_admin BIT DEFAULT 0,
            is_disabled BIT DEFAULT 0,
            created_at DATETIME DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='group_ratings' AND xtype='U')
        CREATE TABLE group_ratings (
            id INT IDENTITY(1,1) PRIMARY KEY,
            group_code NVARCHAR(50),
            group_name NVARCHAR(255),
            rating INT,
            comment NVARCHAR(MAX),
            expert NVARCHAR(255),
            timestamp DATETIME DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='group_proposals' AND xtype='U')
        CREATE TABLE group_proposals (
            id INT IDENTITY(1,1) PRIMARY KEY,
            type NVARCHAR(50),
            group_code NVARCHAR(50),
            group_name NVARCHAR(255),
            reason NVARCHAR(MAX),
            description NVARCHAR(MAX),
            justification NVARCHAR(MAX),
            taxon_origin NVARCHAR(500),
            from_code NVARCHAR(50),
            proposed_by NVARCHAR(255),
            proposed_at DATETIME DEFAULT GETDATE(),
            status NVARCHAR(50) DEFAULT 'pending'
        )""",
        """IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='audit_log' AND xtype='U')
        CREATE TABLE audit_log (
            id INT IDENTITY(1,1) PRIMARY KEY,
            taxon NVARCHAR(500),
            action NVARCHAR(100),
            expert NVARCHAR(255),
            from_code NVARCHAR(50),
            to_code NVARCHAR(50),
            to_name NVARCHAR(255),
            note NVARCHAR(MAX),
            timestamp DATETIME DEFAULT GETDATE()
        )""",
    ]
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


# ── Auth ───────────────────────────────────────────────────────────────────────

def sign_in(email: str, password: str) -> dict:
    from sqlalchemy import text

    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, display_name, password_hash, is_admin, is_disabled FROM users WHERE email = :email"),
            {"email": email.strip().lower()},
        ).fetchone()

    if row is None:
        raise ValueError(_AUTH_ERRORS["EMAIL_NOT_FOUND"])
    if row.is_disabled:
        raise ValueError(_AUTH_ERRORS["USER_DISABLED"])
    if not _check_password(password, row.password_hash):
        raise ValueError(_AUTH_ERRORS["INVALID_PASSWORD"])

    return {
        "uid": str(row.id),
        "email": row.email,
        "displayName": row.display_name or "",
        "is_admin": bool(row.is_admin),
    }


def expert_name_from_auth(auth: dict) -> str:
    display = (auth.get("displayName") or "").strip()
    if display:
        return display
    email = auth.get("email", "")
    return email.split("@")[0].replace(".", " ").title()


def is_admin(auth: dict) -> bool:
    if auth.get("is_admin"):
        return True
    admin_str = _get_secret("ADMIN_EMAILS", "")
    admin_emails = [e.strip().lower() for e in admin_str.split(",") if e.strip()]
    return auth.get("email", "").lower() in admin_emails


# ── Reads ──────────────────────────────────────────────────────────────────────

def is_imported(db) -> bool:
    from sqlalchemy import text

    with db.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM species")).scalar()
    return count > 0


def load_species(db, force: bool = False) -> pd.DataFrame:
    if not force and _SESSION_KEY in st.session_state:
        return st.session_state[_SESSION_KEY]
    df = pd.read_sql("SELECT * FROM species", db)
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
    df = load_species(db)
    if df.empty:
        return {}
    active = df[df["status"] != "removed"]
    summary: dict = {}
    for _, row in active.iterrows():
        code = row.get("current_code", "UNCLASSIFIED")
        name = row.get("current_group", "")
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
    if not force and _PROPOSED_KEY in st.session_state:
        return st.session_state[_PROPOSED_KEY]
    df = pd.read_sql("SELECT * FROM group_proposals", db)
    result = df.to_dict("records")
    st.session_state[_PROPOSED_KEY] = result
    return result


def get_proposed_groups(db) -> list[dict]:
    return load_proposed(db)


def load_group_ratings(db, force: bool = False) -> pd.DataFrame:
    if not force and _GROUPS_RATINGS_KEY in st.session_state:
        return st.session_state[_GROUPS_RATINGS_KEY]
    df = pd.read_sql("SELECT * FROM group_ratings", db)
    st.session_state[_GROUPS_RATINGS_KEY] = df
    return df


def get_group_rating_summary(db) -> dict:
    ratings_df = load_group_ratings(db)
    if ratings_df.empty:
        return {}
    summary = {}
    for group_code in ratings_df["group_code"].unique():
        group_ratings = ratings_df[ratings_df["group_code"] == group_code]
        summary[group_code] = {
            "avg_rating": group_ratings["rating"].mean(),
            "count": len(group_ratings),
            "comments": group_ratings["comment"].tolist(),
        }
    return summary


def get_audit_log(db, limit: int = 500) -> pd.DataFrame:
    df = pd.read_sql(
        f"SELECT TOP {limit} * FROM audit_log ORDER BY timestamp DESC", db
    )
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M UTC")
    return df


# ── Writes ─────────────────────────────────────────────────────────────────────

def _update_species(taxon: str, updates: dict, db):
    from sqlalchemy import text

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "taxon": taxon}
    with db.begin() as conn:
        conn.execute(
            text(f"UPDATE species SET {set_clause} WHERE taxon = :taxon"),
            params,
        )
    df = st.session_state.get(_SESSION_KEY)
    if df is not None and not df.empty:
        mask = df["taxon"] == taxon
        for col, val in updates.items():
            if col not in df.columns:
                df[col] = None
            df.loc[mask, col] = val
        st.session_state[_SESSION_KEY] = df.reset_index(drop=True)


def _log(taxon: str, action: str, data: dict, db):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(
            text("""INSERT INTO audit_log (taxon, action, expert, from_code, to_code, to_name, note)
                     VALUES (:taxon, :action, :expert, :from_code, :to_code, :to_name, :note)"""),
            {
                "taxon": taxon,
                "action": action,
                "expert": data.get("expert"),
                "from_code": data.get("from_code"),
                "to_code": data.get("to_code"),
                "to_name": data.get("to_name"),
                "note": data.get("note"),
            },
        )


def validate_species(taxon: str, expert: str, db):
    now = _now()
    updates = {"status": "validated", "last_modified_by": expert, "last_modified_at": now}
    _update_species(taxon, updates, db)
    _log(taxon, "validate", {"expert": expert}, db)


def remove_species(taxon: str, current_code: str, expert: str, note: str, db):
    now = _now()
    updates = {"status": "removed", "last_modified_by": expert, "last_modified_at": now}
    _update_species(taxon, updates, db)
    _log(taxon, "remove", {"expert": expert, "from_code": current_code, "note": note}, db)


def move_species(taxon: str, from_code: str, to_code: str, to_name: str, expert: str, note: str, db):
    now = _now()
    updates = {
        "current_code": to_code, "current_group": to_name,
        "status": "validated", "last_modified_by": expert, "last_modified_at": now,
    }
    _update_species(taxon, updates, db)
    _log(taxon, "move", {
        "expert": expert, "from_code": from_code, "to_code": to_code, "to_name": to_name, "note": note,
    }, db)


def restore_species(taxon: str, original_code: str, original_group: str, expert: str, db):
    now = _now()
    updates = {
        "current_code": original_code, "current_group": original_group,
        "status": "pending", "last_modified_by": expert, "last_modified_at": now,
    }
    _update_species(taxon, updates, db)
    _log(taxon, "restore", {"expert": expert}, db)


def propose_new_group(
    taxon: str, from_code: str,
    group_name: str, group_code: str, description: str,
    expert: str, db,
):
    from sqlalchemy import text

    now = _now()
    prop_code = f"PROP_{group_code.upper()}"
    with db.begin() as conn:
        conn.execute(
            text("""INSERT INTO group_proposals
                    (type, group_code, group_name, description, taxon_origin, from_code, proposed_by, status)
                    VALUES ('new_group', :group_code, :group_name, :description, :taxon, :from_code, :expert, 'pending')"""),
            {
                "group_code": group_code.upper(), "group_name": group_name,
                "description": description, "taxon": taxon,
                "from_code": from_code, "expert": expert,
            },
        )
    if _PROPOSED_KEY in st.session_state:
        del st.session_state[_PROPOSED_KEY]

    updates = {
        "current_code": prop_code,
        "current_group": f"[Propuesto] {group_name}",
        "status": "validated",
        "last_modified_by": expert,
        "last_modified_at": now,
    }
    _update_species(taxon, updates, db)
    _log(taxon, "propose_group", {
        "expert": expert, "from_code": from_code,
        "to_code": group_code.upper(), "to_name": group_name,
    }, db)


def rate_group(group_code: str, group_name: str, rating: int, comment: str, expert: str, db):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(
            text("DELETE FROM group_ratings WHERE group_code = :group_code AND expert = :expert"),
            {"group_code": group_code, "expert": expert},
        )
        conn.execute(
            text("""INSERT INTO group_ratings (group_code, group_name, rating, comment, expert)
                     VALUES (:group_code, :group_name, :rating, :comment, :expert)"""),
            {"group_code": group_code, "group_name": group_name,
             "rating": rating, "comment": comment, "expert": expert},
        )
    if _GROUPS_RATINGS_KEY in st.session_state:
        del st.session_state[_GROUPS_RATINGS_KEY]


def propose_group_deletion(group_code: str, group_name: str, reason: str, expert: str, db):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(
            text("""INSERT INTO group_proposals (type, group_code, group_name, reason, proposed_by, status)
                     VALUES ('deletion', :group_code, :group_name, :reason, :expert, 'pending')"""),
            {"group_code": group_code, "group_name": group_name, "reason": reason, "expert": expert},
        )
    if _PROPOSED_KEY in st.session_state:
        del st.session_state[_PROPOSED_KEY]


def propose_new_group_detailed(
    group_code: str, group_name: str, description: str,
    justification: str, expert: str, db,
):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(
            text("""INSERT INTO group_proposals
                    (type, group_code, group_name, description, justification, proposed_by, status)
                    VALUES ('new_group', :group_code, :group_name, :description, :justification, :expert, 'pending')"""),
            {
                "group_code": group_code.upper(), "group_name": group_name,
                "description": description, "justification": justification, "expert": expert,
            },
        )
    if _PROPOSED_KEY in st.session_state:
        del st.session_state[_PROPOSED_KEY]


# ── User management ────────────────────────────────────────────────────────────

def list_experts() -> list[dict]:
    engine = get_db()
    df = pd.read_sql(
        "SELECT id, email, display_name, is_admin, is_disabled, created_at FROM users ORDER BY display_name",
        engine,
    )
    return [
        {
            "uid": str(row["id"]),
            "email": row["email"] or "",
            "display_name": row["display_name"] or "",
            "disabled": bool(row["is_disabled"]),
            "is_admin": bool(row["is_admin"]),
            "email_verified": True,
            "created": None,
        }
        for _, row in df.iterrows()
    ]


def create_expert(email: str, display_name: str) -> str:
    from sqlalchemy import text

    engine = get_db()
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email.strip().lower()},
        ).fetchone()

    if existing:
        raise ValueError(f"Ya existe una cuenta con el correo {email}.")

    password = _gen_password()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO users (email, display_name, password_hash, is_admin)
                     VALUES (:email, :display_name, :password_hash, 0)"""),
            {
                "email": email.strip().lower(),
                "display_name": display_name.strip(),
                "password_hash": _hash_password(password),
            },
        )
    return password


def update_expert_name(uid: str, display_name: str):
    from sqlalchemy import text

    engine = get_db()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET display_name = :name WHERE id = :uid"),
            {"name": display_name.strip(), "uid": int(uid)},
        )


def toggle_expert(uid: str, disable: bool):
    from sqlalchemy import text

    engine = get_db()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_disabled = :disabled WHERE id = :uid"),
            {"disabled": 1 if disable else 0, "uid": int(uid)},
        )


def delete_expert(uid: str):
    from sqlalchemy import text

    engine = get_db()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": int(uid)})


def send_password_reset(email: str) -> str:
    """Reset password and return the new temporary password (share manually with the expert)."""
    from sqlalchemy import text

    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email.strip().lower()},
        ).fetchone()

    if row is None:
        raise ValueError(_AUTH_ERRORS["EMAIL_NOT_FOUND"])

    new_password = _gen_password()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :hash WHERE email = :email"),
            {"hash": _hash_password(new_password), "email": email.strip().lower()},
        )
    return new_password


# ── Legacy compat ──────────────────────────────────────────────────────────────

def import_classifications(classified_csv, groups_csv, db) -> int:
    return 0


def refresh_token(refresh_tok: str) -> dict:
    return {}
