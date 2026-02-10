import streamlit as st
import os
import requests
import urllib.request
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

# 1. 환경 변수 로드 (API 키 및 인증 정보 관리)
load_dotenv()
KMA_API_KEY = os.getenv("KMA_API_KEY")      # 기상청 API 키
OPENAI_KEY = os.getenv("OPENAI_API_KEY")    # OpenAI API 키
KAMIS_KEY = os.getenv("KAMIS_CERT_KEY")     # KAMIS API 키
KAMIS_ID = os.getenv("KAMIS_ID") or os.getenv("KAMIS_CERT_ID") # KAMIS 사용자 ID

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_KEY)

# --- [안정적인 지역 매핑: 기상청 지점 코드 확충] ---
# 지점 코드는 기상청 API(ASOS)에서 사용하는 고유 번호입니다.
CITY_CODE_MAP = {
    # 경상권
    "거제": "294", "거창": "253", "진주": "192", "부산": "159", "대구": "143", 
    "안동": "136", "통영": "162", "포항": "138", "울산": "152", "창원": "155", "밀양": "288",
    # 수도권
    "서울": "108", "인천": "112", "수원": "119", "파주": "99", "이천": "203", "양평": "202",
    # 충청권
    "대전": "133", "청주": "131", "충주": "127", "천안": "232", "보령": "235", "홍성": "177",
    # 전라권
    "광주": "156", "전주": "146", "목포": "165", "여수": "168", "군산": "140", "순천": "174",
    # 강원권
    "춘천": "101", "강릉": "105", "원주": "114", "속초": "90", "동해": "106", "철원": "95",
    # 제주 및 기타
    "제주": "184", "서귀포": "189", "울릉도": "115", "독도": "115"
}

def get_kma_weather(city_name):
    """
    기상청 API를 통해 특정 지역의 실시간 기온 데이터를 가져오는 함수
    """
    stn_id = CITY_CODE_MAP.get(city_name)
    if not stn_id: return None # 매핑 실패 시 None 반환
    
    # 최근 3시간 데이터를 시도하여 데이터 누락 방지
    for h in range(1, 4):
        tm_str = (datetime.now() - timedelta(hours=h)).strftime("%Y%m%d%H00")
        url = f"https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php?tm={tm_str}&stn={stn_id}&help=0&authKey={KMA_API_KEY}"
        try:
            with urllib.request.urlopen(url) as f:
                res_text = f.read().decode('euc-kr')
                # 주석(#)으로 시작하지 않는 실제 데이터 줄 추출
                lines = [l for l in res_text.split('\n') if l and not l.startswith('#')]
                if lines: 
                    # 기상청 데이터 포맷에서 11번째 인덱스가 기온(TA)
                    return float(lines[0].split()[11])
        except: continue
    return None # 조회 실패 시 None 반환

def get_market_price(item_name, category_name):
    """
    KAMIS API를 통해 실시간 소매 시장 평균가를 조회하는 함수
    """
    # KAMIS 부류 코드 매핑: 100(식량), 200(채소), 400(과일), 500(축산), 600(수산)
    category_map = {
        "식량작물": "100", "채소류": "200", "과일류": "400", 
        "특용작물": "400", "축산물": "500", "수산물": "600"
    }
    item_code = category_map.get(category_name, "200")
    
    url = "https://www.kamis.or.kr/service/price/xml.do?action=dailySalesList"
    params = {
        "p_cert_key": KAMIS_KEY, 
        "p_cert_id": KAMIS_ID, 
        "p_returntype": "json",
        "p_item_category_code": item_code
    }
    
    try:
        res = requests.get(url, params=params).json()
        items = res.get('price', [])
        
        if not items or not isinstance(items, list):
            return None
            
        for item in items:
            # API 결과의 품목명에 사용자가 입력한 검색어가 포함되어 있는지 확인
            if item_name in item.get('item_name', ''):
                price = item.get('dpr1', '').replace(',', '')
                return int(price) if price.isdigit() else None
        return None
    except: 
        return None

# --- [Streamlit 웹 인터페이스 설정] ---
st.set_page_config(page_title="장날 AI 전문가 리포트", layout="wide")

# 사이드바: 사용자 입력 섹션
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2674/2674505.png", width=80)
    st.header("📋 산지 및 품목 정보")
    category = st.selectbox("품목 분류", ["식량작물", "과일류", "채소류", "특용작물", "수산물", "축산물"])
    crop = st.text_input("상세 품목명", "감자")
    city = st.text_input("산지 지역", "거제")
    house = st.selectbox("생산 방식", ["노지/자연산", "하우스/시설/양식"])
    
    st.divider()
    st.header("🍏 전문가 품질 데이터")
    # 카테고리별 동적 입력 필드 (당도, 조직감, 선도 등)
    if category == "과일류":
        q_metric = st.slider("당도 (Brix)", 10.0, 20.0, 13.0, 0.5); q_label = "당도(Brix)"
    elif category in ["채소류", "식량작물"]:
        q_metric = st.select_slider("조직감(팽압/전분가)", options=["부족", "보통", "우수", "최상(특급)"], value="우수"); q_label = "조직감"
    elif category == "수산물":
        q_metric = st.select_slider("선도(어체 탄력)", options=["부족", "보통", "우수", "활어급"], value="우수"); q_label = "선도"
    elif category == "축산물":
        q_metric = st.select_slider("육질 등급", options=["3등급", "2등급", "1등급", "1+", "1++"], value="1등급"); q_label = "육질등급"
    else:
        q_metric = st.select_slider("품질 상태", options=["하", "중", "상", "최상"], value="상"); q_label = "품질"

    size = st.select_slider("크기 등급", options=["소", "중", "대", "특대"], value="중")
    appearance = st.radio("외관 등급", ["정품(최상)", "정품(보통)", "못난이(흠과)"])
    record_date = st.date_input("수확/어획/도축 날짜", datetime.now())
    
    analyze_btn = st.button("장날 정밀 분석 시작")

# 메인 타이틀
st.title(f"🍎 [장날] 지능형 전 품목 가격 결정 에이전트")

if analyze_btn:
    with st.spinner(f"데이터 정밀 분석 중..."):
        # --- [데이터 수집 및 예외 안내 로직 추가] ---
        # 기상 데이터 수집 시도
        temp_val = get_kma_weather(city)
        if temp_val is None:
            st.warning(f"⚠️ {city} 지역의 실시간 기상 데이터를 불러올 수 없어 기본 기온(15.0℃)으로 분석을 진행합니다.")
            temp = 15.0
        else:
            temp = temp_val

        # 시장가 데이터 수집 시도
        market_val = get_market_price(crop, category)
        if market_val is None:
            st.warning(f"⚠️ '{crop}' 품목의 실시간 소매가 정보를 찾을 수 없어 기본 시장가(5,500원)를 기준으로 추천가를 산출합니다.")
            market_p = 5500
        else:
            market_p = market_val

        days_passed = (datetime.now().date() - record_date).days
        
        # GPT-4o 분석 프롬프트: 유통 전문가 시점의 분석 및 판매 전략 요청
        analysis_prompt = f"""
        날짜: {datetime.now().strftime('%Y-%m-%d')}. 품목: {crop}({category}), 산지: {city}, 방식: {house}, 
        {q_label}: {q_metric}, 크기: {size}, 외관: {appearance}, 경과일: {days_passed}일.
        위 데이터를 기반으로 다음 JSON을 작성:
        1. summary: 전문가적인 한 줄 요약 결론
        2. d_idx/d_expl: 시기 요인 지수(1.0~1.1)와 설명 (명절 수요 및 시즈널 이슈 언급)
        3. l_idx/l_expl: 산지 브랜드 가치 지수(0.85~1.05)와 근거
        4. q_expl: {q_label}의 수치에 따른 구체적인 맛과 상품성 특징 설명
        5. long_advice: 10개 이상의 상세 판매 전략 (못난이 전략 포함, 반드시 마크다운 굵게 처리와 이모티콘 사용), 한개의 전략마다 반드시 엔터를 쳐 줄바꿈할것
        """
        
        # GPT API 호출
        res = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": analysis_prompt}], 
            response_format={"type": "json_object"}
        )
        data = json.loads(res.choices[0].message.content)

        # --- [장날 지수 산출 로직] ---
        # 1. 기상 보정 (폭염이나 혹한 시 유통비 상승 반영)
        w_val = 1.05 if temp >= 33 or temp <= 0 else 1.0
        # 2. 재배 방식 보정
        h_val = 1.05 if "하우스" in house else 1.0
        # 3. 크기 보정
        s_val = {"소": 0.95, "중": 1.0, "대": 1.05, "특대": 1.1}.get(size, 1.0)
        # 4. 외관 보정
        a_val = {"정품(최상)": 1.1, "정품(보통)": 1.0, "못난이(흠과)": 0.9}.get(appearance, 1.0)
        # 5. 신선도(경과일) 보정
        f_val = 1.02 if days_passed <= 1 else (0.95 if days_passed > 5 else 1.0)
        
        # 6. 품질 지수 산출 (과일은 당도 비례, 나머지는 등급 매핑)
        q_val_map = {"하": 0.9, "부족": 0.95, "보통": 1.0, "우수": 1.05, "최상": 1.1, "최상(특급)": 1.1, "활어급": 1.15, "1++": 1.2}
        q_val = q_val_map.get(str(q_metric), 1.0)
        if category == "과일류": q_val = 1.0 + (float(q_metric) - 13.0) * 0.015
        
        # [최종 장날 지수 산출] 모든 가중치를 곱하여 산출 (최대 1.4 제한)
        j_idx = round(min(w_val * h_val * float(data.get("d_idx", 1.0)) * float(data.get("l_idx", 1.0)) * q_val * s_val * a_val * f_val, 1.4), 2)
        rec_price = int(market_p * j_idx)

        # 결과 화면 출력: 지표 카드
        st.write(""); st.write(""); st.write("")
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("시장 소매 평균가", f"{market_p:,}원")
        col_p2.metric("장날 추천 판매가", f"{rec_price:,}원", f"지수 {j_idx}")
        col_p3.metric("예상 순수익", f"{int(rec_price * 0.55):,}원", "중간 마진 절감분")
        
        st.write(""); 
        st.success(f"📌 **전문가 총평**: {data.get('summary')}")
        
        st.write(""); st.write(""); st.write("")

        # 장날 지수 가독성 그래프 (Progress Bar 및 라벨링)
        st.markdown(f"### 📊 장날 통합 지수 분석 : {j_idx}")
        norm_idx = min(max((j_idx - 0.5) / 1.0, 0.0), 1.0)
        st.progress(norm_idx)
        
        # 지수별 시장 구간 설명 (HTML 사용)
        st.markdown("""
        <div style="display: flex; width: 100%; margin-top: -5px;">
            <div style="width: 20%;"></div> <div style="width: 20%; text-align: center; font-weight: bold;">0.8</div>
            <div style="width: 20%; text-align: center; font-weight: bold;">1.0</div>
            <div style="width: 20%; text-align: center; font-weight: bold;">1.2</div>
            <div style="width: 20%; text-align: center; font-weight: bold;">1.4</div>
        </div>
        <div style="display: flex; width: 100%; margin-top: 5px;">
            <div style="width: 20%; text-align: center; font-size: 0.8rem; color: #666;"></div>
            <div style="width: 20%; text-align: center; font-size: 0.8rem; color: #666;">⚠️ 재고소진</div>
            <div style="width: 20%; text-align: center; font-size: 0.8rem; color: #666;">🏠 수급안정</div>
            <div style="width: 20%; text-align: center; font-size: 0.8rem; color: #666;">📈 수요상승</div>
            <div style="width: 20%; text-align: center; font-size: 0.8rem; color: #666;">🔥 최고가형성</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.write(""); st.write(""); st.write("")

        # 8대 유통 및 품질 상세 분석 리포트 (Expander 사용으로 깔끔하게 구성)
        st.markdown(f"### 🔍 8대 유통 및 품질 상세 분석 리포트")
        with st.expander("🌐 외부 유통 환경 분석", expanded=True):
            weather_desc = "고온 상태" if temp >= 33 else ("저온 상태" if temp <= 0 else "생육 최적 온도")
            st.info(f"🌡️ **(1) 기상 요인**: {city} 현재 기온 {temp}℃. {weather_desc}")
            st.info(f"📅 **(2) 시기 요인**: {data.get('d_expl')}")
            st.info(f"🏠 **(3) 생산 방식**: {house} 방식 적용")
            st.info(f"🌟 **(4) 산지 요인**: {data.get('l_expl')}")

        with st.expander("✨ 내부 작물 품질 분석", expanded=True):
            st.info(f"💎 **(5) 품질 지표**: {data.get('q_expl')}")
            st.info(f"📏 **(6) 크기 등급**: {size} 등급 맞춤 전략 필요")
            st.info(f"🎨 **(7) 외관 등급**: {appearance} 상태 반영")
            st.info(f"🍃 **(8) 신선도 유지**: 수확 후 {days_passed}일 경과 분석")

        st.write(""); st.write(""); st.write("")

        # 최종 AI 전문가 판매 가이드 출력
        st.markdown("### 💡 AI 유통 전문가의 10대 판매 전략")
        st.success(data.get("long_advice"))
        
        # 하단 인증 정보 (신뢰도 부여)
        st.caption(f"인증번호: JNG-{datetime.now().strftime('%Y%m%d%H%M')} | 실시간 데이터 기반 공인 리포트")

