import re
from typing import Tuple, Dict, Any

class DynamicPromoParser:
    """
    Generalized Dynamic Promotion Parser.
    Extracts nominal discounts, BXGY ratios, flat-off cart thresholds, and
    under-price promotions with ZERO false positives on markdown collections.
    """

    NON_VOUCHERS = {
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
        'DIRECT_CLEARANCE', 'CLEARANCE', 'SHOP', 'COLLECTION', 'OFFERS', 'SALE',
        'WOMEN', 'MEN', 'BOYS', 'GIRLS', 'KIDS', 'INFANTS', 'FUSION', 'BAGS', 'SHOES',
        'FOOTWEAR', 'CLOTHING', 'PANTS', 'SHIRTS', 'JEANS', 'DRESSES', 'TOPS', 'KURTAS',
        'SAREES', 'JEWELLERY', 'ACCESSORIES', 'WATCHES', 'WALLETS', 'BEAUTY', 'HOME',
        'GADGETS', 'ETHNIC', 'INDIE', 'LUXE', 'SPORTS', 'ATHLEISURE', 'FRESH', 'EOSS'
    }

    @classmethod
    def is_markdown_collection(cls, code: str, slug: str = "") -> bool:
        c = (code or '').upper().strip()
        s = (slug or '').upper().strip()
        if not c or c in cls.NON_VOUCHERS:
            return True
        if re.match(r'^(?:MIN|MAX|FLAT|UPTO)\d+(?:PERCENTOFF)?$', c) or re.match(r'^\d+TO\d+PERCENTOFF$', c):
            return True
        if re.match(r'^(?:UNDERRS|STARTINGATRS)\d+$', c):
            return True
        if 'PERCENTOFF' in c or 'PERCENTOFF' in s or '0-TO-' in s or 'YEARS' in s or 'CLEARANCE' in c:
            return True
        return False

    @classmethod
    def parse_promotion(cls, code: str, description: str, slug: str = "") -> Dict[str, Any]:
        raw_text = f"{code} {description} {slug}".upper()
        code_clean = (code or '').strip().upper()
        desc_clean = (description or '').strip()

        # 1. First, check if this is a Base Markdown Collection / Curated Department (0% extra voucher)
        if cls.is_markdown_collection(code_clean, slug):
            return {
                "promo_type": "Direct Clearance / Markdown",
                "nominal_rate": 0.0,
                "is_standalone": False,
                "is_markdown_collection": True,
                "min_base_needed": 70.0,
                "target_facet_tier": "70% and above",
                "explanation": "Base catalog collection. Selling price is the final price (0% extra voucher)."
            }

        # 2. Check for Buy X Get Y Free (BXGY) mechanics
        # e.g., "BUY 1 GET 5 FREE", "BUY 1 @MRP GET 4 FREE", "BUY 2 GET 1 FREE", "B2G2"
        bxgy_match = re.search(r'BUY\s*(\d+)\s*(?:@|AT)?\s*(?:MRP)?\s*,?\s*GET\s*(\d+)\s*(?:FREE)?', raw_text, re.IGNORECASE)
        bxg_compact = re.search(r'B(\d+)G(\d+)', raw_text, re.IGNORECASE)

        if bxgy_match:
            buy_x = float(bxgy_match.group(1))
            get_y = float(bxgy_match.group(2))
            if (buy_x + get_y) > 0:
                realized_rate = (get_y / (buy_x + get_y)) * 100.0
                return {
                    "promo_type": "Buy X Get Y Free",
                    "nominal_rate": round(realized_rate, 2),
                    "is_standalone": True,
                    "is_markdown_collection": False,
                    "min_base_needed": 0.0,
                    "target_facet_tier": "50% and above",
                    "explanation": f"Buy {int(buy_x)} Get {int(get_y)} Free: Yields {realized_rate:.1f}% standalone price cut on qualified items."
                }
        elif bxg_compact:
            buy_x = float(bxg_compact.group(1))
            get_y = float(bxg_compact.group(2))
            if (buy_x + get_y) > 0:
                realized_rate = (get_y / (buy_x + get_y)) * 100.0
                return {
                    "promo_type": "Buy X Get Y Free",
                    "nominal_rate": round(realized_rate, 2),
                    "is_standalone": True,
                    "is_markdown_collection": False,
                    "min_base_needed": 0.0,
                    "target_facet_tier": "50% and above",
                    "explanation": f"Buy {int(buy_x)} Get {int(get_y)} Free: Yields {realized_rate:.1f}% standalone price cut."
                }

        # 3. Check for Flat Rupee Off with Minimum Cart Threshold
        # e.g., "EXTRA 400 OFF ON CART VALUE OF 3190", "FLAT 2000 OFF ON 7999", "300 OFF ON 2890"
        flat_cart_match = re.search(r'(?:EXTRA|FLAT|GET|RS\.?|INR)?\s*(\d{3,5})\s*(?:OFF|DISCOUNT).*?(?:ON|OF|ABOVE|MIN)\s*(?:CART|RS\.?|INR)?\s*(\d{3,6})', raw_text, re.IGNORECASE)
        if flat_cart_match:
            discount_amount = float(flat_cart_match.group(1))
            min_cart = float(flat_cart_match.group(2))
            if min_cart > discount_amount > 0:
                nominal_rate = round((discount_amount / min_cart) * 100.0, 2)
                r_frac = nominal_rate / 100.0
                min_base = max(0.0, round((1.0 - (0.30 / (1.0 - r_frac))) * 100.0, 1))
                facet_tier = "70% and above" if min_base >= 65.0 else ("60% and above" if min_base >= 55.0 else "50% and above")
                return {
                    "promo_type": "Cart Threshold Voucher",
                    "nominal_rate": nominal_rate,
                    "discount_amount": discount_amount,
                    "min_cart_value": min_cart,
                    "is_standalone": False,
                    "is_markdown_collection": False,
                    "min_base_needed": min_base,
                    "target_facet_tier": facet_tier,
                    "explanation": f"Flat ₹{int(discount_amount)} off on ₹{int(min_cart)} cart (~{nominal_rate:.1f}% marginal rate). Needs ≥{min_base:.0f}% base discount item to cross 70%."
                }

        # 4. Check for Standard Percentage Promo Vouchers
        # e.g., "GET 30% OFF UPTO 500", "EXTRA 25% OFF", "ADDITIONAL 20% OFF", "23% OFF"
        pct_match = re.search(r'(?:GET|EXTRA|ADDITIONAL|SPECIAL|PROMO)\s*(\d{1,2})%\s*(?:OFF|DISCOUNT)?', raw_text, re.IGNORECASE)
        if not pct_match:
            # Suffix percentage on genuine voucher codes (e.g. DESIDRIP20 -> 20%, KIDS15 -> 15%, RBK20 -> 20%)
            code_num_match = re.search(r'^[A-Z]{3,}(\d{2})$', code_clean)
            if code_num_match and not code_clean.startswith(('MIN', 'MAX', 'FLAT', 'UPTO')):
                pct_val = float(code_num_match.group(1))
                if 5 <= pct_val <= 50:
                    pct_match = code_num_match

        if pct_match:
            nominal_rate = float(pct_match.group(1))
            r_frac = nominal_rate / 100.0
            if r_frac >= 0.70:
                return {
                    "promo_type": "High Percentage Voucher",
                    "nominal_rate": nominal_rate,
                    "is_standalone": True,
                    "is_markdown_collection": False,
                    "min_base_needed": 0.0,
                    "target_facet_tier": "70% and above",
                    "explanation": f"Flat {nominal_rate:.0f}% checkout cut applies directly to entire basket."
                }
            
            min_base = max(0.0, round((1.0 - (0.30 / (1.0 - r_frac))) * 100.0, 1))
            facet_tier = "70% and above" if min_base >= 65.0 else ("60% and above" if min_base >= 55.0 else "50% and above")
            return {
                "promo_type": "Percentage Voucher",
                "nominal_rate": nominal_rate,
                "is_standalone": False,
                "is_markdown_collection": False,
                "min_base_needed": min_base,
                "target_facet_tier": facet_tier,
                "explanation": f"Extra {nominal_rate:.0f}% off. Stack with items having ≥{min_base:.0f}% base discount to reach >70% net price."
            }

        # 5. Default Fallback for generic promotional campaigns (0% extra voucher unless verified)
        return {
            "promo_type": "Curated Catalog Collection",
            "nominal_rate": 0.0,
            "is_standalone": False,
            "is_markdown_collection": True,
            "min_base_needed": 70.0,
            "target_facet_tier": "70% and above",
            "explanation": "Catalog collection. Items must have ≥70% base discount to qualify."
        }

