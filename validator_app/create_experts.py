"""
create_experts.py — Crea cuentas de Firebase Auth para los expertos validadores.
================================================================================

Uso:
    cd Functional_groups_creator_clasiffier
    python validator_app/create_experts.py

Edita la lista EXPERTS con los correos y nombres de los 20 expertos.
Se genera una contraseña temporal aleatoria para cada uno.
Los expertos deberán cambiar su contraseña en el primer inicio de sesión
(o pueden usar el enlace de restablecimiento que Firebase puede enviar).

Requisitos: firebase-credentials.json en el directorio del proyecto.
"""

import sys
import secrets
import string
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import firebase_admin
from firebase_admin import credentials, auth

PROJECT_ROOT = Path(__file__).parent.parent
CREDS_FILE = PROJECT_ROOT / "firebase-credentials.json"

# ── Edita esta lista con los expertos del proyecto ────────────────────────────
EXPERTS = [
    {"email": "experto1@institucion.mx",  "display_name": "Dr. Juan Pérez"},
    {"email": "experto2@institucion.mx",  "display_name": "Dra. María García"},
    {"email": "experto3@institucion.mx",  "display_name": "Dr. Carlos López"},
    # ... agrega los 20 expertos aquí
]


def _gen_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


def create_experts():
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(CREDS_FILE))
        firebase_admin.initialize_app(cred)

    print(f"\n{'='*60}")
    print(f"Creando {len(EXPERTS)} cuentas de expertos en Firebase Auth")
    print(f"{'='*60}\n")

    results = []
    for expert in EXPERTS:
        email = expert["email"]
        display_name = expert["display_name"]
        password = _gen_password()

        try:
            # Check if user already exists
            try:
                existing = auth.get_user_by_email(email)
                print(f"  ⚠️  Ya existe: {email} ({existing.display_name})")
                results.append({"email": email, "display_name": display_name,
                                 "password": "(ya existía)", "status": "skipped"})
                continue
            except auth.UserNotFoundError:
                pass

            user = auth.create_user(
                email=email,
                display_name=display_name,
                password=password,
                email_verified=False,
            )
            print(f"  ✅ Creado: {email} | Contraseña temporal: {password}")
            results.append({"email": email, "display_name": display_name,
                             "password": password, "status": "created",
                             "uid": user.uid})

        except Exception as e:
            print(f"  ❌ Error con {email}: {e}")
            results.append({"email": email, "display_name": display_name,
                             "password": "", "status": f"error: {e}"})

    # Save credentials to CSV for distribution
    import csv
    out_file = PROJECT_ROOT / "output" / "expert_credentials.csv"
    out_file.parent.mkdir(exist_ok=True)
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "display_name", "password", "status"])
        writer.writeheader()
        writer.writerows(results)

    created = sum(1 for r in results if r["status"] == "created")
    print(f"\n{'='*60}")
    print(f"Resumen: {created} creados, {len(results)-created} omitidos/errores")
    print(f"Credenciales guardadas en: {out_file}")
    print(f"{'='*60}")
    print("\n⚠️  Distribuye las contraseñas de forma segura (no por email en claro).")
    print("    Los expertos pueden cambiar su contraseña en:")
    print("    https://functional-groups-87d67.firebaseapp.com/__/auth/action?mode=resetPassword")


if __name__ == "__main__":
    create_experts()
