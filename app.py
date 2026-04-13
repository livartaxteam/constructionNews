import streamlit as st
import datetime
from datetime import timezone, timedelta
from email.utils import parsedate_to_datetime
import feedparser
import pandas as pd
import urllib.parse
import re

# ---------------------------------------------------------
# 1. 초기 데이터 및 세션 상태(Session State) 설정
# ---------------------------------------------------------
default_companies = [
    "삼성물산", "현대건설", "대우건설", "디엘이앤씨", "지에스건설", 
    "현대엔지니어링", "포스코이앤씨", "롯데건설", "SK에코플랜트", "호반건설",
    "HDC현대산업개발", "한화건설", "대방건설", "금호건설", "코오롱글로벌"
]

if 'companies' not in st.session_state:
    st.session_state.companies = default_companies

# ---------------------------------------------------------
# 2. 사이드바 (왼쪽 메뉴바) 구성: 검색 설정
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

new_company = st.sidebar.text_input("새로운 건설사 추가", placeholder="건설사명 입력")
if st.sidebar.button("건설사 추가"):
    if new_company and new_company not in st.session_state.companies:
        st.session_state.companies.append(new_company)
        st.rerun()

st.sidebar.divider()

st.sidebar.subheader("검색 키워드")
keywords_input = st.sidebar.text_input(
    "키워드 (쉼표로 구분하여 입력)",
    value="재개발, 재건축, 착공, 수주"
)
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

st.sidebar.divider()

st.sidebar.subheader("수집 기간")
period_option = st.sidebar.radio(
    "기간을 선택하세요",
    ["하루", "일주일", "한달", "직접입력"]
)

start_date, end_date = None, None
if period_option == "직접입력":
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("시작일", datetime.date.today() - datetime.timedelta(days=7))
    with col2:
        end_date = st.date_input("종료일", datetime.date.today())

st.sidebar.divider()

max_news_count = st.sidebar.number_input("건설사별 최대 수집 뉴스 갯수", min_value=1, max_value=100, value=10)

st.sidebar.divider()
start_crawling = st.sidebar.button("🚀 뉴스 수집 시작", type="primary", use_container_width=True)

# ---------------------------------------------------------
# 3. 메인 화면 구성
# ---------------------------------------------------------
st.title("🏗️ 건설 수주-재개발 뉴스 트래커")
st.markdown("건설사별 신규 수주, 재개발, 재건축, 분양 뉴스를 실시간으로 수집합니다.")
st.divider()

st.subheader("📌 선정 건설사")
if selected_companies:
    st.info(", ".join(selected_companies))
else:
    st.warning("왼쪽 메뉴에서 기사를 수집할 건설사를 1개 이상 선택해주세요.")

# ---------------------------------------------------------
# 4. 날짜 파싱 및 변환 함수 (KST 적용 및 포맷팅)
# ---------------------------------------------------------
def parse_and_format_date(date_str):
    try:
        # 구글 뉴스의 영문 날짜를 datetime 객체로 변환
        dt = parsedate_to_datetime(date_str)
        # 한국 시간(KST)으로 맞춤
        kst_tz = timezone(timedelta(hours=9))
        dt_kst = dt.astimezone(kst_tz)
        
        # YY.MM.DD 형식 추출
        formatted_date = dt_kst.strftime('%y.%m.%d')
        # 요일 추출
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        weekday = weekdays[dt_kst.weekday()]
        
        # 정렬용 원본 시간과, 화면 표시용 문자열 반환
        return dt_kst, f"{formatted_date} ({weekday})"
    except Exception:
        return datetime.datetime.now(), date_str

# ---------------------------------------------------------
# 5. 구글 뉴스 수집 및 처리 로직
# ---------------------------------------------------------
if start_crawling:
    if not selected_companies:
        st.error("선택된 건설사가 없습니다. 검색을 중단합니다.")
    elif not keywords:
        st.error("입력된 키워드가 없습니다.")
    else:
        st.success("데이터 수집을 시작합니다. 잠시만 기다려주세요...")
        
        all_news_data = []
        time_query = ""
        
        if period_option == "하루":
            time_query = " when:1d"
        elif period_option == "일주일":
            time_query = " when:7d"
        elif period_option == "한달":
            time_query = " when:1m"
        elif period_option == "직접입력":
            time_query = f" after:{start_date} before:{end_date}"

        progress_bar = st.progress(0)
        total_steps = len(selected_companies) * len(keywords)
        current_step = 0

        for company in selected_companies:
            for keyword in keywords:
                search_query = f'"{company}" "{keyword}"{time_query}'
                encoded_query = urllib.parse.quote(search_query)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
                
                feed = feedparser.parse(rss_url)
                
                for entry in feed.entries[:max_news_count]:
                    # 날짜 변환 함수 호출
                    dt_obj, display_date = parse_and_format_date(entry.published)
                    
                    # 1. 중복 검사를 위한 제목 정제: "제목 - 언론사명" 에서 언론사명 제거
                    cleaned_title = entry.title.rsplit(' - ', 1)[0].strip()
                    # 2. 띄어쓰기 및 특수문자까지 모두 제거하여 엄격한 '비교용 키' 생성
                    compare_key = re.sub(r'[^가-힣a-zA-Z0-9]', '', cleaned_title)

                    all_news_data.append({
                        "기사 제목": cleaned_title, # 언론사가 제거된 깔끔한 제목
                        "게시일": display_date,    # YY.MM.DD (요일) 포맷
                        "정렬시간": dt_obj,         # 시간순 정렬을 위한 실제 datetime 데이터
                        "비교키": compare_key,       # 중복 제거 전용 키
                    })
                
                current_step += 1
                progress_bar.progress(current_step / total_steps)

        st.divider()
        
        if all_news_data:
            df = pd.DataFrame(all_news_data)
            
            # --- 중복 제거 및 최초 보도 기사 추출 로직 ---
            # 1. 먼저 보도된 순(오래된 시간순)으로 정렬
            df = df.sort_values(by='정렬시간', ascending=True)
            # 2. 내용이 같은 기사(비교키 동일) 중 첫 번째(최초 보도) 기사만 남기고 제거
            df = df.drop_duplicates(subset=['비교키'], keep='first')
            # 3. 보기 편하게 다시 최신 기사(가장 최근 시간)가 위로 오도록 내림차순 정렬
            df = df.sort_values(by='정렬시간', ascending=False)
            
            st.subheader(f"📊 수집 결과 (중복 제거 후 총 {len(df)}건)")
            
            # 화면에 보여줄 컬럼만 추출
            df_display = df[['기사 제목', '게시일']]
            
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("해당 조건에 맞는 뉴스가 없습니다.")
