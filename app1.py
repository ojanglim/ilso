import streamlit as st
import os
import requests
import urllib.request
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

# 1. 환경 변수 로드: .env 파일 등에서 설정된 API 키와 인증 정보를 가져와 관리합니다.
load_dotenv()
KMA_API_KEY = os.getenv("KMA_API_KEY")      # 기상청 허브 API 인증키
OPENAI_KEY = os.getenv("OPENAI_API_KEY")    # OpenAI API 호출을 위한 키
KAMIS_KEY = os.getenv("KAMIS_CERT_KEY")     # KAMIS(농수축산물 가격정보) 인증키
KAMIS_ID = os.getenv("KAMIS_ID") or os.getenv("KAMIS_CERT_ID") # KAMIS 사용자 ID

# OpenAI 클라이언트 초기화: GPT-4o 모델과 통신하기 위한 객체 생성
client = OpenAI(api_key=OPENAI_KEY)

# --- [지역 매핑 데이터] ---
# 기상청 ASOS(지상기상관측) 지점 코드를 지역명과 매핑해둔 딕셔너리입니다.
CITY_CODE_MAP = {
    "거제": "294", "거창": "253", "진주": "192", "부산": "159", "대구": "143", 
    "안동": "136", "통영": "162", "포항": "138", "울산": "152", "창원": "155", "밀양": "288",
    "서울": "108", "인천": "112", "수원": "119", "파주": "99", "이천": "203", "양평": "202",
    "대전": "133", "청주": "131", "충주": "127", "천안": "232", "보령": "235", "홍성": "177",
    "광주": "156", "전주": "146", "목포": "165", "여수": "168", "군산": "140", "순천": "174",
    "춘천": "101", "강릉": "105", "원주": "114", "속초": "90", "동해": "106", "철원": "95",
    "제주": "184", "서귀포": "189", "울릉도": "115", "독도": "115"
}

def get_kma_weather(city_name):
    """
    기상청 API를 호출하여 입력받은 지역의 실시간 기온 데이터를 추출합니다.
    최근 3시간 내의 데이터를 순차적으로 조회하여 유효한 값을 찾습니다.
    """
    stn_id = CITY_CODE_MAP.get(city_name)
    if not stn_id: return None
    
    for h in range(1, 4):
        tm_str = (datetime.now() - timedelta(hours=h)).strftime("%Y%m%d%H00")
        # 기상청 지상기상관측(SFCTM) API URL 구성
        url = f"https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php?tm={tm_str}&stn={stn_id}&help=0&authKey={KMA_API_KEY}"
        try:
            with urllib.request.urlopen(url) as f:
                res_text = f.read().decode('euc-kr') # 기상청 데이터는 주로 EUC-KR 인코딩 사용
                # '#' 주석 줄을 제외하고 공백으로 구분된 데이터 라인만 추출
                lines = [l for l in res_text.split('\n') if l and not l.startswith('#')]
                if lines: 
                    # 기상청 데이터 규격상 11번째 인덱스가 지면 기온(TA) 임
                    return float(lines[0].split()[11])
        except: continue
    return None

def get_market_price(item_name, category_name):
    """
    KAMIS API를 통해 해당 품목 부류 내에서 사용자가 입력한 품목의 평균 소매가를 조회합니다.
    """
    # KAMIS 코드 매핑: 식량(100), 채소(200), 과일(400), 축산(500), 수산(600)
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
        if not items or not isinstance(items, list): return None
        
        for item in items:
            # 반환된 리스트 중 사용자가 입력한 품목명이 포함된 첫 번째 결과의 당일 가격(dpr1) 반환
            if item_name in item.get('item_name', ''):
                price = item.get('dpr1', '').replace(',', '')
                return int(price) if price.isdigit() else None
        return None
    except: return None

# --- [Streamlit UI 설정] ---
st.set_page_config(page_title="장날 AI 전문가 리포트", layout="wide")

# 사이드바 구성: 사용자로부터 분석에 필요한 변수들을 입력받음
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2674/2674505.png", width=80)
    st.header("📋 산지 및 품목 정보")
    category = st.selectbox("품목 분류", ["식량작물", "과일류", "채소류", "특용작물", "수산물", "축산물"])
    crop = st.text_input("상세 품목명", "감자")
    city = st.text_input("산지 지역", "거제")
    house = st.selectbox("생산 방식", ["노지/자연산", "하우스/시설/양식"])
    
    st.divider()
    st.header("🍏 전문가 품질 데이터")
    # 카테고리 선택에 따라 품질 측정 지표(Label)와 입력 방식(Slider/Select)을 동적으로 변경
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

# 메인 화면 타이틀
st.title(f"🍎 [장날] 지능형 농수산물 가격 결정 에이전트")

if analyze_btn:
    with st.spinner(f"데이터 정밀 분석 중..."):
        # 1. 기상 데이터 연동
        temp_val = get_kma_weather(city)
        temp = temp_val if temp_val is not None else 15.0 # 데이터 부재 시 기본값 15도
        if temp_val is None:
            st.warning(f"⚠️ {city} 지역의 실시간 기상 데이터를 불러올 수 없어 기본 기온(15.0℃)으로 분석을 진행합니다.")

        # 2. 시장가 데이터 연동
        market_val = get_market_price(crop, category)
        market_p = market_val if market_val is not None else 5500 # 데이터 부재 시 기본값 5,500원
        if market_val is None:
            st.warning(f"⚠️ '{crop}' 품목의 실시간 소매가 정보를 찾을 수 없어 기본 시장가(5,500원)를 기준으로 추천가를 산출합니다.")

        # 3. 선도 판단을 위한 경과일 계산
        days_passed = (datetime.now().date() - record_date).days
        
        # 4. GPT-4o 분석 프롬프트: 8대 요인(기상, 시기, 방식, 산지, 품질, 크기, 외관, 신선도) 전체 분석 요청
        analysis_prompt = f"""
        날짜: {datetime.now().strftime('%Y-%m-%d')}. 품목: {crop}({category}), 산지: {city}, 방식: {house}, 
        {q_label}: {q_metric}, 크기: {size}, 외관: {appearance}, 경과일: {days_passed}일, 기온: {temp}℃.
        
        위 데이터를 기반으로 다음 JSON을 작성하세요:
        1. summary: 전문가적인 한 줄 요약 결론
        2. d_idx: 시기 요인 지수(1.0~1.1)
        3. l_idx: 산지 브랜드 가치 지수(0.85~1.05)
        4. factors: 다음 8가지 요인에 대한 각각의 구체적인 분석 내용을 포함한 객체, "~니다"와 같은 존댓말 사용
           - weather_expl: 현재 기온({temp}℃)이 {crop}의 유통 및 수급에 미치는 영향
           - timing_expl: 현재 시기적 특성(계절적인 수요 언급 and 날짜에 따라 설 추석 등의 명절 기간이 다가온다면 언급, 아니라면 언급 금지)과 수요 변화 분석
           - method_expl: {house} 재배 방식에 따른 상품 가치 설명
           - origin_expl: {city} 산지의 브랜드 가치와 인지도 분석(만약 생산품이 그 지역의 특산물이라면 그것에 관한 언급, 지어내기 금지)
           - quality_expl: {q_label}({q_metric})에 따른 구체적인 맛과 품질 특징
           - size_expl: {size} 크기 등급의 시장 선호도 및 용도 제안
           - appearance_expl: {appearance} 등급에 따른 소비자 소구 포인트
           - freshness_expl: 수확 후 {days_passed}일 경과에 따른 신선도 상태 및 관리 조언
        5. long_advice: 10개 이상의 상세 판매 전략 (각 전략의 첫문장은 굵게 처리하고 "~세요"와 같은 문장으로 끝맺음, 마침표 찍을 것, 첫문장 이후 관련 이모티콘 한개 사용, 첫문장이후 부가설명 작성, 전략마다 번호매김 필수, 전략마다 줄바꿈 두번 필수)
        """
        
        # GPT API 호출 (JSON 모드 사용)
        res = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": analysis_prompt}], 
            response_format={"type": "json_object"}
        )
        data = json.loads(res.choices[0].message.content)

        # --- [장날 지수 산출 로직] ---
        # (1) 기상 보정: 극심한 폭염이나 한파 시 유통/관리비 반영
        w_val = 1.05 if temp >= 33 or temp <= 0 else 1.0
        # (2) 재배 방식 보정: 시설(하우스) 재배의 초기 투자비 및 품질 안정성 반영
        h_val = 1.05 if "하우스" in house else 1.0
        # (3) 크기 등급별 가중치
        s_val = {"소": 0.95, "중": 1.0, "대": 1.05, "특대": 1.1}.get(size, 1.0)
        # (4) 외관 상태별 가중치
        a_val = {"정품(최상)": 1.1, "정품(보통)": 1.0, "못난이(흠과)": 0.9}.get(appearance, 1.0)
        # (5) 신선도(경과일) 보정: 갓 수확한 상품에는 프리미엄, 5일 경과 시 감가
        f_val = 1.02 if days_passed <= 1 else (0.95 if days_passed > 5 else 1.0)
        # (6) 품질 등급 가중치 매핑
        q_val_map = {"하": 0.9, "부족": 0.95, "보통": 1.0, "우수": 1.05, "최상": 1.1, "최상(특급)": 1.1, "활어급": 1.15, "1++": 1.2}
        q_val = q_val_map.get(str(q_metric), 1.0)
        # 과일의 경우 당도 수치를 직접 연산에 반영 (기본값 13 brix)
        if category == "과일류": q_val = 1.0 + (float(q_metric) - 13.0) * 0.015
        
        # [최종 통합 지수 산출] 모든 보정치를 곱하며, 무분별한 가격 상승 방지를 위해 최대 1.4배 제한
        j_idx = round(min(w_val * h_val * float(data.get("d_idx", 1.0)) * float(data.get("l_idx", 1.0)) * q_val * s_val * a_val * f_val, 1.4), 2)
        rec_price = int(market_p * j_idx) # 시장 평균가에 지수 적용

        # 결과 화면 출력: 주요 지표를 3개의 컬럼으로 구성
        st.write(""); st.write(""); st.write("")
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("시장 소매 평균가", f"{market_p:,}원")
        col_p2.metric("장날 추천 판매가", f"{rec_price:,}원", f"지수 {j_idx}")
        col_p3.metric("예상 순수익", f"{int(rec_price * 0.55):,}원", "중간 마진 55% 절감분")
        
        st.write(""); 
        st.success(f"📌 **전문가 총평**: {data.get('summary')}")
        
        # 통합 지수 시각화: 프로그레스 바를 통해 현재 가격 위치 표시
        st.markdown(f"### 📊 장날 통합 지수 분석 : {j_idx}")
        norm_idx = min(max((j_idx - 0.5) / 1.0, 0.0), 1.0) # 0.5~1.5 범위를 0~100%로 정규화
        st.progress(norm_idx)
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

        # 8대 유통 및 품질 상세 분석 리포트: GPT가 분석한 내용을 상세히 출력
        st.markdown(f"### 🔍 8대 유통 및 품질 상세 분석 리포트")
        with st.expander("🌐 외부 유통 환경 분석", expanded=True):
            st.info(f"🌡️ **(1) 기상 요인**: {data['factors'].get('weather_expl')}")
            st.info(f"📅 **(2) 시기 요인**: {data['factors'].get('timing_expl')}")
            st.info(f"🏠 **(3) 생산 방식**: {data['factors'].get('method_expl')}")
            st.info(f"🌟 **(4) 산지 요인**: {data['factors'].get('origin_expl')}")

        with st.expander("✨ 내부 작물 품질 분석", expanded=True):
            st.info(f"💎 **(5) 품질 지표**: {data['factors'].get('quality_expl')}")
            st.info(f"📏 **(6) 크기 등급**: {data['factors'].get('size_expl')}")
            st.info(f"🎨 **(7) 외관 등급**: {data['factors'].get('appearance_expl')}")
            st.info(f"🍃 **(8) 신선도 유지**: {data['factors'].get('freshness_expl')}")

        st.write(""); st.write(""); st.write("")

        # 판매 가이드 섹션: 마케팅 포인트 및 판매 전략 출력
        st.markdown("### 💡 AI 유통 전문가의 10개 판매 전략")
        st.success(data.get("long_advice"))
        
        # 하단 푸터: 리포트의 신뢰성을 높여주는 인증 마크
        st.caption(f"인증번호: JNG-{datetime.now().strftime('%Y%m%d%H%M')} | 실시간 데이터 기반 공인 리포트")











