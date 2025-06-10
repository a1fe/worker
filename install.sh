#!/bin/bash
# Автоматический установщик Pump Bot Worker

set -e

echo "🚀 PUMP BOT WORKER - АВТОМАТИЧЕСКАЯ УСТАНОВКА"
echo "============================================="
echo ""

# Проверка операционной системы
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    CYGWIN*)    MACHINE=Cygwin;;
    MINGW*)     MACHINE=MinGw;;
    *)          MACHINE="UNKNOWN:${unameOut}"
esac

echo "🖥️  Операционная система: $MACHINE"

# Проверка и установка uv
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null || echo "unknown")
    echo "⚡ uv: $UV_VERSION"
else
    echo "❌ uv не найден. Устанавливаем..."
    if [[ "$MACHINE" == "Linux" ]] || [[ "$MACHINE" == "Mac" ]]; then
        echo "📥 Установка uv через curl..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Добавляем uv в PATH для текущей сессии
        export PATH="$HOME/.cargo/bin:$PATH"
        # Проверяем установку
        if command -v uv &> /dev/null; then
            UV_VERSION=$(uv --version)
            echo "✅ uv установлен: $UV_VERSION"
        else
            echo "❌ Ошибка установки uv. Попробуйте установить вручную:"
            echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    elif [[ "$MACHINE" == "CYGWIN" ]] || [[ "$MACHINE" == "MINGW" ]]; then
        echo "📥 Установка uv через PowerShell..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        if ! command -v uv &> /dev/null; then
            echo "❌ Ошибка установки uv. Попробуйте установить вручную:"
            echo "   powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\""
            exit 1
        fi
    else
        echo "❌ Неподдерживаемая операционная система для автоматической установки uv"
        echo "   Установите uv вручную: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

# Проверка Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "🐍 Python: $PYTHON_VERSION"
else
    echo "❌ Python 3 не найден. Устанавливаем..."
    if [[ "$MACHINE" == "Linux" ]]; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    elif [[ "$MACHINE" == "Mac" ]]; then
        if command -v brew &> /dev/null; then
            brew install python3
        else
            echo "❌ Homebrew не найден. Установите Python 3 вручную: https://python.org"
            exit 1
        fi
    fi
fi

# Установка uv если не установлен
if ! command -v uv &> /dev/null; then
    echo "⚡ Установка uv (быстрый менеджер пакетов Python)..."
    if [[ "$MACHINE" == "Linux" ]] || [[ "$MACHINE" == "Mac" ]]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source ~/.bashrc 2>/dev/null || source ~/.zshrc 2>/dev/null || export PATH="$HOME/.cargo/bin:$PATH"
    else
        echo "❌ Автоматическая установка uv не поддерживается для $MACHINE"
        echo "   Установите uv вручную: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

# Проверка установки uv
if ! command -v uv &> /dev/null; then
    echo "❌ uv не найден в PATH. Перезапустите терминал или добавьте ~/.cargo/bin в PATH"
    echo "   export PATH=\"\$HOME/.cargo/bin:\$PATH\""
    exit 1
fi

UV_VERSION=$(uv --version)
echo "⚡ uv: $UV_VERSION"

# Создание виртуального окружения через uv
echo "📦 Создание виртуального окружения через uv..."
uv venv venv --python python3

# Активация виртуального окружения
source venv/bin/activate

# Установка зависимостей через uv (намного быстрее pip)
echo "📚 Установка зависимостей через uv..."
if [[ -f "pyproject.toml" ]]; then
    echo "   Используем pyproject.toml для установки..."
    uv pip install -e .
else
    echo "   Используем requirements.txt для установки..."
    uv pip install -r requirements.txt
fi

# Создание директорий
echo "📁 Создание директорий..."
mkdir -p logs
mkdir -p wallets
mkdir -p config

# Копирование конфигурации
if [[ ! -f .env ]]; then
    echo "⚙️  Создание конфигурации..."
    cp .env.example .env
    echo ""
    echo "⚠️  ВНИМАНИЕ: Необходимо настроить .env файл!"
    echo "   1. Откройте .env файл в редакторе"
    echo "   2. Установите COORDINATOR_WS_URL"
    echo "   3. Установите API_KEY"
    echo "   4. Установите SOLANA_PRIVATE_KEY"
    echo ""
else
    echo "✅ Конфигурация уже существует"
fi

# Создание systemd сервиса (только для Linux)
if [[ "$MACHINE" == "Linux" ]]; then
    echo "🔧 Создание systemd сервиса..."
    
    SERVICE_FILE="/etc/systemd/system/pump-bot-worker.service"
    CURRENT_DIR=$(pwd)
    
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Pump Bot Worker
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/venv/bin
ExecStart=$CURRENT_DIR/venv/bin/python -m src.worker_app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable pump-bot-worker
    
    echo "✅ Systemd сервис создан и активирован"
    echo "   Запуск: sudo systemctl start pump-bot-worker"
    echo "   Статус: sudo systemctl status pump-bot-worker"
    echo "   Логи:   sudo journalctl -u pump-bot-worker -f"
fi

# Создание скрипта запуска
echo "📝 Создание скриптов управления..."
chmod +x start.sh stop.sh update.sh
chmod +x scripts/*.sh

# Проверка установки
echo ""
echo "🧪 Проверка установки..."
source venv/bin/activate
echo "   Тестирование импорта зависимостей..."
python3 -c "
try:
    import asyncio
    import websockets
    import solana
    import httpx
    import pydantic
    print('✅ Все основные зависимости установлены')
    print('   - asyncio: встроенный модуль')
    print('   - websockets: импортирован')
    print('   - solana: импортирован')
    print('   - httpx: импортирован')
    print('   - pydantic: импортирован')
except ImportError as e:
    print(f'❌ Ошибка импорта: {e}')
    print('   Попробуйте переустановить: uv pip install -r requirements.txt')
    exit(1)
"

echo ""
echo "🎉 УСТАНОВКА ЗАВЕРШЕНА!"
echo "======================"
echo ""
echo "📦 Использован uv для быстрой установки зависимостей"
echo "⚡ Время установки значительно сокращено"
echo ""
echo "📋 Следующие шаги:"
echo "1. Настройте .env файл: nano .env"
echo "2. Запустите воркера: ./start.sh"
echo "3. Проверьте статус: ./scripts/health_check.sh"
echo ""
echo "📖 Документация: cat README.md"
echo "🆘 Поддержка: tail -f logs/worker.log"
echo ""

# Проверка конфигурации
if grep -q "your-coordinator" .env 2>/dev/null; then
    echo "⚠️  ВНИМАНИЕ: Не забудьте настроить .env файл!"
fi
