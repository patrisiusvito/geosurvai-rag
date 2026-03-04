# GeoSurvAI — Hugging Face Spaces Deployment Guide

## What Your Supervisor Gets

A clean public link like:
```
https://VtoWantToLearn-geosurvai-rag.hf.space
```
Opens the chat UI in any browser — no login, no setup, works on phone.

---

## Step 1: Create Hugging Face Account

1. Go to https://huggingface.co/join
2. Sign up with GitHub or email — **no credit card needed**

---

## Step 2: Create a New Space

1. Go to https://huggingface.co/new-space
2. Fill in:
   - **Owner:** your username (VtoWantToLearn)
   - **Space name:** `geosurvai-rag`
   - **License:** leave blank (private/proprietary)
   - **SDK:** select **Docker**
   - **Visibility:** **Private** (you can share the link directly, only people with the link can access)
     - Or set **Public** if your supervisor is okay with it being discoverable
3. Click **Create Space**

---

## Step 3: Add Secret Environment Variables

Before pushing code, add your secrets so they don't end up in the repo:

1. Go to your Space → **Settings** → **Variables and secrets**
2. Click **New secret** for each:

| Name | Value |
|------|-------|
| `GEMINI_API_KEY` | your Gemini API key |
| `OLLAMA_HOST` | `http://117.54.250.177:5162` |
| `GEOSURVAI_EMAIL` | your geosurvai.com login email |
| `GEOSURVAI_PASSWORD` | your geosurvai.com login password |
| `GEOSURVAI_LOGIN_URL` | `https://geosurvai.com/login` |

These are injected as environment variables at runtime — never stored in code.

---

## Step 4: Prepare Your Local Files

You need to add 3 new files to your project and upload your database.

### 4a. Copy the new files

Download the provided files and place them in your project:

```
geosurvai-rag/
├── Dockerfile          ← NEW (from this guide)
├── start.py            ← NEW (from this guide)
├── app/
│   └── scraper/
│       └── auth.py     ← NEW (from this guide)
├── db/
│   └── geosurvai.duckdb  ← INCLUDE (your existing database)
└── data/
    └── cache/
        └── precomputed.json  ← INCLUDE (your existing cache)
```

### 4b. Allow database and cache in Git

Your `.gitignore` currently blocks the database and cache files. For cloud deployment,
these files need to be uploaded. Open `.gitignore` in a text editor and **delete** these two lines:

```
db/*.duckdb
data/cache/*.json
```

Just find those lines and delete them. Save the file. That's it — now Git will include
your database and cache when you push to Hugging Face.

### 4c. Update requirements.txt

Make sure your `requirements.txt` has ALL dependencies. It should include at minimum:

```
fastapi
uvicorn[standard]
duckdb
loguru
pandas
openpyxl
playwright
apscheduler
google-genai
httpx
chromadb
```

Check your current working `requirements.txt` in conda and export if needed:
```bash
pip freeze > requirements_full.txt
```
Then keep only the packages you actually import.

---

## Step 5: Modify browser.py for Cloud Login

In `app/scraper/browser.py`, find where the browser is launched (the Chrome profile section).

Add this near the top of the `run` method:

```python
import os
use_cloud_mode = os.getenv("GEOSURVAI_EMAIL", "") != ""
```

Then replace the Chrome profile launch logic. Look for something like:

```python
# OLD: Chrome profile (local only)
context = await playwright.chromium.launch_persistent_context(
    user_data_dir=chrome_profile_path, ...
)
page = context.pages[0]
```

Replace with:

```python
if use_cloud_mode:
    # Cloud: headless Chromium + credential login
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    from app.scraper.auth import login_with_credentials
    logged_in = await login_with_credentials(page)
    if not logged_in:
        raise Exception("Cloud login failed - check GEOSURVAI_EMAIL/PASSWORD secrets")
    logger.info("Cloud mode: logged in with credentials")
else:
    # Local: use Chrome profile (existing code)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=chrome_profile_path, ...
    )
    page = context.pages[0]
    logger.info(f"Using Chrome profile: {chrome_profile_path}")
```

**IMPORTANT:** You also need to adjust the CSS selectors in `auth.py` to match the actual geosurvai.com login form. Open the login page, press F12, and inspect the username/password input fields.

---

## Step 6: Push to Hugging Face

HF Spaces builds from a Git repo. You'll push your code to their Git remote:

```bash
cd C:\Users\Asus\my-multimodal-rag\geosurvai\geosurvai-rag\geosurvai-rag

# Install Git LFS (needed for large files like .duckdb)
git lfs install
git lfs track "*.duckdb"
git add .gitattributes

# Add the HF Spaces remote
git remote add hf https://huggingface.co/spaces/VtoWantToLearn/geosurvai-rag

# Stage all changes (new files + database)
git add .
git commit -m "deploy: add Docker + cloud auth for HF Spaces"

# Push to Hugging Face (this triggers the build)
git push hf main
```

When prompted for credentials:
- **Username:** your HF username
- **Password:** go to https://huggingface.co/settings/tokens → create a **Write** token → use that as password

---

## Step 7: Monitor the Build

1. Go to your Space: `https://huggingface.co/spaces/VtoWantToLearn/geosurvai-rag`
2. Click the **"Building"** status badge to see logs
3. The Docker build takes ~5-10 minutes the first time
4. Once it shows **"Running"**, your app is live!

---

## Step 8: Share the Link

Send your supervisor:

```
https://VtoWantToLearn-geosurvai-rag.hf.space
```

Done. Clean URL, works everywhere, always on.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Build fails on Playwright | Check Dockerfile has all system deps listed |
| "No module named X" | Add the missing package to `requirements.txt` and push again |
| Scraper login fails | Check auth.py selectors — screenshot saved to `screenshots/login_debug.png` |
| Ollama connection timeout | Verify from your Ollama server that port 5162 accepts external connections |
| DuckDB file too large for Git | Use `git lfs` (Step 6 includes this) |
| Space sleeps after 48h inactivity | Free Spaces may sleep — just visit the URL to wake it (takes ~30s) |
| Need to update code | Just `git push hf main` again — auto-rebuilds |

---

## Updating the App

After making changes locally:

```bash
git add .
git commit -m "update: description of changes"
git push origin main    # push to GitHub
git push hf main        # push to HF Spaces (triggers rebuild)
```

---

## Architecture on HF Spaces

```
┌─── Hugging Face Spaces (Docker) ──────────────┐
│                                                 │
│  FastAPI (:7860) ← supervisor opens this link   │
│     ├── Chat UI (static HTML)                   │
│     ├── Query Router                            │
│     │   ├── Text-to-SQL → Gemini API (external) │
│     │   ├── Precomputed Cache (local JSON)      │
│     │   └── Semantic → ChromaDB (local)         │
│     ├── DuckDB (local file)                     │
│     └── Auto-Sync Scheduler                     │
│         └── Playwright (headless Chromium)       │
│             └── Login via credentials            │
│                                                  │
│  Ollama ← 117.54.250.177:5162 (your server)    │
└─────────────────────────────────────────────────┘
```
