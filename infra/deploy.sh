#!/usr/bin/env bash
# Deploy WhyItMatters to Azure Container Apps. Built for Azure Cloud Shell (Bash), which already
# has the Azure CLI and is signed in. Step-by-step guide: docs/DEPLOY.md.
#
#   bash infra/deploy.sh
#
# Deploys the image GitHub already built (ghcr.io/isaacboque/why-it-matters:latest, made public).
# Free Azure subscriptions block ACR Tasks, so building in Azure is off by default:
#   IMAGE=ghcr.io/<owner>/<name>:<tag> bash infra/deploy.sh   # another image
#   BUILD_IN_AZURE=1 bash infra/deploy.sh                      # build from source (needs ACR Tasks)
#
# Optional, to switch on the model-written captions (Microsoft Foundry):
#   export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
#   export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"
#   export AZURE_OPENAI_API_KEY="<key>"        # stored as a Container Apps secret, never printed
set -euo pipefail

APP="${APP:-whyitmatters}"
RG="${RG:-rg-wim-se}"
LOCATION="${LOCATION:-swedencentral}"
IMAGE="${IMAGE:-ghcr.io/isaacboque/why-it-matters:latest}"
cd "$(dirname "$0")/.."

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

say "Checking the Azure CLI session"
az account show --query "{subscription:name, user:user.name}" -o table

say "Making sure the Container Apps extension and providers are ready (first time: ~2 min)"
az extension add --name containerapp --upgrade --only-show-errors -y >/dev/null
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry; do
  az provider register --namespace "$ns" --wait --only-show-errors >/dev/null
done

say "Resource group $RG in $LOCATION"
az group create --name "$RG" --location "$LOCATION" --only-show-errors -o none

if [[ "${BUILD_IN_AZURE:-}" == "1" ]]; then
  say "Building the image in Azure and creating the app (5-10 min the first time)"
  SOURCE_ARGS=(--source .)
else
  say "Creating the app from $IMAGE (2-3 min)"
  SOURCE_ARGS=(--image "$IMAGE")
fi
az containerapp up \
  --name "$APP" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  "${SOURCE_ARGS[@]}" \
  --ingress external \
  --target-port 8000 \
  --env-vars WIM_ENGINE=agent_framework WIM_WARM_SEEDS=60,32,51,156,173,194,409,487

say "Keeping one replica warm so judges never hit a cold start"
# a new revision suffix on every run makes Azure pull the current :latest again
REVISION="r$(date -u +%d%H%M%S)"
UPDATE_ARGS=(--revision-suffix "$REVISION")
[[ "${BUILD_IN_AZURE:-}" == "1" ]] || UPDATE_ARGS+=(--image "$IMAGE")
az containerapp update --name "$APP" --resource-group "$RG" "${UPDATE_ARGS[@]}" \
  --min-replicas 1 --max-replicas 3 --cpu 1.0 --memory 2.0Gi --only-show-errors -o none

if [[ -n "${AZURE_OPENAI_ENDPOINT:-}" && -n "${AZURE_OPENAI_DEPLOYMENT:-}" && -n "${AZURE_OPENAI_API_KEY:-}" ]]; then
  say "Switching on model-written captions (Microsoft Foundry deployment $AZURE_OPENAI_DEPLOYMENT)"
  az containerapp secret set --name "$APP" --resource-group "$RG" \
    --secrets "aoai-key=$AZURE_OPENAI_API_KEY" --only-show-errors -o none
  az containerapp update --name "$APP" --resource-group "$RG" --only-show-errors -o none \
    --revision-suffix "r$(date -u +%d%H%M%S)b" \
    --set-env-vars WIM_GENERATOR=llm \
      "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT" \
      "AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT" \
      "AZURE_OPENAI_API_KEY=secretref:aoai-key" \
      "WIM_LLM_MAX_CALLS=${WIM_LLM_MAX_CALLS:-400}"
else
  say "No Foundry credentials set: captions come from the offline templates (en/es/ca)"
fi

URL="https://$(az containerapp show --name "$APP" --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)"

say "Waiting for the app to answer"
for _ in $(seq 1 30); do
  if curl -fsS "$URL/health" >/dev/null 2>&1; then break; fi
  sleep 10
done
curl -fsS "$URL/health" && echo

say "Done"
echo "App:      $URL"
echo "API docs: $URL/docs"
echo "Health:   $URL/health   (engine should say agent_framework)"
echo
echo "To stop paying after judging ends (10 Nov):  az group delete --name $RG --yes"
