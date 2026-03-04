# GeoSurvAI Cloud Deployment Guide

## Strategy Overview

Deploy GeoSurvAI on Oracle Cloud Free Tier (always-free VM). Your supervisor gets a clean public URL like `http://129.xxx.xxx.xxx:8000` — no setup, works on any browser.

**What moves to cloud:**
- FastAPI app + DuckDB + chat UI
- Playwright scraper (headless, with password login instead of Chrome profile)
- Gemini API (works anywhere)
- Ollama stays at 117.54.250.177 (already public)

**Cost: $0** — Oracle Free Tier is genuinely always-free, not a trial.

---

## Step 1: Create Oracle Cloud Account

1. Go to: https://www.oracle.com/cloud/free/
2. Click "Start for Free"
3. Sign up with email, set your **Home Region** to the closest one (e.g., Singapore or Tokyo)
4. You'll need a credit card for verification — **it will NOT be charged** on the free tier
5. Wait for account activation (usually 5-15 minutes)

---

## Step 2: Create the VM

1. Go to Oracle Cloud Console → **Compute → Instances → Create Instance**

2. Configure:
   - **Name:** `geosurvai`
   - **Image:** Ubuntu 22.04 (Canonical)
   - **Shape:** Click "Change Shape" → **Ampere** (ARM) → **VM.Standard.A1.Flex**
     - OCPU: **2** (free tier allows up to 4)
     - Memory: **12 GB** (free tier allows up to 24)
   - **Networking:** Accept defaults (creates VCN + public subnet)
   - **Add SSH keys:** Click "Generate a key pair" → **Download both keys** (save them safely!)

3. Click **Create** — wait 2-3 minutes for the instance to start

4. Copy the **Public IP Address** from the instance details page

---

## Step 3: Open Port 8000

By default Oracle blocks all incoming traffic. You need to open port 8000:

1. Go to **Networking → Virtual Cloud Networks** → click your VCN
2. Click your **Public Subnet** → click the **Security List**
3. Click **Add Ingress Rules**:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port Range: `8000`
   - Description: `GeoSurvAI`
4. Click **Add**

---

## Step 4: Connect to the VM

From your local terminal (Git Bash on Windows, or PowerShell):

```bash
# Fix key permissions (Git Bash / WSL)
chmod 400 ~/Downloads/ssh-key-*.key

# Connect
ssh -i ~/Downloads/ssh-key-*.key ubuntu@YOUR_PUBLIC_IP
```

For PowerShell:
```powershell
ssh -i $HOME\Downloads\ssh-key-YYYY-MM-DD.key ubuntu@YOUR_PUBLIC_IP
```

---

## Step 5: Set Up the Environment

Run these commands on the VM:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11 + pip
sudo apt install -y python3.11 python3.11-venv python3-pip git

# Install Playwright system dependencies
sudo apt install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libx11-xcb1

# Also open port 8000 in the OS firewall
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

---

## Step 6: Deploy the App

```bash
# Clone repo
git clone https://github.com/patrisiusvito/geosurvai-rag.git
cd geosurvai-rag

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

---

## Step 7: Configure Environment Variables

```bash
# Create .env file
cat > .env << 'EOF'
GEMINI_API_KEY=your_gemini_api_key_here
OLLAMA_HOST=http://117.54.250.177:5162

# Login credentials for the scraper (replaces Chrome profile)
GEOSURVAI_USERNAME=your_username_here
GEOSURVAI_PASSWORD=your_password_here
GEOSURVAI_LOGIN_URL=https://geosurvai.com/login
EOF

# Protect the file
chmod 600 .env
```

---

## Step 8: Upload Your Database

From your **local machine** (Anaconda Prompt), upload the existing DuckDB:

```bash
scp -i ~/Downloads/ssh-key-*.key ^
    C:\Users\Asus\my-multimodal-rag\geosurvai\geosurvai-rag\geosurvai-rag\db\geosurvai.duckdb ^
    ubuntu@YOUR_PUBLIC_IP:~/geosurvai-rag/db/
```

Also upload the precomputed cache:
```bash
scp -i ~/Downloads/ssh-key-*.key ^
    C:\Users\Asus\my-multimodal-rag\geosurvai\geosurvai-rag\geosurvai-rag\data\cache\precomputed.json ^
    ubuntu@YOUR_PUBLIC_IP:~/geosurvai-rag/data/cache/
```

---

## Step 9: Modify the Scraper for Cloud

The scraper needs two changes for cloud deployment:

### 9a. Add auth.py

Copy the `auth.py` file (provided separately) to `app/scraper/auth.py`.

### 9b. Update browser.py

In `app/scraper/browser.py`, replace the Chrome profile launch with headless Chromium + login.

Find the section that does something like:
```python
browser = await playwright.chromium.launch_persistent_context(
    user_data_dir=chrome_profile_path, ...
)
```

Replace with:
```python
import os

# Cloud mode: headless Chromium + credential login
use_cloud_mode = os.getenv("GEOSURVAI_USERNAME", "") != ""

if use_cloud_mode:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Login with credentials
    from app.scraper.auth import login_with_credentials
    logged_in = await login_with_credentials(page)
    if not logged_in:
        raise Exception("Cloud login failed - check credentials")
    logger.info("Cloud mode: logged in via credentials")
else:
    # Local mode: use Chrome profile (existing behavior)
    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=chrome_profile_path, ...
    )
```

**Important:** You'll need to adjust the CSS selectors in `auth.py` to match the actual login form on geosurvai.com. Open the login page in Chrome DevTools (F12) and inspect the username/password fields to find the correct selectors.

---

## Step 10: Run the App

```bash
cd ~/geosurvai-rag
source venv/bin/activate

# Load environment variables
export $(cat .env | xargs)

# Create required directories
mkdir -p db data/cache screenshots

# Test run (foreground)
python app/main.py
```

Visit: **http://YOUR_PUBLIC_IP:8000**

If it works, set it up to run permanently:

```bash
# Run in background with auto-restart
sudo tee /etc/systemd/system/geosurvai.service << 'EOF'
[Unit]
Description=GeoSurvAI RAG
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/geosurvai-rag
EnvironmentFile=/home/ubuntu/geosurvai-rag/.env
ExecStart=/home/ubuntu/geosurvai-rag/venv/bin/python app/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable geosurvai
sudo systemctl start geosurvai

# Check status
sudo systemctl status geosurvai

# View logs
sudo journalctl -u geosurvai -f
```

---

## Step 11: Share the Link

Send your supervisor:

```
http://YOUR_PUBLIC_IP:8000
```

That's it — a clean link that opens the chat UI in any browser.

---

## Optional: Custom Domain (Nice URL)

If you want a clean URL like `demo.geosurvai.com` instead of an IP address:

1. Get a free domain from https://freedns.afraid.org or use a domain you own
2. Create an A record pointing to your Oracle VM's IP
3. Install Caddy for automatic HTTPS:

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile << 'EOF'
demo.geosurvai.com {
    reverse_proxy localhost:8000
}
EOF
sudo systemctl restart caddy
```

---

## Maintenance Commands

```bash
# View logs
sudo journalctl -u geosurvai -f

# Restart after code changes
sudo systemctl restart geosurvai

# Pull latest code from GitHub
cd ~/geosurvai-rag && git pull && sudo systemctl restart geosurvai

# Trigger manual sync
curl -X POST http://localhost:8000/api/sync

# Check health
curl http://localhost:8000/health
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 8000 not accessible | Check both Oracle Security List AND iptables |
| Scraper login fails | Check selectors in auth.py — inspect the login form with DevTools |
| Ollama connection timeout | Verify 117.54.250.177:5162 is reachable from VM: `curl http://117.54.250.177:5162` |
| DuckDB read-only error | Ensure only one process accesses the .duckdb file |
| Out of memory | Reduce VM OCPU to 1, increase memory to 16GB |
