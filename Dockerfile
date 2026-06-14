FROM python:3.11-slim

# Kerakli system paketlar
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Ishchi papka
WORKDIR /app

# Dependency fayllari
COPY requirements.txt .

# Python kutubxonalarini o'rnatish
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Loyiha fayllari
COPY . .

# Data papkasi
RUN mkdir -p data uploads

# Port (aiohttp API uchun)
EXPOSE 8000

# Environment
ENV PYTHONUNBUFFERED=1

# Botni ishga tushirish
CMD ["python", "-m", "bot"]
