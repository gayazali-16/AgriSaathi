# Deploy AgriSaathi: plain-language guide

This guide matches **https://github.com/gayazali-16/AgriSaathi**. It packages the
React frontend and FastAPI backend together using the included Dockerfile, then
publishes one HTTPS website on Google Cloud Run. You do not deploy Vite separately.

## Understand the limits first

- This is a **public demonstration**, with sample usernames and public password
  `123`. Use synthetic contact details and photos. `DEMO_MODE=false` disables login;
  it does not add production authentication.
- Your laptop's `.env`, database, questions, officer notes, uploads and recordings
  are excluded from the build. The hosted app starts with sample field profiles
  and empty case/advisory history. Prepared reference data is included.
- SQLite and uploaded photos are stored on the container's local filesystem.
  **Cloud Run can lose these when an instance restarts, is replaced or is redeployed.**
  Minimum/maximum instance settings do not make storage permanent. Keep this route
  for a rehearsed demonstration. Permanent records need a host with a persistent
  local disk or a separately implemented storage migration; do not mount SQLite
  on a shared network filesystem.
- Billing is required. Builds, image storage, secrets and the running service can
  incur charges. Set billing budget alerts and monitor usage; alerts do not cap spending.

No deployed URL is asserted by this guide. Successful local tests or a health
response do not prove a live Gemini answer on the hosted website.

## 1. Create a Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Sign in. Use the project selector at the top, then **New Project**.
3. Name it `AgriSaathi Demo` and create it. Select that project.
4. Open **Billing** and link a billing account. In Billing, optionally create a
   budget with email alerts for your chosen spending level.
5. Copy the **Project ID**, such as `agrisaathi-demo-123456`. This is different
   from the display name. If using an organization-managed project, you need its
   administrator to grant deployment/build/secret permissions and allow a public
   Cloud Run service.

## 2. Install Google Cloud CLI

Follow [Google's Windows installer instructions](https://docs.cloud.google.com/sdk/docs/install-sdk/).
Open a **new PowerShell window** afterward and check:

```powershell
gcloud --version
git --version
```

The cloud route does not require Docker Desktop, a local Python environment or
local npm installation: Cloud Build installs and packages the declared dependencies.
They are only needed if you also run the local README setup.

## 3. Open the clean repository and sign in

If you have not cloned the submitted repo yet, choose a folder and run:

```powershell
git clone https://github.com/gayazali-16/AgriSaathi.git
cd AgriSaathi
```

If you already have it, open PowerShell in its folder instead. For the project
owner's cleaned checkout that is `D:\CODE-FOR-COMMUNITIES\AgriSaathi`.
Confirm this folder contains `Dockerfile`, `.gcloudignore`, `requirements.txt`,
`backend/` and `frontend/`.

Run:

```powershell
gcloud auth login
```

A browser opens; sign in as the account with access to your project. Then replace
`YOUR_PROJECT_ID` below with your actual ID:

```powershell
$cloudProject = 'YOUR_PROJECT_ID'
$cloudRegion = 'asia-south1'
gcloud config set project $cloudProject
```

`asia-south1` is Mumbai. Use this same terminal for the rest of the commands so
the variables remain available. Run each block separately and stop if it fails.

## 4. Enable the required cloud services

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com compute.googleapis.com
```

Wait for success. These enable website hosting, remote builds, package storage
and private secrets. If permission is denied, check the selected project and ask
its administrator for the missing permission; do not continue with failed setup.

## 5. Build and store the application package

Create the image repository once:

```powershell
gcloud artifacts repositories create agrisaathi --repository-format=docker --location=$cloudRegion
```

If it already exists in that project/region, skip this creation command. Build:

```powershell
$imageUri = "${cloudRegion}-docker.pkg.dev/${cloudProject}/agrisaathi/app:demo"
gcloud builds submit --ignore-file=.gcloudignore --tag $imageUri .
```

Wait for **SUCCESS**. The Dockerfile builds the frontend and includes it in the
Python image. `.gcloudignore` excludes keys, private runtime state, dependencies
and recordings from the upload; `.dockerignore` also excludes them from the image.
Do not remove these protections to solve a build error.

If this step reports build-service-account permission errors, open **Cloud Build
→ History → the failed build → Logs**. Have the project administrator grant the
reported missing build/log/storage/image permissions to the actual build account.
Do not grant the app account Owner/Editor or paste a secret into build arguments.
Official instructions: [build a Docker image](https://docs.cloud.google.com/build/docs/build-push-docker-image)
and [build-command reference](https://docs.cloud.google.com/sdk/gcloud/reference/builds/submit).

## 6. Create two private secrets

Use the Console search bar to open **Secret Manager** and confirm the project.

### Session secret

Generate a random value into your clipboard without displaying it:

```powershell
$sessionBytes = New-Object byte[] 48
$sessionGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$sessionGenerator.GetBytes($sessionBytes)
[Convert]::ToBase64String($sessionBytes) | Set-Clipboard
$sessionGenerator.Dispose()
```

1. Click **Create secret**.
2. Name: `agrisaathi-session-secret`.
3. Paste the clipboard into **Secret value**.
4. Create the secret. Its first version is `1`.
5. Clear the clipboard after saving: `Set-Clipboard -Value ''`.

Keep this value stable across deployments; deliberately rotating it signs users
out. Do not use the public demo password as the session secret.

### Gemini key

1. Obtain your working API key privately from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create another secret named `agrisaathi-gemini-key`.
3. Paste the API key in Secret value and create it.

Keys stay on the backend. Never commit `.env`, post keys in chat, show them in a
recording or embed them in frontend code. Secret creation instructions:
[Google Secret Manager](https://docs.cloud.google.com/secret-manager/docs/creating-and-accessing-secrets).

An AI key is needed for generated guidance. Hosting the website alone cannot fix
a quota restriction, unavailable model, disabled account or invalid key.

## 7. Let the website read those secrets

Create the app's service account once:

```powershell
gcloud iam service-accounts create agrisaathi-demo
$serviceAccount = "agrisaathi-demo@${cloudProject}.iam.gserviceaccount.com"
```

If it already exists, skip the creation command but still set `$serviceAccount`.
Grant that account access to the two secrets:

```powershell
gcloud secrets add-iam-policy-binding agrisaathi-session-secret --member="serviceAccount:$serviceAccount" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding agrisaathi-gemini-key --member="serviceAccount:$serviceAccount" --role=roles/secretmanager.secretAccessor
```

The account runs the app; it is not the account that builds the image. Secret
access uses [Cloud Run's documented service-identity permissions](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## 8. Deploy the website

Paste the entire line:

```powershell
gcloud run deploy agrisaathi-demo --image=$imageUri --region=$cloudRegion --service-account=$serviceAccount --allow-unauthenticated --port=8000 --concurrency=8 --min-instances=1 --max-instances=1 --set-env-vars="APP_ENV=production,DEMO_MODE=true,ENABLE_RECORDED_OBSERVATIONS=true,ENABLE_NO_KEY_WEATHER=true" --set-secrets="SESSION_SECRET=agrisaathi-session-secret:1,GEMINI_API_KEY=agrisaathi-gemini-key:1"
```

Wait for completion. `--allow-unauthenticated` makes the website reachable by
judges; the app still presents its public demonstration login. Production startup
requires a stable 32+ character session secret and an explicit demo flag. Port
8000 is the internal container port; local Vite port 5174 is not deployed.

The command uses version `1` of each new secret. If using existing secrets, select
their actual numbered versions. Do not add `APP_ENV=development` on the hosted app.
Minimum one instance helps the demonstration stay warm and can add idle costs;
maximum one limits scaling but does not guarantee permanent or shared state.

The default Gemini primary/fallback model IDs come from the current code. If
your working local setup uses another account-supported primary model, add
`GEMINI_MODEL=YOUR_SUPPORTED_MODEL_ID` to the environment-variable list before
deploying. A displayed model name or catalogue entry alone does not prove your
account can generate with it.

Official deployment details: [Cloud Run container deployment](https://docs.cloud.google.com/run/docs/deploying).

## 9. Get the link and test it

```powershell
$serviceUrl = gcloud run services describe agrisaathi-demo --region=$cloudRegion --format='value(status.url)'
$serviceUrl
Invoke-RestMethod "$serviceUrl/api/v1/health"
```

Open the printed HTTPS URL in a fresh browser. The health result should say OK.
Your laptop can then be turned off; Google is running the website.

Follow [the judge journey](docs/demo-script.md) on this URL:

1. Ramesh asks a new synthetic question. Confirm an actual AI answer, or the honest
   failure category. A configured key in health is not a live-call verification.
2. Send a consented officer request using synthetic contact data.
3. Rajesh reviews/approves and separately publishes a public Rice advisory.
4. Lakshmi sees that specific title for Krishna Rice, not for Maize.
5. Verify sign-out, language controls, source limits and keyboard/mobile usability.

If a step fails, check **Cloud Run → agrisaathi-demo → Logs**. Share only redacted
errors, not keys or private farmer inputs. Do not claim the hosted journey passed
merely because local automated tests passed.

## 10. Optional: use OpenWeather instead of no-key estimates

Without an OpenWeather key the hosted app requests labelled Open-Meteo current
model estimates. Failed requests stay unavailable; NASA historical climate does
not substitute for current weather. Review provider terms/limits.

To use your OpenWeather account:

1. Create secret `agrisaathi-openweather-key` in Secret Manager with its key.
2. Grant the app account access:

```powershell
gcloud secrets add-iam-policy-binding agrisaathi-openweather-key --member="serviceAccount:$serviceAccount" --role=roles/secretmanager.secretAccessor
```

3. Update only that secret mapping, selecting its actual numbered version:

```powershell
gcloud run services update agrisaathi-demo --region=$cloudRegion --update-secrets="OPENWEATHER_API_KEY=agrisaathi-openweather-key:1"
```

This creates a new revision and may reset local case history. Verify a returned
OpenWeather reading afterward. On future full redeploys, include this mapping in
Step 8's `--set-secrets` list, because that flag replaces the list.

## Updating the deployed application

Open the submitted repo in PowerShell, pull the desired changes, and repeat Step
3's project/region assignments. Repeat Step 5's image build, Step 7's service-account
assignment, then Step 8's deployment. Reuse the repository, account and stable
secrets; do not recreate them. Redeploying can reset local cases and advisories.

## Optional local Docker check

With Docker Desktop running and a private `.env` configured from the README:

```powershell
docker build -t agrisaathi:demo .
docker run --name agrisaathi-demo --rm -p 8002:8000 --env-file .env -e APP_ENV=production -e DEMO_MODE=true --mount type=volume,src=agrisaathi-runtime,dst=/app/backend/data/runtime --mount type=volume,src=agrisaathi-uploads,dst=/app/backend/data/uploads agrisaathi:demo
```

Your `.env` must contain the generated session secret; an empty secret deliberately
fails production startup. Open `http://localhost:8002` and its `/api/v1/health`.
Named Docker volumes preserve local container data across runs; they are not
transferred to Cloud Run. Back them up with the app stopped.

## What still needs the project owner

- A Google Cloud project with billing and sufficient deployment/build permissions.
- A valid Gemini key and a model the account can actually use.
- Optional OpenWeather credentials if town readings are preferred over estimates.
- A real hosted health and farmer/officer/receiving-state check after deployment.
- A persistent-storage and real-authentication plan before handling real farmer data.

This guide prepares those steps; it does not claim cloud deployment or provider
verification has been completed. [Cloud Run's filesystem contract](https://docs.cloud.google.com/run/docs/container-contract)
explains the storage limitation.
