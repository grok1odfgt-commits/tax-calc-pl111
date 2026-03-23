# ==============================================================================
# app.py — Головний UI Streamlit-застосунку (ОПТИМІЗОВАНО ПІД ПК + МОБІЛЬНА АДАПТИВНІСТЬ)
# ==============================================================================
import streamlit as st
import pandas as pd
import io
import streamlit.components.v1 as components
from auth import (
    init_auth_session,
    login_dialog,
    register_dialog,
    require_pro_for_feature,
    apply_free_limits,
    check_subscription_status
)
from calc import (
    Module1_Data_Import,
    Module2_Currency_Rates,
    Module3_FIFO_Data_Compiler,
    Module4_Finance_Data_Compiler,
    Module5_FIFO_Detailed_Tax_Report,
    Module6_FIFO_Summary_Tax_Report,
    Module7_Dividend_Tax_Report,
    Module8_Interest_Tax_Report,
    Module9_Cash_Report,
    Module10_Transactions_Report,
    Module11_Portfolio,
    Module12_PIT38_Report,
    safe_get_loc
)

# ────────────────────────────────────────────────
#   CSS — сучасний, чистий, оптимізований під десктоп
# ────────────────────────────────────────────────
st.markdown("""
<style>
    /* Прибираємо стандартний хедер і сайдбар */
    header, section[data-testid="stSidebar"] { display: none !important; }
    .stApp { background: #f8fafc; }

    /* Топ-бар */
    .top-bar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 56px;
        background: white;
        border-bottom: 1px solid #e2e8f0;
        z-index: 1000;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        padding: 0 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .top-bar .user-info {
        font-size: 14px;
        color: #475569;
        margin-right: 20px;
        font-weight: 500;
    }
    .top-bar button {
        font-size: 14px !important;
        padding: 8px 16px !important;
        border-radius: 6px !important;
        font-weight: 500;
    }

    /* Ліва панель — фіксована ширина для ПК */
    .left-panel {
        position: fixed;
        top: 56px;
        left: 0;
        bottom: 0;
        width: 260px;
        background: white;
        border-right: 1px solid #e2e8f0;
        padding: 24px 16px;
        overflow-y: auto;
        z-index: 999;
        box-shadow: 1px 0 3px rgba(0,0,0,0.04);
    }
    .left-panel h3 {
        margin: 0 0 20px 0;
        font-size: 1.25rem;
        color: #1e40af;
        font-weight: 600;
    }
    .left-panel button {
        width: 100%;
        margin-bottom: 12px;
        font-size: 14px;
        padding: 10px 12px;
        border-radius: 8px;
        font-weight: 500;
    }

    /* Основний контент */
    .main-content {
        margin-left: 260px;
        margin-top: 56px;
        padding: 32px 40px;
        max-width: 1600px;
        margin-right: auto;
        margin-left: auto;
    }

    /* Мобільна адаптивність */
    @media (max-width: 992px) {
        .left-panel {
            position: relative;
            width: 100%;
            height: auto;
            border-right: none;
            border-bottom: 1px solid #e2e8f0;
            top: 56px;
            padding: 20px 16px;
        }
        .main-content {
            margin-left: 0;
            padding: 20px 16px;
        }
        .top-bar {
            padding: 0 16px;
        }
    }

    /* Інші покращення */
    h1, h2, h3 { color: #1e40af; font-weight: 600; }
    .stButton > button { border-radius: 8px; }
    .block-container { padding: 0; }
    .welcome-card {
        background: white;
        padding: 48px 32px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        text-align: center;
        max-width: 900px;
        margin: 40px auto;
    }
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
#   Конфігурація сторінки
# ────────────────────────────────────────────────
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator", page_icon="🧮")

init_auth_session()
check_subscription_status()

# ────────────────────────────────────────────────
#   Топ-бар
# ────────────────────────────────────────────────
st.markdown('<div class="top-bar">', unsafe_allow_html=True)

if st.session_state.authenticated and st.session_state.user:
    status = "PRO" if st.session_state.is_pro else "Free"
    st.markdown(
        f'<span class="user-info">{st.session_state.user.email} • <strong>{status}</strong></span>',
        unsafe_allow_html=True
    )
    if st.button("Вийти", type="secondary", key="logout_top"):
        from supabase import create_client
        supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
        supabase.auth.sign_out()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
else:
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("Увійти", key="login_top"):
            login_dialog()
    with col2:
        if st.button("Реєстрація", key="register_top"):
            register_dialog()

st.markdown('</div>', unsafe_allow_html=True)

# ────────────────────────────────────────────────
#   Ліва панель (260 px)
# ────────────────────────────────────────────────
st.markdown('<div class="left-panel">', unsafe_allow_html=True)

st.markdown("### 🧮 FIFO Tax Calculator")

if "my_files" not in st.session_state:
    st.session_state.my_files = []

st.file_uploader(" ", accept_multiple_files=True, key="hidden_uploader", label_visibility="collapsed")

if st.button("➕ Додати файли CSV", type="primary"):
    components.html("""
        <script>
            window.parent.document.querySelector('input[type="file"]').click();
        </script>
    """, height=0)

if st.session_state.my_files:
    st.markdown(f"**Файли: {len(st.session_state.my_files)}**")
    for i, file in enumerate(st.session_state.my_files):
        col1, col2 = st.columns([5,1])
        col1.markdown(f"📄 {file.name[:28]}{'...' if len(file.name)>28 else ''}")
        if col2.button("×", key=f"del_{i}", help="Видалити"):
            st.session_state.my_files.pop(i)
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Очистити все"):
        st.session_state.my_files.clear()
        st.rerun()

    if st.button("🔄 Розрахувати все", type="primary"):
        with st.spinner("Обчислюємо..."):
            st.session_state.broker_data, st.session_state.rates_data = Module1_Data_Import(st.session_state.my_files)
            st.session_state.rates_data = Module2_Currency_Rates(st.session_state.rates_data)
            st.session_state.fifo_df = Module3_FIFO_Data_Compiler(st.session_state.broker_data, st.session_state.rates_data)
            st.session_state.finance_df = Module4_Finance_Data_Compiler(st.session_state.broker_data)
            recalculate_reports("Wszystkie lata")
        st.success("Готово!")
        st.rerun()
else:
    st.info("Завантажте CSV-файли з Interactive Brokers")

st.markdown('</div>', unsafe_allow_html=True)

# ────────────────────────────────────────────────
#   Основний контент
# ────────────────────────────────────────────────
st.markdown('<div class="main-content">', unsafe_allow_html=True)

# ... (тут весь решта коду — ключі сесії, функції show_no_data_message, style_dataframe, download_excel,
# всі render_..._Tab функції, render_global_year_selector, render_main_tabs, recalculate_reports — 
# вони залишаються точно такими ж, як у твоєму оригінальному app.py)

# Для прикладу — тільки початок логіки запуску (встав весь код після CSS до кінця)

keys = [ ... ]  # весь список ключів з твого коду

# всі def show_no_data_message, style_dataframe, download_excel ...

# всі def render_..._Tab (Rates_NBP, FIFO_Data, Tax_Detailed_Report тощо)

# def recalculate_reports, render_global_year_selector, render_main_tabs

# Логіка відображення
if st.session_state.broker_data is not None:
    render_global_year_selector()
    render_main_tabs()
else:
    st.markdown('<div class="welcome-card">', unsafe_allow_html=True)
    st.markdown("""
    <h1>🧮 FIFO Tax Calculator</h1>
    <p style="font-size:1.3rem; margin:24px 0;">
        Сучасний калькулятор податків для інвесторів з Польщі
    </p>
    """, unsafe_allow_html=True)
    st.info("Завантажте файли в лівій панелі та натисніть «Розрахувати все»")
    st.image("https://picsum.photos/id/1015/1000/500", use_column_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # закриття main-content
