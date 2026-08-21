# AjioRadar • Live Flash Promo Codes & 70%+ Deep Steals Platform

An autonomous deal intelligence engine that continuously discovers, models, and verifies **100% of live flash discount codes and genuine &ge;70% net savings deals** across all Ajio departments, categories, and brand storefronts.

---

## 1. Product Overview & Core Features

Ajio provides hundreds of overlapping promotional campaigns and coupon codes simultaneously (`NEW30`, `FLASHSALE`, `BUY1GET5FREE`, `DESIDRIP20`, `WISH`, `PUMASPL`, `KIDS30`, `TRENDS`, etc.). 

**AjioRadar** organizes platform inventory across **3 purpose-built views**:
1. **Flash Promo Collections (580+ Campaigns, 440+ Verified &ge;70%)**: Browse all active voucher codes with pre-applied internal search facets to explore full catalog collections of verified &ge;70% items.
2. **Verified 70%+ Products (11,800+ SKUs)**: Direct catalog item feed (jeans, shirts, sneakers, perfumes, ethnic wear) with ground-truth prices, verified formulas, post-coupon checkout pricing, and direct product links.
3. **Sync Changelog & Delta Timeline**: A transparent 3-layer chronological audit log capturing every newly dropped voucher (`+ Code`), updated price tiers (`~ Code`), and pruned inactive promotions (`- Code`) with Before &rarr; After transition records across hourly verification cycles.

---

## 2. Technical Stack

| Layer | Technology | Purpose & Design Decision |
| :--- | :--- | :--- |
| **Frontend UI** | **Single Page App (Light Blue Sky Theme)** | Zero-framework runtime overhead, instant initial paint, sub-10ms edge caching on Cloudflare Pages. |
| **Backend REST API**| **FastAPI + Uvicorn ASGI** | High-concurrency Python 3 async server with Pydantic v2 strict data schemas. |
| **Parsing Engine** | **Grammar-Based Dynamic Rule Parser** | Pure algorithmic rule parser extracting ratios, percentages, and cart thresholds with **zero hardcoded coupon names**. |
| **Crawler & Registry** | **680 Universal Seeds & 94 Featured Brands** | Sweeps 83 canonical `l1l3nestedcategory` trees and 94 curated brand storefront anchors. |
| **Audit & Persistence**| **SQLite (WAL Mode) + 3-Layer Delta Changelog** | Lock-free reads, bounded upserts (zero disk bloat), and rolling audit logs. |
| **Edge Hosting & CI**| **Cloudflare Pages + GitHub Actions** | 100% free global CDN distribution with automated hourly background sync. |

---

## 3. End-to-End System Architecture & Data Flow

```
                                      DATA PIPELINE & LIFECYCLE
                                      
  [ Sitemaps & 94 Brand Storefronts ] ──► [ Campaign Harvester ] ──► Seed Targets Pool (680 Seeds)
                                                                            │
                                                                            ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
  │                         UNIVERSAL PARALLEL CATEGORY & BRAND CRAWLER                         │
  │  • 83 Canonical L1L3 Category Trees (Men's Pants, Footwear, Women's Ethnic, Tech, etc.)     │
  │  • 94 Featured & Trending Brand Anchors (Benetton, Puma, Levi's, Snitch, Armani, etc.)      │
  │  • Intercepts window.__PRELOADED_STATE__ & calculates net realized checkout discount        │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                            │
                                                                            ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
  │                           BI-DIRECTIONAL DYNAMIC CAMPAIGN SYNTHESIZER                       │
  │  • Reverse-aggregates clearance products into Verified Campaign cards from cold boot        │
  │  • Computes starting post-coupon deals, catalog bounds, and active brand lists              │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                            │
                                                                            ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
  │                         DUAL-LAYER STORAGE & CUMULATIVE PERSISTENCE                         │
  │  • SQLite Persistence: Upsert on compound primary keys (zero growth; updates in place)      │
  │  • Self-Healing Bootstrap (pull_live_data.py): Pulls cumulative CDN snapshot before crawl   │
  │  • Stale Pruner (prune_stale_deals): Cleans items unseen for > 7 days                       │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                            │
                                      ┌─────────────────────────────────────┴─────────────────────────────────────┐
                                      ▼                                                                           ▼
                       ┌──────────────────────────────┐                                            ┌──────────────────────────────┐
                       │  FastAPI Backend (Port 8088) │                                            │ Cloudflare Pages Static Edge │
                       │  (Local & Self-Hosted Runs)  │                                            │ (100% Free CDN Distribution) │
                       └──────────────────────────────┘                                            └──────────────────────────────┘
```

---

## 4. Key Design Decisions & Pricing Mathematics

### A. Post-Coupon Checkout Pricing vs. Ajio Listing Price
When browsing an Ajio collection link, Ajio displays the **pre-coupon selling price** on the grid. 

AjioRadar models the **realized checkout price**:
$$\text{Final Price} = \text{Selling Price} \times \left(1 - \frac{\text{Coupon Discount \%}}{100}\right)$$
$$\text{Net Realized Savings} = \frac{\text{MRP} - \text{Final Price}}{\text{MRP}} \times 100$$

* Example: An MRP ₹4,999 cargo pant on 70% base sale is listed at ₹1,450 on Ajio. Applying coupon `EXTRA30` yields a **final price of ₹1,015**, generating **79.7% net savings**.
* Campaign cards display **`Post-Coupon Deals: Starts @ ₹X (At Checkout)`** representing the lowest ground-truth purchase price achievable for items in that collection.

### B. 3-Layer Delta Audit Trail
Every sync execution records:
1. **Headline Metrics**: Execution duration, total deals verified, active &ge;70% collections.
2. **Executive Highlights**: Summary of newly discovered coupons, upgraded tiers, or expired vouchers.
3. **Itemized Changelog**: Granular before &rarr; after transition records for each modified campaign:
   * `[UPDATED · TRENDS]` Discount 71.0% (45 items) &rarr; 76.5% (62 items)
   * `[NEW · FLASHSALE]` Discovered new promo: FLASHSALE (75% Max, 28 items)
   * `[EXPIRED · WEEKEND50]` Discount dropped to sub-70% (Delisted)

### C. 680-Seed Universal Target Pool & 94 Featured Brands
The crawler targets 680 distinct endpoints organized across 8 lifestyle clusters:
1. **Premium / Luxe**: Armani Exchange, Superdry, Tommy Hilfiger, Diesel, Aldo, Steve Madden
2. **Exclusive**: Trends, Outryt, DnaMX, Teamspirit, Netplay, Avaasa
3. **Footwear & Athletics**: Puma, Nike, Adidas, Skechers, Asics, Red Tape, Campus, Bata, Woodland
4. **Western Wear**: Levi's, GAP, Snitch, The Indian Garage Co, Vero Moda, Only, Rare Rabbit, Spykar, Pepe Jeans
5. **Ethnic Wear**: Biba, Aurelia, Soch, W, Global Desi, Manyavar
6. **Innerwear & Loungewear**: Jockey, Zivame, Enamor, Amante, Hunkemoller
7. **Accessories & Bags**: Mokobara, American Tourister, Fastrack, Fossil, Titan
8. **Tech & Grooming**: Boat, Noise, Fire-Boltt, Boult, Beardo, Bombay Shaving Co

---

## 5. Execution & Deployment Guide

### A. 1-Click Local Data Sync (`./sync_from_cloud.sh`)
To instantly pull the latest cloud discoveries, updated prices, and changelog records to your local machine:

```bash
./sync_from_cloud.sh
```
*Downloads the fresh production bundle from Cloudflare Pages Edge and synchronizes the local `backend/deals.db` database in 2 seconds.*

---

### B. Local Development Server

```bash
# 1. Setup Environment
cd backend
source ../ajio-discount-finder/venv/bin/activate # or create python -m venv venv
pip install -r requirements.txt

# 2. Run local validation sweep
python3 -c "
from app.services.sync_daemon import daemon_instance
daemon_instance.perform_full_sync()
"

# 3. Start FastAPI Backend (Port 8088)
uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
```

* **Interactive Web Dashboard**: [http://127.0.0.1:8088](http://127.0.0.1:8088)
* **REST API Documentation**: [http://127.0.0.1:8088/docs](http://127.0.0.1:8088/docs)

---

### C. Deploy to Cloudflare Pages (`deploy.sh`)

Ensure `.env` contains your Cloudflare credentials (see `.env.example`), then run:

```bash
./deploy.sh
```

---

### D. 24/7 Automated Background Sync (GitHub Actions CI/CD)

The automated workflow ([`.github/workflows/sync-and-deploy.yml`](.github/workflows/sync-and-deploy.yml)) runs every hour:
1. Restores the cumulative database snapshot via GitHub native cache + Cloudflare Edge bootstrap.
2. Sweeps all 680 categories and brand storefronts in parallel.
3. Prunes inactive deals older than 7 days.
4. Generates a rich visual **GitHub Step Summary** report.
5. Deploys updated snapshots to **`ajioradar.pages.dev`**.

---

## 6. Repository Structure

```
ajio-deal-matrix/
├── .github/
│   └── workflows/
│       └── sync-and-deploy.yml         # Hourly automated GitHub Actions sync & deploy
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── dynamic_parser.py       # Generalized promo parser (ZERO hardcoded codes)
│   │   │   └── stealth_client.py       # Session pool manager with TLS profile rotation
│   │   ├── database/
│   │   │   ├── featured_brands.json    # Curated featured brand anchors across 8 clusters
│   │   │   ├── navigation_category_seeds.json # Universal category & brand sweep targets
│   │   │   ├── campaign_seeds.json     # Baseline campaign seed fallback registry
│   │   │   ├── taxonomy_master.json    # Complete hierarchical category tree
│   │   │   └── storage.py              # SQLite storage, campaign synthesizer & delta recorder
│   │   ├── engines/
│   │   │   ├── campaign_harvester.py   # Parallel sitemap & brand storefront harvester
│   │   │   ├── category_crawler.py     # Universal clearance crawler
│   │   │   └── deal_validator.py       # Multi-tier validator & product extractor
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic data schemas
│   │   ├── services/
│   │   │   └── sync_daemon.py          # Background sync orchestrator
│   │   └── main.py                     # FastAPI REST API application (Port 8088)
│   ├── export_cloudflare.py            # Static edge exporter script & GitHub summary generator
│   ├── pull_live_data.py               # 1-click cloud edge -> local database sync script
│   └── requirements.txt                # Python dependencies
├── frontend/
│   └── index.html                      # Light Blue Sky responsive Dual-Feed Web App
├── dist/                               # Production edge bundle for Cloudflare Pages
│   ├── index.html                      # Static Web App entry point
│   ├── 404.html                        # SPA direct deep link fallback
│   ├── _redirects                      # Cloudflare Pages 200 rewrite rule
│   ├── _headers                        # Edge CDN caching & security headers
│   └── data/
│       ├── taxonomy.json               # Category tree for fast client-side filtering
│       ├── campaigns.json              # Harvested and verified campaigns
│       ├── products.json               # Verified clearance products
│       ├── metadata.json               # Indexed brands, scan timestamps & metadata
│       └── history.json                # Rolling 7-day delta changelog & highlights
├── sync_from_cloud.sh                  # 1-Click executable local sync script
├── deploy.sh                           # 1-Click executable deployment script
├── README.md                           # Comprehensive architecture blueprint & guide
└── .gitignore                          # Standard git exclusions
```
