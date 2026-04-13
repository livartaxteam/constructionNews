import streamlit as st
import datetime
import feedparser
import pandas as pd
import urllib.parse

# ---------------------------------------------------------
# 1. 초기 데이터 및 세션 상태(Session State) 설정
# ---------------------------------------------------------
# 25년 기준 시공능력평가 상위 건설사 예시 (필요시 50개까지 확장 가능)
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

# [건설사 선택] - st.container(height=)를 사용하여 스크롤 영역 구현 (약 5개 높이)
st.sidebar.subheader("대상 건설사")
st.sidebar.caption("수집할 건설사를 선택하세요 (스크롤 가능)")

# 선택된 건설사를 담을 리스트
selected_companies = []

# 스크롤 가능한 컨테이너 생성 (Streamlit 1.30.0 이상 필요)
company_container = st.sidebar.container(height=200)
with company_container:
    for comp in st.session_state.companies:
        # 체크박스 생성
        if st.checkbox(comp, key=f"chk_{comp}"):
            selected_companies.append(comp)

# [건설사 추가 기능]
new_company = st.sidebar.text_input("새로운 건설사 추가", placeholder="건설사명 입력")
if st.sidebar.button("건설사 추가"):
    if new_company and new_company not in st.session_state.companies:
        st.session_state.companies.append(new_company)
        st.rerun() # 추가 후 화면 새로고침

st.sidebar.divider()

# [키워드 설정]
st.sidebar.subheader("검색 키워드")
keywords_input = st.sidebar.text_input(
    "키워드 (쉼표로 구분하여 입력)",
    value="재개발, 재건축, 착공, 수주"
)
# 쉼표를 기준으로 리스트화하고 공백 제거
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

st.sidebar.divider()

# [수집 기간 설정]
st.sidebar.subheader("수집 기간")
period_option = st.sidebar.radio(
    "기간을 선택하세요",
    ["하루", "일주일", "한달", "직접입력"]
)

# 직접입력을 선택했을 경우 연-월-일 선택창 표시
start_date, end_date = None, None
if period_option == "직접입력":
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("시작일", datetime.date.today() - datetime.timedelta(days=7))
    with col2:
        end_date = st.date_input("종료일", datetime.date.today())

st.sidebar.divider()

# [최대 수집 뉴스 갯수]
st.sidebar.subheader("수집 설정")
max_news_count = st.sidebar.number_input("건설사별 최대 수집 뉴스 갯수", min_value=1, max_value=100, value=10)

st.sidebar.divider()

# [뉴스 수집 시작 버튼] - 메뉴 맨 아래
start_crawling = st.sidebar.button("🚀 뉴스 수집 시작", type="primary", use_container_width=True)


# ---------------------------------------------------------
# 3. 메인 화면 구성
# ---------------------------------------------------------
st.title("🏗️ 건설 수주-재개발 뉴스 트래커")
st.markdown("건설사별 신규 수주, 재개발, 재건축, 분양 뉴스를 실시간으로 수집합니다.")
st.divider()

# 선정 건설사 나열
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

        # 기간에 따른 구글 뉴스 검색 쿼리(문법) 설정
        time_query = ""
        if period_option == "하루":
            time_query = " when:1d"
        elif period_option == "일주일":
            time_query = " when:7d"
        elif period_option == "한달":
            time_query = " when:1m"
        elif period_option == "직접입력":
            time_query = f" after:{start_date} before:{end_date}"

        # 진행 상태바 표시
        progress_bar = st.progress(0)
        total_steps = len(selected_companies) * len(keywords)
        current_step = 0

        # 건설사 + 키워드 조합으로 검색
        for company in selected_companies:
            for keyword in keywords:
                # 구글 뉴스 검색어 조합 (예: "삼성물산" "재건축" when:1d)
                search_query = f'"{company}" "{keyword}"{time_query}'
                encoded_query = urllib.parse.quote(search_query)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
                
                # RSS 피드 파싱
                feed = feedparser.parse(rss_url)
                
                # 최대 갯수 제한에 맞춰 데이터 수집
                for entry in feed.entries[:max_news_count]:
                    all_news_data.append({
                        "건설사": company,
                        "키워드": keyword,
                        "기사 제목": entry.title,
                        "게시일": entry.published,
                        "링크": entry.link
                    })
                
                current_step += 1
                progress_bar.progress(current_step / total_steps)

        # 결과 출력
        st.divider()
        st.subheader(f"📊 수집 결과 (총 {len(all_news_data)}건)")
        
        if all_news_data:
            # 판다스 데이터프레임으로 변환하여 표 형태로 예쁘게 출력
            df = pd.DataFrame(all_news_data)
            
            # 링크를 클릭 가능한 형태로 만들기 위한 Streamlit 설정
            st.dataframe(
                df,
                column_config={
                    "링크": st.column_config.LinkColumn("기사 링크 (클릭)")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("해당 조건에 맞는 뉴스가 없습니다.")
