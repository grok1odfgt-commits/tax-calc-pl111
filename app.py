# ==============================================================================
# ==============================================================================
# КАЛЬКУЛЯТОР ПОДАТКІВ FIFO — ВСІ ТАБЛИЦІ ПОКАЗУЮТЬ ВСІ РЯДКИ (height="content")
# ==============================================================================
# ==============================================================================
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import io

# ==============================================================================
# ============================ ДОДАНО ДЛЯ АВТОРИЗАЦІЇ ===========================
# ==============================================================================
# Ці рядки дозволяють використовувати функції з файлу auth.py
from auth import require_auth, show_auth_status_and_logout, require_pro_for_feature, apply_free_limits
# ==============================================================================

# ==============================================================================
# CSS — гарантуємо повну висоту контенту
# ==============================================================================
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
    .ag-theme-streamlit .ag-body-viewport,
    .ag-theme-streamlit .ag-center-cols-viewport {
        max-height: none !important;
        height: auto !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# ІНІЦІАЛІЗАЦІЯ СЕСІЙНОГО СТАНУ
# ==============================================================================
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

# ==============================================================================
# УНІВЕРСАЛЬНЕ ПОВІДОМЛЕННЯ "БРАК ДАНИХ ЗА РІК"
# ==============================================================================
def show_no_data_message(section_name=""):
    """Єдине повідомлення для всіх вкладок, коли за вибраний рік немає даних"""
    msg = "✅ Dane zostały obliczone, ale za wybrany rok brak operacji tego typu."
    if section_name:
        msg = f"✅ {section_name} — dane zostały obliczone, ale za wybrany rok brak operacji."
    st.info(msg)

# ==============================================================================
# SIDEBAR (твій оригінальний код без змін)
# ==============================================================================
import streamlit.components.v1 as components

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
        st.subheader("📥 Завантаження даних")
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

# ==============================================================================
# ТВОЇ МОДУЛІ (без жодних змін)
# ==============================================================================
# ... (всі твої функції Module1, Module2, ..., Module12 залишаються точно такими ж, як були)

def Module1_Data_Import(uploaded_files):
    all_data = {}
    unique_currencies = set()
    min_date = datetime.now().date()
    for file in uploaded_files:
        df = pd.read_csv(file)
        df.columns = [c.strip().lower() for c in df.columns]
        file_name = file.name.replace(".csv", "")
        if 'datetime' in df.columns:
            df['date_fmt'] = pd.to_datetime(df['datetime'].astype(str).str[:8], format='%Y%m%d', errors='coerce').dt.strftime('%Y-%m-%d')
        elif 'date' in df.columns:
            df['date_fmt'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        all_data[file_name] = df
        if 'currencyprimary' in df.columns:
            for c in df['currencyprimary'].dropna().unique():
                c_s = str(c).strip().upper()
                if len(c_s) == 3 and c_s != "PLN":
                    unique_currencies.add(c_s)
        if 'date_fmt' in df.columns:
            m = pd.to_datetime(df['date_fmt']).min().date()
            if m < min_date: min_date = m
    date_range = pd.date_range(start=min_date - timedelta(days=7), end=datetime.now().date())
    rates_df = pd.DataFrame({'Date': date_range.strftime('%Y-%m-%d')})
    for cur in sorted(list(unique_currencies)):
        rates_df[cur] = None
    return all_data, rates_df

# ... (всі інші Module2 ... Module12 — без змін, я їх пропускаю для економії місця, але вони залишаються такими ж)

# ==============================================================================
# RENDER ФУНКЦІЇ — з обмеженнями для FREE
# ==============================================================================
def render_Rates_NBP_Tab():
    st.subheader("📈 Курси валют NBP")
    st.dataframe(st.session_state.rates_data, use_container_width=True, height="content")

def render_FIFO_Data_Tab():
    st.subheader("📋 Скомпільовані дані FIFO")
    if st.session_state.fifo_df is not None:
        st.dataframe(st.session_state.fifo_df, use_container_width=True, height="content")

def render_Finance_Data_Tab():
    st.subheader("💰 Finance Data")
    if st.session_state.finance_df is not None:
        st.dataframe(st.session_state.finance_df, use_container_width=True, height="content")

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
        st.dataframe(st.session_state.sales_summary.style.set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**Ogolny profit [PLN]**")
        def profit_style(row):
            styles = [''] * 2
            if row[" "] == "Przeplyw":
                styles = ['color: #006100'] * 2 if row["Value"] >= 0 else ['color: #9c0006'] * 2
            return styles
        st.dataframe(st.session_state.profit_summary.style.apply(profit_style, axis=1).format({"Value": "{:,.7f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")

    for block in blocks:
        if block.empty: continue
        # === ДОДАНО ОБМЕЖЕННЯ ДЛЯ FREE ===
        limited_block = apply_free_limits(block, "Tax_Detailed_Report")
        def safe_format(x):
            if pd.isna(x) or isinstance(x, str): return x if isinstance(x, str) else ""
            return f"{float(x):,.7f}"
        styled = limited_block.style.map(lambda v: 'color: #9c0006' if isinstance(v, (int, float)) and v < 0 else 'color: #006100', subset=['Przepływ [PLN]']).format({"Cena": safe_format, "Kwota": safe_format, "Prowizja": safe_format, "Jednostki": safe_format, "Przychod [PLN]": safe_format, "Koszt [PLN]": safe_format, "Przepływ [PLN]": safe_format, "Kurs NBP": safe_format})
        styled = styled.set_table_styles([{'selector': 'tr:last-child td:nth-child(n+2):nth-child(-n+10)', 'props': [('display', 'none')]}])
        st.dataframe(styled, use_container_width=True, height="content")

def render_Tax_Summary_Report_Tab():
    st.subheader("📊 Tax Report — підсумковий податковий звіт (FIFO Summary)")
    df = st.session_state.get('summary_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Summary Report")
        return

    # === ДОДАНО ОБМЕЖЕННЯ ДЛЯ FREE ===
    limited_df = apply_free_limits(df, "Tax_Summary_Report")

    col1, col2 = st.columns([1.4, 1.6])
    with col1:
        st.markdown("**Podsumowanie sprzedaz**")
        st.dataframe(st.session_state.summary_sales.style.set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**Ogolny profit [PLN]**")
        def profit_style(row):
            styles = [''] * 2
            if row[" "] == "Przeplyw":
                styles = ['color: #006100'] * 2 if row["Value"] >= 0 else ['color: #9c0006'] * 2
            return styles
        st.dataframe(st.session_state.summary_profit.style.apply(profit_style, axis=1).format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**Детальна таблиця продажів**")
    styled = limited_df.style.format({"Przeplyw PLN": "{:,.2f}", "Data sprzedazy": lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ""}).apply(lambda x: ['color: #006100' if v >= 0 else 'color: #9c0006' for v in x], subset=['Przeplyw PLN'])
    st.dataframe(styled, use_container_width=True, height="content")

def render_Tax_Dividend_Report_Tab():
    st.subheader("💰 Tax Dividend — податковий звіт по дивідендах")
    df = st.session_state.get('dividend_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Dividend")
        return

    # === ДОДАНО ОБМЕЖЕННЯ ДЛЯ FREE ===
    limited_df = apply_free_limits(df, "Tax_Dividend")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Підсумування в валюті**")
        st.dataframe(st.session_state.dividend_summary_val.style.set_properties(**{'font-weight': 'bold'}).format({"Value": "{:,.2f}"}), hide_index=True, height="content")
    with col2:
        st.markdown("**Підсумування (PLN)**")
        def pln_style(row):
            styles = [''] * 2
            if row[" "] in ["Doplata w PL", "Pod. u zrodla"]: styles = ['color: #9c0006'] * 2
            elif row[" "] == "Suma Netto": styles = ['color: #006100'] * 2 if row["Value"] >= 0 else ['color: #9c0006'] * 2
            return styles
        st.dataframe(st.session_state.dividend_summary_pln.style.apply(pln_style, axis=1).format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**Детальна таблиця дивідендів**")
    styled = limited_df.style.format({
        "Data": lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else "",
        "Data NBP": lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else "",
        "Przychod": "{:,.2f}", "Pod. zrodlo": "{:,.2f}", "Netto (Wal)": "{:,.2f}",
        "Stawka zr. %": "{:.2%}", "Kurs": "{:,.4f}",
        "Przychod (PLN)": "{:,.2f}", "Pod. zr. (PLN)": "{:,.2f}",
        "Pod. PL (19%)": "{:,.2f}", "Doplata (PLN)": "{:,.2f}", "Netto (PLN)": "{:,.2f}"
    })
    st.dataframe(styled, use_container_width=True, height="content")

def render_Tax_Interest_Report_Tab():
    st.subheader("📈 Tax Interest — податковий звіт по відсотках")
    df = st.session_state.get('interest_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Interest")
        return

    # === ДОДАНО ОБМЕЖЕННЯ ДЛЯ FREE ===
    limited_df = apply_free_limits(df, "Tax_Interest")

    col1, col2 = st.columns([1.3, 1.7])
    with col1:
        st.markdown("**Podsumowanie (VAL)**")
        st.dataframe(st.session_state.interest_summary_val.style.set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**Podsumowanie (PLN)**")
        st.dataframe(st.session_state.interest_summary_pln.style.format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**Детальна таблиця відсотків**")
    st.dataframe(limited_df.style.format({"Data": lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else "", "Data NBP": lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else "", "Przychod": "{:,.2f}", "Pod. zrodlo": "{:,.2f}", "Netto": "{:,.2f}", "Stawka zr. %": "{:.2%}", "Kurs": "{:,.4f}", "Przychod (PLN)": "{:,.2f}", "Pod. zr. (PLN)": "{:,.2f}", "Pod. PL (19%)": "{:,.2f}", "Doplata (PLN)": "{:,.2f}", "Netto (PLN)": "{:,.2f}"}), use_container_width=True, height="content")

def render_Cash_Report_Tab():
    st.subheader("💵 Cash Report — рух готівки")
    df = st.session_state.get('cash_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Cash Report")
        return
    st.dataframe(st.session_state.cash_df.style.format({"Data": lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else "", "Kwota (PLN)": "{:,.2f}", "Kwota (USD)": "{:,.2f}", "Kurs (USD)": "{:,.4f}"}), use_container_width=True, height="content")
    st.markdown("**Підсумки**")
    st.dataframe(st.session_state.cash_summary.style.format({"Value": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")

def render_Transactions_Report_Tab():
    st.subheader("📋 Transactions Report")
    df = st.session_state.get('transactions_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Transactions Report")
        return
    styled = st.session_state.transactions_df.style.format({
        "Data i Czas": lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(x) else "",
        "Jednostki": "{:,.4f}", "Cena": "{:,.4f}", "Kwota": "{:,.2f}", "Prowizja": "{:,.2f}"
    })
    st.dataframe(styled, use_container_width=True, height="content")

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
    st.dataframe(st.session_state.portfolio_df.style.format({"Ilosc": "{:g}","Koszt sredni": "{:,.4f}","Suma покупки": "{:,.2f}","Waga %": "{:.2%}"}), use_container_width=True, height="content")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Структура за валютою (уділ %)**")
        st.dataframe(st.session_state.portfolio_currency_percent.style.format({"Udział %": "{:.2%}"}), hide_index=True, height="content")
    with col2:
        st.markdown("**Вартість за валютою (оригінальна)**")
        st.dataframe(st.session_state.portfolio_currency_value.style.format({"Wartosc": "{:,.2f}"}), hide_index=True, height="content")

def render_PIT38_Tab():
    st.subheader("📋 PIT-38 — підсумковий податковий звіт")
    # === ДОДАНО ОБМЕЖЕННЯ ДЛЯ FREE — повне блокування вкладки ===
    if not st.session_state.get("is_pro", False):
        st.warning("🔒 PIT-38 доступний тільки для підписників")
        st.info("Після оплати напишіть мені свій email — активую за 5 хвилин")
        return

    akcje = st.session_state.get('pit38_akcje')
    if akcje is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if akcje.empty:
        show_no_data_message("PIT-38")
        return
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PIT-38 - Akcje i Koszty**")
        st.dataframe(st.session_state.pit38_akcje.style.format({"Wartosc": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**PIT-38 - Dywidendy**")
        st.dataframe(st.session_state.pit38_dywidendy.style.format({"Wartosc": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**PIT-38 - Podatek do zaplaty**")
    podatek_do_zaplaty = max(0, st.session_state.pit38_akcje.loc[12, "Wartosc"] + st.session_state.pit38_dywidendy.loc[4, "Wartosc"])
    podatek_df = pd.DataFrame({"Komorka": ["G.51"], "Nazwa": ["PODATEK DO ZAPLATY<br>Od sumy kwot z poz. 35, 45, 46 i 49 należy odjąć kwotę z poz. 50. Jeżeli różnica jest liczbą ujemną, należy wpisać 0."], "Wartosc": [podatek_do_zaplaty]})
    st.dataframe(podatek_df.style.format({"Wartosc": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    st.markdown("**PIT/ZG — Zagraniczne przychody**")
    st.dataframe(st.session_state.pit38_zg.style.format({"Inne przychody, w tym uzyskane za granicą - Dochod": "{:,.2f}", "Podatek od innych przychodów zapłacony za granicą": "{:,.2f}"}), hide_index=True, height="content")
    if st.button("📥 Завантажити Excel PIT-38.xlsx"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            st.session_state.pit38_akcje.to_excel(writer, sheet_name="Akcje", index=False)
            st.session_state.pit38_dywidendy.to_excel(writer, sheet_name="Dywidendy", index=False)
            st.session_state.pit38_zg.to_excel(writer, sheet_name="PIT_ZG", index=False)
        output.seek(0)
        st.download_button(label="⬇️ Завантажити PIT-38.xlsx", data=output, file_name=f"PIT-38_{st.session_state.selected_year}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==============================================================================
# recalculate_reports + селектор року + вкладки
# ==============================================================================
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
    def on_year_change():
        year = st.session_state.global_year
        if year != st.session_state.get('selected_year'):
            recalculate_reports(year)
    col_left, _ = st.columns([1, 5])
    with col_left:
        st.selectbox("Wybierz rok:", options=year_options, key="global_year",
                     index=year_options.index(st.session_state.selected_year) if st.session_state.selected_year in year_options else 0,
                     on_change=on_year_change)

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
                st.dataframe(st.session_state.broker_data.get(name), use_container_width=True, height="content")
            elif name == "Rates_NBP": render_Rates_NBP_Tab()
            elif name == "FIFO_Data": render_FIFO_Data_Tab()
            elif name == "Finance_Data": render_Finance_Data_Tab()
            elif name == "Tax_Detailed_Report": render_Tax_Detailed_Report_Tab()
            elif name == "Tax_Summary_Report": render_Tax_Summary_Report_Tab()
            elif name == "Tax_Dividend": render_Tax_Dividend_Report_Tab()
            elif name == "Tax_Interest": render_Tax_Interest_Report_Tab()
            elif name == "Cash": render_Cash_Report_Tab()
            elif name == "Transactions": render_Transactions_Report_Tab()
            elif name == "Portfolio": render_Portfolio_Tab()
            elif name == "PIT38": render_PIT38_Tab()

# ==============================================================================
# ЗАПУСК
# ==============================================================================
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator")

# ==============================================================================
# ============================ АВТОРИЗАЦІЯ (НЕ ЧІПАЙ НІЖЧЕ) =====================
# ==============================================================================
require_auth()                    # блокує все, якщо не увійшов
show_auth_status_and_logout()     # кнопка виходу + статус у sidebar
# ==============================================================================

uploaded_files = render_sidebar()

# ==============================================================================
# ============================ ОБМЕЖЕННЯ FREE РЕЖИМУ ============================
# ==============================================================================
if st.session_state.broker_data is not None:
    if not st.session_state.get("is_pro", False):
        require_pro_for_feature("Вибір року")   # селектор року тільки для PRO
    render_global_year_selector()
    render_main_tabs()
else:
    st.info("Будь ласка, завантажте CSV файли брокера та натисніть «Розрахувати все».")
# ==============================================================================
