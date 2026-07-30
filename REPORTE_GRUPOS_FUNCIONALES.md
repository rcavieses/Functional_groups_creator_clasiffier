# Reporte integrado: Revisión de grupos funcionales

**Fecha:** 2026-07-24
**Fuentes:** (A) 23 comentarios de expertos registrados el 2026-06-16 en `group_ratings`; (B) barrido taxonómico automatizado de las 10,757 especies activas en los 85 `current_code` de la tabla `species`; (C) 55 sugerencias de IA generadas y registradas en `ai_suggestions` el 2026-07-24 a partir de (B).

Este documento sustituye a los reportes previos `REPORTE_COMENTARIOS_EXPERTOS.md` y `REPORTE_BARRIDO_GRUPOS.md`, integrando ambos análisis y cruzando sus hallazgos.

---

## 1. Metodología

**Comentarios de expertos (A):** se extrajeron todos los comentarios con texto no vacío de `group_ratings`, y se verificó el estado *actual* de cada grupo mencionado contra la composición real de `species` (no solo lo que dice el nombre del grupo). No se encontraron registros en `ai_suggestion_comments` ni `ai_batch_comments` — ningún experto ha comentado todavía sobre los lotes de sugerencias de IA ya filed.

**Barrido taxonómico (B):** para cubrir los 85 grupos rápidamente se trabajó **por encima del nivel de especie** (agregando por reino/phylum/clase/orden):
1. Para cada grupo se calculó el reino (`kingdom`) dominante; si cubre ≥90% se buscan outliers de reino dentro del grupo.
2. Dentro de grupos dominados por Animalia, se calculó el phylum y (si cubre ≥70%) la clase dominante, para detectar contaminación de otro phylum/clase (p. ej. un reptil en un grupo de peces).
3. Los catch-all *por diseño* (multi-reino intencional: OBI, MA, PL, PS, ZM, PB, BB, SG, UNCLASSIFIED) se trataron aparte, cualitativamente.
4. Se cruzó género → grupo dominante en todo el dataset para sugerir destino de reasignación.

**Limitación:** ambos análisis dependen de columnas de taxonomía conocidas por ser ruidosas ([[taxonomy-columns-unreliable]] en memoria). No sustituyen una verificación experta especie por especie.

**Sugerencias generadas (C):** tras el barrido, se filed 55 sugerencias formales vía `create_ai_suggestion` (mismo mecanismo de consenso de 2 expertos que ya usa la app), cubriendo los 6 grupos de mayor contaminación confirmada.

---

## 2. Resumen ejecutivo

| Fuente | Hallazgo | Cifra |
|---|---|---|
| Comentarios de expertos | Ya resueltos por la reestructuración de grupos | 2 / 23 |
| Comentarios de expertos | Pendientes de acción de datos | 7 / 23 |
| Comentarios de expertos | Juicios cualitativos de manejo (no requieren corrección) | 14 / 23 |
| Barrido taxonómico | Grupos con contaminación significativa | 8 / 85 |
| Barrido taxonómico | Grupos con contaminación menor (mayormente ruido de etiqueta) | ~30 / 85 |
| Barrido taxonómico | Grupos limpios | ~38 / 85 |
| Barrido taxonómico | Catch-all por diseño (multi-reino intencional) | 9 / 85 |
| Sugerencias de IA | Generadas y `pending` de consenso el 2026-07-24 | 55 (7 lotes) |

---

## 3. Grupos donde comentario de experto y barrido taxonómico se cruzan

Esta es la sección de mayor valor: casos donde ambas fuentes de evidencia apuntan al mismo grupo, confirmándose o complementándose mutuamente.

### COR / CRO — Corvinas ✅ resuelto
**Comentario (Mariana Walther):** "pasar las corvinas a CRO, fue un error incluirlas aquí [Corals and Anemones]".
**Barrido:** COR hoy solo contiene *Cynoscion othonopterus* (1 especie), y CRO ("Drums and croakers") tiene 37 sciénidos separados — ambos grupos limpios y taxonómicamente consistentes.
**Estado:** el comentario ya fue atendido por la reestructuración posterior a junio. Sin acción pendiente.

### OPI — Other Pinnipeds 🔴 contaminación severa
**Comentario (Gabriela Cruz Piñón):** *Phoca vitulina* ya no es relevante; el lobo fino de Guadalupe es importante.
**Barrido:** *Phoca vitulina* efectivamente ya no está en el grupo. Pero solo 5 de 16 especies son pinnípedos reales — el resto son 8 serpientes, 1 murciélago, y 2 registros con bug de datos (`Castela peninsularis`→genus `Neogale`; `Martesia striata`→genus `Martes`).
**Estado:** **11 sugerencias de IA ya generadas** (10 `remove_species` + 1 `move_species` de *Martesia striata* → BIV), `pending` de consenso.

### BB — Benthic Bacteria 🔴 catch-all sin depurar
**Comentario (Leonardo Vazquez):** incluir bacterias de ventilas hidrotermales.
**Barrido:** el reino dominante de BB **no es Bacteria sino Fungi** (46%), con contaminación de patógenos humanos (*Clostridioides difficile*, *Blautia wexlerae* — microbioma intestinal).
**Estado:** ya existían 28 sugerencias de IA `pending` (categoría "Terrestres · Hongos y líquenes") de un barrido anterior. El comentario de agregar bacterias de ventilas **sigue sin atenderse** — es una tarea de *adición*, no de limpieza, y no se generaron sugerencias nuevas para ella en esta ronda.

### SPO — Sponges and Tunicates 🔴 contaminación menor + adición pendiente
**Comentario (Adrian Munguia Vega):** incluir corales blandos filtradores (Alcyonacea).
**Barrido:** ninguno de los 308 táxones actuales es Alcyonacea (el comentario sigue sin atenderse). Se encontró además un hongo real (*Trametes cinnabarina*) contaminando el grupo — hallazgo nuevo, no relacionado con el comentario.
**Estado:** **1 sugerencia de IA generada** (`remove_species` para el hongo). La adición de Alcyonacea sigue pendiente — requeriría una búsqueda dedicada de especies candidatas, no solo limpieza.

### TWH — Toothed Whales ✅ comentario resuelto, pero contaminación nueva sin atender
**Comentario (Gabriela Cruz Piñón):** Orca debería ser un grupo funcional aparte.
**Barrido:** confirmado — existe un grupo **ORC** dedicado con *Orcinus orca* ya separado (comentario ya resuelto). Pero el barrido encontró que TWH tiene contaminado *Lima lima*, que es un **bivalvo**, no un cetáceo.
**Estado:** ⚠️ **no se generó sugerencia para esto en la ronda de 55** — quedó fuera del alcance de los 7 lotes generados. Pendiente para una próxima ronda.

### OBI — Other Benthic Invertebrates ⚪ catch-all, en progreso
**Comentario (Adrian Munguia Vega):** crear un grupo funcional de infauna (nematodos, poliquetos, anfípodos).
**Barrido:** OBI es 73% Animalia (2,337 especies); ya se extrajeron poliquetos (→PWO, 29 sugerencias), cangrejos bentónicos (→BEC, 59) y una limpieza de gasterópodos (→GAS, 18) en rondas anteriores, todas `pending` de consenso.
**Estado:** en progreso, pero no existe todavía un grupo "infauna" dedicado como tal — el comentario original pide una categoría nueva, no solo depuración del catch-all.

### SNA — Snappers 🟡 comentario pendiente, sin problema de datos
**Comentario (Frida Cisneros Soberanis):** separar *Lutjanus peru* por manejo pesquero.
**Barrido:** sin contaminación real — la única "anomalía" detectada es una inconsistencia de etiqueta (Actinopterygii vs Actinopteri) sin significado biológico.
**Estado:** este es un comentario de *reestructuración de manejo*, no de limpieza taxonómica — requeriría crear una subdivisión nueva (p. ej. usar el grupo "Small snappers"/OSN ya definido en `data/functional_groups_final.csv` pero no usado), no una sugerencia de `remove_species`/`move_species`.

### BIV — Bivalves 🟡 comentario pendiente + contaminación menor
**Comentario (Mariana Walther Mendoza):** separar ostión japonés (introducida) de especies nativas.
**Barrido:** contaminación mínima (1 gasterópodo *Gemma gemma*, 1 quitón mal etiquetado) — no relacionada con el comentario. El comentario en sí requiere una clasificación nativa/introducida que no existe hoy en las columnas de la BD.
**Estado:** sin acción — requiere trabajo de investigación adicional (determinar origen nativo/introducido por especie) antes de poder generar sugerencias.

---

## 4. Comentarios de expertos sin correlato en el barrido taxonómico

Estos son juicios de manejo pesquero/ecológico sobre la importancia relativa de un grupo — el barrido taxonómico no aplica porque no son errores de clasificación:

BIL, LRA, OCT (comentario de importancia pesquera — no confundir con el hallazgo de contaminación de OCT en la sección 5, que es un tema distinto), BSH, MA, HHS, RPL, RPI, OSP, LCS, ZS, BPI (comentario de abundancia — no confundir con el hallazgo de contaminación en sección 5).

> Nota sobre HHS: el comentario de James Ketchum (agregar *S. corona*, *S. tiburo*, *S. media*) es potencialmente accionable pero no se verificó en ninguno de los dos análisis — requiere una búsqueda taxonómica dedicada, similar al barrido terrestre ya hecho.

---

## 5. Otros hallazgos del barrido taxonómico (sin comentario de experto asociado)

### 🔴 Contaminación significativa, ya convertida en sugerencias de IA

| Grupo | Hallazgo | Sugerencias generadas |
|---|---|---|
| SBS (Surface-feeding Seabirds, 641 especies) | ~20 registros de fauna terrestre: murciélagos, mariposas, un zorrillo, una gallina, jilgueros (*Spinus*) y cuervos (*Corvus*) — estos últimos dos son los homónimos terrestres que memoria dejaba como "seguimiento abierto" del barrido terrestre anterior | 20 `remove_species` |
| ODF (Other Demersal Fish, 176 especies) | 13 registros terrestres: lagartijas cornudas (*Phrynosoma*), víboras (*Pituophis*), mariposas, y plantas (*Cyrtocarpa*, *Phragmites*) | 13 `remove_species` |
| OCT (Octopus, 20 especies) | 7 especies son en realidad gasterópodos (*Aplysia* — liebres de mar —, y un nudibranquio) | 7 `move_species` → GAS |
| BPI (Benthic Piscivores, 47 especies) | Un cuervo (*Corvus sp.*) y una boa de arena (*Lichanura trivirgata*) | 2 `remove_species` |
| PSH (Pelagic Sharks, 11 especies) | Una serpiente marina (*Hydrophis platurus*) | 1 `remove_species` |

**Total generado en esta ronda: 55 sugerencias** (ver también OPI y SPO en la sección 3).

### 🟡 Contaminación menor detectada pero no accionada (candidatos a próxima ronda)

| Grupo | Hallazgo |
|---|---|
| TWH (Toothed Whales) | *Lima lima* (un bivalvo) mezclado con cetáceos — ver sección 3 |
| BIV | *Gemma gemma* (gasterópodo), 1 quitón mal etiquetado |
| CNA (Corals/Anemones) | Varios hidrozoos — parientes de Cnidaria, discutible si pertenecen aquí o a JE/ZM |
| JE (Jellyfish) | *Physalia physalis* y *Obelia geniculata* con columnas de taxonomía corruptas (ruido, no error de grupo) |
| ZL (Large Zooplankton) | 1 mislabel de *Porpita porpita* |
| SBD (Diving Seabirds) | 1 murciélago (*Glossophaga mutica*) entre 70 aves |
| GAS (Gastropods) | Contaminación mínima, mayormente ruido de etiquetas (97% consistente) |
| CRO, RCA, RPI, RHE, FLA, LAN, CPL, NEE, MUL, OGR, OTU, LAM, PAR, LIZ, MEE, BIL, LCS, SCS, LRA, SRA, SKA, GUI, BST, SST | Solo diferencias de orden/clase entre peces o equinodermos — mayormente ruido de etiqueta (Actinopterygii/Actinopteri), no errores reales |

### 🟢 Grupos limpios

BEC, BST, BWH, CSL, DOL, DPF, GWS, HAK, HHS, JSQ, LOB, MAC, ORC, OSH, OSQ, SAR, SCU, SEU, SKJ, SWC, TGR, THR, TLB, TLH, TOR, TOT, VAQ, YFT, y todos los grupos de 1 especie — sin outliers detectados.

### ⚪ Catch-all por diseño

| Grupo | n | Reino dominante | % | Nota |
|---|---|---|---|---|
| OBI | 2337 | Animalia | 73% | ver sección 3 |
| MA | 1166 | Plantae | 95% | ya mayormente depurado por el barrido terrestre anterior |
| PL | 1133 | Chromista | 100% | limpio |
| ZM | 673 | Chromista | 60% | mezcla esperada para zooplancton pequeño |
| UNCLASSIFIED | 455 | Plantae | 70% | **grupo no barrido todavía** por el proceso terrestre previo — candidato a revisión dedicada |
| PS | 174 | Chromista | 57% | mezcla esperada para fitoplancton pequeño |
| PB | 134 | Bacteria | 39% | dominancia baja, mismo patrón que BB — candidato a revisión |
| BB | 63 | Fungi | 46% | ver sección 3 |
| SG | 126 | Plantae | 99% | limpio |

---

## 6. Bug de datos detectado (transversal, no ligado a un solo grupo)

Durante la generación de sugerencias se identificó un patrón recurrente: el campo `genus` de algunos registros quedó enlazado a un género **textualmente similar pero taxonómicamente no relacionado**, probablemente por un fuzzy-match roto en el pipeline de importación:

- `Martesia (martesia) striata` (almeja marina real) → genus `Martes` (marta)
- `Castela peninsularis` (arbusto terrestre) → genus `Neogale` (visón)
- `Corvus sp.` (cuervo) → genus `Cottus` (pez escultura)
- `Caranx caninus`, `Caranx vinctus` (peces jurel reales, correctamente ubicados en ODF) → genus `Cajanus`/`Carex` (plantas)

En los dos últimos casos el taxón en sí es correcto y permanece en su grupo — **no se generó sugerencia** porque el error está solo en la columna de metadatos, no en la asignación de grupo. Vale la pena que alguien con acceso al pipeline de importación (`add_taxonomy_columns.py` u otro script de enriquecimiento) revise si este problema afecta más registros de forma sistemática.

---

## 7. Recomendaciones priorizadas

1. **Revisar y votar** las 55 sugerencias `pending` generadas el 2026-07-24 en `pages/5_Validación_de_IA.py` (categorías OPI, SBS, ODF, OCT, BPI, PSH, SPO).
2. **Generar sugerencias para TWH** (*Lima lima*) — quedó fuera de la ronda anterior.
3. **UNCLASSIFIED (455 especies)** es el catch-all más grande sin depurar todavía — aplicar el mismo barrido terrestre que ya se hizo para OBI/MA/PL.
4. **PB (Pelagic Bacteria)** tiene dominancia de reino muy baja (39%), igual que BB — mismo tratamiento pendiente.
5. **Investigar el bug de fuzzy-match de género** (sección 6) en el pipeline de importación taxonómica.
6. **Tareas de adición** (no de limpieza) que siguen abiertas: agregar Alcyonacea a SPO, agregar bacterias de ventilas a BB, agregar las 3 especies de tiburón martillo faltantes a HHS, y decidir cómo tratar los comentarios de reestructuración de manejo (SNA/*Lutjanus peru*, BIV nativo/introducido, OBI/infauna).
