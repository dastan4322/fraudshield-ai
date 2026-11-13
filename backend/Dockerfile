FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt constraints.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt && useradd --create-home app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --chown=app:app app ./app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --start-period=45s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["sh","-c","alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
