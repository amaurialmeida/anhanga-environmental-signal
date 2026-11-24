# Brazil Environmental Signal

**Environmental Intelligence Router — Brazil**

A Streamlit portfolio project inspired by the visual language and modular concept of Amauri Almeida's Environmental Signal Router. This independent app focuses on Brazilian environmental and severe-weather signals.

## V1 features

- Dark, green Signal Router-inspired interface.
- Monitored municipality map: Tupanciretã (RS), Timóteo (MG), Ipatinga (MG), Chapecó (SC), Xanxerê (SC).
- GDELT-based media discovery for severe storms, tornadoes, damaging winds, flooding, hail and ENSO.
- Satellite desk linking to INPE/CPTEC official portals.
- Source and methodology panel distinguishing news mentions from official observations and confirmed events.

> **Important:** News results are not official event confirmations. The map initially displays monitored municipalities, not active incidents. This version does not detect tornadoes or supercells and is not an emergency alert service.

## Run locally

```bash
git clone https://github.com/amaurialmeida/brazil-environmental-signal.git
cd brazil-environmental-signal
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a new public GitHub repository named `brazil-environmental-signal`.
2. Upload `app.py`, `requirements.txt`, `README.md`, and `.streamlit/config.toml`.
3. Open https://share.streamlit.io/
4. Select **New app**, choose the repository, branch `main`, and file `app.py`.
5. Deploy. No API key is required for this V1.

## Data sources and next integrations

- [INMET alerts](https://alertas2.inmet.gov.br/)
- [CEMADEN](https://www.gov.br/cemaden/pt-br)
- [SIMGE](https://simge.mg.gov.br/)
- [ANA HidroWeb](https://www.snirh.gov.br/hidroweb/)
- [INPE BIG](https://data.inpe.br/)
- [INPE/CPTEC DSAT — GOES-19](https://www.cptec.inpe.br/dsat/)
- [GDELT DOC API](https://api.gdeltproject.org/api/v2/doc/doc)

## Roadmap

- V1: media discovery, monitored locations, satellite source directory.
- V2: official alert ingestion, INMET station observations, rainfall and river-level datasets.
- V3: satellite imagery layers and time-aware geospatial visualisation, subject to provider terms.
- V4: event deduplication, municipality extraction, evidence status and historical analytics.

## Methodology principles

1. Preserve source, timestamp and original URL for every record.
2. Separate official warnings, observations, media reports and derived analysis.
3. Never label a tornado, supercell or microburst as confirmed based only on a headline.
4. Show data freshness and report outages instead of silently presenting stale information.
5. Respect licensing, attribution and reuse terms for satellite imagery and third-party products.

---
Portfolio project by **Amauri Almeida**.
