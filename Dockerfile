# -------------------------
# STAGE 1: Setup Python (v 3.11)
# -------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
# -------------------------
# STAGE 2: Install dependencies
# -------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    python3-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Upgrade pip tools first
RUN pip install --upgrade pip setuptools wheel

RUN pip install -r requirements.txt


COPY . .

# Collect static files (optional for prod)
# RUN python manage.py collectstatic --noinput

# Run database migrations (if applicable)
RUN python manage.py migrate

EXPOSE 8000

# Run production build with guinicorn
# CMD ["gunicorn", "--bind", "0.0.0.0:8000", "bonaso_data_server.wsgi:application"]

CMD ["sh", "-c", "gunicorn bonaso_data_server.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]