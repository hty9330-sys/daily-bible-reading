import base64
import calendar
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st
import extra_streamlit_components as stx

st.set_page_config(page_title="오늘의 성경읽기", page_icon="📖", layout="centered")

cookie_manager = stx.CookieManager()

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

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


def require_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Streamlit Secrets에 SUPABASE_URL과 SUPABASE_KEY를 입력해 주세요.")
        st.stop()


def auth_headers(token=None):
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {token or SUPABASE_KEY}"
    return headers



def encode_cookie(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def decode_cookie(value: str):
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def save_login_cookie(token: str, refresh_token: str, user_id: str, display_name: str):
    cookie_manager.set(
        "bible_auto_login",
        encode_cookie({
            "access_token": token,
            "refresh_token": refresh_token,
            "user_id": user_id,
            "display_name": display_name,
        }),
        expires_at=datetime.now() + timedelta(days=90),
    )


def clear_login_cookie():
    try:
        cookie_manager.delete("bible_auto_login")
    except Exception:
        pass


def refresh_session(refresh_token: str):
    if not refresh_token:
        return None
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        r = requests.post(
            url,
            headers=auth_headers(),
            json={"refresh_token": refresh_token},
            timeout=20,
        )
    except Exception:
        return None
    if r.status_code >= 400:
        return None
    data = r.json()
    token = data.get("access_token")
    new_refresh_token = data.get("refresh_token") or refresh_token
    user = data.get("user") or {}
    user_id = user.get("id")
    if not token or not user_id:
        return None
    return token, new_refresh_token, user_id


def restore_login_from_cookie():
    if "auth" in st.session_state:
        return
    cookie_value = cookie_manager.get("bible_auto_login")
    if not cookie_value:
        return
    saved = decode_cookie(cookie_value)
    if not saved:
        clear_login_cookie()
        return
    refreshed = refresh_session(saved.get("refresh_token", ""))
    if not refreshed:
        clear_login_cookie()
        return
    token, new_refresh_token, user_id = refreshed
    display_name = saved.get("display_name", "")
    st.session_state.auth = {
        "access_token": token,
        "refresh_token": new_refresh_token,
        "user_id": user_id,
        "display_name": display_name,
    }
    save_login_cookie(token, new_refresh_token, user_id, display_name)


def username_to_email(name: str) -> str:
    clean = name.strip().lower()
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:24]
    return f"user_{digest}@daily-bible.local"


def signup_name_password(display_name: str, password: str):
    require_supabase()
    display_name = display_name.strip()
    if len(display_name) < 2:
        return False, "이름은 2글자 이상 입력해 주세요."
    if len(password) < 4:
        return False, "비밀번호는 4자리 이상 입력해 주세요."

    email = username_to_email(display_name)
    url = f"{SUPABASE_URL}/auth/v1/signup"
    payload = {
        "email": email,
        "password": password,
        "data": {"display_name": display_name, "username": display_name},
    }
    r = requests.post(url, headers=auth_headers(), json=payload, timeout=20)
    if r.status_code >= 400:
        msg = r.json().get("msg") or r.json().get("error_description") or r.text
        if "already" in msg.lower() or "registered" in msg.lower():
            return False, "이미 등록된 이름입니다. 로그인해 주세요."
        return False, f"회원가입 실패: {msg}"

    data = r.json()
    token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    user = data.get("user") or {}
    user_id = user.get("id")
    if not token or not user_id:
        return False, "회원가입은 되었지만 이메일 확인 설정 때문에 바로 로그인되지 않았습니다. Supabase Auth에서 Confirm email을 꺼주세요."

    # profile 저장
    profile_url = f"{SUPABASE_URL}/rest/v1/profiles"
    profile = {"id": user_id, "display_name": display_name, "username": display_name}
    requests.post(profile_url, headers={**auth_headers(token), "Prefer": "resolution=merge-duplicates"}, json=profile, timeout=20)
    st.session_state.auth = {"access_token": token, "refresh_token": refresh_token, "user_id": user_id, "display_name": display_name}
    save_login_cookie(token, refresh_token, user_id, display_name)
    return True, "회원가입 완료"


def login_name_password(display_name: str, password: str):
    require_supabase()
    email = username_to_email(display_name)
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    r = requests.post(url, headers=auth_headers(), json={"email": email, "password": password}, timeout=20)
    if r.status_code >= 400:
        return False, "이름 또는 비밀번호가 맞지 않습니다."
    data = r.json()
    token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    user = data.get("user") or {}
    user_id = user.get("id")
    clean_name = display_name.strip()
    st.session_state.auth = {"access_token": token, "refresh_token": refresh_token, "user_id": user_id, "display_name": clean_name}
    save_login_cookie(token, refresh_token, user_id, clean_name)
    return True, "로그인 완료"


def logout():
    clear_login_cookie()
    st.session_state.pop("auth", None)
    st.rerun()


def render_login():
    st.markdown("# 📖 오늘의 성경읽기")
    st.caption("개인별 읽음 기록을 저장하려면 로그인해 주세요.")
    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

    with tab_login:
        with st.form("login_form"):
            name = st.text_input("이름", placeholder="예: 홍길동")
            pw = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)
        if submitted:
            ok, msg = login_name_password(name, pw)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with tab_signup:
        with st.form("signup_form"):
            name = st.text_input("이름", placeholder="예: 홍길동", key="signup_name")
            pw = st.text_input("비밀번호", type="password", key="signup_pw")
            pw2 = st.text_input("비밀번호 확인", type="password")
            submitted = st.form_submit_button("회원가입", use_container_width=True)
        if submitted:
            if pw != pw2:
                st.error("비밀번호가 서로 다릅니다.")
            else:
                ok, msg = signup_name_password(name, pw)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    st.stop()


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
    return selected - timedelta(days=1)


def find_reading(df: pd.DataFrame, selected: date):
    if selected.weekday() >= 5:
        return None, None
    lookup = lookup_date_for_plan(selected)
    row = df[(df["month"] == lookup.month) & (df["day"] == lookup.day)]
    if row.empty:
        return None, lookup
    return row.iloc[0], lookup


def select_progress(user_id: str, token: str):
    url = f"{SUPABASE_URL}/rest/v1/reading_checks"
    params = {"select": "read_date,psalm_done,old_done,new_done", "user_id": f"eq.{user_id}"}
    r = requests.get(url, headers=auth_headers(token), params=params, timeout=20)
    if r.status_code >= 400:
        st.error(f"읽음 기록 불러오기 실패: {r.text}")
        return pd.DataFrame(columns=["date", "psalm_done", "old_done", "new_done"])
    data = r.json()
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["date", "psalm_done", "old_done", "new_done"])
    df = df.rename(columns={"read_date": "date"})
    for col in ["psalm_done", "old_done", "new_done"]:
        df[col] = df[col].fillna(False).astype(bool)
    return df


def upsert_progress(user_id: str, token: str, selected: date, psalm_done: bool, old_done: bool, new_done: bool):
    url = f"{SUPABASE_URL}/rest/v1/reading_checks"
    params = {"on_conflict": "user_id,read_date"}
    payload = {
        "user_id": user_id,
        "read_date": selected.isoformat(),
        "psalm_done": bool(psalm_done),
        "old_done": bool(old_done),
        "new_done": bool(new_done),
        "updated_at": datetime.utcnow().isoformat(),
    }
    headers = {**auth_headers(token), "Prefer": "resolution=merge-duplicates,return=minimal"}
    r = requests.post(url, headers=headers, params=params, json=payload, timeout=20)
    if r.status_code >= 400:
        st.error(f"저장 실패: {r.text}")
        return False
    return True


def get_progress_row(progress: pd.DataFrame, selected: date):
    key = selected.isoformat()
    row = progress[progress["date"] == key]
    if row.empty:
        return {"psalm_done": False, "old_done": False, "new_done": False}
    r = row.iloc[0]
    return {"psalm_done": bool(r["psalm_done"]), "old_done": bool(r["old_done"]), "new_done": bool(r["new_done"])}


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
    cal = calendar.Calendar(firstweekday=6)
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
        html += f'<div class="month-box"><div class="month-title">{m}월</div>'
        html += '<table class="cal-table"><tr><th>일</th><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th><th>토</th></tr>'
        for week in cal.monthdatescalendar(year, m):
            html += "<tr>"
            for d in week:
                if d.month != m:
                    html += '<td class="empty"></td>'
                elif d not in valid_dates:
                    html += f'<td class="none">{d.day}</td>'
                else:
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


require_supabase()
restore_login_from_cookie()
if "auth" not in st.session_state:
    render_login()

auth = st.session_state.auth
with st.sidebar:
    st.success(f"{auth['display_name']}님 로그인 중")
    if st.button("로그아웃", use_container_width=True):
        logout()

st.markdown("# 📖 오늘의 성경읽기")
st.caption("앱을 열면 오늘 날짜의 통독표가 자동으로 표시됩니다. 과거 날짜는 아래에서 선택할 수 있습니다.")

# 화면 맨 위에 실제 오늘 날짜를 항상 표시합니다.
today = date.today()
st.markdown(
    f"""
    <div style="background:#f8fafc; border:1px solid #e5e7eb; border-radius:16px; padding:18px; margin:12px 0 18px 0; text-align:center;">
        <div style="font-size:0.95rem; color:#64748b; font-weight:700;">📅 오늘 날짜</div>
        <div style="font-size:1.8rem; font-weight:900; color:#111827; margin-top:4px;">
            {today.year}년 {today.month}월 {today.day}일 ({WEEKDAY_KR[today.weekday()]})
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 날짜 선택 상태 관리
# - 앱을 처음 열면 오늘 날짜
# - 과거 날짜 선택은 한 번만 눌러도 바로 반영
# - 1년 달력의 날짜 링크를 누르면 해당 날짜로 이동
query_selected_raw = st.query_params.get("selected")
query_selected = selected_from_query()

if "selected_date" not in st.session_state:
    st.session_state.selected_date = query_selected

if query_selected_raw and st.session_state.get("_last_selected_query") != str(query_selected_raw):
    st.session_state.selected_date = query_selected
    st.session_state._last_selected_query = str(query_selected_raw)

if st.button("오늘 통독표 보기", use_container_width=True):
    st.session_state.selected_date = today
    try:
        st.query_params.clear()
    except Exception:
        pass

with st.expander("📅 과거 날짜 선택", expanded=(st.session_state.selected_date != today)):
    st.date_input("날짜 선택", format="YYYY-MM-DD", key="selected_date")

selected_date = st.session_state.selected_date

df = load_data()
progress = select_progress(auth["user_id"], auth["access_token"])
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
        if upsert_progress(auth["user_id"], auth["access_token"], selected_date, psalm_done, old_done, new_done):
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
progress = select_progress(auth["user_id"], auth["access_token"])
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

try:
    st.image("assets/footer_banner.png", use_container_width=True)
except Exception:
    pass

st.divider()
st.markdown(
    """
    <div style="text-align:center; color:#666; font-size:0.9rem; line-height:1.7;">
    📖 성경 본문은 대한성서공회 성경플랫폼을 통해 제공됩니다.<br><br>
    본 웹앱은 성경 본문을 저장하거나 제공하지 않으며,<br>
    읽기 버튼을 통해 대한성서공회 성경플랫폼으로 연결됩니다.<br><br>
    성경 저작권 © 대한성서공회
    </div>
    """,
    unsafe_allow_html=True,
)