import os
import json
import shutil
import time
import sys

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from app.database.storage import DealStorage

def export_for_cloudflare():
    print("[*] Generating production static bundle for Cloudflare Pages...")
    backend_dir = os.path.abspath(os.path.dirname(__file__))
    root_dir = os.path.abspath(os.path.join(backend_dir, ".."))
    candidates = [
        os.path.join(backend_dir, "deals.db"),
        os.path.join(root_dir, "backend", "deals.db"),
        os.path.join(root_dir, "deals.db"),
        os.path.join(root_dir, "..", "ajio-discount-finder", "deals.db"),
        "deals.db"
    ]
    valid_db = next((p for p in candidates if os.path.exists(p) and os.path.getsize(p) > 5000), os.path.join(backend_dir, "deals.db"))
    print(f"[*] Reading dataset from: {valid_db} ({os.path.getsize(valid_db) if os.path.exists(valid_db) else 0} bytes)")
    storage = DealStorage(valid_db)
    
    # 1. Fetch campaigns, products, brands, departments, stats
    campaigns = storage.get_filtered_campaigns(only_verified_70=False)
    products = storage.get_verified_products(min_discount=70.0, limit=5000)
    brands = storage.get_brands()
    departments = storage.get_departments()
    stats = storage.get_stats()

    # 2. Output directory
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
    data_dir = os.path.join(dist_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    # 3. Write data JSONs
    with open(os.path.join(data_dir, "campaigns.json"), "w") as f:
        json.dump([c.model_dump() for c in campaigns], f, indent=2)

    with open(os.path.join(data_dir, "products.json"), "w") as f:
        json.dump([p.model_dump() for p in products], f, indent=2)

    history = storage.get_sync_history(days=30, limit=50)
    with open(os.path.join(data_dir, "history.json"), "w") as f:
        json.dump([h.model_dump() for h in history], f, indent=2)

    featured_file = os.path.join(os.path.dirname(__file__), "app", "database", "featured_brands.json")
    featured_brands_dict = {}
    if os.path.exists(featured_file):
        with open(featured_file) as f:
            featured_brands_dict = json.load(f)

    with open(os.path.join(data_dir, "metadata.json"), "w") as f:
        json.dump({
            "brands": brands,
            "featured_brands": featured_brands_dict,
            "departments": departments,
            "stats": stats,
            "exported_at": time.time(),
            "exported_iso": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }, f, indent=2)

    # 4. Copy curated taxonomy tree
    tax_file = os.path.join(os.path.dirname(__file__), "app", "database", "taxonomy_master.json")
    if os.path.exists(tax_file):
        shutil.copy(tax_file, os.path.join(data_dir, "taxonomy.json"))

    # 5. Copy static index.html to dist/index.html
    frontend_index = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))
    if os.path.exists(frontend_index):
        shutil.copy(frontend_index, os.path.join(dist_dir, "index.html"))

    print(f"[+] Static bundle successfully exported to '{dist_dir}/'!")
    print(f"    * Campaigns exported: {len(campaigns)}")
    print(f"    * Real 70%+ Products exported: {len(products)}")
    print(f"    * Brands indexed: {len(brands)}")
    print(f"    * Complete Taxonomy exported: {os.path.join(data_dir, 'taxonomy.json')}")
    print(f"    * Ready to deploy directly with: npx wrangler pages deploy dist")

if __name__ == "__main__":
    export_for_cloudflare()
