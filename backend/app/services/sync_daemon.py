import asyncio
import time
import os
import sys
import logging
from typing import Dict, List, Any, Optional
from app.engines.campaign_harvester import CampaignHarvester
from app.engines.deal_validator import DealValidatorEngine
from app.engines.category_crawler import UniversalCategoryCrawler
from app.database.storage import DealStorage
from app.models.schemas import SyncHistoryItem

logger = logging.getLogger("sync_daemon")

class ContinuousSyncDaemon:
    def __init__(self, poll_interval_seconds: int = 1800):  # 30 minutes safe default
        self.poll_interval = poll_interval_seconds
        self.is_running = False
        self.last_sync_time: Optional[float] = None
        self.last_sync_duration: float = 0.0
        self.engine = DealValidatorEngine("deals.db")
        self.category_crawler = UniversalCategoryCrawler("deals.db")
        self.storage = DealStorage("deals.db")
        self.in_memory_campaigns: List[Dict[str, Any]] = []
        self.in_memory_deals: List[Dict[str, Any]] = []
        self.latest_delta: Optional[SyncHistoryItem] = self.storage.get_latest_sync_delta()
        self.in_memory_history: List[SyncHistoryItem] = self.storage.get_sync_history(days=7, limit=50)

    def perform_full_sync(self):
        t0 = time.time()
        logger.info("[SyncDaemon] Starting scheduled full discovery & dual validation sweep (Campaigns + Universal Categories)...")
        try:
            # 1. Harvest & Validate dynamic campaign seeds (Sitemaps + Top Storefronts)
            seeds = CampaignHarvester.harvest_all_campaign_seeds()
            res = self.engine.run_full_validation_cycle(seeds, max_workers=15)
            
            # 2. Universal Navigation Category Sweep across all 498 subcategory seeds
            cat_deals = self.category_crawler.run_full_category_sweep(max_workers=15)
            
            # 3. Forensic database sanitization
            self.storage.sanitize_database()

            # 4. Pull merged products from storage
            merged_deals = self.storage.get_verified_products(min_discount=70.0, limit=25000)

            self.in_memory_campaigns = res['campaigns']
            self.in_memory_deals = [d.model_dump() for d in merged_deals]
            self.latest_delta = res.get('delta')
            self.in_memory_history = self.storage.get_sync_history(days=7, limit=50)
            self.last_sync_time = time.time()
            self.last_sync_duration = round(time.time() - t0, 2)

            # 4. Automatically export fresh edge static bundle
            try:
                export_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "export_cloudflare.py"))
                if os.path.exists(export_script):
                    import subprocess
                    subprocess.run([sys.executable, export_script], check=False)
            except Exception as exp_err:
                logger.debug(f"[SyncDaemon] Static export note: {exp_err}")

            # 5. Backup SQLite database to Cloudflare R2 bucket for permanent persistence
            try:
                from app.database.r2_sync import backup_database_to_r2
                db_path = self.storage.db_path
                backup_database_to_r2(local_path=db_path)
            except Exception as r2_err:
                logger.debug(f"[SyncDaemon] R2 backup note: {r2_err}")

            logger.info(f"[SyncDaemon] Dual sync complete in {self.last_sync_duration}s. Total campaigns: {len(self.in_memory_campaigns)}, Total 70%+ items across categories: {len(self.in_memory_deals)}.")
        except Exception as e:
            logger.error(f"[SyncDaemon] Sync error: {e}")

    async def start_background_loop(self):
        self.is_running = True
        logger.info(f"[SyncDaemon] Active with interval = {self.poll_interval}s ({self.poll_interval/60:.1f} mins).")
        while self.is_running:
            try:
                await asyncio.sleep(self.poll_interval)
                await asyncio.to_thread(self.perform_full_sync)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SyncDaemon] Loop exception: {e}")
                await asyncio.sleep(60)

daemon_instance = ContinuousSyncDaemon(poll_interval_seconds=1800)
