# 🐟 Algoritmo de Grupos Funcionales para ATLANTIS

**Algoritmo iterativo asistido por LLM para la creación y optimización de grupos funcionales en modelos ecosistémicos ATLANTIS.**

> Diseñado para el modelado del ecosistema del Golfo de California.

---

## Descripción

Este sistema automatiza la clasificación de especies marinas en **grupos funcionales** utilizando un modelo de lenguaje local (via Ollama) como motor de razonamiento ecológico. El algoritmo itera sobre las asignaciones hasta encontrar una configuración que:

- ✅ Maximice la inclusión de especies (mínimo sin grupo)
- ✅ Mantenga la diversidad representativa del ecosistema
- ✅ Cumpla con la restricción de **< 80 grupos**
- ✅ Jerarquice los grupos por importancia ecosistémica

## Arquitectura

```
main.py                    ← Pipeline principal
├── config.py              ← Configuración y parámetros
├── data_loader.py         ← Carga de datos (CSV/JSON)
├── llm_classifier.py      ← Interfaz con Ollama API
│   ├── classify_species_into_groups()
│   ├── create_groups_for_unassigned()
│   ├── evaluate_group_importance()
│   └── propose_group_merges()
├── scoring.py             ← Sistema de puntaje
│   ├── compute_quantitative_scores()
│   ├── compute_composite_score()
│   └── generate_score_report()
└── optimizer.py           ← Bucle iterativo de optimización
    └── run_optimization()
```

## Flujo del Algoritmo

```
┌─────────────────────────────────────────────────┐
│  1. Cargar especies y grupos existentes         │
└──────────────────────┬──────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────┐
│  2. LLM clasifica especies → grupos existentes  │◄─────┐
└──────────────────────┬──────────────────────────┘      │
                       ▼                                  │
┌─────────────────────────────────────────────────┐      │
│  3. LLM crea grupos para especies sin asignar   │      │
└──────────────────────┬──────────────────────────┘      │
                       ▼                                  │
┌─────────────────────────────────────────────────┐      │
│  4. Evaluar importancia (cuantitativa + LLM)    │      │
└──────────────────────┬──────────────────────────┘      │
                       ▼                                  │
┌─────────────────────────────────────────────────┐      │
│  5. ¿Grupos > 80?  → Fusionar/consolidar        │      │
└──────────────────────┬──────────────────────────┘      │
                       ▼                                  │
┌─────────────────────────────────────────────────┐      │
│  6. ¿Cobertura ≥ 95% y Grupos ≤ 80?            │      │
│     → SÍ: Fin ✅                                │      │
│     → NO: Iterar ───────────────────────────────┼──────┘
└─────────────────────────────────────────────────┘
```

## Instalación

### 1. Instalar Ollama

Ollama permite ejecutar modelos LLM localmente sin necesidad de API keys.

- **Linux/Mac:** Descargar desde https://ollama.ai
- **Windows:** Descargar desde https://ollama.ai

### 2. Descargar un modelo

```bash
# Recomendado: Mistral (buen equilibrio velocidad/calidad)
ollama pull mistral

# Alternativas:
ollama pull llama2
ollama pull neural-chat
ollama pull orca-mini
```

### 3. Ejecutar Ollama

En una terminal separada, mantén Ollama ejecutándose:

```bash
ollama serve
```

### 4. Instalar dependencias del proyecto

```bash
pip install -r requirements.txt
```

## Uso

> **Prerequisito:** Ollama debe estar ejecutándose (`ollama serve`) en otra terminal.

### Con LLM (requiere Ollama ejecutándose localmente)

```bash
# Usar modelo por defecto (mistral)
python main.py

# Usar modelo específico
OLLAMA_MODEL=llama2 python main.py
```

### 🧪 Testing Rápido

Antes de ejecutar main, valida que todo funciona:

```bash
# Suite automática de tests (RECOMENDADO)
./run_tests.sh

# O tests individuales
python check_ollama.py          # Verifica setup (5 seg)
python test_llm_integration.py  # Test LLM (30 seg)
python test_quick.py            # 300 especies (2-3 min)
```

Ver [TESTS_SUMMARY.md](TESTS_SUMMARY.md) para matriz de tests disponibles.

### Sin LLM (modo heurístico para testing)

```bash
python main.py --no-llm
```

### Con archivos personalizados

```bash
python main.py --species data/mis_especies.csv --groups data/mis_grupos.json
```

## Configuración de Ollama

Ver el archivo [OLLAMA_SETUP.md](OLLAMA_SETUP.md) para:
- Instrucciones detalladas de instalación
- Modelos recomendados
- Solución de problemas
- Configuración avanzada

Las variables de entorno se pueden establecer en `.env`:

```env
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=mistral
OLLAMA_TIMEOUT=300
```

Ver `.env.example` para más opciones.

## Formato de Datos

### CSV de especies (`data/species_occurrences.csv`)

| Columna | Descripción |
|---------|-------------|
| `species_name` | Nombre científico |
| `phylum` | Phylum taxonómico |
| `class` | Clase taxonómica |
| `order` | Orden taxonómico |
| `family` | Familia taxonómica |
| `habitat` | pelagic / benthic / demersal / coastal |
| `trophic_level` | carnivore / herbivore / omnivore / planktivore / filter_feeder / detritivore / primary_producer / mixotroph |
| `depth_range_m` | Rango de profundidad (e.g., "0-200") |
| `body_size_cm` | Tamaño corporal en cm |
| `commercial_importance` | high / medium / low / protected / ecological |

### JSON de grupos funcionales (`data/initial_groups.json`)

```json
[
  {
    "group_id": "FG01",
    "group_name": "Nombre del grupo",
    "description": "Descripción del rol funcional",
    "characteristics": {
      "habitat": "pelagic",
      "trophic_level": "planktivore",
      "size_class": "small",
      "taxonomic_affinity": "Clupeiformes"
    },
    "species": []
  }
]
```

## Criterios de Puntaje

| Criterio | Peso | Descripción |
|----------|------|-------------|
| Riqueza de especies | 20% | Número de especies en el grupo |
| Importancia trófica | 20% | Rol clave en la red alimentaria |
| Valor comercial | 15% | Importancia pesquera |
| Rol ecológico | 20% | Función ecosistémica |
| Estado de conservación | 10% | Presencia de especies protegidas |
| Unicidad | 15% | Singularidad del nicho funcional |

## Salidas

El algoritmo genera tres archivos en `output/`:

- **`optimized_groups.json`** — Configuración final de grupos funcionales con especies asignadas y puntajes
- **`score_report.txt`** — Reporte tabular de ranking de grupos por importancia
- **`optimization_history.json`** — Historial de métricas por iteración

## Configuración

Editar `config.py` para ajustar:

- `MAX_GROUPS = 80` — Límite máximo de grupos
- `MAX_ITERATIONS = 10` — Iteraciones del optimizador
- `TARGET_UNASSIGNED_RATIO = 0.05` — Objetivo de cobertura (95%)
- `LLM_TEMPERATURE = 0.3` — Temperatura del LLM
- `SCORING_CRITERIA` — Pesos de los criterios de evaluación

## Notas

- **Sin API keys:** El sistema usa Ollama (LLM local), sin dependencias de servicios en la nube
- **Privado:** Todos los datos permanecen en tu máquina
- **Flexible:** Puedes cambiar de modelo fácilmente (`ollama pull <modelo>`)
- **Económico:** Sin costos de API
- El modo heurístico funciona sin LLM, útil para testing y ajuste de parámetros
- Los datos de ejemplo incluyen ~60 especies del Golfo de California
- El algoritmo converge típicamente en 2-4 iteraciones

## Ventajas de Ollama sobre APIs en la nube

| Aspecto | Ollama | Servicios en la Nube |
|--------|--------|---------------------|
| **API Key** | ❌ No requiere | ✅ Requiere |
| **Privacidad** | ✅ Local | ❌ Datos en nube |
| **Costo** | ✅ Gratis | ⚠️ Por uso |
| **Latencia** | ✅ Muy baja | ⚠️ Depende de internet |
| **Offline** | ✅ Funciona | ❌ Requiere internet |
| **Modelos** | ✅ Múltiples | ⚠️ Limitados |
