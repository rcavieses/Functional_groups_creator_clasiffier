# 🚀 Quick Start - Ollama Local LLM

## En 5 minutos: Instala y ejecuta

### 1️⃣ Instala Ollama (2 min)
```bash
# Descarga desde https://ollama.ai
# Ejecuta el instalador
```

### 2️⃣ Descarga un modelo (2 min)
```bash
ollama pull mistral
```

### 3️⃣ Ejecuta Ollama en una terminal
```bash
ollama serve
# Output: Listening on 127.0.0.1:11434
```

### 4️⃣ En otra terminal, instala dependencias
```bash
pip install -r requirements.txt
```

### 5️⃣ Valida tu setup (30 segundos)
```bash
# Opción A: Suite automática (RECOMENDADO)
./run_tests.sh

# Opción B: Test individual
python check_ollama.py
```

Si ves "✅ Todos OK" o similar - ¡el setup está correcto!

### 6️⃣ Test de integración LLM (~30 segundos)
```bash
python test_llm_integration.py
```

Si los 4 tests pasan - ¡el LLM está listo!

### 7️⃣ ¡Ejecuta el proyecto!
```bash
python main.py
```

---

## 🧪 Otros tests disponibles

```bash
# Suite automática completa (check + integración + optional quick)
./run_tests.sh

# Test rápido con 300 especies (2-3 min)
python test_quick.py

# Test completo con todas las especies
python main.py

# Ver matriz de todos los tests disponibles
cat TESTS_SUMMARY.md
```

---

## Comandos útiles

```bash
# Ver modelos instalados
ollama list

# Descargar otro modelo
ollama pull llama2
ollama pull neural-chat
ollama pull orca-mini

# Ejecutar con modelo específico
OLLAMA_MODEL=llama2 python main.py

# Ejecutar sin LLM (testing rápido)
python main.py --no-llm
```

---

## Si algo no funciona

```bash
# Verificar que Ollama está ejecutándose
ps aux | grep ollama

# Ver logs de Ollama
# Revisa la ventana de terminal donde ejecutaste "ollama serve"

# Reiniciar Ollama
# Detén (Ctrl+C) y vuelve a ejecutar: ollama serve
```

---

## ¿Prefieres más detalles?

Ver los otros documentos:
- **TESTING.md** - Guía completa de tests
- **OLLAMA_SETUP.md** - Guía completa con troubleshooting
- **MIGRATION_OLLAMA.md** - Qué cambió en la migración
- **README.md** - Documentación del proyecto completa

---

**¡Disfruta de LLMs locales sin API keys! 🎉**
