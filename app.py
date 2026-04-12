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
div[data-testid="stSidebar"] { background: #f7f9fc; }
.scroll-container {
    max-height: 150px;
    overflow-y: auto;
    border: 1px solid #e6e9ef;
    border-radius: 5px;
    padding: 10px;
    background-color: white;
    margin-bottom: 10px;
}
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

SAVE_FILE = "companies.json"

# ── 건설사 저장/로드 ────────────────────────────────────────────────────────
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
    return {
        "pool": DEFAULT_COMPANIES.copy(),
        "selected": DEFAULT_COMPANIES[:5].copy(),
    }

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

# ── 구글 뉴스 수집 (네이버 제외) ─────────────────────────────────────────────
def fetch_google_news(query: str, num: int = 15, date_from=None, date_to=None) -> list:
    results = []
    period_param = ""
    if date_from and date_to:
        delta = (date_to - date_from).days
        if delta <= 1:   period_param = "&tbs=qdr:d"
        elif delta <= 7: period_param = "&tbs=qdr:w"
        elif delta <= 31:period_param = "&tbs=qdr:m"

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

def collect_all_news(companies, extra_kw, per_company_news, date_from=None, date_to=None):
    all_news = []
    total    = max(len(companies) + len(extra_kw), 1)
    progress = st.progress(0, text="뉴스 수집 중…")

    for i, company in enumerate(companies):
        q = f"{company} 수주 OR 재개발 OR 재건축 OR 분양"
        # 구글 뉴스만 수집
        all_news += fetch_google_news(q, per_company_news, date_from, date_to)
        time.sleep(0.2)
        progress.progress((i + 1) / total, text=f"수집 중: {company}")

    for i, kw in enumerate(extra_kw):
        all_news += fetch_google_news(kw, per_company_news, date_from, date_to)
        time.sleep(0.2)
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

    # ── 선정 건설사 (스크롤 가능한 옵션 박스) ─────────────────────────
    st.markdown("#### 🏢 선정 건설사")
    
    st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
    for company in st.session_state.company_pool:
        is_checked = company in st.session_state.company_selected
        checked = st.checkbox(company, value=is_checked, key=f"sidebar_chk_{company}")
        
        if checked and company not in st.session_state.company_selected:
            st.session_state.company_selected.append(company)
            save_companies(st.session_state.company_pool, st.session_state.company_selected)
        elif not checked and company in st.session_state.company_selected:
            st.session_state.company_selected.remove(company)
            save_companies(st.session_state.company_pool, st.session_state.company_selected)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 건설사 직접 추가 ──────────────────────────────────────────────────────
    with st.form("add_company_form", clear_on_submit=True):
        new_company = st.text_input("➕ 건설사 추가", placeholder="예: 쌍용건설")
        if st.form_submit_button("추가", use_container_width=True):
            if new_company.strip():
                name = new_company.strip()
                if name not in st.session_state.company_pool:
                    st.session_state.company_pool.append(name)
                if name not in st.session_state.company_selected:
                    st.session_state.company_selected.append(name)
                save_companies(st.session_state.company_pool, st.session_state.company_selected)
                st.rerun()

    st.markdown("---")

    # ── 추가 키워드 ──────────────────────────────────────────────────────────
    st.markdown("#### 🔍 추가 키워드")
    extra_kw_input = st.text_input("쉼표(,)로 구분", value="재개발 수주, 재건축 착공", placeholder="예: 재개발 수주, 낙찰")
    extra_keywords = [k.strip() for k in extra_kw_input.split(",") if k.strip()]

    st.markdown("---")

    # ── 수집 기간 ────────────────────────────────────────────────────────────
    st.markdown("#### 📅 수집 기간")
    period = st.radio(
        "기간 선택",
        ["하루", "일주일", "한달", "직접 입력"],
        index=1,
        label_visibility="collapsed"
    )
    custom_start = custom_end = None
    if period == "직접 입력":
        col_s, col_e = st.columns(2)
        with col_s: custom_start = st.date_input("시작", value=date.today() - timedelta(days=7))
        with col_e: custom_end = st.date_input("종료", value=date.today())

    st.markdown("---")
    
    # ── 건설사별 뉴스 수 (수정됨) ──────────────────────────────────────────────
    per_company_news = st.slider("건설사별 뉴스 수", 5, 30, 15)
    st.info(f"💡 건설사 1곳 당 최대 {per_company_news}개의 기사를 수집합니다.")
    
    search_btn = st.button("🔎 뉴스 수집 시작", use_container_width=True, type="primary")

# ════════════════════════════════════════════════════════════════════════════
# 메인 화면
# ════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="main-header">
  <h1>🏗️ 건설 수주 · 재개발 뉴스 트래커</h1>
  <p>건설사별 신규 수주 · 재개발 · 재건축 · 분양 뉴스를 실시간으로 수집합니다 (Google News)</p>
</div>
""", unsafe_allow_html=True)

selected = st.session_state.company_selected
if selected:
    tags = "".join(
        f'<span style="display:inline-block;background:#0f3460;color:white;'
        f'border-radius:20px;padding:4px 13px;font-size:0.78rem;'
        f'font-weight:500;margin:3px;">{c}</span>'
        for c in selected
    )
    st.markdown(
        f'<div style="margin-bottom:1rem"><b style="font-size:0.85rem;color:#444">선정 건설사</b><br>'
        f'<div style="margin-top:5px">{tags}</div></div>',
        unsafe_allow_html=True,
    )
else:
    st.warning("👈 왼쪽 사이드바에서 건설사를 1개 이상 선택해 주세요.")

if search_btn:
    if not selected and not extra_keywords:
        st.warning("건설사 또는 키워드를 1개 이상 선택해 주세요.")
    else:
        date_from, date_to = get_date_range(period, custom_start, custom_end)
        with st.spinner("뉴스를 수집하고 있습니다…"):
            df = collect_all_news(selected, extra_keywords, per_company_news, date_from, date_to)
            st.session_state.df       = df
            st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

df = st.session_state.df

if df.empty:
    if st.session_state.last_run:
        st.info("선택 조건에 맞는 뉴스가 없습니다. 기간을 늘리거나 키워드를 바꿔보세요.")
    else:
        st.info("👆 사이드바에서 설정을 마친 후 **뉴스 수집 시작** 버튼을 눌러주세요.")
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
        st.caption(f"🕐 마지막 수집: {st.session_state.last_run}  |  조회 기간: {period}")

    st.markdown("---")

    def render_news(dataframe: pd.DataFrame):
        if dataframe.empty:
            st.info("해당 카테고리의 뉴스가 없습니다.")
            return
        for _, row in dataframe.iterrows():
            badge_cls = "badge-google"
            badge_lbl = "Google 뉴스"
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
    with tab1: render_news(df)
    with tab2: render_news(redev_df)
    with tab3: render_news(order_df)
    with tab4: render_news(housing_df)

    st.markdown("---")
    csv = df[["source", "title", "date", "query", "link"]].to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "📥 CSV로 다운로드",
        data=csv,
        file_name=f"construction_news_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
