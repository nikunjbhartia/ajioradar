#!/usr/bin/env bash
set -e

# Determine script root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Load environment variables from .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "========================================================"
echo "⚡ AjioRadar • Automated Cloudflare Pages Deployment"
echo "========================================================"

# Validate credentials
if [ -z "$CLOUDFLARE_ACCOUNT_ID" ] || [ -z "$CLOUDFLARE_API_TOKEN" ]; then
  echo "❌ Error: CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is missing in .env"
  exit 1
fi

# 2. Run export_cloudflare.py to package fresh database snapshots
echo "[1/2] 📦 Exporting latest verified deals and taxonomy to dist/..."
python3 backend/export_cloudflare.py

# 3. Deploy to Cloudflare Pages via Wrangler
echo "[2/2] 🚀 Deploying dist/ to Cloudflare Pages (project: ajioradar)..."
CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID" \
CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" \
npx wrangler pages deploy dist --project-name=ajioradar --commit-dirty=true

echo "========================================================"
echo "✅ Deployment complete! Website is live on Cloudflare."
echo "========================================================"
