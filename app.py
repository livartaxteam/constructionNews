import streamlit as st
import requests
from bs4 import BeautifulSoup
import feedparser
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import time
import re

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="건설 수주 · 재개발 뉴스 트래커",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS 스타일 ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

/* 헤더 */
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 2rem 2.5rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    color: white;
    position: relative;
    overflow: hidden;
}
.main-header::before {
    content: "🏗️";
    position: absolute;
    right: 2rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 5rem;
    opacity: 0.15;
}
.main-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; letter-spacing: -0.5px; }
.main-header p  { margin: 0.4rem 0 0; opacity: 0.75; font-size: 0.9rem; }

/* 뉴스 카드 */
.news-card {
    background: white;
    border: 1px solid #e8ecf0;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.9rem;
    transition: box-shadow .2s, border-color .2s;
    position: relative;
}
.news-card:hover { box-shadow: 0 4px 20px rgba(0,0,0,.08); border-color: #c0ccd8; }
.news-card .source-badge {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 20px;
    margin-bottom: 0.5rem;
}
.badge-naver  { background: #03c75a22; color: #03c75a; }
.badge-google { background: #4285f422; color: #4285f4; }

.news-card .title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #1a1a2e;
    margin-bottom: 0.3rem;
    line-height: 1.45;
}
.news-card .title a { text-decoration: none; color: inherit; }
.news-card .title a:hover { color: #0f3460; text-decoration: underline; }
.news-card .meta { font-size: 0.78rem; color: #8a96a3; }

/* 키워드 태그 */
.kw-tag {
    display: inline-block;
    background: #f0f4ff;
    color: #4a6fa5;
    border-radius: 6px;
    padding: 1px 7px;
    font-size: 0.72rem;
    font-weight: 500;
    margin-right: 4px;
}

/* 통계 카드 */
.stat-box {
    background: #f7f9fc;
    border: 1px solid #e4e9f0;
    border-radius: 10px;
    padding: 1rem;
    text-align: center;
}
.stat-box .num  { font-size: 1.8rem; font-weight: 700; color: #0f3460; }
.stat-box .label{ font-size: 0.75rem; color: #6b7a8d; margin-top: 2px; }

/* 섹션 구분 */
.section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1a1a2e;
    border-left: 4px solid #0f3460;
    padding-left: 0.7rem;
    margin: 1.2rem 0 0.8rem;
}

div[data-testid="stSidebar"] { background: #f7f9fc; }
</style>
""", unsafe_allow_html=True)

# ── 상수 ────────────────────────────────────────────────────────────────────
DEFAULT_COMPANIES = [
    "삼성물산", "현대건설", "대우건설", "GS건설", "포스코이앤씨",
    "롯데건설", "HDC현대산업개발", "SK에코플랜트", "DL이앤씨", "호반건설",
]

KEYWORDS_REDEV = ["재개발", "재건축", "정비사업", "뉴타운", "도시정비"]
KEYWORDS_ORDER = ["수주", "신규공사", "공사계약", "낙찰", "착공", "시공권"]
KEYWORDS_HOUSING = ["분양", "아파트", "주택사업", "공동주택", "단지"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── 유틸 ────────────────────────────────────────────────────────────────────
def highlight_keywords(text: str, keywords: list[str]) -> list[str]:
    found = [kw for kw in keywords if kw in text]
    return found

def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()

def parse_date(date_str: str) -> str:
    """날짜 문자열을 깔끔하게 변환"""
    try:
        if not date_str:
            return ""
        # feedparser struct_time
        if hasattr(date_str, "tm_year"):
            dt = datetime(*date_str[:6])
            return dt.strftime("%Y.%m.%d %H:%M")
        return str(date_str)[:16]
    except Exception:
        return str(date_str)[:16] if date_str else ""

# ── 뉴스 수집 함수 ──────────────────────────────────────────────────────────
def fetch_naver_news(query: str, display: int = 10) -> list[dict]:
    """네이버 뉴스 RSS로 수집"""
    results = []
    encoded = urllib.parse.quote(query)
    url = f"https://news.naver.com/search/results.naver?query={encoded}&sm=tab_tmr&sort=1"
    # 네이버 뉴스 RSS (검색)
    rss_url = f"https://news.naver.com/search/results.naver?query={encoded}&sm=tab_tmr&sort=1&photo=0&field=0&ds=&de=&start=1&refresh_start=0"

    # feedparser로 네이버 뉴스 RSS 시도
    rss_feed_url = f"https://search.naver.com/rss.nhn?where=news&query={encoded}&start=1&display={display}"
    feed = feedparser.parse(rss_feed_url)

    for entry in feed.entries[:display]:
        title = clean_html(entry.get("title", ""))
        desc  = clean_html(entry.get("description", entry.get("summary", "")))
        link  = entry.get("link", "")
        pub   = parse_date(entry.get("published_parsed") or entry.get("published", ""))

        all_kw = KEYWORDS_REDEV + KEYWORDS_ORDER + KEYWORDS_HOUSING
        found = highlight_keywords(title + desc, all_kw)

        results.append({
            "source": "naver",
            "title": title,
            "desc": desc[:120] + "…" if len(desc) > 120 else desc,
            "link": link,
            "date": pub,
            "keywords": found,
            "query": query,
        })
    return results


def fetch_google_news(query: str, num: int = 10) -> list[dict]:
    """Google News RSS로 수집"""
    results = []
    encoded = urllib.parse.quote(f"{query} 건설")
    rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)

    for entry in feed.entries[:num]:
        title = clean_html(entry.get("title", ""))
        desc  = clean_html(entry.get("description", entry.get("summary", "")))
        link  = entry.get("link", "")
        pub   = parse_date(entry.get("published_parsed") or entry.get("published", ""))

        all_kw = KEYWORDS_REDEV + KEYWORDS_ORDER + KEYWORDS_HOUSING
        found = highlight_keywords(title + desc, all_kw)

        results.append({
            "source": "google",
            "title": title,
            "desc": desc[:120] + "…" if len(desc) > 120 else desc,
            "link": link,
            "date": pub,
            "keywords": found,
            "query": query,
        })
    return results


def collect_all_news(companies: list[str], extra_kw: list[str], per_query: int = 5) -> pd.DataFrame:
    all_news = []
    progress = st.progress(0, text="뉴스 수집 중…")
    total = len(companies) + len(extra_kw)

    for i, company in enumerate(companies):
        q = f"{company} 수주 OR 재개발 OR 재건축 OR 분양"
        all_news += fetch_naver_news(q, per_query)
        all_news += fetch_google_news(company, per_query)
        time.sleep(0.3)
        progress.progress((i + 1) / total, text=f"수집 중: {company}")

    for i, kw in enumerate(extra_kw):
        all_news += fetch_naver_news(kw, per_query)
        all_news += fetch_google_news(kw, per_query)
        time.sleep(0.3)
        progress.progress((len(companies) + i + 1) / total, text=f"수집 중: {kw}")

    progress.empty()

    if not all_news:
        return pd.DataFrame()

    df = pd.DataFrame(all_news)
    # 중복 제거 (제목 기준)
    df = df.drop_duplicates(subset=["title"])
    # 키워드 있는 것 우선 정렬
    df["kw_count"] = df["keywords"].apply(len)
    df = df.sort_values("kw_count", ascending=False).reset_index(drop=True)
    return df


# ── 사이드바 ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ 검색 설정")

    selected_companies = st.multiselect(
        "🏢 건설사 선택",
        options=DEFAULT_COMPANIES,
        default=DEFAULT_COMPANIES[:5],
        help="뉴스를 검색할 건설사를 선택하세요",
    )

    custom_company = st.text_input("➕ 건설사 직접 추가", placeholder="예: 태영건설")
    if custom_company:
        selected_companies.append(custom_company.strip())

    st.markdown("---")
    st.markdown("### 🔍 추가 키워드")
    extra_kw_input = st.text_area(
        "키워드 (줄바꿈으로 구분)",
        value="재개발 수주\n재건축 착공\n정비사업 낙찰",
        height=100,
    )
    extra_keywords = [k.strip() for k in extra_kw_input.split("\n") if k.strip()]

    st.markdown("---")
    st.markdown("### 📂 카테고리 필터")
    show_redev  = st.checkbox("🏚️ 재개발·재건축",  value=True)
    show_order  = st.checkbox("📋 신규 수주",       value=True)
    show_housing= st.checkbox("🏠 분양·주택사업",   value=True)

    st.markdown("---")
    per_query = st.slider("쿼리당 뉴스 수", 3, 15, 5)
    search_btn = st.button("🔎 뉴스 수집 시작", use_container_width=True, type="primary")

# ── 메인 헤더 ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>🏗️ 건설 수주 · 재개발 뉴스 트래커</h1>
  <p>건설사별 신규 수주현장 · 재개발 · 재건축 · 분양 뉴스를 네이버·구글에서 실시간 수집합니다</p>
</div>
""", unsafe_allow_html=True)

# ── 세션 상태 초기화 ─────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "last_run" not in st.session_state:
    st.session_state.last_run = None

# ── 뉴스 수집 실행 ───────────────────────────────────────────────────────────
if search_btn:
    if not selected_companies and not extra_keywords:
        st.warning("건설사 또는 키워드를 1개 이상 선택해 주세요.")
    else:
        with st.spinner("뉴스를 수집하고 있습니다…"):
            df = collect_all_news(selected_companies, extra_keywords, per_query)
            st.session_state.df = df
            st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── 결과 표시 ────────────────────────────────────────────────────────────────
df = st.session_state.df

if df.empty:
    st.info("👆 왼쪽 사이드바에서 건설사와 키워드를 선택한 후 **뉴스 수집 시작** 버튼을 눌러주세요.")
    st.markdown("""
    #### 이런 뉴스를 찾아드립니다
    - 🏚️ **재개발·재건축** — 정비구역 지정, 시공사 선정, 조합원 모집 등
    - 📋 **신규 수주** — 공사 낙찰, 계약 체결, 착공 소식
    - 🏠 **분양·주택사업** — 아파트 분양, 공동주택 인허가, 단지 개발
    """)
else:
    # ── 통계 ─────────────────────────────────────────────────────────────────
    redev_df   = df[df["keywords"].apply(lambda x: any(k in x for k in KEYWORDS_REDEV))]
    order_df   = df[df["keywords"].apply(lambda x: any(k in x for k in KEYWORDS_ORDER))]
    housing_df = df[df["keywords"].apply(lambda x: any(k in x for k in KEYWORDS_HOUSING))]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="stat-box"><div class="num">{len(df)}</div>
        <div class="label">총 수집 뉴스</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="stat-box"><div class="num">{len(redev_df)}</div>
        <div class="label">🏚️ 재개발·재건축</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="stat-box"><div class="num">{len(order_df)}</div>
        <div class="label">📋 신규 수주</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="stat-box"><div class="num">{len(housing_df)}</div>
        <div class="label">🏠 분양·주택사업</div></div>""", unsafe_allow_html=True)

    if st.session_state.last_run:
        st.caption(f"🕐 마지막 수집: {st.session_state.last_run}")

    st.markdown("---")

    # ── 필터링 ───────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["전체", "🏚️ 재개발·재건축", "📋 신규 수주", "🏠 분양·주택"])

    def render_news(dataframe: pd.DataFrame):
        if dataframe.empty:
            st.info("해당 카테고리의 뉴스가 없습니다.")
            return
        for _, row in dataframe.iterrows():
            badge_cls = "badge-naver" if row["source"] == "naver" else "badge-google"
            badge_lbl = "네이버 뉴스" if row["source"] == "naver" else "Google 뉴스"
            kw_tags   = "".join(f'<span class="kw-tag">{k}</span>' for k in row["keywords"]) if row["keywords"] else ""
            date_str  = f" · {row['date']}" if row["date"] else ""
            query_str = f" · 검색어: {row['query']}" if row.get("query") else ""

            st.markdown(f"""
            <div class="news-card">
              <span class="source-badge {badge_cls}">{badge_lbl}</span>
              <div class="title"><a href="{row['link']}" target="_blank">{row['title']}</a></div>
              <div class="meta">{date_str}{query_str}</div>
              {f'<div style="margin-top:0.5rem">{kw_tags}</div>' if kw_tags else ''}
            </div>
            """, unsafe_allow_html=True)

    with tab1:
        st.markdown(f'<div class="section-title">전체 뉴스 ({len(df)}건)</div>', unsafe_allow_html=True)
        render_news(df)

    with tab2:
        st.markdown(f'<div class="section-title">재개발·재건축 ({len(redev_df)}건)</div>', unsafe_allow_html=True)
        render_news(redev_df)

    with tab3:
        st.markdown(f'<div class="section-title">신규 수주 ({len(order_df)}건)</div>', unsafe_allow_html=True)
        render_news(order_df)

    with tab4:
        st.markdown(f'<div class="section-title">분양·주택사업 ({len(housing_df)}건)</div>', unsafe_allow_html=True)
        render_news(housing_df)

    # ── CSV 다운로드 ──────────────────────────────────────────────────────────
    st.markdown("---")
    csv = df[["source","title","date","query","link"]].to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "📥 CSV로 다운로드",
        data=csv,
        file_name=f"construction_news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
