"""
Crea el primer usuario administrador en Azure SQL.
Ejecutar una sola vez antes de arrancar la app.

Uso:
    python create_admin.py
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import sys
import getpass
from sql_client import get_db, _hash_password

def main():
    print("=== Crear usuario administrador ===\n")
    email = input("Correo electrónico: ").strip().lower()
    name  = input("Nombre completo: ").strip()
    pwd1  = getpass.getpass("Contraseña: ")
    pwd2  = getpass.getpass("Confirmar contraseña: ")

    if pwd1 != pwd2:
        print("❌ Las contraseñas no coinciden.")
        sys.exit(1)
    if len(pwd1) < 8:
        print("❌ La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)

    from sqlalchemy import text
    engine = get_db()

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        ).fetchone()

    if existing:
        # Update to admin if already exists
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET is_admin = 1, password_hash = :hash, display_name = :name WHERE email = :email"),
                {"hash": _hash_password(pwd1), "name": name, "email": email},
            )
        print(f"\n✅ Usuario existente actualizado como admin: {email}")
    else:
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO users (email, display_name, password_hash, is_admin)
                         VALUES (:email, :name, :hash, 1)"""),
                {"email": email, "name": name, "hash": _hash_password(pwd1)},
            )
        print(f"\n✅ Admin creado: {name} <{email}>")

    print("Ya puedes iniciar sesión en la app.")

if __name__ == "__main__":
    main()
