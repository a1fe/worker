# Pump Bot Worker - Автономное Развертывание

Этот модуль содержит все необходимое для развертывания воркера Pump Bot на любом устройстве.

## 🚀 Быстрая Установка

### Вариант 1: Сверхбыстрая установка через uv (рекомендуется)
```bash
# Быстрая установка с автоматической установкой uv
chmod +x fast-install.sh
./fast-install.sh

# Или одной командой:
curl -sSL https://your-repo.com/fast-install.sh | bash
```

### Вариант 2: Стандартная установка
```bash
# 1. Скачать и установить
curl -L https://github.com/your-repo/pump-bot-worker/archive/main.zip -o worker.zip
unzip worker.zip && cd pump-bot-worker-main

# 2. Запустить установку
chmod +x install.sh
./install.sh

# 3. Настроить конфигурацию
cp .env.example .env
nano .env  # Установить COORDINATOR_URL и API_KEY

# 4. Запустить воркера
./start.sh
```

### Вариант 3: Docker развертывание
```bash
# Создать и запустить контейнер
docker-compose up -d

# Просмотр логов
docker-compose logs -f worker
```

## ⚡ Особенности uv

**uv** - сверхбыстрый менеджер пакетов Python, который:
- ⚡ **В 10-100 раз быстрее** pip
- 🔒 **Более надежный** (лучшее разрешение зависимостей)
- 💾 **Меньше места** (эффективное кэширование)
- 🔄 **Автоматическая установка** (встроена в наши скрипты)

## 📁 Структура

```
worker/
├── install.sh          # Скрипт автоматической установки
├── start.sh            # Скрипт запуска воркера
├── stop.sh             # Скрипт остановки воркера
├── update.sh           # Скрипт обновления
├── requirements.txt    # Python зависимости
├── pyproject.toml      # Настройки проекта
├── Dockerfile          # Docker образ
├── docker-compose.yml  # Docker Compose конфигурация
├── .env.example        # Пример конфигурации
├── README.md           # Документация
├── src/                # Исходный код воркера
│   ├── __init__.py
│   ├── worker_app.py   # Основное приложение
│   ├── config.py       # Конфигурация
│   ├── crypto.py       # Криптографические операции
│   ├── pump_trading.py # Торговая логика
│   ├── encryption_utils.py # Утилиты шифрования
│   └── worker_metrics.py   # Метрики
├── scripts/            # Вспомогательные скрипты
│   ├── health_check.sh
│   ├── backup_logs.sh
│   └── monitor.sh
└── logs/               # Логи (создается автоматически)
```

## ⚙️ Конфигурация

### Основные параметры (.env файл):

```env
# Координатор
COORDINATOR_WS_URL=ws://your-coordinator:8000/ws/coordinator
API_KEY=your-api-key

# Воркер
WORKER_ID=worker-001
WORKER_REGION=us-east-1

# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY=your-private-key

# Торговля
MAX_SLIPPAGE=0.05
TRADE_AMOUNT_SOL=0.01
MAX_WALLETS=10

# Логирование
LOG_LEVEL=INFO
LOG_FILE=./logs/worker.log

# Метрики
METRICS_ENABLED=true
METRICS_PORT=8081
```

## 🐳 Docker Развертывание

```bash
# Создать и запустить контейнер
docker-compose up -d

# Просмотр логов
docker-compose logs -f worker

# Остановка
docker-compose down
```

## 📊 Мониторинг

- **Статус воркера**: `./scripts/health_check.sh`
- **Метрики**: `http://localhost:8081/metrics`
- **Логи**: `tail -f logs/worker.log`

## 🔧 Обслуживание

```bash
# Обновление воркера
./update.sh

# Резервное копирование логов
./scripts/backup_logs.sh

# Мониторинг производительности
./scripts/monitor.sh
```

## 🆘 Поддержка

- Проверьте логи: `tail -f logs/worker.log`
- Проверьте подключение к координатору
- Убедитесь, что API_KEY корректный
- Проверьте баланс Solana кошелька

## 📝 Требования

- Python 3.8+
- Docker (опционально)
- 4GB RAM минимум
- Стабильное интернет соединение
