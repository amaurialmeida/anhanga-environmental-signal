"""
ANHANGA ENVIRONMENTAL SIGNAL
Painel de sinais ambientais para eventos climáticos no Brasil.

Inclui:
- consulta pública de eventos cadastrados no Supabase;
- área administrativa protegida por Supabase Auth;
- cadastro de evento, notícia e vídeo por URL;
- fontes oficiais INPE, CEMADEN, INMET e ANA;
- notícias recentes via GDELT, sempre rotuladas como mídia.

Nunca use a chave service_role no Streamlit Cloud.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import re
import xml.etree.ElementTree as ET

import folium
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

try:
    from supabase import create_client
except ImportError:
    create_client = None

st.set_page_config(
    page_title="Anhanga Environmental Signal",
    page_icon="🇧🇷",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
.event-box{border:1px solid var(--line);background:rgba(12,29,22,.82);border-radius:14px;padding:16px;margin:10px 0}.event-box h3{margin:0 0 6px}.muted{color:var(--muted);font-size:12px}
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


def safe(value):
    return html.escape(str(value or ""))


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
    root = ET.fromstring(data)
    rows = []
    for item in root.iter():
        if item.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title = link = date_raw = ""
        for child in item:
            tag = child.tag.split("}")[-1]
            if tag == "title":
                title = (child.text or "").strip()
            elif tag == "link":
                link = child.attrib.get("href", "") or (child.text or "").strip()
            elif tag in ("pubDate", "published", "updated", "date") and not date_raw:
                date_raw = (child.text or "").strip()
        if title and link:
            rows.append({"title": re.sub(r"\s+", " ", title), "url": link, "published": parse_date(date_raw)})
    return rows


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(topic):
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query": f"{TOPICS[topic]} Brazil sourcecountry:BR", "mode":"ArtList", "format":"json", "maxrecords":24, "sort":"DateDesc", "timespan":"7d"}
    try:
        payload = get(url, timeout=25).json()
        rows = [{"title": i.get("title", "Sem título"), "source": i.get("domain", "Fonte não informada"), "published": i.get("seendate", ""), "url": i.get("url", "")} for i in payload.get("articles", [])]
        return pd.DataFrame(rows, columns=["title", "source", "published", "url"]), None
    except Exception as exc:
        return pd.DataFrame(columns=["title", "source", "published", "url"]), str(exc)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_inmet():
    for url in ["https://apiprevmet3.inmet.gov.br/avisos/rss", "https://alertas2.inmet.gov.br/alt_rss.xml"]:
        try:
            return parse_rss(get(url, timeout=12).content)[:30], url, None
        except Exception:
            continue
    return [], None, "Feed de avisos não respondeu"


def supabase_client():
    """Cliente por sessão. Use somente SUPABASE_ANON_KEY, nunca service_role."""
    if create_client is None:
        return None
    if "supabase_client" in st.session_state:
        return st.session_state["supabase_client"]
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets.get("SUPABASE_ANON_KEY", st.secrets.get("SUPABASE_KEY"))
        if not url or not key:
            return None
        client = create_client(url, key)
        st.session_state["supabase_client"] = client
        return client
    except Exception:
        return None


def admin_email():
    try:
        return str(st.secrets["ADMIN_EMAIL"]).strip().lower()
    except Exception:
        return ""


def is_admin():
    user = st.session_state.get("admin_user")
    return bool(user and str(user.get("email", "")).lower() == admin_email() and admin_email())


def load_events(public_only=True):
    client = supabase_client()
    if client is None:
        return [], "Supabase não configurado"
    try:
        query = client.table("environmental_events").select("*").order("event_date", desc=True)
        if public_only:
            query = query.eq("published", True)
        return query.execute().data or [], None
    except Exception as exc:
        return [], str(exc)


def video_embed(url):
    url = (url or "").strip()
    if not url:
        return False
    if "youtube.com" in url or "youtu.be" in url or "vimeo.com" in url:
        st.video(url)
        return True
    st.markdown(f"[Abrir vídeo externo ↗]({safe(url)})")
    return True


def metric(label, value, note):
    st.markdown(f'<div class="panel"><div class="metric-label">{safe(label)}</div><div class="metric-value">{safe(value)}</div><div class="metric-note">{safe(note)}</div></div>', unsafe_allow_html=True)


def render_news(df, limit=8):
    if df.empty:
        st.info("Nenhuma menção encontrada para este filtro.")
        return
    for row in df.head(limit).itertuples(index=False):
        st.markdown(f'<div class="news-card"><div class="news-title">{safe(row.title)}</div><div class="news-meta">{safe(row.source)} · {safe(row.published)}</div></div>', unsafe_allow_html=True)
        if row.url:
            st.markdown(f"[Abrir matéria original ↗]({row.url})")


def render_public_events(events):
    if not events:
        st.info("Ainda não existem eventos publicados no caderno. A área administrativa pode cadastrar o primeiro registro.")
        return
    for event in events:
        st.markdown(f"<div class='event-box'><h3>{safe(event.get('title'))}</h3><div class='muted'>{safe(event.get('event_type'))} · {safe(event.get('city'))} / {safe(event.get('state'))} · {safe(event.get('event_date'))}</div><p>{safe(event.get('summary'))}</p></div>", unsafe_allow_html=True)
        if event.get("source_url"):
            st.markdown(f"[Abrir fonte ou notícia ↗]({event['source_url']})")
        if event.get("video_url"):
            video_embed(event["video_url"])
        st.markdown("---")


def render_admin():
    st.markdown('<div class="section-label">PRIVATE ADMINISTRATION</div>', unsafe_allow_html=True)
    client = supabase_client()
    if client is None:
        st.error("Supabase não está configurado. Adicione SUPABASE_URL, SUPABASE_ANON_KEY e ADMIN_EMAIL nos Secrets do Streamlit.")
        return
    if not is_admin():
        with st.form("admin_login"):
            email = st.text_input("E-mail administrativo")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("ENTRAR")
        if submit:
            if email.strip().lower() != admin_email():
                st.error("E-mail não autorizado.")
            else:
                try:
                    result = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
                    user = result.user
                    st.session_state["admin_user"] = {"id": user.id, "email": user.email}
                    st.success("Login realizado.")
                    st.rerun()
                except Exception:
                    st.error("Não foi possível entrar. Confira o e-mail, a senha e se o usuário foi criado no Supabase Auth.")
        return

    st.success(f"Sessão administrativa: {st.session_state['admin_user']['email']}")
    if st.button("SAIR"):
        try:
            client.auth.sign_out()
        except Exception:
            pass
        st.session_state.pop("admin_user", None)
        st.rerun()

    with st.form("event_form", clear_on_submit=True):
        st.subheader("Cadastrar acontecimento")
        title = st.text_input("Título do evento *")
        event_type = st.selectbox("Categoria", ["Enchente / inundação", "Queimada / incêndio", "Seca / calor", "Tempestade", "Deslizamento", "Outro"])
        c1, c2, c3 = st.columns(3)
        city = c1.text_input("Cidade")
        state = c2.text_input("UF", max_chars=2).upper()
        event_date = c3.date_input("Data do evento")
        summary = st.text_area("Resumo")
        source_url = st.text_input("Link da notícia ou fonte")
        video_url = st.text_input("Link do vídeo YouTube ou Vimeo (opcional)")
        published = st.checkbox("Publicar imediatamente", value=True)
        submit = st.form_submit_button("SALVAR EVENTO")

    if submit:
        if not title.strip():
            st.error("O título é obrigatório.")
        else:
            try:
                payload = {"title": title.strip(), "event_type": event_type, "city": city.strip(), "state": state.strip(), "event_date": event_date.isoformat(), "summary": summary.strip(), "source_url": source_url.strip() or None, "video_url": video_url.strip() or None, "published": published, "created_by": st.session_state["admin_user"]["id"]}
                client.table("environmental_events").insert(payload).execute()
                st.success("Evento salvo no Supabase.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível salvar o evento: {exc}")

    events, error = load_events(public_only=False)
    if error:
        st.warning(error)
    elif events:
        st.subheader("Registros existentes")
        st.dataframe(pd.DataFrame(events)[[c for c in ["title", "event_type", "city", "state", "event_date", "published"] if c in events[0]]], use_container_width=True, hide_index=True)


with st.sidebar:
    st.markdown('<div class="kicker">BRAZIL · ENVIRONMENTAL INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown("## 🇧🇷 ANHANGA SIGNAL")
    page = st.radio("SIGNAL ROUTER", ["Overview", "Event Radar", "Caderno de Eventos", "Brazil News", "Satellite Desk", "Administração", "Sources & Method"])
    st.markdown("---")
    st.caption("V1.2 · Brasil · Supabase ready")
    st.caption("Notícias não são confirmação oficial.")

st.markdown('<div class="kicker">BRAZIL · SOUTH AMERICA · CLIMATE EVENTS</div>', unsafe_allow_html=True)
titles = {"Overview":"BRAZIL ENVIRONMENTAL SIGNAL", "Event Radar":"EVENT RADAR", "Caderno de Eventos":"CADERNO DE EVENTOS", "Brazil News":"BRAZIL NEWS SIGNAL", "Satellite Desk":"SATELLITE DESK", "Administração":"ADMINISTRATION", "Sources & Method":"SOURCES & METHODOLOGY"}
subs = {"Overview":"Sinais oficiais, observações e cobertura jornalística sobre eventos climáticos no Brasil.", "Event Radar":"Mapa de regiões de referência para leitura territorial.", "Caderno de Eventos":"Acervo público de acontecimentos documentados no observatório.", "Brazil News":"Descoberta de reportagens recentes, sem transformar notícia em alerta.", "Satellite Desk":"GOES-19 em animação temporal e fontes brasileiras de observação da Terra.", "Administração":"Cadastro privado de acontecimentos, fontes e vídeos.", "Sources & Method":"Proveniência, limitações e regras para interpretar os sinais."}
st.markdown(f'<div class="hero">{safe(titles[page])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub">{safe(subs[page])}</div>', unsafe_allow_html=True)
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
public_events, events_error = load_events(public_only=True)

if page == "Overview":
    a, b, c, d = st.columns(4)
    with a: metric("REGIÕES DE REFERÊNCIA", len(REGIONS), "território brasileiro")
    with b: metric("EVENTOS NO CADERNO", len(public_events), "registros públicos")
    with c: metric("AVISOS INMET", len(inmet_rows), "feed público quando disponível")
    with d: metric("FONTES OFICIAIS", len(SOURCES), "INPE · CEMADEN · INMET · ANA")
    left, right = st.columns([1.25, 1])
    with left:
        st.markdown('<div class="section-label">01 / TERRITORIAL SIGNAL</div>', unsafe_allow_html=True)
        m = folium.Map(location=[-14.5, -52.5], zoom_start=4, tiles="OpenStreetMap", control_scale=True)
        for row in REGIONS.itertuples(index=False):
            popup = f"<b>{safe(row.name)}</b><br>{safe(row.state)}<br>{safe(row.focus)}<br><small>Ponto de referência; não representa ocorrência confirmada.</small>"
            folium.CircleMarker([row.lat, row.lon], radius=9, color="#63dda0", fill=True, fill_color="#63dda0", fill_opacity=.78, tooltip=f"{row.name} · {row.state}", popup=popup).add_to(m)
        st_folium(m, height=430, use_container_width=True, returned_objects=[])
        st.caption("As marcações representam regiões de referência, não focos ativos nem alertas confirmados.")
    with right:
        st.markdown('<div class="section-label">02 / OFFICIAL STATUS</div>', unsafe_allow_html=True)
        st.markdown('<span class="badge official">INPE · DADOS ABERTOS</span><span class="badge official">CEMADEN · MAPA</span><span class="badge official">INMET · AVISOS</span>', unsafe_allow_html=True)
        if inmet_error: st.warning("O feed automático do INMET não respondeu nesta sessão.")
        else: st.success(f"{len(inmet_rows)} itens encontrados no feed público do INMET.")
        st.markdown("---")
        st.markdown('<div class="section-label">03 / RECENT EVENTS</div>', unsafe_allow_html=True)
        render_public_events(public_events[:3])

elif page == "Event Radar":
    st.markdown('<div class="section-label">REGIONAL REFERENCE MAP</div>', unsafe_allow_html=True)
    m = folium.Map(location=[-14.5, -52.5], zoom_start=4, tiles="OpenStreetMap", control_scale=True)
    for row in REGIONS.itertuples(index=False):
        folium.Marker([row.lat, row.lon], tooltip=f"{row.name} / {row.state}", popup=f"<b>{row.name}</b><br>Prioridade: {row.focus}", icon=folium.Icon(color="green", icon="info-sign")).add_to(m)
    st_folium(m, height=600, use_container_width=True, returned_objects=[])
    st.info("O mapa usa regiões de referência. Os eventos do caderno ficam na seção pública dedicada.")

elif page == "Caderno de Eventos":
    if events_error: st.warning("Supabase ainda não está configurado. O caderno aparecerá depois que os Secrets e o SQL forem aplicados.")
    render_public_events(public_events)

elif page == "Brazil News":
    st.markdown('<div class="section-label">MEDIA DISCOVERY · NOT OFFICIAL CONFIRMATION</div>', unsafe_allow_html=True)
    render_news(news, 24)

elif page == "Satellite Desk":
    st.markdown('<div class="section-label">LIVE SATELLITE INTELLIGENCE / NOAA · NESDIS</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="panel" style="margin-bottom:14px">
        <div class="metric-label">PRIMARY GEOSTATIONARY SATELLITE</div>
        <div class="hero" style="font-size:clamp(25px,3vw,38px);margin-top:8px">🛰️ GOES-19 / GOES EAST</div>
        <div class="metric-note" style="font-size:12px;margin-top:9px">
            Advanced Baseline Imager (ABI) · South America · NOAA / NESDIS / STAR
        </div>
        <div class="muted" style="margin-top:8px">
            Imagens observacionais reais, com animação temporal e diferentes canais espectrais.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Os setores norte e sul são produtos oficiais NOAA para a América do Sul.
    c1, c2, c3 = st.columns([1.15, 1.15, 1])
    with c1:
        sector_label = st.selectbox(
            "GEOGRAPHIC SECTOR",
            ["América do Sul — Sul", "América do Sul — Norte"],
            key="goes_sector"
        )
    with c2:
        product_labels = {
            "GeoColor · Dia / noite": "GEOCOLOR",
            "Infravermelho · Band 13": "13",
            "Vapor d'água · Band 08": "08",
            "Visível · Band 02": "02",
        }
        product_label = st.selectbox(
            "SPECTRAL PRODUCT",
            list(product_labels.keys()),
            key="goes_product"
        )
    with c3:
        loop_label = st.selectbox(
            "ANIMATION WINDOW",
            ["2 horas · 12 imagens", "4 horas · 24 imagens"],
            key="goes_loop"
        )

    sector_code = "ssa" if sector_label == "América do Sul — Sul" else "nsa"
    band_code = product_labels[product_label]
    image_count = 12 if loop_label.startswith("2") else 24
    goes_url = (
        "https://www.goes.noaa.gov/sector_band.php"
        f"?band={band_code}&length={image_count}&sat=G19&sector={sector_code}"
    )

    st.markdown('<div class="section-label">01 / REAL-TIME SATELLITE LOOP</div>', unsafe_allow_html=True)
    st.caption(
        f"GOES-19 · {sector_label} · {product_label} · "
        f"{loop_label} · intervalo nominal de 10 minutos"
    )

    # A página NOAA contém o player, controle temporal, horários UTC e opção de ampliar.
    # O conteúdo é servido pela própria NOAA; não é uma imagem simulada nem um cache local.
    components.iframe(goes_url, height=790, scrolling=True)

    st.markdown("""
    <div class="panel" style="margin-top:10px">
        <div class="metric-label">HOW TO READ THIS PRODUCT</div>
        <div class="news-title" style="margin-top:8px">GeoColor</div>
        <div class="metric-note">Composição em cores naturais durante o dia e infravermelho multiespectral à noite.</div>
        <div class="news-title" style="margin-top:12px">Band 13 · Infrared</div>
        <div class="metric-note">Canal infravermelho de janela, útil para observar nuvens de dia e de noite e estimar características térmicas dos topos das nuvens.</div>
        <div class="news-title" style="margin-top:12px">Band 08 · Water Vapor</div>
        <div class="metric-note">Canal de vapor d’água em altos níveis da troposfera, útil para acompanhar umidade e padrões atmosféricos.</div>
        <div class="news-title" style="margin-top:12px">Band 02 · Visible</div>
        <div class="metric-note">Canal visível de alta resolução; não fornece imagem iluminada durante a noite.</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label">02 / DATA PROVENANCE</div>', unsafe_allow_html=True)
    sector_name = "Southern" if sector_code == "ssa" else "Northern"
    st.markdown(
        "**SATELLITE:** GOES-19 \n"
        "**INSTRUMENT:** Advanced Baseline Imager (ABI)  \n"
        "**OPERATOR:** NOAA / NESDIS  \n"
        f"**SECTOR:** South America — {sector_name}  \n"
        "**SOURCE:** NOAA / NESDIS / STAR  \n"
        "**NOMINAL UPDATE:** approximately every 10 minutes."
    )
    st.caption(
        "Crédito das imagens GeoColor: CIRA / NOAA. Os horários das imagens são exibidos "
        "no próprio visualizador NOAA em UTC. A disponibilidade pode variar conforme "
        "manutenção ou falhas na fonte."
    )
    st.warning(
        "Uso para observação e pesquisa. Este produto experimental não substitui "
        "avisos oficiais, previsões meteorológicas ou orientações de defesa civil."
    )
    st.markdown(f"[ABRIR VISUALIZADOR ORIGINAL DA NOAA ↗]({goes_url})")

    st.markdown('<div class="section-label">03 / BRAZILIAN AND GLOBAL EARTH OBSERVATION SOURCES</div>', unsafe_allow_html=True)
    st.write(
        "O GOES-19 passa a ser o visualizador meteorológico principal. "
        "As fontes brasileiras continuam disponíveis para queimadas, uso da terra, "
        "monitoramento de desastres e dados hidrológicos."
    )
    cols = st.columns(2)
    for i, (name, desc, url, kind) in enumerate(SOURCES):
        with cols[i % 2]:
            st.markdown(
                f'<div class="panel"><span class="badge official">{safe(kind.upper())}</span>'
                f'<div class="news-title" style="margin-top:8px">{safe(name)}</div>'
                f'<div class="metric-note" style="margin:8px 0 12px">{safe(desc)}</div>'
                f'<a href="{safe(url)}" target="_blank">ABRIR FONTE OFICIAL ↗</a></div>',
                unsafe_allow_html=True
            )

elif page == "Administração":
    render_admin()

else:
    st.markdown('<div class="section-label">DATA PROVENANCE FIRST</div>', unsafe_allow_html=True)
    st.markdown("### Camadas do painel")
    st.write("**Oficial / alerta:** publicação de uma instituição competente. **Observação:** produto ou dado instrumental/geoespacial do INPE. **Mídia:** reportagem para contexto e triagem. **Caderno:** registro editorial criado pelo administrador.")
    st.markdown("### Configuração do Supabase")
    st.code("SUPABASE_URL = \"https://seu-projeto.supabase.co\"\nSUPABASE_ANON_KEY = \"sua-chave-anon-public\"\nADMIN_EMAIL = \"seu-email\"", language="toml")
    st.warning("Nunca coloque SUPABASE_SERVICE_ROLE_KEY no Streamlit Cloud.")
    st.markdown("### Limitações")
    st.write("A primeira versão salva links de YouTube/Vimeo, em vez de copiar vídeos para o Storage. Isso reduz custos e problemas de direitos autorais. O SQL fornecido cria a tabela e as políticas de segurança; ele precisa ser executado uma vez no SQL Editor do Supabase.")

st.markdown("---")
st.markdown('<div class="kicker">ANHANGA ENVIRONMENTAL SIGNAL · BRAZIL · DATA PROVENANCE FIRST</div>', unsafe_allow_html=True)
st.caption(f"Atualização da consulta: {st.session_state.get('last_fetch', 'sob demanda')} · Consulte sempre os órgãos oficiais para instruções de emergência.")
