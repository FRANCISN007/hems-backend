import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# -----------------------------
# Load environment variables
# -----------------------------
env_path = Path('.') / '.env'
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / '.env'

load_dotenv(dotenv_path=env_path)
print(f"🔄 Loaded environment from: {env_path}")

SQLALCHEMY_DATABASE_URL = os.getenv("DB_URL2")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("❌ DB_URL2 environment variable is not set!")

# Show partial DB info for verification
print(f"🔍 Using database host: {SQLALCHEMY_DATABASE_URL.split('@')[-1]}")

# -----------------------------
# SQLAlchemy Engine with Pooling
# -----------------------------
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,          # Number of persistent connections
    max_overflow=40,       # Extra connections beyond pool_size
    pool_pre_ping=True,    # Test connections before using
    pool_recycle=1800,     # Recycle connections every 30 minutes
)

# -----------------------------
# SessionLocal for dependency
# -----------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# -----------------------------
# Base declarative class
# -----------------------------
Base = declarative_base()

# -----------------------------
# Dependency for FastAPI routes
# -----------------------------
def get_db():
    """
    Provides a transactional scope around a series of operations.
    Each request gets a session from the pool, which is returned after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
