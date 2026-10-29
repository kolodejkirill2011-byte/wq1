import streamlit as st
import math
import os
import random
import base64
import io
import time
import requests
from PIL import Image, ImageDraw, ImageFilter

# ============ ДАННЫЕ ============
PLANETS = {
    "Меркурий": {"au": 0.39, "d_km": 4879, "icon": "☿️", "type": "Скалистая", "moons": 0},
    "Венера":   {"au": 0.72, "d_km": 12104, "icon": "♀️", "type": "Скалистая", "moons": 0},
    "Марс":     {"au": 1.52, "d_km": 6779, "icon": "🔴", "type": "Скалистая", "moons": 2},
    "Юпитер":   {"au": 5.20, "d_km": 139820, "icon": "🟤", "type": "Газовый гигант", "moons": 95},
    "Сатурн":   {"au": 9.54, "d_km": 116460, "icon": "🪐", "type": "Газовый гигант", "moons": 146},
    "Уран":     {"au": 19.19, "d_km": 50724, "icon": "🔵", "type": "Ледяной гигант", "moons": 28},
    "Нептун":   {"au": 30.07, "d_km": 49244, "icon": "🔷", "type": "Ледяной гигант", "moons": 16},
}
CONSTELLATIONS = {
    "Орион": {"star": "Бетельгейзе", "ly": 548, "icon": "🏹", "area": 594},
    "Центавр": {"star": "Альфа Центавра", "ly": 4.37, "icon": "🐴", "area": 1060},
    "Большой Пёс": {"star": "Сириус", "ly": 8.60, "icon": "🐕", "area": 380},
    "Лира": {"star": "Вега", "ly": 25.0, "icon": "🎵", "area": 286},
    "Лебедь": {"star": "Денеб", "ly": 2615, "icon": "🦢", "area": 804},
    "Кассиопея": {"star": "Шедар", "ly": 228, "icon": "👑", "area": 598},
    "Большая Медведица": {"star": "Алиот", "ly": 82.6, "icon": "🐻", "area": 1280},
}
AU_KM = 149_597_870
LY_M = 9.4607e15
C_SPEED = 299_792_458
G = 9.80665

# ============ РАСЧЁТ ============
def travel_years(distance_m):
    a = G
    d_half = distance_m / 2
    t_earth = 2 * math.sqrt(d_half**2 / C_SPEED**2 + 2 * d_half / a)
    t_ship = 2 * (C_SPEED / a) * math.asinh(a * t_earth / C_SPEED)
    year = 365.25 * 24 * 3600
    return t_earth / year, t_ship / year

def info_planet(name):
    p = PLANETS[name]
    dist_m = p["au"] * AU_KM * 1000
    te, ts = travel_years(dist_m)
    return (f"{p['icon']} **{name}**\n\n"
            f"Тип: {p['type']} | Спутников: {p['moons']}\n"
            f"Расстояние от Солнца: {p['au']:.2f} а.е. ({p['au']*AU_KM:,.0f} км)\n"
            f"Диаметр: {p['d_km']:,} км\n\n"
            f"**Перелёт (1g):**\n  • Земля: {te:.2f} лет\n  • Корабль: {ts:.2f} лет")

def info_constellation(name):
    c = CONSTELLATIONS[name]
    dist_m = c["ly"] * LY_M
    te, ts = travel_years(dist_m)
    return (f"{c['icon']} **{name}**\n\n"
            f"Площадь на небе: {c['area']} кв. градусов\n"
            f"Ориентир: {c['star']} ({c['ly']} св. лет)\n\n"
            f"**Перелёт (1g) до ориентира:**\n  • Земля: {te:.2f} лет\n  • Корабль: {ts:.2f} лет")

# ============ РАСПОЗНАВАНИЕ (ПРЯМОЙ API) ============
def recognize_photo(file_bytes, api_key):
    try:
        from astropy.wcs import WCS
        from skyfield.api import load_constellation_map, position_of_radec
        
        # 1. Логин и получение сессии
        login_url = "https://nova.astrometry.net/api/login"
        login_data = {"request-json": f'{{"apikey": "{api_key}"}}'}
        resp = requests.post(login_url, data=login_data)
        session_id = resp.json().get("session")
        
        if not session_id:
            return "❌ Неверный API Key. Проверьте ключ."

        # 2. Загрузка файла напрямую
        upload_url = "https://nova.astrometry.net/api/upload"
        files = {
            "request-json": (None, f'{{"session": "{session_id}"}}'),
            "file": ("image.jpg", file_bytes)
        }
        resp = requests.post(upload_url, files=files)
        sub_id = resp.json().get("subid")
        
        if not sub_id:
            return "❌ Ошибка загрузки файла на сервер."

        # 3. Ожидание обработки (поллинг)
        job_id = None
        for _ in range(30):  # Ждём до 1.5 минут
            time.sleep(3)
            sub_url = f"https://nova.astrometry.net/api/submissions/{sub_id}"
            sub_resp = requests.get(sub_url).json()
            if sub_resp.get("jobs") and sub_resp["jobs"][0] is not None:
                job_id = sub_resp["jobs"][0]
                break
        
        if not job_id:
            return "❌ Сервер не смог обработать фото.\nВозможно, на фото нет звёзд или оно размытое."

        # 4. Получение координат
        calib_url = f"https://nova.astrometry.net/api/jobs/{job_id}/calibration"
        calib_resp = requests.get(calib_url).json()
        
        if "ra" not in calib_resp:
            return "❌ Не удалось определить координаты (фото не распознано)."
            
        ra, dec = calib_resp["ra"], calib_resp["dec"]
        ra_hours = ra / 15.0

        # 5. Определение созвездия
        const_map = load_constellation_map()
        pos = position_of_radec(ra_hours, dec)
        abbr = const_map(pos)

        names = {
            "Ori": "Орион", "UMa": "Большая Медведица", "UMi": "Малая Медведица",
            "Cen": "Центавр", "CMa": "Большой Пёс", "Lyr": "Лира",
            "Cyg": "Лебедь", "Cas": "Кассиопея", "Leo": "Лев",
            "Sco": "Скорпион", "Sgr": "Стрелец", "Peg": "Пегас",
            "And": "Андромеда", "Per": "Персей", "Aur": "Возничий",
            "Tau": "Телец", "Gem": "Близнецы", "Cnc": "Рак",
            "Vir": "Дева", "Lib": "Весы", "Cap": "Козерог",
            "Aqr": "Водолей", "Psc": "Рыбы", "Ari": "Овен",
        }
        const_name = names.get(abbr, abbr)

        res_text = f"✅ **Распознано!**\n\n"
        res_text += f"📍 **Координаты центра:** RA={ra_hours:.2f}ч, Dec={dec:.1f}°\n"
        res_text += f"✨ **Созвездие:** {const_name}\n\n"
        
        if const_name in CONSTELLATIONS:
            c_data = CONSTELLATIONS[const_name]
            res_text += f"ℹ️ Ориентир: {c_data['star']} (расстояние {c_data['ly']} св. лет)\n"
            te, ts = travel_years(c_data['ly'] * LY_M)
            res_text += f"🚀 **Перелёт до ориентира (1g):**\n  • Земля: {te:.1f} лет\n  • Корабль: {ts:.1f} лет\n"
        else:
            res_text += f"⚠️ Расстояние зависит от конкретной звезды в кадре.\n"

        return res_text

    except Exception as e:
        return f"❌ Ошибка при распознавании:\n{e}"

# ============ ФОН ============
def get_base64_starfield():
    img = Image.new("RGB", (800, 900), "#0a0a0a")
    draw = ImageDraw.Draw(img)
    for _ in range(300):
        x, y = random.randint(0, 800), random.randint(0, 900)
        r = random.choice([1, 1, 1, 2])
        color = random.choice([(255, 255, 255), (200, 200, 255), (255, 255, 200)])
        draw.ellipse((x, y, x + r, y + r), fill=color)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

star_bg = get_base64_starfield()

# ============ НАСТРОЙКИ И СТИЛИ ============
st.set_page_config(page_title="Космический распознаватель", page_icon="🔭", layout="centered")

st.markdown(f"""
<style>
    .stApp {{
        background-image: url("data:image/png;base64,{star_bg}");
        background-size: cover;
        background-attachment: fixed;
        background-color: #0a0a0a;
    }}
    .block-container {{
        background-color: rgba(22, 22, 22, 0.8);
        border-radius: 15px;
        padding: 20px;
        max-width: 800px;
    }}
    div.stButton > button {{
        background-color: #161616;
        color: #ffffff;
        border: 1px solid #1f1f1f;
        border-radius: 8px;
        transition: all 0.3s;
        padding: 10px 15px;
    }}
    div.stButton > button:hover {{
        border-color: #00d4ff;
        color: #00d4ff;
        background-color: #1f1f1f;
    }}
    div.stButton > button[kind="primary"] {{
        background-color: #00d4ff;
        color: #000000;
        border: none;
        font-weight: bold;
    }}
    div.stButton > button[kind="primary"]:hover {{
        background-color: #00b8e0;
    }}
    h1, h2, h3, p {{ color: #ffffff !important; }}
    .stText {{ color: #ffffff; }}
    .stTextInput > div > div > input {{
        background-color: #0f0f0f;
        color: #ffffff;
        border: 1px solid #1f1f1f;
    }}
</style>
""", unsafe_allow_html=True)

# ============ СОСТОЯНИЕ ============
if "history" not in st.session_state:
    st.session_state.history = []
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "active_info" not in st.session_state:
    st.session_state.active_info = "1. Введи API Key и нажми 💾\n2. Загрузи фото звёздного неба\n3. Нажми 🔍 Распознать\n\nДля планет используй плитки ниже"

def add_to_history(name, icon, is_planet):
    entry = {"name": name, "icon": icon, "is_planet": is_planet}
    st.session_state.history = [h for h in st.session_state.history if h["name"] != name]
    st.session_state.history.insert(0, entry)
    st.session_state.history = st.session_state.history[:5]

# ============ ИНТЕРФЕЙС ============
st.markdown("<h1 style='text-align: center; color: white;'>🔭 Космический распознаватель</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Исследуй вселенную</p>", unsafe_allow_html=True)

with st.expander("🔑 API Key", expanded=True):
    api_key_input = st.text_input("Введите ключ", value=st.session_state.api_key, type="password", label_visibility="collapsed")
    if st.button("💾 Сохранить"):
        st.session_state.api_key = api_key_input
        st.success("Ключ сохранён в сессии")

st.markdown("### 📷 Фото")
uploaded_file = st.file_uploader("Загрузите фото (jpg, jpeg, png)", label_visibility="collapsed")
if uploaded_file is not None:
    st.image(uploaded_file) 
    if st.button("🔍 Распознать", type="primary"):
        if not st.session_state.api_key:
            st.error("Введите API Key выше!")
        else:
            with st.spinner("Отправка в Astrometry.net (1-3 мин)..."):
                result = recognize_photo(uploaded_file.read(), st.session_state.api_key)
                st.session_state.active_info = result

st.markdown("---")
tab1, tab2 = st.tabs(["🪐 Планеты", "✨ Созвездия"])

with tab1:
    cols = st.columns(7)
    for i, (name, data) in enumerate(PLANETS.items()):
        if cols[i].button(f"{data['icon']}\n{name}"): 
            add_to_history(name, data['icon'], True)
            st.session_state.active_info = info_planet(name)
            st.rerun()

with tab2:
    cols = st.columns(7)
    for i, (name, data) in enumerate(CONSTELLATIONS.items()):
        if cols[i].button(f"{data['icon']}\n{name}"):
            add_to_history(name, data['icon'], False)
            st.session_state.active_info = info_constellation(name)
            st.rerun()

st.markdown("### 📜 История")
if not st.session_state.history:
    st.write("Пока пусто")
else:
    cols = st.columns(5)
    for i, h in enumerate(st.session_state.history):
        if cols[i].button(f"{h['icon']} {h['name']}"):
            st.session_state.active_info = info_planet(h['name']) if h['is_planet'] else info_constellation(h['name'])
            st.rerun()

st.markdown("---")
st.info(st.session_state.active_info)