import streamlit as st
import datetime
import feedparser
import pandas as pd
import urllib.parse

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

# 스크롤 가능한 컨테이너 생성
company_container = st.sidebar.container(height=200)
with company_container:
    for comp in st.session_state.companies:
        if st.checkbox(comp, key=f"chk_{comp}"):
            selected_companies.append(comp)

# 건설사 추가 기능
new_company = st.sidebar.text_input("새로운 건설사 추가", placeholder="건설사명 입력")
if st.sidebar.button("건설사 추가"):
    if new_company and new_company not in st.session_state.companies:
        st.session_state.companies.append(new_company)
        st.rerun()

st.sidebar.divider()

# 키워드 설정
st.sidebar.subheader("검색 키워드")
keywords_input = st.sidebar.text_input(
    "키워드 (쉼표로 구분하여 입력)",
    value="재개발, 재건축, 착공, 수주"
)
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

st.sidebar.divider()

# 수집 기간 설정
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

# 최대 수집 뉴스 갯수
st.sidebar.subheader("수집 설정")
max_news_count = st.sidebar.number_input("건설사별 최대 수집 뉴스 갯수", min_value=1, max_value=100, value=10)

st.sidebar.divider()

# 뉴스 수집 시작 버튼
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
# 4. 구글 뉴스 수집 로직 작동 (버튼 클릭 시)
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
                    all_news_data.append({
                        "기사 제목": entry.title,
                        "게시일": entry.published,
                        "링크": entry.link # 중복 제거용으로 숨겨서 가져옴
                    })
                
                current_step += 1
                progress_bar.progress(current_step / total_steps)

        # ---------------------------------------------------------
        # 5. 결과 출력 (중복 제거 및 컬럼 축소)
        # ---------------------------------------------------------
        st.divider()
        
        if all_news_data:
            # 1. 수집된 데이터를 판다스 데이터프레임으로 변환
            df = pd.DataFrame(all_news_data)
            
            # 2. 기사 링크(또는 제목)를 기준으로 중복 제거 (첫 번째 기사만 남김)
            df = df.drop_duplicates(subset=['기사 제목'], keep='first')
            
            st.subheader(f"📊 수집 결과 (총 {len(df)}건)")
            
            # 3. 화면에 보여줄 컬럼만 선택 ('기사 제목', '게시일')
            df_display = df[['기사 제목', '게시일']]
            
            # 4. 데이터프레임 출력
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("해당 조건에 맞는 뉴스가 없습니다.")
