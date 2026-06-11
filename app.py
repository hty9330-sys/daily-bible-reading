
import calendar
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

st.set_page_config(page_title="오늘의 성경읽기", page_icon="📖", layout="centered")

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
PROGRESS_FILE = Path("progress.csv")


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
        return str(ref)
    return str(ref).replace(book, FULL_NAMES.get(book, book), 1)


def bsk_url(ref: str) -> str:
    book, chap = split_reference(ref)
    if not book or not chap:
        return "https://www.bskorea.or.kr/bible/korbibReadpage.php"
    params = urlencode({"book": BOOK_CODES[book], "chap": chap, "version": "GAE"})
    return f"https://www.bskorea.or.kr/bible/korbibReadpage.php?{params}"


@st.cache_data
def load_data():
    df = pd.read_csv("readings.csv", encoding="utf-8-sig")
    df.columns = [str(c).replace("\ufeff", "").strip().lower() for c in df.columns]
    rename_map = {
        "월": "month", "일": "day", "시편": "psalm", "구약": "old_testament", "신약": "new_testament",
        "old": "old_testament", "new": "new_testament", "ot": "old_testament", "nt": "new_testament",
    }
    df = df.rename(columns=rename_map)
    required = ["month", "day", "psalm", "old_testament", "new_testament"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("readings.csv의 열 이름이 맞지 않습니다.")
        st.write("필요한 열:", required)
        st.write("현재 열:", list(df.columns))
        st.stop()
    df["month"] = df["month"].astype(int)
    df["day"] = df["day"].astype(int)
    return df


def lookup_date_for_plan(selected: date):
    # 원본표의 왼쪽 날짜가 일요일 기준이어서 실제 선택일에서 하루를 빼서 CSV를 찾습니다.
    return selected - timedelta(days=1)


def find_reading(df: pd.DataFrame, selected: date):
    if selected.weekday() >= 5:
        return None, None
    lookup = lookup_date_for_plan(selected)
    row = df[(df["month"] == lookup.month) & (df["day"] == lookup.day)]
    if row.empty:
        return None, lookup
    return row.iloc[0], lookup


def load_progress():
    if PROGRESS_FILE.exists():
        df = pd.read_csv(PROGRESS_FILE, encoding="utf-8-sig")
    else:
        df = pd.DataFrame(columns=["date", "psalm_done", "old_done", "new_done", "updated_at"])
    for col in ["psalm_done", "old_done", "new_done"]:
        if col not in df.columns:
            df[col] = False
        df[col] = df[col].fillna(False).astype(bool)
    if "date" not in df.columns:
        df["date"] = ""
    if "updated_at" not in df.columns:
        df["updated_at"] = ""
    return df


def save_progress(df: pd.DataFrame):
    df = df[["date", "psalm_done", "old_done", "new_done", "updated_at"]].copy()
    df.to_csv(PROGRESS_FILE, index=False, encoding="utf-8-sig")


def get_progress_row(progress: pd.DataFrame, selected: date):
    key = selected.isoformat()
    row = progress[progress["date"] == key]
    if row.empty:
        return {"psalm_done": False, "old_done": False, "new_done": False}
    r = row.iloc[0]
    return {"psalm_done": bool(r["psalm_done"]), "old_done": bool(r["old_done"]), "new_done": bool(r["new_done"])}


def update_progress(selected: date, psalm_done: bool, old_done: bool, new_done: bool):
    progress = load_progress()
    key = selected.isoformat()
    new_row = {
        "date": key,
        "psalm_done": bool(psalm_done),
        "old_done": bool(old_done),
        "new_done": bool(new_done),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    progress = progress[progress["date"] != key]
    progress = pd.concat([progress, pd.DataFrame([new_row])], ignore_index=True)
    save_progress(progress)


def reading_row(icon: str, label: str, ref: str, done_key: str, selected: date, current_done: bool):
    left, middle, link_col, check_col = st.columns([1.0, 2.1, 0.9, 0.8], vertical_alignment="center")
    with left:
        st.markdown(f"**{icon} {label}**")
    with middle:
        st.markdown(f"### {pretty_reference(ref)}")
    with link_col:
        st.link_button("📖 읽기", bsk_url(ref), use_container_width=True)
    with check_col:
        return st.checkbox("읽음", value=current_done, key=f"{selected.isoformat()}_{done_key}")


def reading_dates_for_year(df: pd.DataFrame, year: int):
    dates = []
    for _, row in df.iterrows():
        try:
            actual = date(year, int(row["month"]), int(row["day"])) + timedelta(days=1)
        except ValueError:
            continue
        if actual.year == year and actual.weekday() < 5:
            dates.append(actual)
    return sorted(set(dates))


def progress_count_for_date(progress: pd.DataFrame, d: date):
    row = progress[progress["date"] == d.isoformat()]
    if row.empty:
        return 0
    r = row.iloc[0]
    return int(bool(r["psalm_done"])) + int(bool(r["old_done"])) + int(bool(r["new_done"]))


def render_year_calendar(year: int, progress: pd.DataFrame, valid_dates: set):
    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
    month_names = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"]
    html = """
    <style>
    .year-grid {display:grid; grid-template-columns: repeat(3, 1fr); gap:14px;}
    .month-box {border:1px solid #e5e7eb; border-radius:14px; padding:10px; background:#ffffff;}
    .month-title {font-weight:800; margin-bottom:6px; text-align:center;}
    .cal-table {width:100%; border-collapse:separate; border-spacing:3px; font-size:12px;}
    .cal-table th {color:#6b7280; font-weight:700; padding:2px;}
    .cal-table td {text-align:center; height:25px; border-radius:7px;}
    .cal-table a {display:block; text-decoration:none; color:#111827; padding:4px 0; border-radius:7px;}
    .none {background:#f3f4f6; color:#9ca3af;}
    .empty {background:#ffffff;}
    .notdone a {background:#f9fafb; border:1px solid #e5e7eb;}
    .partial a {background:#fde68a; border:1px solid #f59e0b;}
    .done a {background:#86efac; border:1px solid #22c55e; font-weight:800;}
    .today a {outline:2px solid #2563eb;}
    @media (max-width: 700px) {.year-grid {grid-template-columns: repeat(1, 1fr);} }
    </style>
    <div style="font-size:13px; margin-bottom:8px;">🟩 완료 · 🟨 일부 완료 · ⬜ 미완료</div>
    <div class="year-grid">
    """
    today = date.today()
    for m in range(1, 13):
        html += f'<div class="month-box"><div class="month-title">{month_names[m-1]}</div>'
        html += '<table class="cal-table"><tr><th>일</th><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th><th>토</th></tr>'
        for week in cal.monthdatescalendar(year, m):
            html += "<tr>"
            for d in week:
                if d.month != m:
                    html += '<td class="empty"></td>'
                    continue
                if d not in valid_dates:
                    html += f'<td class="none">{d.day}</td>'
                    continue
                cnt = progress_count_for_date(progress, d)
                cls = "done" if cnt == 3 else ("partial" if cnt > 0 else "notdone")
                if d == today:
                    cls += " today"
                html += f'<td class="{cls}"><a href="?selected={d.isoformat()}">{d.day}</a></td>'
            html += "</tr>"
        html += "</table></div>"
    html += "</div>"
    st.components.v1.html(html, height=1350, scrolling=True)


def selected_from_query():
    value = st.query_params.get("selected")
    if not value:
        return date.today()
    if isinstance(value, list):
        value = value[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today()


st.markdown("# 📖 오늘의 성경읽기")
st.caption("날짜를 선택하면 통독표의 해당 요일 구절이 표시됩니다. 읽은 항목은 체크하면 진행률과 1년 달력에 반영됩니다.")

initial_date = selected_from_query()
selected_date = st.date_input("📅 날짜 선택", value=initial_date, format="YYYY-MM-DD")
if selected_date.isoformat() != st.query_params.get("selected", selected_date.isoformat()):
    st.query_params["selected"] = selected_date.isoformat()

df = load_data()
progress = load_progress()
reading, lookup_date = find_reading(df, selected_date)

st.divider()
st.markdown(f"## {selected_date.month}월 {selected_date.day}일 ({WEEKDAY_KR[selected_date.weekday()]})")

if selected_date.weekday() >= 5:
    st.info("이 통독표는 월~금 성경읽기 기준입니다. 월요일부터 금요일 날짜를 선택해 주세요.")
elif reading is None:
    st.warning("이 날짜의 통독표가 아직 입력되지 않았습니다. readings.csv를 확인해 주세요.")
else:
    row_progress = get_progress_row(progress, selected_date)
    psalm_done = reading_row("🌿", "시편", reading["psalm"], "psalm", selected_date, row_progress["psalm_done"])
    st.divider()
    old_done = reading_row("📘", "구약", reading["old_testament"], "old", selected_date, row_progress["old_done"])
    st.divider()
    new_done = reading_row("✝️", "신약", reading["new_testament"], "new", selected_date, row_progress["new_done"])

    if (psalm_done, old_done, new_done) != (row_progress["psalm_done"], row_progress["old_done"], row_progress["new_done"]):
        update_progress(selected_date, psalm_done, old_done, new_done)
        st.rerun()

    today_count = int(psalm_done) + int(old_done) + int(new_done)
    st.progress(today_count / 3)
    if today_count == 3:
        st.success("오늘 성경읽기를 모두 완료했습니다. ✅")
    elif today_count > 0:
        st.warning(f"오늘 {today_count}/3개를 읽었습니다.")
    else:
        st.info("오늘 읽은 항목을 체크해 주세요.")

st.divider()
progress = load_progress()
valid_dates = set(reading_dates_for_year(df, selected_date.year))
read_items = sum(progress_count_for_date(progress, d) for d in valid_dates)
total_items = len(valid_dates) * 3
st.markdown("### 📊 올해 진행률")
st.progress((read_items / total_items) if total_items else 0)
st.write(f"**{read_items} / {total_items}개 완료**")

with st.expander("📅 1년 달력 보기", expanded=False):
    render_year_calendar(selected_date.year, progress, valid_dates)

st.divider()
st.markdown("### 🙏 오늘의 다짐")
st.info("하나님의 말씀을 읽고 묵상하는 하루가 되게 하소서.")

st.image("assets/footer_banner.png", use_container_width=True)
st.caption("성경 본문은 앱에 저장하지 않고 공식 성경 사이트로 연결합니다. 체크 기록은 progress.csv에 저장됩니다.")
