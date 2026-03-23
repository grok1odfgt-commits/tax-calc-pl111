# ==============================================================================
# app.py — Головний UI Streamlit-застосунку (КАСТОМНІ ПАНЕЛІ + МОБІЛЬНА АДАПТИВНІСТЬ)
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
#   CSS — прибираємо дефолтний header/sidebar + адаптивність
# ────────────────────────────────────────────────
st.markdown("""
<style>
    /* Прибираємо стандартний хедер і сайдбар */
    header { visibility: hidden; height: 0 !important; }
    .stApp > header { display: none !important; }
    section[data-testid="stSidebar"] { display: none !important; }

    /* Топ-бар (горизонтальний, справа) */
    .top-bar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 48px;
        background: white;
        border-bottom: 1px solid #e0e0e0;
        z-index: 999;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        padding: 0 16px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }
    .top-bar .user-info {
        font-size: 13px;
        color: #444;
        margin-right: 16px;
    }
    .top-bar button {
        font-size: 13px !important;
        padding: 6px 12px !important;
        min-height: 32px !important;
        border-radius: 6px !important;
    }

    /* Ліва панель (20% на десктопі) */
    .left-panel {
        position: fixed;
        top: 48px;
        left: 0;
        bottom: 0;
        width: 20%;
        background: #f9fafb;
        border-right: 1px solid #e5e7eb;
        padding: 16px;
        overflow-y: auto;
        z-index: 998;
        transition: all 0.3s;
    }
    .left-panel h3 {
        margin: 0 0 16px 0;
        font-size: 1.15rem;
        color: #1e40af;
    }
    .left-panel button {
        width: 100%;
        margin-bottom: 8px;
        font-size: 14px;
        padding: 10px;
        border-radius: 6px;
    }

    /* Основний контент */
    .main-content {
        margin-left: 20%;
        margin-top: 48px;
        padding: 24px 32px 80px;
    }

    /* Мобільна адаптивність */
    @media (max-width: 768px) {
        .left-panel {
            position: relative;
            width: 100%;
            height: auto;
            border-right: none;
            border-bottom: 1px solid #e5e7eb;
            padding: 16px;
            top: 48px;
        }
        .main-content {
            margin-left: 0;
            margin-top: 0;
            padding: 16px 12px;
        }
        .top-bar {
            padding: 0 12px;
        }
    }

    /* Додаткові стилі */
    .stButton > button { font-size: 13px !important; padding: 8px 14px !important; }
    h1, h2, h3 { color: #1e40af; }
    .block-container { padding: 0.5rem 0; max-width: 1400px; }
    .welcome-card {
        background: linear-gradient(135deg, #f8f9fa, #e0f2fe);
        padding: 40px 24px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
#   Конфігурація сторінки
# ────────────────────────────────────────────────
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator", page_icon="🧮", initial_sidebar_state="collapsed")

init_auth_session()
check_subscription_status()

# ────────────────────────────────────────────────
#   Топ-бар (авторизація, статус)
# ────────────────────────────────────────────────
st.markdown('<div class="top-bar">', unsafe_allow_html=True)

if st.session_state.authenticated and st.session_state.user:
    status = "PRO" if st.session_state.is_pro else "Free"
    st.markdown(
        f'<span class="user-info">👤 {st.session_state.user.email}  •  <b>{status}</b></span>',
        unsafe_allow_html=True
    )
    if st.button("Вийти", key="btn_logout_top"):
        from supabase import create_client
        supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
        supabase.auth.sign_out()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
else:
    col_login, col_reg = st.columns([1,1])
    with col_login:
        if st.button("Увійти", key="btn_login_top"):
            login_dialog()
    with col_reg:
        if st.button("Реєстрація", key="btn_reg_top"):
            register_dialog()

st.markdown('</div>', unsafe_allow_html=True)

# ────────────────────────────────────────────────
#   Ліва панель (файли + розрахунок)
# ────────────────────────────────────────────────
st.markdown('<div class="left-panel">', unsafe_allow_html=True)

st.markdown("### 🧮 FIFO Tax")

if "my_files" not in st.session_state:
    st.session_state.my_files = []

st.file_uploader(" ", accept_multiple_files=True, key="hidden_uploader", label_visibility="collapsed")

if st.button("➕ Додати CSV-файли", type="primary"):
    components.html("""
        <script>
            window.parent.document.querySelector('input[type="file"]').click();
        </script>
    """, height=0)

if st.session_state.my_files:
    st.markdown(f"**Завантажено файлів: {len(st.session_state.my_files)}**")
    for idx, file in enumerate(st.session_state.my_files):
        col_name, col_del = st.columns([5,1])
        with col_name:
            st.markdown(f"📄 {file.name}")
        with col_del:
            if st.button("×", key=f"del_file_{idx}", help="Видалити"):
                st.session_state.my_files.pop(idx)
                st.rerun()

    if st.button("🗑️ Очистити список"):
        st.session_state.my_files.clear()
        st.rerun()

    if st.button("🔄 Розрахувати все", type="primary"):
        with st.spinner("Обчислення даних..."):
            st.session_state.broker_data, st.session_state.rates_data = Module1_Data_Import(st.session_state.my_files)
            st.session_state.rates_data = Module2_Currency_Rates(st.session_state.rates_data)
            st.session_state.fifo_df = Module3_FIFO_Data_Compiler(st.session_state.broker_data, st.session_state.rates_data)
            st.session_state.finance_df = Module4_Finance_Data_Compiler(st.session_state.broker_data)
            recalculate_reports("Wszystkie lata")
        st.success("Розрахунок завершено")
        st.rerun()
else:
    st.info("Завантажте файли брокера (Activity, Dividends, etc.)")

st.markdown('</div>', unsafe_allow_html=True)

# ────────────────────────────────────────────────
#   Основний контент
# ────────────────────────────────────────────────
st.markdown('<div class="main-content">', unsafe_allow_html=True)

# Ключі сесії (без змін)
keys = [
    'broker_data', 'rates_data', 'fifo_df', 'finance_df', 'report_blocks',
    'sales_summary', 'profit_summary', 'summary_df', 'summary_sales', 'summary_profit',
    'dividend_df', 'dividend_summary_val', 'dividend_summary_pln',
    'interest_df', 'interest_summary_val', 'interest_summary_pln',
    'cash_df', 'cash_summary', 'transactions_df',
    'portfolio_df', 'portfolio_currency_percent', 'portfolio_currency_value',
    'pit38_akcje', 'pit38_dywidendy', 'pit38_zg',
    'selected_year'
]
for key in keys:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'selected_year' else "Wszystkie lata"

# Допоміжні функції (без змін)
def show_no_data_message(section_name=""):
    msg = "✅ Dane zostały obliczone, ale za wybrany rok brak operacji tego typu."
    if section_name:
        msg = f"✅ {section_name} — dane zostały obliczone, ale za wybrany rok brak operacji."
    st.info(msg)

def style_dataframe(df, tab_name):
    if not st.session_state.get("is_pro", False):
        return df
    if df is None or df.empty:
        return df
    cols_4dec = ["Kurs NBP", "Kurs", "Kurs (USD)", "Koszt sredni", "Kurs NBP (D-1)"]
    cols_percent = ["Stawka zr. %", "Waga %", "Udział %"]
    styler = df.style.set_properties(**{'text-align': 'center'})
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    for col in numeric_cols:
        if col in cols_4dec:
            styler = styler.format({col: "{:,.4f}"})
        elif col in cols_percent:
            styler = styler.format({col: "{:.2%}"})
        else:
            styler = styler.format({col: "{:,.2f}"})
    return styler

def download_excel(data_dict, default_filename, key_suffix=""):
    if not st.session_state.get("is_pro", False):
        st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        return
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in data_dict.items():
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    output.seek(0)
    st.download_button(
        label="⬇️ Завантажити Excel",
        data=output,
        file_name=f"{default_filename}_{st.session_state.selected_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_{key_suffix}"
    )

# Функції рендеру вкладок (без змін, скопійовані з твого коду)
# ────────────────────────────────────────────────
# render_Rates_NBP_Tab, render_FIFO_Data_Tab, ... render_PIT38_Tab
# (вставляю всі функції, які були в твоєму коді)

def render_Rates_NBP_Tab():
    st.subheader("📈 Курси валют NBP")
    styled_df = style_dataframe(st.session_state.rates_data, "Rates_NBP")
    st.dataframe(styled_df, use_container_width=True, height="content")

def render_FIFO_Data_Tab():
    st.subheader("📋 Скомпільовані дані FIFO")
    if st.session_state.fifo_df is not None:
        styled_df = style_dataframe(st.session_state.fifo_df, "FIFO_Data")
        st.dataframe(styled_df, use_container_width=True, height="content")

def render_Finance_Data_Tab():
    st.subheader("💰 Finance Data")
    if st.session_state.finance_df is not None:
        styled_df = style_dataframe(st.session_state.finance_df, "Finance_Data")
        st.dataframe(styled_df, use_container_width=True, height="content")

def render_Tax_Detailed_Report_Tab():
    st.subheader("📑 Детальний податковий звіт (FIFO)")
    blocks = st.session_state.get('report_blocks')
    if blocks is None:
        st.info("Натисніть «Розрахувати все» в лівій панелі")
        return
    if not blocks:
        show_no_data_message("Tax Detailed Report")
        return
    col1, col2 = st.columns([1.4, 1.6])
    with col1:
        st.markdown("**Podsumowanie sprzedaz**")
        if not st.session_state.get("is_pro", False):
            st.dataframe(st.session_state.sales_summary, hide_index=True, height="content")
        else:
            st.dataframe(st.session_state.sales_summary.style.set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**Ogolny profit [PLN]**")
        if not st.session_state.get("is_pro", False):
            st.info("🔒 Підсумковий прибуток доступний тільки для PRO-підписників")
        else:
            def profit_style(row):
                styles = [''] * 2
                if row[" "] == "Przeplyw":
                    styles = ['color: #006100'] * 2 if row["Value"] >= 0 else ['color: #9c0006'] * 2
                return styles
            st.dataframe(st.session_state.profit_summary.style.apply(profit_style, axis=1).format({"Value": "{:,.7f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    if st.session_state.get("is_pro", False):
        blocks_to_show = blocks
    else:
        blocks_to_show = blocks[:5]
        if len(blocks) > 5:
            st.info("🔒 Показано тільки перші 5 транзакцій. Для перегляду всіх придбайте PRO-підписку.")
    for block in blocks_to_show:
        if block.empty:
            continue
        if st.session_state.get("is_pro", False):
            limited_block = apply_free_limits(block, "Tax_Detailed_Report")
            styled = style_dataframe(limited_block, "Tax_Detailed_Report")
            styled = styled.set_table_styles([{'selector': 'tr:last-child td:nth-child(n+2):nth-child(-n+10)', 'props': [('display', 'none')]}])
            st.dataframe(styled, use_container_width=True, height="content")
        else:
            st.dataframe(block, use_container_width=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Detailed Report)", key="dl_tax_detailed"):
        all_blocks = pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()
        download_excel({
            "Blocks": all_blocks,
            "Sales Summary": st.session_state.sales_summary,
            "Profit Summary": st.session_state.profit_summary
        }, "Tax_Detailed_Report", "tax_detailed")

# (всі інші функції рендеру вкладок — render_Tax_Summary_Report_Tab, render_Tax_Dividend_Report_Tab тощо — залишаються точно такими ж, як у твоєму оригінальному коді)

# render_main_tabs (без змін)
def render_main_tabs():
    tabs_names = list(st.session_state.broker_data.keys()) + ["Rates_NBP", "FIFO_Data", "Finance_Data"]
    if st.session_state.get('fifo_df') is not None:
        tabs_names.extend(["Tax_Detailed_Report", "Tax_Summary_Report", "Transactions", "Portfolio"])
    if st.session_state.get('finance_df') is not None:
        tabs_names.extend(["Tax_Dividend", "Tax_Interest", "Cash", "PIT38"])
    tabs = st.tabs(tabs_names)
    for i, name in enumerate(tabs_names):
        with tabs[i]:
            if name in st.session_state.broker_data:
                st.subheader(f"📄 Оригінальні дані: {name}")
                styled_df = style_dataframe(st.session_state.broker_data.get(name), "BrokerData")
                st.dataframe(styled_df, use_container_width=True, height="content")
            elif name == "Rates_NBP":
                render_Rates_NBP_Tab()
            elif name == "FIFO_Data":
                render_FIFO_Data_Tab()
            elif name == "Finance_Data":
                render_Finance_Data_Tab()
            elif name == "Tax_Detailed_Report":
                render_Tax_Detailed_Report_Tab()
            elif name == "Tax_Summary_Report":
                render_Tax_Summary_Report_Tab()
            elif name == "Tax_Dividend":
                render_Tax_Dividend_Report_Tab()
            elif name == "Tax_Interest":
                render_Tax_Interest_Report_Tab()
            elif name == "Cash":
                render_Cash_Report_Tab()
            elif name == "Transactions":
                render_Transactions_Report_Tab()
            elif name == "Portfolio":
                render_Portfolio_Tab()
            elif name == "PIT38":
                render_PIT38_Tab()

# recalculate_reports (без змін)
def recalculate_reports(selected_year):
    if st.session_state.fifo_df is None or st.session_state.finance_df is None:
        return
    blocks, sales_sum, profit_sum = Module5_FIFO_Detailed_Tax_Report(st.session_state.fifo_df, selected_year)
    st.session_state.report_blocks = blocks
    st.session_state.sales_summary = sales_sum
    st.session_state.profit_summary = profit_sum
    main_df, sales_sum6, profit_sum6 = Module6_FIFO_Summary_Tax_Report(st.session_state.fifo_df, selected_year)
    st.session_state.summary_df = main_df
    st.session_state.summary_sales = sales_sum6
    st.session_state.summary_profit = profit_sum6
    d_main, d_val, d_pln = Module7_Dividend_Tax_Report(st.session_state.finance_df, st.session_state.rates_data, selected_year)
    st.session_state.dividend_df = d_main
    st.session_state.dividend_summary_val = d_val
    st.session_state.dividend_summary_pln = d_pln
    i_main, i_val, i_pln = Module8_Interest_Tax_Report(st.session_state.finance_df, st.session_state.rates_data, selected_year)
    st.session_state.interest_df = i_main
    st.session_state.interest_summary_val = i_val
    st.session_state.interest_summary_pln = i_pln
    c_main, c_sum = Module9_Cash_Report(st.session_state.finance_df, st.session_state.rates_data, selected_year)
    st.session_state.cash_df = c_main
    st.session_state.cash_summary = c_sum
    st.session_state.transactions_df = Module10_Transactions_Report(st.session_state.fifo_df, selected_year)
    portfolio_df, curr_percent, curr_value = Module11_Portfolio(st.session_state.fifo_df, st.session_state.rates_data)
    st.session_state.portfolio_df = portfolio_df
    st.session_state.portfolio_currency_percent = curr_percent
    st.session_state.portfolio_currency_value = curr_value
    akcje, dyw, zg = Module12_PIT38_Report(st.session_state.fifo_df, st.session_state.finance_df, st.session_state.rates_data, selected_year)
    st.session_state.pit38_akcje = akcje
    st.session_state.pit38_dywidendy = dyw
    st.session_state.pit38_zg = zg
    st.session_state.selected_year = selected_year

# render_global_year_selector (без змін)
def render_global_year_selector():
    if st.session_state.fifo_df is None and st.session_state.finance_df is None:
        return
    years = set()
    if st.session_state.fifo_df is not None and not st.session_state.fifo_df.empty:
        years.update(st.session_state.fifo_df['Date'].dt.year.dropna().unique())
    if st.session_state.finance_df is not None and not st.session_state.finance_df.empty:
        years.update(pd.to_datetime(st.session_state.finance_df['Date'], errors='coerce').dt.year.dropna().unique())
    year_options = ["Wszystkie lata"] + sorted([str(y) for y in years])
    current_index = 0
    if st.session_state.selected_year in year_options:
        current_index = year_options.index(st.session_state.selected_year)
    def on_year_change():
        new_year = st.session_state.global_year
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Зміна року доступна тільки для PRO-підписників")
            st.session_state.global_year = st.session_state.selected_year
        else:
            if new_year != st.session_state.selected_year:
                recalculate_reports(new_year)
    st.markdown('<div style="margin-top: 10px;"></div>', unsafe_allow_html=True)
    col_label, col_selector = st.columns([1, 1], vertical_alignment="center", gap="xxsmall")
    with col_label:
        st.markdown("**Wybierz rok:**")
    with col_selector:
        st.selectbox(
            label="",
            options=year_options,
            key="global_year",
            index=current_index,
            on_change=on_year_change,
            label_visibility="collapsed"
        )

# ────────────────────────────────────────────────
#   Логіка запуску
# ────────────────────────────────────────────────
if st.session_state.broker_data is not None:
    render_global_year_selector()
    render_main_tabs()
else:
    st.markdown('<div class="welcome-card">', unsafe_allow_html=True)
    st.markdown("""
    <h1 style="text-align:center;">🧮 FIFO Tax Calculator</h1>
    <p style="text-align:center; font-size:1.3rem; margin:20px 0;">
        Сучасний калькулятор податків для інвесторів з Польщі
    </p>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.info("📥 Завантажте CSV-файли брокера в лівій панелі та натисніть «Розрахувати все»")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.image("https://picsum.photos/id/1015/800/400", use_column_width=True)

st.markdown('</div>', unsafe_allow_html=True)  # закриття .main-content
