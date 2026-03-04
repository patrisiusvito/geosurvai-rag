FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV ANONYMIZED_TELEMETRY=False
ENV CHROMA_IS_PERSISTENT=TRUE
ENV ORT_DISABLE_ALL=1

# Store Playwright browsers in a shared location (not user-specific cache)
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Install system dependencies for Playwright + DuckDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libx11-xcb1 \
    libdbus-1-3 libatspi2.0-0 libx11-6 libxcb1 \
    libxext6 libxfixes3 wget curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 appuser

WORKDIR /home/appuser/app

# Install Python deps in stages to reduce peak memory
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] duckdb pandas openpyxl \
    google-genai httpx ollama loguru apscheduler

# ChromaDB (heavier, install separately)
RUN pip install --no-cache-dir chromadb && \
    rm -rf /root/.cache /tmp/* /home/appuser/.cache && \
    pip uninstall -y onnxruntime 2>/dev/null || true

# Playwright: install package + browsers in shared path
RUN pip install --no-cache-dir playwright && \
    mkdir -p $PLAYWRIGHT_BROWSERS_PATH && \
    playwright install chromium --with-deps && \
    chmod -R 755 $PLAYWRIGHT_BROWSERS_PATH && \
    rm -rf /root/.cache /tmp/*

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p db data/cache screenshots data/raw downloads \
    && chown -R appuser:appuser /home/appuser/app

USER appuser

ENV PORT=7860
EXPOSE 7860

COPY start.py .
CMD ["python", "start.py"]
