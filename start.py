"""
Cloud startup wrapper for Hugging Face Spaces.
Reads PORT from environment (HF Spaces uses 7860).
Place at project root: start.py
"""
import os
import subprocess
import sys


def main():
    port = os.getenv("PORT", "7860")

    # Patch: ensure the app binds to the correct port
    os.environ["APP_PORT"] = port

    # Start uvicorn directly
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--workers", "1",
    ])


if __name__ == "__main__":
    main()
