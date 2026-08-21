# AjioRadar • Live Flash Promo Codes & 70%+ Deep Steals Platform

An autonomous deal intelligence engine that continuously discovers, models, and verifies **100% of live flash discount codes and genuine &ge;70% net savings deals** across all Ajio departments and categories.

---

## 1. Product Overview & Core Features

Ajio provides hundreds of overlapping promotional campaigns and coupon codes simultaneously (`NEW30`, `FLASHSALE`, `BUY1GET5FREE`, `DESIDRIP20`, `WISH`, `PUMASPL`, `KIDS30`, etc.). 

**AjioRadar** organizes platform inventory across **3 purpose-built views**:
1. **Flash Promo Collections**: Browse all active voucher codes with pre-applied `:discountranges:` internal search facets to explore full catalog collections of verified &ge;70% items.
2. **Verified 70%+ Products**: Direct catalog item feed (jeans, shirts, sneakers, perfumes, ethnic wear) with ground-truth prices, verified formulas, and buy links.
3. **7-Day Sync Audit & Changelog**: A transparent chronological audit log capturing every newly dropped voucher (`+ Code`), updated price tiers (`~ Code`), and pruned inactive promotions (`- Code`) across 30-minute verification cycles.

---

## 2. Technical Stack

| Layer | Technology | Purpose & Design Decision |
| :--- | :--- | :--- |
| **Frontend UI** | **Vite + Tailwind CSS (Light Blue Sky Theme)** | Zero-framework runtime overhead, instant initial paint, sub-10ms edge caching on Cloudflare Pages. |
| **Backend REST API**| **FastAPI + Uvicorn ASGI** | High-concurrency Python 3 async server with Pydantic v2 strict data schemas. |
| **Parsing Engine** | **Grammar-Based Dynamic Rule Parser** | Pure algorithmic rule parser extracting ratios, percentages, and cart thresholds with **zero hardcoded coupon names**. |
| **Audit & Persistence**| **SQLite (WAL Mode) + 7-Day Changelog** | Lock-free reads, bounded upserts (zero disk bloat), and rolling 7-day audit logs. |
| **In-Memory Cache** | **Python RAM Hot-Cache** | Sub-millisecond query responses for instant filter and search interactions. |
| **Edge Hosting & CI**| **Cloudflare Pages + GitHub Actions** | 100% free global CDN distribution with automated 30-minute background sync. |

---

## 3. End-to-End System Architecture & Data Flow

```
                                      DATA PIPELINE & LIFECYCLE
                                      
  [ Sitemaps & Storefronts ] ──► [ Campaign Harvester ] ──► Seed URLs Pool
                                                                  │
                                                                  ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                           4-TIER MULTI-STAGE VALIDATION ENGINE                         │
  │  1. Primary Faceted Search Query  ──► (e.g., :discountranges:60% and above)           │
  │  2. Relaxed Facet Fallback        ──► (e.g., :discountranges:50% and above)           │
  │  3. Direct Curated SSR Fallback   ──► (/s/<slug>?query=:discount-desc)                │
  │  4. Catalog Endpoint Fallback     ──► (/c/<id>?query=:discount-desc)                  │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                                                  │
                                                                  ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │                         DUAL-LAYER STORAGE & IN-MEMORY HOT CACHE                       │
  │  • In-Memory RAM Cache: Sub-millisecond lookups for 281 Verified Campaigns & Products  │
  │  • SQLite Persistence: Upsert on compound primary keys (zero growth; updates in place) │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────┴───────────────────────────┐
                                      ▼                                                       ▼
                       ┌──────────────────────────────┐                       ┌──────────────────────────────┐
                       │  FastAPI Backend (Port 8088) │                       │ Cloudflare Pages Static Edge │
                       │  (Local & Self-Hosted Runs)  │                       │ (100% Free CDN Distribution) │
                       └──────────────────────────────┘                       └──────────────────────────────┘
```

---

## 4. Key Design Decisions

### A. How Deals Are Kept Fresh & Active Lifecycle Pruning
1. **Initial Hot-State Cold Boot**: On startup, the engine reads the pre-validated snapshot into fast RAM, delivering sub-millisecond API responses immediately.
2. **Dynamic Discovery of New Campaigns**: Every 30 minutes, the background daemon streams `sitemap_landing.xml` and surveys 40+ brand storefront anchors. Any newly published flash codes are dynamically modeled by the grammar parser.
3. **Active Promotion Lifecycle & Automated Deletion**: 
   * Active deals are updated in place with fresh inventory counts and price cuts.
   * If a promotion expires or 0 current items reach &ge;70% net savings, its status is updated (`has_70_plus_verified = 0`, `total_verified_skus = 0`), automatically purging it from the live &ge;70% feed.
4. **Automated Edge Snapshot Persistence**: At the conclusion of every sync run, updated JSON data feeds (`campaigns.json`, `products.json`, `taxonomy.json`) are re-exported into `dist/data/` for serverless Cloudflare Pages distribution.

### B. Universal Dynamic Rule Parser (No Brittle Hardcoding)
Instead of matching static coupon strings, our dynamic parser classifies rules based on grammatical patterns:
* **Buy X Get Y Free (BXGY)**: $\text{Realized Rate} = \frac{Y}{X + Y} \times 100$ (e.g., `BUY 1 GET 5` $\to 83.33\%$).
* **Flat Cart Reductions**: $\text{Rate} = \frac{\text{Discount Amount}}{\text{Min Cart Value}} \times 100$ (e.g., `2000 OFF ON 7999` $\to 25.0\%$).
* **Percentage Vouchers**: Extracts nominal rate $r$ and calculates required base discount:
  $$b_{\text{min}} = \max\left(0, 1 - \frac{0.30}{1 - r}\right) \times 100$$

### C. 11 First-Class Departments & Taxonomy Hierarchy
The system exposes 11 independent first-class departments matching Ajio's official navigation layout:
1. **MEN** (Western Wear, Ethnic Wear, Winterwear, Innerwear, Loungewear, Plus Size)
2. **WOMEN** (Western Wear, Ethnic Wear, Lingerie & Innerwear, Handbags & Wallets, Winterwear, Maternity)
3. **FOOTWEAR** (Men's Casual/Sneakers/Formal/Boots, Women's Heels/Flats/Sandals, Kids Footwear)
4. **GADGETS & TECH** (Smart Wearables, Smartwatches, Fitness Bands, Headphones, TWS Wireless Earbuds, Speakers)
5. **FASHION JEWELLERY** (Men's Bracelets/Chains/Cufflinks/Rings, Women's Earrings/Necklaces/Bangles/Silver)
6. **ACCESSORIES & LUGGAGE** (Backpacks, Trolley Bags, Belts, Caps, Sunglasses, Wallets, Watches, Socks)
7. **KIDS & INFANTS** (Boys Clothing, Girls Clothing, Infants 0-2 Yrs, Toys & Babycare)
8. **BEAUTY & GROOMING** (Skincare, Makeup, Haircare, Fragrances, Men's Grooming)
9. **HOME & KITCHEN** (Bedding & Linen, Cushions, Curtains & Mats, Cookware & Dining, Home Decor, Bath)
10. **INDIE & HANDLOOM** (Handloom Sarees, Chanderi, Ikat, Artisanal Kurtas, Block Print Decor)
11. **LUXE & DESIGNER** (Armani Exchange, Superdry, Tommy Hilfiger, Gas, Steve Madden, Diesel, Aldo)

### D. 5-Layer Fallback Data Preservation Pipeline
To guarantee 100% website uptime and zero data loss during transient upstream network fluctuations:
* **Layer 1 (Live Facet Search)**: Probes internal search bridge with strict base discount tier (`60% and above`).
* **Layer 2 (Relaxed Facet)**: Automatically falls back to `50% and above` if zero results on strict facet.
* **Layer 3 (Direct Curated Collection SSR)**: Queries collection page directly to parse preloaded state.
* **Layer 4 (Direct Catalog Category)**: Probes parent category anchor routes.
* **Layer 5 (Historical Snapshot Retention)**: Retains verified records from previous successful crawl cycle until fresh data is confirmed.

### E. Safe Concurrency & Network Pacing
* **Worker Concurrency**: The validation pool uses **15 worker threads** with connection reuse rather than aggressive socket flooding.
* **Average Load**: 280 queries executed in ~45 seconds every 30 minutes results in a gentle sustained rate of **~0.15 requests/second**, ensuring reliable long-term operation.

---

## 5. Execution & Deployment Guide

### Local Development (FastAPI + Vite)

```bash
# 1. Setup Python Backend Environment
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run initial validation sweep
python3 -c "
from app.services.sync_daemon import daemon_instance
daemon_instance.perform_full_sync()
"

# 3. Start FastAPI Server (Port 8088)
uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload

# 4. (Optional) Run Vite Dev Server with Hot-Reload
cd ../frontend
npm install
npm run dev # Accessible on http://localhost:5173
```

* **Interactive Web Dashboard**: [http://127.0.0.1:8088](http://127.0.0.1:8088)
* **REST API Documentation**: [http://127.0.0.1:8088/docs](http://127.0.0.1:8088/docs)

---

### Free Hosting on Cloudflare Pages

Cloudflare Pages provides global CDN hosting for the frontend and pre-calculated static deal snapshots with <10ms edge latency at **$0 monthly cost**.

#### Option 1: 1-Click Local Terminal Deployment (`deploy.sh`)

Ensure your local `.env` file contains your credentials (see `.env.example`), then run:

```bash
./deploy.sh
```

This automatically:
1. Re-indexes the latest database records and generates fresh JSON snapshots in `dist/data/`.
2. Deploys `dist/` directly to Cloudflare Pages project **`ajioradar`**.

#### Option 2: Automated 24/7 Background Sync (GitHub Actions CI/CD)

The repository includes a 24/7 background automation workflow at [`.github/workflows/sync-and-deploy.yml`](file:///.github/workflows/sync-and-deploy.yml).

Every 30 minutes, a free GitHub Actions cloud runner:
1. Sweeps all 498 subcategories and verifies live flash voucher stacking mathematics.
2. Runs `python3 backend/export_cloudflare.py` to regenerate `dist/data/`.
3. Pushes updated snapshots directly to your live `https://ajioradar.pages.dev` edge deployment using Wrangler.

##### GitHub Secrets Required:
In your GitHub repo $\to$ **Settings** $\to$ **Secrets and variables** $\to$ **Actions**, set:
* `CLOUDFLARE_API_TOKEN`: Your Cloudflare API Token (Permissions: `Cloudflare Pages: Edit`).
* `CLOUDFLARE_ACCOUNT_ID`: Your Cloudflare Account ID.

---

## 6. Repository Layout

```
ajio-deal-matrix/
├── .github/
│   └── workflows/
│       └── sync-and-deploy.yml         # 30-min automated GitHub Actions sync & deploy
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── dynamic_parser.py       # Generalized promo parser (ZERO hardcoded codes)
│   │   │   └── stealth_client.py       # Session pool manager with TLS profile rotation
│   │   ├── database/
│   │   │   ├── navigation_category_seeds.json # 498 official category navigation seeds
│   │   │   ├── taxonomy_master.json    # Complete 11-Department hierarchical category tree
│   │   │   └── storage.py              # SQLite WAL storage & tokenized multi-search
│   │   ├── engines/
│   │   │   ├── campaign_harvester.py   # Sitemap XML & brand storefront harvester
│   │   │   ├── category_crawler.py     # Universal 498-category parallel clearance crawler
│   │   │   └── deal_validator.py       # 4-tier resilient validation & product extraction
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic data schemas
│   │   ├── services/
│   │   │   └── sync_daemon.py          # Continuous 30-min in-memory sync daemon
│   │   └── main.py                     # FastAPI REST API application (Port 8088)
│   ├── export_cloudflare.py            # Static edge exporter script
│   └── requirements.txt                # Python dependencies
├── frontend/
│   └── index.html                      # Mobile-first responsive Dual-Feed SPA
├── dist/                               # Production edge bundle ready for Cloudflare Pages
│   ├── index.html
│   └── data/
│       ├── taxonomy.json               # Full category tree for edge resolution
│       ├── campaigns.json              # 430 campaigns (281 verified ≥70%)
│       ├── products.json               # 5,000+ real verified ≥70% items
│       └── metadata.json               # 496 verified brands & scan timestamps
├── .env.example                        # Template for required environment variables
├── deploy.sh                           # 1-Click executable deployment script
├── CLOUDFLARE_DEPLOYMENT_GUIDE.md      # Detailed Cloudflare Pages vs Workers architecture
├── README.md                           # Comprehensive documentation & system blueprint
└── .gitignore                          # Standard git and credentials exclusions
```
