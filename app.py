import re
from datetime import date, timedelta
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

st.set_page_config(page_title="오늘의 성경읽기", page_icon="📖", layout="centered")

# 대한성서공회 book 코드 매핑
BOOK_CODES = {
    "창": "gen", "출": "exo", "레": "lev", "민": "num", "신": "deu",
    "수": "jos", "삿": "jdg", "룻": "rut", "삼상": "1sa", "삼하": "2sa",
    "왕상": "1ki", "왕하": "2ki", "대상": "1ch", "대하": "2ch",
    "스": "ezr", "느": "neh", "에": "est", "욥": "job", "시": "psa", "잠": "pro",
    "전": "ecc", "아": "sng", "사": "isa", "렘": "jer", "애": "lam", "겔": "ezk", "단": "dan",
    "호": "hos", "욜": "jol", "암": "amo", "옵": "oba", "욘": "jon", "미": "mic", "나": "nam",
    "합": "hab", "습": "zep", "학": "hag", "슥": "zec", "말": "mal",
    "마": "mat", "막": "mrk", "눅": "luk", "요": "jhn", "행": "act", "롬": "rom",
    "고전": "1co", "고후": "2co", "갈": "gal", "엡": "eph", "빌": "php", "골": "col",
    "살전": "1th", "살후": "2th", "딤전": "1ti", "딤후": "2ti", "딛": "tit", "몬": "phm",
    "히": "heb", "약": "jas", "벧전": "1pe", "벧후": "2pe", "요일": "1jn", "요이": "2jn", "요삼": "3jn",
    "유": "jud", "계": "rev",
}

FULL_NAMES = {
    "창": "창세기", "출": "출애굽기", "레": "레위기", "민": "민수기", "신": "신명기",
    "수": "여호수아", "삿": "사사기", "룻": "룻기", "삼상": "사무엘상", "삼하": "사무엘하",
    "왕상": "열왕기상", "왕하": "열왕기하", "대상": "역대상", "대하": "역대하",
    "스": "에스라", "느": "느헤미야", "에": "에스더", "욥": "욥기", "시": "시편", "잠": "잠언",
    "전": "전도서", "아": "아가", "사": "이사야", "렘": "예레미야", "애": "예레미야애가", "겔": "에스겔", "단": "다니엘",
    "호": "호세아", "욜": "요엘", "암": "아모스", "옵": "오바댜", "욘": "요나", "미": "미가", "나": "나훔",
    "합": "하박국", "습": "스바냐", "학": "학개", "슥": "스가랴", "말": "말라기",
    "마": "마태복음", "막": "마가복음", "눅": "누가복음", "요": "요한복음", "행": "사도행전", "롬": "로마서",
    "고전": "고린도전서", "고후": "고린도후서", "갈": "갈라디아서", "엡": "에베소서", "빌": "빌립보서", "골": "골로새서",
    "살전": "데살로니가전서", "살후": "데살로니가후서", "딤전": "디모데전서", "딤후": "디모데후서", "딛": "디도서", "몬": "빌레몬서",
    "히": "히브리서", "약": "야고보서", "벧전": "베드로전서", "벧후": "베드로후서", "요일": "요한일서", "요이": "요한이서", "요삼": "요한삼서",
    "유": "유다서", "계": "요한계시록",
}

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def split_reference(ref: str):
    ref = str(ref).strip().replace(" ", "")
    keys = sorted(BOOK_CODES.keys(), key=len, reverse=True)
    for key in keys:
        if ref.startswith(key):
            rest = ref[len(key):]
            m = re.search(r"\d+", rest)
            if not m:
                return key, None
            return key, int(m.group())
    return None, None


def pretty_reference(ref: str) -> str:
    book, _ = split_reference(ref)
    if not book:
        return ref
    return ref.replace(book, FULL_NAMES.get(book, book), 1)


def bsk_url(ref: str) -> str:
    book, chap = split_reference(ref)
    if not book or not chap:
        return "https://www.bskorea.or.kr/bible/korbibReadpage.php"
    params = urlencode({"book": BOOK_CODES[book], "chap": chap, "version": "GAE"})
    return f"https://www.bskorea.or.kr/bible/korbibReadpage.php?{params}"


@st.cache_data
def load_data():
    df = pd.read_csv("readings.csv")
    df["month"] = df["month"].astype(int)
    df["day"] = df["day"].astype(int)
    return df


def lookup_date_for_plan(selected: date):
    """
    원본 통독표의 왼쪽 '일'은 일요일 기준입니다.
    CSV는 월~금 칸을 일요일 날짜부터 +0~+4로 입력해 둔 구조라서,
    실제 달력 날짜에서 하루를 빼서 찾으면 월~금 칸이 정확히 맞습니다.
    예: 실제 6/11(목) -> CSV 6/10 -> 원본표 목요일 칸.
    """
    return selected - timedelta(days=1)


def find_reading(df: pd.DataFrame, selected: date):
    if selected.weekday() >= 5:  # 토/일
        return None, None
    lookup = lookup_date_for_plan(selected)
    row = df[(df["month"] == lookup.month) & (df["day"] == lookup.day)]
    if row.empty:
        return None, lookup
    return row.iloc[0], lookup


def reading_row(icon: str, label: str, ref: str):
    left, middle, right = st.columns([1.05, 2.4, 1.0], vertical_alignment="center")
    with left:
        st.markdown(f"**{icon} {label}**")
    with middle:
        st.markdown(f"### {pretty_reference(ref)}")
    with right:
        st.link_button("📖 읽기", bsk_url(ref), use_container_width=True)


st.markdown("# 📖 오늘의 성경읽기")
st.caption("날짜를 선택하면 통독표의 해당 요일 구절이 표시됩니다. 성경 본문은 대한성서공회 사이트에서 읽습니다.")

selected_date = st.date_input("📅 날짜 선택", value=date.today(), format="YYYY-MM-DD")

df = load_data()
reading, lookup_date = find_reading(df, selected_date)

st.divider()
st.markdown(f"## {selected_date.month}월 {selected_date.day}일 ({WEEKDAY_KR[selected_date.weekday()]})")

if selected_date.weekday() >= 5:
    st.info("이 통독표는 월~금 성경읽기 기준입니다. 월요일부터 금요일 날짜를 선택해 주세요.")
elif reading is None:
    st.warning("이 날짜의 통독표가 아직 입력되지 않았습니다. readings.csv를 확인해 주세요.")
else:
    reading_row("🌿", "시편", reading["psalm"])
    st.divider()
    reading_row("📘", "구약", reading["old_testament"])
    st.divider()
    reading_row("✝️", "신약", reading["new_testament"])

st.divider()
st.markdown("### 🙏 오늘의 다짐")
st.info("하나님의 말씀을 읽고 묵상하는 하루가 되게 하소서.")

st.image("assets/footer_banner.png", use_container_width=True)
st.caption("성경 본문은 앱에 저장하지 않고 공식 성경 사이트로 연결합니다.")
