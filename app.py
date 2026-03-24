# ===========================================================================================================================================
# app.py — Головний UI Streamlit-застосунку (НОВИЙ СУЧАСНИЙ ДИЗАЙН + МОДАЛЬНИЙ ЛОГІН)
# ===============================================================================================================================================
import streamlit as st
import pandas as pd
import io
import streamlit.components.v1 as components
from auth import (
    init_auth_session,
    show_auth_status_and_logout,
    require_pro_for_feature,
    apply_free_limits,
    check_subscription_status
)
# Імпортуємо всі функції з бекенду
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


# ====================== ІНІЦІАЛІЗАЦІЯ ==================================================================================================================
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator", page_icon="🧮")
init_auth_session()

# Додаємо заголовок у сайдбар ДО кнопок авторизації
with st.sidebar:
    st.title("🧮 Калькулятор податків FIFO")
    st.markdown("---")

show_auth_status_and_logout()


# ====================== СУЧАСНИЙ CSS ================================================================================================================
st.markdown("""
<style>
    .stAppHeader { background: transparent; height: 0; }                           /* Головний хедер (верхня панель з навігацією) робимо прозорим і з нульовою висотою */
    a[data-testid="stLogo"] { display: none; }                                     /* Ховаємо логотип Streamlit, який за замовчуванням з'являється зліва в хедері */
    div[data-testid="stDecoration"] { display: none; }                             /* Ховаємо декоративний елемент (лінію або тінь), який додається автоматично */
    button[data-testid="baseButton-header"] { display: none !important; }          /* Ховаємо кнопку, що відповідає за розгортання/згортання сайдбару в хедері */
    .main > div:first-child { padding-top: 0.5rem; }                               /* Для основного контенту: зменшуємо відступ зверху від першого дочірнього елемента */
    .block-container { padding-top: 1rem; }                                        /* Зменшуємо відступ зверху для контейнера з усім вмістом сторінки (блок контенту) */
    #MainMenu {visibility: hidden;}                                                /* Ховаємо стандартне меню Streamlit (три крапки у верхньому правому куті) */
    footer {visibility: hidden;}                                                   /* Ховаємо футер (напис "Made with Streamlit") */
    h1, h2, h3 { color: #1a3c5e; }                                                 /* Встановлюємо колір для заголовків h1, h2, h3 по всьому застосунку */
    .welcome-card {                                                                /* Стилі для привітальної картки, яка показується, коли немає даних */
        background: linear-gradient(135deg, #f8f9fa, #e9f0ff);
        padding: 40px;
        border-radius: 16px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }

    /* Третій варіант: абсолютне позиціонування заголовка */
    section[data-testid="stSidebar"] {
        position: relative;                                /* Робимо сайдбар відносним для абсолютного позиціонування */
        overflow-x: hidden;                                /* Щоб нічого не вилазило */
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 40px;                                 /* Додаємо відступ зверху, щоб вміст не накладався на заголовок */
    }
    section[data-testid="stSidebar"] h1 {
        position: absolute;                                /* Абсолютне позиціонування */
        top: 0;                                            /* Притискаємо до верху сайдбару */
        left: 20px;                                        /* Відступ зліва (можна змінити, щоб не перекривати кнопку) */
        margin: 0;
        padding: 0;
        z-index: 10;                                       /* Щоб був поверх кнопки */
        font-size: 1.5rem;                                 /* За бажанням, можна змінити розмір */
    }
</style>
""", unsafe_allow_html=True)

# ====================== КЛЮЧІ СЕСІЇ =====================================================================================================================
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

# ====================== ДОПОМІЖНІ ФУНКЦІЇ ======================
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

# ====================== ФУНКЦІЇ ВКЛАДОК ================================================================================================================
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
        all_blocks = pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()
        download_excel({
            "Blocks": all_blocks,
            "Sales Summary": st.session_state.sales_summary,
            "Profit Summary": st.session_state.profit_summary
        }, "Tax_Detailed_Report", "tax_detailed")

def render_Tax_Summary_Report_Tab():
    st.subheader("📊 Tax Report — підсумковий податковий звіт (FIFO Summary)")
    df = st.session_state.get('summary_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Summary Report")
        return
    col1, col2 = st.columns([1.4, 1.6])
    with col1:
        st.markdown("**Podsumowanie sprzedaz**")
        if not st.session_state.get("is_pro", False):
            st.dataframe(st.session_state.summary_sales, hide_index=True, height="content")
        else:
            st.dataframe(st.session_state.summary_sales.style.set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
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
            st.dataframe(st.session_state.summary_profit.style.apply(profit_style, axis=1).format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**Детальна таблиця продажів**")
    limited_df = apply_free_limits(df, "Tax_Summary_Report")
    if not st.session_state.get("is_pro", False):
        st.dataframe(limited_df, use_container_width=True, height="content")
        if len(df) > 5:
            st.info("🔒 Показано тільки перші 5 рядків. Для перегляду всіх придбайте PRO-підписку.")
    else:
        styled = style_dataframe(limited_df, "Tax_Summary_Report")
        styled = styled.apply(lambda x: ['color: #006100' if v >= 0 else 'color: #9c0006' for v in x], subset=['Przeplyw PLN'])
        st.dataframe(styled, use_container_width=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Summary Report)", key="dl_tax_summary"):
        download_excel({
            "Summary": st.session_state.summary_df,
            "Sales Summary": st.session_state.summary_sales,
            "Profit Summary": st.session_state.summary_profit
        }, "Tax_Summary_Report", "tax_summary")

def render_Tax_Dividend_Report_Tab():
    st.subheader("💰 Tax Dividend — податковий звіт по дивідендах")
    df = st.session_state.get('dividend_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Dividend")
        return
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Підсумування в валюті**")
        if not st.session_state.get("is_pro", False):
            st.info("🔒 Дані приховані")
        else:
            st.dataframe(st.session_state.dividend_summary_val.style.set_properties(**{'font-weight': 'bold'}).format({"Value": "{:,.2f}"}), hide_index=True, height="content")
    with col2:
        st.markdown("**Підсумування (PLN)**")
        if not st.session_state.get("is_pro", False):
            st.info("🔒 Дані приховані")
        else:
            def pln_style(row):
                styles = [''] * 2
                if row[" "] in ["Doplata w PL", "Pod. u zrodla"]:
                    styles = ['color: #9c0006'] * 2
                elif row[" "] == "Suma Netto":
                    styles = ['color: #006100'] * 2 if row["Value"] >= 0 else ['color: #9c0006'] * 2
                return styles
            st.dataframe(st.session_state.dividend_summary_pln.style.apply(pln_style, axis=1).format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**Детальна таблиця дивідендів**")
    limited_df = apply_free_limits(df, "Tax_Dividend")
    if not st.session_state.get("is_pro", False):
        st.dataframe(limited_df, use_container_width=True, height="content")
        if len(df) > 3:
            st.info("🔒 Показано тільки перші 3 рядки. Для перегляду всіх придбайте PRO-підписку.")
    else:
        styled = style_dataframe(limited_df, "Tax_Dividend")
        st.dataframe(styled, use_container_width=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Dividend Report)", key="dl_tax_dividend"):
        download_excel({
            "Dividends": st.session_state.dividend_df,
            "Summary (Val)": st.session_state.dividend_summary_val,
            "Summary (PLN)": st.session_state.dividend_summary_pln
        }, "Tax_Dividend", "tax_dividend")

def render_Tax_Interest_Report_Tab():
    st.subheader("📈 Tax Interest — податковий звіт по відсотках")
    df = st.session_state.get('interest_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Interest")
        return
    col1, col2 = st.columns([1.3, 1.7])
    with col1:
        st.markdown("**Podsumowanie (VAL)**")
        if not st.session_state.get("is_pro", False):
            st.info("🔒 Дані приховані")
        else:
            st.dataframe(st.session_state.interest_summary_val.style.set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**Podsumowanie (PLN)**")
        if not st.session_state.get("is_pro", False):
            st.info("🔒 Дані приховані")
        else:
            st.dataframe(st.session_state.interest_summary_pln.style.format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**Детальна таблиця відсотків**")
    limited_df = apply_free_limits(df, "Tax_Interest")
    if not st.session_state.get("is_pro", False):
        st.dataframe(limited_df, use_container_width=True, height="content")
        if len(df) > 3:
            st.info("🔒 Показано тільки перші 3 рядки. Для перегляду всіх придбайте PRO-підписку.")
    else:
        styled = style_dataframe(limited_df, "Tax_Interest")
        st.dataframe(styled, use_container_width=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Interest Report)", key="dl_tax_interest"):
        download_excel({
            "Interest": st.session_state.interest_df,
            "Summary (Val)": st.session_state.interest_summary_val,
            "Summary (PLN)": st.session_state.interest_summary_pln
        }, "Tax_Interest", "tax_interest")

def render_Cash_Report_Tab():
    st.subheader("💵 Cash Report — рух готівки")
    df = st.session_state.get('cash_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Cash Report")
        return
    if not st.session_state.get("is_pro", False):
        st.dataframe(df, use_container_width=True, height="content")
    else:
        styled = style_dataframe(df, "Cash")
        st.dataframe(styled, use_container_width=True, height="content")
    st.markdown("**Підсумки**")
    st.dataframe(st.session_state.cash_summary, hide_index=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Cash Report)", key="dl_cash"):
        download_excel({
            "Cash": st.session_state.cash_df,
            "Summary": st.session_state.cash_summary
        }, "Cash_Report", "cash")

def render_Transactions_Report_Tab():
    st.subheader("📋 Transactions Report")
    df = st.session_state.get('transactions_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Transactions Report")
        return
    if not st.session_state.get("is_pro", False):
        st.dataframe(df, use_container_width=True, height="content")
    else:
        styled = style_dataframe(df, "Transactions")
        st.dataframe(styled, use_container_width=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Transactions Report)", key="dl_transactions"):
        download_excel({
            "Transactions": st.session_state.transactions_df
        }, "Transactions", "transactions")

def render_Portfolio_Tab():
    st.subheader("📊 Portfolio — поточний стан портфеля")
    df = st.session_state.get('portfolio_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Portfolio")
        return
    st.markdown("**Основна таблиця портфеля**")
    if not st.session_state.get("is_pro", False):
        st.dataframe(df, use_container_width=True, height="content")
    else:
        styled = style_dataframe(df, "Portfolio")
        st.dataframe(styled, use_container_width=True, height="content")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Структура за валютою (уділ %)**")
        st.dataframe(st.session_state.portfolio_currency_percent, hide_index=True, height="content")
    with col2:
        st.markdown("**Вартість за валютою (оригінальна)**")
        st.dataframe(st.session_state.portfolio_currency_value, hide_index=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Portfolio)", key="dl_portfolio"):
        download_excel({
            "Portfolio": st.session_state.portfolio_df,
            "Currency Percent": st.session_state.portfolio_currency_percent,
            "Currency Value": st.session_state.portfolio_currency_value
        }, "Portfolio", "portfolio")

def render_PIT38_Tab():
    st.subheader("📋 PIT-38 — підсумковий податковий звіт")
    akcje = st.session_state.get('pit38_akcje')
    if akcje is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if st.session_state.get("is_pro", False):
        akcje_display = akcje
        dyw_display = st.session_state.pit38_dywidendy
        zg_display = st.session_state.pit38_zg
    else:
        akcje_display = apply_free_limits(akcje, "PIT38")
        dyw_display = apply_free_limits(st.session_state.pit38_dywidendy, "PIT38")
        zg_display = apply_free_limits(st.session_state.pit38_zg, "PIT38")
        st.info("🔒 Дані PIT-38 приховані для free-користувачів. Купіть підписку для доступу.")
    st.markdown("**PIT-38 - Akcje i Koszty**")
    if st.session_state.get("is_pro", False):
        styled = style_dataframe(akcje_display, "PIT38")
        st.dataframe(styled, hide_index=True, height="content")
    else:
        st.dataframe(akcje_display, hide_index=True, height="content")
    st.markdown("**PIT-38 - Dywidendy**")
    if st.session_state.get("is_pro", False):
        styled = style_dataframe(dyw_display, "PIT38")
        st.dataframe(styled, hide_index=True, height="content")
    else:
        st.dataframe(dyw_display, hide_index=True, height="content")
    st.markdown("**PIT-38 - Podatek do zaplaty**")
    if st.session_state.get("is_pro", False):
        akcje_wartosc = safe_get_loc(akcje, 12, "Wartosc")
        dyw_wartosc = safe_get_loc(st.session_state.pit38_dywidendy, 4, "Wartosc")
        podatek_do_zaplaty = max(0, akcje_wartosc + dyw_wartosc)
        podatek_df = pd.DataFrame({
            "Komorka": ["G.51"],
            "Nazwa": ["PODATEK DO ZAPLATY<br>Od sumy kwot z poz. 35, 45, 46 i 49 należy odjąć kwotę z poz. 50. Jeżeli różnica jest liczbą ujemną, należy wpisać 0."],
            "Wartosc": [podatek_do_zaplaty]
        })
        styled = style_dataframe(podatek_df, "PIT38")
        st.dataframe(styled, hide_index=True, height="content")
    else:
        podatek_df = pd.DataFrame({"Komorka": ["G.51"], "Nazwa": ["PODATEK DO ZAPLATY"], "Wartosc": ["X"]})
        st.dataframe(podatek_df, hide_index=True, height="content")
    st.markdown("**PIT/ZG — Zagraniczne przychody**")
    if not st.session_state.get("is_pro", False):
        st.info("🔒 Дані приховані")
    else:
        styled = style_dataframe(zg_display, "PIT38")
        st.dataframe(styled, hide_index=True, height="content")
    st.markdown("---")
    if st.button("📥 Завантажити Excel (PIT-38)", key="dl_pit38"):
        download_excel({
            "Akcje": st.session_state.pit38_akcje,
            "Dywidendy": st.session_state.pit38_dywidendy,
            "PIT_ZG": st.session_state.pit38_zg
        }, "PIT-38", "pit38")

# ====================== БОКОВА ПАНЕЛЬ ============================================================================================================================
def update_file_list():
    new_files = st.session_state.hidden_uploader
    if new_files:
        for f in new_files:
            if f.name not in [file.name for file in st.session_state.my_files]:
                st.session_state.my_files.append(f)

def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <style>
            div[data-testid="stFileUploader"] { display: none !important; }
            div[data-testid="stSidebar"] .stButton button { width: 100% !important; }
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

# ====================== ОБРОБКА ЗМІНИ РОКУ ТА ПЕРЕРАХУНОК ==================================================================================================================
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

# ====================== ЗАПУСК ======================
render_sidebar()

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
    st.info("📥 Завантажте CSV-файли брокера в боковій панелі та натисніть «Розрахувати все»")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.image("https://picsum.photos/id/1015/800/400", use_column_width=True)
