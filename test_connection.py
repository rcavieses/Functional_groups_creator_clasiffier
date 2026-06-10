"""Test de conexión a Azure SQL - diagnóstico"""
import os
from pathlib import Path
from dotenv import load_dotenv
import pyodbc

load_dotenv(Path(__file__).parent / ".env")

AZURE_SERVER = "gocfg.database.windows.net"
AZURE_DB = "free-sql-db-5085999"
AZURE_USER = "rcavieses"
AZURE_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

print(f"Password cargada: {'SÍ (len=' + str(len(AZURE_PASSWORD)) + ')' if AZURE_PASSWORD else 'NO - vacía'}")
print(f"Primeros 2 caracteres: '{AZURE_PASSWORD[:2]}...'")
print()

conn_str = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"Server=tcp:{AZURE_SERVER},1433;"
    f"Database={AZURE_DB};"
    f"Uid={AZURE_USER};"
    f"Pwd={AZURE_PASSWORD};"
    f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)
try:
    conn = pyodbc.connect(conn_str, timeout=15)
    print("✅ Conexión exitosa!")
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    print(f"   {cursor.fetchone()[0][:60]}")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")
