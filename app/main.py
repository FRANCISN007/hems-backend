import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles





# Routers
from app.users.routers import router as user_router
from app.rooms.router import router as rooms_router
from app.bookings.router import router as bookings_router
from app.payments.router import router as payments_router
from app.license.router import router as license_router
from app.events.router import router as events_router
from app.eventpayment.router import router as eventpayment_router
from backup.backup import router as backup_router
from app.bank.router import router as bank_router
from app.store.router import router as store_router
from app.bar.routers import router as bar_router
from app.barpayment.router import router as barpayment_router
from app.vendor.router import router as vendor_router
from app.kitchen.router import router as kitchen_router
from app.restaurant.router import router as restaurant_router
from app.restpayment.router import router as restpayment_router

from app.superadmin.router import router as superadmin_router
from app.business.router import router as business_router


import pytz
from datetime import datetime
from contextlib import asynccontextmanager

from app.core.tenant_middleware import TenantMiddleware

app = FastAPI()

app.add_middleware(TenantMiddleware)

# --------------------------------------------------
# ENV LOADING (works for installer / frozen mode)
# --------------------------------------------------
POSSIBLE_ENV_PATHS = [
    Path(__file__).resolve().parent.parent / ".env",
    Path(sys.executable).resolve().parent / ".env",
    Path.cwd() / ".env",
]

for env_path in POSSIBLE_ENV_PATHS:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"[INFO] Loaded .env from {env_path}")
        break

from app.database import engine, Base


SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
print(f"[INFO] SERVER_IP = {SERVER_IP}")

# --------------------------------------------------
# TIMEZONE
# --------------------------------------------------
os.environ["TZ"] = "Africa/Lagos"
lagos_tz = pytz.timezone("Africa/Lagos")
print("[INFO] Time:", datetime.now(lagos_tz))

# --------------------------------------------------
# PATH FIX
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# --------------------------------------------------
# DATABASE LIFESPAN
# --------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[INFO] Application starting...")
    Base.metadata.create_all(bind=engine)
    yield
    print("[INFO] Application shutting down...")

# --------------------------------------------------
# FASTAPI APP
# --------------------------------------------------
app = FastAPI(
    title="Hotel & Event Management System",
    version="1.0.0",
    lifespan=lifespan
)

# --------------------------------------------------
# CORS (LAN SAFE)
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# FILE UPLOADS
# --------------------------------------------------
os.makedirs("uploads/attachments", exist_ok=True)
app.mount("/files", StaticFiles(directory="uploads"), name="files")

# --------------------------------------------------
# API ROUTERS (IMPORTANT: BEFORE SPA)
# --------------------------------------------------
app.include_router(superadmin_router, prefix="/superadmin", tags=["Super Admin"])
app.include_router(business_router, prefix="/business", tags=["Business"])
app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(rooms_router, prefix="/rooms", tags=["Rooms"])
app.include_router(bookings_router, prefix="/bookings", tags=["Bookings"])
app.include_router(bank_router, prefix="/bank", tags=["Banks"])
app.include_router(payments_router, prefix="/payments", tags=["Payments"])
app.include_router(events_router, prefix="/events", tags=["Events"])
app.include_router(eventpayment_router, prefix="/eventpayment", tags=["Event Payments"])
app.include_router(license_router, prefix="/license", tags=["License"])
app.include_router(store_router, prefix="/store", tags=["Store"])
app.include_router(bar_router, prefix="/bar", tags=["Bar"])
app.include_router(barpayment_router, prefix="/barpayment", tags=["Bar Payments"])
app.include_router(vendor_router, prefix="/vendor", tags=["Vendor"])
app.include_router(kitchen_router, prefix="/kitchen", tags=["Kitchen"])
app.include_router(restaurant_router, prefix="/restaurant", tags=["Restaurant"])
app.include_router(restpayment_router, prefix="/restpayment", tags=["Restaurant Payments"])
app.include_router(backup_router)

# --------------------------------------------------
# HEALTH
# --------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug/ping")
def ping():
    return {"status": "ok"}

# --------------------------------------------------
# REACT FRONTEND
# --------------------------------------------------
REACT_BUILD_DIR = BASE_DIR / "react-frontend" / "build"
REACT_STATIC_DIR = REACT_BUILD_DIR / "static"
INDEX_FILE = REACT_BUILD_DIR / "index.html"

if REACT_BUILD_DIR.exists():
    app.mount("/static", StaticFiles(directory=REACT_STATIC_DIR), name="static")
    print(f"[INFO] React build detected: {REACT_BUILD_DIR}")
else:
    print("[WARNING] React build not found")

# --------------------------------------------------
# SPA FALLBACK (CRITICAL FIX)
# --------------------------------------------------
@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    response = await call_next(request)

    # If API route → return JSON normally
    if request.url.path.startswith((
        "/users", "/rooms", "/bookings", "/payments", "/events",
        "/eventpayment", "/license", "/store", "/bar", "/vendor",
        "/kitchen", "/restaurant", "/restpayment", "/bank",
        "/backup", "/files", "/static", "/health", "/debug"
    )):
        return response

    # If frontend route and 404 → serve React
    if response.status_code == 404 and INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)

    return response
