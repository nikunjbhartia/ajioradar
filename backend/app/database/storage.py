import os
import sqlite3
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
try:
    from app.models.schemas import VerifiedCampaign, VerifiedProductDeal, SyncHistoryItem
except ImportError:
    from models.schemas import VerifiedCampaign, VerifiedProductDeal, SyncHistoryItem

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
            conn.commit()

    def save_campaigns(self, campaigns: List[Dict[str, Any]], duration_seconds: float = 0.0) -> SyncHistoryItem:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 1. Fetch previous state to calculate delta audit trail
            previous_map = {}
            try:
                cursor.execute('SELECT curated_id, code, has_70_plus_verified, max_realized_discount, total_verified_skus FROM filtered_campaigns')
                for r in cursor.fetchall():
                    previous_map[r['curated_id']] = {
                        'code': r['code'],
                        'has_70': bool(r['has_70_plus_verified']),
                        'max_disc': r['max_realized_discount'],
                        'skus': r['total_verified_skus']
                    }
            except Exception as e:
                logger.debug(f"Delta baseline fetch error: {e}")

            added_codes = []
            updated_codes = []
            removed_codes = []
            detailed_changes = []
            new_curated_ids = set()

            for c in campaigns:
                c_id = c['curated_id']
                code = c.get('code', 'PROMO')
                title = c.get('title', code)
                new_curated_ids.add(c_id)
                has_70 = bool(c.get('has_70_plus_verified', False))
                curr_disc = float(c.get('max_realized_discount', 0.0) or 0.0)
                curr_skus = int(c.get('total_verified_skus', 0) or 0)

                if c_id not in previous_map:
                    if code and code not in added_codes:
                        added_codes.append(code)
                    if has_70:
                        detailed_changes.append({
                            "type": "new_campaign",
                            "code": code,
                            "title": title,
                            "detail": f"Discovered new collection: {title} ({curr_disc:.1f}% max off, {curr_skus} verified items)",
                            "before": "New Entry",
                            "after": f"{curr_disc:.1f}% Max ({curr_skus} items)",
                            "badge": "NEW"
                        })
                else:
                    prev = previous_map[c_id]
                    prev_disc = float(prev.get('max_disc', 0.0) or 0.0)
                    prev_skus = int(prev.get('skus', 0) or 0)

                    if prev['has_70'] and not has_70:
                        if code and code not in removed_codes:
                            removed_codes.append(code)
                        detailed_changes.append({
                            "type": "expired",
                            "code": code,
                            "title": title,
                            "detail": f"Discount dropped from {prev_disc:.1f}% to {curr_disc:.1f}% (sub-70% / degraded)",
                            "before": f"{prev_disc:.1f}% ({prev_skus} items)",
                            "after": f"{curr_disc:.1f}% (Sub-70% / Expired)",
                            "badge": "EXPIRED"
                        })
                    elif abs(prev_disc - curr_disc) >= 0.1 or prev_skus != curr_skus:
                        if code and code not in updated_codes:
                            updated_codes.append(code)
                        
                        diff_parts = []
                        disc_diff = curr_disc - prev_disc
                        sku_diff = curr_skus - prev_skus
                        if abs(disc_diff) >= 0.1:
                            diff_parts.append(f"Discount {prev_disc:.1f}% → {curr_disc:.1f}% ({'+' if disc_diff > 0 else ''}{disc_diff:.1f}%)")
                        if sku_diff != 0:
                            diff_parts.append(f"Catalog {'+' if sku_diff > 0 else ''}{sku_diff} items ({prev_skus} → {curr_skus})")
                        
                        detailed_changes.append({
                            "type": "updated",
                            "code": code,
                            "title": title,
                            "detail": " · ".join(diff_parts) if diff_parts else "Catalog refreshed",
                            "before": f"{prev_disc:.1f}% ({prev_skus} items)",
                            "after": f"{curr_disc:.1f}% ({curr_skus} items)",
                            "badge": "UPDATED"
                        })

                # Upsert campaign
                cursor.execute('''
                    INSERT OR REPLACE INTO filtered_campaigns (
                        curated_id, code, title, description, details_url,
                        promo_type, department, brands, min_realized_discount,
                        max_realized_discount, min_price, max_price, min_base_needed,
                        applied_filter_tier, has_70_plus_verified, is_standalone_deal,
                        total_verified_skus, scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    c['curated_id'], c['code'], c['title'], c['description'], c['details_url'],
                    c['promo_type'], c['department'], c['brands'], c['min_realized_discount'],
                    c['max_realized_discount'], c['min_price'], c['max_price'], c['min_base_needed'],
                    c['applied_filter_tier'], 1 if c['has_70_plus_verified'] else 0,
                    1 if c['is_standalone_deal'] else 0, c['total_verified_skus']
                ))

            # Check if any previous campaigns were removed entirely
            for prev_id, prev in previous_map.items():
                if prev_id not in new_curated_ids and prev.get('has_70'):
                    p_code = prev.get('code', '')
                    if p_code and p_code not in removed_codes:
                        removed_codes.append(p_code)
                    detailed_changes.append({
                        "type": "expired",
                        "code": p_code,
                        "title": p_code,
                        "detail": f"Offer no longer active on Ajio (0 catalog items)",
                        "before": f"{prev.get('max_disc', 0):.1f}% ({prev.get('skus', 0)} items)",
                        "after": "Delisted / Inactive",
                        "badge": "DELISTED"
                    })

            # Build high-level highlights
            highlights = []
            if added_codes:
                highlights.append(f"🔥 Discovered {len(added_codes)} fresh promo vouchers: {', '.join(added_codes[:4])}{' +' + str(len(added_codes)-4) + ' more' if len(added_codes) > 4 else ''}")
            if updated_codes:
                highlights.append(f"📈 Re-priced & updated {len(updated_codes)} promotional collections: {', '.join(updated_codes[:4])}{' +' + str(len(updated_codes)-4) + ' more' if len(updated_codes) > 4 else ''}")
            if removed_codes:
                highlights.append(f"📉 {len(removed_codes)} promotions expired/sub-70%: {', '.join(removed_codes[:4])}")
            if not highlights:
                highlights.append(f"✨ Catalog steady — verified {len(campaigns)} campaign collections & active clearance inventory")

            # 2. Record sync history event
            now = time.time()
            sync_id = f"sync_{int(now)}"
            formatted_time = time.strftime("%b %d, %I:%M %p", time.localtime(now))
            active_70_count = sum(1 for c in campaigns if c.get('has_70_plus_verified'))

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
                active_70_count=active_70_count,
                total_campaigns=len(campaigns),
                total_deals=0,
                highlights=highlights,
                changes=detailed_changes[:60]
            )

            cursor.execute('''
                INSERT OR REPLACE INTO sync_history (
                    sync_id, timestamp, formatted_time, duration_seconds,
                    added_coupons, updated_coupons, removed_coupons,
                    added_count, updated_count, removed_count,
                    active_70_count, total_campaigns, total_deals,
                    highlights, changes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                delta_record.sync_id, delta_record.timestamp, delta_record.formatted_time,
                delta_record.duration_seconds,
                json.dumps(delta_record.added_coupons),
                json.dumps(delta_record.updated_coupons),
                json.dumps(delta_record.removed_coupons),
                delta_record.added_count, delta_record.updated_count, delta_record.removed_count,
                delta_record.active_70_count, delta_record.total_campaigns, 0,
                json.dumps(delta_record.highlights),
                json.dumps(delta_record.changes)
            ))

            # 3. Prune history older than 7 days (7 * 86400 = 604800s)
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

            # Update deal count in latest sync history item if exists
            try:
                cursor.execute('UPDATE sync_history SET total_deals = ? WHERE sync_id = (SELECT sync_id FROM sync_history ORDER BY timestamp DESC LIMIT 1)', (len(products),))
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
                        department,
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
                    dept = r[1] or "Multi-Category"
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
                    total_deals=r['total_deals'],
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

            return {
                "verified_70_plus_campaigns": camp_70,
                "total_campaigns": total_camps,
                "verified_70_plus_products": total_prods_70,
                "total_brands": len(self.get_brands()),
                "total_departments": len(self.get_departments())
            }
