#!/usr/bin/env python3
import os
import json
import sqlite3
import urllib.request
import time
import sys

BASE_URL = "https://ajioradar.pages.dev/data"

def pull_live_data():
    print("========================================================")
    print("📥 AjioRadar • Live Cloud Edge -> Local Dataset Sync")
    print("========================================================")
    
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dist_data_dir = os.path.join(root_dir, "dist", "data")
    db_path = os.path.join(root_dir, "backend", "deals.db")
    os.makedirs(dist_data_dir, exist_ok=True)

    files_to_pull = ["metadata.json", "campaigns.json", "products.json", "history.json", "taxonomy.json"]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    pulled_data = {}
    for filename in files_to_pull:
        url = f"{BASE_URL}/{filename}?t={int(time.time())}"
        target_path = os.path.join(dist_data_dir, filename)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode('utf-8')
                with open(target_path, "w", encoding='utf-8') as f:
                    f.write(content)
                pulled_data[filename] = json.loads(content)
                print(f"  ✓ Downloaded {filename} ({len(content)} bytes)")
        except Exception as e:
            print(f"  ⚠️ Note on {filename}: {e}")

    # Synchronize into local SQLite deals.db
    if "products.json" in pulled_data or "campaigns.json" in pulled_data:
        print("\n[*] Updating local SQLite database (backend/deals.db)...")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Import products (Strictly authenticated >= 70% deals only)
        non_vouchers = {
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
            'MIN50', 'MIN60', 'MIN40PERCENTOFF', 'MIN30PERCENTOFF', '40TO80PERCENTOFF', 'FLAT50PERCENTOFF',
            'UPTO70PERCENTOFF', 'UPTO80PERCENTOFF', 'MIN45PERCENTOFF', 'MIN65PERCENTOFF', 'MIN75', 'MIN80',
            'UPTO60PERCENTOFF', 'MIN55PERCENTOFF', 'FLASH_STACK_20', 'GIRLS', 'WOMEN', 'FRESH', 'KIDS', 'FUSION', 'TOPS',
            'MISS', 'BAGS', 'REEBOK', 'PANTS', 'DUNE', 'SKIRTS', 'PRECIOUS', 'PLUS', 'JUTTIS', 'ISHIN',
            'HI', 'UCB', 'MARC', 'JAIPUR', 'BRAND', 'SHIRTS', 'TSHIRTS', 'MEN', 'SWEATERS', 'F', 'OOTD',
            'JACKET', 'MARKS', 'NETWORK', 'JEANS', 'EOSS', 'UNITED', 'BOYS', 'SUPERDRYBACK', 'SCOTCH',
            'SHORTS', 'JACK', 'STEVE', 'SHOP', 'HUBBERHOLME', 'NETPLAY', 'CATWALK', 'ZIVAME', 'WHP',
            'WATCHES', 'WALLETS', 'WAISCOATS', 'UPTO', 'PETER', 'OFFERS', 'HIDESIGN', 'GAP', 'FLIP',
            'EXCLUSIVE', 'DUPATTAS', 'ATHLEISURE', 'ARMANI', 'ALLEN', 'ADIDAS', 'WOODLAND', 'ALENA',
            'SUPERDRY', 'JEWELLERY', 'CLOTHING', 'MIN', 'MHP', 'BEAUTYPROMO', 'TALLY', 'INDIE', 'GUESS',
            'ADIDASFRESH', 'PUMA', 'ANCESTRY', 'ASOS', 'ZAVERI', 'TOMMY', 'SUIT', 'FOOTWEAR', 'FIRST',
            'FEATURED', 'LOUIS', 'JOHN', 'GAS', 'CLOSET', 'BRAVE'
        }
        products = pulled_data.get("products.json", [])
        if isinstance(products, list):
            for p in products:
                c_code = (p.get('coupon_code') or '').strip().upper()
                net_d = float(p.get('net_discount_percent') or 0.0)
                mrp = float(p.get('mrp') or 0.0)
                final_p = float(p.get('final_price') or 0.0)
                if net_d < 70.0 or c_code in non_vouchers or (mrp > 0 and (mrp - final_p)/mrp < 0.699):
                    continue
                cur.execute('''
                    INSERT OR REPLACE INTO verified_products (
                        id, name, brand, category, department, mrp, selling_price,
                        final_price, base_discount_percent, net_discount_percent,
                        formula_desc, coupon_code, coupon_slug, product_url, image_url, scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    p.get('id'), p.get('name'), p.get('brand'), p.get('category'), p.get('department'),
                    p.get('mrp'), p.get('selling_price'), p.get('final_price'),
                    p.get('base_discount_percent'), p.get('net_discount_percent'),
                    p.get('formula_desc', ''), p.get('coupon_code'), p.get('coupon_slug', ''),
                    p.get('product_url'), p.get('image_url', '')
                ))

        # Import campaigns
        campaigns = pulled_data.get("campaigns.json", [])
        if isinstance(campaigns, list):
            for c in campaigns:
                cur.execute('''
                    INSERT OR REPLACE INTO filtered_campaigns (
                        curated_id, code, title, description, details_url, promo_type,
                        department, brands, min_realized_discount, max_realized_discount,
                        min_price, max_price, min_base_needed, applied_filter_tier,
                        has_70_plus_verified, is_standalone_deal, total_verified_skus, scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    c.get('curated_id'), c.get('code'), c.get('title'), c.get('description'),
                    c.get('details_url'), c.get('promo_type'), c.get('department'),
                    c.get('brands'), c.get('min_realized_discount'), c.get('max_realized_discount'),
                    c.get('min_price'), c.get('max_price'), c.get('min_base_needed', 0.0),
                    c.get('applied_filter_tier'), 1 if c.get('has_70_plus_verified') else 0,
                    1 if c.get('is_standalone_deal') else 0, c.get('total_verified_skus', 0)
                ))

        # Import history
        history = pulled_data.get("history.json", [])
        if isinstance(history, list) and history:
            for h in history:
                cur.execute('''
                    INSERT OR REPLACE INTO sync_history (
                        sync_id, timestamp, formatted_time, duration_seconds,
                        added_coupons, updated_coupons, removed_coupons,
                        added_count, updated_count, removed_count,
                        active_70_count, total_campaigns, total_deals,
                        highlights, changes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    h.get('sync_id'), h.get('timestamp'), h.get('formatted_time'),
                    h.get('duration_seconds', 0.0),
                    json.dumps(h.get('added_coupons', [])),
                    json.dumps(h.get('updated_coupons', [])),
                    json.dumps(h.get('removed_coupons', [])),
                    h.get('added_count', 0), h.get('updated_count', 0), h.get('removed_count', 0),
                    h.get('active_70_count', 0), h.get('total_campaigns', 0), h.get('total_deals', 0),
                    json.dumps(h.get('highlights', [])),
                    json.dumps(h.get('changes', []))
                ))

        conn.commit()
        conn.close()
        print("  ✓ Local SQLite database fully synchronized!")

    meta = pulled_data.get("metadata.json", {})
    stats = meta.get("stats", {})
    print("\n========================================================")
    print("📊 Latest Live Cloud Dataset Stats:")
    print(f"  • Verified ≥70% Campaigns: {stats.get('verified_70_plus_campaigns', 'N/A')} (Total: {stats.get('total_campaigns', 'N/A')})")
    print(f"  • Verified Clearance Products: {stats.get('verified_70_plus_products', 'N/A')}")
    print(f"  • Tracked Brands: {stats.get('total_brands', 'N/A')}")
    print(f"  • Exported At: {meta.get('exported_iso', 'N/A')}")
    print("========================================================")

if __name__ == "__main__":
    pull_live_data()
