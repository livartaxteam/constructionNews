import streamlit as st
import feedparser
import pandas as pd
from datetime import datetime, timedelta, date
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

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 1.6rem 2rem; border-radius: 16px;
    margin-bottom: 1.2rem; color: white;
    position: relative; overflow: hidden;
}
.main-header::before {
    content: "🏗️"; position: absolute; right: 2rem; top: 50%;
    transform: translateY(-50%); font-size: 5rem; opacity: 0.12;
}
.main-header h1 { margin: 0; font-size: 1.55rem; font-weight: 700; letter-spacing: -0.5px; }
.main-header p  { margin: 0.35rem 0 0; opacity: 0.72; font-size: 0.85rem; }

.news-card {
    background: white; border: 1px solid #e8ecf0;
    border-radius: 12px; padding: 1.1rem 1.3rem;
    margin-bottom: 0.8rem; transition: box-shadow .2s, border-color .2s;
}
.news-card:hover { box-shadow: 0 4px 18px rgba(0,0,0,.07); border-color: #c0ccd8; }
.source-badge {
    display: inline-block; font-size: 0.68rem; font-weight: 700;
    padding: 2px 8px; border-radius: 20px; margin-bottom: 0.45rem;
}
.badge-naver  { background: #03c75a22; color: #03c75a; }
.badge-google { background: #4285f422; color: #4285f4; }
.news-title { font-size: 0.93rem; font-weight: 600; color: #1a1a2e; margin-bottom: 0.25rem; line-height: 1.45; }
.news-title a { text-decoration: none; color: inherit; }
.news-title a:hover { color: #0f3460; text-decoration: underline; }
.news-meta { font-size: 0.76rem; color: #8a96a3; }
.kw-tag {
    display: inline-block; background: #f0f4ff; color: #4a6fa5;
    border-radius: 5px; padding: 1px 7px;
    font-size: 0.7rem; font-weight: 500; margin-right: 4px;
}
.stat-box {
    background: #f7f9fc; border: 1px solid #e4e9f0;
    border-radius: 10px; padding: 0.9rem; text-align: center;
}
.stat-box .num   { font-size: 1.7rem; font-weight: 700; color: #0f3460; }
.stat-box .label { font-size: 0.72rem; color: #6b7a8d; margin-top: 2px; }
.section-title {
    font-size: 0.95rem; font-weight: 700; color: #1a1a2e;
    border-left: 4px solid #0f3460; padding-left: 0.65rem; margin: 1rem 0 0.7rem;
}
.company-tag {
    display: inline-block; background: #e8f0ff; color: #2c4a8a;
    border-radius: 20px; padding: 3px 11px;
    font-size: 0.75rem; font-weight: 500; margin: 2px;
}
div[data-testid="stSidebar"] { background: #f7f9fc; }
</style>
""", unsafe_allow_html=True)

# ── 상수 ────────────────────────────────────────────────────────────────────
DEFAULT_COMPANIES = [
    "삼성물산", "현대건설", "대우건설", "GS건설", "포스코이앤씨",
    "롯데건설", "HDC현대산업개발", "SK에코플랜트", "DL이앤씨", "호반건설",
]
KEYWORDS_REDEV   = ["재개발", "재건축", "정비사업", "뉴타운", "도시정비"]
KEYWORDS_ORDER   = ["수주", "신규공사", "공사계약", "낙찰", "착공", "시공권"]
KEYWORDS_HOUSING = ["분양", "아파트", "주택사업", "공동주택", "단지"]

# ── 세션 상태 초기화 ─────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "last_run" not in st.session_state:
    st.session_state.last_run = None
if "company_pool" not in st.session_state:
    st.session_state.company_pool = DEFAULT_COMPANIES.copy()
if "selected_companies" not in st.session_state:
    st.session_state.selected_companies = DEFAULT_COMPANIES[:5].copy()

# ── 유틸 ────────────────────────────────────────────────────────────────────
def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()

def highlight_keywords(text: str, keywords: list) -> list:
    return [kw for kw in keywords if kw in text]

def parse_pub_date(entry) -> datetime:
    pp = entry.get("published_parsed")
    if pp:
        try:
            return datetime(*pp[:6])
        except Exception:
            pass
    return None

def fmt_date(dt) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y.%m.%d %H:%M")

def get_date_range(period: str, custom_start=None, custom_end=None):
    now = datetime.now()
    if period == "하루":
        return now - timedelta(days=1), now
    elif period == "일주일":
        return now - timedelta(days=7), now
    elif period == "한달":
        return now - timedelta(days=30), now
    elif period == "직접 입력" and custom_start and custom_end:
        return (
            datetime.combine(custom_start, datetime.min.time()),
            datetime.combine(custom_end,   datetime.max.time()),
        )
    return None, None

# ── 네이버 뉴스 수집 ─────────────────────────────────────────────────────────
def fetch_naver_news(query: str, display: int = 20,
                     date_from=None, date_to=None) -> list:
    import os
    results  = []
    encoded  = urllib.parse.quote(query)
    cid      = os.environ.get("NAVER_CLIENT_ID", "")
    csecret  = os.environ.get("NAVER_CLIENT_SECRET", "")

    # ① 네이버 Open API (API 키 있을 때)
    if cid and csecret:
        try:
            import requests as req
            url = (
                f"https://openapi.naver.com/v1/search/news.json"
                f"?query={encoded}&display={display}&sort=date"
            )
            resp = req.get(
                url,
                headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csecret},
                timeout=8,
            )
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    title = clean_html(item.get("title", ""))
                    desc  = clean_html(item.get("description", ""))
                    link  = item.get("originallink") or item.get("link", "")
                    try:
                        dt = datetime.strptime(
                            item.get("pubDate", ""), "%a, %d %b %Y %H:%M:%S %z"
                        ).replace(tzinfo=None)
                    except Exception:
                        dt = None
                    if date_from and date_to and dt and not (date_from <= dt <= date_to):
                        continue
                    found = highlight_keywords(title + desc, KEYWORDS_REDEV + KEYWORDS_ORDER + KEYWORDS_HOUSING)
                    results.append({
                        "source": "naver", "title": title,
                        "desc": (desc[:150] + "…") if len(desc) > 150 else desc,
                        "link": link, "date": fmt_date(dt),
                        "dt": dt, "keywords": found, "query": query,
                    })
                return results
        except Exception:
            pass

    # ② 네이버 모바일 검색 스크래핑 (fallback)
    try:
        import requests as req
        from bs4 import BeautifulSoup
        url = (
            f"https://m.search.naver.com/search.naver"
            f"?where=m_news&query={encoded}&sort=1&nso=so:dd,p:all"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            )
        }
        resp = req.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        for item in (soup.select("div.news_wrap") or soup.select("li.bx"))[:display]:
            a_tag = item.select_one("a.news_tit") or item.select_one("a[href]")
            if not a_tag:
                continue
            title   = a_tag.get_text(strip=True)
            link    = a_tag.get("href", "")
            desc_el = item.select_one("div.news_dsc") or item.select_one("div.dsc_wrap")
            desc    = desc_el.get_text(strip=True) if desc_el else ""
            time_el = item.select_one("span.info") or item.select_one("span.t11")
            pub_str = time_el.get_text(strip=True) if time_el else ""
            found   = highlight_keywords(title + desc, KEYWORDS_REDEV + KEYWORDS_ORDER + KEYWORDS_HOUSING)
            results.append({
                "source": "naver", "title": title,
                "desc": (desc[:150] + "…") if len(desc) > 150 else desc,
                "link": link, "date": pub_str,
                "dt": None, "keywords": found, "query": query,
            })
    except Exception:
        pass

    return results

# ── 구글 뉴스 수집 ────────────────────────────────────────────────────────────
def fetch_google_news(query: str, num: int = 15,
                      date_from=None, date_to=None) -> list:
    results = []
    period_param = ""
    if date_from and date_to:
        delta = (date_to - date_from).days
        if delta <= 1:
            period_param = "&tbs=qdr:d"
        elif delta <= 7:
            period_param = "&tbs=qdr:w"
        elif delta <= 31:
            period_param = "&tbs=qdr:m"

    encoded = urllib.parse.quote(query)
    rss_url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded}&hl=ko&gl=KR&ceid=KR:ko{period_param}"
    )
    feed = feedparser.parse(rss_url)
    for entry in feed.entries[:num]:
        title = clean_html(entry.get("title", ""))
        desc  = clean_html(entry.get("description", entry.get("summary", "")))
        link  = entry.get("link", "")
        dt    = parse_pub_date(entry)
        if date_from and date_to and dt and not (date_from <= dt <= date_to):
            continue
        found = highlight_keywords(title + desc, KEYWORDS_REDEV + KEYWORDS_ORDER + KEYWORDS_HOUSING)
        results.append({
            "source": "google", "title": title,
            "desc": (desc[:150] + "…") if len(desc) > 150 else desc,
            "link": link, "date": fmt_date(dt),
            "dt": dt, "keywords": found, "query": query,
        })
    return results

# ── 전체 수집 ────────────────────────────────────────────────────────────────
def collect_all_news(companies, extra_kw, per_query, date_from=None, date_to=None):
    all_news = []
    total    = max(len(companies) + len(extra_kw), 1)
    progress = st.progress(0, text="뉴스 수집 중…")

    for i, company in enumerate(companies):
        q = f"{company} 수주 OR 재개발 OR 재건축 OR 분양"
        all_news += fetch_naver_news(q, per_query, date_from, date_to)
        all_news += fetch_google_news(company, per_query, date_from, date_to)
        time.sleep(0.25)
        progress.progress((i + 1) / total, text=f"수집 중: {company}")

    for i, kw in enumerate(extra_kw):
        all_news += fetch_naver_news(kw, per_query, date_from, date_to)
        all_news += fetch_google_news(kw, per_query, date_from, date_to)
        time.sleep(0.25)
        progress.progress((len(companies) + i + 1) / total, text=f"수집 중: {kw}")

    progress.empty()
    if not all_news:
        return pd.DataFrame()

    df = pd.DataFrame(all_news)
    df = df.drop_duplicates(subset=["title"])
    df["kw_count"] = df["keywords"].apply(len)
    df = df.sort_values("kw_count", ascending=False).reset_index(drop=True)
    return df

# ════════════════════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ 검색 설정")

    # ── 선정 건설사 ──────────────────────────────────────────────────────────
    st.markdown("#### 🏢 선정 건설사")
    selected_companies = st.multiselect(
        "건설사를 선택하세요",
        options=st.session_state.company_pool,
        default=[c for c in st.session_state.selected_companies
                 if c in st.session_state.company_pool],
        key="multiselect_companies",
    )
    st.session_state.selected_companies = selected_companies

    if selected_companies:
        tags_html = "".join(
            f'<span class="company-tag">{c}</span>' for c in selected_companies
        )
        st.markdown(f'<div style="margin:4px 0 8px">{tags_html}</div>', unsafe_allow_html=True)

    # 건설사 직접 추가
    st.markdown("**➕ 건설사 직접 추가**")
    new_company = st.text_input(
        "건설사명 입력 후 엔터",
        placeholder="예: 태영건설",
        key="new_company_input",
        label_visibility="collapsed",
    )
    if new_company:
        name = new_company.strip()
        if name and name not in st.session_state.company_pool:
            st.session_state.company_pool.append(name)
        if name and name not in st.session_state.selected_companies:
            st.session_state.selected_companies.append(name)
        st.rerun()

    st.markdown("---")

    # ── 추가 키워드 ──────────────────────────────────────────────────────────
    st.markdown("#### 🔍 추가 키워드")
    extra_kw_input = st.text_input(
        "쉼표(,)로 구분",
        value="재개발 수주, 재건축 착공, 정비사업 낙찰",
        placeholder="예: 재개발 수주, 착공, 낙찰",
    )
    extra_keywords = [k.strip() for k in extra_kw_input.split(",") if k.strip()]

    st.markdown("---")

    # ── 수집 기간 ────────────────────────────────────────────────────────────
    st.markdown("#### 📅 수집 기간")
    period = st.radio(
        "기간",
        ["하루", "일주일", "한달", "직접 입력", "전체"],
        index=1,
        label_visibility="collapsed",
    )
    custom_start = custom_end = None
    if period == "직접 입력":
        col_s, col_e = st.columns(2)
        with col_s:
            custom_start = st.date_input("시작일", value=date.today() - timedelta(days=7))
        with col_e:
            custom_end   = st.date_input("종료일", value=date.today())

    st.markdown("---")
    per_query  = st.slider("쿼리당 뉴스 수", 5, 30, 15)
    search_btn = st.button("🔎 뉴스 수집 시작", use_container_width=True, type="primary")

# ════════════════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="main-header">
  <h1>🏗️ 건설 수주 · 재개발 뉴스 트래커</h1>
  <p>건설사별 신규 수주 · 재개발 · 재건축 · 분양 뉴스를 네이버·구글에서 실시간 수집합니다</p>
</div>
""", unsafe_allow_html=True)

if search_btn:
    if not selected_companies and not extra_keywords:
        st.warning("건설사 또는 키워드를 1개 이상 선택해 주세요.")
    else:
        date_from, date_to = get_date_range(period, custom_start, custom_end)
        with st.spinner("뉴스를 수집하고 있습니다…"):
            df = collect_all_news(
                selected_companies, extra_keywords, per_query, date_from, date_to
            )
            st.session_state.df = df
            st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

df = st.session_state.df

if df.empty:
    if st.session_state.last_run:
        st.info("선택 조건에 맞는 뉴스가 없습니다. 기간을 늘리거나 키워드를 바꿔보세요.")
    else:
        st.info("👆 왼쪽 사이드바에서 건설사와 키워드를 설정한 후 **뉴스 수집 시작** 버튼을 눌러주세요.")
        st.markdown("""
#### 이런 뉴스를 찾아드립니다
- 🏚️ **재개발·재건축** — 정비구역 지정, 시공사 선정, 조합원 모집 등
- 📋 **신규 수주** — 공사 낙찰, 계약 체결, 착공 소식
- 🏠 **분양·주택사업** — 아파트 분양, 공동주택 인허가, 단지 개발
        """)
else:
    redev_df   = df[df["keywords"].apply(lambda x: any(k in x for k in KEYWORDS_REDEV))]
    order_df   = df[df["keywords"].apply(lambda x: any(k in x for k in KEYWORDS_ORDER))]
    housing_df = df[df["keywords"].apply(lambda x: any(k in x for k in KEYWORDS_HOUSING))]

    c1, c2, c3, c4 = st.columns(4)
    for col, num, label in [
        (c1, len(df),         "총 수집 뉴스"),
        (c2, len(redev_df),   "🏚️ 재개발·재건축"),
        (c3, len(order_df),   "📋 신규 수주"),
        (c4, len(housing_df), "🏠 분양·주택사업"),
    ]:
        with col:
            st.markdown(
                f'<div class="stat-box"><div class="num">{num}</div>'
                f'<div class="label">{label}</div></div>',
                unsafe_allow_html=True,
            )

    if st.session_state.last_run:
        st.caption(f"🕐 마지막 수집: {st.session_state.last_run}  |  기간: {period}")

    st.markdown("---")

    def render_news(dataframe: pd.DataFrame):
        if dataframe.empty:
            st.info("해당 카테고리의 뉴스가 없습니다.")
            return
        for _, row in dataframe.iterrows():
            badge_cls = "badge-naver" if row["source"] == "naver" else "badge-google"
            badge_lbl = "네이버 뉴스" if row["source"] == "naver" else "Google 뉴스"
            kw_tags   = "".join(
                f'<span class="kw-tag">{k}</span>' for k in row["keywords"]
            ) if row["keywords"] else ""
            date_str  = f" · {row['date']}" if row["date"] else ""
            query_str = f" · 검색어: {row['query']}" if row.get("query") else ""
            st.markdown(f"""
<div class="news-card">
  <span class="source-badge {badge_cls}">{badge_lbl}</span>
  <div class="news-title"><a href="{row['link']}" target="_blank">{row['title']}</a></div>
  <div class="news-meta">{date_str}{query_str}</div>
  {f'<div style="margin-top:0.45rem">{kw_tags}</div>' if kw_tags else ''}
</div>
""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        f"전체 ({len(df)})",
        f"🏚️ 재개발·재건축 ({len(redev_df)})",
        f"📋 신규 수주 ({len(order_df)})",
        f"🏠 분양·주택 ({len(housing_df)})",
    ])
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

    st.markdown("---")
    csv = df[["source", "title", "date", "query", "link"]].to_csv(
        index=False, encoding="utf-8-sig"
    )
    st.download_button(
        "📥 CSV로 다운로드",
        data=csv,
        file_name=f"construction_news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
