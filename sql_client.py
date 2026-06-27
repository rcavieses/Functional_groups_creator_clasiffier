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

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).parent

_SESSION_KEY = "_species_df"
_PROPOSED_KEY = "_proposed_groups"
_GROUPS_RATINGS_KEY = "_groups_ratings"
_GROUP_DESCRIPTIONS_KEY = "_group_descriptions"
_GROUP_ASSIGNMENTS_KEY = "_group_assignments"

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


_AZURE_TRANSIENT_CODES = {40613, 40197, 40501, 49918, 4060, 1205}

def _with_retry(fn, *args, retries: int = 3, delay: float = 2.0, **kwargs):
    """Retry fn on Azure SQL transient errors."""
    import time
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            code = getattr(e, "args", [None])[0] if e.args else None
            if isinstance(code, int) and code in _AZURE_TRANSIENT_CODES:
                last_exc = e
                time.sleep(delay * (attempt + 1))
            else:
                raise
    raise last_exc


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
    """Return SQLAlchemy engine connected to Azure SQL (pymssql — no system driver needed)."""
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus

    server = _get_secret("AZURE_SQL_SERVER", "gocfg.database.windows.net")
    database = _get_secret("AZURE_SQL_DATABASE", "free-sql-db-5085999")
    user = _get_secret("AZURE_SQL_USER", "rcavieses")
    password = _get_secret("AZURE_SQL_PASSWORD", "")

    if not password:
        st.error("❌ `AZURE_SQL_PASSWORD` no configurada.")
        st.stop()

    engine = create_engine(
        f"mssql+pymssql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{server}:1433/{database}?tds_version=7.4",
        pool_pre_ping=True,       # descarta conexiones obsoletas del pool antes de usarlas
        pool_recycle=1800,        # recicla conexiones cada 30 min para evitar timeouts de Azure
        pool_size=5,
        max_overflow=2,
        connect_args={"timeout": 30, "login_timeout": 30},
    )
    return engine


def _ensure_tables_on_startup(engine):
    """Called once per session after the engine is ready. Separated from get_db() so a
    transient Azure SQL auto-resume error doesn't poison the @st.cache_resource engine."""
    if st.session_state.get("_tables_ensured"):
        return
    _ensure_tables(engine)
    st.session_state["_tables_ensured"] = True


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
        """IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='group_descriptions' AND xtype='U')
        CREATE TABLE group_descriptions (
            group_code NVARCHAR(50) PRIMARY KEY,
            description NVARCHAR(MAX),
            updated_by NVARCHAR(255),
            updated_at DATETIME DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='group_assignments' AND xtype='U')
        CREATE TABLE group_assignments (
            id INT IDENTITY(1,1) PRIMARY KEY,
            group_code NVARCHAR(50),
            expert_email NVARCHAR(255),
            assigned_at DATETIME DEFAULT GETDATE(),
            assigned_by NVARCHAR(255),
            UNIQUE (group_code, expert_email)
        )""",
    ]

    # Column migrations for tables created by an earlier schema version. The CREATE TABLE
    # statements above are guarded by IF NOT EXISTS, so columns added later (e.g. `expert`
    # in group_ratings) are NOT applied to tables that already exist. These idempotent
    # ALTERs backfill the missing columns.
    migrations = [
        ("group_ratings", "expert", "NVARCHAR(255)"),
        ("audit_log", "expert", "NVARCHAR(255)"),
        ("species", "family", "NVARCHAR(255)"),
        ("species", "genus", "NVARCHAR(255)"),
        ("species", "order_taxon", "NVARCHAR(255)"),
        ("species", "class_taxon", "NVARCHAR(255)"),
        ("species", "phylum", "NVARCHAR(255)"),
        ("species", "kingdom", "NVARCHAR(255)"),
    ]
    migration_ddl = [
        f"""IF EXISTS (SELECT * FROM sysobjects WHERE name='{table}' AND xtype='U')
        AND NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME='{table}' AND COLUMN_NAME='{column}'
        )
        ALTER TABLE {table} ADD {column} {coltype}"""
        for table, column, coltype in migrations
    ]

    import time
    last_exc = None
    for attempt in range(4):
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for stmt in ddl:
                    conn.execute(text(stmt))
                for stmt in migration_ddl:
                    conn.execute(text(stmt))
            return
        except Exception as e:
            last_exc = e
            # Azure SQL serverless auto-resume takes ~60-90 s; back off gradually
            time.sleep(20 * (attempt + 1))
    raise last_exc


# ── Auth ───────────────────────────────────────────────────────────────────────

def sign_in(email: str, password: str) -> dict:
    from sqlalchemy import text

    engine = get_db()
    _ensure_tables_on_startup(engine)

    def _query():
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT id, email, display_name, password_hash, is_admin, is_disabled FROM users WHERE email = :email"),
                {"email": email.strip().lower()},
            ).fetchone()

    row = _with_retry(_query)

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


def get_admin_emails() -> set:
    """Return all emails that have admin privileges (DB flag or ADMIN_EMAILS secret)."""
    engine = get_db()
    df = pd.read_sql("SELECT email FROM users WHERE is_admin = 1", engine)
    admin_set = {row.lower() for row in df["email"].dropna()}
    admin_str = _get_secret("ADMIN_EMAILS", "")
    for e in admin_str.split(","):
        e = e.strip().lower()
        if e:
            admin_set.add(e)
    return admin_set


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


def get_species_by_genus(db) -> dict[str, pd.DataFrame]:
    """Group active species by genus. Returns {genus: DataFrame}."""
    df = load_species(db)
    if df.empty:
        return {}
    active = df[df["status"] != "removed"].copy()
    grouped = {}
    for genus, group_df in active.groupby("genus"):
        if pd.notna(genus):
            grouped[str(genus)] = group_df.sort_values("taxon").reset_index(drop=True)
    return dict(sorted(grouped.items()))


def get_species_by_family(db) -> dict[str, pd.DataFrame]:
    """Group active species by family. Returns {family: DataFrame}."""
    df = load_species(db)
    if df.empty:
        return {}
    active = df[df["status"] != "removed"].copy()
    grouped = {}
    for family, group_df in active.groupby("family"):
        if pd.notna(family):
            grouped[str(family)] = group_df.sort_values("genus").reset_index(drop=True)
    return dict(sorted(grouped.items()))


def get_taxon_summary(taxon_name: str, taxon_type: str, db) -> dict:
    """
    Get summary of a genus or family: how many species, how many groups, etc.
    taxon_type: 'genus' or 'family'
    Returns: {"count": int, "groups": {code: name}, "species_by_group": {code: [taxon...]}}
    """
    df = load_species(db)
    if df.empty:
        return {"count": 0, "groups": {}, "species_by_group": {}}

    col = "genus" if taxon_type == "genus" else "family"
    active = df[(df["status"] != "removed") & (df[col] == taxon_name)].copy()

    if active.empty:
        return {"count": 0, "groups": {}, "species_by_group": {}}

    groups_set = {}
    species_by_group = {}

    for _, row in active.iterrows():
        code = row.get("current_code", "UNCLASSIFIED")
        name = row.get("current_group", "")
        taxon = row.get("taxon", "")

        if code not in groups_set:
            groups_set[code] = name
            species_by_group[code] = []

        species_by_group[code].append(taxon)

    return {
        "count": len(active),
        "groups": groups_set,
        "species_by_group": species_by_group,
        "full_df": active,
    }


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


def get_my_group_rating(group_code: str, expert: str, db) -> dict | None:
    """Return this expert's existing rating for a group as {'rating', 'comment'}, or None.

    Handles the schema drift where the identity column may be named `expert` or `rated_by`.
    """
    df = load_group_ratings(db)
    if df.empty or "group_code" not in df.columns:
        return None
    id_cols = [c for c in ("expert", "rated_by") if c in df.columns]
    if not id_cols:
        return None

    id_mask = None
    for c in id_cols:
        m = df[c] == expert
        id_mask = m if id_mask is None else (id_mask | m)
    match = df[(df["group_code"] == group_code) & id_mask]
    if match.empty:
        return None

    row = match.iloc[-1]
    comment = row.get("comment")
    if comment is None or (isinstance(comment, float) and pd.isna(comment)):
        comment = ""
    return {
        "rating": int(row["rating"]) if pd.notna(row["rating"]) else None,
        "comment": str(comment),
    }


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
        # The expert identity column has drifted across schema versions: the code-defined
        # schema names it `expert`, while the original Azure table used `rated_by` (NOT NULL).
        # A given deployment may have either or both, so adapt to whatever exists and fill
        # every present identity column to satisfy NOT NULL constraints.
        existing = {
            row[0].lower()
            for row in conn.execute(
                text("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'group_ratings'")
            )
        }
        id_cols = [c for c in ("expert", "rated_by") if c in existing]

        params = {"group_code": group_code, "group_name": group_name,
                  "rating": rating, "comment": comment, "expert": expert}

        if id_cols:
            where_expert = " OR ".join(f"{c} = :expert" for c in id_cols)
            conn.execute(
                text(f"DELETE FROM group_ratings WHERE group_code = :group_code AND ({where_expert})"),
                {"group_code": group_code, "expert": expert},
            )

        insert_cols = ["group_code", "group_name", "rating", "comment"] + id_cols
        col_list = ", ".join(insert_cols)
        # both `expert` and `rated_by` bind to the same :expert parameter
        val_list = ", ".join(":expert" if c in id_cols else f":{c}" for c in insert_cols)
        conn.execute(
            text(f"INSERT INTO group_ratings ({col_list}) VALUES ({val_list})"),
            params,
        )
    if _GROUPS_RATINGS_KEY in st.session_state:
        del st.session_state[_GROUPS_RATINGS_KEY]


def propose_group_modification(group_code: str, group_name: str, suggestion: str, expert: str, db):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(
            text("""INSERT INTO group_proposals (type, group_code, group_name, reason, proposed_by, status)
                     VALUES ('modification', :group_code, :group_name, :reason, :expert, 'pending')"""),
            {"group_code": group_code, "group_name": group_name, "reason": suggestion, "expert": expert},
        )
    if _PROPOSED_KEY in st.session_state:
        del st.session_state[_PROPOSED_KEY]


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


def _ensure_new_tables(db):
    _ensure_tables_on_startup(db)


# ── Group descriptions ─────────────────────────────────────────────────────────

def get_group_descriptions(db, force: bool = False) -> dict:
    """Return {group_code: description} for all groups."""
    _ensure_new_tables(db)
    if not force and _GROUP_DESCRIPTIONS_KEY in st.session_state:
        return st.session_state[_GROUP_DESCRIPTIONS_KEY]
    df = pd.read_sql("SELECT group_code, description FROM group_descriptions", db)
    result = {row["group_code"]: row["description"] or "" for _, row in df.iterrows()}
    st.session_state[_GROUP_DESCRIPTIONS_KEY] = result
    return result


def set_group_description(group_code: str, description: str, updated_by: str, db):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(
            text("""MERGE group_descriptions AS target
                    USING (SELECT :group_code AS group_code) AS source ON target.group_code = source.group_code
                    WHEN MATCHED THEN UPDATE SET description = :description, updated_by = :updated_by, updated_at = GETDATE()
                    WHEN NOT MATCHED THEN INSERT (group_code, description, updated_by) VALUES (:group_code, :description, :updated_by);"""),
            {"group_code": group_code, "description": description, "updated_by": updated_by},
        )
    if _GROUP_DESCRIPTIONS_KEY in st.session_state:
        del st.session_state[_GROUP_DESCRIPTIONS_KEY]


def seed_group_descriptions(rows: list[dict], db):
    """Seed descriptions from CSV rows [{Code, Species_Composition}]. Skips existing."""
    from sqlalchemy import text

    with db.begin() as conn:
        for row in rows:
            code = str(row.get("Code", "")).strip()
            desc = str(row.get("Species_Composition", "")).strip()
            if not code:
                continue
            conn.execute(
                text("""IF NOT EXISTS (SELECT 1 FROM group_descriptions WHERE group_code = :code)
                         INSERT INTO group_descriptions (group_code, description, updated_by)
                         VALUES (:code, :desc, 'system')"""),
                {"code": code, "desc": desc},
            )
    if _GROUP_DESCRIPTIONS_KEY in st.session_state:
        del st.session_state[_GROUP_DESCRIPTIONS_KEY]


# ── Group assignments ──────────────────────────────────────────────────────────

def get_group_assignments(db, force: bool = False) -> pd.DataFrame:
    """Return full assignments table."""
    _ensure_new_tables(db)
    if not force and _GROUP_ASSIGNMENTS_KEY in st.session_state:
        return st.session_state[_GROUP_ASSIGNMENTS_KEY]
    df = pd.read_sql("SELECT * FROM group_assignments ORDER BY group_code, expert_email", db)
    st.session_state[_GROUP_ASSIGNMENTS_KEY] = df
    return df


def get_my_assignments(expert_email: str, db) -> list:
    """Return list of group_codes assigned to this expert."""
    df = get_group_assignments(db)
    if df.empty:
        return []
    return df[df["expert_email"] == expert_email.lower()]["group_code"].tolist()


def get_assignment_stats(db) -> dict:
    """Return {group_code: count} of assignments per group."""
    df = get_group_assignments(db)
    if df.empty:
        return {}
    return df.groupby("group_code").size().to_dict()


def distribute_groups(expert_emails: list, min_evals: int, assigned_by: str, db):
    """Distribute groups so each group is assigned to at least min_evals experts.

    Uses a round-robin approach: each group is repeated min_evals times in the
    assignment queue, then distributed sequentially across experts.
    Clears previous assignments before inserting new ones.
    """
    import random
    from sqlalchemy import text

    engine = db
    groups_df = pd.read_sql("SELECT DISTINCT current_code FROM species WHERE status != 'removed'", engine)
    group_codes = sorted(groups_df["current_code"].dropna().unique().tolist())

    N = len(expert_emails)
    G = len(group_codes)
    if N == 0 or G == 0:
        return

    # Each group needs min_evals evaluators; cap at number of available experts
    evals_per_group = min(min_evals, N)

    # Build assignment queue: each group appears evals_per_group times
    # Interleave groups so the same expert doesn't get consecutive codes from the same cluster
    assignment_queue = []
    for i in range(evals_per_group):
        assignment_queue.extend(group_codes)

    # Sort experts list deterministically but vary with iteration offset
    shuffled_experts = expert_emails[:]
    random.shuffle(shuffled_experts)

    assignments = []
    for idx, group_code in enumerate(assignment_queue):
        expert = shuffled_experts[idx % N]
        assignments.append((group_code, expert))

    # Deduplicate: keep first occurrence of each (group, expert) pair
    seen = set()
    deduped = []
    for group_code, expert in assignments:
        key = (group_code, expert)
        if key not in seen:
            seen.add(key)
            deduped.append(key)

    # If after dedup some groups have fewer than evals_per_group assignments, fill gaps
    from collections import defaultdict
    group_expert_map = defaultdict(set)
    for group_code, expert in deduped:
        group_expert_map[group_code].add(expert)

    for group_code in group_codes:
        assigned = group_expert_map[group_code]
        needed = evals_per_group - len(assigned)
        if needed <= 0:
            continue
        remaining = [e for e in shuffled_experts if e not in assigned]
        for expert in remaining[:needed]:
            deduped.append((group_code, expert))

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM group_assignments"))
        for group_code, expert in deduped:
            conn.execute(
                text("""INSERT INTO group_assignments (group_code, expert_email, assigned_by)
                         VALUES (:group_code, :expert_email, :assigned_by)"""),
                {"group_code": group_code, "expert_email": expert.lower(), "assigned_by": assigned_by},
            )

    if _GROUP_ASSIGNMENTS_KEY in st.session_state:
        del st.session_state[_GROUP_ASSIGNMENTS_KEY]


def clear_assignments(db):
    from sqlalchemy import text

    with db.begin() as conn:
        conn.execute(text("DELETE FROM group_assignments"))
    if _GROUP_ASSIGNMENTS_KEY in st.session_state:
        del st.session_state[_GROUP_ASSIGNMENTS_KEY]


# ── Legacy compat ──────────────────────────────────────────────────────────────

def import_classifications(classified_csv, groups_csv, db) -> int:
    return 0


def refresh_token(refresh_tok: str) -> dict:
    return {}


# ── Dashboard analytics ────────────────────────────────────────────────────────

def get_recent_comments(db, limit: int = 20) -> pd.DataFrame:
    """Get recent comments from all experts, excluding current user."""
    df = pd.read_sql(
        f"""SELECT TOP {limit} group_code, group_name, comment, COALESCE(expert, rated_by) as expert, rated_at
           FROM group_ratings
           WHERE comment IS NOT NULL AND comment != ''
           ORDER BY rated_at DESC""",
        db
    )
    if not df.empty and "rated_at" in df.columns:
        df["timestamp"] = pd.to_datetime(df["rated_at"]).dt.strftime("%Y-%m-%d %H:%M")
        df = df.drop("rated_at", axis=1)
    return df


def get_most_commented_groups(db, limit: int = 10) -> pd.DataFrame:
    """Get groups with most comments, ordered by count."""
    df = pd.read_sql(
        f"""SELECT TOP {limit}
           group_code, group_name,
           COUNT(*) as comment_count,
           COUNT(DISTINCT expert) as expert_count
           FROM group_ratings
           WHERE comment IS NOT NULL AND comment != ''
           GROUP BY group_code, group_name
           ORDER BY comment_count DESC""",
        db
    )
    return df


def get_proposals_summary(db) -> dict:
    """Get summary of proposals by type and status."""
    df = pd.read_sql(
        """SELECT type, status, COUNT(*) as count
           FROM group_proposals
           GROUP BY type, status""",
        db
    )
    if df.empty:
        return {"new_group": 0, "modification": 0, "deletion": 0, "pending": 0, "approved": 0}

    result = {
        "new_group": int(df[df["type"] == "new_group"]["count"].sum()) if "new_group" in df["type"].values else 0,
        "modification": int(df[df["type"] == "modification"]["count"].sum()) if "modification" in df["type"].values else 0,
        "deletion": int(df[df["type"] == "deletion"]["count"].sum()) if "deletion" in df["type"].values else 0,
        "pending": int(df[df["status"] == "pending"]["count"].sum()) if "pending" in df["status"].values else 0,
    }
    return result


def get_pending_proposals(db, limit: int = 15) -> pd.DataFrame:
    """Get pending proposals with details."""
    df = pd.read_sql(
        f"""SELECT TOP {limit} id, type, group_code, group_name, reason, description, justification, proposed_by, proposed_at
           FROM group_proposals
           WHERE status = 'pending'
           ORDER BY proposed_at DESC""",
        db
    )
    if not df.empty and "proposed_at" in df.columns:
        df["proposed_at"] = pd.to_datetime(df["proposed_at"]).dt.strftime("%Y-%m-%d %H:%M")
    return df


def get_expert_activity(db, limit: int = 10) -> pd.DataFrame:
    """Get activity count by expert."""
    df = pd.read_sql(
        f"""SELECT TOP {limit} expert, COUNT(*) as actions_count
           FROM audit_log
           GROUP BY expert
           ORDER BY actions_count DESC""",
        db
    )
    return df


def get_group_rating_stats(db) -> pd.DataFrame:
    """Get average rating and comment count for each group."""
    df = pd.read_sql(
        """SELECT group_code, group_name,
           AVG(CAST(rating AS FLOAT)) as avg_rating,
           COUNT(*) as rating_count,
           SUM(CASE WHEN comment IS NOT NULL AND comment != '' THEN 1 ELSE 0 END) as comment_count
           FROM group_ratings
           WHERE rating IS NOT NULL
           GROUP BY group_code, group_name
           ORDER BY avg_rating DESC, rating_count DESC""",
        db
    )
    return df


def get_recent_activity(db, limit: int = 30) -> pd.DataFrame:
    """Get recent audit log entries."""
    df = pd.read_sql(
        f"""SELECT TOP {limit} taxon, action, expert, from_code, to_code, timestamp
           FROM audit_log
           ORDER BY timestamp DESC""",
        db
    )
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
    return df


def get_groups_validation_status(db) -> pd.DataFrame:
    """Get validation status for each group with species counts."""
    df = pd.read_sql(
        """SELECT
           current_code as group_code,
           current_group as group_name,
           COUNT(*) as total_species,
           SUM(CASE WHEN status = 'validated' THEN 1 ELSE 0 END) as validated_count,
           SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_count,
           SUM(CASE WHEN status = 'removed' THEN 1 ELSE 0 END) as removed_count
           FROM species
           WHERE status != 'removed' AND current_code IS NOT NULL
           GROUP BY current_code, current_group
           ORDER BY total_species DESC""",
        db
    )
    if not df.empty:
        df['validation_pct'] = (df['validated_count'] / df['total_species'].clip(lower=1) * 100).round(1)
    return df


def get_unvalidated_groups(db) -> pd.DataFrame:
    """Get groups with 0% validation (all species pending)."""
    df = pd.read_sql(
        """SELECT
           current_code as group_code,
           current_group as group_name,
           COUNT(*) as total_species
           FROM species
           WHERE status = 'pending' AND current_code IS NOT NULL
           GROUP BY current_code, current_group
           HAVING COUNT(*) = (
               SELECT COUNT(*) FROM species s2
               WHERE s2.current_code = species.current_code
           )
           ORDER BY total_species DESC""",
        db
    )
    return df


def get_fully_validated_groups(db) -> pd.DataFrame:
    """Get groups with 100% validation (all species validated)."""
    df = pd.read_sql(
        """SELECT
           current_code as group_code,
           current_group as group_name,
           COUNT(*) as total_species
           FROM species
           WHERE status = 'validated' AND current_code IS NOT NULL
           GROUP BY current_code, current_group
           HAVING COUNT(*) = (
               SELECT COUNT(*) FROM species s2
               WHERE s2.current_code = species.current_code
           )
           ORDER BY total_species DESC""",
        db
    )
    return df


def get_group_validation_with_ratings(db) -> pd.DataFrame:
    """Get complete validation status with average ratings."""
    df = pd.read_sql(
        """SELECT
           s.current_code as group_code,
           s.current_group as group_name,
           COUNT(DISTINCT s.taxon) as total_species,
           SUM(CASE WHEN s.status = 'validated' THEN 1 ELSE 0 END) as validated_count,
           SUM(CASE WHEN s.status = 'pending' THEN 1 ELSE 0 END) as pending_count,
           ROUND(AVG(CAST(gr.rating AS FLOAT)), 2) as avg_rating,
           COUNT(DISTINCT gr.id) as rating_count,
           SUM(CASE WHEN gr.comment IS NOT NULL AND gr.comment != '' THEN 1 ELSE 0 END) as comment_count
           FROM species s
           LEFT JOIN group_ratings gr ON s.current_code = gr.group_code
           WHERE s.status != 'removed' AND s.current_code IS NOT NULL
           GROUP BY s.current_code, s.current_group
           ORDER BY total_species DESC""",
        db
    )
    if not df.empty:
        df['validation_pct'] = (df['validated_count'] / df['total_species'].clip(lower=1) * 100).round(1)
        df['rating_stars'] = df['avg_rating'].apply(lambda x: '⭐' * int(x) if pd.notna(x) else '—')
    return df


def get_groups_eligible_for_auto_validation(db) -> pd.DataFrame:
    """Get groups that meet auto-validation criteria (avg_rating > 3, rating_count >= 3)."""
    df = pd.read_sql(
        """SELECT
           group_code,
           group_name,
           ROUND(AVG(CAST(rating AS FLOAT)), 2) as avg_rating,
           COUNT(*) as rating_count
           FROM group_ratings
           WHERE rating IS NOT NULL
           GROUP BY group_code, group_name
           HAVING AVG(CAST(rating AS FLOAT)) > 3 AND COUNT(*) >= 3
           ORDER BY AVG(CAST(rating AS FLOAT)) DESC""",
        db
    )
    return df


def auto_validate_groups_by_rating(db, system_user: str = "system") -> dict:
    """Automatically validate all taxa in groups with avg_rating > 3 and rating_count >= 3.

    Returns:
        dict with keys: 'groups_validated', 'taxa_validated', 'summary'
    """
    from sqlalchemy import text

    now = _now()

    # Get eligible groups
    eligible = pd.read_sql(
        """SELECT group_code
           FROM group_ratings
           WHERE rating IS NOT NULL
           GROUP BY group_code
           HAVING AVG(CAST(rating AS FLOAT)) > 3 AND COUNT(*) >= 3""",
        db
    )

    if eligible.empty:
        return {
            'groups_validated': 0,
            'taxa_validated': 0,
            'summary': 'No hay grupos que cumplan los criterios de validación automática'
        }

    groups_to_validate = eligible['group_code'].tolist()

    # Count taxa that will be validated
    placeholders = ','.join(f"'{g}'" for g in groups_to_validate)
    count_df = pd.read_sql(
        f"""SELECT COUNT(*) as count FROM species
           WHERE current_code IN ({placeholders})
           AND status = 'pending'""",
        db
    )
    taxa_count = int(count_df.iloc[0]['count']) if not count_df.empty else 0

    # Update species to validated
    with db.begin() as conn:
        for group_code in groups_to_validate:
            conn.execute(
                text("""UPDATE species
                       SET status = 'validated', last_modified_by = :user, last_modified_at = :now
                       WHERE current_code = :code AND status = 'pending'"""),
                {
                    'code': group_code,
                    'user': system_user,
                    'now': now
                }
            )

            # Log the action
            conn.execute(
                text("""INSERT INTO audit_log (taxon, action, expert, from_code, note, timestamp)
                       VALUES (:taxon, :action, :expert, :from_code, :note, :timestamp)"""),
                {
                    'taxon': f'[Grupo: {group_code}]',
                    'action': 'auto_validate_by_rating',
                    'expert': system_user,
                    'from_code': group_code,
                    'note': f'Validación automática: promedio de calificación > 3, >= 3 calificaciones',
                    'timestamp': now
                }
            )

    # Clear cache
    if _SESSION_KEY in st.session_state:
        del st.session_state[_SESSION_KEY]

    return {
        'groups_validated': len(groups_to_validate),
        'taxa_validated': taxa_count,
        'summary': f'✅ Validados {len(groups_to_validate)} grupos y {taxa_count} taxa automáticamente'
    }
