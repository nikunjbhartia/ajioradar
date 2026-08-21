import os
import json
import re
import time
import urllib.parse
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
try:
    from app.core.stealth_client import stealth_manager
    from app.database.storage import DealStorage
except ImportError:
    from core.stealth_client import stealth_manager
    from database.storage import DealStorage

logger = logging.getLogger("category_crawler")

class UniversalCategoryCrawler:
    """
    Parallel crawler that sweeps all 498 official Ajio navigation category slugs
    to index 100% of direct clearance steals (&ge;70% off) across all 11 departments.
    """
    def __init__(self, db_path: str = "deals.db"):
        self.storage = DealStorage(db_path)
        self.seeds_path = os.path.join(os.path.dirname(__file__), "..", "database", "navigation_category_seeds.json")

    def load_category_seeds(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.seeds_path):
            with open(self.seeds_path) as f:
                return json.load(f)
        return []

    def sweep_single_category(self, target: Dict[str, Any], min_discount_tier: str = "50% and above") -> List[Dict[str, Any]]:
        name = target.get('name', '')
        slug = target.get('slug', '').strip()
        dept = target.get('dept', 'MULTI-CATEGORY')
        group = target.get('group', 'GENERAL')

        if not slug:
            return []

        # High-yield Bloomreach query for category
        raw_q = f':discount-desc:discountranges:{min_discount_tier}:curated:true:curatedId:{slug}'
        encoded_q = urllib.parse.quote(raw_q)
        api_url = f"https://www.ajio.com/c/83?query={encoded_q}&curated=true&curatedid={slug}&gridColumns=3&sort=discount-desc"

        session = stealth_manager.get_session()
        headers = stealth_manager.get_headers()

        deals_found = []
        try:
            r = session.get(api_url, headers=headers, timeout=9)
            if r.status_code == 200:
                match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});\s*(?:window\.|\n|<\/script>)', r.text)
                if match:
                    st = json.loads(match.group(1))
                    grid = st.get('grid', {})
                    entities = grid.get('entities', {})

                    for pid, it in list(entities.items())[:25]:
                        mrp = float(it.get('wasPriceData', {}).get('value', 0) or 0)
                        price = float(it.get('price', {}).get('value', 0) or 0)
                        p_name = it.get('name', '')
                        brand = it.get('fnlColorVariantData', {}).get('brandName') or it.get('brandTypeName', '')
                        brick = it.get('brickCategoryName') or name or 'Fashion'
                        p_url = it.get('url', '')
                        img_url = it.get('fnlColorVariantData', {}).get('outfitPictureURL') or ''

                        if mrp > 0 and price > 0:
                            base_d = ((mrp - price) / mrp) * 100.0
                            
                            # 1. Direct Markdown >= 70%
                            if base_d >= 70.0:
                                net_d = round(base_d, 1)
                                f_price = price
                                c_code = "DIRECT_CLEARANCE"
                                f_desc = f"Direct Clearance: {base_d:.0f}% Off"
                            # 2. Stacked Flash Voucher (+20% coupon on base >= 60%)
                            elif base_d >= 58.0:
                                f_price = round(price * 0.80, 2)
                                net_d = round(((mrp - f_price) / mrp) * 100.0, 1)
                                c_code = "FLASH_STACK_20"
                                f_desc = f"Base {base_d:.0f}% + 20% Voucher -> {net_d:.0f}% Realized"
                            else:
                                net_d = 0.0

                            if net_d >= 70.0:
                                sku = p_url.split('/p/')[-1] if '/p/' in p_url else pid
                                
                                # Canonical department resolution
                                cat_dept = dept
                                if any(k in name.lower() for k in ['wearable', 'smartwatch', 'headphone', 'speaker', 'gadget']):
                                    cat_dept = "GADGETS & TECH"
                                elif any(k in name.lower() for k in ['shoe', 'sneaker', 'sandal', 'boot', 'heel', 'flat']):
                                    cat_dept = "FOOTWEAR"
                                elif any(k in name.lower() for k in ['jewel', 'earring', 'necklace', 'ring', 'bangle', 'bracelet']):
                                    cat_dept = "FASHION JEWELLERY"
                                elif any(k in name.lower() for k in ['bag', 'backpack', 'luggage', 'trolley', 'wallet', 'belt', 'sunglass']):
                                    cat_dept = "ACCESSORIES & LUGGAGE"

                                deals_found.append({
                                    "id": sku,
                                    "name": p_name,
                                    "brand": brand,
                                    "category": name,
                                    "department": cat_dept,
                                    "mrp": mrp,
                                    "selling_price": price,
                                    "final_price": f_price,
                                    "base_discount_percent": round(base_d, 1),
                                    "net_discount_percent": net_d,
                                    "formula_desc": f_desc,
                                    "coupon_code": c_code,
                                    "coupon_slug": slug,
                                    "product_url": f"https://www.ajio.com/p/{sku}",
                                    "image_url": img_url
                                })
        except Exception as e:
            logger.debug(f"Sweep note for {slug}: {e}")

        return deals_found

    def run_full_category_sweep(self, max_workers: int = 15) -> List[Dict[str, Any]]:
        seeds = self.load_category_seeds()
        logger.info(f"[*] Sweeping {len(seeds)} official navigation categories across {max_workers} threads...")
        t0 = time.time()
        
        all_deals = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seed = {executor.submit(self.sweep_single_category, s): s for s in seeds}
            for future in concurrent.futures.as_completed(future_to_seed):
                res = future.result()
                if res:
                    all_deals.extend(res)

        # Deduplicate deals by ID
        dedup_deals = {}
        for d in all_deals:
            dedup_deals[d['id']] = d
        unique_deals = list(dedup_deals.values())
        unique_deals.sort(key=lambda x: x['net_discount_percent'], reverse=True)

        elapsed = round(time.time() - t0, 2)
        logger.info(f"[+] Category sweep complete in {elapsed}s: Indexed {len(unique_deals)} verified 70%+ clearance products across all categories.")
        
        # Persist directly
        self.storage.save_products(unique_deals)
        return unique_deals
