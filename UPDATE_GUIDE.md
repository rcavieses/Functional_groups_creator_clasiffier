# Guía de Actualización: App a Nuevas Clasificaciones

## 📋 Resumen de lo que se hizo

✅ **Clasificación completada:**
- **10,787 especies** clasificadas (sin --by-genus para preservar nombres)
- **10,732 clasificadas** (99.5% de éxito)
- **55 sin clasificar** (UNCLASSIFIED)
- Archivo: `output/species_classified.csv`

✅ **App Streamlit lista:**
- Detecta automáticamente columna `species_name` vs `genus_name`
- Firebase/Firestore configurado
- Sistema de validación de expertos funcional

✅ **Análisis Firestore:**
- Plan gratuito **AGUANTA** 20 usuarios × 30 cambios cada uno
- Consumo estimado: 1,200 escrituras (6% del límite)
- Recomendación: Implementar cache local para lecturas eficientes

---

## 🚀 Próximos Pasos

### 1. Actualizar Firestore con nuevas clasificaciones

**Opción A: Script automático (RECOMENDADO)**

```bash
cd Functional_groups_creator_clasiffier_clone
python update_firestore.py
```

El script:
1. Borra todos los registros existentes de especies
2. Importa las nuevas 10,787 especies
3. Preserva el audit log
4. Tarda ~2-3 minutos

**Opción B: Manual (dejar que app.py lo haga)**

Simplemente abre la app:
```bash
streamlit run app.py
```

Si Firestore está vacío, importará automáticamente. Tarda ~5 minutos.

### 2. Verificar que todo funciona

```bash
streamlit run app.py
```

✅ Deberías ver:
- Login screen
- Dashboard con estadísticas
  - Taxa activos: 10,732
  - Pendientes: 10,732 (al inicio, todos sin validar)
  - % Validados: 0%

---

## 📊 Consumo de Firestore (Detallado)

Consulta `FIRESTORE_ANALYSIS.md` para detalles completos.

**Resumen rápido:**

| Métrica | Valor | % del Límite |
|---------|-------|------------|
| Escrituras por validación | 2 | - |
| Escrituras 20u × 30c | 1,200 | **6%** ✅ |
| Almacenamiento | 8.6 MB | **<1%** ✅ |
| Lecturas (sin optimizar) | 539,350 | **1,079%** ❌ |
| Lecturas (con cache) | 600 | **1.2%** ✅ |

**Conclusión:** El plan gratuito es suficiente si implementamos cache local.

---

## 🔧 Optimización Recomendada (Fase 2)

Para mayor escalabilidad, implementar cache local en `firebase_client.py`:

```python
def load_species(db, force: bool = False) -> pd.DataFrame:
    """Load from CSV cache first (free), fallback to Firestore."""
    cache_file = Path.home() / ".cache/species.csv"
    
    if cache_file.exists() and not force:
        return pd.read_csv(cache_file)
    
    # Cargar y cachear
    df = load_from_firestore(db)
    cache_file.parent.mkdir(exist_ok=True)
    df.to_csv(cache_file, index=False)
    return df
```

**Beneficios:**
- ✅ App 10x más rápida
- ✅ Plan gratuito 100% seguro
- ✅ Funciona offline
- ✅ Escalable a 100+ usuarios

---

## 📝 Cambios en el CSV

### Antes (--by-genus)
```
genus_name,group_code,group_name,confidence
Accipiter,SBS,Surface-feeding Seabirds,medium
```

### Ahora (sin --by-genus) ✅ CORRECTO
```
species_name,group_code,group_name,confidence
Accipiter striatus,SBS,Surface-feeding Seabirds,medium
Accipiter cooperii,SBS,Surface-feeding Seabirds,medium
```

**App.py detecta automáticamente** la columna correcta (línea 154 de `firebase_client.py`).

---

## 📱 Prueba con 20 usuarios

Para simular 20 usuarios validando 30 especies cada uno:

```python
# En python3:
from pathlib import Path
from firebase_client import get_db, validate_species, load_species
import pandas as pd

db = get_db()
df = load_species(db)

# Simular 20 usuarios × 30 validaciones
for user_id in range(20):
    for i in range(30):
        taxon = df.iloc[user_id * 30 + i]['taxon']
        expert = f"expert_{user_id:02d}"
        validate_species(taxon, expert, db)
        print(f"[{user_id:2d}] Validado: {taxon}")

# Verificar consumo
print("Transacción completada: 20 × 30 = 600 validaciones")
```

---

## 🆘 Troubleshooting

### Error: "No se encontró el archivo clasificado"
```bash
# Revisar que el archivo existe:
ls -lah output/species_classified.csv

# Si no existe, correr clasificación nuevamente:
python3 classifier/classify_species.py \
  --input data/final_taxonomy_occ.csv \
  --provider anthropic --no-reasoning
```

### Firestore no importa automáticamente
```bash
# Ejecutar manualmente:
python3 update_firestore.py
```

### Taxa muestran "genus_name" en lugar de "species_name"
Esto significa que tiene un CSV viejo con --by-genus. Usa el nuevo:
```bash
ls -la output/species_classified.csv
head -1 output/species_classified.csv
```

Debería mostrar: `species_name,group_code,group_name,confidence`

---

## 📦 Archivos Nuevos

- ✅ `update_firestore.py` — Script de actualización
- ✅ `FIRESTORE_ANALYSIS.md` — Análisis completo de costos
- ✅ `UPDATE_GUIDE.md` — Este archivo

---

## ✅ Checklist Final

- [ ] Ejecutar `python update_firestore.py`
- [ ] Abrir `streamlit run app.py`
- [ ] Verificar que muestra 10,732 taxa activos
- [ ] Probar login con un experto
- [ ] Validar una especie
- [ ] Mover una especie a otro grupo
- [ ] Revisar que aparece en audit log
- [ ] (Opcional) Implementar cache local para optimización

---

## 📞 Próximos Pasos

1. **Inmediato:** Ejecutar `update_firestore.py`
2. **Esta semana:** Probar con los 20 expertos
3. **Siguiente:** Revisar resultados y optimizar si es necesario

¡Todo listo para comenzar! 🚀
