"""
Cloud startup wrapper for Hugging Face Spaces.
Maps environment variables and starts uvicorn.
"""
import os
import subprocess
import sys


def main():
    port = os.getenv("PORT", "7860")
    os.environ["APP_PORT"] = port

    # Map GEMINI_API_KEY → GOOGLE_API_KEY (google-genai SDK expects GOOGLE_API_KEY)
    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

    # Debug: print which env vars are set (without values)
    secret_vars = ["GOOGLE_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST",
                   "GEOSURVAI_EMAIL", "GEOSURVAI_PASSWORD", "GEOSURVAI_LOGIN_URL"]
    for var in secret_vars:
        status = "SET" if os.getenv(var) else "MISSING"
        print(f"  {var}: {status}")

    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--workers", "1",
    ])


if __name__ == "__main__":
    main()
