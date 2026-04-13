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

# ---------------------------------------------------------
# 1. 초기 데이터 및 세션 상태
# ---------------------------------------------------------
default_companies = [
    "삼성물산", "현대건설", "대우건설", "디엘이앤씨", "지에스건설",
    "현대엔지니어링", "포스코이앤씨", "롯데건설", "SK에코플랜트", "호반건설",
    "HDC현대산업개발", "한화건설", "대방건설", "금호건설", "코오롱글로벌"
]

if 'companies' not in st.session_state:
    st.session_state.companies = default_companies.copy()

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
st.sidebar.title("🔍 검색 설정")
st.sidebar.subheader("대상 건설사")
st.sidebar.caption("수집할 건설사를 선택하세요 (스크롤 가능)")

selected_companies = []
company_container = st.sidebar.container(height=200)
with company_container:
    for comp in st.session_state.companies:
        if st.checkbox(comp, key=f"chk_{comp}"):
            selected_companies.append(comp)

with st.sidebar.form("add_form", clear_on_submit=True):
    new_company = st.text_input("새 건설사 추가", placeholder="건설사명 입력")
    if st.form_submit_button("추가"):
        if new_company and new_company not in st.session_state.companies:
            st.session_state.companies.append(new_company)
            st.rerun()

st.sidebar.divider()
st.sidebar.subheader("검색 키워드")
keywords_input = st.sidebar.text_area(
    "키워드 (쉼표로 구분)",
    value="재건축 수주, 정비사업 시공사 선정, 아파트 분양, 재개발 사업",
    height=100,
    label_visibility="collapsed",
)
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

st.sidebar.divider()
st.sidebar.subheader("수집 기간")
period_option = st.sidebar.radio(
    "기간", ["하루", "일주일", "한달", "직접입력"], label_visibility="collapsed"
)
start_date, end_date = None, None
if period_option == "직접입력":
    c1, c2 = st.sidebar.columns(2)
    with c1:
        start_date = st.date_input("시작일", datetime.date.today() - datetime.timedelta(days=7))
    with c2:
        end_date = st.date_input("종료일", datetime.date.today())

st.sidebar.divider()
max_news_count = st.sidebar.number_input("건설사별 최대 뉴스 수", min_value=1, max_value=100, value=10)

debug_mode = st.sidebar.checkbox("🔧 디버그 모드 (오류 원인 표시)")

st.sidebar.divider()
start_crawling = st.sidebar.button("🚀 뉴스 수집 시작", type="primary", use_container_width=True)

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
# 4. RSS 수집 함수 (순차 처리 + 상세 디버그)
# ---------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def parse_and_format_date(date_str: str):
    try:
        dt = parsedate_to_datetime(date_str)
        kst_tz = timezone(timedelta(hours=9))
        dt_kst = dt.astimezone(kst_tz)
        weekdays = ['월','화','수','목','금','토','일']
        return dt_kst, f"{dt_kst.strftime('%y.%m.%d')} ({weekdays[dt_kst.weekday()]})"
    except Exception:
        return datetime.datetime.now(timezone(timedelta(hours=9))), date_str

def build_query_url(company: str, keyword: str, period: str,
                    start_date=None, end_date=None) -> str:
    tbs_map = {"하루": "qdr:d", "일주일": "qdr:w", "한달": "qdr:m"}
    query   = f"{company} {keyword}"

    if period == "직접입력" and start_date and end_date:
        query += f" after:{start_date} before:{end_date}"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    else:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        if period in tbs_map:
            url += f"&tbs={tbs_map[period]}"
    return url

def fetch_one(company: str, keyword: str, period: str,
              max_count: int, start_date=None, end_date=None,
              debug: bool = False):
    url = build_query_url(company, keyword, period, start_date, end_date)
    log = {"url": url, "http_status": None, "entries": 0, "error": None}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        log["http_status"] = resp.status_code

        if resp.status_code != 200:
            log["error"] = f"HTTP {resp.status_code}"
            return [], log

        if not resp.text.strip():
            log["error"] = "빈 응답"
            return [], log

        feed = feedparser.parse(resp.text)
        log["entries"] = len(feed.entries)

        if feed.bozo and len(feed.entries) == 0:
            log["error"] = f"파싱 실패(bozo): {feed.bozo_exception}"
            return [], log

        results = []
        for entry in feed.entries[:max_count]:
            pub_raw       = entry.get("published", "")
            dt_obj, disp  = parse_and_format_date(pub_raw)
            raw_title     = entry.get("title", "제목 없음")
            title         = raw_title.rsplit(' - ', 1)[0].strip()
            compare_key   = re.sub(r'[^가-힣a-zA-Z0-9]', '', title)
            results.append({
                "건설사":    company,
                "키워드":    keyword,
                "기사 제목": title,
                "게시일":    disp,
                "정렬시간":  dt_obj,
                "비교키":    compare_key,
                "링크":      entry.get("link", ""),
            })
        return results, log

    except requests.exceptions.ConnectionError as e:
        log["error"] = f"연결 오류: {str(e)[:120]}"
        return [], log
    except requests.exceptions.Timeout:
        log["error"] = "Timeout (15초 초과)"
        return [], log
    except Exception as e:
        log["error"] = f"알 수 없는 오류: {str(e)[:120]}"
        return [], log

# ---------------------------------------------------------
# 5. 수집 실행
# ---------------------------------------------------------
if start_crawling:
    if not selected_companies:
        st.error("선택된 건설사가 없습니다.")
    elif not keywords:
        st.error("키워드를 입력해주세요.")
    else:
        combinations  = [(c, k) for c in selected_companies for k in keywords]
        total         = len(combinations)
        all_news      = []
        debug_logs    = []

        st.info(f"총 {total}개 조합 수집 시작… (건설사 {len(selected_companies)}개 × 키워드 {len(keywords)}개)")
        prog = st.progress(0)
        status = st.empty()

        # 순차 처리 (병렬 처리 시 Rate Limit 가능성 제거)
        for i, (comp, kw) in enumerate(combinations):
            status.caption(f"수집 중 ({i+1}/{total}): {comp} / {kw}")
            results, log = fetch_one(
                comp, kw, period_option, max_news_count,
                start_date, end_date, debug_mode
            )
            all_news.extend(results)
            debug_logs.append(log)
            prog.progress((i + 1) / total)
            time.sleep(0.3)  # Rate Limit 방지

        status.empty()
        st.divider()

        # 디버그 모드: 요청 결과 상세 표시
        if debug_mode:
            with st.expander("🔧 디버그 로그 (요청별 상세)", expanded=True):
                ok    = [l for l in debug_logs if l["entries"] > 0]
                fail  = [l for l in debug_logs if l["entries"] == 0]
                st.write(f"✅ 성공: {len(ok)}건, ❌ 실패: {len(fail)}건")
                if fail:
                    st.markdown("**실패 목록:**")
                    for l in fail[:20]:
                        st.code(f"URL: {l['url']}\nHTTP: {l['http_status']}  오류: {l['error']}")

        # 결과 출력
        if all_news:
            df = pd.DataFrame(all_news)
            df = df.sort_values("정렬시간", ascending=True)
            df = df.drop_duplicates(subset=["비교키"], keep="first")
            df = df.sort_values("정렬시간", ascending=False).reset_index(drop=True)

            st.subheader(f"📊 수집 결과 — 중복 제거 후 총 {len(df)}건")

            tab_labels = ["전체"] + list(df["건설사"].unique())
            tabs       = st.tabs(tab_labels)

            def show_table(data: pd.DataFrame):
                rows = []
                for _, row in data.iterrows():
                    link  = row.get("링크", "")
                    title = row["기사 제목"]
                    linked = f'<a href="{link}" target="_blank">{title}</a>' if link else title
                    rows.append({
                        "건설사": row["건설사"],
                        "키워드": row["키워드"],
                        "기사 제목": linked,
                        "게시일": row["게시일"],
                    })
                st.write(
                    pd.DataFrame(rows).to_html(escape=False, index=False),
                    unsafe_allow_html=True,
                )

            with tabs[0]:
                show_table(df)
            for i, comp in enumerate(df["건설사"].unique()):
                with tabs[i + 1]:
                    show_table(df[df["건설사"] == comp])

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
                st.info("💡 왼쪽 사이드바 하단의 **🔧 디버그 모드**를 켜고 다시 수집하면 오류 원인을 확인할 수 있습니다.")
            else:
                # 디버그 모드인데도 없으면 연결 자체 문제
                st.error(
                    "Google News RSS 연결 자체가 안 되고 있습니다.\n\n"
                    "**해결 방법:**\n"
                    "1. Streamlit Cloud → Settings → Secrets 에서 별도 설정 불필요\n"
                    "2. 앱을 Reboot 해보세요 (Manage app → Reboot)\n"
                    "3. 그래도 안 되면 Streamlit Cloud IP가 Google에 일시 차단된 것으로,\n"
                    "   잠시 후 다시 시도하거나 네이버 Open API 연동이 필요합니다."
                )
