import os
from app.security.passwords import hash_password

plain = input("Enter the ADMIN LICENSE password: ").strip()
h = hash_password(plain)
print("\nCopy this line into your .env:\n")
print(f'ADMIN_LICENSE_PASSWORD_HASH="{h}"')
