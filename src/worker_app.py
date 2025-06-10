"""
Основное приложение Pump Bot Worker.
Автономный воркер для торговли на Solana.
"""

import asyncio
import json
import logging
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import os

import websockets
from websockets import State
import httpx
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.transaction import Transaction
import base58

from .config import get_config, WorkerConfig
from .encryption_utils import EncryptionUtils
from .pump_trading import TradingEngine, TradeResult
from .worker_metrics import start_worker_metrics_server, WorkerMetricsCollector


class WorkerApp:
    """Главный класс приложения воркера."""

    def __init__(self, config: Optional[WorkerConfig] = None):
        # Загрузка конфигурации
        self.config = config or get_config()
        
        # Основные настройки
        self.worker_id = self.config.worker_id
        self.coordinator_ws_url = self.config.coordinator_ws_url
        self.websocket = None
        self.is_running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10

        # Настройка логирования
        self._setup_logging()
        self.logger = logging.getLogger(__name__)

        # Инициализация метрик
        self.metrics = None
        if self.config.metrics_enabled:
            self.metrics = start_worker_metrics_server(
                self.worker_id, self.config.metrics_port
            )
            if self.metrics:
                self.metrics.set_worker_status("initializing")

        # Настройки шифрования
        self.worker_private_key = self.config.worker_private_key_x25519
        self.coordinator_public_key = self.config.coordinator_public_key_x25519
        self.shared_key = None

        # Кошельки (индекс -> Keypair)
        self.wallets: Dict[int, Keypair] = {}
        
        # Торговый движок
        self.trading_engine = None

        # HTTP клиент
        self.http_client = None
        
        # Solana клиент
        self.solana_client = None

        # Статистика
        self.stats = {
            "start_time": datetime.now(timezone.utc),
            "messages_sent": 0,
            "messages_received": 0,
            "trades_executed": 0,
            "errors": 0,
            "last_heartbeat": None
        }

        # Обработчики сигналов для корректного завершения
        self._setup_signal_handlers()

    def _setup_logging(self):
        """Настройка системы логирования."""
        # Создаем директорию для логов
        log_dir = os.path.dirname(self.config.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Настройка уровня логирования
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        # Формат логов
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Обработчики логов
        handlers = []
        
        # Файловый обработчик
        if self.config.log_file:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                self.config.log_file,
                maxBytes=self._parse_size(self.config.log_max_size),
                backupCount=self.config.log_backup_count
            )
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)

        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

        # Применение настроек
        logging.basicConfig(
            level=log_level,
            handlers=handlers,
            force=True
        )

    def _parse_size(self, size_str: str) -> int:
        """Парсинг размера файла (например, '50MB')."""
        size_str = size_str.upper()
        if size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)

    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов."""
        def signal_handler(signum, frame):
            self.logger.info(f"Получен сигнал {signum}, завершение работы...")
            asyncio.create_task(self.shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def initialize(self):
        """Инициализация воркера."""
        self.logger.info(f"🚀 Инициализация Pump Bot Worker: {self.worker_id}")
        
        try:
            # Инициализация шифрования
            await self._initialize_encryption()
            
            # Инициализация HTTP клиента
            await self._initialize_http_client()
            
            # Инициализация Solana клиента
            await self._initialize_solana_client()
            
            # Инициализация торгового движка
            await self._initialize_trading_engine()
            
            # Обновление метрик
            if self.metrics:
                self.metrics.set_worker_status("initialized")
            
            self.logger.info("✅ Воркер успешно инициализирован")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации: {e}")
            if self.metrics:
                self.metrics.increment_errors()
            raise

    async def _initialize_encryption(self):
        """Инициализация шифрования."""
        if not self.config.encryption_enabled:
            self.logger.info("🔓 Шифрование отключено")
            return

        if not self.worker_private_key or not self.coordinator_public_key:
            self.logger.warning("⚠️ Ключи шифрования не настроены")
            return

        try:
            # Вычисление общего ключа
            self.shared_key = EncryptionUtils.perform_key_exchange_x25519(
                self.worker_private_key, self.coordinator_public_key
            )
            self.logger.info("🔐 Шифрование инициализировано")
            
        except Exception as e:
            raise ValueError(f"Ошибка инициализации шифрования: {e}")

    async def _initialize_http_client(self):
        """Инициализация HTTP клиента."""
        timeout = httpx.Timeout(30.0)
        limits = httpx.Limits(
            max_keepalive_connections=self.config.http_pool_size,
            max_connections=self.config.http_pool_size * 2
        )
        
        self.http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            proxy=self.config.proxy_url
        )
        
        self.logger.info("🌐 HTTP клиент инициализирован")

    async def _initialize_solana_client(self):
        """Инициализация Solana клиента."""
        try:
            rpc_urls = self.config.get_solana_rpc_urls()
            self.solana_client = AsyncClient(
                rpc_urls[0],
                commitment=self.config.solana_commitment,
                timeout=30
            )
            
            # Проверка подключения
            await self.solana_client.get_health()
            self.logger.info(f"🔗 Solana клиент подключен: {rpc_urls[0]}")
            
        except Exception as e:
            raise ValueError(f"Ошибка подключения к Solana: {e}")

    async def _initialize_trading_engine(self):
        """Инициализация торгового движка."""
        try:
            self.trading_engine = TradingEngine(
                config=self.config,
                solana_client=self.solana_client,
                http_client=self.http_client,
                logger=self.logger
            )
            
            await self.trading_engine.initialize()
            self.logger.info("💰 Торговый движок инициализирован")
            
        except Exception as e:
            raise ValueError(f"Ошибка инициализации торгового движка: {e}")

    async def connect_to_coordinator(self):
        """Подключение к координатору."""
        self.logger.info(f"🔗 Подключение к координатору: {self.coordinator_ws_url}")
        
        retry_delay = self.config.retry_delay
        
        while self.is_running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                # Подключение WebSocket
                self.websocket = await websockets.connect(
                    self.coordinator_ws_url,
                    ping_interval=self.config.ws_ping_interval,
                    ping_timeout=self.config.ws_ping_timeout,
                    close_timeout=10
                )
                
                self.logger.info("✅ Подключен к координатору")
                self.reconnect_attempts = 0
                
                # Отправка регистрации
                await self._send_registration()
                
                # Обновление метрик
                if self.metrics:
                    self.metrics.set_worker_status("connected")
                
                return True
                
            except Exception as e:
                self.reconnect_attempts += 1
                self.logger.error(
                    f"❌ Ошибка подключения (попытка {self.reconnect_attempts}): {e}"
                )
                
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    self.logger.info(f"⏳ Повтор через {retry_delay} сек...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= self.config.backoff_factor
                
                if self.metrics:
                    self.metrics.increment_errors()
        
        return False

    async def _send_registration(self):
        """Отправка сообщения регистрации."""
        registration_message = {
            "type": "register",
            "api_key": self.config.api_key,
            "worker_id": self.worker_id,
            "worker_public_key_x25519_base64": self.config.worker_public_key_x25519,
            "region": self.config.worker_region,
            "capabilities": self.config.get_capabilities(),
            "status": "ready",
            "metadata": {
                "version": "2.0.0",
                "name": self.config.worker_name,
                "description": self.config.worker_description,
                "max_wallets": self.config.max_wallets_per_worker,
                "max_concurrent_trades": self.config.max_concurrent_trades,
            }
        }
        
        await self._send_message(registration_message)
        self.logger.info("📤 Отправлено сообщение регистрации")

    async def _send_message(self, message: Dict[str, Any]):
        """Отправка сообщения координатору."""
        if not self.websocket or self.websocket.closed:
            raise RuntimeError("WebSocket соединение закрыто")
        
        try:
            message_json = json.dumps(message)
            
            # Шифрование сообщения если включено
            if self.config.encryption_enabled and self.shared_key:
                encrypted_data = self._encrypt_message(message_json)
                final_message = {
                    "type": "encrypted",
                    "data": encrypted_data
                }
                message_json = json.dumps(final_message)
            
            await self.websocket.send(message_json)
            self.stats["messages_sent"] += 1
            
            if self.config.debug_websocket:
                self.logger.debug(f"📤 Отправлено: {message.get('type', 'unknown')}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки сообщения: {e}")
            if self.metrics:
                self.metrics.increment_errors()
            raise

    def _encrypt_message(self, message: str) -> str:
        """Шифрование сообщения."""
        try:
            ciphertext, nonce, tag = EncryptionUtils.encrypt_aes_gcm(
                message, self.shared_key
            )
            return f"{ciphertext}:{nonce}:{tag}"
        except Exception as e:
            self.logger.error(f"❌ Ошибка шифрования: {e}")
            raise

    def _decrypt_message(self, encrypted_data: str) -> str:
        """Дешифрование сообщения."""
        try:
            parts = encrypted_data.split(":")
            if len(parts) != 3:
                raise ValueError("Неверный формат зашифрованных данных")
            
            ciphertext, nonce, tag = parts
            return EncryptionUtils.decrypt_aes_gcm(
                ciphertext, nonce, tag, self.shared_key
            )
        except Exception as e:
            self.logger.error(f"❌ Ошибка дешифрования: {e}")
            raise

    async def message_handler(self):
        """Обработчик входящих сообщений."""
        self.logger.info("👂 Запуск обработчика сообщений")
        
        try:
            async for message in self.websocket:
                await self._process_message(message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("🔌 WebSocket соединение закрыто")
        except Exception as e:
            self.logger.error(f"❌ Ошибка в обработчике сообщений: {e}")
            if self.metrics:
                self.metrics.increment_errors()

    async def _process_message(self, raw_message: str):
        """Обработка входящего сообщения."""
        try:
            message = json.loads(raw_message)
            self.stats["messages_received"] += 1
            
            if self.config.debug_websocket:
                self.logger.debug(f"📥 Получено: {message.get('type', 'unknown')}")
            
            # Дешифрование если нужно
            if message.get("type") == "encrypted":
                decrypted = self._decrypt_message(message["data"])
                message = json.loads(decrypted)
            
            # Обработка различных типов сообщений
            message_type = message.get("type")
            
            if message_type == "registration_success":
                await self._handle_registration_success(message)
            elif message_type == "registration_error":
                await self._handle_registration_error(message)
            elif message_type == "pump_command":
                await self._handle_pump_command(message)
            elif message_type == "heartbeat_request":
                await self._handle_heartbeat_request(message)
            elif message_type == "wallet_assignment":
                await self._handle_wallet_assignment(message)
            elif message_type == "status_request":
                await self._handle_status_request(message)
            else:
                self.logger.warning(f"⚠️ Неизвестный тип сообщения: {message_type}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки сообщения: {e}")
            if self.metrics:
                self.metrics.increment_errors()

    async def _handle_registration_success(self, message: Dict[str, Any]):
        """Обработка успешной регистрации."""
        self.logger.info("✅ Регистрация успешна")
        
        # Получение публичного ключа координатора
        coordinator_key = message.get("coordinator_public_key_x25519")
        if coordinator_key and not self.coordinator_public_key:
            self.coordinator_public_key = coordinator_key
            await self._initialize_encryption()
        
        # Обновление метрик
        if self.metrics:
            self.metrics.set_worker_status("registered")

    async def _handle_registration_error(self, message: Dict[str, Any]):
        """Обработка ошибки регистрации."""
        error_msg = message.get("message", "Неизвестная ошибка")
        self.logger.error(f"❌ Ошибка регистрации: {error_msg}")
        
        # Критическая ошибка - останавливаем воркера
        await self.shutdown()

    async def _handle_pump_command(self, message: Dict[str, Any]):
        """Обработка команды пампа."""
        try:
            self.logger.info(f"💰 Получена команда пампа: {message.get('token_address')}")
            
            if not self.trading_engine:
                raise ValueError("Торговый движок не инициализирован")
            
            # Выполнение торговой операции
            result = await self.trading_engine.execute_pump_trade(message)
            
            # Отправка результата
            response = {
                "type": "pump_result",
                "worker_id": self.worker_id,
                "command_id": message.get("command_id"),
                "result": result.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await self._send_message(response)
            
            # Обновление статистики
            self.stats["trades_executed"] += 1
            if self.metrics:
                self.metrics.increment_trades()
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения пампа: {e}")
            
            # Отправка ошибки
            error_response = {
                "type": "pump_error",
                "worker_id": self.worker_id,
                "command_id": message.get("command_id"),
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await self._send_message(error_response)
            
            if self.metrics:
                self.metrics.increment_errors()

    async def _handle_heartbeat_request(self, message: Dict[str, Any]):
        """Обработка запроса heartbeat."""
        response = {
            "type": "heartbeat_ack",
            "worker_id": self.worker_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "stats": self.stats.copy(),
            "health": await self._get_health_status()
        }
        
        await self._send_message(response)
        self.stats["last_heartbeat"] = datetime.now(timezone.utc)

    async def _handle_wallet_assignment(self, message: Dict[str, Any]):
        """Обработка назначения кошелька."""
        try:
            wallet_index = message.get("wallet_index")
            encrypted_key = message.get("encrypted_private_key")
            
            if not self.shared_key:
                raise ValueError("Шифрование не инициализировано")
            
            # Дешифрование приватного ключа
            private_key_base58 = EncryptionUtils.decrypt_wallet_key(
                encrypted_key, self.shared_key
            )
            
            # Создание Keypair
            private_key_bytes = base58.b58decode(private_key_base58)
            keypair = Keypair.from_bytes(private_key_bytes)
            
            # Сохранение кошелька
            self.wallets[wallet_index] = keypair
            
            self.logger.info(f"💳 Назначен кошелек {wallet_index}: {keypair.pubkey()}")
            
            # Подтверждение
            response = {
                "type": "wallet_assigned",
                "worker_id": self.worker_id,
                "wallet_index": wallet_index,
                "public_key": str(keypair.pubkey()),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await self._send_message(response)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка назначения кошелька: {e}")

    async def _handle_status_request(self, message: Dict[str, Any]):
        """Обработка запроса статуса."""
        status = {
            "type": "worker_status",
            "worker_id": self.worker_id,
            "status": "active" if self.is_running else "inactive",
            "uptime": (datetime.now(timezone.utc) - self.stats["start_time"]).total_seconds(),
            "stats": self.stats.copy(),
            "config": {
                "region": self.config.worker_region,
                "capabilities": self.config.get_capabilities(),
                "max_wallets": self.config.max_wallets_per_worker,
                "max_concurrent_trades": self.config.max_concurrent_trades
            },
            "health": await self._get_health_status(),
            "wallets": len(self.wallets),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self._send_message(status)

    async def _get_health_status(self) -> Dict[str, Any]:
        """Получение статуса здоровья воркера."""
        health = {
            "overall": "healthy",
            "websocket": "connected" if self.websocket and not self.websocket.closed else "disconnected",
            "solana_client": "unknown",
            "trading_engine": "unknown",
            "memory_usage": 0,
            "errors_24h": self.stats.get("errors", 0)
        }
        
        try:
            # Проверка Solana клиента
            if self.solana_client:
                await self.solana_client.get_health()
                health["solana_client"] = "healthy"
        except:
            health["solana_client"] = "unhealthy"
        
        # Проверка торгового движка
        if self.trading_engine:
            health["trading_engine"] = "ready"
        
        # Использование памяти
        try:
            import psutil
            process = psutil.Process()
            health["memory_usage"] = process.memory_info().rss / 1024 / 1024  # MB
        except:
            pass
        
        # Общая оценка здоровья
        if health["websocket"] != "connected" or health["solana_client"] == "unhealthy":
            health["overall"] = "degraded"
        
        if health["errors_24h"] > 100:
            health["overall"] = "unhealthy"
        
        return health

    async def run(self):
        """Основной цикл работы воркера."""
        self.is_running = True
        self.logger.info("🏃 Запуск воркера...")
        
        try:
            # Инициализация
            await self.initialize()
            
            # Основной цикл
            while self.is_running:
                try:
                    # Подключение к координатору
                    if not await self.connect_to_coordinator():
                        self.logger.error("❌ Не удалось подключиться к координатору")
                        break
                    
                    # Обработка сообщений
                    await self.message_handler()
                    
                except websockets.exceptions.ConnectionClosed:
                    self.logger.warning("🔌 Соединение закрыто координатором")
                except Exception as e:
                    self.logger.error(f"❌ Ошибка в основном цикле: {e}")
                    if self.metrics:
                        self.metrics.increment_errors()
                
                # Пауза перед переподключением
                if self.is_running:
                    self.logger.info("⏳ Переподключение через 5 секунд...")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка: {e}")
            if self.metrics:
                self.metrics.set_worker_status("error")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Корректное завершение работы воркера."""
        if not self.is_running:
            return
            
        self.logger.info("🛑 Завершение работы воркера...")
        self.is_running = False
        
        try:
            # Закрытие WebSocket
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
            
            # Закрытие HTTP клиента
            if self.http_client:
                await self.http_client.aclose()
            
            # Закрытие Solana клиента
            if self.solana_client:
                await self.solana_client.close()
            
            # Остановка торгового движка
            if self.trading_engine:
                await self.trading_engine.shutdown()
            
            # Обновление метрик
            if self.metrics:
                self.metrics.set_worker_status("stopped")
            
            self.logger.info("✅ Воркер остановлен")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при завершении: {e}")


def main():
    """Точка входа в приложение."""
    try:
        # Создание и запуск воркера
        worker = WorkerApp()
        asyncio.run(worker.run())
        
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал прерывания")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
