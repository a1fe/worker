"""
Модуль метрик для Pump Bot Worker.
Предоставляет Prometheus метрики и HTTP сервер для мониторинга.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from threading import Thread

try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Info, CollectorRegistry,
        generate_latest, CONTENT_TYPE_LATEST, start_http_server
    )
    from fastapi import FastAPI, Response
    import uvicorn
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


class WorkerMetricsCollector:
    """Сборщик метрик для воркера."""

    def __init__(self, worker_id: str, registry: Optional[CollectorRegistry] = None):
        self.worker_id = worker_id
        self.registry = registry or CollectorRegistry()
        
        if not METRICS_AVAILABLE:
            self.enabled = False
            return
        
        self.enabled = True
        self._setup_metrics()

    def _setup_metrics(self):
        """Настройка метрик Prometheus."""
        # Информация о воркере
        self.worker_info = Info(
            'pump_bot_worker_info',
            'Information about the pump bot worker',
            registry=self.registry
        )
        self.worker_info.info({
            'worker_id': self.worker_id,
            'version': '2.0.0',
            'type': 'pump_trading_worker'
        })

        # Статус воркера
        self.worker_status = Gauge(
            'pump_bot_worker_status',
            'Current status of the worker (1=healthy, 0=unhealthy)',
            registry=self.registry
        )

        # Время работы
        self.worker_uptime = Gauge(
            'pump_bot_worker_uptime_seconds',
            'Worker uptime in seconds',
            registry=self.registry
        )

        # Сообщения
        self.messages_sent_total = Counter(
            'pump_bot_worker_messages_sent_total',
            'Total number of messages sent to coordinator',
            registry=self.registry
        )
        
        self.messages_received_total = Counter(
            'pump_bot_worker_messages_received_total',
            'Total number of messages received from coordinator',
            registry=self.registry
        )

        # Торговые операции
        self.trades_executed_total = Counter(
            'pump_bot_worker_trades_executed_total',
            'Total number of trades executed',
            ['status'],  # success, failed
            registry=self.registry
        )

        self.trade_volume_sol_total = Counter(
            'pump_bot_worker_trade_volume_sol_total',
            'Total trading volume in SOL',
            registry=self.registry
        )

        self.trade_execution_duration = Histogram(
            'pump_bot_worker_trade_execution_duration_seconds',
            'Time taken to execute trades',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            registry=self.registry
        )

        # Ошибки
        self.errors_total = Counter(
            'pump_bot_worker_errors_total',
            'Total number of errors encountered',
            ['type'],  # websocket, trading, solana, etc.
            registry=self.registry
        )

        # Подключения
        self.connection_status = Gauge(
            'pump_bot_worker_connection_status',
            'Connection status to coordinator (1=connected, 0=disconnected)',
            registry=self.registry
        )

        self.reconnection_attempts_total = Counter(
            'pump_bot_worker_reconnection_attempts_total',
            'Total number of reconnection attempts',
            registry=self.registry
        )

        # Кошельки
        self.active_wallets = Gauge(
            'pump_bot_worker_active_wallets',
            'Number of active wallets',
            registry=self.registry
        )

        self.wallet_balance_sol = Gauge(
            'pump_bot_worker_wallet_balance_sol',
            'Wallet balance in SOL',
            ['wallet_address'],
            registry=self.registry
        )

        # Производительность
        self.memory_usage_bytes = Gauge(
            'pump_bot_worker_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )

        self.cpu_usage_percent = Gauge(
            'pump_bot_worker_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )

    def set_worker_status(self, status: str):
        """Установка статуса воркера."""
        if not self.enabled:
            return

        status_value = {
            'healthy': 1,
            'initializing': 0.5,
            'connected': 1,
            'registered': 1,
            'active': 1,
            'error': 0,
            'stopped': 0,
            'disconnected': 0
        }.get(status, 0)

        self.worker_status.set(status_value)

    def update_uptime(self, start_time: datetime):
        """Обновление времени работы."""
        if not self.enabled:
            return

        uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.worker_uptime.set(uptime)

    def increment_messages_sent(self):
        """Увеличение счетчика отправленных сообщений."""
        if not self.enabled:
            return
        self.messages_sent_total.inc()

    def increment_messages_received(self):
        """Увеличение счетчика полученных сообщений."""
        if not self.enabled:
            return
        self.messages_received_total.inc()

    def increment_trades(self, status: str = 'success', volume_sol: float = 0):
        """Увеличение счетчика торговых операций."""
        if not self.enabled:
            return
        
        self.trades_executed_total.labels(status=status).inc()
        if volume_sol > 0:
            self.trade_volume_sol_total.inc(volume_sol)

    def observe_trade_duration(self, duration_seconds: float):
        """Добавление времени выполнения торговой операции."""
        if not self.enabled:
            return
        self.trade_execution_duration.observe(duration_seconds)

    def increment_errors(self, error_type: str = 'general'):
        """Увеличение счетчика ошибок."""
        if not self.enabled:
            return
        self.errors_total.labels(type=error_type).inc()

    def set_connection_status(self, connected: bool):
        """Установка статуса подключения."""
        if not self.enabled:
            return
        self.connection_status.set(1 if connected else 0)

    def increment_reconnection_attempts(self):
        """Увеличение счетчика попыток переподключения."""
        if not self.enabled:
            return
        self.reconnection_attempts_total.inc()

    def set_active_wallets(self, count: int):
        """Установка количества активных кошельков."""
        if not self.enabled:
            return
        self.active_wallets.set(count)

    def set_wallet_balance(self, wallet_address: str, balance_sol: float):
        """Установка баланса кошелька."""
        if not self.enabled:
            return
        self.wallet_balance_sol.labels(wallet_address=wallet_address).set(balance_sol)

    def update_system_metrics(self):
        """Обновление системных метрик."""
        if not self.enabled:
            return

        try:
            import psutil
            process = psutil.Process()
            
            # Память
            memory_info = process.memory_info()
            self.memory_usage_bytes.set(memory_info.rss)
            
            # CPU
            cpu_percent = process.cpu_percent()
            self.cpu_usage_percent.set(cpu_percent)
            
        except ImportError:
            pass

    def get_metrics(self) -> str:
        """Получение метрик в формате Prometheus."""
        if not self.enabled:
            return "# Metrics disabled\n"
        
        return generate_latest(self.registry).decode('utf-8')


class MetricsServer:
    """HTTP сервер для предоставления метрик."""

    def __init__(self, worker_id: str, port: int = 8081, path: str = '/metrics'):
        self.worker_id = worker_id
        self.port = port
        self.path = path
        self.collector = WorkerMetricsCollector(worker_id)
        self.app = None
        self.server_task = None
        self.logger = logging.getLogger(__name__)

    def create_app(self) -> FastAPI:
        """Создание FastAPI приложения."""
        app = FastAPI(
            title=f"Pump Bot Worker Metrics - {self.worker_id}",
            description="Prometheus metrics for Pump Bot Worker",
            version="2.0.0"
        )

        @app.get(self.path)
        async def metrics():
            """Endpoint для метрик."""
            metrics_data = self.collector.get_metrics()
            return Response(
                content=metrics_data,
                media_type=CONTENT_TYPE_LATEST
            )

        @app.get('/health')
        async def health():
            """Health check endpoint."""
            return {
                "status": "healthy",
                "worker_id": self.worker_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics_enabled": self.collector.enabled
            }

        @app.get('/info')
        async def info():
            """Информация о воркере."""
            return {
                "worker_id": self.worker_id,
                "version": "2.0.0",
                "type": "pump_trading_worker",
                "metrics_path": self.path,
                "port": self.port
            }

        return app

    async def start_async(self):
        """Асинхронный запуск сервера."""
        if not METRICS_AVAILABLE:
            self.logger.warning("⚠️ Зависимости для метрик не установлены")
            return None

        try:
            self.app = self.create_app()
            
            config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="warning",
                access_log=False
            )
            
            server = uvicorn.Server(config)
            self.server_task = asyncio.create_task(server.serve())
            
            self.logger.info(f"📊 Сервер метрик запущен на порту {self.port}")
            return self.collector
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска сервера метрик: {e}")
            return None

    def start_threaded(self):
        """Запуск сервера в отдельном потоке."""
        if not METRICS_AVAILABLE:
            self.logger.warning("⚠️ Зависимости для метрик не установлены")
            return None

        try:
            # Простой HTTP сервер для метрик
            start_http_server(self.port, registry=self.collector.registry)
            self.logger.info(f"📊 Сервер метрик запущен на порту {self.port}")
            return self.collector
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска сервера метрик: {e}")
            return None

    async def stop(self):
        """Остановка сервера."""
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
            
        self.logger.info("📊 Сервер метрик остановлен")


def start_worker_metrics_server(worker_id: str, port: int = 8081) -> Optional[WorkerMetricsCollector]:
    """
    Запуск сервера метрик для воркера.
    
    Args:
        worker_id: Идентификатор воркера
        port: Порт для сервера метрик
        
    Returns:
        WorkerMetricsCollector или None если не удалось запустить
    """
    try:
        metrics_server = MetricsServer(worker_id, port)
        return metrics_server.start_threaded()
        
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Ошибка запуска метрик: {e}")
        return None


# Фиктивные классы для совместимости если зависимости не установлены
if not METRICS_AVAILABLE:
    class WorkerMetricsCollector:
        def __init__(self, *args, **kwargs):
            self.enabled = False
            
        def __getattr__(self, name):
            return lambda *args, **kwargs: None
