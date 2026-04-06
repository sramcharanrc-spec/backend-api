from cryptography.fernet import Fernet
import os

KEY = os.getenv("ENCRYPTION_KEY")

# If key is missing, generate one (for testing)
if not KEY:
    KEY = Fernet.generate_key()

# Ensure correct type
if isinstance(KEY, str):
    KEY = KEY.encode()

cipher = Fernet(KEY)


def encrypt_data(value: str):
    return cipher.encrypt(value.encode()).decode()


def decrypt_data(value: str):
    return cipher.decrypt(value.encode()).decode()