# Use the official Python 3.12 image as a base
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright and other tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    librandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (chrome is used by the app for better stealth)
RUN playwright install chrome
RUN playwright install-deps chrome

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p docs logs issues tests data tmp src/output

# Initialize database
# RUN python scripts/init_db.py (Optional: handle via entrypoint or manual command)

# Expose API port
EXPOSE 8000

# Default command: Start API (Worker runs as a background thread inside)
CMD ["python3", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
