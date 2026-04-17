import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import FileResponse
from dotenv import load_dotenv


# --------------------------------------------------
# Load .env from project root
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


router = APIRouter()


# --------------------------------------------------
# Backup Directory (inside project root)
# --------------------------------------------------
BACKUP_DIR = BASE_DIR / "backup_files"
BACKUP_DIR.mkdir(exist_ok=True)


# --------------------------------------------------
# Backup Endpoint
# --------------------------------------------------
@router.get("/backup/db")
def backup_database():
    DB_URL = os.getenv("DB_URL2")  # Always fetch inside function

    if not DB_URL:
        return {"error": "DB_URL not set in .env file."}

    if not DB_URL.startswith("postgresql://"):
        return {"error": "Only PostgreSQL backups are supported."}

    try:
        # Parse database URL safely
        parsed_url = urlparse(DB_URL)

        db_user = parsed_url.username
        db_password = parsed_url.password
        db_host = parsed_url.hostname or "localhost"
        db_port = parsed_url.port or 5432
        db_name = parsed_url.path.lstrip("/")

        # Create timestamped backup file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hems_backup_{timestamp}.backup"
        filepath = BACKUP_DIR / filename

        # pg_dump command
        command = [
            r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-F", "c",  # Custom format
            "-f", str(filepath),
            db_name,
        ]

        # Set password securely
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        subprocess.run(command, env=env, check=True)

        return FileResponse(
            path=str(filepath),
            media_type="application/octet-stream",
            filename=filename,
        )

    except subprocess.CalledProcessError:
        return {"error": "pg_dump failed. Check PostgreSQL installation or credentials."}

    except Exception as e:
        return {"error": str(e)}
