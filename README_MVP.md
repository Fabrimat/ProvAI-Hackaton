# PROV-AI MVP: Quick Reference

## Run locally

```bash
pip install -r requirements.txt
python -m app.ingest
streamlit run app/ui/streamlit_app.py
```

## Run locally with Docker

```bash
docker compose up -d --build
```

Serves on http://localhost:8501, DB persisted in `./data`.

## Deploy to vidar

```bash
./deploy/deploy.sh          # sync + rebuild + start
./deploy/deploy.sh --logs   # same, then tail remote logs
```

**App URL:** http://vidar:8501
