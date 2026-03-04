FROM python:3.11-slim

# Install system dependencies for Playwright + DuckDB
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libx11-xcb1 \
    libdbus-1-3 libatspi2.0-0 libx11-6 libxcb1 \
    libxext6 libxfixes3 wget curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /home/appuser/app

# Copy requirements first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium
RUN pip install playwright && playwright install chromium

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p db data/cache screenshots data/raw \
    && chown -R appuser:appuser /home/appuser/app

# Switch to non-root user
USER appuser

# HF Spaces expects port 7860
ENV PORT=7860
EXPOSE 7860

# Copy startup wrapper
COPY start.py .

# Start the app (reads PORT env, defaults to 7860 for HF Spaces)
CMD ["python", "start.py"]
