import streamlit as st
import datetime
from datetime import timezone, timedelta
from email.utils import parsedate_to_datetime
import feedparser
import requests
import pandas as pd
import urllib.parse
import re
import time
import json
import os

# ---------------------------------------------------------
# 영구 저장
# ---------------------------------------------------------
SAVE_FILE = "settings.json"

DEFAULT_COMPANIES = [
    "삼성물산", "현대건설", "대우건설", "GS건설", "DL이앤씨",
    "현대엔지니어링", "포스코이앤씨", "롯데건설", "SK에코플랜트", "호반건설",
    "HDC현대산업개발", "한화건설", "대방건설", "금호건설", "코오롱글로벌"
]
DEFAULT_KEYWORDS = "재건축 수주, 정비사업 시공사 선정, 아파트 분양, 재개발 사업, 모델하우스"

def load_settings():
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 저장된 목록을 그대로 사용 (DEFAULT 자동 보충 없음)
            return data
        except Exception:
            pass
    return {"companies": DEFAULT_COMPANIES.copy(), "keywords": DEFAULT_KEYWORDS, "chk_states": {}}

def save_settings():
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "companies":  st.session_state.companies,
                "keywords":   st.session_state.saved_keywords,
                "chk_states": st.session_state.chk_states,
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ---------------------------------------------------------
# 스타일 + JS (아이콘 버튼 테두리 제거)
# ---------------------------------------------------------
st.markdown("""
<style>
section[data-testid="stSidebar"] [data-testid="baseButton-primary"] {
    background-color: #e53935 !important;
    color: white !important;
    border: 2px solid #b71c1c !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 6px rgba(229,57,53,0.35) !important;
}
section[data-testid="stSidebar"] [data-testid="baseButton-primary"]:hover {
    background-color: #b71c1c !important;
}
</style>

""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 1. 세션 상태 초기화 (최초 1회)
# ---------------------------------------------------------
if "initialized" not in st.session_state:
    cfg = load_settings()
    st.session_state.companies       = cfg["companies"]
    st.session_state.saved_keywords  = cfg.get("keywords", DEFAULT_KEYWORDS)
    st.session_state.chk_states      = cfg.get("chk_states", {})
    st.session_state.editing_company = None
    st.session_state.chk_ver         = 0   # 전체선택 토글 시 key 버전 증가 → 강제 재렌더링
    st.session_state.initialized     = True

def sync_chk():
    for c in st.session_state.companies:
        if c not in st.session_state.chk_states:
            st.session_state.chk_states[c] = False
    for c in list(st.session_state.chk_states):
        if c not in st.session_state.companies:
            del st.session_state.chk_states[c]

sync_chk()

# query_params로 넘어온 edit / del 액션 처리
_params = st.query_params
if "action" in _params:
    _action = _params.get("action", "")
    _target = _params.get("target", "")
    if _action == "edit" and _target in st.session_state.companies:
        st.session_state.editing_company = _target
    elif _action == "del" and _target in st.session_state.companies:
        st.session_state.companies.remove(_target)
        st.session_state.chk_states.pop(_target, None)
        st.session_state.editing_company = None
        save_settings()
    st.query_params.clear()
    st.rerun()

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
st.sidebar.title("🔍 검색 설정")
start_crawling_top = st.sidebar.button("🚀 뉴스 수집 시작", type="primary", use_container_width=True, key="crawl_top")
st.sidebar.subheader("대상 건설사")
st.sidebar.caption("✏️ 이름 변경  |  🗑️ 삭제")

# ── 전체 선택 / 해제 ──────────────────────────────────────
# 토글 버튼 방식: 누를 때마다 전체선택 ↔ 전체해제 반전
# chk_ver 를 올려서 개별 체크박스 key를 바꿔 강제 재렌더링
all_now = bool(st.session_state.companies) and all(
    st.session_state.chk_states.get(c, False) for c in st.session_state.companies
)
btn_label = "☑️ 전체 해제" if all_now else "🔲 전체 선택"
if st.sidebar.button(btn_label, use_container_width=True, key="select_all_btn"):
    new_val = not all_now
    for c in st.session_state.companies:
        st.session_state.chk_states[c] = new_val
    st.session_state.chk_ver = st.session_state.get("chk_ver", 0) + 1
    save_settings()
    st.rerun()

# ── 건설사 목록 ───────────────────────────────────────────
selected_companies = []
with st.sidebar.container(height=220):
    for comp in list(st.session_state.companies):

        # 편집 모드
        if st.session_state.editing_company == comp:
            new_name = st.text_input(
                "변경", value=comp, key=f"edit_input_{comp}",
                label_visibility="collapsed",
            )
            ca, cb = st.columns(2)
            with ca:
                if st.button("저장", key=f"save_{comp}", use_container_width=True):
                    new_name = new_name.strip()
                    if new_name and new_name != comp:
                        idx = st.session_state.companies.index(comp)
                        st.session_state.companies[idx] = new_name
                        st.session_state.chk_states[new_name] = \
                            st.session_state.chk_states.pop(comp, False)
                    st.session_state.editing_company = None
                    save_settings()
                    st.rerun()
            with cb:
                if st.button("취소", key=f"cancel_{comp}", use_container_width=True):
                    st.session_state.editing_company = None
                    st.rerun()

        # 일반 모드
        else:
            col_chk, col_icons = st.columns([6, 2])
            with col_chk:
                ver = st.session_state.get("chk_ver", 0)
                checked = st.checkbox(
                    comp,
                    value=st.session_state.chk_states.get(comp, False),
                    key=f"chk_{comp}_v{ver}",
                )
                if checked != st.session_state.chk_states.get(comp, False):
                    st.session_state.chk_states[comp] = checked
                    save_settings()
                if checked:
                    selected_companies.append(comp)
            with col_icons:
                # query_params 방식으로 액션 전달 — 버튼 없이 순수 HTML 링크
                enc = urllib.parse.quote(comp)
                st.markdown(
                    f'''<div style="display:flex;gap:8px;padding-top:6px;line-height:1">
                        <a href="?action=edit&target={enc}"
                           style="text-decoration:none;font-size:15px;cursor:pointer"
                           title="{comp} 이름 변경">✏️</a>
                        <a href="?action=del&target={enc}"
                           style="text-decoration:none;font-size:15px;cursor:pointer"
                           title="{comp} 삭제">🗑️</a>
                    </div>''',
                    unsafe_allow_html=True,
                )

# ── 건설사 추가 ───────────────────────────────────────────
with st.sidebar.form("add_form", clear_on_submit=True):
    new_company = st.text_input("새 건설사 추가", placeholder="건설사명 입력")
    if st.form_submit_button("➕ 추가", use_container_width=True):
        name = new_company.strip()
        if name and name not in st.session_state.companies:
            st.session_state.companies.append(name)
            st.session_state.chk_states[name] = True   # 추가 즉시 선택
            save_settings()
            st.rerun()

st.sidebar.divider()

# ── 검색 키워드 (변경 시 자동 저장) ──────────────────────
st.sidebar.subheader("검색 키워드")
keywords_input = st.sidebar.text_area(
    "키워드",
    value=st.session_state.saved_keywords,
    height=100,
    label_visibility="collapsed",
    key="keywords_area",
)
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
if keywords_input != st.session_state.saved_keywords:
    st.session_state.saved_keywords = keywords_input
    save_settings()

st.sidebar.divider()

# ── 수집 기간 ─────────────────────────────────────────────
st.sidebar.subheader("수집 기간")
period_option = st.sidebar.radio(
    "기간", ["하루", "일주일", "한달", "직접입력"], label_visibility="collapsed"
)
start_date = end_date = None
if period_option == "직접입력":
    c1, c2 = st.sidebar.columns(2)
    with c1:
        start_date = st.date_input("시작일", datetime.date.today() - datetime.timedelta(days=7))
    with c2:
        end_date = st.date_input("종료일", datetime.date.today())

st.sidebar.divider()
max_news_count = st.sidebar.number_input("건설사별 최대 뉴스 수", min_value=1, max_value=100, value=10)
debug_mode     = st.sidebar.checkbox("🔧 디버그 모드 (오류 원인 표시)")
st.sidebar.divider()
start_crawling_bot = st.sidebar.button("🚀 뉴스 수집 시작", type="primary", use_container_width=True, key="crawl_bot")

# ---------------------------------------------------------
# 3. 메인 화면
# ---------------------------------------------------------
st.title("🏗️ 건설 수주·재개발 뉴스 트래커")
st.markdown("건설사별 신규 수주, 재개발, 재건축, 분양 뉴스를 실시간으로 수집합니다.")
st.divider()
st.subheader("📌 선정 건설사")
if selected_companies:
    st.info(", ".join(selected_companies))
else:
    st.warning("왼쪽 메뉴에서 건설사를 1개 이상 선택해주세요.")

# ---------------------------------------------------------
# 4. 수집 함수
# ---------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def parse_and_format_date(date_str):
    try:
        dt     = parsedate_to_datetime(date_str)
        kst_tz = timezone(timedelta(hours=9))
        dt_kst = dt.astimezone(kst_tz)
        days   = ['월','화','수','목','금','토','일']
        return dt_kst, f"{dt_kst.strftime('%y.%m.%d')} ({days[dt_kst.weekday()]})"
    except Exception:
        return datetime.datetime.now(timezone(timedelta(hours=9))), date_str

def get_cutoff(period, s=None, e=None):
    kst = timezone(timedelta(hours=9))
    now = datetime.datetime.now(kst)
    if period == "하루":    return now - timedelta(days=1),  now
    if period == "일주일":  return now - timedelta(days=7),  now
    if period == "한달":    return now - timedelta(days=30), now
    if period == "직접입력" and s and e:
        return (
            datetime.datetime.combine(s, datetime.time.min).replace(tzinfo=kst),
            datetime.datetime.combine(e, datetime.time.max).replace(tzinfo=kst),
        )
    return None, None

def extract_nouns(title):
    tokens    = re.findall(r'[가-힣]{2,}|[A-Za-z0-9]{2,}', title)
    stopwords = {'기자','뉴스','에서','으로','하는','있는','있다','했다',
                 '한다','이번','지난','올해','최근','통해','위해','대한'}
    return {t for t in tokens if t not in stopwords}

def is_dup(a, b, thr=0.4):
    sa, sb = extract_nouns(a), extract_nouns(b)
    if not sa or not sb: return False
    return len(sa & sb) / len(sa | sb) >= thr

def deduplicate(df):
    df = df.sort_values("정렬시간", ascending=False)
    df = df.drop_duplicates(subset=["비교키"], keep="first").reset_index(drop=True)
    keep, kept = [], []
    for idx, row in df.iterrows():
        t = row["기사 제목"]
        if not any(is_dup(t, k) for k in kept):
            keep.append(idx); kept.append(t)
    return df.loc[keep].reset_index(drop=True)

def fetch_one(company, keyword, period, max_count, s=None, e=None):
    encoded = urllib.parse.quote(f"{company} {keyword}")
    url     = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    log     = {"url": url, "http_status": None, "entries": 0, "filtered": 0, "error": None}
    dt_from, dt_to = get_cutoff(period, s, e)
    kst = timezone(timedelta(hours=9))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        log["http_status"] = resp.status_code
        if resp.status_code != 200:
            log["error"] = f"HTTP {resp.status_code}"; return [], log
        if not resp.text.strip():
            log["error"] = "빈 응답"; return [], log
        feed = feedparser.parse(resp.text)
        log["entries"] = len(feed.entries)
        if feed.bozo and not feed.entries:
            log["error"] = f"파싱 실패: {feed.bozo_exception}"; return [], log
        results = []
        for entry in feed.entries:
            pub_raw      = entry.get("published", "")
            dt_obj, disp = parse_and_format_date(pub_raw)
            if dt_from and dt_to:
                chk = dt_obj if dt_obj.tzinfo else dt_obj.replace(tzinfo=kst)
                if not (dt_from <= chk <= dt_to):
                    continue
            title = entry.get("title", "제목 없음").rsplit(' - ', 1)[0].strip()
            results.append({
                "건설사": company, "키워드": keyword,
                "기사 제목": title, "게시일": disp, "정렬시간": dt_obj,
                "비교키": re.sub(r'[^가-힣A-Za-z0-9]', '', title),
                "링크": entry.get("link", ""),
            })
            if len(results) >= max_count: break
        log["filtered"] = len(results)
        return results, log
    except requests.exceptions.ConnectionError as ex:
        log["error"] = f"연결 오류: {str(ex)[:120]}"; return [], log
    except requests.exceptions.Timeout:
        log["error"] = "Timeout"; return [], log
    except Exception as ex:
        log["error"] = f"오류: {str(ex)[:120]}"; return [], log

# ---------------------------------------------------------
# 5. 수집 실행
# ---------------------------------------------------------
start_crawling = start_crawling_top or start_crawling_bot
if start_crawling:
    if not selected_companies:
        st.error("선택된 건설사가 없습니다.")
    elif not keywords:
        st.error("키워드를 입력해주세요.")
    else:
        combos    = [(c, k) for c in selected_companies for k in keywords]
        total     = len(combos)
        all_news  = []
        dbg_logs  = []
        st.info(f"총 {total}개 조합 수집 시작… (건설사 {len(selected_companies)}개 × 키워드 {len(keywords)}개)")
        prog   = st.progress(0)
        status = st.empty()
        for i, (comp, kw) in enumerate(combos):
            status.caption(f"수집 중 ({i+1}/{total}): {comp} / {kw}")
            res, log = fetch_one(comp, kw, period_option, max_news_count, start_date, end_date)
            all_news.extend(res)
            dbg_logs.append(log)
            prog.progress((i + 1) / total)
            time.sleep(0.3)
        status.empty()
        st.divider()

        if debug_mode:
            with st.expander("🔧 디버그 로그", expanded=True):
                ok   = [l for l in dbg_logs if l["entries"] > 0]
                fail = [l for l in dbg_logs if l["entries"] == 0]
                st.write(f"✅ 성공: {len(ok)}건  ❌ 실패: {len(fail)}건")
                for l in fail[:20]:
                    st.code(f"URL: {l['url']}\nHTTP: {l['http_status']}  오류: {l['error']}")

        if all_news:
            df     = pd.DataFrame(all_news)
            before = len(df)
            df     = deduplicate(df)
            after  = len(df)
            plabel = period_option if period_option != "직접입력" else f"{start_date} ~ {end_date}"
            st.subheader(f"📊 수집 결과 — {plabel} 기준, 총 {after}건 (유사기사 {before-after}건 제거)")

            tabs = st.tabs(["전체"] + list(df["건설사"].unique()))

            def show_table(data):
                rows = []
                for _, row in data.iterrows():
                    lnk   = row.get("링크", "")
                    title = row["기사 제목"]
                    rows.append({
                        "건설사": row["건설사"], "키워드": row["키워드"],
                        "기사 제목": f'<a href="{lnk}" target="_blank">{title}</a>' if lnk else title,
                        "게시일": row["게시일"],
                    })
                st.write(pd.DataFrame(rows).to_html(escape=False, index=False), unsafe_allow_html=True)

            with tabs[0]: show_table(df)
            for i, comp in enumerate(df["건설사"].unique()):
                with tabs[i + 1]: show_table(df[df["건설사"] == comp])

            st.divider()
            csv = df[["건설사","키워드","기사 제목","게시일","링크"]].to_csv(
                index=False, encoding="utf-8-sig"
            )
            st.download_button(
                "📥 CSV 다운로드", data=csv,
                file_name=f"construction_news_{datetime.date.today()}.csv",
                mime="text/csv",
            )
        else:
            st.warning("수집된 뉴스가 없습니다.")
            if not debug_mode:
                st.info("💡 사이드바 하단 **🔧 디버그 모드**를 켜고 다시 수집하면 원인을 확인할 수 있습니다.")
            else:
                st.error("Google News RSS 연결이 안 됩니다. Manage app → Reboot 후 재시도해주세요.")
