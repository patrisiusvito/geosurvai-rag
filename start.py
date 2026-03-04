"""
Cloud startup wrapper for Hugging Face Spaces.
Maps environment variables and starts uvicorn.

HF Spaces may inject secrets as:
  1. Environment variables (normal case)
  2. Files under /run/secrets/ (Docker Spaces)
This script checks both.
"""
import os
import subprocess
import sys
from pathlib import Path


def load_secrets():
    """Load secrets from /run/secrets/ files into env vars if not already set."""
    secrets_dir = Path("/run/secrets")

    # Debug: show what's available
    print("===== Loading Secrets =====")

    if secrets_dir.exists():
        print(f"  /run/secrets/ exists, contents: {list(secrets_dir.iterdir())}")
        for secret_file in secrets_dir.iterdir():
            if secret_file.is_file():
                var_name = secret_file.name
                if not os.getenv(var_name):
                    value = secret_file.read_text().strip()
                    os.environ[var_name] = value
                    print(f"  Loaded {var_name} from /run/secrets/")
    else:
        print("  /run/secrets/ does not exist")

    # Map GEMINI_API_KEY → GOOGLE_API_KEY (google-genai SDK expects GOOGLE_API_KEY)
    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

    # Also check GOOGLE_API_KEY → GEMINI_API_KEY (in case user set GOOGLE_API_KEY directly)
    if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

    # Status report
    print("===== Secret Status =====")
    secret_vars = ["GOOGLE_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST",
                   "GEOSURVAI_EMAIL", "GEOSURVAI_PASSWORD", "GEOSURVAI_LOGIN_URL"]
    for var in secret_vars:
        status = "SET" if os.getenv(var) else "MISSING"
        print(f"  {var}: {status}")

    # Debug: dump ALL env var names (not values) to see what HF provides
    print("===== All Environment Variables (names only) =====")
    for key in sorted(os.environ.keys()):
        print(f"  {key}")
    print("=" * 40)


def main():
    port = os.getenv("PORT", "7860")
    os.environ["APP_PORT"] = port

    load_secrets()

    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--workers", "1",
    ])


if __name__ == "__main__":
    main()
