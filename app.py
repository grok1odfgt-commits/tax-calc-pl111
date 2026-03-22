# ==============================================================================
# AUTH.PY — СИСТЕМА РЕЄСТРАЦІЇ + ПІДПИСКИ (РУЧНА АКТИВАЦІЯ)
# ==============================================================================
import streamlit as st
from supabase import create_client, Client
import os
import pandas as pd

# ====================== НАЛАШТУВАННЯ SUPABASE ======================
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Не знайдено SUPABASE_URL або SUPABASE_ANON_KEY у Render secrets!")
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

# ====================== ВЕРХНЯ ПАНЕЛЬ (горизонтальна) ======================
def render_top_bar():
    """Рендерить горизонтальну панель з кнопками входу/реєстрації або інформацією про користувача."""
    init_auth_session()

    # Використовуємо 4 колонки: лого (або пусто), кнопки, пусто
    col_logo, col_buttons, col_spacer = st.columns([1, 2, 1])
    with col_buttons:
        if not st.session_state.authenticated:
            # Кнопки для неавторизованого користувача
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔑 Увійти", use_container_width=True):
                    st.session_state.show_login = True
            with col2:
                if st.button("📝 Реєстрація", use_container_width=True):
                    st.session_state.show_register = True
        else:
            # Інформація про авторизованого користувача
            status = "✅ PRO" if st.session_state.is_pro else "🔓 Free"
            st.markdown(f"**{st.session_state.user.email}** &nbsp;&nbsp; {status}")
            if st.button("🚪 Вийти", use_container_width=True):
                supabase.auth.sign_out()
                st.session_state.clear()
                st.rerun()

# ====================== ОСНОВНА ФУНКЦІЯ: ПЕРЕВІРКА АВТОРИЗАЦІЇ ======================
def require_auth():
    """Показує модальні форми логіну/реєстрації, якщо користувач не увійшов."""
    init_auth_session()
    if st.session_state.authenticated:
        return

    # Більше немає кнопок у тілі сторінки – вони перенесені у верхню панель

    # === МОДАЛЬНЕ ВІКНО ЛОГІНУ ===
    if st.session_state.get("show_login", False):
        with st.form("login_form"):
            st.subheader("🔑 Увійти в акаунт")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Увійти"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.session_state.authenticated = True
                    st.session_state.show_login = False
                    try:
                        check_subscription_status()
                    except Exception as e:
                        st.sidebar.warning(f"⚠️ Не вдалося перевірити підписку: {e}")
                    st.success("✅ Успішний вхід!")
                    st.rerun()
                except Exception as auth_error:
                    st.error(f"Помилка входу: {auth_error}")

    # === МОДАЛЬНЕ ВІКНО РЕЄСТРАЦІЇ ===
    if st.session_state.get("show_register", False):
        with st.form("register_form"):
            st.subheader("📝 Створити новий акаунт")
            email = st.text_input("Email")
            password = st.text_input("Пароль (мінімум 6 символів)", type="password")
            if st.form_submit_button("Зареєструватися"):
                try:
                    res = supabase.auth.sign_up({"email": email, "password": password})
                    st.success("✅ Акаунт створено! Перевір пошту (якщо потрібно). Тепер увійди.")
                    st.session_state.show_register = False
                except Exception as e:
                    st.error(f"Помилка: {e}")

    # Якщо не увійшов – зупиняємо весь додаток (показуємо тільки форму)
    st.info("👋 Для користування калькулятором потрібно увійти або зареєструватися")
    st.stop()

# ====================== ПЕРЕВІРКА ПІДПИСКИ ======================
def check_subscription_status():
    """Перевіряє статус підписки в таблиці profiles"""
    if not st.session_state.authenticated:
        return

    try:
        data = supabase.table("profiles").select("subscription_active, subscription_plan").eq("id", st.session_state.user.id).execute()
        if data.data and len(data.data) > 0:
            st.session_state.is_pro = data.data[0].get("subscription_active", False)
            st.session_state.subscription_plan = data.data[0].get("subscription_plan", "free")
        else:
            try:
                supabase.table("profiles").insert({
                    "id": st.session_state.user.id,
                    "email": st.session_state.user.email,
                    "subscription_active": False,
                    "subscription_plan": "free"
                }).execute()
                st.session_state.is_pro = False
                st.session_state.subscription_plan = "free"
            except Exception as insert_error:
                st.sidebar.warning(f"⚠️ Не вдалося створити профіль: {insert_error}")
                st.session_state.is_pro = False
                st.session_state.subscription_plan = "free"
    except Exception as e:
        st.sidebar.warning(f"⚠️ Помилка доступу до профілю: {e}")
        st.session_state.is_pro = False
        st.session_state.subscription_plan = "free"

# ====================== ОБМЕЖЕННЯ ДЛЯ FREE КОРИСТУВАЧІВ ======================
def apply_free_limits(df, tab_name):
    """
    Повертає DataFrame з заміненими на 'X' значеннями для free-користувачів,
    але перші N рядків залишаються недоторканими.
    Для PRO повертає оригінал.
    """
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

# ====================== КНОПКА ВИХОДУ + СТАТУС (ЗАЛИШЕНО ДЛЯ СУМІСНОСТІ, АЛЕ НЕ ВИКОРИСТОВУЄТЬСЯ) ======================
def show_auth_status_and_logout():
    """Більше не використовується, оскільки статус тепер у верхній панелі."""
    pass

# ====================== ФУНКЦІЯ ДЛЯ PRO ПЕРЕВІРКИ ======================
def require_pro_for_feature(feature_name=""):
    """Показує попередження, якщо користувач не PRO, але не зупиняє виконання (тільки для інтерактивних дій)"""
    check_subscription_status()
    if not st.session_state.is_pro:
        st.warning(f"🔒 {feature_name} доступно тільки після покупки підписки")
        return False
    return True
