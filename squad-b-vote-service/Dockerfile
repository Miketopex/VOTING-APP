# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Unbuffered so logs reach Docker immediately; no .pyc files to own or stale.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached and only rebuilt when requirements.txt
# changes, so an application edit does not reinstall psycopg2 every time.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY wsgi.py gunicorn.conf.py ./

# Run as a user that is not root. If the app is ever compromised, the blast radius
# is a process that cannot write to its own code.
RUN useradd --system --create-home --home-dir /home/vote vote \
    && mkdir -p /app/instance \
    && chown -R vote:vote /app
USER vote

EXPOSE 5000

# /health/ready is 503 until Postgres answers, so Docker reports this container
# healthy only once it can actually serve a request — which is what nginx waits on.
# No curl in the slim image, so the check is a one-liner of Python.
HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health/ready', timeout=4).status == 200 else 1)"

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
