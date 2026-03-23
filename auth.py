# ==============================================================================
# AUTH.PY — СИСТЕМА АВТОРИЗАЦІЇ + ПІДПИСКИ (МОДАЛЬНИЙ ДІАЛОГ + FREE РЕЖИМ)
# ==============================================================================
import streamlit as st
from supabase import create_client, Client
import os

# ====================== НАЛАШТУВАННЯ SUPABASE ======================
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Не знайдено SUPABASE_URL або SUPABASE_ANON_KEY у secrets!")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====================== ІНІЦІАЛІЗАЦІЯ СЕСІЇ ======================
def init_auth_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "is_pro" not in st.session_state:
        st.session_state.is_pro = False
    if "subscription_plan" not in st.session_state:
        st.session_state.subscription_plan = "free"

# ====================== ПЕРЕВІРКА ПІДПИСКИ ======================
def check_subscription_status():
    if not st.session_state.authenticated or not st.session_state.user:
        return
    try:
        data = supabase.table("profiles").select("subscription_active, subscription_plan") \
               .eq("id", st.session_state.user.id).execute()
        if data.data and len(data.data) > 0:
            st.session_state.is_pro = data.data[0].get("subscription_active", False)
            st.session_state.subscription_plan = data.data[0].get("subscription_plan", "free")
        else:
            supabase.table("profiles").insert({
                "id": st.session_state.user.id,
                "email": st.session_state.user.email,
                "subscription_active": False,
                "subscription_plan": "free"
            }).execute()
            st.session_state.is_pro = False
            st.session_state.subscription_plan = "free"
    except Exception as e:
        st.warning(f"⚠️ Не вдалося перевірити підписку: {e}")
        st.session_state.is_pro = False
        st.session_state.subscription_plan = "free"

# ====================== МОДАЛЬНЕ ВІКНО ЛОГІН ======================
@st.dialog("🔑 Увійти")
def login_dialog():
    st.markdown("**Введіть дані для входу**")
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="your@email.com")
        password = st.text_input("Пароль", type="password")
        if st.form_submit_button("Увійти", type="primary", use_container_width=True):
            if not email or not password:
                st.error("Заповніть обидва поля")
                return
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.session_state.authenticated = True
                check_subscription_status()
                st.success(f"✅ Вітаємо, {res.user.email}!")
                st.rerun()
            except Exception as e:
                st.error(f"Помилка входу: {e}")

# ====================== МОДАЛЬНЕ ВІКНО РЕЄСТРАЦІЯ ======================
@st.dialog("📝 Реєстрація")
def register_dialog():
    st.markdown("**Створити новий акаунт**")
    with st.form("register_form"):
        email = st.text_input("Email", placeholder="your@email.com")
        password = st.text_input("Пароль (мінімум 6 символів)", type="password")
        if st.form_submit_button("Зареєструватися", type="primary", use_container_width=True):
            if not email or not password:
                st.error("Заповніть обидва поля")
                return
            if len(password) < 6:
                st.error("Пароль має бути не менше 6 символів")
                return
            try:
                supabase.auth.sign_up({"email": email, "password": password})
                st.success("✅ Акаунт створено! Перевірте пошту та увійдіть.")
            except Exception as e:
                st.error(f"Помилка реєстрації: {e}")

# ====================== СТАТУС + КНОПКИ В SIDEBAR ======================
def show_auth_status_and_logout():
    if st.session_state.authenticated and st.session_state.user:
        status = "✅ PRO" if st.session_state.is_pro else "🔓 Free"
        st.sidebar.markdown(f"**Користувач:** {st.session_state.user.email}")
        st.sidebar.markdown(f"**Статус:** {status}")
        if st.sidebar.button("🚪 Вийти", use_container_width=True, type="secondary"):
            supabase.auth.sign_out()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    else:
        st.sidebar.markdown("**🔓 Гість (free-режим)**")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("🔑 Увійти", use_container_width=True):
                login_dialog()
        with col2:
            if st.button("📝 Реєстрація", use_container_width=True):
                register_dialog()

# ====================== ОБМЕЖЕННЯ ДЛЯ FREE ======================
def apply_free_limits(df, tab_name):
    if st.session_state.is_pro:
        return df
    if df is None or df.empty:
        return df
    df = df.copy()
    limits = {
        "Tax_Detailed_Report": 5,
        "Tax_Summary_Report": 5,
        "Tax_Dividend": 3,
        "Tax_Interest": 3
    }
    if tab_name in limits:
        limit = limits[tab_name]
        if len(df) > limit:
            for i in range(limit, len(df)):
                for col in df.columns:
                    df.at[i, col] = "X"
        return df
    elif tab_name == "PIT38":
        if "Wartosc" in df.columns:
            df["Wartosc"] = "X"
        return df
    return df

def require_pro_for_feature(feature_name=""):
    if not st.session_state.is_pro:
        st.warning(f"🔒 {feature_name} доступно тільки для PRO-підписників")
        return False
    return True
