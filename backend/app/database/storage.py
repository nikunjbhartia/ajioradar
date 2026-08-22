import os
import sqlite3
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
try:
    from app.models.schemas import VerifiedCampaign, VerifiedProductDeal, SyncHistoryItem
    from app.core.classifier import classify_campaign
except ImportError:
    from models.schemas import VerifiedCampaign, VerifiedProductDeal, SyncHistoryItem
    from core.classifier import classify_campaign

logger = logging.getLogger("storage")

class DealStorage:
    """
    SQLite WAL Database with in-memory caching, multi-stage category tree support,
    7-day sync audit log history, and bounded upsert policies.
    """
    def __init__(self, db_path: str = "deals.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
            cursor.execute('PRAGMA temp_store=MEMORY;')
            cursor.execute('PRAGMA cache_size=-65536;')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS filtered_campaigns (
                    curated_id TEXT PRIMARY KEY,
                    code TEXT,
                    title TEXT,
                    description TEXT,
                    details_url TEXT,
                    promo_type TEXT,
                    department TEXT,
                    brands TEXT,
                    min_realized_discount REAL,
                    max_realized_discount REAL,
                    min_price REAL,
                    max_price REAL,
                    min_base_needed REAL,
                    applied_filter_tier TEXT,
                    has_70_plus_verified INTEGER,
                    is_standalone_deal INTEGER,
                    total_verified_skus INTEGER,
                    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS verified_products (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    brand TEXT,
                    category TEXT,
                    department TEXT,
                    mrp REAL,
                    selling_price REAL,
                    final_price REAL,
                    base_discount_percent REAL,
                    net_discount_percent REAL,
                    formula_desc TEXT,
                    coupon_code TEXT,
                    coupon_slug TEXT,
                    product_url TEXT,
                    image_url TEXT,
                    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_history (
                    sync_id TEXT PRIMARY KEY,
                    timestamp REAL,
                    formatted_time TEXT,
                    duration_seconds REAL,
                    added_coupons TEXT,
                    updated_coupons TEXT,
                    removed_coupons TEXT,
                    added_count INTEGER,
                    updated_count INTEGER,
                    removed_count INTEGER,
                    active_70_count INTEGER,
                    total_campaigns INTEGER,
                    total_deals INTEGER,
                    highlights TEXT,
                    changes TEXT
                )
            ''')
            # Indexes on hot filter and sort columns
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_vp_dept_disc ON verified_products(department, net_discount_percent DESC);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_vp_brand ON verified_products(brand);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_vp_cat ON verified_products(category);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fc_code ON filtered_campaigns(code);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fc_dept ON filtered_campaigns(department);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sh_timestamp ON sync_history(timestamp DESC);')

            # Ensure all schema columns exist in existing DBs
            cursor.execute("PRAGMA table_info(verified_products)")
            vp_cols = [c[1] for c in cursor.fetchall()]
            if 'department' not in vp_cols and len(vp_cols) > 0:
                cursor.execute("ALTER TABLE verified_products ADD COLUMN department TEXT")
            if 'formula_desc' not in vp_cols and len(vp_cols) > 0:
                cursor.execute("ALTER TABLE verified_products ADD COLUMN formula_desc TEXT")
            if 'coupon_slug' not in vp_cols and len(vp_cols) > 0:
                cursor.execute("ALTER TABLE verified_products ADD COLUMN coupon_slug TEXT")

            cursor.execute("PRAGMA table_info(sync_history)")
            sh_cols = [c[1] for c in cursor.fetchall()]
            if 'highlights' not in sh_cols and len(sh_cols) > 0:
                cursor.execute("ALTER TABLE sync_history ADD COLUMN highlights TEXT")
            if 'changes' not in sh_cols and len(sh_cols) > 0:
                cursor.execute("ALTER TABLE sync_history ADD COLUMN changes TEXT")
            if 'active_codes_count' not in sh_cols and len(sh_cols) > 0:
                cursor.execute("ALTER TABLE sync_history ADD COLUMN active_codes_count INTEGER")
            if 'total_codes_count' not in sh_cols and len(sh_cols) > 0:
                cursor.execute("ALTER TABLE sync_history ADD COLUMN total_codes_count INTEGER")
            if 'active_coupons' not in sh_cols and len(sh_cols) > 0:
                cursor.execute("ALTER TABLE sync_history ADD COLUMN active_coupons TEXT")
            if 'department_breakdown' not in sh_cols and len(sh_cols) > 0:
                cursor.execute("ALTER TABLE sync_history ADD COLUMN department_breakdown TEXT")
            conn.commit()

    def save_campaigns(self, campaigns: List[Dict[str, Any]], duration_seconds: float = 0.0) -> SyncHistoryItem:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 1. Fetch previous baseline state aggregated per clean coupon code
            previous_coupons = {}
            try:
                cursor.execute('''
                    SELECT 
                        UPPER(TRIM(code)) as clean_code,
                        MAX(has_70_plus_verified) as has_70,
                        MAX(max_realized_discount) as max_disc,
                        SUM(total_verified_skus) as skus,
                        MIN(title) as title
                    FROM filtered_campaigns
                    WHERE code IS NOT NULL AND TRIM(code) != ''
                    GROUP BY clean_code
                ''')
                for r in cursor.fetchall():
                    previous_coupons[r['clean_code']] = {
                        'code': r['clean_code'],
                        'has_70': bool(r['has_70']),
                        'max_disc': float(r['max_disc'] or 0.0),
                        'skus': int(r['skus'] or 0),
                        'title': r['title'] or r['clean_code']
                    }
            except Exception as e:
                logger.debug(f"Delta baseline fetch error: {e}")

            # 2. Upsert newly validated campaigns
            for c in campaigns:
                cursor.execute('''
                    INSERT OR REPLACE INTO filtered_campaigns (
                        curated_id, code, title, description, details_url,
                        promo_type, department, brands, min_realized_discount,
                        max_realized_discount, min_price, max_price, min_base_needed,
                        applied_filter_tier, has_70_plus_verified, is_standalone_deal,
                        total_verified_skus, scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    c['curated_id'], c.get('code', 'PROMO'), c.get('title', ''), c.get('description', ''), c.get('details_url', ''),
                    c.get('promo_type', 'Promo Voucher'), c.get('department', 'Multi-Category'), c.get('brands', ''),
                    c.get('min_realized_discount', 0.0), c.get('max_realized_discount', 0.0),
                    c.get('min_price', 0.0), c.get('max_price', 0.0), c.get('min_base_needed', 0.0),
                    c.get('applied_filter_tier', 'Verified'), 1 if c.get('has_70_plus_verified') else 0,
                    1 if c.get('is_standalone_deal') else 0, c.get('total_verified_skus', 0)
                ))

            # 3. Fetch updated current coupon state from database
            current_coupons = {}
            cursor.execute('''
                SELECT 
                    UPPER(TRIM(code)) as clean_code,
                    MAX(has_70_plus_verified) as has_70,
                    MAX(max_realized_discount) as max_disc,
                    SUM(total_verified_skus) as skus,
                    MIN(title) as title
                FROM filtered_campaigns
                WHERE code IS NOT NULL AND TRIM(code) != ''
                GROUP BY clean_code
            ''')
            for r in cursor.fetchall():
                current_coupons[r['clean_code']] = {
                    'code': r['clean_code'],
                    'has_70': bool(r['has_70']),
                    'max_disc': float(r['max_disc'] or 0.0),
                    'skus': int(r['skus'] or 0),
                    'title': r['title'] or r['clean_code']
                }

            SYSTEM_EXCLUDED_CODES = {'DIRECT_CLEARANCE', 'PREMIUM_OFFER', 'FLASH_STACK_20', 'FLASH_STACK_25', 'FLASH_STACK_30', 'INSTANT_OFFER'}
            added_codes = []
            updated_codes = []
            removed_codes = []
            detailed_changes = []

            # Compare deltas only on meaningful shifts
            for code, curr in current_coupons.items():
                if code in SYSTEM_EXCLUDED_CODES:
                    continue
                prev = previous_coupons.get(code)
                if prev is None:
                    if curr['has_70']:
                        added_codes.append(code)
                        detailed_changes.append({
                            "type": "new_campaign",
                            "code": code,
                            "title": curr['title'],
                            "detail": f"Discovered new collection ({curr['max_disc']:.0f}% max off, {curr['skus']} verified deals)",
                            "before": "New Code",
                            "after": f"{curr['max_disc']:.1f}% ({curr['skus']} items)",
                            "badge": "NEW"
                        })
                else:
                    if not prev['has_70'] and curr['has_70']:
                        added_codes.append(code)
                        detailed_changes.append({
                            "type": "new_campaign",
                            "code": code,
                            "title": curr['title'],
                            "detail": f"Voucher boosted to ≥70%: {prev['max_disc']:.0f}% → {curr['max_disc']:.0f}% ({curr['skus']} items ≥70%)",
                            "before": f"{prev['max_disc']:.1f}% (Sub-70%)",
                            "after": f"{curr['max_disc']:.1f}% ({curr['skus']} items)",
                            "badge": "NEW"
                        })
                    elif prev['has_70'] and not curr['has_70']:
                        removed_codes.append(code)
                        detailed_changes.append({
                            "type": "expired",
                            "code": code,
                            "title": curr['title'],
                            "detail": f"Discount fell below 70% threshold ({prev['max_disc']:.0f}% → {curr['max_disc']:.0f}%, 0 qualifying steals)",
                            "before": f"{prev['max_disc']:.1f}% ({prev['skus']} items)",
                            "after": f"{curr['max_disc']:.1f}% (Sub-70% / Expired)",
                            "badge": "EXPIRED"
                        })
                    elif prev['has_70'] and curr['has_70']:
                        disc_diff = curr['max_disc'] - prev['max_disc']
                        sku_diff = curr['skus'] - prev['skus']
                        is_material_disc = abs(disc_diff) >= 1.0
                        is_material_sku = abs(sku_diff) >= 10 and (abs(sku_diff) / max(1, prev['skus'])) >= 0.20
                        if is_material_disc or is_material_sku:
                            updated_codes.append(code)
                            diff_parts = []
                            if is_material_disc:
                                diff_parts.append(f"Discount {prev['max_disc']:.0f}% → {curr['max_disc']:.0f}% ({'+' if disc_diff > 0 else ''}{disc_diff:.0f}%)")
                            if is_material_sku:
                                diff_parts.append(f"Catalog {'+' if sku_diff > 0 else ''}{sku_diff} deals ({prev['skus']} → {curr['skus']})")
                            detailed_changes.append({
                                "type": "updated",
                                "code": code,
                                "title": curr['title'],
                                "detail": " · ".join(diff_parts),
                                "before": f"{prev['max_disc']:.1f}% ({prev['skus']} items)",
                                "after": f"{curr['max_disc']:.1f}% ({curr['skus']} items)",
                                "badge": "UPDATED"
                            })

            for code, prev in previous_coupons.items():
                if code in SYSTEM_EXCLUDED_CODES:
                    continue
                if code not in current_coupons and prev['has_70'] and code not in removed_codes and code not in added_codes and code not in updated_codes:
                    removed_codes.append(code)
                    detailed_changes.append({
                        "type": "expired",
                        "code": code,
                        "title": prev['title'],
                        "detail": "Promotion no longer active on Ajio (delisted / inactive)",
                        "before": f"{prev['max_disc']:.1f}% ({prev['skus']} items)",
                        "after": "Delisted / Inactive",
                        "badge": "DELISTED"
                    })

            # Query live comprehensive database metrics
            try:
                cursor.execute('SELECT COUNT(*), SUM(CASE WHEN has_70_plus_verified = 1 THEN 1 ELSE 0 END) FROM filtered_campaigns')
                tot_camps_row = cursor.fetchone()
                total_collections = (tot_camps_row[0] or len(campaigns)) if tot_camps_row else len(campaigns)
                active_collections = (tot_camps_row[1] or 0) if tot_camps_row else sum(1 for c in campaigns if c.get('has_70_plus_verified'))
            except Exception:
                total_collections = len(campaigns)
                active_collections = sum(1 for c in campaigns if c.get('has_70_plus_verified'))

            active_codes_count = sum(1 for c in current_coupons.values() if c['has_70'])
            total_codes_count = len(current_coupons)

            try:
                cursor.execute('SELECT COUNT(*) FROM verified_products WHERE net_discount_percent >= 70.0')
                total_verified_deals = cursor.fetchone()[0] or 0
            except Exception:
                total_verified_deals = 0

            try:
                cursor.execute('''
                    SELECT DISTINCT UPPER(TRIM(code)) as clean_code, MAX(max_realized_discount) as max_disc
                    FROM filtered_campaigns 
                    WHERE has_70_plus_verified = 1 AND code IS NOT NULL AND TRIM(code) != '' AND code != 'DIRECT_CLEARANCE'
                    GROUP BY clean_code
                    ORDER BY max_disc DESC
                    LIMIT 30
                ''')
                active_coupons_list = [r[0] for r in cursor.fetchall() if r[0]]
            except Exception:
                active_coupons_list = [code for code, c in current_coupons.items() if c['has_70']][:30]

            try:
                cursor.execute('''
                    SELECT department, COUNT(*) as cnt 
                    FROM verified_products 
                    WHERE net_discount_percent >= 70.0 
                    GROUP BY department 
                    ORDER BY cnt DESC
                ''')
                dept_breakdown = {r[0]: r[1] for r in cursor.fetchall() if r[0]}
            except Exception:
                dept_breakdown = {}

            # Build high-level highlights
            highlights = []
            if added_codes:
                highlights.append(f"🔥 Discovered {len(added_codes)} fresh promo vouchers: {', '.join(added_codes[:4])}{' +' + str(len(added_codes)-4) + ' more' if len(added_codes) > 4 else ''}")
            if updated_codes:
                highlights.append(f"📈 Re-priced & updated {len(updated_codes)} promotional collections: {', '.join(updated_codes[:4])}{' +' + str(len(updated_codes)-4) + ' more' if len(updated_codes) > 4 else ''}")
            if removed_codes:
                highlights.append(f"📉 {len(removed_codes)} promotions expired/sub-70%: {', '.join(removed_codes[:4])}")
            if not added_codes and not updated_codes and not removed_codes:
                highlights.append(f"✨ 100% active integrity: {active_collections}/{total_collections} collections & {active_codes_count}/{total_codes_count} promo codes verified live ({total_verified_deals:,} items ≥70%)")

            # 4. Record sync history event
            now = time.time()
            sync_id = f"sync_{int(now)}"
            formatted_time = time.strftime("%b %d, %I:%M %p", time.localtime(now))

            delta_record = SyncHistoryItem(
                sync_id=sync_id,
                timestamp=now,
                formatted_time=formatted_time,
                duration_seconds=round(duration_seconds, 2),
                added_coupons=added_codes[:30],
                updated_coupons=updated_codes[:30],
                removed_coupons=removed_codes[:30],
                added_count=len(added_codes),
                updated_count=len(updated_codes),
                removed_count=len(removed_codes),
                active_70_count=active_collections,
                total_campaigns=total_collections,
                active_codes_count=active_codes_count,
                total_codes_count=total_codes_count,
                total_deals=total_verified_deals,
                active_coupons=active_coupons_list,
                department_breakdown=dept_breakdown,
                highlights=highlights,
                changes=detailed_changes[:60]
            )

            cursor.execute('''
                INSERT OR REPLACE INTO sync_history (
                    sync_id, timestamp, formatted_time, duration_seconds,
                    added_coupons, updated_coupons, removed_coupons,
                    added_count, updated_count, removed_count,
                    active_70_count, total_campaigns, total_deals,
                    highlights, changes,
                    active_codes_count, total_codes_count, active_coupons, department_breakdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                delta_record.sync_id, delta_record.timestamp, delta_record.formatted_time,
                delta_record.duration_seconds,
                json.dumps(delta_record.added_coupons),
                json.dumps(delta_record.updated_coupons),
                json.dumps(delta_record.removed_coupons),
                delta_record.added_count, delta_record.updated_count, delta_record.removed_count,
                delta_record.active_70_count, delta_record.total_campaigns, delta_record.total_deals,
                json.dumps(delta_record.highlights),
                json.dumps(delta_record.changes),
                delta_record.active_codes_count, delta_record.total_codes_count,
                json.dumps(delta_record.active_coupons),
                json.dumps(delta_record.department_breakdown)
            ))

            # 5. Prune history older than 7 days (7 * 86400 = 604800s)
            seven_days_ago = now - (7 * 86400)
            cursor.execute('DELETE FROM sync_history WHERE timestamp < ?', (seven_days_ago,))

            conn.commit()
            return delta_record

    def save_products(self, products: List[Dict[str, Any]]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for p in products:
                cursor.execute('''
                    INSERT OR REPLACE INTO verified_products (
                        id, name, brand, category, department, mrp, selling_price,
                        final_price, base_discount_percent, net_discount_percent,
                        formula_desc, coupon_code, coupon_slug, product_url, image_url, scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    p['id'], p['name'], p['brand'], p['category'], p.get('department', 'Multi-Category'),
                    p['mrp'], p['selling_price'], p['final_price'],
                    p['base_discount_percent'], p['net_discount_percent'],
                    p.get('formula_desc', ''), p['coupon_code'], p.get('coupon_slug', ''),
                    p['product_url'], p.get('image_url', '')
                ))

            # Update deal count in latest sync history item
            try:
                cursor.execute('''
                    UPDATE sync_history 
                    SET total_deals = (SELECT COUNT(*) FROM verified_products WHERE net_discount_percent >= 70.0) 
                    WHERE sync_id = (SELECT sync_id FROM sync_history ORDER BY timestamp DESC LIMIT 1)
                ''')
            except Exception:
                pass

            conn.commit()

        # 1. Prune expired or out-of-stock items unseen for > 7 days
        self.prune_stale_deals(max_age_days=7)

        # 2. Dynamically synthesize campaign collections from newly scanned products
        self.synthesize_campaigns_from_products()

    def prune_stale_deals(self, max_age_days: int = 7):
        """
        Prunes deals that have not been re-verified or present in live sweeps for over max_age_days.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"DELETE FROM verified_products WHERE datetime(scanned_at) < datetime('now', '-{max_age_days} days')")
                conn.commit()
            except Exception as e:
                logger.debug(f"[Storage] Stale deal cleanup note: {e}")

    def synthesize_campaigns_from_products(self):
        """
        Dynamically aggregates all verified clearance products carrying coupon codes
        into first-class Verified Campaigns. Ensures 100% dynamic coupon discovery from cold boot.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT 
                        coupon_code,
                        GROUP_CONCAT(DISTINCT department) as depts_agg,
                        GROUP_CONCAT(DISTINCT brand) as brand_agg,
                        MIN(net_discount_percent) as min_disc,
                        MAX(net_discount_percent) as max_disc,
                        MIN(final_price) as min_p,
                        MAX(final_price) as max_p,
                        COUNT(*) as sku_cnt,
                        coupon_slug
                    FROM verified_products
                    WHERE coupon_code IS NOT NULL AND coupon_code != '' AND net_discount_percent >= 70.0
                    GROUP BY coupon_code
                ''')
                rows = cursor.fetchall()
                for r in rows:
                    code = r[0].strip().upper()
                    if not code or len(code) < 2:
                        continue
                    depts_raw = r[1] or ""
                    brands = r[2] or ""
                    min_disc = round(r[3], 1) if r[3] else 70.0
                    max_disc = round(r[4], 1) if r[4] else 70.0
                    min_p = round(r[5], 2) if r[5] else 0.0
                    max_p = round(r[6], 2) if r[6] else 0.0
                    sku_cnt = r[7]
                    
                    curated_id = f"dyn-{code.lower()}"
                    title = f"{code} - Live Verified Clearance Collection"
                    description = f"Autonomous live aggregated collection with {sku_cnt} verified items up to {max_disc}% off."
                    details_url = f"https://www.ajio.com/c/83?query=%3Adiscount-desc%3Adiscountranges%3A60%25%20and%20above%3Apromotions%3A{code}"

                    seed_dept = depts_raw if ("," not in depts_raw and depts_raw) else "Multi-Category"
                    dept = classify_campaign(
                        title=title,
                        desc=description,
                        brands_str=brands,
                        slug=code.lower(),
                        seed_dept=seed_dept
                    )

                    cursor.execute('''
                        INSERT OR REPLACE INTO filtered_campaigns (
                            curated_id, code, title, description, details_url, promo_type,
                            department, brands, min_realized_discount, max_realized_discount,
                            min_price, max_price, min_base_needed, applied_filter_tier,
                            has_70_plus_verified, is_standalone_deal, total_verified_skus, scanned_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        curated_id, code, title, description, details_url, "Verified Promo Sweep",
                        dept, brands, min_disc, max_disc,
                        min_p, max_p, 0.0, "Live Feed",
                        1, 1, sku_cnt
                    ))
                conn.commit()
            except Exception as e:
                logger.debug(f"[Storage] Campaign synthesis note: {e}")

    def get_sync_history(self, days: int = 7, limit: int = 50) -> List[SyncHistoryItem]:
        min_time = time.time() - (days * 86400)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM sync_history
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (min_time, limit))
            rows = cursor.fetchall()
            
            history = []
            for r in rows:
                try:
                    added = json.loads(r['added_coupons']) if r['added_coupons'] else []
                except Exception:
                    added = []
                try:
                    updated = json.loads(r['updated_coupons']) if r['updated_coupons'] else []
                except Exception:
                    updated = []
                try:
                    removed = json.loads(r['removed_coupons']) if r['removed_coupons'] else []
                except Exception:
                    removed = []

                try:
                    highlights = json.loads(r['highlights']) if 'highlights' in r.keys() and r['highlights'] else []
                except Exception:
                    highlights = []

                try:
                    changes = json.loads(r['changes']) if 'changes' in r.keys() and r['changes'] else []
                except Exception:
                    changes = []

                try:
                    active_coups = json.loads(r['active_coupons']) if 'active_coupons' in r.keys() and r['active_coupons'] else []
                except Exception:
                    active_coups = []

                try:
                    dept_bd = json.loads(r['department_breakdown']) if 'department_breakdown' in r.keys() and r['department_breakdown'] else {}
                except Exception:
                    dept_bd = {}

                active_codes_cnt = r['active_codes_count'] if 'active_codes_count' in r.keys() and r['active_codes_count'] is not None else 0
                total_codes_cnt = r['total_codes_count'] if 'total_codes_count' in r.keys() and r['total_codes_count'] is not None else 0

                history.append(SyncHistoryItem(
                    sync_id=r['sync_id'],
                    timestamp=r['timestamp'],
                    formatted_time=r['formatted_time'],
                    duration_seconds=r['duration_seconds'],
                    added_coupons=added,
                    updated_coupons=updated,
                    removed_coupons=removed,
                    added_count=r['added_count'] if 'added_count' in r.keys() else len(added),
                    updated_count=r['updated_count'] if 'updated_count' in r.keys() else len(updated),
                    removed_count=r['removed_count'] if 'removed_count' in r.keys() else len(removed),
                    active_70_count=r['active_70_count'],
                    total_campaigns=r['total_campaigns'],
                    active_codes_count=active_codes_cnt,
                    total_codes_count=total_codes_cnt,
                    total_deals=r['total_deals'],
                    active_coupons=active_coups,
                    department_breakdown=dept_bd,
                    highlights=highlights,
                    changes=changes
                ))
            return history

    def get_latest_sync_delta(self) -> Optional[SyncHistoryItem]:
        hist = self.get_sync_history(days=7, limit=1)
        return hist[0] if hist else None

    def get_filtered_campaigns(
        self,
        search: Optional[str] = None,
        departments: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        brands: Optional[List[str]] = None,
        min_discount: Optional[float] = None,
        only_verified_70: bool = True,
        is_standalone_only: bool = False,
        sort_by: str = "discount_desc"
    ) -> List[VerifiedCampaign]:
        conditions = []
        params: List[Any] = []

        if only_verified_70:
            conditions.append("has_70_plus_verified = 1")
            conditions.append("total_verified_skus > 0")

        if is_standalone_only:
            conditions.append("is_standalone_deal = 1")

        if min_discount:
            conditions.append("max_realized_discount >= ?")
            params.append(min_discount)

        if search:
            for token in search.strip().split():
                p_val = f"%{token}%"
                conditions.append("(code LIKE ? OR title LIKE ? OR description LIKE ? OR curated_id LIKE ? OR brands LIKE ? OR department LIKE ?)")
                params.extend([p_val, p_val, p_val, p_val, p_val, p_val])

        if departments and len(departments) > 0 and "all" not in [d.lower() for d in departments]:
            dept_clauses = ["department LIKE ?" for _ in departments]
            conditions.append(f"({' OR '.join(dept_clauses)})")
            for d in departments:
                params.append(f"%{d}%")

        if categories and len(categories) > 0 and "all" not in [c.lower() for c in categories]:
            cat_clauses = ["(title LIKE ? OR description LIKE ? OR curated_id LIKE ? OR department LIKE ?)" for _ in categories]
            conditions.append(f"({' OR '.join(cat_clauses)})")
            for c in categories:
                p_c = f"%{c}%"
                params.extend([p_c, p_c, p_c, p_c])

        if brands and len(brands) > 0 and "all" not in [b.lower() for b in brands]:
            brand_clauses = ["brands LIKE ?" for _ in brands]
            conditions.append(f"({' OR '.join(brand_clauses)})")
            for b in brands:
                params.append(f"%{b}%")

        sort_sql = "max_realized_discount DESC, total_verified_skus DESC"
        if sort_by == "skus_desc":
            sort_sql = "total_verified_skus DESC, max_realized_discount DESC"
        elif sort_by == "code_asc":
            sort_sql = "code ASC"
        elif sort_by == "price_asc":
            sort_sql = "min_price ASC, max_realized_discount DESC"

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM filtered_campaigns {where_clause} ORDER BY {sort_sql}"

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                VerifiedCampaign(
                    curated_id=r['curated_id'],
                    code=r['code'],
                    title=r['title'],
                    description=r['description'],
                    details_url=r['details_url'],
                    promo_type=r['promo_type'],
                    department=r['department'],
                    brands=r['brands'],
                    brand_list=[b.strip() for b in r['brands'].split(',') if b.strip()] if r['brands'] else [],
                    min_realized_discount=r['min_realized_discount'],
                    max_realized_discount=r['max_realized_discount'],
                    min_price=r['min_price'],
                    max_price=r['max_price'],
                    min_base_needed=r['min_base_needed'],
                    applied_filter_tier=r['applied_filter_tier'],
                    has_70_plus_verified=bool(r['has_70_plus_verified']),
                    is_standalone_deal=bool(r['is_standalone_deal']),
                    total_verified_skus=r['total_verified_skus'],
                    scanned_at=str(r['scanned_at'])
                )
                for r in rows
            ]

    def get_verified_products(
        self,
        search: Optional[str] = None,
        departments: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        brands: Optional[List[str]] = None,
        min_discount: float = 70.0,
        max_price: Optional[float] = None,
        sort_by: str = "discount_desc",
        limit: int = 100,
        offset: int = 0
    ) -> List[VerifiedProductDeal]:
        conditions = ["net_discount_percent >= ?"]
        params: List[Any] = [min_discount]

        if search:
            for token in search.strip().split():
                p_val = f"%{token}%"
                conditions.append("(name LIKE ? OR brand LIKE ? OR coupon_code LIKE ? OR category LIKE ? OR department LIKE ?)")
                params.extend([p_val, p_val, p_val, p_val, p_val])

        if departments and len(departments) > 0 and "all" not in [d.lower() for d in departments]:
            dept_clauses = ["department LIKE ?" for _ in departments]
            conditions.append(f"({' OR '.join(dept_clauses)})")
            for d in departments:
                params.append(f"%{d}%")

        if categories and len(categories) > 0 and "all" not in [c.lower() for c in categories]:
            cat_clauses = ["(category LIKE ? OR name LIKE ?)" for _ in categories]
            conditions.append(f"({' OR '.join(cat_clauses)})")
            for c in categories:
                p_c = f"%{c}%"
                params.extend([p_c, p_c])

        if brands and len(brands) > 0 and "all" not in [b.lower() for b in brands]:
            brand_clauses = ["brand LIKE ?" for _ in brands]
            conditions.append(f"({' OR '.join(brand_clauses)})")
            for b in brands:
                params.append(f"%{b}%")

        if max_price:
            conditions.append("final_price <= ?")
            params.append(max_price)

        sort_sql = "net_discount_percent DESC, final_price ASC"
        if sort_by == "price_asc":
            sort_sql = "final_price ASC"
        elif sort_by == "price_desc":
            sort_sql = "final_price DESC"
        elif sort_by == "mrp_desc":
            sort_sql = "mrp DESC"
        elif sort_by == "boost_desc":
            sort_sql = "(net_discount_percent - base_discount_percent) DESC, net_discount_percent DESC"
        elif sort_by == "base_desc":
            sort_sql = "base_discount_percent DESC, net_discount_percent DESC"

        query_sql = f'''
            SELECT * FROM verified_products
            WHERE {' AND '.join(conditions)}
            ORDER BY {sort_sql}
            LIMIT ? OFFSET ?
        '''
        params.extend([limit, offset])

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            return [
                VerifiedProductDeal(
                    id=r['id'],
                    name=r['name'],
                    brand=r['brand'],
                    category=r['category'],
                    department=r['department'] if 'department' in r.keys() else "Multi-Category",
                    mrp=r['mrp'],
                    selling_price=r['selling_price'],
                    final_price=r['final_price'] if 'final_price' in r.keys() else r['selling_price'],
                    base_discount_percent=r['base_discount_percent'],
                    net_discount_percent=r['net_discount_percent'],
                    formula_desc=r['formula_desc'] if 'formula_desc' in r.keys() else "",
                    coupon_code=r['coupon_code'],
                    product_url=r['product_url'] if 'product_url' in r.keys() else f"https://www.ajio.com/p/{r['id']}",
                    image_url=r['image_url'] if 'image_url' in r.keys() else "",
                    scanned_at=str(r['scanned_at'])
                )
                for r in rows
            ]

    def get_filtered_deals(self, *args, **kwargs):
        return self.get_verified_products(*args, **kwargs)

    def get_taxonomy(self) -> Dict[str, Any]:
        tax_path = os.path.join(os.path.dirname(__file__), "taxonomy_master.json")
        if os.path.exists(tax_path):
            with open(tax_path) as f:
                return json.load(f)
        return {}

    def get_brands(self) -> List[str]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            brands = set()
            try:
                cursor.execute("SELECT DISTINCT brands FROM filtered_campaigns WHERE brands IS NOT NULL AND brands != ''")
                for r in cursor.fetchall():
                    for b in r[0].split(','):
                        cl = b.strip()
                        if cl: brands.add(cl)
            except Exception:
                pass

            try:
                cursor.execute("SELECT DISTINCT brand FROM verified_products WHERE brand IS NOT NULL AND brand != ''")
                for r in cursor.fetchall():
                    if r[0]: brands.add(r[0].strip())
            except Exception:
                pass

            return sorted(list(brands))

    def get_departments(self) -> List[str]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            depts = set()
            try:
                cursor.execute("SELECT DISTINCT department FROM filtered_campaigns WHERE department IS NOT NULL AND department != ''")
                for r in cursor.fetchall():
                    if r[0]: depts.add(r[0].strip())
            except Exception:
                pass
            return sorted(list(depts))

    def get_stats(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('SELECT COUNT(*) FROM filtered_campaigns WHERE has_70_plus_verified = 1')
                camp_70 = cursor.fetchone()[0]
            except Exception:
                camp_70 = 0

            try:
                cursor.execute('SELECT COUNT(*) FROM filtered_campaigns')
                total_camps = cursor.fetchone()[0]
            except Exception:
                total_camps = 0

            try:
                cursor.execute('SELECT COUNT(*) FROM verified_products WHERE net_discount_percent >= 70')
                total_prods_70 = cursor.fetchone()[0]
            except Exception:
                total_prods_70 = 0

            try:
                cursor.execute('''
                    SELECT 
                        COUNT(DISTINCT UPPER(TRIM(code))),
                        COUNT(DISTINCT CASE WHEN has_70_plus_verified = 1 THEN UPPER(TRIM(code)) END)
                    FROM filtered_campaigns
                    WHERE code IS NOT NULL AND TRIM(code) != ''
                ''')
                tot_codes, act_codes = cursor.fetchone()
            except Exception:
                tot_codes, act_codes = 0, 0

            return {
                "verified_70_plus_campaigns": camp_70,
                "total_campaigns": total_camps,
                "verified_70_plus_codes": act_codes,
                "total_codes": tot_codes,
                "verified_70_plus_products": total_prods_70,
                "total_brands": len(self.get_brands()),
                "total_departments": len(self.get_departments())
            }
