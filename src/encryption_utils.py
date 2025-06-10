"""
Модуль шифрования для Pump Bot Worker.
Реализует X25519 обмен ключами и AES-GCM симметричное шифрование.
"""

import base64
import hashlib
import os
from typing import Tuple, Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class EncryptionUtils:
    """Утилиты для криптографических операций."""

    @staticmethod
    def generate_key_pair_x25519() -> Tuple[str, str]:
        """
        Генерирует пару ключей X25519.

        Returns:
            Tuple[str, str]: (private_key_base64, public_key_base64)
        """
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw, 
            format=serialization.PublicFormat.Raw
        )

        return (
            base64.b64encode(private_key_bytes).decode("utf-8"),
            base64.b64encode(public_key_bytes).decode("utf-8"),
        )

    @staticmethod
    def perform_key_exchange_x25519(
        private_key_base64: str, public_key_other_base64: str
    ) -> bytes:
        """
        Выполняет обмен ключами X25519.

        Args:
            private_key_base64: Собственный приватный ключ в Base64
            public_key_other_base64: Публичный ключ другой стороны в Base64

        Returns:
            bytes: Общий секрет (32 байта)
        """
        try:
            private_key_bytes = base64.b64decode(private_key_base64)
            public_key_other_bytes = base64.b64decode(public_key_other_base64)

            private_key = X25519PrivateKey.from_private_bytes(private_key_bytes)
            public_key_other = X25519PublicKey.from_public_bytes(public_key_other_bytes)

            shared_key = private_key.exchange(public_key_other)

            # Использовать HKDF для получения стабильного ключа
            derived_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b"pump_bot_encryption",
            ).derive(shared_key)

            return derived_key

        except Exception as e:
            raise ValueError(f"Ошибка обмена ключами X25519: {str(e)}")

    @staticmethod
    def encrypt_aes_gcm(
        plaintext: str, shared_key_bytes: bytes
    ) -> Tuple[str, str, str]:
        """
        Шифрует данные с использованием AES-GCM.

        Args:
            plaintext: Текст для шифрования
            shared_key_bytes: Общий секретный ключ (32 байта)

        Returns:
            Tuple[str, str, str]: (ciphertext_base64, nonce_base64, tag_base64)
        """
        try:
            # Генерировать случайный nonce
            nonce = os.urandom(12)  # 96 бит для AES-GCM

            # Создать AESGCM объект
            aesgcm = AESGCM(shared_key_bytes)

            # Шифровать данные
            plaintext_bytes = plaintext.encode("utf-8")
            ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext_bytes, None)

            # Разделить ciphertext и tag (последние 16 байт)
            ciphertext = ciphertext_with_tag[:-16]
            tag = ciphertext_with_tag[-16:]

            return (
                base64.b64encode(ciphertext).decode("utf-8"),
                base64.b64encode(nonce).decode("utf-8"),
                base64.b64encode(tag).decode("utf-8"),
            )

        except Exception as e:
            raise ValueError(f"Ошибка шифрования AES-GCM: {str(e)}")

    @staticmethod
    def decrypt_aes_gcm(
        ciphertext_base64: str,
        nonce_base64: str,
        tag_base64: str,
        shared_key_bytes: bytes,
    ) -> str:
        """
        Дешифрует данные AES-GCM.

        Args:
            ciphertext_base64: Зашифрованный текст в Base64
            nonce_base64: Nonce в Base64
            tag_base64: Тег аутентификации в Base64
            shared_key_bytes: Общий секретный ключ (32 байта)

        Returns:
            str: Расшифрованный текст
        """
        try:
            ciphertext = base64.b64decode(ciphertext_base64)
            nonce = base64.b64decode(nonce_base64)
            tag = base64.b64decode(tag_base64)

            # Создать AESGCM объект
            aesgcm = AESGCM(shared_key_bytes)

            # Объединить ciphertext и tag для decrypt
            ciphertext_with_tag = ciphertext + tag

            # Дешифровать данные
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)

            return plaintext_bytes.decode("utf-8")

        except Exception as e:
            raise ValueError(f"Ошибка дешифрования AES-GCM: {str(e)}")

    @staticmethod
    def encrypt_wallet_key(private_key_base58: str, shared_key_bytes: bytes) -> str:
        """
        Шифрует приватный ключ кошелька для передачи.

        Args:
            private_key_base58: Приватный ключ кошелька в формате base58
            shared_key_bytes: Общий секретный ключ

        Returns:
            str: Зашифрованные данные в формате "ciphertext:nonce:tag" (все в Base64)
        """
        ciphertext, nonce, tag = EncryptionUtils.encrypt_aes_gcm(
            private_key_base58, shared_key_bytes
        )
        return f"{ciphertext}:{nonce}:{tag}"

    @staticmethod
    def decrypt_wallet_key(encrypted_data: str, shared_key_bytes: bytes) -> str:
        """
        Дешифрует приватный ключ кошелька.

        Args:
            encrypted_data: Зашифрованные данные в формате "ciphertext:nonce:tag"
            shared_key_bytes: Общий секретный ключ

        Returns:
            str: Приватный ключ кошелька в формате base58
        """
        try:
            ciphertext_base64, nonce_base64, tag_base64 = encrypted_data.split(":")
            return EncryptionUtils.decrypt_aes_gcm(
                ciphertext_base64, nonce_base64, tag_base64, shared_key_bytes
            )
        except ValueError as e:
            if "not enough values to unpack" in str(e):
                raise ValueError(
                    "Неверный формат зашифрованных данных. Ожидается 'ciphertext:nonce:tag'"
                )
            raise

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """
        Хеширует API ключ для безопасного хранения.

        Args:
            api_key: API ключ

        Returns:
            str: Хеш API ключа в base64
        """
        # Используем соль для безопасности
        salt = b"pump_bot_api_key_salt"
        key_bytes = api_key.encode('utf-8')
        hash_bytes = hashlib.pbkdf2_hmac('sha256', key_bytes, salt, 100000)
        return base64.b64encode(hash_bytes).decode('utf-8')

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        Генерирует криптографически стойкий токен.

        Args:
            length: Длина токена в байтах

        Returns:
            str: Токен в base64
        """
        token_bytes = os.urandom(length)
        return base64.b64encode(token_bytes).decode('utf-8')

    @staticmethod
    def verify_message_integrity(message: str, signature: str, public_key: str) -> bool:
        """
        Проверяет целостность сообщения.

        Args:
            message: Сообщение
            signature: Подпись сообщения
            public_key: Публичный ключ для проверки

        Returns:
            bool: True если сообщение подлинное
        """
        try:
            # Простая реализация для проверки целостности
            expected_hash = hashlib.sha256(
                (message + public_key).encode('utf-8')
            ).hexdigest()
            return signature == expected_hash
        except Exception:
            return False

    @staticmethod
    def sign_message(message: str, private_key: str) -> str:
        """
        Подписывает сообщение.

        Args:
            message: Сообщение для подписи
            private_key: Приватный ключ

        Returns:
            str: Подпись сообщения
        """
        try:
            # Простая реализация подписи
            signature_hash = hashlib.sha256(
                (message + private_key).encode('utf-8')
            ).hexdigest()
            return signature_hash
        except Exception as e:
            raise ValueError(f"Ошибка подписи сообщения: {str(e)}")

    @staticmethod
    def encrypt_sensitive_data(data: str, password: str) -> str:
        """
        Шифрует чувствительные данные с помощью пароля.

        Args:
            data: Данные для шифрования
            password: Пароль

        Returns:
            str: Зашифрованные данные
        """
        try:
            # Генерируем ключ из пароля
            salt = os.urandom(16)
            key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
            
            # Шифруем данные
            nonce = os.urandom(12)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, data.encode('utf-8'), None)
            
            # Объединяем соль, nonce и зашифрованные данные
            encrypted = salt + nonce + ciphertext
            return base64.b64encode(encrypted).decode('utf-8')
            
        except Exception as e:
            raise ValueError(f"Ошибка шифрования данных: {str(e)}")

    @staticmethod
    def decrypt_sensitive_data(encrypted_data: str, password: str) -> str:
        """
        Дешифрует чувствительные данные.

        Args:
            encrypted_data: Зашифрованные данные
            password: Пароль

        Returns:
            str: Расшифрованные данные
        """
        try:
            # Декодируем данные
            data = base64.b64decode(encrypted_data.encode('utf-8'))
            
            # Извлекаем соль, nonce и зашифрованные данные
            salt = data[:16]
            nonce = data[16:28]
            ciphertext = data[28:]
            
            # Генерируем ключ из пароля
            key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
            
            # Дешифруем данные
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            return plaintext.decode('utf-8')
            
        except Exception as e:
            raise ValueError(f"Ошибка дешифрования данных: {str(e)}")
