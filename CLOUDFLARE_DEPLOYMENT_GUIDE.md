# Cloudflare Deployment & Architecture Guide: Pages, Workers, CI/CD & Free Hosting

This guide provides a comprehensive breakdown of deploying the **AjioRadar Flash Deals & 70%+ Deep Steals Platform** to Cloudflare, comparing **Cloudflare Pages** vs. **Cloudflare Workers**, explaining the "Sync Now" client lifecycle, and demonstrating how to run the entire stack **100% free forever**.

---

## 1. What is `export_cloudflare.py` and Why is it Needed?

[`backend/export_cloudflare.py`](file:///Users/nikunjbhartia/Desktop/projects/ajio/ajio-deal-matrix/backend/export_cloudflare.py) is the **Edge Static Bundle Generator**.

```
  ┌─────────────────────────┐
  │  SQLite DB (deals.db)   │ ◄── Populated by Universal Category Crawler & Campaign Validator
  │  • 430 Promo Campaigns  │
  │  • 5,000+ Real Deals    │
  │  • 496 Indexed Brands   │
  └────────────┬────────────┘
               │
               ▼  python3 backend/export_cloudflare.py
  ┌───────────────────────────────────────────────────────────┐
  │                   dist/  (Deployable Bundle)              │
  │  ├── index.html            (High-Performance Responsive UI│
  │  └── data/                                                │
  │      ├── campaigns.json    (Pre-calculated voucher math)  │
  │      ├── products.json     (5,000+ verified 70%+ items)   │
  │      ├── taxonomy.json     (11 Depts & 45 Subcategories)  │
  │      └── metadata.json     (Brands, stats & sync times)   │
  └───────────────────────────────────────────────────────────┘
```

### Key Rationale:
1. **Zero Database Infrastructure Overhead**: Cloudflare Pages distributes static assets to 300+ global edge cities. It serves files in <10 milliseconds with zero server management.
2. **Infinite Free Traffic**: Serving JSON files from Cloudflare edge caches consumes 0 CPU time, allowing unlimited page views and zero hosting bills.
3. **Dual-Mode UI Rehydration**: When running locally or on a VPS with Python, the web app queries `/api/products` and `/api/campaigns`. When hosted as a static site on Cloudflare Pages, it automatically falls back to loading `data/products.json` and `data/campaigns.json` seamlessly.

---

## 2. Cloudflare Workers vs. Cloudflare Pages: What is Workers For?

### What is Cloudflare Workers?
Cloudflare Workers is a **Serverless V8 JavaScript/WebAssembly Execution Environment** that runs code directly on Cloudflare's edge network without traditional servers.

| Feature / Dimension | Cloudflare Pages (Recommended) | Cloudflare Workers (Edge Compute) |
| :--- | :--- | :--- |
| **Primary Purpose** | Hosting Web Apps, SPAs & Static Assets | Dynamic API routing, Request Rewriting, Edge logic |
| **Cost Model** | **100% Free** (Unlimited bandwidth & requests) | **100% Free** (Up to 100,000 requests/day) |
| **Can it host the Web UI?** | ✅ Native (Direct HTML/CSS/JS delivery) | ✅ Yes (via Workers Static Assets / KV Store) |
| **Can it run the Ajio Crawler?** | ❌ Run on external runner (GitHub Actions) | ❌ **BLOCKED by Akamai Bot Defense** |
| **Global Latency** | **Sub-10ms** (Cached at Cloudflare Edge CDN) | **15ms – 50ms** (V8 isolate compute execution) |

### Why Cloudflare Workers Alone CANNOT Run the Ajio Crawler:
* **The Bot Detection Barrier**: Ajio is protected by Akamai Bot Manager. Akamai analyzes:
  1. **IP Subnet Reputation**: Cloudflare Workers execute on known datacenter IP subnets (`AS13335`), which are flagged as automated bot servers.
  2. **TLS ClientHello Fingerprints**: Workers use standard V8 `fetch()` with fixed Cloudflare TLS cipher suites. They cannot use raw socket mutation or compile C-extensions like `curl_cffi` to mimic real macOS Safari / Chrome TLS handshakes.
* **The Result**: If a Cloudflare Worker directly requests Ajio, Akamai immediately returns **HTTP 403 Forbidden**.
* **The Solution**: Keep the web hosting on **Cloudflare Pages** (static edge) and run the crawler on **GitHub Actions / Cloud Runners** which have legitimate browser TLS impersonation capabilities.

---

## 3. What Happens on the "Sync Now" Click Event?

The UI has a dual-aware execution handler built into `triggerManualSync()`:

```
                            USER CLICKS "SYNC NOW"
                                      │
                                      ▼
                        Checks if Backend API is Active
                                      │
                     ┌────────────────┴────────────────┐
                     ▼                                 ▼
         [ Live FastAPI Backend ]            [ Static Cloudflare Pages ]
                     │                                 │
     1. Dispatches POST /api/sync/trigger     1. Catches 404 / static mode
     2. Runs live category & campaign crawl   2. Generates cache-busting timestamp (?t=1724285400)
     3. Queries updated SQLite records        3. Re-fetches data/campaigns.json?t=...
     4. Displays real-time delta toast:          and data/products.json?t=...
        "+8 new codes, 124 updated"           4. Instantly updates client filter memory
                                              5. Displays: "Edge deals refreshed!
                                                 Automated sync runs every 30m."
```

When hosted statically, clicking **"Sync Now"** immediately forces the user's browser to bypass local browser caches and pull the latest production dataset deployed to Cloudflare's CDN.

---

## 4. Is the GitHub Actions Deal Scanner Really 100% Free?

**YES, it is completely free.**

### Cost Breakdown:
1. **Public Repositories**:
   * GitHub Actions provides **100% Unlimited Free Minutes** for all public open-source repositories.
   * Total Cost: **$0.00 / month**.
2. **Private Repositories**:
   * GitHub gives every free account **2,000 free Linux build minutes per month**.
   * Our parallel category crawler takes approximately **40 seconds** per sweep.
   * Running 48 times/day (every 30 minutes) for 30 days = ~1,440 runs $\times$ 0.67 minutes $\approx$ **960 minutes/month** (well within the 2,000 free monthly quota).
3. **Cloudflare Pages**:
   * Free Tier includes unlimited bandwidth, unlimited requests, and up to 500 builds per month.
   * Total Cost: **$0.00 / month**.

---

## 5. Three Step-by-Step Deployment Methods

### Method 1: Instant Terminal Deploy via Wrangler CLI (30 Seconds)

1. Open your terminal in the `ajio-deal-matrix` directory:
   ```bash
   cd /Users/nikunjbhartia/Desktop/projects/ajio/ajio-deal-matrix
   ```
2. Run the deployment command:
   ```bash
   npx wrangler pages deploy dist --project-name=ajioradar
   ```
3. Authorize your Cloudflare account in the browser pop-up.
4. Wrangler uploads `dist/` and provides your live website URL (e.g. `https://ajioradar.pages.dev`).

---

### Method 2: Connect GitHub Repository to Cloudflare Pages Dashboard

1. Push your repository to GitHub:
   ```bash
   cd /Users/nikunjbhartia/Desktop/projects/ajio/ajio-deal-matrix
   git init
   git add .
   git commit -m "Deploy AjioRadar"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/ajio-deal-matrix.git
   git push -u origin main
   ```
2. Log in to the [Cloudflare Dashboard](https://dash.cloudflare.com/) $\to$ **Compute (Workers & Pages)** $\to$ **Create application** $\to$ **Pages** $\to$ **Connect to Git**.
3. Select `ajio-deal-matrix` and set build parameters:
   * **Framework preset**: `None`
   * **Build command**: `python3 backend/export_cloudflare.py`
   * **Build output directory**: `dist`
4. Click **Save and Deploy**.

---

### Method 3: Fully Automated 24/7 Deal Refreshes via GitHub Actions

The automated workflow file is located at [`.github/workflows/sync-and-deploy.yml`](file:///Users/nikunjbhartia/Desktop/projects/ajio/ajio-deal-matrix/.github/workflows/sync-and-deploy.yml):

```yaml
name: Sync Deals & Deploy to Cloudflare Pages

on:
  schedule:
    - cron: '*/30 * * * *' # Sweeps every 30 minutes 24/7
  workflow_dispatch:        # Allows manual trigger button in GitHub UI
  push:
    branches: [ main ]

jobs:
  sync-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -r backend/requirements.txt
      - run: |
          cd backend
          python -c "from app.services.sync_daemon import daemon_instance; daemon_instance.perform_full_sync()"
          python export_cloudflare.py
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy dist --project-name=ajioradar
```

#### How to supply secrets:
1. In your GitHub repository, open **Settings** $\to$ **Secrets and variables** $\to$ **Actions**.
2. Add:
   * `CLOUDFLARE_API_TOKEN`: Your Cloudflare API Token (from [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) with `Cloudflare Pages: Edit`).
   * `CLOUDFLARE_ACCOUNT_ID`: Your Account ID (visible on Cloudflare Dashboard homepage right sidebar).
3. The platform will continuously update live verified 70%+ deals around the clock at **$0 cost**.
