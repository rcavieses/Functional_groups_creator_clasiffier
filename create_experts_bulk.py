"""One-shot script: inserts invited experts from data/expertos_invitados.csv with a shared password."""
import hashlib
import secrets
import csv
from pathlib import Path
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

PASSWORD = "Plancton2026!"
CSV_PATH = Path(__file__).parent / "data" / "expertos_invitados.csv"

AZURE_SQL_SERVER   = "gocfg.database.windows.net"
AZURE_SQL_DATABASE = "free-sql-db-5085999"
AZURE_SQL_USER     = "rcavieses"
AZURE_SQL_PASSWORD = "Fiatlux.89"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{key.hex()}"


def main():
    engine = create_engine(
        f"mssql+pymssql://{quote_plus(AZURE_SQL_USER)}:{quote_plus(AZURE_SQL_PASSWORD)}"
        f"@{AZURE_SQL_SERVER}:1433/{AZURE_SQL_DATABASE}?tds_version=7.4",
        connect_args={"timeout": 60, "login_timeout": 60},
    )

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Email", "").strip()]

    print(f"Procesando {len(rows)} expertos...\n")

    created, skipped, errors = 0, 0, 0

    with engine.connect() as conn:
        for row in rows:
            email = row["Email"].strip().lower()
            name  = row["Nombre"].strip()

            existing = conn.execute(
                text("SELECT id FROM users WHERE email = :email"), {"email": email}
            ).fetchone()

            if existing:
                print(f"  SKIP  {email} (ya existe)")
                skipped += 1
                continue

            try:
                with engine.begin() as wconn:
                    wconn.execute(
                        text("""INSERT INTO users (email, display_name, password_hash, is_admin)
                                 VALUES (:email, :name, :hash, 0)"""),
                        {"email": email, "name": name, "hash": hash_password(PASSWORD)},
                    )
                print(f"  OK    {name} <{email}>")
                created += 1
            except Exception as exc:
                print(f"  ERROR {email}: {exc}")
                errors += 1

    print(f"\nResumen: {created} creados, {skipped} omitidos, {errors} errores.")


if __name__ == "__main__":
    main()
