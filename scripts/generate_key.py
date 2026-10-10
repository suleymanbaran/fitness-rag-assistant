"""Print a new TOKEN_ENCRYPTION_KEY for .env. Losing the key means reconnecting every integration.

Usage: python -m scripts.generate_key
"""

from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(Fernet.generate_key().decode())
