import json
import re
import time
import urllib.parse
import logging
import concurrent.futures
from typing import Dict, List, Any, Optional, Tuple
from app.core.dynamic_parser import DynamicPromoParser
from app.core.stealth_client import stealth_manager
from app.database.storage import DealStorage
from app.core.classifier import classify_product, classify_campaign

logger = logging.getLogger("deal_validator")

# Full Platform Category Roots across all of Ajio
ALL_CATEGORY_ROOTS = [
    {"name": "Men Western Wear", "dept": "MEN", "url": "https://www.ajio.com/c/830216"},
    {"name": "Men Footwear", "dept": "FOOTWEAR", "url": "https://www.ajio.com/c/830207"},
    {"name": "Men Ethnic Wear", "dept": "MEN", "url": "https://www.ajio.com/c/830208"},
    {"name": "Men Accessories", "dept": "ACCESSORIES & LUGGAGE", "url": "https://www.ajio.com/c/830201"},
    {"name": "Women Western Wear", "dept": "WOMEN", "url": "https://www.ajio.com/c/830316"},
    {"name": "Women Ethnic Wear", "dept": "WOMEN", "url": "https://www.ajio.com/c/830303"},
    {"name": "Women Footwear", "dept": "FOOTWEAR", "url": "https://www.ajio.com/c/830302"},
    {"name": "Women Lingerie", "dept": "WOMEN", "url": "https://www.ajio.com/c/830313"},
    {"name": "Women Jewellery", "dept": "FASHION JEWELLERY", "url": "https://www.ajio.com/c/830309"},
    {"name": "Boys Wear", "dept": "KIDS & INFANTS", "url": "https://www.ajio.com/c/830101"},
    {"name": "Girls Wear", "dept": "KIDS & INFANTS", "url": "https://www.ajio.com/c/830102"},
    {"name": "Infants & Babies", "dept": "KIDS & INFANTS", "url": "https://www.ajio.com/c/830103"},
    {"name": "Kids Footwear", "dept": "FOOTWEAR", "url": "https://www.ajio.com/c/830104"},
    {"name": "Toys & Babycare", "dept": "KIDS & INFANTS", "url": "https://www.ajio.com/c/830105"},
    {"name": "Skincare", "dept": "BEAUTY & GROOMING", "url": "https://www.ajio.com/c/830501"},
    {"name": "Makeup & Cosmetics", "dept": "BEAUTY & GROOMING", "url": "https://www.ajio.com/c/830502"},
    {"name": "Fragrances & EDP", "dept": "BEAUTY & GROOMING", "url": "https://www.ajio.com/c/830504"},
    {"name": "Men Grooming", "dept": "BEAUTY & GROOMING", "url": "https://www.ajio.com/c/830505"},
    {"name": "Bedding & Linen", "dept": "HOME & KITCHEN", "url": "https://www.ajio.com/c/830401"},
    {"name": "Cushions & Curtains", "dept": "HOME & KITCHEN", "url": "https://www.ajio.com/c/830402"},
    {"name": "Kitchen & Dining", "dept": "HOME & KITCHEN", "url": "https://www.ajio.com/c/830403"},
    {"name": "Home Decor", "dept": "HOME & KITCHEN", "url": "https://www.ajio.com/c/830404"}
]

class DealValidatorEngine:
    def __init__(self, db_path: str = "deals.db"):
        self.storage = DealStorage(db_path)

    def _extract_grid_entities(self, html_text: str) -> Tuple[Dict[str, Any], int]:
        match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});\s*(?:window\.|\n|<\/script>)', html_text)
        if match:
            raw_json = match.group(1)
            try:
                st = json.loads(raw_json)
                grid = st.get('grid', {})
                entities = grid.get('entities', {})
                pagination = grid.get('pagination', {})
                total_results = pagination.get('totalResults', len(entities))
                return entities, total_results
            except Exception:
                try:
                    import html
                    st = json.loads(html.unescape(raw_json))
                    grid = st.get('grid', {})
                    entities = grid.get('entities', {})
                    pagination = grid.get('pagination', {})
                    total_results = pagination.get('totalResults', len(entities))
                    return entities, total_results
                except Exception:
                    pass
        return {}, 0

    def validate_campaign(self, camp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        code = camp.get('code', '').strip().upper()
        slug = camp.get('slug', '').strip()
        desc = camp.get('description', camp.get('discount_description', ''))
        title = camp.get('title', f"Promotion {code}")

        # 1. Dynamic Rule Parsing (No hardcoded coupons)
        parsed = DynamicPromoParser.parse_promotion(code, desc, slug)
        nominal_r = parsed['nominal_rate']
        facet_tier = parsed['target_facet_tier']
        min_base = parsed['min_base_needed']
        is_standalone = parsed['is_standalone']

        session = stealth_manager.get_session()
        headers = stealth_manager.get_headers()

        entities = {}
        total_verified_skus = 0
        used_facet_tier = facet_tier
        user_outbound_url = f"https://www.ajio.com/s/{slug}?query=:discount-desc"

        # --- TIER 1 PROBE: Bloomreach Faceted Grid with strict target tier ---
        facet_q1 = f':discount-desc:discountranges:{facet_tier}:curated:true:curatedId:{slug}'
        encoded_q1 = urllib.parse.quote(facet_q1)
        api_url1 = f"https://www.ajio.com/c/83?query={encoded_q1}&curated=true&curatedid={slug}&gridColumns=3&sort=discount-desc"
        
        try:
            r1 = session.get(api_url1, headers=headers, timeout=9)
            if r1.status_code == 200:
                entities, total_verified_skus = self._extract_grid_entities(r1.text)
                if total_verified_skus > 0:
                    user_outbound_url = f"https://www.ajio.com/s/{slug}?query={encoded_q1}&curated=true&curatedid={slug}&gridColumns=3&sort=discount-desc"
        except Exception as e:
            logger.debug(f"Tier 1 Bloomreach probe note for {slug}: {e}")

        # --- TIER 2 FALLBACK: Relaxed facet tier (50% and above) if 0 results ---
        if total_verified_skus == 0 and facet_tier != "50% and above":
            facet_q2 = f':discount-desc:discountranges:50% and above:curated:true:curatedId:{slug}'
            encoded_q2 = urllib.parse.quote(facet_q2)
            api_url2 = f"https://www.ajio.com/c/83?query={encoded_q2}&curated=true&curatedid={slug}&gridColumns=3&sort=discount-desc"
            try:
                r2 = session.get(api_url2, headers=headers, timeout=8)
                if r2.status_code == 200:
                    e2, t2 = self._extract_grid_entities(r2.text)
                    if t2 > 0:
                        entities = e2
                        total_verified_skus = t2
                        used_facet_tier = "50% and above"
                        user_outbound_url = f"https://www.ajio.com/s/{slug}?query={encoded_q2}&curated=true&curatedid={slug}&gridColumns=3&sort=discount-desc"
            except Exception:
                pass

        # --- TIER 3 FALLBACK: Direct Curated Collection SSR Scraping ---
        if total_verified_skus == 0:
            direct_s_url = f"https://www.ajio.com/s/{slug}?query=:discount-desc"
            try:
                r3 = session.get(direct_s_url, headers=headers, timeout=8)
                if r3.status_code == 200:
                    e3, t3 = self._extract_grid_entities(r3.text)
                    if t3 > 0:
                        entities = e3
                        total_verified_skus = t3
                        used_facet_tier = "All Active Curated Items"
                        user_outbound_url = direct_s_url
            except Exception:
                pass

        # --- TIER 4 FALLBACK: Direct Category Slug Probe ---
        if total_verified_skus == 0:
            direct_c_url = f"https://www.ajio.com/c/{slug}?query=:discount-desc"
            try:
                r4 = session.get(direct_c_url, headers=headers, timeout=7)
                if r4.status_code == 200:
                    e4, t4 = self._extract_grid_entities(r4.text)
                    if t4 > 0:
                        entities = e4
                        total_verified_skus = t4
                        used_facet_tier = "Catalog Direct"
                        user_outbound_url = direct_c_url
            except Exception:
                pass

        # Process extracted product entities
        if total_verified_skus > 0 and len(entities) > 0:
            realized_discounts = []
            effective_prices = []
            brands_found = set()
            categories_found = set()
            sample_deals = []

            for pid, it in entities.items():
                mrp = float(it.get('wasPriceData', {}).get('value', 0) or 0)
                price = float(it.get('price', {}).get('value', 0) or 0)
                brand = it.get('fnlColorVariantData', {}).get('brandName') or it.get('brandTypeName', '')
                cat = it.get('brickCategoryName') or 'Fashion'
                p_name = it.get('name', '')
                p_url = it.get('url', '')
                img_url = it.get('fnlColorVariantData', {}).get('outfitPictureURL') or ''

                if brand: brands_found.add(brand)
                if cat: categories_found.add(cat)

                if mrp > 0 and price > 0:
                    base_d = max(0.0, min(100.0, ((mrp - price) / mrp) * 100.0))
                    if is_standalone:
                        final_p = mrp * (1.0 - (nominal_r / 100.0))
                    else:
                        final_p = price * (1.0 - (nominal_r / 100.0))

                    final_p = max(0.0, min(mrp, final_p))
                    net_d = max(0.0, min(100.0, ((mrp - final_p) / mrp) * 100.0))

                    net_d = round(net_d, 1)
                    final_p = round(final_p, 2)
                    realized_discounts.append(net_d)
                    effective_prices.append(final_p)

                    sku = p_url.split('/p/')[-1] if '/p/' in p_url else pid
                    prod_dept = classify_product(p_name, brand, cat)

                    sample_deals.append({
                        "id": sku,
                        "name": p_name,
                        "brand": brand,
                        "category": cat,
                        "department": prod_dept,
                        "mrp": mrp,
                        "selling_price": price,
                        "final_price": final_p,
                        "base_discount_percent": round(base_d, 1),
                        "net_discount_percent": net_d,
                        "coupon_code": code,
                        "product_url": f"https://www.ajio.com/p/{sku}",
                        "image_url": img_url
                    })

            min_net = min(realized_discounts) if realized_discounts else nominal_r
            max_net = max(realized_discounts) if realized_discounts else nominal_r
            min_p = min(effective_prices) if effective_prices else 0.0
            max_p = max(effective_prices) if effective_prices else 0.0

            brands_str = ", ".join(list(brands_found)[:6])
            camp_dept = classify_campaign(
                title=title,
                desc=desc,
                brands_str=brands_str,
                slug=slug,
                sample_deals=sample_deals,
                seed_dept=c.get('department', 'Multi-Category')
            )

            return {
                "curated_id": slug,
                "code": code,
                "title": title,
                "description": desc,
                "details_url": user_outbound_url,
                "promo_type": parsed['promo_type'],
                "department": camp_dept,
                "brands": brands_str,
                "brand_list": list(brands_found),
                "min_realized_discount": round(min_net, 1),
                "max_realized_discount": round(max_net, 1),
                "min_price": round(min_p, 2),
                "max_price": round(max_p, 2),
                "min_base_needed": min_base,
                "applied_filter_tier": used_facet_tier,
                "has_70_plus_verified": max_net >= 70.0,
                "is_standalone_deal": is_standalone,
                "total_verified_skus": total_verified_skus,
                "sample_deals": sample_deals
            }
        else:
            # 0 items qualifying currently
            fallback_dept = classify_campaign(
                title=title,
                desc=desc,
                brands_str="",
                slug=slug,
                sample_deals=None,
                seed_dept=c.get('department', 'Multi-Category')
            )

            return {
                "curated_id": slug,
                "code": code,
                "title": title,
                "description": desc,
                "details_url": f"https://www.ajio.com/s/{slug}?query=:discount-desc",
                "promo_type": parsed['promo_type'],
                "department": fallback_dept,
                "brands": "",
                "brand_list": [],
                "min_realized_discount": nominal_r,
                "max_realized_discount": nominal_r,
                "min_price": 0,
                "max_price": 0,
                "min_base_needed": min_base,
                "applied_filter_tier": "None (0 Qualifying Items)",
                "has_70_plus_verified": False,
                "is_standalone_deal": False,
                "total_verified_skus": 0,
                "sample_deals": []
            }

    def run_full_validation_cycle(self, campaigns_seed: List[Dict[str, Any]], max_workers: int = 15):
        t0 = time.time()
        logger.info(f"[*] Validating {len(campaigns_seed)} campaigns using {max_workers} worker threads...")

        verified_camps = []
        all_deals = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.validate_campaign, c) for c in campaigns_seed]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    verified_camps.append(res)
                    for d in res.get('sample_deals', []):
                        d['department'] = res['department']
                        all_deals.append(d)

        # Also probe category direct clearances across all departments
        session = stealth_manager.get_session()
        headers = stealth_manager.get_headers()
        for root in ALL_CATEGORY_ROOTS:
            try:
                r = session.get(f"{root['url']}?query=%3Adiscount-desc", headers=headers, timeout=6)
                if r.status_code == 200:
                    entities, total = self._extract_grid_entities(r.text)
                    for pid, it in list(entities.items())[:15]:
                        mrp = float(it.get('wasPriceData', {}).get('value', 0) or 0)
                        price = float(it.get('price', {}).get('value', 0) or 0)
                        if mrp > 0:
                            base_d = ((mrp - price) / mrp) * 100.0
                            if base_d >= 70.0:
                                p_url = it.get('url', '')
                                sku = p_url.split('/p/')[-1] if '/p/' in p_url else pid
                                all_deals.append({
                                    "id": sku,
                                    "name": it.get('name', ''),
                                    "brand": it.get('fnlColorVariantData', {}).get('brandName') or it.get('brandTypeName', ''),
                                    "category": it.get('brickCategoryName') or root['name'],
                                    "department": root['dept'],
                                    "mrp": mrp,
                                    "selling_price": price,
                                    "final_price": price,
                                    "base_discount_percent": round(base_d, 1),
                                    "net_discount_percent": round(base_d, 1),
                                    "formula_desc": f"Direct Clearance: {base_d:.0f}% Off",
                                    "coupon_code": "DIRECT_CLEARANCE",
                                    "product_url": f"https://www.ajio.com/p/{sku}",
                                    "image_url": it.get('fnlColorVariantData', {}).get('outfitPictureURL') or ''
                                })
            except Exception:
                pass

        # Deduplicate and sort
        dedup_deals = {}
        for d in all_deals:
            dedup_deals[d['id']] = d
        final_deals = list(dedup_deals.values())
        final_deals.sort(key=lambda x: x['net_discount_percent'], reverse=True)

        verified_camps.sort(key=lambda x: (x['has_70_plus_verified'], x['max_realized_discount'], x['total_verified_skus']), reverse=True)

        elapsed = round(time.time() - t0, 2)
        active_70 = sum(1 for c in verified_camps if c['has_70_plus_verified'])

        # Persist fresh records in place and record delta in 7-day sync history
        delta_item = self.storage.save_campaigns(verified_camps, duration_seconds=elapsed)
        self.storage.save_products(final_deals)

        logger.info(f"[+] Validation Complete in {elapsed}s: {active_70} verified 70%+ campaigns & {len(final_deals)} products indexed. Delta: +{delta_item.added_count} new, ~{delta_item.updated_count} updated, -{delta_item.removed_count} expired.")

        return {
            "campaigns": verified_camps,
            "deals": final_deals,
            "delta": delta_item,
            "elapsed_seconds": elapsed
        }
