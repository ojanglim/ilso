import streamlit as st
import os
import requests
import urllib.request
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

# 1. 환경 변수 로드
load_dotenv()
KMA_API_KEY = os.getenv("KMA_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
KAMIS_KEY = os.getenv("KAMIS_CERT_KEY")
KAMIS_ID = os.getenv("KAMIS_ID")

client = OpenAI(api_key=OPENAI_KEY)

# --- [유틸리티 데이터 및 매핑] ---
CITY_CODE_MAP = {
    "거제": "294", "거창": "253", "진주": "192", "서울": "108", "부산": "159", 
    "대구": "143", "제주": "184", "안동": "136", "통영": "162", "포항": "138"
}

def get_kma_weather(city_name):
    stn_id = CITY_CODE_MAP.get(city_name)
    if not stn_id: return 15.0
    for h in range(1, 4):
        tm_str = (datetime.now() - timedelta(hours=h)).strftime("%Y%m%d%H00")
        url = f"https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php?tm={tm_str}&stn={stn_id}&help=0&authKey={KMA_API_KEY}"
        try:
            with urllib.request.urlopen(url) as f:
                res_text = f.read().decode('euc-kr')
                lines = [l for l in res_text.split('\n') if l and not l.startswith('#')]
                if lines: return float(lines[0].split()[11])
        except: continue
    return 15.0

def get_market_price(item_name):
    url = "https://www.kamis.or.kr/service/price/xml.do?action=dailySalesList"
    params = {"p_cert_key": KAMIS_KEY, "p_cert_id": KAMIS_ID, "p_returntype": "json"}
    try:
        res = requests.get(url, params=params).json()
        items = res.get('price', [])
        for item in items:
            if item_name in item.get('item_name', ''):
                price = item.get('dpr1', '').replace(',', '')
                return int(price) if price.isdigit() else 5500
        return 5500
    except: return 5500

# --- [웹 UI 설정] ---
st.set_page_config(page_title="장날 AI 전문가 리포트", layout="wide")

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2674/2674505.png", width=80)
    st.header("📋 산지 및 품목 정보")
    category = st.selectbox("품목 분류", ["식량작물", "과일류", "채소류", "특용작물", "수산물", "축산물"])
    crop = st.text_input("상세 품목명", "감자")
    city = st.text_input("산지 지역", "거제")
    house = st.selectbox("생산 방식", ["노지/자연산", "하우스/시설/양식"])
    
    st.divider()
    st.header("🍏 전문가 품질 데이터")
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

st.title(f"🍎 [장날] 지능형 전 품목 가격 결정 에이전트")

if analyze_btn:
    with st.spinner(f"데이터 정밀 분석 중..."):
        temp = get_kma_weather(city)
        market_p = get_market_price(crop)
        days_passed = (datetime.now().date() - record_date).days
        
        # GPT 분석 요청
        analysis_prompt = f"""
        날짜: {datetime.now().strftime('%Y-%m-%d')}. 품목: {crop}({category}), 산지: {city}, 방식: {house}, 
        {q_label}: {q_metric}, 크기: {size}, 외관: {appearance}, 경과일: {days_passed}일.
        위 데이터를 기반으로 다음 JSON을 작성:
        1. summary: 전문가적인 한 줄 요약 결론
        2. d_idx/d_expl: 시기 요인 지수(1.0~1.1)와 설명 (명절 약 일주일 전 수요 패턴 구체적 언급)
        3. l_idx/l_expl: 산지 브랜드 가치 지수(0.85~1.05)와 근거
        4. q_expl: {q_label}의 수치에 따른 구체적인 맛과 상품성 특징 설명
        5. long_advice: 10개 이상의 상세 판매(조리나 사용에 관한 조언이 아님)에 관한 조언. 못난이(흠과)일경우에는 그에 관련한 전략을 제시. 반드시 각 항목 사이에는 엔터(\n)를 넣으세요.
           형식: "1. **첫 문장은 굵게.(반드시 문장형태, "~세요"와 같은 정중한 말투)** (첫문장 뒤에는 관련 이모티콘 하나 입력) 내용... \n\n 2. **첫 문장은 굵게.**(이모티콘) 내용..."
        """
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": analysis_prompt}], response_format={"type": "json_object"})
        data = json.loads(res.choices[0].message.content)

        # 지수 보정 및 산출
        w_val = 1.05 if temp >= 33 or temp <= 0 else 1.0
        h_val = 1.05 if "하우스" in house else 1.0
        s_val = {"소": 0.95, "중": 1.0, "대": 1.05, "특대": 1.1}.get(size, 1.0)
        a_val = {"정품(최상)": 1.1, "정품(보통)": 1.0, "못난이(흠과)": 0.9}.get(appearance, 1.0)
        f_val = 1.02 if days_passed <= 1 else (0.95 if days_passed > 5 else 1.0)
        q_val = {"하": 0.9, "부족": 0.95, "보통": 1.0, "우수": 1.05, "최상": 1.1, "활어급": 1.15, "1++": 1.2}.get(q_metric, 1.0)
        if category == "과일류": q_val = 1.0 + (q_metric - 13.0) * 0.015
        
        j_idx = round(min(w_val * h_val * float(data.get("d_idx", 1.0)) * float(data.get("l_idx", 1.0)) * q_val * s_val * a_val * f_val, 1.4), 2)
        rec_price = int(market_p * j_idx)

        # --- [레이아웃: 가격 정보] ---
        st.write(""); st.write(""); st.write("")
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("시장 소매 평균가", f"{market_p:,}원")
        col_p2.metric("장날 추천 판매가", f"{rec_price:,}원", f"지수 {j_idx}")
        col_p3.metric("예상 순수익", f"{int(rec_price * 0.55):,}원", "중간 마진 절감분")
        
        st.write(""); 

        # --- [한 줄 요약] ---
        st.success(f"📌 **전문가 총평**: {data.get('summary')}")
        
        st.write(""); st.write(""); st.write("")

        # --- [지수 분석 그래프 및 정밀 눈금] ---
        st.markdown(f"### 📊 장날 통합 지수 분석 : {j_idx}")
        
        # 0.5~1.5 범위를 기준으로 프로그레스 바 렌더링
        norm_idx = min(max((j_idx - 0.5) / 1.0, 0.0), 1.0)
        st.progress(norm_idx)
        
        # 각 숫자와 문구를 동일한 너비(25%)의 칸에 담아 간격을 완벽히 일치시킴
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

        # --- [8대 요인 상세 분석 리포트] ---
        st.markdown(f"### 🔍 8대 유통 및 품질 상세 분석 리포트")
        with st.expander("🌐 외부 유통 환경 분석", expanded=True):
            # (1) 기상 요인
            weather_desc = "작물의 호흡량이 급증해 선도 유지가 어려운 고온 상태입니다." if temp >= 33 else ("저온으로 인한 세포 위축 우려가 있습니다." if temp <= 0 else "생육 및 신선도 보존에 최적화된 기온입니다.")
            st.info(f"🌡️ **(1) 기상 요인**: {city} 현재 기온 {temp}℃. {weather_desc}")
            
            # (2) 시기 요인
            st.info(f"📅 **(2) 시기 요인**: {data.get('d_expl')}")
            
            # (3) 생산 방식
            house_desc = "시설 재배를 통해 기후 변수를 차단하고 규격화된 고품질을 확보했습니다." if "하우스" in house else "자연 광량과 토양의 기운을 담은 노지 생산본연의 풍미를 강조할 수 있습니다."
            st.info(f"🏠 **(3) 생산 방식**: {house} 방식. {house_desc}")
            
            # (4) 산지 요인
            st.info(f"🌟 **(4) 산지 요인**: {data.get('l_expl')}")

        st.write("")

        with st.expander("✨ 내부 작물 품질 분석", expanded=True):
            # (5) 품질 지표
            st.info(f"💎 **(5) 품질 지표**: {data.get('q_expl')}")
            
            # (6) 크기 등급
            size_desc = {"소": "1인 가구 및 간편 조리용 선호도가 높습니다.", "중": "가정용 및 대중적 소비가 가장 활발한 골든 사이즈입니다.", "대": "명절 선물 및 제수용으로 적합한 프리미엄 크기입니다.", "특대": "최상위 전문점 및 대형 선물 세트용 고부가가치 규격입니다."}.get(size)
            st.info(f"📏 **(6) 크기 등급**: {size} 등급. {size_desc}")
            
            # (7) 외관 등급
            app_desc = {"정품(최상)": "표면에 흠집이 전혀 없어 최상위 백화점 납품이 가능한 수준입니다.", "정품(보통)": "육안상 결점이 적어 대형 마트 및 일반 시장 판매에 적합합니다.", "못난이(흠과)": "외관은 투박하나 맛은 동일하여 가성비 및 가공용 수요가 높습니다."}.get(appearance)
            st.info(f"🎨 **(7) 외관 등급**: {appearance}. {app_desc}")
            
            # (8) 신선도 유지
            fresh_desc = "수확 직후의 최상급 세포 탄력을 유지 중입니다." if days_passed <= 1 else (f"수확 후 {days_passed}일 경과로 미생물 대사가 진행 중이니 빠른 판매가 권장됩니다." if days_passed > 5 else "유통 최적기의 신선도를 유지하고 있습니다.")
            st.info(f"🍃 **(8) 신선도 유지**: {days_passed}일 경과. {fresh_desc}")

        st.write(""); st.write(""); st.write("")

        # --- [전문가 어드바이스] ---
        st.markdown("### 💡 AI 유통 전문가의 10대 판매 전략")
        st.success(data.get("long_advice"))
        
        st.caption(f"인증번호: JNG-{datetime.now().strftime('%Y%m%d%H%M')} | 실시간 데이터 기반 공인 리포트")