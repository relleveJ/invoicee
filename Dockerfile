FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for Pillow, WeasyPrint, and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    libssl-dev \
    pkg-config \
    curl \
    ca-certificates \
    fonts-liberation \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    shared-mime-info \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (leverages Docker layer cache)
COPY requirements.txt /app/
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Create a volume location for collectstatic output
RUN mkdir -p /vol/static

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
