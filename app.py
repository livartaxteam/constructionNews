import streamlit as st
import datetime
from datetime import timezone, timedelta
from email.utils import parsedate_to_datetime
import feedparser
import requests
import pandas as pd
import urllib.parse
import re
import concurrent.futures
import time

# ---------------------------------------------------------
# 1. 초기 데이터 및 세션 상태 설정
# ---------------------------------------------------------
default_companies = [
    "삼성물산", "현대건설", "대우건설", "디엘이앤씨", "지에스건설",
    "현대엔지니어링", "포스코이앤씨", "롯데건설", "SK에코플랜트", "호반건설",
    "HDC현대산업개발", "한화건설", "대방건설", "금호건설", "코오롱글로벌"
]

if 'companies' not in st.session_state:
    st.session_state.companies = default_companies.copy()

# ---------------------------------------------------------
# 2. 사이드바 구성
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

col_input, col_btn = st.sidebar.columns([3, 1])
with col_input:
    new_company = st.text_input("새로운 건설사 추가", placeholder="건설사명 입력", label_visibility="collapsed")
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("추가"):
        if new_company and new_company not in st.session_state.companies:
            st.session_state.companies.append(new_company)
            st.rerun()

st.sidebar.divider()

st.sidebar.subheader("검색 키워드")
default_keywords = "재건축 수주, 정비사업 시공사 선정, 아파트 분양, 재개발 사업, 하이엔드 주거"
keywords_input = st.sidebar.text_area(
    "키워드 (쉼표로 구분)",
    value=default_keywords,
    height=100,
    label_visibility="collapsed",
)
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

st.sidebar.divider()

st.sidebar.subheader("수집 기간")
period_option = st.sidebar.radio(
    "기간 선택",
    ["하루", "일주일", "한달", "직접입력"],
    label_visibility="collapsed",
)

start_date, end_date = None, None
if period_option == "직접입력":
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("시작일", datetime.date.today() - datetime.timedelta(days=7))
    with col2:
        end_date = st.date_input("종료일", datetime.date.today())

st.sidebar.divider()

max_news_count = st.sidebar.number_input(
    "건설사별 최대 뉴스 수", min_value=1, max_value=100, value=10
)

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
# 4. 날짜 파싱 함수
# ---------------------------------------------------------
def parse_and_format_date(date_str: str):
    try:
        dt = parsedate_to_datetime(date_str)
        kst_tz = timezone(timedelta(hours=9))
        dt_kst = dt.astimezone(kst_tz)
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        weekday  = weekdays[dt_kst.weekday()]
        return dt_kst, f"{dt_kst.strftime('%y.%m.%d')} ({weekday})"
    except Exception:
        return datetime.datetime.now(timezone(timedelta(hours=9))), date_str

# ---------------------------------------------------------
# 5. ✅ 핵심 수정: Google News RSS 수집 함수
# ---------------------------------------------------------
# 수정 ①: feedparser 직접 URL 호출 → requests로 먼저 받고 feedparser에 텍스트 전달
# 수정 ②: when:Xd → tbs=qdr:X 파라미터로 교체 (URL 인코딩 문제 해결)
# 수정 ③: 회사명 큰따옴표 제거 (RSS에서 완전일치 검색이 오히려 결과 누락)
# 수정 ④: entry.published → entry.get('published', '') 안전 접근

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

def build_rss_url(company: str, keyword: str, period: str,
                  start_date=None, end_date=None) -> str:
    # 수정 ②: tbs 파라미터 사용
    tbs_map = {"하루": "qdr:d", "일주일": "qdr:w", "한달": "qdr:m"}

    # 수정 ③: 큰따옴표 없이 자연어 검색
    query = f"{company} {keyword}"
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"

    if period in tbs_map:
        url += f"&tbs={tbs_map[period]}"
    elif period == "직접입력" and start_date and end_date:
        # after/before는 인코딩 없이 직접 쿼리에 붙임
        date_query = f"{query} after:{start_date} before:{end_date}"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(date_query)}&hl=ko&gl=KR&ceid=KR:ko"

    return url

def fetch_rss(url: str) -> list:
    """requests로 가져온 뒤 feedparser에 텍스트로 전달 (수정 ①)"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)   # ← 텍스트로 파싱
        return feed.entries
    except Exception:
        return []

def fetch_news_single(company: str, keyword: str, period: str,
                      max_count: int, start_date=None, end_date=None) -> list:
    url      = build_rss_url(company, keyword, period, start_date, end_date)
    entries  = fetch_rss(url)
    news_list = []

    for entry in entries[:max_count]:
        pub_raw  = entry.get("published", "")        # 수정 ④: 안전 접근
        dt_obj, display_date = parse_and_format_date(pub_raw)

        raw_title    = entry.get("title", "제목 없음")
        cleaned_title = raw_title.rsplit(' - ', 1)[0].strip()
        compare_key  = re.sub(r'[^가-힣a-zA-Z0-9]', '', cleaned_title)

        news_list.append({
            "건설사":   company,
            "키워드":   keyword,
            "기사 제목": cleaned_title,
            "게시일":   display_date,
            "정렬시간": dt_obj,
            "비교키":   compare_key,
            "링크":     entry.get("link", ""),
        })
    return news_list

# ---------------------------------------------------------
# 6. 수집 실행
# ---------------------------------------------------------
if start_crawling:
    if not selected_companies:
        st.error("선택된 건설사가 없습니다.")
    elif not keywords:
        st.error("키워드를 입력해주세요.")
    else:
        combinations = [(c, k) for c in selected_companies for k in keywords]
        total        = len(combinations)

        st.info(f"총 {total}개 조합 수집 시작… (건설사 {len(selected_companies)}개 × 키워드 {len(keywords)}개)")
        progress_bar   = st.progress(0)
        status_text    = st.empty()
        all_news_data  = []
        current_step   = 0

        # 수정 ⑤: max_workers=3으로 줄여 Rate Limit 방지, 딜레이 추가
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_req = {
                executor.submit(
                    fetch_news_single, comp, kw, period_option,
                    max_news_count, start_date, end_date
                ): (comp, kw)
                for comp, kw in combinations
            }

            for future in concurrent.futures.as_completed(future_to_req):
                comp, kw = future_to_req[future]
                try:
                    data = future.result()
                    if data:
                        all_news_data.extend(data)
                except Exception as e:
                    pass

                current_step += 1
                progress_bar.progress(current_step / total)
                status_text.caption(f"수집 중: {comp} / {kw} ({current_step}/{total})")
                time.sleep(0.1)   # 짧은 딜레이

        status_text.empty()
        st.divider()

        # ---------------------------------------------------------
        # 7. 결과 출력
        # ---------------------------------------------------------
        if all_news_data:
            df = pd.DataFrame(all_news_data)
            df = df.sort_values(by='정렬시간', ascending=True)
            df = df.drop_duplicates(subset=['비교키'], keep='first')
            df = df.sort_values(by='정렬시간', ascending=False).reset_index(drop=True)

            st.subheader(f"📊 수집 결과 — 중복 제거 후 총 {len(df)}건")

            # 탭으로 전체 / 건설사별 분리
            tab_labels = ["전체"] + list(df["건설사"].unique())
            tabs        = st.tabs(tab_labels)

            def show_df(data: pd.DataFrame):
                display = data[['건설사', '키워드', '기사 제목', '게시일', '링크']].copy()
                # 링크를 클릭 가능한 HTML로
                def make_link(row):
                    return f'<a href="{row["링크"]}" target="_blank">{row["기사 제목"]}</a>'
                display["기사 제목"] = display.apply(make_link, axis=1)
                st.write(
                    display[['건설사', '키워드', '기사 제목', '게시일']].to_html(
                        escape=False, index=False
                    ),
                    unsafe_allow_html=True,
                )

            with tabs[0]:
                show_df(df)

            for i, company in enumerate(df["건설사"].unique()):
                with tabs[i + 1]:
                    show_df(df[df["건설사"] == company])

            # CSV 다운로드
            st.divider()
            csv = df[['건설사', '키워드', '기사 제목', '게시일', '링크']].to_csv(
                index=False, encoding="utf-8-sig"
            )
            st.download_button(
                "📥 CSV 다운로드",
                data=csv,
                file_name=f"construction_news_{datetime.date.today()}.csv",
                mime="text/csv",
            )
        else:
            st.warning("수집된 뉴스가 없습니다. 건설사 체크 여부와 키워드를 확인해주세요.")
            st.info("💡 팁: 기간을 '전체'로 바꾸거나 키워드를 단순하게 줄여보세요.")
