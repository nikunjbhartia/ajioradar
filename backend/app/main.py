import os
import time
import json
import hmac
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, Query, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.models.schemas import VerifiedCampaign, VerifiedProductDeal, SyncStatusReport, SyncHistoryItem
from app.database.storage import DealStorage
from app.services.sync_daemon import daemon_instance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("AjioDealMatrix")

app = FastAPI(
    title="StealRadar • Live Ajio Flash Codes & 70%+ Deep Steals API",
    description="Zero-block, multi-stage category flash deal discovery engine for Ajio.",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = DealStorage("deals.db")

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(daemon_instance.start_background_loop())
    logger.info("Ajio Deal Matrix API online with multi-stage category tree & 30-minute background daemon.")

@app.get("/api/campaigns", response_model=List[VerifiedCampaign])
def list_campaigns(
    search: Optional[str] = Query(None, description="Search by code, title, brand, or keyword"),
    departments: Optional[List[str]] = Query(None, description="Multi-select filter by departments"),
    categories: Optional[List[str]] = Query(None, description="Multi-select filter by specific categories"),
    brands: Optional[List[str]] = Query(None, description="Multi-select filter by brands"),
    min_discount: Optional[float] = Query(None, description="Filter by minimum realized discount %"),
    only_verified_70: bool = Query(True, description="Show only campaigns that contain verified >=70% products"),
    is_standalone_only: bool = Query(False, description="Show only standalone 75%+ deals (e.g. Buy 1 Get 5 Free)"),
    sort_by: str = Query("discount_desc", enum=["discount_desc", "skus_desc", "code_asc", "price_asc"])
):
    return storage.get_filtered_campaigns(
        search=search,
        departments=departments,
        categories=categories,
        brands=brands,
        min_discount=min_discount,
        only_verified_70=only_verified_70,
        is_standalone_only=is_standalone_only,
        sort_by=sort_by
    )

@app.get("/api/products", response_model=List[VerifiedProductDeal])
def list_products(
    search: Optional[str] = Query(None, description="Search product name, brand, or category"),
    departments: Optional[List[str]] = Query(None, description="Multi-select filter by departments"),
    categories: Optional[List[str]] = Query(None, description="Multi-select filter by specific categories"),
    brands: Optional[List[str]] = Query(None, description="Multi-select filter by brands"),
    min_discount: float = Query(70.0, ge=50.0, le=99.0, description="Minimum net discount percentage"),
    max_price: Optional[float] = Query(None, description="Maximum final selling price"),
    sort_by: str = Query("discount_desc", enum=["discount_desc", "price_asc", "price_desc", "mrp_desc"]),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0)
):
    return storage.get_verified_products(
        search=search,
        departments=departments,
        categories=categories,
        brands=brands,
        min_discount=min_discount,
        max_price=max_price,
        sort_by=sort_by,
        limit=limit,
        offset=offset
    )

@app.get("/api/taxonomy", response_model=Dict[str, Any])
def get_taxonomy():
    """Returns the complete multi-stage category tree across Men, Women, Kids, Beauty, Home & Kitchen."""
    return storage.get_taxonomy()

@app.get("/api/brands", response_model=List[str])
def list_brands():
    return storage.get_brands()

@app.get("/api/departments", response_model=List[str])
def list_departments():
    return storage.get_departments()

@app.get("/api/sync/status", response_model=SyncStatusReport)
def sync_status():
    now = time.time()
    last_sync = daemon_instance.last_sync_time or now
    stats = storage.get_stats()
    return SyncStatusReport(
        is_active=daemon_instance.is_running,
        verified_70_plus_campaigns=stats.get("verified_70_plus_campaigns", 0),
        total_campaigns=stats.get("total_campaigns", 0),
        verified_70_plus_products=stats.get("verified_70_plus_products", 0),
        last_sync_timestamp=last_sync,
        seconds_since_last_sync=round(now - last_sync, 1),
        last_sync_duration_seconds=daemon_instance.last_sync_duration,
        total_brands_indexed=stats.get("total_brands", 0),
        total_departments_indexed=stats.get("total_departments", 0),
        poll_interval_seconds=daemon_instance.poll_interval,
        safe_pacing_minutes=round(daemon_instance.poll_interval / 60, 1),
        latest_delta=daemon_instance.latest_delta
    )

@app.get("/api/sync/history", response_model=List[SyncHistoryItem])
def get_sync_history(days: int = Query(7, ge=1, le=30), limit: int = Query(50, ge=1, le=100)):
    """Returns rolling 7-day sync audit log with added, updated, and purged coupons."""
    if daemon_instance.in_memory_history:
        return daemon_instance.in_memory_history[:limit]
    return storage.get_sync_history(days=days, limit=limit)

@app.post("/api/sync/trigger")
async def trigger_sync(background_tasks: BackgroundTasks, authorization: Optional[str] = Header(default=None)):
    sync_token = os.environ.get("AJIORADAR_SYNC_TOKEN")
    if sync_token:
        expected = f"Bearer {sync_token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Unauthorized sync trigger request.")

    if daemon_instance.is_running:
        return JSONResponse({"status": "in_progress", "message": "Deal validation sweep is already actively running."}, status_code=409)

    background_tasks.add_task(daemon_instance.perform_full_sync)
    return {"status": "triggered", "message": "Deal validation sweep dispatched in background."}

def find_index_file() -> Optional[str]:
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "index.html")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist", "index.html")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "index.html")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "static", "index.html")),
        os.path.abspath(os.path.join(os.getcwd(), "frontend", "index.html")),
        os.path.abspath(os.path.join(os.getcwd(), "static", "index.html")),
        os.path.abspath(os.path.join(os.getcwd(), "dist", "index.html"))
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

@app.get("/")
def serve_home():
    index_file = find_index_file()
    if index_file and os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Ajio Flash Deals API is online. Access /docs or static dashboard."}

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse({"error": "API route not found"}, status_code=404)
    # Check if a static asset/data file matches safely without directory traversal
    for base_dir in [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static")),
        os.path.abspath(os.path.join(os.getcwd(), "dist")),
        os.path.abspath(os.path.join(os.getcwd(), "frontend")),
    ]:
        if not os.path.exists(base_dir):
            continue
        try:
            base_resolved = Path(base_dir).resolve()
            target_candidate = (base_resolved / full_path).resolve()
            if target_candidate.is_relative_to(base_resolved) and target_candidate.is_file():
                return FileResponse(str(target_candidate))
        except (ValueError, OSError):
            continue

    index_file = find_index_file()
    if index_file and os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"error": "Resource not found"}, status_code=404)

