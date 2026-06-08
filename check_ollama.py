#!/usr/bin/env python3
"""
check_ollama.py - Script para validar la configuración de Ollama
==================================================================
Verifica que Ollama esté instalado, ejecutándose y con modelos disponibles.
"""

import sys
import os
from pathlib import Path

# Añadir directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

try:
    import requests
except ImportError:
    print("⚠️  Error: 'requests' no está instalado")
    print("Instala dependencias: pip install -r requirements.txt")
    sys.exit(1)

from config import OLLAMA_API_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


def check_ollama_running():
    """Verifica si Ollama está ejecutándose."""
    print("🔍 Verificando si Ollama está ejecutándose...")
    try:
        response = requests.get(
            OLLAMA_API_URL.replace("/api/generate", ""),
            timeout=60,
        )
        if response.status_code == 200:
            print(f"  ✅ Ollama está ejecutándose en {OLLAMA_API_URL}")
            return True
    except requests.exceptions.ConnectionError:
        print(f"  ❌ No se puede conectar a Ollama en {OLLAMA_API_URL}")
        print("  Solución: Ejecuta 'ollama serve' en otra terminal")
        return False
    except Exception as e:
        print(f"  ❌ Error inesperado: {e}")
        return False


def check_model_available():
    """Verifica si el modelo está disponible."""
    print(f"\n🔍 Verificando disponibilidad del modelo '{OLLAMA_MODEL}'...")
    try:
        # Hacer una llamada simple para verificar que el modelo existe
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": "test",
            "stream": False,
        }
        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=min(OLLAMA_TIMEOUT, 30),
        )
        
        if response.status_code == 200:
            print(f"  ✅ Modelo '{OLLAMA_MODEL}' está disponible")
            return True
        else:
            print(f"  ❌ Error al acceder al modelo: {response.status_code}")
            print(f"     Respuesta: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"  ❌ Timeout: El modelo tarda demasiado en responder")
        print(f"     Aumenta OLLAMA_TIMEOUT en config.py o usa un modelo más rápido")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def check_ollama_installed():
    """Verifica si Ollama está instalado."""
    print("🔍 Verificando si Ollama está instalado...")
    try:
        import subprocess
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  ✅ Ollama está instalado: {version}")
            return True
    except FileNotFoundError:
        print("  ❌ Ollama no está instalado o no está en PATH")
        print("  Descarga desde: https://ollama.ai")
        return False
    except Exception as e:
        print(f"  ❌ Error al verificar: {e}")
        return False


def list_available_models():
    """Lista los modelos disponibles localmente."""
    print("\n🔍 Modelos disponibles localmente:")
    try:
        import subprocess
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:  # Si hay más que el header
                for line in lines[1:]:
                    if line.strip():
                        print(f"  • {line}")
                return True
            else:
                print("  ℹ️  No hay modelos descargados")
                return False
    except FileNotFoundError:
        print("  ℹ️  No se puede ejecutar 'ollama list'")
        return False
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return False


def main():
    """Ejecuta todas las verificaciones."""
    print("╔════════════════════════════════════════════════════════╗")
    print("║     VERIFICACIÓN DE CONFIGURACIÓN DE OLLAMA            ║")
    print("╚════════════════════════════════════════════════════════╝\n")
    
    # Verificaciones básicas
    checks = {
        "Ollama instalado": check_ollama_installed,
        "Ollama ejecutándose": check_ollama_running,
        "Modelo disponible": check_model_available,
    }
    
    results = {}
    for check_name, check_func in checks.items():
        results[check_name] = check_func()
    
    # Lista de modelos disponibles
    list_available_models()
    
    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN:")
    print("=" * 60)
    
    all_passed = all(results.values())
    
    for check_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{check_name:<30} {status}")
    
    print("=" * 60)
    
    if all_passed:
        print("\n✅ ¡Listo! Tu configuración de Ollama está correcta.")
        print(f"\nPuedes ejecutar el proyecto con:")
        print(f"  python main.py")
        return 0
    else:
        print("\n❌ Hay problemas en tu configuración.")
        print("\nSoluciones comunes:")
        
        if not results.get("Ollama instalado"):
            print("  1. Instala Ollama: https://ollama.ai")
        
        if not results.get("Ollama ejecutándose"):
            print("  1. Ejecuta 'ollama serve' en otra terminal")
        
        if not results.get("Modelo disponible"):
            print("  1. Descarga un modelo: ollama pull mistral")
            print("  2. Verifica modelos disponibles: ollama list")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
