# Deploying to Azure

This puts WhyItMatters on a public URL for the judges, from a browser only (phone works too). Total time about 30 minutes, most of it waiting. The judging period runs to **10 November 2026**, so the app must stay up until then.

What you end up with:

- The app on **Azure Container Apps**, running the image that GitHub Actions builds from this repo's Dockerfile and publishes to GHCR (`ghcr.io/isaacboque/why-it-matters:latest`), with one replica kept warm so nobody waits for a cold start.
- The agent pipeline running as a **Microsoft Agent Framework** workflow (`WIM_ENGINE=agent_framework`).
- Optional: captions written by a model deployed in **Microsoft Foundry**, still checked number by number by the Verifier.

## 1. Azure account (10 min)

1. Go to <https://azure.microsoft.com/free> and choose **Try Azure for free** (or **Start free**).
2. Sign in with a personal Microsoft account, not the work one, and verify by phone and card. The card is identity only: the free account gives USD 200 of credit for 30 days and does not charge unless you upgrade.
3. When it finishes you land in the Azure portal: <https://portal.azure.com>.

Cost check: one warm replica (1 vCPU, 2 GiB) is a few dollars a day, well inside the credit until 10 November. There is no Azure container registry to pay for. The model calls are cents per match.

## 2. A model in Microsoft Foundry (optional, 10 min)

Skip this section to run on the offline templates (English, Spanish, Catalan); everything else works the same.

1. Open <https://ai.azure.com> (Microsoft Foundry) with the same account.
2. **Create project**. Name: `whyitmatters`. Let it create a new hub/resource in **West Europe** or **Sweden Central**.
3. In the project, open **Models + endpoints** → **Deploy model** → **Deploy base model**. Pick **gpt-4o-mini** (or **gpt-4.1-mini** if listed). Deployment type **Global Standard**, then **Deploy**.
4. On the deployment page copy three things:
   - **Target URI**: keep only the start, `https://<resource>.openai.azure.com/`
   - **Key**
   - **Deployment name**, for example `gpt-4o-mini`

## 3. Make the image public (once, 2 min)

Why GHCR: free Azure subscriptions refuse to build images (`TasksOperationsNotAllowed: ACR Tasks requests ... are not permitted`), so the script deploys an image that GitHub already built. Azure then has to pull it without a login:

1. On GitHub, open your profile, then **Packages**, then **why-it-matters** (it exists after the first run of the *Publish image* workflow on `main`).
2. **Package settings**, then **Change visibility**, then **Public**.

## 4. Deploy from Cloud Shell (5 min, mostly waiting)

1. In the portal, click the **Cloud Shell** icon (`>_`, top bar). Choose **Bash**. If it asks for storage, accept the default (or "No storage account required").
2. Paste:

   ```bash
   git clone https://github.com/isaacboque/why-it-matters.git
   cd why-it-matters
   ```

3. The default resource group is `rg-wim-se` in Sweden Central; there is nothing to set. Only if you did section 2, paste your values (the key is stored as a secret in Azure and never printed):

   ```bash
   export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
   export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"
   export AZURE_OPENAI_API_KEY="<key>"
   ```

4. Deploy:

   ```bash
   bash infra/deploy.sh
   ```

   The script registers the services it needs, creates the app from the GHCR image (no Docker or build on your side), keeps one replica warm (`--min-replicas 1`, so judges never hit a cold start), adds the model secret if you set it, and waits until `/health` answers. It ends by printing the URL.

## 5. Check it

- Open the printed URL. You should see the Match Centre. Pick a match, set Pace to **Live**, press **Kick off**.
- `<url>/health` should show `"engine":"agent_framework"`, and `"generator":"llm via azure openai / foundry"` if section 2 was done.
- In the **Trust** tab, the flow says "runs as a Microsoft Agent Framework workflow".
- The first minute after a deploy, the featured matches (`WIM_WARM_SEEDS`) are pre-computed in the background; other seeds compute on first request, which can take up to a minute with the model on.

## 6. Put the URL in the submission

- Paste the URL into the submission form and the README ("Try it").
- No login is needed, as the rules require.

## Updating after a change on main

GitHub rebuilds the image on every push to `main` (about 3 minutes; watch the *Publish image* run). Then in Cloud Shell:

```bash
cd ~/why-it-matters && git pull && bash infra/redeploy.sh
```

`redeploy.sh` is one `az containerapp update --image ... --revision-suffix ...`: the new suffix forces Azure to pull the fresh `:latest`, and the settings and the Foundry secret stay as they are. Re-running `bash infra/deploy.sh` also works (it adds a new suffix each time). To switch Foundry on or change the key later, export the three `AZURE_OPENAI_*` variables from section 2 and run `bash infra/deploy.sh` again.

## Switching it off after judging

After 10 November 2026:

```bash
az group delete --name rg-wim-se --yes
```

## If something fails

| Message | What to do |
| --- | --- |
| `The subscription is not registered to use namespace` | Run the script again; registration can take a few minutes the first time. |
| `RequestDisallowedByAzure ... region is currently not accepting new customers` | Some regions refuse new subscriptions. The script defaults to Sweden Central; try `export LOCATION=northeurope` and a fresh group name (`export RG=rg-wim-ne`), because a resource group cannot change region. |
| `MissingSubscriptionRegistration` or a quota error | Try another region as in the row above. |
| `TasksOperationsNotAllowed ... ACR Tasks` | You used `BUILD_IN_AZURE=1` on a free subscription. Run `bash infra/deploy.sh` without it (it deploys the GHCR image). |
| `Failed to pull image` or `unauthorized` | The GHCR package is still private: do section 3. |
| The page loads but no match starts | Open `<url>/health`. If it does not answer, run `az containerapp logs show -n whyitmatters -g rg-wim-se --follow` and look at the last lines. |
| Captions stay in English for other languages | The model is not on: check the three `AZURE_OPENAI_*` values and re-run the script. |
