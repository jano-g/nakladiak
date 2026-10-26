# Playwright image: Chromium is pre-installed for the ZSD diportal connector (the portal sits
# behind F5 bot protection + reCAPTCHA, plain HTTP clients are blocked). The app itself is a
# plain FastAPI process; the browser only runs inside the connector subprocess once a day.
FROM mcr.microsoft.com/playwright/python:v1.64.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TZ=Europe/Bratislava

RUN groupadd -r nakladiak && useradd -r -g nakladiak -d /srv -s /usr/sbin/nologin nakladiak \
 && mkdir -p /data && chown nakladiak:nakladiak /data

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# „O appke“: čo je nové + kedy bolo nasadené (čas buildu = čas deployu)
COPY changelog.md ./
RUN date -u +%Y-%m-%dT%H:%M:%SZ > /srv/BUILT_AT

USER nakladiak
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

# One process on purpose: SQLite + in-process scheduler thread. nginx terminates TLS.
# No --proxy-headers: with --forwarded-allow-ips "*" uvicorn would put the client-controlled
# first X-Forwarded-For hop into request.client; app/auth.py:client_ip reads the LAST hop itself.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
