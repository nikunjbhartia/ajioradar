import re
import json
import logging
import xml.etree.ElementTree as ET
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
    def harvest_all_campaign_seeds() -> List[Dict[str, Any]]:
        session = stealth_manager.get_session()
        headers = stealth_manager.get_headers()
        discovered = {}

        # 1. Harvest from Sitemap Landing XML (instant authoritative feed)
        try:
            r_sitemap = session.get("https://www.ajio.com/sitemap_landing.xml", headers=headers, timeout=10)
            if r_sitemap.status_code == 200:
                root = ET.fromstring(r_sitemap.content)
                ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                for url_elem in root.findall('sm:url', ns):
                    loc = url_elem.find('sm:loc', ns)
                    if loc is not None and loc.text and '/s/' in loc.text:
                        slug = loc.text.split('/s/')[-1].strip('/')
                        # Extract alpha tokens for code name
                        tokens = re.findall(r'[A-Za-z]+', slug)
                        code = tokens[0].upper() if tokens else "FLASHDEAL"
                        discovered[slug] = {
                            "code": code,
                            "slug": slug,
                            "title": slug.replace('-', ' ').title(),
                            "description": f"Curated Promotional Collection for {slug}",
                            "source": "sitemap_landing"
                        }
        except Exception as e:
            logger.warning(f"Sitemap harvest notice: {e}")

        # 2. Harvest from Brand Storefronts (captures brand-specific vouchers)
        for brand in TOP_BRAND_ANCHORS:
            try:
                url = f"https://www.ajio.com/c/83?query=%3Arelevance%3Abrand%3A{brand}&curPage=0"
                r = session.get(url, headers=headers, timeout=6)
                if r.status_code == 200:
                    match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});', r.text)
                    if match:
                        st = json.loads(match.group(1))
                        entities = st.get('grid', {}).get('entities', {})
                        for pid, it in list(entities.items())[:5]:
                            p_url = it.get('url', '')
                            if p_url and '/p/' in p_url:
                                sku = p_url.split('/p/')[-1]
                                # Probe 1 SKU to capture potentialPromotions
                                r_pdp = session.get(f"https://www.ajio.com/p/{sku}", headers=headers, timeout=6)
                                if r_pdp.status_code == 200:
                                    m_pdp = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});', r_pdp.text)
                                    if m_pdp:
                                        p_st = json.loads(m_pdp.group(1))
                                        promos = p_st.get('product', {}).get('productDetails', {}).get('potentialPromotions', [])
                                        for p in promos:
                                            p_code = p.get('code', '').strip().upper()
                                            p_desc = p.get('description', '')
                                            p_det = p.get('detailsUrl', '')
                                            if p_det and '/s/' in p_det:
                                                p_slug = p_det.split('/s/')[-1].strip('/')
                                                discovered[p_slug] = {
                                                    "code": p_code or "PROMO",
                                                    "slug": p_slug,
                                                    "title": p.get('title', f"Offer {p_code}"),
                                                    "description": p_desc,
                                                    "source": "brand_storefront"
                                                }
            except Exception:
                pass

        logger.info(f"[Harvester] Successfully discovered {len(discovered)} unique campaign seed targets.")
        return list(discovered.values())
