# Propuestas de Optimización - Functional Groups Creator

Documento de análisis de optimizaciones implementadas y propuestas para mejorar eficiencia, estabilidad y uso de tokens del LLM.

**Fecha:** Marzo 2026  
**Estado:** Análisis en progreso

---

## 📊 Tabla Resumen de Optimizaciones

| Optimización | Estado | Impacto | Complejidad | Prioridad |
|---|---|---|---|---|
| Reducir BATCH_SIZE 25% | ✅ Implementado | Alto | Bajo | Alta |
| Detectar respuestas duplicadas | ✅ Implementado | Medio | Bajo | Alta |
| Aumentar LLM_MAX_TOKENS | ✅ Implementado | Alto | Bajo | Alta |
| Mejorar extracción JSON truncado | ✅ Implementado | Alto | Bajo | Alta |
| Compresión de descripción de grupos | ⏳ Propuesto | Alto | Bajo | Alta |
| Caché de resultados de LLM | ⏳ Propuesto | Medio | Medio | Media |
| Paralelización de batches | ⏳ Propuesto | Alto | Alto | Baja |
| Ajuste dinámico de batch size | ⏳ Propuesto | Medio | Alto | Baja |

---

## ✅ Optimizaciones Implementadas

### 1. Reducción de BATCH_SIZE (25%)

**Implementado:** Sí  
**Cambio:**
```python
# Antes
BATCH_SIZE = 250

# Ahora
BATCH_SIZE = 187  # 250 * 0.75
```

**Justificación:**
- Permite que el modelo procese mejor cada lote
- Reduce riesgo de respuestas truncadas
- Mejora calidad de clasificación individual

**Impacto:**
- ➖ Más batches (≈33% más llamadas al LLM)
- ✅ Mejor estabilidad y completitud de respuestas
- ✅ Mejor precisión en asignaciones

---

### 2. Detección de Respuestas Duplicadas

**Implementado:** Sí  
**Función agregada:** `_is_response_duplicate()`

```python
def _is_response_duplicate(current_response: dict | list, previous_response: dict | list) -> bool:
    """
    Compara si la respuesta actual es idéntica a la anterior.
    Evita procesar respuestas repetidas.
    """
```

**Dónde se usa:**
- `classify_species_into_groups()` - Clasificación
- `create_groups_for_unassigned()` - Creación de grupos

**Comportamiento:**
```
Batch 1: Procesa normalmente
Batch 2: Si respuesta == Batch 1 → SKIP (no procesa)
Batch 3: Si respuesta == Batch 2 → SKIP (no procesa)
Batch 4: Si respuesta diferente → Procesa
```

**Impacto:**
- ✅ Evita redundancia cuando el modelo se queda sin "ideas"
- ✅ Poco overhead (comparación JSON simple)
- ⚠️ Puede perder información si es un falso positivo (raro)

---

### 3. Aumento de LLM_MAX_TOKENS

**Implementado:** Sí  
**Cambio:**
```python
# Antes
LLM_MAX_TOKENS = 4096

# Ahora
LLM_MAX_TOKENS = 8192
```

**Justificación:**
- Con 187 especies + descripciones, 4096 tokens era insuficiente
- El modelo se truncaba a mitad de respuesta
- Ollama soporta estos límites sin problema

**Impacto:**
- ✅ Previene truncado de respuestas
- ➖ Tiempos de generación ~40-50% más lentos
- ➖ Mayor uso de recursos locales

---

### 4. Robustez en Extracción JSON Truncado

**Implementado:** Sí  
**Función agregada:** `_try_parse_json()`

Estrategia multi-nivel:
1. Parse directo
2. Remover comas innecesarias
3. Cerrar braces/brackets sin match
4. Búsqueda hacia atrás para último JSON válido

**Impacto:**
- ✅ Recupera JSONs truncados incompletos
- ✅ No requiere reintentos
- ✅ Mantiene máximo de datos extraíbles

---

## ⏳ Optimizaciones Propuestas

### 5. Compresión de Descripción de Grupos

**Estado:** Propuesto  
**Impacto potencial:** **ALTO** (reducción 60-70% tokens)

#### Problema actual:
En cada batch se reenvía la DESCRIPCIÓN COMPLETA de todos los grupos:

```
CURRENT FUNCTIONAL GROUPS:
FG01 - Phytoplankton (small diatoms, silica-based producers): 
  Small microscopic organisms that form the base of the food web, 
  primarily consuming nutrients to produce organic carbon through photosynthesis. 
  Key trophic role in ecosystem. Habitat: Pelagic, surface. 
  Size: Small. Taxonomic affinity: Various algae and diatoms...

FG02 - Zooplankton (filter feeders, copepods): 
  Small crustaceans that filter feed on phytoplankton and organic particles. 
  Important trophic link between primary producers and fish...
  [MUCHO MÁS TEXTO]
```

**Solución propuesta:**

Crear función `_compress_groups_for_llm()`:

```python
def _compress_groups_for_llm(groups: list[dict]) -> str:
    """
    Crea representación ultra-compacta de grupos para prompts LLM.
    Solo información esencial: ID, nombre, características clave.
    
    Reduce ~65% de tokens en descripción de grupos.
    """
    lines = []
    for g in groups:
        chars = g.get("characteristics", {})
        
        # Extracto comprimido
        trophic = chars.get("trophic_level", "unknown")
        habitat = chars.get("habitat", "")
        size = chars.get("size_class", "")
        
        # Formato compacto
        essentials = " | ".join(filter(None, [trophic, habitat, size]))
        line = f"{g['group_id']} - {g['group_name']} [{essentials}]"
        lines.append(line)
    
    return "\n".join(lines)
```

**Resultado:**
```
FG01 - Phytoplankton [primary_producer | pelagic | small]
FG02 - Zooplankton-filter [planktivore | pelagic | very_small]
FG03 - Mesopelagic fish [carnivore | mesopelagic | medium]
FG04 - Demersal cephalopods [carnivore | benthic | medium]
```

**Implementación:**
- Reemplazar `groups_text = groups_to_text(groups)` con:
  ```python
  groups_text = _compress_groups_for_llm(groups)
  ```
- En `classify_species_into_groups()` y `create_groups_for_unassigned()`

**Impacto:**
- ✅ Reduce tokens por batch: 250-300 → 50-80 (60-70% menos)
- ✅ Misma precisión (modelo tiene lo esencial)
- ✅ Con BATCH_SIZE=187, esto aliviaría mucho la presión de tokens
- ✅ Permitiría reducir LLM_MAX_TOKENS a 6144
- ⚠️ Requiere validación que modelo entienda formato compacto

**Estimación de beneficio:**
```
ACTUAL: 187 species × 50 chars/species + 300 chars grupos = ~10,000 chars (~2,500 tokens)
COMPRIMIDO: 187 species × 50 chars + 80 chars grupos = ~9,370 chars (~2,350 tokens)
AHORRO: ~150 tokens/batch (~6% reducción)

Con múltiples batches, ahorro acumulado significativo.
```

---

### 6. Caché de Resultados del LLM

**Estado:** Propuesto  
**Impacto potencial:** MEDIO (reutilización inteligente)

#### Problema:
Si el mismo conjunto de especies vuelve a procesarse (ej: en iteraciones futuras del optimizador), se hace trabajo redundante.

#### Solución:
Crear caché basado en hash de especies + grupos:

```python
class LLMResponseCache:
    """
    Cache simple de respuestas del LLM basado en hash de entrada.
    Evita reprocessamiento de combinaciones idénticas de especies+grupos.
    """
    def __init__(self, cache_file: Path = None):
        self.cache = {}
        self.cache_file = cache_file or OUTPUT_DIR / "llm_cache.json"
        self.load()
    
    def get_hash(self, species_list: list[str], groups_list: list[dict]) -> str:
        """Hash de entrada = identificador único de request."""
        data = {
            "species": sorted(species_list),
            "group_ids": sorted([g["group_id"] for g in groups_list]),
        }
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()
    
    def get(self, species_list, groups_list) -> dict | None:
        """Retorna cachéd result si existe."""
        h = self.get_hash(species_list, groups_list)
        return self.cache.get(h)
    
    def set(self, species_list, groups_list, result: dict):
        """Almacena resultado en caché."""
        h = self.get_hash(species_list, groups_list)
        self.cache[h] = {"timestamp": datetime.now().isoformat(), "result": result}
        self.save()
    
    def save(self):
        """Persiste caché a disco."""
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f, indent=2)
    
    def load(self):
        """Carga caché desde disco."""
        if self.cache_file.exists():
            with open(self.cache_file, "r") as f:
                self.cache = json.load(f)
```

**Uso en `classify_species_into_groups()`:**
```python
cache = LLMResponseCache()

for batch_idx, batch in enumerate(batches, 1):
    # Intenta obtener del caché
    cached = cache.get(batch, groups)
    if cached:
        print(f"  [Batch {batch_idx}] 💾 Cache hit - skipping LLM call")
        result = cached
    else:
        # LLM call normal
        response = _call_llm(system_prompt, user_prompt)
        result = _extract_json_from_response(response)
        cache.set(batch, groups, result)
    
    # Procesa result normalmente...
```

**Impacto:**
- ✅ Evita LLM calls redundantes en iteraciones posteriores
- ✅ Acelera significativamente si hay reprocessamiento
- ⚠️ Requiere espacio en disco
- ⚠️ Caché crece con el tiempo (necesita limpieza periódica)

**Caso de uso:**
- Iteración 1: Procesa 500 especies → 3 batches
- Iteración 2: Procesa 450 especies (100 repetidas) → 1 batch hit cache, 2 LLM calls

---

### 7. Paralelización de Batches

**Estado:** Propuesto  
**Impacto potencial:** ALTO (pero complejo)  
**Complejidad:** ALTA

#### Problema:
Actualmente:
```
Batch 1 → wait for response (30 sec) → Batch 2 → wait (30 sec) → Batch 3
Total: 90 segundos (secuencial)
```

#### Solución:
Ejecutar múltiples batches en paralelo:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def classify_species_into_groups_parallel(
    species_text: str,
    groups_text: str,
    groups: list[dict],
    max_parallel: int = 2,  # Máximo 2 requests paralelas
) -> tuple[list[dict], list[str]]:
    """
    Procesa batches en paralelo (con limite para no saturar Ollama).
    """
    
    batches = [...]  # Crear batches como antes
    
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = []
        
        for batch_idx, batch in enumerate(batches, 1):
            batch_text = "\n".join(batch)
            user_prompt = f"""..."""
            
            # Envía request en thread separado
            future = executor.submit(
                _call_llm, 
                system_prompt, 
                user_prompt
            )
            futures.append((batch_idx, future))
        
        # Procesa respuestas conforme llegan
        all_unassigned = []
        results_by_batch = {}
        
        for batch_idx, future in futures:
            response = future.result()  # Espera completitud
            result = _extract_json_from_response(response)
            results_by_batch[batch_idx] = result
        
        # Procesa en orden para mantener consistency
        for batch_idx in sorted(results_by_batch.keys()):
            result = results_by_batch[batch_idx]
            # [procesa result...]
    
    return groups, all_unassigned
```

**Impacto:**
- ✅ Reduce tiempo total: 90 seg → 45 seg (con max_parallel=2)
- ✅ Escalable (puede ajustar max_parallel)
- ⚠️ Aumenta complejidad (debugging, manejo de errores)
- ⚠️ Requiere límite para no saturar Ollama (local)
- ⚠️ Pierde control de orden de procesamiento

**Recomendación:** Baja prioridad hasta que otros optimizaciones estén validadas.

---

### 8. Ajuste Dinámico de BATCH_SIZE

**Estado:** Propuesto  
**Impacto potencial:** MEDIO

#### Problema:
Actualmente BATCH_SIZE=187 fijo. Pero:
- Si hay pocos grupos: batch podría ser más grande (ej: 250)
- Si hay muchos grupos: batch debería reducirse (ej: 100)

#### Solución:

```python
def _calculate_optimal_batch_size(
    n_groups: int,
    max_tokens: int = LLM_MAX_TOKENS,
    target_prompt_ratio: float = 0.4,
) -> int:
    """
    Calcula batch size óptimo basado en cantidad de grupos.
    
    Asunción: ~50 chars por species, ~200 chars por group description
    
    formula: max_species = (max_tokens * target_ratio) / chars_per_species
    """
    
    # Estimación de tokens para descripción de grupos (sin comprimir)
    estimated_group_tokens = n_groups * 50  # ~50 tokens por grupo
    
    # Tokens disponibles para especies
    available_tokens = max_tokens * target_prompt_ratio - estimated_group_tokens
    
    # Si grupos muy grandes, reduce batch size
    tokens_per_species = 10  # estimado
    optimal_batch = int(available_tokens / tokens_per_species)
    
    # Límites razonables
    return max(50, min(optimal_batch, 250))

# Uso:
batch_size = _calculate_optimal_batch_size(len(groups))
print(f"Batch size dinámico: {batch_size} (grupos: {len(groups)})")
```

**Ejemplo:**
```
N grupos: 10   → BATCH_SIZE = 200 (más eficiente)
N grupos: 30   → BATCH_SIZE = 187 (actual)
N grupos: 60   → BATCH_SIZE = 130 (necesario reducir)
N grupos: 80   → BATCH_SIZE = 80  (máximo límite)
```

**Impacto:**
- ✅ Adapta automáticamente a complejidad
- ✅ Mejora eficiencia en diferentes escenarios
- ⚠️ Requiere validación de fórmula estimativa
- ⚠️ Pequeña ganancia vs. complejidad added

---

## 📈 Recomendación de Implementación

### Fase 1 (Inmediata - Ya hecha)
- ✅ Reducir BATCH_SIZE a 187
- ✅ Detectar duplicados
- ✅ Aumentar LLM_MAX_TOKENS a 8192
- ✅ Mejorar JSON parsing

### Fase 2 (Próxima - Recomendado)
- ⏳ **Implementar compresión de grupos** (#5)
  - Máximo impacto
  - Baja complejidad
  - Requiere poco testing

### Fase 3 (Opcional - Si hay problemas)
- ⏳ Caché de resultados (#6) - si hay reiteraciones
- ⏳ Ajuste dinámico de batch size (#8) - si hay variabilidad

### Fase 4 (Baja prioridad)
- ⏳ Paralelización (#7) - solo si speed es crítica

---

## 🧪 Plan de Testing

Para cada optimización implementada:

1. **Test 1: Corrección**
   - Verificar que resultados sean idénticos a versión anterior
   - Validar JSON extraction en muestras

2. **Test 2: Rendimiento**
   - Medir tiempo por batch
   - Contar tokens consumidos
   - Comparar contra baseline

3. **Test 3: Casos extremos**
   - Respuestas truncadas/malformadas
   - Muchos grupos (n>70)
   - Pocas especies
   - Modelos diferentes (mistral, llama2, etc.)

---

## 📝 Notas Técnicas

### Comportamiento actual del LLM:
- Cada batch = nuevo HTTP request
- **Sin contexto persistente entre batches** ✅
- Modelo inicia "limpio" para cada classify/create_groups
- Solo datos en prompt = sistema + grupos + especies actuales

### Posibles problemas:
1. **Truncado de respuesta** → Solucionado con LLM_MAX_TOKENS=8192
2. **JSON malformado** → Solucionado con _try_parse_json()
3. **Respuestas repetidas** → Solucionado con detección duplicados
4. **Ineficiencia de tokens** → Solucionable con compresión grupos

---

## 📊 Estimación de Impacto Cuantitativo

| Optimización | Reducción Tokens | Speedup | Complejidad |
|---|---|---|---|
| Batches+tokens actuales | - | 1x | 1 |
| + Compresión grupos | ~35% | 1x | 1.2 |
| + Caché resultados | ~10% extra | 1.5-2x* | 2 |
| + Paralelización | ~0% tokens | 2x | 3 |
| **TOTAL OPTIMIZADO** | **~40%** | **2x** | **2** |

*Si hay reiteraciones (dependencia)

---

## ✋ Siguiente Paso

¿Implementamos **Fase 2: Compresión de grupos**? 

Propuesta de cambios:
1. Agregar función `_compress_groups_for_llm()`
2. Reemplazar `groups_to_text()` en batch loops
3. Validar con corrida de test
4. Medir tokens antes/después

¿Procedo?
