# Deploying to Azure

This puts WhyItMatters on a public URL for the judges, from a browser only (phone works too). Total time about 30 minutes, most of it waiting. The judging period runs to **10 November 2026**, so the app must stay up until then.

What you end up with:

- The app on **Azure Container Apps**, built from this repo's Dockerfile, with one replica kept warm so nobody waits for a cold start.
- The agent pipeline running as a **Microsoft Agent Framework** workflow (`WIM_ENGINE=agent_framework`).
- Optional: captions written by a model deployed in **Microsoft Foundry**, still checked number by number by the Verifier.

## 1. Azure account (10 min)

1. Go to <https://azure.microsoft.com/free> and choose **Try Azure for free** (or **Start free**).
2. Sign in with a personal Microsoft account, not the work one, and verify by phone and card. The card is identity only: the free account gives USD 200 of credit for 30 days and does not charge unless you upgrade.
3. When it finishes you land in the Azure portal: <https://portal.azure.com>.

Cost check: one warm replica (1 vCPU, 2 GiB) plus the container registry is a few dollars a day, well inside the credit until 10 November. The model calls are cents per match.

## 2. A model in Microsoft Foundry (optional, 10 min)

Skip this section to run on the offline templates (English, Spanish, Catalan); everything else works the same.

1. Open <https://ai.azure.com> (Microsoft Foundry) with the same account.
2. **Create project**. Name: `whyitmatters`. Let it create a new hub/resource in **West Europe** or **Sweden Central**.
3. In the project, open **Models + endpoints** → **Deploy model** → **Deploy base model**. Pick **gpt-4o-mini** (or **gpt-4.1-mini** if listed). Deployment type **Global Standard**, then **Deploy**.
4. On the deployment page copy three things:
   - **Target URI**: keep only the start, `https://<resource>.openai.azure.com/`
   - **Key**
   - **Deployment name**, for example `gpt-4o-mini`

## 3. Deploy from Cloud Shell (10–15 min, mostly waiting)

1. In the portal, click the **Cloud Shell** icon (`>_`, top bar). Choose **Bash**. If it asks for storage, accept the default (or "No storage account required").
2. Paste:

   ```bash
   git clone https://github.com/isaacboque/why-it-matters.git
   cd why-it-matters
   ```

3. Only if you did section 2, paste your values (the key is stored as a secret in Azure and never printed):

   ```bash
   export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
   export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"
   export AZURE_OPENAI_API_KEY="<key>"
   ```

4. Deploy:

   ```bash
   bash infra/deploy.sh
   ```

   The script registers the services it needs, builds the image in Azure (no Docker on your side), creates the app, keeps one replica warm, adds the model secret if you set it, and waits until `/health` answers. It ends by printing the URL.

## 4. Check it

- Open the printed URL. You should see the Match Centre. Pick a match, set Pace to **Live**, press **Kick off**.
- `<url>/health` should show `"engine":"agent_framework"`, and `"generator":"llm via azure openai / foundry"` if section 2 was done.
- In the **Trust** tab, the flow says "runs as a Microsoft Agent Framework workflow".
- The first minute after a deploy, matches 7, 11 and 23 are pre-computed in the background; other seeds compute on first request, which can take up to a minute with the model on.

## 5. Put the URL in the submission

- Paste the URL into the submission form and the README ("Try it").
- No login is needed, as the rules require.

## Updating after a change on main

Run the same command again in Cloud Shell:

```bash
cd ~/why-it-matters && git pull && bash infra/deploy.sh
```

## Switching it off after judging

After 10 November 2026:

```bash
az group delete --name rg-whyitmatters --yes
```

## If something fails

| Message | What to do |
| --- | --- |
| `The subscription is not registered to use namespace` | Run the script again; registration can take a few minutes the first time. |
| `RequestDisallowedByAzure ... region is currently not accepting new customers` | Some regions refuse new subscriptions. The script defaults to Sweden Central; try `export LOCATION=northeurope` and a fresh group name (`export RG=rg-wim-ne`), because a resource group cannot change region. |
| `MissingSubscriptionRegistration` or a quota error | Try another region as in the row above. |
| The page loads but no match starts | Open `<url>/health`. If it does not answer, run `az containerapp logs show -n whyitmatters -g rg-whyitmatters --follow` and look at the last lines. |
| Captions stay in English for other languages | The model is not on: check the three `AZURE_OPENAI_*` values and re-run the script. |
