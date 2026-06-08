# Configuración de Ollama para el Proyecto ATLANTIS

## Overview

Este proyecto utiliza **Ollama** para ejecutar modelos LLM localmente. No requiere API keys ni conexiones a servicios en la nube.

**Ventajas de Ollama:**
- ✅ Funciona completamente local (sin dependencias de internet)
- ✅ Sin costos de API
- ✅ Privacidad: los datos no salen de tu máquina
- ✅ Rápido y flexible
- ✅ Soporta múltiples modelos

---

## 1. Instalación de Ollama

### Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### macOS
Descarga el instalador desde: https://ollama.ai/download

### Windows
Descarga el instalador desde: https://ollama.ai/download

---

## 2. Descargar un Modelo

Una vez instalado Ollama, descarga un modelo:

### Modelos Recomendados (ordenados por velocidad):

```bash
# nous-hermes2 7B (⭐ RECOMENDADO: Más rápido, buena calidad)
ollama pull nous-hermes2

# Mistral 7B (Buena velocidad y calidad, si nous-hermes2 es lento)
ollama pull mistral

# Neural Chat (Optimizado para chat, rápido)
ollama pull neural-chat

# Orca Mini (Muy rápido, requiere menos recursos)
ollama pull orca-mini
```

### Modelos Alternativos:

```bash
# Llama 2 (Versión de Meta, buen desempeño)
ollama pull llama2

# Zephyr (Basado en Mistral, buena calidad)
ollama pull zephyr

# Dolphin (Diversidad de respuestas)
ollama pull dolphin-mixtral
```

Para ver todos los modelos disponibles: https://ollama.ai/tags

---

## 3. Ejecutar Ollama

En una terminal, inicia el servidor de Ollama:

```bash
ollama serve
```

Verás un output como:
```
2024/01/15 10:30:45 Listening on 127.0.0.1:11434
```

**Nota:** Deja esta terminal ejecutándose mientras uses el proyecto.

---

## 4. Configurar el Proyecto

### Opción A: Usar variables de entorno (Recomendado)

Crea un archivo `.env` en el directorio raíz del proyecto:

```bash
.env
```

Contenido del `.env`:

```env
# Configuración de Ollama
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=nous-hermes2
```

**Modelos disponibles para usar:**
- `nous-hermes2` ⭐ (recomendado, más rápido)
- `mistral`
- `llama2`
- `neural-chat`
- `orca-mini`
- `zephyr`
- Cualquier otro modelo que hayas descargado

### Opción B: Cambiar modelo sin reiniciar

```bash
# Usar Llama2 en lugar de nous-hermes2
OLLAMA_MODEL=llama2 python main.py

# Usar otro modelo
OLLAMA_MODEL=mistral python main.py
```

---

## 5. Instalar Dependencias Python

```bash
pip install -r requirements.txt
```

---

## 6. Ejecutar el Proyecto

```bash
# Con LLM (requiere que Ollama esté ejecutándose)
python main.py

# Sin LLM (solo heurísticas, para testing)
python main.py --no-llm

# Con modelo específico
OLLAMA_MODEL=llama2 python main.py
```

---

## Troubleshooting

### Error: "No se pudo conectar a Ollama"

**Solución:**
1. Verifica que Ollama está ejecutándose: `ollama serve`
2. Verifica la URL: por defecto es `http://localhost:11434`
3. Asegúrate de tener un modelo descargado: `ollama list`

### Error: "Timeout esperando respuesta"

**Soluciones:**
1. El modelo es demasiado lento para tu hardware
2. Intenta con un modelo más pequeño: `ollama pull orca-mini`
3. Aumenta el timeout en `config.py`: `OLLAMA_TIMEOUT = 600`

### Bajo desempeño / Respuestas lentas

**Soluciones optimización:**
1. Usa modelos más pequeños (orca-mini, neural-chat)
2. Verifica que no haya otros procesos intensivos
3. Si tienes GPU: asegúrate que Ollama puede acceder a ella
4. Aumenta la RAM disponible si es posible

### Como verificar modelos descargados

```bash
ollama list
```

---

## Características del Proyecto con Ollama

El proyecto ahora:

1. **No requiere API keys** - Funciona completamente local
2. **Es privado** - Todos los datos permanecen en tu máquina
3. **Es flexible** - Puedes cambiar de modelo fácilmente
4. **Es económico** - Sin costos de API

---

## Referencia Rápida

```bash
# Descargar un modelo
ollama pull mistral

# Ver modelos instalados
ollama list

# Ejecutar el servidor
ollama serve

# Ejecutar el proyecto
python main.py

# Ejecutar sin LLM (testing)
python main.py --no-llm

# Ver/cambiar configuración
cat config.py  # Busca sección "OLLAMA"
```

---

## Próximos Pasos

1. ✅ Instala Ollama
2. ✅ Descarga un modelo (`ollama pull mistral`)
3. ✅ Ejecuta Ollama (`ollama serve`)
4. ✅ Instala dependencias (`pip install -r requirements.txt`)
5. ✅ Ejecuta el proyecto (`python main.py`)

¡Listo! El proyecto debería funcionar completamente local y privado.
