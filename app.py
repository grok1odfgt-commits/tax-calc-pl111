# ==============================================================================
# app.py — Головний UI Streamlit-застосунку
# ==============================================================================
import streamlit as st
import pandas as pd
import io
import streamlit.components.v1 as components
from auth import (
    require_auth,
    show_auth_status_and_logout,
    require_pro_for_feature,
    apply_free_limits,
    check_subscription_status
)
# Імпортуємо всі функції з бекенду
from tax_calculator import (
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

# ====================== CSS ======================
st.markdown("""
<style>
    .stDataFrame, div[data-testid="stDataFrame"] {
        max-height: none !important;
        height: auto !important;
    }
    .ag-theme-streamlit {
        max-height: none !important;
        height: auto !important;
    }
    header[data-testid="stHeader"] {
        display: none;
    }
    .main > div:first-child {
        padding-top: 0rem;
    }
    .block-container {
        padding-top: 0rem;
        margin-top: -0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ====================== ІНІЦІАЛІЗАЦІЯ СЕСІЇ ======================
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

# ====================== ДОПОМІЖНІ ФУНКЦІЇ UI ======================
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
    styler = df.style
    styler = styler.set_properties(**{'text-align': 'center'})
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
    """Універсальна функція для завантаження Excel."""
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

# ====================== ВСІ ФУНКЦІЇ ВІДОБРАЖЕННЯ ВКЛАДОК ======================
# (Тут потрібно скопіювати всі render_*_Tab з оригінального коду,
#  але замінити виклики стилів на style_dataframe,
#  та замінити повторювані частини завантаження Excel на виклик download_excel)
# Для економії місця я покажу лише одну як приклад, але в повному файлі будуть усі.

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
        st.info("Натисніть «Розрахувати все» в боковій панелі")
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
        download_excel({
            "Blocks": pd.concat(blocks) if blocks else pd.DataFrame(),
            "Sales Summary": st.session_state.sales_summary,
            "Profit Summary": st.session_state.profit_summary
        }, "Tax_Detailed_Report", "tax_detailed")

# ... (аналогічно для інших вкладок)

# ====================== БОКОВА ПАНЕЛЬ ======================
def update_file_list():
    new_files = st.session_state.hidden_uploader
    if new_files:
        for f in new_files:
            if f.name not in [file.name for file in st.session_state.my_files]:
                st.session_state.my_files.append(f)

def render_sidebar():
    with st.sidebar:
        st.title("🧮 Калькулятор податків FIFO")
        st.markdown("---")
        st.markdown("""
        <style>
            div[data-testid="stFileUploader"] { display: none !important; }
            div[data-testid="stSidebar"] .stButton button { width: 100% !important; }
            section[data-testid="stSidebar"] p { font-size: 15px !important; line-height: 1.4 !important; }
        </style>
        """, unsafe_allow_html=True)
        if "my_files" not in st.session_state:
            st.session_state.my_files = []
        st.file_uploader(" ", accept_multiple_files=True, key="hidden_uploader",
                         label_visibility="collapsed", on_change=update_file_list)
        if st.button("📁 Додати файли (CSV)", type="primary", use_container_width=True):
            components.html("""
                <script>
                    window.parent.document.querySelector('input[type="file"]').click();
                </script>
            """, height=0)
        if st.session_state.my_files:
            st.write(f"**Завантажено {len(st.session_state.my_files)} файлів:**")
            for i, file in enumerate(st.session_state.my_files):
                col1, col2 = st.columns([0.78, 0.22])
                size_kb = round(file.size / 1024, 1)
                col1.write(f"📄 **{file.name}** \n({size_kb} KB)")
                if col2.button("❌", key=f"del_{i}"):
                    st.session_state.my_files.pop(i)
                    st.rerun()
            if st.button("🗑️ Очистити всі", use_container_width=True):
                st.session_state.my_files.clear()
                st.rerun()
            if st.button("🔄 Розрахувати все", type="primary", use_container_width=True):
                with st.spinner("Виконується повний розрахунок за всі роки..."):
                    st.session_state.broker_data, st.session_state.rates_data = Module1_Data_Import(st.session_state.my_files)
                    st.session_state.rates_data = Module2_Currency_Rates(st.session_state.rates_data)
                    st.session_state.fifo_df = Module3_FIFO_Data_Compiler(st.session_state.broker_data, st.session_state.rates_data)
                    st.session_state.finance_df = Module4_Finance_Data_Compiler(st.session_state.broker_data)
                    recalculate_reports("Wszystkie lata")
                st.success("✅ Усе розраховано!")
                st.rerun()
        else:
            st.info("Завантажте файли, щоб з’явилася кнопка «Розрахувати все»")
    return st.session_state.my_files

# ====================== ОБРОБКА ЗМІНИ РОКУ ТА ПЕРЕРАХУНОК ======================
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
            # ... (решта вкладок аналогічно)

# ====================== ЗАПУСК ======================
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator")
require_auth()
check_subscription_status()
show_auth_status_and_logout()
uploaded_files = render_sidebar()
if st.session_state.broker_data is not None:
    render_global_year_selector()
    render_main_tabs()
else:
    st.markdown('<div style="margin-top: 30px;"></div>', unsafe_allow_html=True)
    st.info("Будь ласка, завантажте CSV файли брокера та натисніть «Розрахувати все».")
