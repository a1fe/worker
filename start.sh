#!/bin/bash
# Скрипт запуска Pump Bot Worker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 ЗАПУСК PUMP BOT WORKER"
echo "========================"
echo ""

# Проверка виртуального окружения
if [[ ! -d "venv" ]]; then
    echo "❌ Виртуальное окружение не найдено. Запустите: ./install.sh"
    exit 1
fi

# Проверка и установка uv (если не найден)
if ! command -v uv &> /dev/null; then
    echo "❌ uv не найден. Устанавливаем автоматически..."
    
    # Определение операционной системы
    OS="$(uname -s)"
    case "${OS}" in
        Linux*|Darwin*)
            echo "📥 Установка uv через curl..."
            curl -LsSf https://astral.sh/uv/install.sh | sh
            # Добавляем uv в PATH для текущей сессии
            export PATH="$HOME/.cargo/bin:$PATH"
            ;;
        CYGWIN*|MINGW*)
            echo "📥 Установка uv через PowerShell..."
            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
            ;;
        *)
            echo "❌ Автоматическая установка uv не поддерживается"
            echo "   Установите uv вручную: https://docs.astral.sh/uv/getting-started/installation/"
            echo "   Или используйте стандартную активацию venv..."
            source venv/bin/activate
            ;;
    esac
    
    # Проверяем установку
    if command -v uv &> /dev/null; then
        echo "✅ uv установлен успешно"
    else
        echo "⚠️  uv не удалось установить. Используем стандартную активацию venv..."
        source venv/bin/activate
    fi
else
    echo "✅ uv найден: $(uv --version 2>/dev/null || echo 'версия недоступна')"
fi

# Активация виртуального окружения
if command -v uv &> /dev/null; then
    echo "⚡ Используем uv для управления окружением"
    source venv/bin/activate
else
    echo "🐍 Используем стандартную активацию venv..."
    source venv/bin/activate
fi

# Проверка конфигурации
if [[ ! -f ".env" ]]; then
    echo "❌ Файл .env не найден. Скопируйте из .env.example и настройте"
    exit 1
fi

# Проверка основных параметров
if grep -q "your-coordinator" .env 2>/dev/null; then
    echo "❌ Необходимо настроить COORDINATOR_WS_URL в .env файле"
    exit 1
fi

if grep -q "your-api-key" .env 2>/dev/null; then
    echo "❌ Необходимо настроить API_KEY в .env файле"
    exit 1
fi

# Создание необходимых директорий
mkdir -p logs
mkdir -p wallets

# Проверка зависимостей
echo "🔍 Проверка зависимостей..."
python3 -c "
import sys
required_modules = ['asyncio', 'websockets', 'solana', 'httpx', 'pydantic']
missing = []
for module in required_modules:
    try:
        __import__(module)
    except ImportError:
        missing.append(module)
if missing:
    print('❌ Отсутствуют модули:', ', '.join(missing))
    if 'uv' in sys.modules or 'uv' in globals():
        print('   Переустановите: uv pip install -r requirements.txt')
    else:
        print('   Переустановите: pip install -r requirements.txt')
    print('   Или запустите: ./install.sh')
    sys.exit(1)
else:
    print('✅ Все зависимости установлены')
"

# Проверка подключения к координатору (опционально)
echo "🔗 Проверка подключения к координатору..."
COORDINATOR_URL=$(grep COORDINATOR_WS_URL .env | cut -d'=' -f2 | tr -d '"'"'"'')
HTTP_URL=${COORDINATOR_URL//ws:/http:}
HTTP_URL=${HTTP_URL//wss:/https:}
HTTP_URL=${HTTP_URL%/ws/coordinator}

if command -v curl &> /dev/null; then
    if curl -s "$HTTP_URL/health" > /dev/null 2>&1; then
        echo "✅ Координатор доступен"
    else
        echo "⚠️  Координатор недоступен (возможно, еще не запущен)"
    fi
fi

# Запуск воркера
echo ""
echo "🏃 Запуск воркера..."
echo "Логи: tail -f logs/worker.log"
echo "Остановка: Ctrl+C или ./stop.sh"
echo ""

# Запуск с обработкой сигналов
trap 'echo ""; echo "🛑 Остановка воркера..."; exit 0' INT TERM

if [[ "$1" == "--daemon" ]] || [[ "$1" == "-d" ]]; then
    # Запуск в фоновом режиме
    echo "🔄 Запуск в фоновом режиме..."
    nohup python3 -m src.worker_app > logs/worker.log 2>&1 &
    WORKER_PID=$!
    echo $WORKER_PID > worker.pid
    echo "✅ Воркер запущен с PID: $WORKER_PID"
    echo "   Логи: tail -f logs/worker.log"
    echo "   Остановка: ./stop.sh"
else
    # Запуск в интерактивном режиме
    python3 -m src.worker_app
fi
