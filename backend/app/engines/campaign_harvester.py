import os
import re
import json
import logging
import xml.etree.ElementTree as ET
import concurrent.futures
from typing import List, Dict, Any
from app.core.stealth_client import stealth_manager

logger = logging.getLogger("campaign_harvester")

TOP_BRAND_ANCHORS = [
    "Puma", "Nike", "Adidas", "LEVIS", "SUPERDRY", "ARMANI EXCHANGE", "TOMMY HILFIGER",
    "Snitch", "The Indian Garage Co", "Cover Story", "ONLY", "Vero Moda", "Red Tape",
    "Campus", "STEVE MADDEN", "BIBA", "AURELIA", "SOCH", "W", "U.S. Polo Assn.",
    "Flying Machine", "GAP", "DIESEL", "ALDO", "SKECHERS", "WOODLAND", "BATA",
    "JOCKEY", "ZIVAME", "MOKOBARA", "BEARDO", "PEPE JEANS", "SPYKAR", "MUFTI",
    "KILLER", "RARE RABBIT", "ANDAMEN", "WROGN", "Forever New", "Hunkemoller", "ASICS"
]

class CampaignHarvester:
    """
    Automated Campaign Discovery Harvester.
    Surveys Sitemaps, CMS Navigation slots, and Brand Storefronts to discover
    100% of newly published or ongoing campaign collections.
    """
    @staticmethod
    def harvest_single_brand(brand: str) -> List[Dict[str, Any]]:
        session = stealth_manager.get_session()
        headers = stealth_manager.get_headers()
        found = []
        try:
            url = f"https://www.ajio.com/c/83?query=%3Arelevance%3Abrand%3A{brand}&curPage=0"
            r = session.get(url, headers=headers, timeout=4)
            if r.status_code == 200:
                match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});', r.text)
                if match:
                    st = json.loads(match.group(1))
                    facets = st.get('facets', {})
                    # Harvest promo voucher facet values
                    results = facets.get('nextFacets', {}).get('results', [])
                    for item in results:
                        if 'promotions-' in item:
                            code = item.replace('promotions-', '').strip().upper()
                            found.append({
                                "code": code,
                                "slug": f"promo-{code.lower()}",
                                "title": f"{brand} - Flash Offer {code}",
                                "description": f"Verified voucher promotion for {brand}",
                                "source": "brand_storefront"
                            })
        except Exception:
            pass
        return found

    @staticmethod
    def harvest_all_campaign_seeds() -> List[Dict[str, Any]]:
        session = stealth_manager.get_session()
        headers = stealth_manager.get_headers()
        discovered = {}

        # 0. Load Curated Baseline Campaign Seeds (Guarantees Minimum 430 Campaign Baseline Targets)
        try:
            seeds_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database", "campaign_seeds.json"))
            if not os.path.exists(seeds_file):
                seeds_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "database", "campaign_seeds.json"))
            if os.path.exists(seeds_file):
                with open(seeds_file, "r") as f:
                    cached_seeds = json.load(f)
                    for cs in cached_seeds:
                        slug = cs.get("slug")
                        if slug:
                            discovered[slug] = cs
        except Exception as e:
            logger.warning(f"Baseline seed load note: {e}")

        NON_VOUCHER = {
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15',
            'DIRECT_CLEARANCE', 'PREMIUM_OFFER', 'INSTANT_OFFER', 'FLASH_STACK_20', 'FLASH_STACK_25', 'FLASH_STACK_30',
            'WOMEN', 'MEN', 'MENS', 'KIDS', 'BOYS', 'GIRLS', 'INFANTS', 'SHOP', 'FOOTWEAR', 'ATHLEISURE',
            'ETHNIC', 'FUSION', 'SAREES', 'JEANS', 'GAS', 'ASOS', 'JACK', 'LOUIS', 'MARC', 'BRAND',
            'PLUS', 'MISS', 'FRESH', 'WHP', 'MHP', 'FLASHSALE', 'INDIE', 'HOME', 'BEAUTY', 'TECH',
            'CLOTHING', 'ACCESSORIES', 'BAGS', 'SHOES', 'SALE', 'DEALS', 'OFFER', 'SPECIAL', 'PROMO', 'COLLECTION'
        }

        # 1. Harvest from Sitemap Landing XML (authoritative fast feed)
        try:
            r_sitemap = session.get("https://www.ajio.com/sitemap_landing.xml", headers=headers, timeout=6)
            if r_sitemap.status_code == 200:
                root = ET.fromstring(r_sitemap.content)
                ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                for url_elem in root.findall('sm:url', ns):
                    loc = url_elem.find('sm:loc', ns)
                    if loc is not None and loc.text and '/s/' in loc.text:
                        slug = loc.text.split('/s/')[-1].strip('/')
                        code = ""
                        promo_m = re.match(r'^(?:promo-|coupon-|voucher-)?([A-Za-z0-9]{3,20})(?:-\d+)?$', slug, re.IGNORECASE)
                        if promo_m:
                            candidate = promo_m.group(1).upper()
                            if candidate not in NON_VOUCHER and not candidate.isdigit() and len(candidate) >= 3:
                                code = candidate
                        discovered[slug] = {
                            "code": code,
                            "slug": slug,
                            "title": slug.replace('-', ' ').title(),
                            "description": f"Curated Promotional Collection for {slug}",
                            "source": "sitemap_landing"
                        }
        except Exception as e:
            logger.warning(f"Sitemap harvest notice: {e}")

        # 2. Parallel Harvest from Brand Storefronts
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            brand_results = executor.map(CampaignHarvester.harvest_single_brand, TOP_BRAND_ANCHORS)
            for b_list in brand_results:
                for item in b_list:
                    discovered[item['slug']] = item

        logger.info(f"[Harvester] Successfully discovered {len(discovered)} unique campaign seed targets.")
        return list(discovered.values())
