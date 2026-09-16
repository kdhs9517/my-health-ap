import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import json
from google import genai
from google.genai import types

# 페이지 기본 설정
st.set_page_config(page_title="나만의 헬스 파트너", page_icon="🩺", layout="centered")

# --- DB 초기화 ---
DB_FILE = "health_tracker.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 일상 기록 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS health_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symptoms TEXT,
            details TEXT,
            free_text TEXT,
            ai_summary TEXT,
            ai_cause TEXT
        )
    ''')
    # 사용자 정의 규칙 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule TEXT,
            created_at TEXT
        )
    ''')
    # 기존 질환 / 병력 관리 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_diseases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disease_name TEXT,
            note TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 사이드바: 설정 및 기존질환 관리 ---
st.sidebar.title("⚙️ 설정 및 프로필")

# Gemini API Key 입력
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="AIzaSy... 형태의 키를 입력하세요")
if not api_key and "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]

st.sidebar.markdown("---")
st.sidebar.subheader("🏥 기존 질환 / 병력 관리")

# 질환 추가 입력 폼
with st.sidebar.form("disease_form", clear_on_submit=True):
    new_disease = st.text_input("질환/증상명", placeholder="예: 편두통, 역류성 식도염")
    disease_note = st.text_input("상세 내용/복용약", placeholder="예: 필요시 타이레놀 복용중")
    add_disease_btn = st.form_submit_button("질환 추가하기")

if add_disease_btn and new_disease:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO user_diseases (disease_name, note, created_at) VALUES (?, ?, ?)",
              (new_disease, disease_note, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    st.sidebar.success(f"'{new_disease}' 추가 완료!")

# 등록된 기존 질환 목록 표시 및 삭제 기능
conn = sqlite3.connect(DB_FILE)
diseases_df = pd.read_sql_query("SELECT * FROM user_diseases ORDER BY id DESC", conn)
conn.close()

user_profile_text = ""
if not diseases_df.empty:
    st.sidebar.write("📌 **현재 등록된 질환 목록:**")
    profile_items = []
    for idx, row in diseases_df.iterrows():
        item_str = f"- {row['disease_name']} ({row['note']})" if row['note'] else f"- {row['disease_name']}"
        profile_items.append(item_str)
        col1, col2 = st.sidebar.columns([3, 1])
        col1.caption(item_str)
        if col2.button("삭제", key=f"del_dis_{row['id']}"):
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("DELETE FROM user_diseases WHERE id = ?", (row['id'],))
            conn.commit()
            conn.close()
            st.rerun()
    user_profile_text = "\n".join(profile_items)
else:
    st.sidebar.caption("등록된 기존 질환이 없습니다.")

# --- 증상 선택지 데이터 정의 ---
SYMPTOM_OPTIONS = {
    "두통": [
        "머리가 깨질 듯이 콕콕 쑤신다 (편두통 양상)",
        "뒤통수나 머리 전체가 묵직하게 조인다 (긴장성 두통)",
        "관자놀이 주변이 뻐근하고 당긴다 (안구/근육 피로)",
        "숙이거나 움직일 때 머리가 울린다",
        "❓ 잘 모르겠다 / 명확히 설명하기 어려움",
        "✨ 기존 선택지 중에 없음 (자유 입력에 상세 작성)"
    ],
    "눈아픔": [
        "눈 안쪽이 뻑뻑하고 푹푹 쑤신다",
        "눈 앞이 빠질 것처럼 압박감이 든다",
        "초점이 잘 안 맞고 눈을 뜨기 힘들다",
        "❓ 잘 모르겠다 / 명확히 설명하기 어려움",
        "✨ 기존 선택지 중에 없음 (자유 입력에 상세 작성)"
    ],
    "복통": [
        "쥐어짜듯 콕콕 찌르는 통증",
        "속이 쓰리고 묵직하게 더부룩함",
        "아랫배가 팽만하고 알싸하게 아픔 (월경통/장가스)",
        "❓ 잘 모르겠다 / 명확히 설명하기 어려움",
        "✨ 기존 선택지 중에 없음 (자유 입력에 상세 작성)"
    ],
    "피로/어지러움": [
        "몸이 물을 흠뻑 적신 듯 묵직하고 무겁다",
        "일어나거나 움직일 때 순간적으로 핑 돈다",
        "머리가 멍하고 안개가 낀 것 같다 (Brain Fog)",
        "❓ 잘 모르겠다 / 명확히 설명하기 어려움",
        "✨ 기존 선택지 중에 없음 (자유 입력에 상세 작성)"
    ],
    "집중력저하": [
        "글씨나 화면이 눈에 들어오지 않는다",
        "간단한 사고나 판단이 느려진다",
        "❓ 잘 모르겠다 / 명확히 설명하기 어려움",
        "✨ 기존 선택지 중에 없음 (자유 입력에 상세 작성)"
    ]
}

# --- 메인 화면 ---
st.title("🩺 나만의 헬스 파트너")

tabs = st.tabs(["📝 오늘의 상태 입력", "📊 역대 기록 & 원인 분석", "📜 누적 커스텀 규칙"])

# TAB 1: 입력 화면
with tabs[0]:
    st.subheader("1. 주요 증상 선택")
    
    selected_symptoms = []
    symptom_details = {}
    
    cols = st.columns(3)
    categories = list(SYMPTOM_OPTIONS.keys())
    for idx, cat in enumerate(categories):
        with cols[idx % 3]:
            if st.checkbox(cat, key=f"cat_{cat}"):
                selected_symptoms.append(cat)
                
    if selected_symptoms:
        st.markdown("---")
        st.write("🔍 **세부 증상을 선택하세요 (복수 선택 가능):**")
        for cat in selected_symptoms:
            options = st.multiselect(
                f"[{cat}] 해당하는 세부 증상을 모두 고르세요:",
                options=SYMPTOM_OPTIONS[cat],
                key=f"detail_{cat}"
            )
            symptom_details[cat] = options

    st.markdown("---")
    st.subheader("2. 서술형 입력 & 코드/규칙 변경 요청")
    st.caption("오늘의 식사, 운동, 월경, 수술/약, 전자기기, 컨디션 또는 시스템 규칙 변경 요청을 적어주세요.")
    
    free_text = st.text_area(
        "자유 입력 칸",
        placeholder="예: 오늘 전자기기 6시간 봄. 관자놀이 뻐근함. / 세부 선택지에 없는 증상 작성 등"
    )
    
    if st.button("🚀 제출 및 AI 원인 분석 받기", type="primary"):
        if not api_key:
            st.error("Gemini API Key를 입력하거나 Secrets에 GEMINI_API_KEY로 등록해주세요.")
        else:
            client = genai.Client(api_key=api_key)
            
            # DB에서 커스텀 규칙 읽기
            conn = sqlite3.connect(DB_FILE)
            rules_df = pd.read_sql_query("SELECT rule FROM user_rules", conn)
            existing_rules = "\n".join(rules_df['rule'].tolist()) if not rules_df.empty else "없음"
            conn.close()

            # AI 분석 프롬프트
            prompt = f"""
너는 사용자의 전담 개인 의사이자 헬스케어 분석가이다.

[사용자 기존 질환 프로필]
{user_profile_text if user_profile_text else "등록된 질환 없음"}

[사용자가 수동 추가한 시스템 규칙]
{existing_rules}

[오늘 입력 데이터]
- 선택 증상: {selected_symptoms}
- 세부 선택 옵션(복수선택됨): {json.dumps(symptom_details, ensure_ascii=False)}
- 자유 서술 내용: {free_text}

[수행할 작업]
1. [자유 서술 내용]에 '시스템 규칙/코드 변경 요청'(예: "앞으로 ~해줘", "~할 때 이렇게 바꿔줘")이 포함되어 있는지 판별하라.
   - 요청이 있다면 `rule_update` 필드에 해당 규칙 문장을 요약해서 넣고, 없으면 null로 하라.
2. 현재 증상 및 입력 내용에 대한 의학적/생체학적 **원인 분석**과 **상세 설명**을 작성하라.
3. 사용자가 선택한 '잘 모르겠다' 또는 '선택지 없음' 항목이 있다면 자유 서술 내용을 바탕으로 정밀 추론하라.
4. 사용자가 읽기 좋은 **서술형 요약문**을 생성하라 (예: ~해서 ~함. 이는 ~때문으로 보임).
5. **예상되는 내일 상태** 및 **지금 하면 내일 이렇게 된다는 가능성(Simulation)**을 작성하라.
6. **운동 추천 및 단기/장기 효과**, 그리고 **컨디션 모니터링 & 권장 행동**을 제시하라.

응답은 반드시 JSON 형식으로만 작성해야 하며, 키 이름은 다음과 같아야 한다:
- rule_update: 추가할 규칙 문장 (없으면 null)
- summary: 일기장 형태의 증상 및 정황 요약문
- cause: 의학적/생체학적 예상 원인 분석
- tomorrow_prediction: 내일 상태 예측 및 시뮬레이션
- recommendation: 권장 행동 및 컨디션 모니터링 수칙
- exercise_effect: 운동 시 단기적/장기적 효과 가이드
"""
            with st.spinner("Gemini AI가 분석 중입니다..."):
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                        ),
                    )
                    res_json = json.loads(response.text)
                    
                    # 규칙 업데이트 요청 저장
                    if res_json.get("rule_update"):
                        new_rule = res_json["rule_update"]
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("INSERT INTO user_rules (rule, created_at) VALUES (?, ?)", 
                                  (new_rule, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        conn.close()
                        st.success(f"💡 새 시스템 규칙이 적용되었습니다: '{new_rule}'")

                    # 일상 기록 DB 저장
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO health_logs (timestamp, symptoms, details, free_text, ai_summary, ai_cause)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ", ".join(selected_symptoms),
                        json.dumps(symptom_details, ensure_ascii=False),
                        free_text,
                        res_json.get("summary", ""),
                        res_json.get("cause", "")
                    ))
                    conn.commit()
                    conn.close()

                    # 결과 출력
                    st.markdown("---")
                    st.header("📋 AI 분석 리포트")
                    
                    st.subheader("📝 정리된 오늘의 기록")
                    st.info(res_json.get("summary"))
                    
                    st.subheader("🔍 예상되는 원인 분석")
                    st.warning(res_json.get("cause"))
                    
                    st.subheader("🔮 내일 상태 예측 & 시뮬레이션")
                    st.write(res_json.get("tomorrow_prediction"))
                    
                    st.subheader("💡 컨디션 모니터링 & 권장 행동")
                    st.success(res_json.get("recommendation"))
                    
                    st.subheader("🏃‍♂️ 운동 제안 (단기/장기 효과)")
                    st.write(res_json.get("exercise_effect"))

                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")

# TAB 2: 히스토리
with tabs[1]:
    st.subheader("📜 누적 기록 & 원인 분석")
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT timestamp, symptoms, ai_summary, ai_cause FROM health_logs ORDER BY id DESC", conn)
    conn.close()
    
    if df.empty:
        st.write("기록이 없습니다.")
    else:
        for idx, row in df.iterrows():
            with st.expander(f"📅 {row['timestamp']} | 증상: {row['symptoms']}"):
                st.write(f"**기록 요약:** {row['ai_summary']}")
                st.write(f"**원인 분석:** {row['ai_cause']}")

# TAB 3: 규칙 관리
with tabs[2]:
    st.subheader("⚙️ 누적된 사용자 정의 규칙")
    conn = sqlite3.connect(DB_FILE)
    rules_df = pd.read_sql_query("SELECT * FROM user_rules ORDER BY id DESC", conn)
    conn.close()
    
    if rules_df.empty:
        st.write("등록된 규칙이 없습니다.")
    else:
        st.dataframe(rules_df[['created_at', 'rule']], use_container_width=True)
