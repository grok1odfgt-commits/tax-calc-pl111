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
    if "show_login_dialog" not in st.session_state:
        st.session_state.show_login_dialog = False
    if "show_register_dialog" not in st.session_state:
        st.session_state.show_register_dialog = False

# ====================== МОДАЛЬНІ ВІКНА (DIALOG) ======================
def show_login_modal():
    """Відображає модальне вікно входу"""
    if not st.session_state.get("show_login_dialog", False):
        return

    @st.dialog("🔑 Увійти в акаунт")
    def login_form():
        email = st.text_input("Email")
        password = st.text_input("Пароль", type="password")
        if st.button("Увійти", type="primary", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.session_state.authenticated = True
                st.session_state.show_login_dialog = False
                try:
                    check_subscription_status()
                except Exception as e:
                    st.sidebar.warning(f"⚠️ Не вдалося перевірити підписку: {e}")
                st.success("✅ Успішний вхід!")
                st.rerun()
            except Exception as auth_error:
                st.error(f"Помилка входу: {auth_error}")

    login_form()

def show_register_modal():
    """Відображає модальне вікно реєстрації"""
    if not st.session_state.get("show_register_dialog", False):
        return

    @st.dialog("📝 Створити новий акаунт")
    def register_form():
        email = st.text_input("Email")
        password = st.text_input("Пароль (мінімум 6 символів)", type="password")
        if st.button("Зареєструватися", type="primary", use_container_width=True):
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                st.success("✅ Акаунт створено! Перевір пошту (якщо потрібно). Тепер увійди.")
                st.session_state.show_register_dialog = False
            except Exception as e:
                st.error(f"Помилка: {e}")

    register_form()

# ====================== КНОПКА ВИХОДУ (викликається з верхньої панелі) ======================
def logout():
    supabase.auth.sign_out()
    st.session_state.clear()
    init_auth_session()
    st.rerun()

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
        return df  # PRO — повний доступ

    if df is None or df.empty:
        return df

    df = df.copy()

    # Ліміти для різних вкладок
    limits = {
        "Tax_Detailed_Report": 5,
        "Tax_Summary_Report": 5,
        "Tax_Dividend": 3,
        "Tax_Interest": 3
    }

    if tab_name in limits:
        limit = limits[tab_name]
        # Якщо рядків більше ніж ліміт, замінюємо всі значення в рядках після ліміту на "X"
        if len(df) > limit:
            for i in range(limit, len(df)):
                for col in df.columns:
                    df.at[i, col] = "X"
        return df

    elif tab_name == "PIT38":
        # Для PIT38 маскуємо тільки колонку зі значеннями (припускаємо, що вона називається "Wartosc")
        if "Wartosc" in df.columns:
            df["Wartosc"] = "X"
        return df

    # Для інших вкладок (Transactions, Portfolio, Cash) повертаємо без змін
    return df

# ====================== ФУНКЦІЯ ДЛЯ PRO ПЕРЕВІРКИ (використовується для вибору року) ======================
def require_pro_for_feature(feature_name=""):
    """Показує попередження, якщо користувач не PRO, але не зупиняє виконання (тільки для інтерактивних дій)"""
    check_subscription_status()
    if not st.session_state.is_pro:
        st.warning(f"🔒 {feature_name} доступно тільки після покупки підписки")
        return False
    return True

# ====================== СТАРА ФУНКЦІЯ ДЛЯ СУМІСНОСТІ (не використовується в новому інтерфейсі) ======================
def require_auth():
    """Стара функція – тепер не блокує додаток, а лише ініціалізує сесію"""
    init_auth_session()
