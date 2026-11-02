FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANGA_ENV=production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY anga ./anga
COPY run.py .

# Run as an unprivileged user that owns only the data directory.
RUN useradd --create-home --uid 1000 anga \
    && mkdir -p /app/instance \
    && chown -R anga:anga /app/instance
USER anga

VOLUME ["/app/instance"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/about', timeout=4)"

# Seeding first means workers start against a ready database and a shared secret key.
CMD ["sh", "-c", "flask --app anga seed && exec gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 4 --access-logfile - 'anga:create_app()'"]
