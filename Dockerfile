# PROV-AI Challenge 1 MVP: Streamlit app image
#
# Data-baking strategy: we run `python -m app.ingest` as a BUILD step so the
# image itself ships pre-seeded with data/provai.db already populated from
# the CSV and GeoJSON. However, docker-compose.yml bind-mounts ./data over
# /app/data for persistence across rebuilds, and bind mounts do NOT inherit
# the image's pre-existing directory content (unlike named volumes), so on
# a fresh host the mount would otherwise shadow the baked-in DB with an
# empty directory. CMD below works around this: it only re-runs ingestion if
# /app/data/provai.db is missing from the mounted volume (i.e. first boot on
# a fresh host), then starts Streamlit. This is safe because `init_db()`
# uses `CREATE TABLE IF NOT EXISTS`, and it means later rebuilds never wipe
# accumulated evidence/scores/status rows already sitting in ./data.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app/ ./app/

# Real data files read by ingestion at build time / runtime
COPY schoten-kbo-1000-2026-09-07.csv .
COPY schoten-kbo-1000-2026-09-07.geojson .
COPY source-metadata.json .

# Bake the SQLite DB in at build time so the image starts pre-seeded.
RUN python -m app.ingest

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["sh", "-c", "test -f /app/data/provai.db || python -m app.ingest; streamlit run app/ui/streamlit_app.py --server.port=8501 --server.address=0.0.0.0"]
