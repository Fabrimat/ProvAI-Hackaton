# PROV-AI

PROV-AI is a prototype dashboard for the Municipality of Schoten. It helps municipal officers review local business data, identify outdated or conflicting information, and prioritize businesses that need verification.

The application is built with Python, Streamlit, and SQLite. It uses a dataset of 1,000 local businesses and combines information from several mock and public data sources.

## Main features

- Business overview and interactive map
- Priority-based verification queue
- Detailed business records
- Evidence and reliability scoring
- Change and data-freshness tracking
- Dutch and English interface

## Run locally

Install the dependencies:

```bash
pip install -r requirements.txt
```

Import the source data:

```bash
python -m app.ingest
```

Start the application:

```bash
streamlit run app/ui/streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## Run with Docker

```bash
docker compose up -d --build
```

The application will be available at [http://localhost:8501](http://localhost:8501). The SQLite database is stored in the `data` directory.

## Run the tests

```bash
python -m unittest discover tests
```
