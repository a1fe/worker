"""
Конфигурация воркера Pump Bot.
"""

import os
from typing import Optional, List
from pydantic import Field, ConfigDict, validator
from pydantic_settings import BaseSettings


class WorkerConfig(BaseSettings):
    """Настройки воркера."""

    # Основная идентификация
    worker_id: str = Field(
        description="Уникальный идентификатор воркера"
    )
    worker_region: str = Field(
        default="unknown",
        description="Регион размещения воркера"
    )
    worker_name: Optional[str] = Field(
        default=None,
        description="Человекочитаемое имя воркера"
    )
    worker_description: Optional[str] = Field(
        default=None,
        description="Описание воркера"
    )

    # Подключение к координатору
    coordinator_ws_url: str = Field(
        description="WebSocket URL координатора"
    )
    api_key: str = Field(
        description="API ключ для аутентификации"
    )

    # Шифрование и безопасность
    worker_private_key_x25519: Optional[str] = Field(
        default=None,
        description="Приватный ключ воркера для шифрования"
    )
    worker_public_key_x25519: Optional[str] = Field(
        default=None,
        description="Публичный ключ воркера"
    )
    coordinator_public_key_x25519: Optional[str] = Field(
        default=None,
        description="Публичный ключ координатора"
    )
    encryption_enabled: bool = Field(
        default=True,
        description="Включить шифрование сообщений"
    )

    # Solana настройки
    solana_rpc_url: str = Field(
        default="https://api.mainnet-beta.solana.com",
        description="URL Solana RPC"
    )
    solana_rpc_urls: Optional[str] = Field(
        default=None,
        description="Альтернативные RPC URLs через запятую"
    )
    solana_private_key: str = Field(
        description="Приватный ключ Solana кошелька"
    )
    solana_commitment: str = Field(
        default="confirmed",
        description="Уровень подтверждения транзакций"
    )

    # Торговые настройки
    max_slippage: float = Field(
        default=0.05,
        description="Максимальный слипаж (5%)"
    )
    trade_amount_sol: float = Field(
        default=0.01,
        description="Размер сделки в SOL"
    )
    max_wallets_per_worker: int = Field(
        default=10,
        description="Максимум кошельков на воркера"
    )
    max_concurrent_trades: int = Field(
        default=5,
        description="Максимум одновременных сделок"
    )

    # Защитные лимиты
    max_trade_size_sol: float = Field(
        default=1.0,
        description="Максимальный размер сделки"
    )
    min_trade_size_sol: float = Field(
        default=0.001,
        description="Минимальный размер сделки"
    )
    daily_trade_limit_sol: float = Field(
        default=10.0,
        description="Дневной лимит торговли"
    )

    # Сетевые настройки
    proxy_url: Optional[str] = Field(
        default=None,
        description="URL прокси сервера"
    )
    http_pool_size: int = Field(
        default=20,
        description="Размер пула HTTP соединений"
    )
    ws_ping_interval: int = Field(
        default=30,
        description="Интервал ping WebSocket (сек)"
    )
    ws_ping_timeout: int = Field(
        default=10,
        description="Таймаут ping WebSocket (сек)"
    )

    # Retry настройки
    max_retries: int = Field(
        default=3,
        description="Максимум попыток повтора"
    )
    retry_delay: float = Field(
        default=1.0,
        description="Задержка между попытками (сек)"
    )
    backoff_factor: float = Field(
        default=2.0,
        description="Фактор экспоненциального отступа"
    )

    # Настройки отчетности
    report_interval_sec: int = Field(
        default=5,
        description="Интервал отчетов (сек)"
    )
    trade_delay_ms: int = Field(
        default=100,
        description="Задержка между сделками (мс)"
    )

    # Логирование
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования"
    )
    log_file: str = Field(
        default="./logs/worker.log",
        description="Путь к файлу логов"
    )
    log_max_size: str = Field(
        default="50MB",
        description="Максимальный размер лог-файла"
    )
    log_backup_count: int = Field(
        default=5,
        description="Количество резервных лог-файлов"
    )

    # Отладка
    debug_mode: bool = Field(
        default=False,
        description="Режим отладки"
    )
    debug_trading: bool = Field(
        default=False,
        description="Отладка торговли"
    )
    debug_websocket: bool = Field(
        default=False,
        description="Отладка WebSocket"
    )
    mock_trading: bool = Field(
        default=False,
        description="Имитация торговли (для тестов)"
    )

    # Метрики и мониторинг
    metrics_enabled: bool = Field(
        default=True,
        description="Включить метрики"
    )
    metrics_port: int = Field(
        default=8081,
        description="Порт для метрик"
    )
    metrics_path: str = Field(
        default="/metrics",
        description="Путь для метрик"
    )
    health_check_enabled: bool = Field(
        default=True,
        description="Включить health check"
    )
    health_check_interval: int = Field(
        default=30,
        description="Интервал health check (сек)"
    )

    # Уведомления
    notifications_enabled: bool = Field(
        default=False,
        description="Включить уведомления"
    )
    discord_webhook_url: Optional[str] = Field(
        default=None,
        description="Discord webhook URL"
    )
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot token"
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Telegram chat ID"
    )

    # Дополнительные настройки
    timezone: str = Field(
        default="UTC",
        description="Временная зона"
    )
    enable_auto_update: bool = Field(
        default=False,
        description="Автоматические обновления"
    )
    update_check_interval: int = Field(
        default=3600,
        description="Интервал проверки обновлений (сек)"
    )

    # Разработка
    dev_mode: bool = Field(
        default=False,
        description="Режим разработки"
    )
    simulate_latency: bool = Field(
        default=False,
        description="Имитация задержки сети"
    )

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    @validator('solana_rpc_urls')
    def parse_rpc_urls(cls, v):
        """Парсинг списка RPC URLs."""
        if v:
            return [url.strip() for url in v.split(',')]
        return []

    @validator('max_slippage')
    def validate_slippage(cls, v):
        """Валидация слипажа."""
        if not 0 < v < 1:
            raise ValueError('Slippage должен быть между 0 и 1')
        return v

    @validator('trade_amount_sol', 'max_trade_size_sol', 'min_trade_size_sol')
    def validate_amounts(cls, v):
        """Валидация торговых сумм."""
        if v <= 0:
            raise ValueError('Торговая сумма должна быть положительной')
        return v

    def get_capabilities(self) -> List[str]:
        """Получить список возможностей воркера."""
        capabilities = ["pump_trading"]
        
        if self.max_wallets_per_worker > 1:
            capabilities.append("portfolio_management")
        
        if self.metrics_enabled:
            capabilities.append("metrics")
        
        if self.notifications_enabled:
            capabilities.append("notifications")
        
        return capabilities

    def get_solana_rpc_urls(self) -> List[str]:
        """Получить список RPC URLs."""
        urls = [self.solana_rpc_url]
        if hasattr(self, 'solana_rpc_urls') and self.solana_rpc_urls:
            urls.extend(self.solana_rpc_urls)
        return list(set(urls))  # Убираем дубликаты


# Глобальный экземпляр конфигурации
_config_instance = None


def get_config() -> WorkerConfig:
    """Получить экземпляр конфигурации (синглтон)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = WorkerConfig()
    return _config_instance


def reload_config() -> WorkerConfig:
    """Перезагрузить конфигурацию."""
    global _config_instance
    _config_instance = None
    return get_config()
