FROM python:3.12-slim

WORKDIR /app

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    tesseract-ocr-uzb \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Project files
COPY . .

# Required directories
RUN mkdir -p uploads logs data static

EXPOSE 8080
EXPOSE 8443

# Telegram bot
CMD ["python", "-m", "bot"]
