# Contexto: Migración de Firestore a Azure SQL Server

## Situación Actual (2026-06-10)

Estamos migrando la aplicación Streamlit de **Firestore → Azure SQL Server** debido a que Firestore se está agotando con 20 usuarios simultáneos.

## Lo que ya se hizo

1. ✅ Clasificadas 10,787 especies usando Claude API
2. ✅ Creada app Streamlit con validación de grupos funcionales
3. ✅ Creado servidor SQL en Azure:
   - Server: `gocfg.database.windows.net`
   - Database: `free-sql-db-2951059`
   - Admin user: `cloudSAa6de9d39`
4. ✅ Creadas 3 tablas en Azure SQL:
   - `species` (10,787 registros listos para insertar)
   - `group_ratings`
   - `group_proposals`
5. ✅ Configurado firewall de Azure con IP de VM (server02)

## Problema Actual

Ejecutando `python3 migrate_to_azure.py` en VM server02, obtenemos:
```
Login failed for user 'cloudSAa6de9d39'. (18456)
```

**Diagnóstico en progreso:**
- Contraseña verificada: ✓ (usuario confirma 100%)
- Firewall Azure: ✓ (regla server02 agregada)
- **Posible causa:** Firewall de la VM puede estar bloqueando puerto 1433

## Próximos Pasos (en orden)

### 1. Diagnosticar firewall VM
```bash
sudo ufw status
# Si está activo:
sudo ufw allow 1433/tcp
sudo ufw allow out 1433/tcp
```

### 2. Ejecutar migración
```bash
cd ~/Functional_groups_creator_clasiffier_clone
python3 migrate_to_azure.py
```

### 3. Si funciona: Actualizar firebase_client.py
Cambiar de Firebase Admin SDK a SQLAlchemy + pyodbc para conectarse a Azure SQL en lugar de Firestore.

### 4. Desplegar en Streamlit Cloud
- Actualizar dependencias en requirements.txt
- Push a GitHub
- Conectar repositorio a Streamlit Cloud

## Credenciales (en .env)

```
AZURE_SQL_PASSWORD=TuPassword
FIREBASE_SERVICE_ACCOUNT=...  (mantener para transición)
OPENAI_API_KEY=...  (para Claude API)
```

## Archivos Importantes

- `migrate_to_azure.py` - Script migración CSV → Azure SQL
- `firebase_client.py` - Actualmente usa Firestore (necesita actualizar a SQL)
- `app.py` - App principal
- `pages/1_Validar_Grupos.py` - Validación de grupos
- `pages/2_Validar_Especies.py` - Validación de especies
- `output/species_classified.csv` - 10,787 especies clasificadas
- `data/functional_groups_final.csv` - Grupos funcionales

## Links Útiles

- Azure SQL Server: https://portal.azure.com
- Credentials: cloudSAa6de9d39 @ gocfg.database.windows.net
- GitHub: https://github.com/rcavieses/Functional_groups_creator_clasiffier

---

**Última actualización:** 2026-06-10 23:30 UTC
**Responsable:** rcavieses@gmail.com
