#!/bin/bash
# start_web_app.sh — Iniciar app Streamlit en Azure VM para acceso web
# Uso:
#   chmod +x start_web_app.sh
#   ./start_web_app.sh

set -e

PORT=${1:-8501}
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$APP_DIR/streamlit_app.log"

echo "🚀 Iniciando Streamlit app..."
echo "   Directorio: $APP_DIR"
echo "   Puerto: $PORT"
echo "   Logs: $LOG_FILE"
echo ""

# Matar proceso anterior si existe
pkill -f "streamlit run app.py" || true
sleep 1

# Iniciar app en segundo plano
cd "$APP_DIR"
nohup python3 -m streamlit run app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.enableXsrfProtection=true \
    > "$LOG_FILE" 2>&1 &

APP_PID=$!
echo "✅ App iniciada (PID: $APP_PID)"
echo ""

# Esperar a que esté lista
sleep 3

if ps -p $APP_PID > /dev/null; then
    echo "📊 App está ejecutándose"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "🌐 ACCESO WEB"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "URL pública:  http://4.151.89.10:$PORT"
    echo "URL local:    http://localhost:$PORT"
    echo ""
    echo "Vista de logs:"
    echo "  tail -f $LOG_FILE"
    echo ""
    echo "Detener app:"
    echo "  pkill -f 'streamlit run app.py'"
    echo ""
    echo "════════════════════════════════════════════════════════════"
else
    echo "❌ Error al iniciar la app. Ver logs:"
    tail -20 "$LOG_FILE"
    exit 1
fi
