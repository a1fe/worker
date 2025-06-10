"""
Торговый движок для Pump Bot Worker.
Обрабатывает торговые операции на Solana.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import httpx
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import Transaction
from solders.system_program import TransferParams, transfer
from solders.pubkey import Pubkey
import base58


@dataclass
class TradeResult:
    """Результат торговой операции."""
    success: bool
    transaction_id: Optional[str] = None
    error_message: Optional[str] = None
    token_address: Optional[str] = None
    amount_sol: Optional[float] = None
    price_impact: Optional[float] = None
    gas_used: Optional[int] = None
    execution_time_ms: Optional[int] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь."""
        return asdict(self)


class TradingEngine:
    """Торговый движок для выполнения операций пампа."""

    def __init__(self, config, solana_client: AsyncClient, http_client: httpx.AsyncClient, logger: logging.Logger):
        self.config = config
        self.solana_client = solana_client
        self.http_client = http_client
        self.logger = logger
        
        # Статистика торговли
        self.trade_stats = {
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_volume_sol": 0.0,
            "average_execution_time": 0.0
        }
        
        # Кошелек для торговли
        self.trading_keypair = None
        
        # Настройки торговли
        self.max_slippage = config.max_slippage
        self.trade_amount_sol = config.trade_amount_sol
        
        # Защитные лимиты
        self.daily_volume_limit = config.daily_trade_limit_sol
        self.daily_volume_used = 0.0
        self.last_reset_day = datetime.now(timezone.utc).date()

    async def initialize(self):
        """Инициализация торгового движка."""
        try:
            # Создание торгового кошелька из приватного ключа
            if self.config.solana_private_key:
                private_key_bytes = base58.b58decode(self.config.solana_private_key)
                self.trading_keypair = Keypair.from_bytes(private_key_bytes)
                
                self.logger.info(f"💳 Торговый кошелек: {self.trading_keypair.pubkey()}")
                
                # Проверка баланса
                balance = await self._get_wallet_balance(self.trading_keypair.pubkey())
                self.logger.info(f"💰 Баланс кошелька: {balance:.4f} SOL")
                
                if balance < self.trade_amount_sol:
                    self.logger.warning(f"⚠️ Низкий баланс! Требуется минимум {self.trade_amount_sol} SOL")
            
            else:
                self.logger.warning("⚠️ Приватный ключ Solana не настроен")
            
            self.logger.info("✅ Торговый движок инициализирован")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации торгового движка: {e}")
            raise

    async def execute_pump_trade(self, command: Dict[str, Any]) -> TradeResult:
        """Выполнение торговой операции пампа."""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Извлечение параметров команды
            token_address = command.get("token_address")
            amount_sol = command.get("amount_sol", self.trade_amount_sol)
            max_slippage = command.get("max_slippage", self.max_slippage)
            
            self.logger.info(f"🚀 Выполнение пампа: {token_address}, {amount_sol} SOL")
            
            # Валидация параметров
            if not token_address:
                raise ValueError("Не указан адрес токена")
            
            if not self.trading_keypair:
                raise ValueError("Торговый кошелек не инициализирован")
            
            # Проверка лимитов
            await self._check_trade_limits(amount_sol)
            
            # Имитация торговли (если включена)
            if self.config.mock_trading:
                return await self._mock_trade(token_address, amount_sol, start_time)
            
            # Реальная торговая операция
            result = await self._execute_real_trade(
                token_address, amount_sol, max_slippage, start_time
            )
            
            # Обновление статистики
            await self._update_trade_stats(result)
            
            return result
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            self.logger.error(f"❌ Ошибка выполнения пампа: {e}")
            
            return TradeResult(
                success=False,
                error_message=str(e),
                token_address=command.get("token_address"),
                amount_sol=command.get("amount_sol"),
                execution_time_ms=int(execution_time),
                timestamp=datetime.now(timezone.utc).isoformat()
            )

    async def _check_trade_limits(self, amount_sol: float):
        """Проверка торговых лимитов."""
        # Сброс дневного лимита если нужно
        current_date = datetime.now(timezone.utc).date()
        if current_date > self.last_reset_day:
            self.daily_volume_used = 0.0
            self.last_reset_day = current_date
        
        # Проверка размера сделки
        if amount_sol > self.config.max_trade_size_sol:
            raise ValueError(f"Размер сделки превышает максимум: {amount_sol} > {self.config.max_trade_size_sol}")
        
        if amount_sol < self.config.min_trade_size_sol:
            raise ValueError(f"Размер сделки меньше минимума: {amount_sol} < {self.config.min_trade_size_sol}")
        
        # Проверка дневного лимита
        if self.daily_volume_used + amount_sol > self.daily_volume_limit:
            raise ValueError(f"Превышен дневной лимит торговли: {self.daily_volume_used + amount_sol} > {self.daily_volume_limit}")
        
        # Проверка баланса кошелька
        balance = await self._get_wallet_balance(self.trading_keypair.pubkey())
        if balance < amount_sol * 1.1:  # 10% запас на комиссии
            raise ValueError(f"Недостаточно средств: {balance} < {amount_sol * 1.1}")

    async def _execute_real_trade(self, token_address: str, amount_sol: float, max_slippage: float, start_time: datetime) -> TradeResult:
        """Выполнение реальной торговой операции."""
        try:
            # Получение информации о токене
            token_info = await self._get_token_info(token_address)
            if not token_info:
                raise ValueError("Токен не найден")
            
            # Расчет количества токенов для покупки
            token_amount = await self._calculate_token_amount(token_address, amount_sol)
            
            # Создание транзакции
            transaction = await self._build_pump_transaction(
                token_address, amount_sol, token_amount, max_slippage
            )
            
            # Подписание транзакции
            transaction.sign([self.trading_keypair])
            
            # Отправка транзакции
            tx_opts = TxOpts(skip_preflight=False, skip_confirmation=False)
            response = await self.solana_client.send_transaction(
                transaction, opts=tx_opts
            )
            
            tx_id = str(response.value)
            
            # Ожидание подтверждения
            await self._wait_for_confirmation(tx_id)
            
            # Вычисление времени выполнения
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Обновление дневного объема
            self.daily_volume_used += amount_sol
            
            self.logger.info(f"✅ Транзакция выполнена: {tx_id}")
            
            return TradeResult(
                success=True,
                transaction_id=tx_id,
                token_address=token_address,
                amount_sol=amount_sol,
                execution_time_ms=int(execution_time),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            raise ValueError(f"Ошибка выполнения транзакции: {e}")

    async def _mock_trade(self, token_address: str, amount_sol: float, start_time: datetime) -> TradeResult:
        """Имитация торговой операции для тестирования."""
        # Имитация задержки
        await asyncio.sleep(0.1)
        
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        # Генерация фиктивного ID транзакции
        fake_tx_id = f"mock_{int(datetime.now().timestamp())}"
        
        self.logger.info(f"🎭 Имитация пампа: {token_address}, {amount_sol} SOL")
        
        return TradeResult(
            success=True,
            transaction_id=fake_tx_id,
            token_address=token_address,
            amount_sol=amount_sol,
            execution_time_ms=int(execution_time),
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    async def _get_wallet_balance(self, pubkey: Pubkey) -> float:
        """Получение баланса кошелька."""
        try:
            response = await self.solana_client.get_balance(pubkey)
            return response.value / 1e9  # Конвертация lamports в SOL
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения баланса: {e}")
            return 0.0

    async def _get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Получение информации о токене."""
        try:
            # Запрос к Jupiter API или другому источнику данных о токенах
            url = f"https://price.jup.ag/v4/price?ids={token_address}"
            
            async with self.http_client.get(url) as response:
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", {}).get(token_address)
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения информации о токене: {e}")
            return None

    async def _calculate_token_amount(self, token_address: str, amount_sol: float) -> int:
        """Расчет количества токенов для покупки."""
        try:
            # Получение текущей цены токена
            token_info = await self._get_token_info(token_address)
            if not token_info:
                raise ValueError("Не удалось получить цену токена")
            
            price_sol = float(token_info.get("price", 0))
            if price_sol <= 0:
                raise ValueError("Некорректная цена токена")
            
            # Расчет количества токенов
            token_amount = int(amount_sol / price_sol)
            
            self.logger.debug(f"💰 Расчет: {amount_sol} SOL → {token_amount} токенов по цене {price_sol}")
            
            return token_amount
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета количества токенов: {e}")
            # Фиктивное значение для демо
            return int(amount_sol * 1000000)

    async def _build_pump_transaction(self, token_address: str, amount_sol: float, token_amount: int, max_slippage: float) -> Transaction:
        """Создание транзакции для пампа."""
        try:
            # Это упрощенная реализация
            # В реальности здесь будет создание инструкций для DEX (Jupiter, Raydium и т.д.)
            
            # Получение последнего блока
            recent_blockhash = await self.solana_client.get_latest_blockhash()
            
            # Создание простой транзакции (для демо)
            # В реальности здесь будут инструкции swap
            transaction = Transaction()
            transaction.recent_blockhash = recent_blockhash.value.blockhash
            transaction.fee_payer = self.trading_keypair.pubkey()
            
            self.logger.debug(f"🔧 Создана транзакция для {token_address}")
            
            return transaction
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания транзакции: {e}")
            raise

    async def _wait_for_confirmation(self, tx_id: str, max_retries: int = 30):
        """Ожидание подтверждения транзакции."""
        for attempt in range(max_retries):
            try:
                response = await self.solana_client.get_signature_status(tx_id)
                
                if response.value and response.value[0]:
                    status = response.value[0]
                    if status.confirmation_status:
                        self.logger.debug(f"✅ Транзакция подтверждена: {tx_id}")
                        return
                    
                    if status.err:
                        raise ValueError(f"Транзакция отклонена: {status.err}")
                
                # Ожидание перед следующей проверкой
                await asyncio.sleep(1)
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ValueError(f"Превышен таймаут подтверждения: {e}")
                
                await asyncio.sleep(1)
        
        raise ValueError("Таймаут ожидания подтверждения транзакции")

    async def _update_trade_stats(self, result: TradeResult):
        """Обновление статистики торговли."""
        self.trade_stats["total_trades"] += 1
        
        if result.success:
            self.trade_stats["successful_trades"] += 1
            if result.amount_sol:
                self.trade_stats["total_volume_sol"] += result.amount_sol
        else:
            self.trade_stats["failed_trades"] += 1
        
        # Обновление среднего времени выполнения
        if result.execution_time_ms:
            current_avg = self.trade_stats["average_execution_time"]
            total_trades = self.trade_stats["total_trades"]
            new_avg = ((current_avg * (total_trades - 1)) + result.execution_time_ms) / total_trades
            self.trade_stats["average_execution_time"] = new_avg

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики торговли."""
        return {
            **self.trade_stats,
            "daily_volume_used": self.daily_volume_used,
            "daily_volume_limit": self.daily_volume_limit,
            "success_rate": (
                self.trade_stats["successful_trades"] / max(self.trade_stats["total_trades"], 1) * 100
            )
        }

    async def shutdown(self):
        """Завершение работы торгового движка."""
        self.logger.info("🛑 Остановка торгового движка...")
        
        # Здесь можно добавить логику для корректного завершения открытых позиций
        
        self.logger.info("✅ Торговый движок остановлен")
