#!/usr/bin/env python3
import secrets
import sys


def generate_key(prefix: str = "client-dev-") -> str:
    """Generates a cryptographically secure random API key."""
    random_part = secrets.token_urlsafe(24)
    return f"{prefix}{random_part}"


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print("\n--- Generated Client API Key(s) for Testing ---")
    for i in range(count):
        key = generate_key()
        print(f"Key {i+1}: {key}")
    print("\nTo use this key:")
    print("1. Add it to CLIENT_API_KEYS in your .env file:")
    print(f'   CLIENT_API_KEYS="client-dev-key-123,{key}"')
    print("2. Send it in HTTP requests via header:")
    print(f"   X-Client-API-Key: {key}\n")
