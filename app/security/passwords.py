#!/usr/bin/env python3
import sys
import os
import argparse
from passlib.hash import argon2

def hash_password(plain_password: str) -> str:
    """Return Argon2 hash for plain_password."""
    return argon2.hash(plain_password)

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verify a candidate password against a stored Argon2 hash."""
    try:
        return argon2.verify(plain_password, stored_hash)
    except Exception:
        return False

def read_env(env_path: str, key: str):
    """Read value for key from .env. Returns None if not present."""
    if not os.path.exists(env_path):
        return None
    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k != key:
                continue
            v = v.strip()
            # Remove surrounding quotes if any
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            return v
    return None

def write_env(env_path: str, key: str, value: str):
    """Safely write or replace KEY=VALUE in .env file (simple parser)."""
    # Ensure directory exists
    env_dir = os.path.dirname(os.path.abspath(env_path)) or "."
    if env_dir and not os.path.exists(env_dir):
        os.makedirs(env_dir, exist_ok=True)

    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    key_found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in line:
            k = line.split("=", 1)[0].strip()
            if k == key:
                new_lines.append(f'{key}="{value}"')
                key_found = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not key_found:
        new_lines.append(f'{key}="{value}"')

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

def prompt_hidden(prompt_text: str) -> str:
    try:
        import getpass
        return getpass.getpass(prompt_text)
    except Exception:
        # Fallback (visible)
        return input(prompt_text)

def main():
    parser = argparse.ArgumentParser(
        description="Safely change or initialize admin license password stored in .env (Argon2)."
    )
    parser.add_argument(
        "--env", default=".env",
        help="Path to .env file (default: .env in current directory)"
    )
    parser.add_argument(
        "--key", default="ADMIN_LICENSE_PASSWORD_HASH",
        help="Env key name to read/write (default: ADMIN_LICENSE_PASSWORD_HASH)"
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Initialize password if none exists. Use this only when setting the first admin password."
    )
    args = parser.parse_args()

    env_path = args.env
    key = args.key

    current_hash = read_env(env_path, key)

    # If no stored hash
    if current_hash is None:
        if not args.init:
            print(f"[ERROR] No existing {key} found in {env_path}.")
            print("If this is the first time setting up the admin password, run with --init to initialize.")
            sys.exit(2)
        # init flow: confirm user intends to create initial password
        print(f"[INIT] No {key} found in {env_path}. Initializing a new admin password.")
        confirm = input("Type YES to proceed with initialization: ").strip()
        if confirm != "YES":
            print("Initialization aborted.")
            sys.exit(1)
        # ask for new password
        new_pass = prompt_hidden("Enter NEW admin password (hidden): ").strip()
        if not new_pass:
            print("No password entered. Exiting.")
            sys.exit(1)
        new_pass2 = prompt_hidden("Confirm NEW admin password: ").strip()
        if new_pass != new_pass2:
            print("Passwords do not match. Exiting.")
            sys.exit(1)
        new_hash = hash_password(new_pass)
        try:
            write_env(env_path, key, new_hash)
            print(f"[OK] Initialized {key} in {env_path}.")
        except Exception as exc:
            print(f"[ERROR] Could not write to {env_path}: {exc}")
            sys.exit(1)
        return

    # Normal flow: verify old password first
    print("To change the admin password you must provide the CURRENT admin password.")
    old_plain = prompt_hidden("Enter CURRENT admin password (hidden): ").strip()
    if not old_plain:
        print("No password entered. Exiting.")
        sys.exit(1)

    if not verify_password(old_plain, current_hash):
        print("[ERROR] Current password verification failed. Aborting.")
        sys.exit(3)

    # Verified, ask for new password twice
    new_pass = prompt_hidden("Enter NEW admin password (hidden): ").strip()
    if not new_pass:
        print("No new password entered. Exiting.")
        sys.exit(1)
    new_pass2 = prompt_hidden("Confirm NEW admin password: ").strip()
    if new_pass != new_pass2:
        print("Passwords do not match. Exiting.")
        sys.exit(1)

    # All good – hash and write
    new_hash = hash_password(new_pass)
    try:
        write_env(env_path, key, new_hash)
        print(f"[OK] Admin password updated in {env_path}.")
    except Exception as exc:
        print(f"[ERROR] Could not write to {env_path}: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
