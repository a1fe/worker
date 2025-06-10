#!/bin/bash
# Health Check для Pump Bot Worker

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(dirname "$SCRIPT_DIR")"

echo "🏥 PUMP BOT WORKER - HEALTH CHECK"
echo "================================"
echo ""

# Основные переменные
METRICS_PORT=${METRICS_PORT:-8081}
PID_FILE="$WORKER_DIR/worker.pid"

# Проверка процесса воркера
echo "🔍 Проверка процесса воркера..."
if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Воркер запущен (PID: $PID)"
        WORKER_RUNNING=true
    else
        echo "❌ Воркер не запущен (PID файл найден, но процесс отсутствует)"
        rm -f "$PID_FILE"
        WORKER_RUNNING=false
    fi
else
    WORKER_PIDS=$(pgrep -f "python.*worker_app" || true)
    if [[ -n "$WORKER_PIDS" ]]; then
        echo "✅ Воркер запущен (PID: $WORKER_PIDS)"
        WORKER_RUNNING=true
    else
        echo "❌ Воркер не запущен"
        WORKER_RUNNING=false
    fi
fi

# Проверка метрик
echo ""
echo "📊 Проверка метрик..."
if command -v curl &> /dev/null; then
    if curl -s "http://localhost:$METRICS_PORT/health" > /dev/null 2>&1; then
        echo "✅ Сервер метрик доступен на порту $METRICS_PORT"
        
        # Получение статуса
        HEALTH_RESPONSE=$(curl -s "http://localhost:$METRICS_PORT/health" 2>/dev/null)
        if [[ -n "$HEALTH_RESPONSE" ]]; then
            echo "📋 Статус воркера:"
            echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"
        fi
    else
        echo "❌ Сервер метрик недоступен на порту $METRICS_PORT"
    fi
else
    echo "⚠️  curl не найден, пропуск проверки метрик"
fi

# Проверка логов
echo ""
echo "📝 Проверка логов..."
LOG_FILE="$WORKER_DIR/logs/worker.log"
if [[ -f "$LOG_FILE" ]]; then
    echo "✅ Лог-файл найден: $LOG_FILE"
    
    # Размер лога
    LOG_SIZE=$(du -h "$LOG_FILE" | cut -f1)
    echo "📏 Размер лога: $LOG_SIZE"
    
    # Последние ошибки
    RECENT_ERRORS=$(tail -n 100 "$LOG_FILE" | grep -i "error\|exception\|failed" | tail -n 5)
    if [[ -n "$RECENT_ERRORS" ]]; then
        echo "⚠️  Последние ошибки:"
        echo "$RECENT_ERRORS"
    else
        echo "✅ Ошибок в последних 100 строках не найдено"
    fi
    
    # Последняя активность
    LAST_LOG_LINE=$(tail -n 1 "$LOG_FILE" 2>/dev/null)
    if [[ -n "$LAST_LOG_LINE" ]]; then
        echo "🕒 Последняя запись в логе:"
        echo "$LAST_LOG_LINE"
    fi
else
    echo "❌ Лог-файл не найден: $LOG_FILE"
fi

# Проверка конфигурации
echo ""
echo "⚙️  Проверка конфигурации..."
ENV_FILE="$WORKER_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    echo "✅ Файл конфигурации найден"
    
    # Проверка основных параметров
    if grep -q "COORDINATOR_WS_URL" "$ENV_FILE" && ! grep -q "your-coordinator" "$ENV_FILE"; then
        echo "✅ COORDINATOR_WS_URL настроен"
    else
        echo "❌ COORDINATOR_WS_URL не настроен"
    fi
    
    if grep -q "API_KEY" "$ENV_FILE" && ! grep -q "your-api-key" "$ENV_FILE"; then
        echo "✅ API_KEY настроен"
    else
        echo "❌ API_KEY не настроен"
    fi
    
    if grep -q "SOLANA_PRIVATE_KEY" "$ENV_FILE" && ! grep -q "your-solana-private-key" "$ENV_FILE"; then
        echo "✅ SOLANA_PRIVATE_KEY настроен"
    else
        echo "❌ SOLANA_PRIVATE_KEY не настроен"
    fi
else
    echo "❌ Файл конфигурации не найден: $ENV_FILE"
fi

# Проверка системных ресурсов
echo ""
echo "💻 Проверка системных ресурсов..."

# Память
if command -v free &> /dev/null; then
    MEMORY_INFO=$(free -h | grep "Mem:")
    echo "🧠 Память: $MEMORY_INFO"
elif command -v vm_stat &> /dev/null; then
    # macOS
    MEMORY_PRESSURE=$(memory_pressure 2>/dev/null | head -1 || echo "Memory pressure: unknown")
    echo "🧠 $MEMORY_PRESSURE"
fi

# Диск
DISK_USAGE=$(df -h "$WORKER_DIR" | tail -1)
echo "💾 Дисковое пространство: $DISK_USAGE"

# CPU (если доступно)
if command -v top &> /dev/null; then
    if [[ "$WORKER_RUNNING" == "true" && -n "$PID" ]]; then
        CPU_USAGE=$(top -p $PID -b -n1 2>/dev/null | grep "$PID" | awk '{print $9}' || echo "N/A")
        echo "⚡ CPU воркера: ${CPU_USAGE}%"
    fi
fi

# Проверка сетевого подключения
echo ""
echo "🌐 Проверка сетевого подключения..."

# Извлечение coordinator URL из конфигурации
if [[ -f "$ENV_FILE" ]]; then
    COORDINATOR_URL=$(grep "COORDINATOR_WS_URL" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"'"'"' | tr -d ' ')
    if [[ -n "$COORDINATOR_URL" ]]; then
        # Преобразование WebSocket URL в HTTP для проверки
        HTTP_URL=${COORDINATOR_URL//ws:/http:}
        HTTP_URL=${HTTP_URL//wss:/https:}
        HTTP_URL=${HTTP_URL%/ws/coordinator}
        
        echo "🔗 Проверка подключения к координатору: $HTTP_URL"
        
        if command -v curl &> /dev/null; then
            if curl -s --max-time 5 "$HTTP_URL/health" > /dev/null 2>&1; then
                echo "✅ Координатор доступен"
            else
                echo "❌ Координатор недоступен или не отвечает"
            fi
        fi
    fi
fi

# Общий статус
echo ""
echo "="*50
echo "📊 ОБЩИЙ СТАТУС"
echo "="*50

if [[ "$WORKER_RUNNING" == "true" ]]; then
    echo "🟢 ВОРКЕР: ЗАПУЩЕН"
else
    echo "🔴 ВОРКЕР: ОСТАНОВЛЕН"
fi

# Дополнительные рекомендации
echo ""
echo "💡 РЕКОМЕНДАЦИИ:"
if [[ "$WORKER_RUNNING" != "true" ]]; then
    echo "   • Запустите воркера: ./start.sh"
fi

if [[ ! -f "$ENV_FILE" ]] || grep -q "your-coordinator\|your-api-key" "$ENV_FILE" 2>/dev/null; then
    echo "   • Настройте .env файл"
fi

echo "   • Мониторинг логов: tail -f logs/worker.log"
echo "   • Метрики: http://localhost:$METRICS_PORT/metrics"
echo "   • Статус: http://localhost:$METRICS_PORT/health"

echo ""
