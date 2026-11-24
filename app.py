"""
BRAZIL ENVIRONMENTAL SIGNAL
Environmental intelligence dashboard — Brazil
Author: Amauri Almeida

V1 starter: GDELT news discovery + monitored locations + official satellite portal links.
News mentions are NOT official event confirmations.
"""

from datetime import datetime, timezone
from urllib.parse import quote
import html

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Brazil Environmental Signal",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Visual identity: dark, green signal-router language ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
:root { --bg:#07110e; --panel:#0c1b16; --line:rgba(111,180,139,.20);
        --green:#65d99a; --muted:#91a69a; --white:#e8f2ec; }
html, body, [class*="css"] { font-family:'Manrope',sans-serif; }
.stApp { background: radial-gradient(ellipse at 15% 0%, #10271d 0%, #07110e 48%, #050b09 100%); color:var(--white); }
[data-testid="stSidebar"] { background:#08150f; border-right:1px solid var(--line); }
.block-container { padding-top:1.6rem; max-width:1500px; }
h1,h2,h3 { letter-spacing:-.04em; }
.signal-kicker { font:500 10px 'DM Mono',monospace; color:var(--green); letter-spacing:.19em; }
.signal-title { font-size:clamp(27px,4vw,48px); line-height:1.05; font-weight:800; letter-spacing:-.055em; }
.signal-sub { color:var(--muted); font-size:13px; margin-top:7px; }
.panel { background:linear-gradient(145deg,rgba(17,39,29,.94),rgba(8,22,16,.96));
         border:1px solid var(--line); border-radius:15px; padding:17px 18px; min-height:112px; }
.metric-label { color:#9ab1a2; font:500 10px 'DM Mono',monospace; letter-spacing:.13em; text-transform:uppercase; }
.metric-value { color:#effaf2; font-size:30px; font-weight:800; margin-top:8px; }
.metric-note { color:#91a69a; font-size:11px; margin-top:3px; }
.section-label { color:var(--green); font:500 10px 'DM Mono',monospace; letter-spacing:.16em; }
.event-card { border:1px solid var(--line); background:rgba(12,27,22,.82); border-radius:12px; padding:14px 16px; margin:8px 0; }
.event-title { font-weight:700; color:#eaf5ed; font-size:14px; }
.event-meta { font:11px 'DM Mono',monospace; color:#8da99a; margin-top:5px; }
a { color:#78e5a8 !important; }
.stButton>button { border:1px solid rgba(101,217,154,.35); border-radius:9px; background:#10291d; color:#dff8e8; }
[data-testid="stMetric"] { background:rgba(12,27,22,.82); border:1px solid var(--line); padding:14px; border-radius:12px; }
[data-testid="stMetricLabel"] { color:#9ab1a2; }
hr { border-color:var(--line); }
footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

LOCATIONS = pd.DataFrame([
    {"city":"Tupanciretã","state":"RS","lat":-29.0833,"lon":-53.8333,"focus":"Severe storms"},
    {"city":"Timóteo","state":"MG","lat":-19.5811,"lon":-42.6444,"focus":"Flooding / rainfall"},
    {"city":"Ipatinga","state":"MG","lat":-19.4683,"lon":-42.5367,"focus":"Flooding / rainfall"},
    {"city":"Chapecó","state":"SC","lat":-27.1000,"lon":-52.6152,"focus":"Severe wind"},
    {"city":"Xanxerê","state":"SC","lat":-26.8753,"lon":-52.4042,"focus":"Severe storms"},
])

TOPICS = {
    "Severe storms": '"supercélula" OR "tempestade severa" OR "temporal"',
    "Tornado": 'tornado OR "funil de vento"',
    "Severe wind": '"vendaval" OR "microexplosão" OR "rajadas de vento"',
    "Flooding": 'enchente OR inundação OR alagamento OR enxurrada',
    "Hail": 'granizo OR "chuva de granizo"',
    "El Niño / La Niña": '"El Niño" OR "La Niña" OR ENSO',
}

def fetch_gdelt_news(query: str, max_records: int = 30) -> pd.DataFrame:
    """Search GDELT DOC API. Results are media mentions, not verified events."""
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": f"({query}) Brazil",
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "sort": "DateDesc",
        "timespan": "7d",
    }
    try:
        response = requests.get(url, params=params, timeout=18,
                                headers={"User-Agent":"BrazilEnvironmentalSignal/1.0"})
        response.raise_for_status()
        payload = response.json()
        rows = []
        for item in payload.get("articles", []):
            rows.append({
                "title": item.get("title", "Untitled"),
                "source": item.get("domain", "Unknown source"),
                "published": item.get("seendate", ""),
                "url": item.get("url", ""),
                "language": item.get("language", ""),
            })
        return pd.DataFrame(rows)
    except Exception as exc:
        st.session_state["news_error"] = str(exc)
        return pd.DataFrame(columns=["title","source","published","url","language"])

def metric(label, value, note):
    st.markdown(f"""<div class="panel">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{value}</div>
      <div class="metric-note">{note}</div>
    </div>""", unsafe_allow_html=True)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown('<div class="signal-kicker">ENVIRONMENTAL INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown("## 🛰️ BRAZIL SIGNAL")
    language = st.selectbox("LANGUAGE / IDIOMA", ["English","Português","Español"], index=1)
    st.markdown("---")
    section = st.radio("SIGNAL ROUTER", [
        "Overview", "Event Radar", "Storm Intelligence",
        "Flood Monitor", "Climate Signal", "Satellite Desk", "Sources & Method"
    ], label_visibility="visible")
    st.markdown("---")
    st.caption("V1.0 • BRAZIL")
    st.caption("News discovery is not an official warning service.")

title_map = {
    "Overview":"BRAZIL ENVIRONMENTAL SIGNAL",
    "Event Radar":"EVENT RADAR",
    "Storm Intelligence":"STORM INTELLIGENCE",
    "Flood Monitor":"FLOOD MONITOR",
    "Climate Signal":"CLIMATE SIGNAL",
    "Satellite Desk":"SATELLITE DESK",
    "Sources & Method":"SOURCES & METHODOLOGY",
}
subtitle_map = {
    "Overview":"Monitoring environmental signals across Brazilian territory.",
    "Event Radar":"Geospatial view of monitored locations and collected reports.",
    "Storm Intelligence":"Severe convection, tornado reports, hail and damaging winds.",
    "Flood Monitor":"Rainfall, flooding reports and hydrological risk signals.",
    "Climate Signal":"Large-scale climate patterns, including ENSO.",
    "Satellite Desk":"Earth observation products relevant to Brazil.",
    "Sources & Method":"Data provenance, limitations and responsible interpretation.",
}
st.markdown('<div class="signal-kicker">BRAZIL • SOUTH AMERICA • ENVIRONMENTAL MONITORING</div>', unsafe_allow_html=True)
st.markdown(f'<div class="signal-title">{title_map[section]}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="signal-sub">{subtitle_map[section]}</div>', unsafe_allow_html=True)
st.markdown("")

# ---------- Search controls ----------
with st.expander("SIGNAL FILTERS", expanded=(section in ["Overview","Event Radar"])):
    c1, c2 = st.columns([1,2])
    topic_label = c1.selectbox("EVENT CATEGORY", list(TOPICS.keys()), index=0)
    city_filter = c2.multiselect("MONITORED LOCATIONS", LOCATIONS["city"].tolist(),
                                 default=LOCATIONS["city"].tolist())
    refresh = st.button("↻  COLLECT LATEST NEWS", use_container_width=False)

if refresh or "news_df" not in st.session_state or st.session_state.get("news_topic") != topic_label:
    with st.spinner("Querying recent media mentions…"):
        st.session_state["news_df"] = fetch_gdelt_news(TOPICS[topic_label])
        st.session_state["news_topic"] = topic_label
        st.session_state["last_fetch"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

news = st.session_state.get("news_df", pd.DataFrame())
visible_locations = LOCATIONS[LOCATIONS["city"].isin(city_filter)] if city_filter else LOCATIONS.iloc[0:0]

if section == "Overview":
    a,b,c,d = st.columns(4)
    with a: metric("MONITORED LOCATIONS", len(visible_locations), "Brazilian municipalities")
    with b: metric("MEDIA MENTIONS", len(news), "GDELT • last 7 days")
    with c: metric("EVENT CATEGORIES", len(TOPICS), "Search taxonomy")
    with d: metric("LAST COLLECTION", "LIVE" if st.session_state.get("last_fetch") else "—",
                   st.session_state.get("last_fetch","Not collected"))
    st.markdown("")
    left, right = st.columns([1.35,1])
    with left:
        st.markdown('<div class="section-label">01 / GEOSPATIAL SIGNAL</div>', unsafe_allow_html=True)
        m = folium.Map(location=[-15.5,-52.5], zoom_start=4, tiles="CartoDB dark_matter")
        for _, r in visible_locations.iterrows():
            folium.CircleMarker(
                [r.lat,r.lon], radius=7, color="#65d99a", fill=True,
                fill_color="#65d99a", fill_opacity=.85,
                tooltip=f"{r.city} / {r.state}",
                popup=f"<b>{r.city} - {r.state}</b><br>{r.focus}<br>Monitored location — not an active incident"
            ).add_to(m)
        st_folium(m, height=430, use_container_width=True, returned_objects=[])
        st.caption("Markers show monitored municipalities, not confirmed active events.")
    with right:
        st.markdown('<div class="section-label">02 / LATEST MEDIA SIGNALS</div>', unsafe_allow_html=True)
        if news.empty:
            st.info("No media mentions returned for this query. Try another category or collect again.")
        else:
            for _, r in news.head(8).iterrows():
                safe_title = html.escape(str(r.title))
                safe_source = html.escape(str(r.source))
                st.markdown(f"""<div class="event-card">
                  <div class="event-title">{safe_title}</div>
                  <div class="event-meta">{safe_source} · {html.escape(str(r.published))}</div>
                </div>""", unsafe_allow_html=True)
                if r.url:
                    st.markdown(f"[OPEN SOURCE ↗]({r.url})")
    st.markdown("---")
    st.markdown('<div class="section-label">03 / MONITORED LOCATIONS</div>', unsafe_allow_html=True)
    st.dataframe(visible_locations[["city","state","focus"]], use_container_width=True, hide_index=True)

elif section == "Event Radar":
    m = folium.Map(location=[-15.5,-52.5], zoom_start=4, tiles="CartoDB dark_matter")
    for _, r in visible_locations.iterrows():
        folium.Marker([r.lat,r.lon], tooltip=f"{r.city}/{r.state}",
                      popup=f"{r.city} - {r.state}<br>{r.focus}",
                      icon=folium.Icon(color="green", icon="info-sign")).add_to(m)
    st_folium(m, height=620, use_container_width=True, returned_objects=[])
    st.caption("This first version maps monitored places. Event coordinates will be added only when a source provides a verifiable location.")

elif section in ["Storm Intelligence","Flood Monitor","Climate Signal"]:
    if section == "Storm Intelligence":
        selected = ["Severe storms","Tornado","Severe wind","Hail"]
    elif section == "Flood Monitor":
        selected = ["Flooding"]
    else:
        selected = ["El Niño / La Niña"]
    st.markdown('<div class="section-label">MEDIA DISCOVERY • NOT OFFICIAL CONFIRMATION</div>', unsafe_allow_html=True)
    if section == "Climate Signal":
        st.info("ENSO is a climate-scale phenomenon. This panel discovers reporting; it does not calculate an official Niño 3.4 index or issue a seasonal forecast.")
    for topic in selected:
        with st.expander(topic, expanded=(topic == selected[0])):
            df = fetch_gdelt_news(TOPICS[topic])
            if df.empty:
                st.write("No results returned.")
            else:
                for _, r in df.head(15).iterrows():
                    st.markdown(f"**{r.title}**  \n<small>{r.source} · {r.published}</small>", unsafe_allow_html=True)
                    if r.url: st.markdown(f"[Read original report]({r.url})")
                    st.markdown("---")

elif section == "Satellite Desk":
    st.markdown('<div class="section-label">EARTH OBSERVATION / OFFICIAL PORTALS</div>', unsafe_allow_html=True)
    st.write("Use the official portals below for satellite imagery and products. This V1 links to source interfaces; it does not redistribute imagery.")
    sat_cols = st.columns(2)
    cards = [
        ("INPE / DSAT — GOES-19","Interactive meteorological satellite imagery and environmental products.","https://www.cptec.inpe.br/dsat/"),
        ("INPE — BIG / Satellite catalogue","CBERS-4, CBERS-4A, Amazonia-1 and geospatial data catalogue.","https://data.inpe.br/"),
        ("CPTEC / DISSM","Satellite products including cloud classification, atmospheric electricity and precipitation.","https://satelite.cptec.inpe.br/home/"),
        ("INPE — Queimadas","Near-real-time fire hotspots and historical fire datasets.","https://terrabrasilis.dpi.inpe.br/queimadas/portal/"),
    ]
    for i, (name, desc, url) in enumerate(cards):
        with sat_cols[i%2]:
            st.markdown(f"""<div class="panel">
              <div class="metric-label">SATELLITE SOURCE</div>
              <div class="event-title" style="margin-top:10px">{name}</div>
              <div class="metric-note" style="margin:8px 0 12px">{desc}</div>
              <a href="{url}" target="_blank">OPEN OFFICIAL SOURCE ↗</a>
            </div>""", unsafe_allow_html=True)
    st.warning("GOES-19 is operated by NOAA (United States), not a Brazilian satellite. CBERS and Amazonia-1 are relevant to Brazil's Earth-observation programme. Check each provider's reuse and attribution terms before embedding imagery.")

else:
    st.markdown("### Data source policy")
    st.write("The application separates media discovery, official alerts, observations and derived analysis. A news article is never automatically promoted to a confirmed tornado, supercell or flood record.")
    st.markdown("### Sources to integrate")
    sources = [
        ("INMET — meteorological warnings and station observations","https://alertas2.inmet.gov.br/"),
        ("CEMADEN — disaster monitoring","https://www.gov.br/cemaden/pt-br"),
        ("SIMGE — Minas Gerais meteorology and hydrology","https://simge.mg.gov.br/"),
        ("ANA — HidroWeb / hydrological data","https://www.snirh.gov.br/hidroweb/"),
        ("INPE BIG — satellite and geospatial data","https://data.inpe.br/"),
        ("INPE DSAT — GOES-19 imagery","https://www.cptec.inpe.br/dsat/"),
        ("GDELT DOC API — media discovery","https://api.gdeltproject.org/api/v2/doc/doc"),
    ]
    for name, url in sources:
        st.markdown(f"- [{name}]({url})")
    st.markdown("### Methodological labels")
    st.write("- **Official warning:** published by an authorised agency.")
    st.write("- **Official observation:** instrument or agency dataset.")
    st.write("- **Media report:** journalistic mention; requires verification.")
    st.write("- **Under investigation:** classification not yet settled.")
    st.write("- **Confirmed:** only when a competent source explicitly confirms the phenomenon.")
    st.markdown("### Limitations")
    st.write("GDELT coverage and article metadata vary. Place names may be ambiguous. This V1 does not geocode news articles into incident coordinates, detect supercells, estimate tornado intensity, or provide emergency alerts. Do not use it as a substitute for Civil Defence or meteorological agency guidance.")

st.markdown("---")
st.markdown(
    '<div class="signal-kicker">BRAZIL ENVIRONMENTAL SIGNAL · V1.0 · DATA PROVENANCE FIRST</div>',
    unsafe_allow_html=True
)
st.caption("Independent portfolio project by Amauri Almeida • Always consult official authorities for warnings and emergency instructions.")
