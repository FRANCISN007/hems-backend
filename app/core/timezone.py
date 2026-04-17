from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Define your default timezone once
WAT = ZoneInfo("Africa/Lagos")

def now_wat() -> datetime:
    """Return current time in Africa/Lagos as timezone-aware datetime"""
    return datetime.now(WAT)

def to_wat(dt: datetime) -> datetime:
    """Convert any datetime (naive or timezone-aware) to WAT"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # ✅ FIXED HERE
    return dt.astimezone(WAT)
