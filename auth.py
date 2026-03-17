# ==============================================================================
# ==============================================================================
# AUTH.PY — СИСТЕМА РЕЄСТРАЦІЇ + ПІДПИСКИ (РУЧНА АКТИВАЦІЯ)
# ==============================================================================
# ==============================================================================
# Цей файл повністю окремий. Нічого з app.py ми тут не чіпаємо.
# ==============================================================================

import streamlit as st
from supabase import create_client, Client
import os

# ====================== НАЛАШТУВАННЯ SUPABASE ======================
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Не знайдено SUPABASE_URL або SUPABASE_ANON_KEY у Render secrets!")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====================== ІНІЦІАЛІЗАЦІЯ СЕСІЇ ======================
def init_auth_session():
    """Створюємо всі потрібні змінні в session_state"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "is_pro" not in st.session_state:
        st.session_state.is_pro = False
    if "subscription_plan" not in st.session_state:
        st.session_state.subscription_plan = "free"

# ====================== ОСНОВНА ФУНКЦІЯ: ПЕРЕВІРКА АВТОРИЗАЦІЇ ======================
def require_auth():
    """Показує форму логіну/реєстрації, якщо користувач не увійшов"""
    init_auth_session()

    if st.session_state.authenticated:
        return  # вже увійшов — продовжуємо

    # === ТОП ПАНЕЛЬ З КНОПКАМИ ===
    st.markdown("---")
    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
    with col2:
        if st.button("🔑 Увійти", use_container_width=True):
            st.session_state.show_login = True
    with col3:
        if st.button("📝 Реєстрація", use_container_width=True):
            st.session_state.show_register = True
    st.markdown("---")

    # === МОДАЛЬНЕ ВІКНО ПОСЕРЕДИНІ ===
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
                    check_subscription_status()
                    st.success("✅ Успішний вхід!")
                    st.rerun()
                except:
                    st.error("Невірний email або пароль")

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

    # Якщо не увійшов — зупиняємо весь додаток (показуємо тільки форму)
    st.info("👋 Для користування калькулятором потрібно увійти або зареєструватися")
    st.stop()

# ====================== ПЕРЕВІРКА ПІДПИСКИ (РУЧНА АКТИВАЦІЯ) ======================
def check_subscription_status():
    """Перевіряє статус підписки в таблиці profiles"""
    if not st.session_state.authenticated:
        return
    try:
        data = supabase.table("profiles").select("subscription_active, subscription_plan").eq("id", st.session_state.user.id).execute()
        if data.data:
            st.session_state.is_pro = data.data[0].get("subscription_active", False)
            st.session_state.subscription_plan = data.data[0].get("subscription_plan", "free")
        else:
            # створюємо запис
            supabase.table("profiles").insert({"id": st.session_state.user.id, "email": st.session_state.user.email}).execute()
            st.session_state.is_pro = False
    except:
        st.session_state.is_pro = False

# ====================== ОБМЕЖЕННЯ ДЛЯ FREE КОРИСТУВАЧІВ ======================
def apply_free_limits(df, tab_name):
    """Застосовує всі обмеження, які ти просив"""
    if st.session_state.is_pro:
        return df  # PRO — повний доступ

    if df.empty:
        return df

    if tab_name in ["Tax_Detailed_Report", "Tax_Summary_Report"]:
        # тільки 5 транзакцій нормально, решта — розмита
        df = df.copy()
        df.iloc[5:] = df.iloc[5:].style.apply(lambda x: ['color: transparent; background: repeating-linear-gradient(45deg, #f0f0f0, #f0f0f0 10px, #ddd 10px, #ddd 20px); text-shadow: 0 0 8px #000;'] * len(x), axis=1)
        return df

    elif tab_name in ["Tax_Dividend", "Tax_Interest"]:
        # тільки 3 рядки нормально
        df = df.copy()
        df.iloc[3:] = df.iloc[3:].style.apply(lambda x: ['color: transparent; background: #f0f0f0; text-shadow: 0 0 8px #000;'] * len(x), axis=1)
        return df

    elif tab_name == "PIT38":
        # повністю приховуємо дані, але показуємо, що вкладка є
        return pd.DataFrame([["🔒 PRO only — купи підписку, щоб побачити PIT-38"]], columns=["Повідомлення"])

    return df

# ====================== КНОПКА ВИХОДУ + СТАТУС ======================
def show_auth_status_and_logout():
    if st.session_state.authenticated:
        status = "✅ PRO" if st.session_state.is_pro else "🔓 Free (5 транзакцій)"
        st.sidebar.markdown(f"**Користувач:** {st.session_state.user.email}")
        st.sidebar.markdown(f"**Статус:** {status}")
        if st.sidebar.button("🚪 Вийти"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

# ====================== ФУНКЦІЯ ДЛЯ PRO ПЕРЕВІРКИ ======================
def require_pro_for_feature(feature_name=""):
    """Використовується для критичних функцій (вибір року, PIT38 тощо)"""
    check_subscription_status()
    if not st.session_state.is_pro:
        st.warning(f"🔒 {feature_name} доступно тільки після покупки підписки")
        st.info("Після оплати напиши мені свій email — я активую за 2 хвилини")
        st.stop()