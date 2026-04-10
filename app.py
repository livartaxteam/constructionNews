import streamlit as st
import feedparser
import pandas as pd
import json
import os
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

/* multiselect 드롭다운 높이 제한 → 스크롤 박스처럼 동작 */
div[data-testid="stSidebar"] div[data-baseweb="select"] > div:first-child {
    max-height: 180px;
    overflow-y: auto;
    flex-wrap: wrap;
}
div[data-testid="stSidebar"] div[data-baseweb="select"] > div:first-child::-webkit-scrollbar { width: 4px; }
div[data-testid="stSidebar"] div[data-baseweb="select"] > div:first-child::-webkit-scrollbar-thumb {
    background: #c0ccd8; border-radius: 4px;
}
/* 선택된 태그 스타일 */
div[data-testid="stSidebar"] span[data-baseweb="tag"] {
    background-color: #0f3460 !important;
    border-radius: 20px !important;
}
div[data-testid="stSidebar"] span[data-baseweb="tag"] span {
    color: white !important;
    font-size: 0.72rem !important;
}

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
.badge-google { background: #4285f422; color: #4285f4; }
.badge-trend  { background: #ff6b3522; color: #ff6b35; }
.news-title { font-size: 0.93rem; font-weight: 600; color: #1a1a2e; margin-bottom: 0.25rem; line-height: 1.45; }
.news-title a { text-decoration: none; color: inherit; }
.news-title a:hover { color: #0f3460; text-decoration: underline; }
.news-meta { font-size: 0.76rem; color: #8a96a3; }
.kw-tag {
    display: inline-block; background: #f0f4ff; color: #4a6fa5;
    border-radius: 5px; padding: 1px 7px;
    font-size: 0.7rem; font-weight: 500; margin-right: 4px;
}
.trend-tag {
    display: inline-block; background: #fff3ee; color: #c94a1a;
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
.trend-section-title {
    font-size: 0.95rem; font-weight: 700; color: #1a1a2e;
    border-left: 4px solid #ff6b35; padding-left: 0.65rem; margin: 1rem 0 0.7rem;
}
.trend-card {
    background: #fffaf7; border: 1px solid #ffdccc;
    border-radius: 12px; padding: 1.1rem 1.3rem;
    margin-bottom: 0.8rem; transition: box-shadow .2s, border-color .2s;
}
.trend-card:hover { box-shadow: 0 4px 18px rgba(255,107,53,.08); border-color: #ffb99a; }
.trend-source {
    font-size: 0.68rem; font-weight: 700;
    padding: 2px 8px; border-radius: 20px; margin-bottom: 0.45rem;
    display: inline-block; background: #ff6b3522; color: #c94a1a;
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

# 트렌드 키워드 (구글 뉴스 RSS 검색용)
TREND_QUERIES = [
    ("주방 인테리어 트렌드 2025",      "주방"),
    ("붙박이장 트렌드 디자인",          "붙박이장"),
    ("kitchen design trend 2025",       "해외 주방"),
    ("built-in wardrobe design trend",  "해외 붙박이장"),
    ("bathroom interior trend 2025",    "욕실"),
    ("아파트 인테리어 트렌드",          "아파트 인테리어"),
    ("home interior design trend 2025", "해외 홈인테리어"),
    ("modular kitchen cabinet trend",   "해외 모듈주방"),
]

SAVE_FILE = "companies.json"

# ── 건설사 저장/로드 ─────────────────────────────────────────────────────────
def load_companies() -> dict:
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for c in DEFAULT_COMPANIES:
                if c not in data["pool"]:
                    data["pool"].append(c)
            return data
        except Exception:
            pass
    return {"pool": DEFAULT_COMPANIES.copy(), "selected": DEFAULT_COMPANIES[:5].copy()}

def save_companies(pool: list, selected: list):
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump({"pool": pool, "selected": selected}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ── 세션 상태 초기화 ─────────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    data = load_companies()
    st.session_state.company_pool     = data["pool"]
    st.session_state.company_selected = data["selected"]
    st.session_state.df               = pd.DataFrame()
    st.session_state.trend_df         = pd.DataFrame()
    st.session_state.last_run         = None
    st.session_state.initialized      = True

# ── 유틸 ────────────────────────────────────────────────────────────────────
def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()

def highlight_keywords(text: str, keywords: list) -> list:
    return [kw for kw in keywords if kw in text]

def parse_pub_date(entry):
    pp = entry.get("published_parsed")
    if pp:
        try:
            return datetime(*pp[:6])
        except Exception:
            pass
    return None

def fmt_date(dt) -> str:
    return dt.strftime("%Y.%m.%d %H:%M") if dt else ""

def get_date_range(period, custom_start=None, custom_end=None):
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

# ── 구글 뉴스 수집 ────────────────────────────────────────────────────────────
def fetch_google_news(query: str, num: int = 15, date_from=None, date_to=None) -> list:
    results = []
    period_param = ""
    if date_from and date_to:
        delta = (date_to - date_from).days
        if delta <= 1:    period_param = "&tbs=qdr:d"
        elif delta <= 7:  period_param = "&tbs=qdr:w"
        elif delta <= 31: period_param = "&tbs=qdr:m"

    encoded = urllib.parse.quote(query)
    feed    = feedparser.parse(
        f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko{period_param}"
    )
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
            "keywords": found, "query": query,
        })
    return results

# ── 트렌드 뉴스 수집 ─────────────────────────────────────────────────────────
TREND_KEYWORDS = [
    "주방", "키친", "붙박이장", "워크인", "욕실", "타일", "마감재",
    "kitchen", "wardrobe", "interior", "design", "trend", "cabinet",
    "인테리어", "디자인", "트렌드", "색상", "소재",
]

def fetch_trend_news(query: str, category: str, num: int = 8) -> list:
    """트렌드 RSS 수집 (영문 쿼리는 영문 Google News)"""
    results = []
    is_eng  = any(ord(c) < 128 for c in query if c.isalpha())
    hl      = "en" if is_eng else "ko"
    gl      = "US" if is_eng else "KR"
    ceid    = f"{gl}:{hl}"

    encoded = urllib.parse.quote(query)
    feed    = feedparser.parse(
        f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid={ceid}"
    )
    for entry in feed.entries[:num]:
        title = clean_html(entry.get("title", ""))
        desc  = clean_html(entry.get("description", entry.get("summary", "")))
        link  = entry.get("link", "")
        dt    = parse_pub_date(entry)
        found = highlight_keywords((title + desc).lower(), [k.lower() for k in TREND_KEYWORDS])
        results.append({
            "title": title,
            "desc": (desc[:180] + "…") if len(desc) > 180 else desc,
            "link": link,
            "date": fmt_date(dt),
            "category": category,
            "keywords": found[:5],
            "query": query,
        })
    return results

def collect_trend_news() -> pd.DataFrame:
    all_trend = []
    prog = st.progress(0, text="트렌드 수집 중…")
    total = len(TREND_QUERIES)
    for i, (q, cat) in enumerate(TREND_QUERIES):
        all_trend += fetch_trend_news(q, cat, num=6)
        time.sleep(0.2)
        prog.progress((i + 1) / total, text=f"트렌드 수집: {cat}")
    prog.empty()
    if not all_trend:
        return pd.DataFrame()
    df = pd.DataFrame(all_trend).drop_duplicates(subset=["title"])
    return df.reset_index(drop=True)

# ── 전체 수주/재개발 뉴스 수집 ───────────────────────────────────────────────
def collect_all_news(companies, extra_kw, per_query, date_from=None, date_to=None):
    all_news = []
    total    = max(len(companies) + len(extra_kw), 1)
    progress = st.progress(0, text="뉴스 수집 중…")

    for i, company in enumerate(companies):
        q = f"{company} 수주 OR 재개발 OR 재건축 OR 분양"
        all_news += fetch_google_news(q, per_query, date_from, date_to)
        time.sleep(0.2)
        progress.progress((i + 1) / total, text=f"수집 중: {company}")

    for i, kw in enumerate(extra_kw):
        all_news += fetch_google_news(kw, per_query, date_from, date_to)
        time.sleep(0.2)
        progress.progress((len(companies) + i + 1) / total, text=f"수집 중: {kw}")

    progress.empty()
    if not all_news:
        return pd.DataFrame()

    df = pd.DataFrame(all_news).drop_duplicates(subset=["title"])
    df["kw_count"] = df["keywords"].apply(len)
    df = df.sort_values("kw_count", ascending=False).reset_index(drop=True)
    return df


# ════════════════════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ 검색 설정")

    # ── 선정 건설사 (multiselect 스크롤 옵션박스) ───────────────────────────
    st.markdown("#### 🏢 선정 건설사")

    # multiselect: 선택된 값이 바뀔 때마다 세션+파일에 저장
    selected_now = st.multiselect(
        "건설사 선택 (스크롤하여 모두 확인)",
        options=st.session_state.company_pool,
        default=[c for c in st.session_state.company_selected
                 if c in st.session_state.company_pool],
        key="ms_companies",
        label_visibility="collapsed",
    )
    # 변경 감지 후 저장
    if selected_now != st.session_state.company_selected:
        st.session_state.company_selected = selected_now
        save_companies(st.session_state.company_pool, st.session_state.company_selected)

    # 건설사 직접 추가
    st.markdown("**➕ 건설사 직접 추가**")
    with st.form("add_company_form", clear_on_submit=True):
        new_company = st.text_input(
            "건설사명",
            placeholder="예: 태영건설",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("추가하기", use_container_width=True)
        if submitted and new_company.strip():
            name = new_company.strip()
            if name not in st.session_state.company_pool:
                st.session_state.company_pool.append(name)
            if name not in st.session_state.company_selected:
                st.session_state.company_selected.append(name)
            save_companies(st.session_state.company_pool, st.session_state.company_selected)
            st.success(f"✅ '{name}' 추가 완료!")
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

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        search_btn = st.button("🔎 뉴스 수집", use_container_width=True, type="primary")
    with col_btn2:
        trend_btn  = st.button("✨ 트렌드 수집", use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="main-header">
  <h1>🏗️ 건설 수주 · 재개발 뉴스 트래커</h1>
  <p>건설사별 신규 수주 · 재개발 · 재건축 · 분양 뉴스 + 건설 인테리어 트렌드를 한 곳에서</p>
</div>
""", unsafe_allow_html=True)

# 선정 건설사 태그 표시
selected = st.session_state.get("ms_companies", st.session_state.company_selected)
if selected:
    tags = "".join(
        f'<span style="display:inline-block;background:#0f3460;color:white;'
        f'border-radius:20px;padding:4px 13px;font-size:0.78rem;'
        f'font-weight:500;margin:3px;">{c}</span>'
        for c in selected
    )
    st.markdown(
        f'<div style="margin-bottom:1rem">'
        f'<b style="font-size:0.85rem;color:#444">선정 건설사</b><br>'
        f'<div style="margin-top:6px">{tags}</div></div>',
        unsafe_allow_html=True,
    )
else:
    st.warning("왼쪽 사이드바에서 건설사를 1개 이상 선택해 주세요.")

# ── 수주/재개발 뉴스 수집 ────────────────────────────────────────────────────
if search_btn:
    if not selected and not extra_keywords:
        st.warning("건설사 또는 키워드를 1개 이상 선택해 주세요.")
    else:
        date_from, date_to = get_date_range(period, custom_start, custom_end)
        with st.spinner("뉴스를 수집하고 있습니다…"):
            df = collect_all_news(selected, extra_keywords, per_query, date_from, date_to)
            st.session_state.df       = df
            st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── 트렌드 수집 ──────────────────────────────────────────────────────────────
if trend_btn:
    with st.spinner("인테리어 트렌드를 수집하고 있습니다…"):
        tdf = collect_trend_news()
        st.session_state.trend_df = tdf

# ── 탭 구성 ──────────────────────────────────────────────────────────────────
main_tab, trend_tab = st.tabs(["📋 수주 · 재개발 뉴스", "✨ 건설 인테리어 트렌드"])

# ════════════ 수주/재개발 탭 ════════════
with main_tab:
    df = st.session_state.df
    if df.empty:
        if st.session_state.last_run:
            st.info("선택 조건에 맞는 뉴스가 없습니다. 기간을 늘리거나 키워드를 바꿔보세요.")
        else:
            st.info("👆 사이드바에서 설정 후 **🔎 뉴스 수집** 버튼을 눌러주세요.")
            st.markdown("""
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
                kw_tags   = "".join(
                    f'<span class="kw-tag">{k}</span>' for k in row["keywords"]
                ) if row["keywords"] else ""
                date_str  = f" · {row['date']}" if row["date"] else ""
                query_str = f" · 검색어: {row['query']}" if row.get("query") else ""
                st.markdown(f"""
<div class="news-card">
  <span class="source-badge badge-google">Google 뉴스</span>
  <div class="news-title"><a href="{row['link']}" target="_blank">{row['title']}</a></div>
  <div class="news-meta">{date_str}{query_str}</div>
  {f'<div style="margin-top:0.45rem">{kw_tags}</div>' if kw_tags else ''}
</div>
""", unsafe_allow_html=True)

        t1, t2, t3, t4 = st.tabs([
            f"전체 ({len(df)})",
            f"🏚️ 재개발·재건축 ({len(redev_df)})",
            f"📋 신규 수주 ({len(order_df)})",
            f"🏠 분양·주택 ({len(housing_df)})",
        ])
        with t1:
            st.markdown(f'<div class="section-title">전체 ({len(df)}건)</div>', unsafe_allow_html=True)
            render_news(df)
        with t2:
            st.markdown(f'<div class="section-title">재개발·재건축 ({len(redev_df)}건)</div>', unsafe_allow_html=True)
            render_news(redev_df)
        with t3:
            st.markdown(f'<div class="section-title">신규 수주 ({len(order_df)}건)</div>', unsafe_allow_html=True)
            render_news(order_df)
        with t4:
            st.markdown(f'<div class="section-title">분양·주택사업 ({len(housing_df)}건)</div>', unsafe_allow_html=True)
            render_news(housing_df)

        st.markdown("---")
        csv = df[["source", "title", "date", "query", "link"]].to_csv(
            index=False, encoding="utf-8-sig"
        )
        st.download_button(
            "📥 CSV 다운로드",
            data=csv,
            file_name=f"construction_news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

# ════════════ 트렌드 탭 ════════════
with trend_tab:
    tdf = st.session_state.trend_df
    if tdf.empty:
        st.info("👆 사이드바의 **✨ 트렌드 수집** 버튼을 눌러주세요.")
        st.markdown("""
#### 수집하는 트렌드 카테고리
| 카테고리 | 검색 소스 |
|---------|----------|
| 🍳 주방 인테리어 트렌드 | Google 뉴스 (국내) |
| 🚪 붙박이장 · 워크인클로젯 | Google 뉴스 (국내) |
| 🛁 욕실 트렌드 | Google 뉴스 (국내) |
| 🌍 해외 주방 디자인 | Google News (영문) |
| 🌍 해외 붙박이장 디자인 | Google News (영문) |
| 🌍 해외 홈인테리어 트렌드 | Google News (영문) |
| 🏠 아파트 인테리어 트렌드 | Google 뉴스 (국내) |
| 🔧 모듈형 주방 캐비닛 | Google News (영문) |
        """)
    else:
        # 카테고리별 탭
        categories = tdf["category"].unique().tolist()
        cat_tabs   = st.tabs(["전체"] + categories)

        def render_trend(dataframe: pd.DataFrame):
            if dataframe.empty:
                st.info("해당 카테고리의 트렌드 정보가 없습니다.")
                return
            for _, row in dataframe.iterrows():
                kw_tags = "".join(
                    f'<span class="trend-tag">{k}</span>' for k in (row.get("keywords") or [])
                )
                date_str = f" · {row['date']}" if row["date"] else ""
                st.markdown(f"""
<div class="trend-card">
  <span class="trend-source">✨ {row['category']}</span>
  <div class="news-title"><a href="{row['link']}" target="_blank">{row['title']}</a></div>
  <div class="news-meta">{date_str}</div>
  {f'<div style="margin-top:0.45rem">{kw_tags}</div>' if kw_tags else ''}
</div>
""", unsafe_allow_html=True)

        with cat_tabs[0]:
            st.markdown(f'<div class="trend-section-title">전체 트렌드 ({len(tdf)}건)</div>', unsafe_allow_html=True)
            render_trend(tdf)

        for i, cat in enumerate(categories):
            cat_df = tdf[tdf["category"] == cat]
            with cat_tabs[i + 1]:
                st.markdown(f'<div class="trend-section-title">{cat} ({len(cat_df)}건)</div>', unsafe_allow_html=True)
                render_trend(cat_df)

        st.markdown("---")
        tcsv = tdf[["category", "title", "date", "link"]].to_csv(
            index=False, encoding="utf-8-sig"
        )
        st.download_button(
            "📥 트렌드 CSV 다운로드",
            data=tcsv,
            file_name=f"trend_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
