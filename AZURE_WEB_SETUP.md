# 🌐 Setup Web en Azure VM — Plan B

## Resumen Ejecutivo

Montar la app en Azure para que 20 expertos accedan vía navegador en lugar de ejecución local.

**Ventajas:**
- ✅ Usuarios solo necesitan navegador (no Python)
- ✅ Una sola app corriendo (datos centralizados)
- ✅ Fácil de compartir URL
- ✅ Perfecto para uso temporal (2-3 horas)

**Desventajas:**
- ⚠️ Requiere abrir puertos en Azure
- ⚠️ No es para producción (sin HTTPS, sin auth)
- ⚠️ Performance depende de ancho de banda

---

## ⚙️ Paso 1: Prerequisitos

✅ Tenemos:
- VM de Azure: `4.151.89.10`
- App Streamlit: `/home/atlantis/Functional_groups_creator_clasiffier_clone/app.py`
- Python + dependencias: ya instaladas
- Firestore: ya actualizado con 10,787 especies

---

## 🔧 Paso 2: Preparar la App

### 2.1 Hacer el script ejecutable

```bash
cd Functional_groups_creator_clasiffier_clone
chmod +x start_web_app.sh
```

### 2.2 Verificar que Firestore está actualizado

```bash
# Debe tener 10,787 especies
python3 << 'EOF'
from firebase_client import get_db, load_species
db = get_db()
df = load_species(db, force=True)
print(f"Especies en Firestore: {len(df):,}")
print(f"Estado: {'✅ LISTO' if len(df) > 10000 else '❌ FALTAN DATOS'}")
EOF
```

---

## 🚀 Paso 3: Iniciar la App

```bash
./start_web_app.sh
```

**Debería ver:**
```
✅ App iniciada (PID: xxxxx)
📊 App está ejecutándose

🌐 ACCESO WEB
════════════════════════════════════════════════════════════
URL pública:  http://4.151.89.10:8501
URL local:    http://localhost:8501
```

**Para ver logs en tiempo real:**
```bash
tail -f streamlit_app.log
```

---

## 🔓 Paso 4: Abrir Puerto en Azure (CRÍTICO)

Sin este paso, la URL no será accesible.

### Opción A: Portal de Azure (GUI)

1. Ir a **Azure Portal**
2. Buscar tu Resource Group
3. Ir a **Network Security Group** (NSG)
4. Click en **Inbound security rules**
5. **+ Add** nueva regla:
   - **Source**: Any (o específica si tienes IP whitelist)
   - **Source port ranges**: *
   - **Destination**: Any
   - **Service**: Custom
   - **Destination port ranges**: `8501`
   - **Protocol**: TCP
   - **Action**: Allow
   - **Priority**: 100 (o siguiente disponible)
   - **Name**: `Allow-Streamlit-8501`
6. **Save**

### Opción B: Azure CLI

```bash
# Obtener nombre del NSG
az network nsg list --query "[].name" -o tsv

# Agregar regla (reemplaza MY-NSG con el nombre real)
az network nsg rule create \
  --resource-group <tu-resource-group> \
  --nsg-name <tu-nsg-name> \
  --name Allow-Streamlit-8501 \
  --protocol tcp \
  --priority 100 \
  --destination-port-ranges 8501 \
  --access Allow
```

### Verificar que el puerto está abierto

```bash
# Desde tu máquina local (NO desde la VM)
nc -zv 4.151.89.10 8501
# O con curl
curl -I http://4.151.89.10:8501
```

---

## 🌐 Paso 5: Compartir URL con Expertos

**URL a compartir:**
```
http://4.151.89.10:8501
```

**Instrucciones para expertos:**
1. Abre tu navegador (Chrome, Firefox, Safari, Edge)
2. Ve a: `http://4.151.89.10:8501`
3. Inicia sesión con tu correo de Firebase
4. ¡A validar especies!

---

## 📊 Monitoreo y Troubleshooting

### Ver estado de la app

```bash
# ¿Está corriendo?
ps aux | grep "streamlit run app.py" | grep -v grep

# Ver últimas líneas del log
tail -20 streamlit_app.log
```

### Reiniciar si falla

```bash
# Matar proceso anterior
pkill -f "streamlit run app.py"

# Esperar 2 segundos
sleep 2

# Reiniciar
./start_web_app.sh
```

### Problemas comunes

| Problema | Causa | Solución |
|----------|-------|----------|
| "No se puede acceder a la URL" | Puerto no abierto en Azure NSG | Ir a Step 4, agregar regla |
| "Timeout" | Firewall bloqueando | Whitelist IP de usuario en NSG |
| "App muy lenta" | Muchos usuarios simultáneos | Normal. Limitar a 5-10 usuarios a la vez |
| "Firestore no responde" | Error de credenciales | Verificar `firebase-credentials.json` |
| "Cache viejo" | Datos desactualizados | Click en "🔄 Recargar datos desde Firebase" |

---

## 🔒 Seguridad (Para Uso Temporal)

⚠️ **IMPORTANTE**: Esta configuración NO es para producción.

### Lo que FALTA (para producción):
- ❌ HTTPS (solo HTTP)
- ❌ Autenticación por IP
- ❌ Rate limiting
- ❌ Encriptación

### Para uso temporal (2-3 horas):
✅ OK. Los usuarios se autentican via Firebase.

### Si necesitas más seguridad:

**Opción 1: IP Whitelist**
```bash
az network nsg rule update \
  --resource-group <tu-resource-group> \
  --nsg-name <tu-nsg-name> \
  --name Allow-Streamlit-8501 \
  --source-address-prefixes "203.0.113.1" "203.0.113.2"  # IPs de usuarios
```

**Opción 2: Cambiar puerto (security by obscurity)**
```bash
./start_web_app.sh 9999  # Usar puerto 9999 en lugar de 8501
# Pero abre el puerto 9999 en NSG
```

**Opción 3: HTTPS con Let's Encrypt (complejo)**
Requiere dominio DNS. No recomendado para uso temporal.

---

## 📈 Performance y Límites

### ¿Cuántos usuarios simultáneos?

Recomendado: **5-10 simultáneos máximo**

**Por qué:**
- VM típica: 2-4 vCPU
- Streamlit: 1 sesión ≈ 200-500 MB RAM
- 10 usuarios = 2-5 GB RAM (OK)
- 20 usuarios = 4-10 GB RAM (lento)

**Solución:**
- Espera turnos (validación en grupos)
- O aumenta VM a más RAM

### Consumo de Firestore

Sigue siendo lo mismo:
- Lecturas: ~11,000 (caché local ✅)
- Escrituras: ~1,200 (6% del límite)
- Costo: $0 ✅

---

## 🛑 Detener la App

Cuando terminen los 2-3 horas:

```bash
# Opción 1: Matar proceso
pkill -f "streamlit run app.py"

# Opción 2: Script simple
kill $(lsof -t -i:8501)

# Opción 3: Cerrar puerto en Azure NSG
# IR a Portal → NSG → Delete la regla "Allow-Streamlit-8501"
```

---

## 📋 Checklist

- [ ] Firestore actualizado (10,787 especies)
- [ ] Script `start_web_app.sh` ejecutable (`chmod +x`)
- [ ] App iniciada (`./start_web_app.sh`)
- [ ] Puerto 8501 abierto en Azure NSG
- [ ] Probé URL localmente desde la VM (`curl localhost:8501`)
- [ ] Probé URL desde otra máquina (`curl 4.151.89.10:8501`)
- [ ] Compartí URL con los 20 expertos
- [ ] Todos pueden iniciar sesión y validar
- [ ] Monitoreo de logs (`tail -f streamlit_app.log`)
- [ ] Plan de cierre (qué hacer cuando termine)

---

## 🎯 Flujo Típico

```
Hora 1: Setup
  1. Ejecutar update_firestore.py (si no lo hiciste)
  2. ./start_web_app.sh
  3. Abrir puerto en Azure NSG
  4. Verificar acceso en http://4.151.89.10:8501

Hora 2-3: Validación
  20 expertos acceden vía URL
  Validan, mueven, removenbspecies
  Cambios se guardan en Firestore ✅

Hora 4: Cierre
  pkill -f "streamlit run app.py"
  Cerrar puerto en Azure NSG (opcional)
  Descargar resultados finales
```

---

## 📊 Comparativa: Local vs Web

| Aspecto | Local | Web en Azure |
|---------|-------|-------------|
| **Setup** | Cada usuario instala | 1 URL |
| **Requisitos usuario** | Python + deps | Navegador |
| **Complejidad** | Alta | Baja |
| **Performance** | Excelente | Buena (depende ancho banda) |
| **Seguridad** | Alta | Media (temporal) |
| **Para uso temporal** | ❌ No ideal | ✅ Perfecto |
| **Para producción** | ✅ Mejor | ❌ Requiere HTTPS |

---

## 🎉 Listo!

Con esto, los 20 expertos pueden acceder via:
```
http://4.151.89.10:8501
```

Sin instalar nada localmente. Solo navegador.

---

**Última actualización: 2026-06-10**
