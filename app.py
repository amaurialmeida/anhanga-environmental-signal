"""
ANHANGA ENVIRONMENTAL SIGNAL
Painel de sinais ambientais para eventos climáticos no Brasil.

Princípio de proveniência:
- Avisos oficiais: INMET e CEMADEN.
- Observação por satélite/dados geoespaciais: INPE.
- Descoberta de notícias: GDELT, sempre rotulada como menção jornalística.

O painel não substitui alertas da Defesa Civil, do INMET ou do CEMADEN.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import re
import xml.etree.ElementTree as ET

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Anhanga Environmental Signal",
    page_icon="🇧🇷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Visual system: same dark signal-router language, adapted to Brazil
# -----------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;600;700;800&display=swap');
:root{--bg:#06100d;--panel:#0c1d16;--line:rgba(93,190,133,.22);--green:#63dda0;--cyan:#41c7e8;--muted:#91aa9b;--white:#edf8f0}
html,body,[class*="css"]{font-family:Manrope,sans-serif}.stApp{background:radial-gradient(ellipse at 10% 0%,#123423 0%,#06100d 52%,#040907 100%);color:var(--white)}
[data-testid="stSidebar"]{background:#07150e;border-right:1px solid var(--line)}.block-container{max-width:1500px;padding-top:1.5rem}h1,h2,h3{letter-spacing:-.04em}
.kicker,.section-label,.metric-label{font:500 10px 'DM Mono',monospace;letter-spacing:.15em;text-transform:uppercase;color:var(--green)}
.hero{font-size:clamp(28px,4vw,50px);line-height:1.04;font-weight:800;letter-spacing:-.06em}.sub{color:var(--muted);font-size:13px;margin-top:8px}
.panel{background:linear-gradient(145deg,rgba(17,42,30,.94),rgba(8,22,16,.96));border:1px solid var(--line);border-radius:15px;padding:17px 18px;min-height:110px}
.metric-value{color:#f1fff4;font-size:30px;font-weight:800;margin-top:8px}.metric-note{color:#91aa9b;font-size:11px;margin-top:3px}
.news-card{border:1px solid var(--line);background:rgba(12,29,22,.82);border-radius:12px;padding:13px 15px;margin:8px 0}.news-title{font-weight:700;color:#edf8f0;font-size:14px;line-height:1.35}.news-meta{font:11px 'DM Mono',monospace;color:#8da99a;margin-top:6px}
a{color:#78e5a8!important}.stButton>button{border:1px solid rgba(99,221,160,.35);border-radius:9px;background:#102b1e;color:#e3faeb}hr{border-color:var(--line)}footer{visibility:hidden}
.badge{display:inline-block;border-radius:999px;padding:4px 9px;font:500 10px 'DM Mono',monospace;letter-spacing:.05em;margin:2px 3px 2px 0}.official{background:rgba(99,221,160,.13);color:#8bf0b6;border:1px solid rgba(99,221,160,.35)}.media{background:rgba(65,199,232,.12);color:#8be4f6;border:1px solid rgba(65,199,232,.35)}
</style>
""", unsafe_allow_html=True)

UA = {"User-Agent": "AnhangaEnvironmentalSignal/1.0 (+https://github.com/amaurialmeida/anhanga-environmental-signal)"}

SOURCES = [
    ("INPE · Programa Queimadas", "Focos de calor e incêndios florestais em quase tempo real.", "https://data.inpe.br/queimadas/dados-abertos/", "Observação"),
    ("INPE · TerraBrasilis", "Desmatamento, uso da terra e dados geoespaciais por bioma.", "https://terrabrasilis.dpi.inpe.br/", "Observação"),
    ("INPE/CPTEC · DSAT", "Produtos e imagens meteorológicas por satélite.", "https://www.cptec.inpe.br/dsat/", "Observação"),
    ("CEMADEN · Mapa interativo", "Monitoramento de chuva, pluviômetros, radar e risco de desastres.", "https://www.gov.br/cemaden/pt-br/assuntos/mapa-interativo", "Oficial"),
    ("INMET · Avisos", "Avisos meteorológicos oficiais por área e severidade.", "https://alertas2.inmet.gov.br/", "Oficial"),
    ("ANA · HidroWeb", "Dados hidrológicos e estações de monitoramento.", "https://www.snirh.gov.br/hidroweb/", "Oficial"),
]

TOPICS = {
    "Todos os eventos": '(enchente OR inundação OR alagamento OR enxurrada OR queimada OR incêndio OR seca OR "chuva intensa" OR tempestade OR granizo OR deslizamento)',
    "Chuvas e inundações": '(enchente OR inundação OR alagamento OR enxurrada OR "chuva intensa" OR deslizamento)',
    "Queimadas e fumaça": '(queimada OR queimadas OR incêndio florestal OR fumaça OR fogo)',
    "Seca e calor": '(seca OR estiagem OR "onda de calor" OR calor extremo OR crise hídrica)',
    "Tempestades": '(tempestade OR granizo OR vendaval OR tornado OR ciclone)',
}

# Locations are reference points for orientation, not incident confirmations.
REGIONS = pd.DataFrame([
    {"name":"Amazônia", "state":"AM/PA/RO/AC", "lat":-3.5, "lon":-62.5, "focus":"queimadas · fumaça · seca"},
    {"name":"Pantanal", "state":"MT/MS", "lat":-17.5, "lon":-57.0, "focus":"queimadas · fogo"},
    {"name":"Centro-Oeste", "state":"GO/MT/MS/DF", "lat":-15.8, "lon":-49.2, "focus":"seca · calor · queimadas"},
    {"name":"Sudeste", "state":"MG/ES/RJ/SP", "lat":-21.1, "lon":-44.4, "focus":"chuvas · deslizamentos"},
    {"name":"Sul", "state":"PR/SC/RS", "lat":-27.7, "lon":-51.0, "focus":"tempestades · inundações"},
    {"name":"Nordeste", "state":"BA/PE/CE/MA/PI", "lat":-8.5, "lon":-40.5, "focus":"seca · chuvas intensas"},
])


def get(url, timeout=18):
    response = requests.get(url, headers=UA, timeout=timeout)
    response.raise_for_status()
    return response


def parse_date(value):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None


def parse_rss(data):
    """Parseia RSS/Atom sem depender de feedparser."""
    root = ET.fromstring(data)
    rows = []
    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = link = date_raw = ""
        for child in item:
            ctag = child.tag.split("}")[-1]
            if ctag == "title":
                title = (child.text or "").strip()
            elif ctag == "link":
                link = child.attrib.get("href", "") or (child.text or "").strip()
            elif ctag in ("pubDate", "published", "updated", "date") and not date_raw:
                date_raw = (child.text or "").strip()
        if title and link:
            rows.append({"title": re.sub(r"\s+", " ", title), "url": link, "published": parse_date(date_raw)})
    return rows


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(topic):
    """GDELT é usado somente para descoberta de cobertura jornalística."""
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query": f"{TOPICS[topic]} Brazil sourcecountry:BR", "mode":"ArtList", "format":"json", "maxrecords":24, "sort":"DateDesc", "timespan":"7d"}
    try:
        payload = get(url, timeout=25).json()
        rows = []
        for item in payload.get("articles", []):
            rows.append({"title": item.get("title", "Sem título"), "source": item.get("domain", "Fonte não informada"), "published": item.get("seendate", ""), "url": item.get("url", "")})
        return pd.DataFrame(rows, columns=["title", "source", "published", "url"]), None
    except Exception as exc:
        return pd.DataFrame(columns=["title", "source", "published", "url"]), str(exc)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_inmet():
    """Feed público de avisos do INMET; falha com segurança se mudar."""
    candidates = ["https://apiprevmet3.inmet.gov.br/avisos/rss", "https://alertas2.inmet.gov.br/alt_rss.xml"]
    for url in candidates:
        try:
            rows = parse_rss(get(url, timeout=12).content)
            return rows[:30], url, None
        except Exception:
            continue
    return [], None, "Feed de avisos não respondeu"


def safe(value):
    return html.escape(str(value or ""))


def metric(label, value, note):
    st.markdown(f'<div class="panel"><div class="metric-label">{safe(label)}</div><div class="metric-value">{safe(value)}</div><div class="metric-note">{safe(note)}</div></div>', unsafe_allow_html=True)


def render_news(df, limit=8):
    if df.empty:
        st.info("Nenhuma menção encontrada para este filtro. Tente coletar novamente ou mude a categoria.")
        return
    for row in df.head(limit).itertuples(index=False):
        st.markdown(f'<div class="news-card"><div class="news-title">{safe(row.title)}</div><div class="news-meta">{safe(row.source)} · {safe(row.published)}</div></div>', unsafe_allow_html=True)
        if row.url:
            st.markdown(f"[Abrir matéria original ↗]({row.url})")


# -----------------------------------------------------------------------------
# Sidebar / controls
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="kicker">BRAZIL · ENVIRONMENTAL INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown("## 🇧🇷 ANHANGA SIGNAL")
    page = st.radio("SIGNAL ROUTER", ["Overview", "Event Radar", "Brazil News", "Satellite Desk", "Sources & Method"])
    st.markdown("---")
    st.caption("V1.1 · Brasil")
    st.caption("Notícias não são confirmação oficial de eventos.")

st.markdown('<div class="kicker">BRAZIL · SOUTH AMERICA · CLIMATE EVENTS</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hero">{safe({"Overview":"BRAZIL ENVIRONMENTAL SIGNAL","Event Radar":"EVENT RADAR","Brazil News":"BRAZIL NEWS SIGNAL","Satellite Desk":"SATELLITE DESK","Sources & Method":"SOURCES & METHODOLOGY"}[page])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub">{safe({"Overview":"Sinais oficiais, observações e cobertura jornalística sobre eventos climáticos no território brasileiro.","Event Radar":"Mapa de regiões de atenção e pontos de referência para leitura territorial.","Brazil News":"Descoberta de reportagens brasileiras recentes, sem transformar notícia em alerta.","Satellite Desk":"Portais oficiais brasileiros para imagens, focos de calor e dados geoespaciais.","Sources & Method":"Proveniência, limitações e regras para interpretar os sinais."}[page])}</div>', unsafe_allow_html=True)
st.markdown("")

with st.expander("SIGNAL FILTERS", expanded=page in ["Overview", "Brazil News"]):
    topic = st.selectbox("CATEGORIA", list(TOPICS))
    refresh = st.button("↻ COLETAR SINAIS MAIS RECENTES")

if refresh or "news_df" not in st.session_state or st.session_state.get("topic") != topic:
    with st.spinner("Consultando fontes públicas…"):
        st.session_state["news_df"], st.session_state["news_error"] = fetch_news(topic)
        st.session_state["topic"] = topic
        st.session_state["last_fetch"] = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

news = st.session_state.get("news_df", pd.DataFrame(columns=["title", "source", "published", "url"]))
inmet_rows, inmet_url, inmet_error = fetch_inmet()

# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
if page == "Overview":
    a, b, c, d = st.columns(4)
    with a: metric("REGIÕES DE REFERÊNCIA", len(REGIONS), "território brasileiro")
    with b: metric("MENÇÕES RECENTES", len(news), "GDELT · últimos 7 dias")
    with c: metric("AVISOS INMET", len(inmet_rows), "feed público quando disponível")
    with d: metric("FONTES OFICIAIS", len(SOURCES), "INPE · CEMADEN · INMET · ANA")
    st.markdown("")

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown('<div class="section-label">01 / TERRITORIAL SIGNAL</div>', unsafe_allow_html=True)
        m = folium.Map(location=[-14.5, -52.5], zoom_start=4, tiles="CartoDB dark_matter", control_scale=True)
        for row in REGIONS.itertuples(index=False):
            popup = f"<b>{safe(row.name)}</b><br>{safe(row.state)}<br>{safe(row.focus)}<br><small>Ponto de referência; não representa ocorrência confirmada.</small>"
            folium.CircleMarker([row.lat, row.lon], radius=9, color="#63dda0", fill=True, fill_color="#63dda0", fill_opacity=.78, tooltip=f"{row.name} · {row.state}", popup=popup).add_to(m)
        st_folium(m, height=430, use_container_width=True, returned_objects=[])
        st.caption("As marcações representam regiões de referência, não focos ativos nem alertas confirmados.")
    with right:
        st.markdown('<div class="section-label">02 / OFFICIAL STATUS</div>', unsafe_allow_html=True)
        st.markdown('<span class="badge official">INPE · DADOS ABERTOS</span><span class="badge official">CEMADEN · MAPA</span><span class="badge official">INMET · AVISOS</span>', unsafe_allow_html=True)
        if inmet_error:
            st.warning("O feed automático do INMET não respondeu nesta sessão. Consulte o portal oficial para o estado atual.")
        else:
            st.success(f"{len(inmet_rows)} itens encontrados no feed público do INMET.")
            for item in inmet_rows[:5]:
                st.markdown(f"**{safe(item['title'])}**")
        st.markdown("---")
        st.markdown('<div class="section-label">03 / MEDIA SIGNAL</div>', unsafe_allow_html=True)
        render_news(news, 5)

elif page == "Event Radar":
    st.markdown('<div class="section-label">REGIONAL REFERENCE MAP</div>', unsafe_allow_html=True)
    m = folium.Map(location=[-14.5, -52.5], zoom_start=4, tiles="CartoDB dark_matter", control_scale=True)
    for row in REGIONS.itertuples(index=False):
        folium.Marker([row.lat, row.lon], tooltip=f"{row.name} / {row.state}", popup=f"<b>{row.name}</b><br>Prioridade temática: {row.focus}", icon=folium.Icon(color="green", icon="info-sign")).add_to(m)
    st_folium(m, height=600, use_container_width=True, returned_objects=[])
    st.info("Próxima evolução: conectar camadas geográficas oficiais do INPE e CEMADEN diretamente ao mapa, mantendo cada camada identificada pela sua fonte e data de atualização.")

elif page == "Brazil News":
    st.markdown('<div class="section-label">MEDIA DISCOVERY · NOT OFFICIAL CONFIRMATION</div>', unsafe_allow_html=True)
    if st.session_state.get("news_error"):
        st.warning("A consulta de notícias falhou nesta sessão. Acesse as fontes oficiais abaixo para confirmar qualquer evento.")
    render_news(news, 24)

elif page == "Satellite Desk":
    st.markdown('<div class="section-label">BRAZILIAN EARTH OBSERVATION SOURCES</div>', unsafe_allow_html=True)
    st.write("O painel prioriza fontes brasileiras. O GOES aparece apenas quando um portal oficial o utiliza como produto meteorológico; ele não é um satélite brasileiro.")
    cols = st.columns(2)
    for i, (name, desc, url, kind) in enumerate(SOURCES):
        with cols[i % 2]:
            badge = "official" if kind == "Oficial" else "media"
            st.markdown(f'<div class="panel"><span class="badge {badge}">{safe(kind.upper())}</span><div class="news-title" style="margin-top:8px">{safe(name)}</div><div class="metric-note" style="margin:8px 0 12px">{safe(desc)}</div><a href="{safe(url)}" target="_blank">ABRIR FONTE OFICIAL ↗</a></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### O que entra como satélite brasileiro?")
    st.write("Para esta versão, o núcleo de observação brasileira é o INPE: Programa Queimadas, TerraBrasilis, CBERS/Amazônia e produtos do CPTEC. O CEMADEN é uma fonte nacional de monitoramento de desastres, mas não é um operador de satélite; ele integra sensores, pluviômetros, radar e análise de risco.")

else:
    st.markdown('<div class="section-label">DATA PROVENANCE FIRST</div>', unsafe_allow_html=True)
    st.markdown("### Camadas do painel")
    st.write("**Oficial / alerta:** publicação de uma instituição competente, como INMET ou CEMADEN. **Observação:** produto ou dado instrumental/geoespacial do INPE. **Mídia:** reportagem descoberta pelo GDELT; serve para contexto e triagem, não para confirmar ocorrência.")
    st.markdown("### Fontes e links")
    for name, desc, url, _ in SOURCES:
        st.markdown(f"- [{name}]({url}) — {desc}")
    st.markdown("### Limitações atuais")
    st.write("A versão inicial não emite notificações, não substitui a Defesa Civil e não estima severidade de um evento. O mapa usa regiões de referência, enquanto a integração de focos de calor e camadas do CEMADEN depende da disponibilidade e dos termos de cada serviço público. Notícias podem conter duplicatas, atraso editorial ou localização ambígua.")
    st.markdown("### Próximos passos recomendados")
    st.write("1. Adicionar um coletor separado para os arquivos abertos do Programa Queimadas do INPE. 2. Integrar camadas GeoJSON/WMS oficialmente expostas pelo CEMADEN. 3. Criar histórico diário local para comparar os sinais por estado e bioma. 4. Adicionar INMET, ANA e Defesa Civil estadual como fontes de alerta e validação.")

st.markdown("---")
st.markdown('<div class="kicker">ANHANGA ENVIRONMENTAL SIGNAL · BRAZIL · DATA PROVENANCE FIRST</div>', unsafe_allow_html=True)
st.caption(f"Atualização da consulta: {st.session_state.get('last_fetch', 'sob demanda')} · Consulte sempre os órgãos oficiais para instruções de emergência.")
