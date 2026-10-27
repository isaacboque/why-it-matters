#!/usr/bin/env bash
# Pull the newest image and restart the app, keeping its settings and secrets. Run in Azure Cloud Shell:
#
#   bash infra/redeploy.sh
#
# Use it after a merge to main (GitHub Actions rebuilds the image, about 3 minutes).
set -euo pipefail

APP="${APP:-whyitmatters}"
RG="${RG:-rg-wim-se}"
IMAGE="${IMAGE:-ghcr.io/isaacboque/why-it-matters:latest}"

az containerapp update --name "$APP" --resource-group "$RG" \
  --image "$IMAGE" --revision-suffix "r$(date -u +%d%H%M%S)" --only-show-errors -o none

URL="https://$(az containerapp show --name "$APP" --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)"
for _ in $(seq 1 30); do
  if curl -fsS "$URL/health" >/dev/null 2>&1; then break; fi
  sleep 10
done
curl -fsS "$URL/health" && echo
echo "Live: $URL"
