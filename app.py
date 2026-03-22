# ==============================================================================
# КАЛЬКУЛЯТОР ПОДАТКІВ FIFO — ВСІ ТАБЛИЦІ ПОКАЗУЮТЬ ВСІ РЯДКИ
# ==============================================================================
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import io
import streamlit.components.v1 as components

# ====================== ІМПОРТ АВТОРИЗАЦІЇ ======================
from auth import (
    require_auth,
    show_auth_status_and_logout,
    require_pro_for_feature,
    apply_free_limits,
    check_subscription_status
)

# ────────────────────────────────────────────────────────────────
# ЕКСПЕРИМЕНТ: топбар без трьох крапок + повернута кнопка сайдбару
# ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FIFO Tax Calculator",
    layout="wide",
    initial_sidebar_state="expanded",          # ← завжди відкритий при старті
    menu_items={"Get help": None, "Report a bug": None, "About": None}
)

st.markdown("""
<style>
    /* Ховаємо тільки три крапки, Deploy та анімацію спортсменів */
    section[data-testid="stToolbar"],
    div[data-testid="stToolbar"],
    [data-testid="stAppToolbar"],
    [data-testid="stDecoration"],
    button[data-testid^="stBaseButton-header"],
    .stDeployButton,
    div.stSpinner > div > svg,
    [data-testid="stToolbar"] svg {
        display: none !important;
    }

    /* ПОВЕРТАЄМО кнопку розгортання/згортання сайдбару ліворуч */
    button[data-testid="stSidebarCollapseButton"],
    button[aria-label="Collapse sidebar"],
    button[aria-label="Open sidebar"],
    [data-testid="collapsedControl"] {
        display: flex !important;
        position: fixed !important;
        left: 12px !important;
        top: 12px !important;
        z-index: 9999 !important;
        background: white !important;
        border: 1px solid #ddd !important;
        border-radius: 50% !important;
        width: 42px !important;
        height: 42px !important;
    }

    /* Трохи піднімаємо контент */
    .main > .block-container {
        padding-top: 0.8rem !important;
    }

    /* Стиль для топбару з кнопками */
    .stAppHeader {
        height: 52px !important;
        padding: 8px 16px !important;
    }
</style>
""", unsafe_allow_html=True)
# ────────────────────────────────────────────────────────────────

# ====================== МОДАЛЬНІ ВІКНА (st.dialog) ======================
@st.dialog("🔑 Увійти")
def login_dialog():
    email = st.text_input("Email")
    password = st.text_input("Пароль", type="password")
    if st.button("Увійти", type="primary"):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user = res.user
            st.session_state.authenticated = True
            check_subscription_status()
            st.success("✅ Успішний вхід!")
            st.rerun()
        except Exception as e:
            st.error(f"Помилка: {e}")

@st.dialog("📝 Реєстрація")
def register_dialog():
    email = st.text_input("Email")
    password = st.text_input("Пароль (мінімум 6 символів)", type="password")
    if st.button("Зареєструватися", type="primary"):
        try:
            supabase.auth.sign_up({"email": email, "password": password})
            st.success("✅ Акаунт створено! Тепер увійдіть.")
            st.rerun()
        except Exception as e:
            st.error(f"Помилка: {e}")

# ====================== ТОПБАР З АВТОРИЗАЦІЄЮ ======================
def show_auth_in_header():
    col1, col2, col3 = st.columns([6, 2, 2])

    with col2:
        if st.session_state.get("authenticated", False):
            status = "✅ PRO" if st.session_state.get("is_pro", False) else "🔓 Free"
            st.markdown(f"**{st.session_state.user.email}**<br>{status}", unsafe_allow_html=True)
            if st.button("🚪 Вийти", key="header_logout"):
                supabase.auth.sign_out()
                st.session_state.clear()
                st.rerun()
        else:
            if st.button("🔑 Увійти", key="header_login"):
                login_dialog()
            if st.button("📝 Реєстрація", key="header_register"):
                register_dialog()

    with col3:
        if not st.session_state.get("authenticated", False):
            st.info("Увійдіть для повного доступу")

show_auth_in_header()

# ====================== ІНІЦІАЛІЗАЦІЯ ======================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.is_pro = False

# Імпорт supabase (для діалогів)
from auth import supabase

# ==============================================================================
# CSS — гарантуємо повну висоту контенту
# ==============================================================================
st.markdown("""
<style>
    .stDataFrame, div[data-testid="stDataFrame"] { max-height: none !important; height: auto !important; }
    .ag-theme-streamlit { max-height: none !important; height: auto !important; }
    .main > div:first-child { padding-top: 0rem; }
    .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# ІНІЦІАЛІЗАЦІЯ СЕСІЙНОГО СТАНУ (залишається без змін)
# ==============================================================================
keys = ['broker_data', 'rates_data', 'fifo_df', 'finance_df', 'report_blocks',
        'sales_summary', 'profit_summary', 'summary_df', 'summary_sales', 'summary_profit',
        'dividend_df', 'dividend_summary_val', 'dividend_summary_pln',
        'interest_df', 'interest_summary_val', 'interest_summary_pln',
        'cash_df', 'cash_summary', 'transactions_df',
        'portfolio_df', 'portfolio_currency_percent', 'portfolio_currency_value',
        'pit38_akcje', 'pit38_dywidendy', 'pit38_zg', 'selected_year']

for key in keys:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'selected_year' else "Wszystkie lata"

# ==============================================================================
# УНІВЕРСАЛЬНЕ ПОВІДОМЛЕННЯ + СТИЛІЗАЦІЯ ТАБЛИЦЬ (без змін)
# ==============================================================================
def show_no_data_message(section_name=""):
    msg = "✅ Dane zostały obliczone, ale za wybrany rok brak operacji tego typu."
    if section_name: msg = f"✅ {section_name} — dane zostały obliczone, ale za wybrany rok brak operacji."
    st.info(msg)

def style_dataframe(df, tab_name):
    if not st.session_state.get("is_pro", False): return df
    if df is None or df.empty: return df
    cols_4dec = ["Kurs NBP", "Kurs", "Kurs (USD)", "Koszt sredni", "Kurs NBP (D-1)"]
    cols_percent = ["Stawka zr. %", "Waga %", "Udział %"]
    styler = df.style.set_properties(**{'text-align': 'center'})
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    for col in numeric_cols:
        if col in cols_4dec: styler = styler.format({col: "{:,.4f}"})
        elif col in cols_percent: styler = styler.format({col: "{:.2%}"})
        else: styler = styler.format({col: "{:,.2f}"})
    return styler


# ==============================================================================
# МОДУЛЬ 1: Імпорт даних від брокера
# ==============================================================================
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

# ==============================================================================
# МОДУЛЬ 2: Завантаження курсів NBP
# ==============================================================================
def Module2_Currency_Rates(rates_df):
    updated_df = rates_df.copy()
    currencies = [col for col in updated_df.columns if len(col) == 3 and col != "PLN"]
    date_start = pd.to_datetime(updated_df['Date'].min())
    date_end = pd.to_datetime(updated_df['Date'].max())
    for currency in currencies:
        chunk_start = date_start
        while chunk_start <= date_end:
            chunk_end = chunk_start + timedelta(days=31)
            if chunk_end > date_end: chunk_end = date_end
            url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency}/{chunk_start.strftime('%Y-%m-%d')}/{chunk_end.strftime('%Y-%m-%d')}/?format=json"
            try:
                res = requests.get(url, timeout=10)
                if res.status_code == 200:
                    for item in res.json()['rates']:
                        updated_df.loc[updated_df['Date'] == item['effectiveDate'], currency] = item['mid']
            except:
                pass
            chunk_start = chunk_end + timedelta(days=1)
    updated_df.set_index('Date', inplace=True)
    updated_df = updated_df.ffill()
    updated_df.reset_index(inplace=True)
    return updated_df

# ==============================================================================
# МОДУЛЬ 3: Компіляція FIFO даних
# ==============================================================================
def Module3_FIFO_Data_Compiler(broker_data, rates_data):
    all_rows = []
    for file_name, df in broker_data.items():
        df.columns = [c.strip().lower() for c in df.columns]
        if 'symbol' in df.columns and 'buy/sell' in df.columns:
            for _, row in df.iterrows():
                bs = str(row.get('buy/sell', '')).upper()
                if bs in ['BUY', 'SELL']:
                    record = {
                        "Symbol": row.get('symbol'),
                        "Asset Class": row.get('asset class', row.get('assetclass', 'UNKNOWN')),
                        "Date": pd.to_datetime(row.get('tradedate', row.get('datetime', ''))).date(),
                        "Type": bs,
                        "Units": abs(float(row.get('quantity', 0))),
                        "Price": float(row.get('tradeprice', 0)),
                        "Comm": abs(float(row.get('ibcommission', 0))),
                        "Currency": str(row.get('currency', row.get('currencyprimary', 'USD'))).upper(),
                        "IssuerCountry": row.get('issuercountrycode', ''),
                        "Exchange": row.get('listingexchange', row.get('exchange', '')),
                        "SubCategory": row.get('subcategory', ''),
                        "DateTime Full": row.get('datetime', '')
                    }
                    all_rows.append(record)
    if not all_rows: return pd.DataFrame()
    fifo_df = pd.DataFrame(all_rows)
    fifo_df['Kwota'] = fifo_df['Units'] * fifo_df['Price']
    rates_data['Date'] = pd.to_datetime(rates_data['Date'])
    fifo_df['Date'] = pd.to_datetime(fifo_df['Date'])
    fifo_df['LookupDate'] = fifo_df['Date'] - timedelta(days=1)
    currencies = [col for col in rates_data.columns if len(col) == 3 and col != "PLN"]
    fifo_df['Kurs NBP (D-1)'] = 1.0
    for cur in currencies:
        rate_map = rates_data.set_index('Date')[cur].to_dict()
        mask = (fifo_df['Currency'] == cur)
        fifo_df.loc[mask, 'Kurs NBP (D-1)'] = fifo_df.loc[mask, 'LookupDate'].map(rate_map).fillna(1.0)
    return fifo_df.drop(columns=['LookupDate'])

# ==============================================================================
# МОДУЛЬ 4: Компіляція Finance даних
# ==============================================================================
def Module4_Finance_Data_Compiler(broker_data):
    all_finance = []
    for file_name, df in broker_data.items():
        if file_name in ["Rates_NBP","Finance_Data","FIFO_Data","Tax_Final_Report","Tax_Detailed_Report","Div_Report","Int_Report","Cash_Report"]: continue
        df = df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        cS = cD = cA = cT = cC = cDes = cLOD = None
        for i in range(len(df)):
            row = df.iloc[i]
            rowTxt = "|" + "|".join([str(x).strip() for x in row.iloc[:40]])
            if "AvailableForTradingDate" in rowTxt and "ExDate" in rowTxt:
                for col_idx, h_val in enumerate(row):
                    h = str(h_val).strip()
                    if h == "Symbol": cS = col_idx
                    if h == "Date/Time": cD = col_idx
                    if h == "Amount": cA = col_idx
                    if h == "Type": cT = col_idx
                    if h == "CurrencyPrimary": cC = col_idx
                    if h == "Description": cDes = col_idx
                    if h == "LevelOfDetail": cLOD = col_idx
                continue
            if cLOD is not None and str(row.iloc[cLOD]).strip().upper() == "DETAIL":
                rawD = str(row.iloc[cD] if cD is not None else "").strip()
                if ";" in rawD: rawD = rawD.split(";")[0].strip()
                try:
                    date_val = pd.to_datetime(rawD, format='%Y%m%d') if len(rawD)==8 and rawD.isnumeric() else pd.to_datetime(rawD)
                except:
                    date_val = pd.NaT
                all_finance.append({
                    "Symbol": str(row.iloc[cS]) if cS is not None else "",
                    "Date": date_val,
                    "Description": str(row.iloc[cDes]) if cDes is not None else "",
                    "Currency": str(row.iloc[cC]) if cC is not None else "",
                    "Amount": float(row.iloc[cA]) if cA is not None else 0.0,
                    "Type": str(row.iloc[cT]) if cT is not None else "",
                    "SourceSheet": file_name
                })
    if not all_finance: return pd.DataFrame(columns=["Symbol","Date","Description","Currency","Amount","Type","SourceSheet"])
    finance_df = pd.DataFrame(all_finance)
    finance_df['Date'] = pd.to_datetime(finance_df['Date'], errors='coerce')
    finance_df = finance_df.sort_values(by="Date").reset_index(drop=True)
    return finance_df

# ==============================================================================
# МОДУЛЬ 5: Детальний податковий звіт (FIFO)
# ==============================================================================
def Module5_FIFO_Detailed_Tax_Report(fifo_df, selected_year="Wszystkie lata"):
    df_full = fifo_df.copy()
    df_full['Date'] = pd.to_datetime(df_full['Date'])
    df_full['Kurs NBP (D-1)'] = df_full['Kurs NBP (D-1)'].fillna(1.0)
    df_full = df_full.sort_values(by=['Symbol', 'Date', 'DateTime Full'])
    if df_full.empty: return [], pd.DataFrame(), pd.DataFrame()
    report_blocks = []
    inventory = {}
    total_all_income = total_all_costs = 0.0
    closed_positions = open_positions = 0
    columns_order = ["Ticker", "Data", "Typ", "Jednostki", "Cena", "Kwota", "Prowizja", "Waluta", "Data D-1", "Kurs NBP", "Przychod [PLN]", "Koszt [PLN]", "Przepływ [PLN]"]
    for _, row in df_full.iterrows():
        symbol = row['Symbol']
        asset_class = str(row.get('Asset Class', '')).strip().upper()
        if row['Type'] == 'BUY':
            if symbol not in inventory: inventory[symbol] = []
            buy_data = row.to_dict().copy()
            buy_data['Orig_Units'] = row['Units']
            inventory[symbol].append(buy_data)
            continue
        if row['Type'] != 'SELL' or asset_class != 'STK': continue
        if selected_year != "Wszystkie lata" and row['Date'].year != int(selected_year): continue
        block_rows = []
        qty_to_sell = row['Units']
        s_date = row['Date'].date()
        s_kurs = row['Kurs NBP (D-1)']
        s_price = row['Price']
        s_comm = row['Comm']
        s_gross_pln = qty_to_sell * s_price * s_kurs
        s_comm_pln = s_comm * s_kurs
        s_net_pln = s_gross_pln - s_comm_pln
        block_buy_cost = 0.0
        while qty_to_sell > 0 and inventory.get(symbol):
            buy_lot = inventory[symbol][0]
            avail = buy_lot['Units']
            if avail <= 0:
                inventory[symbol].pop(0)
                continue
            take = min(qty_to_sell, avail)
            b_units_orig = buy_lot['Orig_Units']
            b_comm_orig = buy_lot['Comm']
            b_kurs = buy_lot['Kurs NBP (D-1)']
            b_prop_comm = b_comm_orig * (take / b_units_orig)
            b_comm_pln = b_prop_comm * b_kurs
            b_cost_shares_pln = take * buy_lot['Price'] * b_kurs
            b_total_cost_pln = b_cost_shares_pln + b_comm_pln
            block_buy_cost += b_total_cost_pln
            block_rows.append({"Ticker": symbol, "Data": pd.to_datetime(buy_lot['Date']).date(), "Typ": "K", "Jednostki": take, "Cena": buy_lot['Price'], "Kwota": take * buy_lot['Price'], "Prowizja": b_prop_comm, "Waluta": buy_lot['Currency'], "Data D-1": (pd.to_datetime(buy_lot['Date']) - timedelta(days=1)).date(), "Kurs NBP": b_kurs, "Przychod [PLN]": 0.0, "Koszt [PLN]": b_total_cost_pln, "Przepływ [PLN]": -b_total_cost_pln})
            buy_lot['Units'] -= take
            qty_to_sell -= take
            if buy_lot['Units'] <= 0: inventory[symbol].pop(0)
        block_rows.append({"Ticker": symbol, "Data": s_date, "Typ": "S", "Jednostki": -row['Units'], "Cena": s_price, "Kwota": row['Units'] * s_price, "Prowizja": s_comm, "Waluta": row['Currency'], "Data D-1": (row['Date'] - timedelta(days=1)).date(), "Kurs NBP": s_kurs, "Przychod [PLN]": s_gross_pln, "Koszt [PLN]": s_comm_pln, "Przepływ [PLN]": s_net_pln})
        current_date = row['Date']
        prev_ops = df_full[(df_full['Symbol'] == symbol) & (df_full['Date'] <= current_date)]
        total_buy = prev_ops[prev_ops['Type'] == 'BUY']['Units'].sum()
        total_sell = prev_ops[prev_ops['Type'] == 'SELL']['Units'].sum()
        remaining = total_buy - total_sell
        status = "Pozycja zamknieta" if remaining <= 0.0001 else f"Pozostalo: {remaining:.4f} jedn."
        if remaining <= 0.0001: closed_positions += 1
        else: open_positions += 1
        status_row = {"Ticker": status, "Data": "", "Typ": "", "Jednostki": "", "Cena": "", "Kwota": "", "Prowizja": "", "Waluta": "", "Data D-1": "", "Kurs NBP": "", "Przychod [PLN]": s_gross_pln, "Koszt [PLN]": block_buy_cost + s_comm_pln, "Przepływ [PLN]": s_net_pln - block_buy_cost}
        block_rows.append(status_row)
        total_all_income += s_gross_pln
        total_all_costs += block_buy_cost + s_comm_pln
        report_blocks.append(pd.DataFrame(block_rows, columns=columns_order))
    sales_summary = pd.DataFrame({" ": ["Sprzedaze calkowite", "Sprzedaze czesciowe", "Razem"], "Value": [closed_positions, open_positions, closed_positions + open_positions]})
    profit_summary = pd.DataFrame({" ": ["Koszt", "Przychod", "Przeplyw"], "Value": [-total_all_costs, total_all_income, total_all_income - total_all_costs]})
    return report_blocks, sales_summary, profit_summary

# ==============================================================================
# МОДУЛЬ 6: Підсумковий податковий звіт (FIFO Summary)
# ==============================================================================
def Module6_FIFO_Summary_Tax_Report(fifo_df, selected_year="Wszystkie lata"):
    if fifo_df.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = fifo_df.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by=['Symbol', 'Date']).reset_index(drop=True)
    df['Used'] = 0.0
    report_rows = []
    total_income = total_costs = 0.0
    closed = open_pos = 0
    for i, row in df.iterrows():
        if row['Type'] != 'SELL' or str(row.get('Asset Class', '')).upper() != 'STK': continue
        current_year = str(row['Date'].year)
        if selected_year != "Wszystkie lata" and selected_year != current_year: continue
        ticker = row['Symbol']
        qty_to_sell = row['Units']
        s_kurs = row.get('Kurs NBP (D-1)', 1.0) or 1.0
        s_price = row['Price']
        s_comm = row['Comm']
        s_income_gross = qty_to_sell * s_price * s_kurs
        s_comm_pln = s_comm * s_kurs
        cost_pln = 0.0
        buy_comm_sum = 0.0
        temp_qty = qty_to_sell
        for j in range(len(df)):
            if df.at[j, 'Symbol'] == ticker and df.at[j, 'Type'] == 'BUY':
                avail = df.at[j, 'Units'] - df.at[j, 'Used']
                if avail > 0 and temp_qty > 0:
                    take = min(avail, temp_qty)
                    b_kurs = df.at[j, 'Kurs NBP (D-1)'] or 1.0
                    buy_comm_sum += (df.at[j, 'Comm'] * (take / df.at[j, 'Units'])) * b_kurs
                    cost_pln += take * df.at[j, 'Price'] * b_kurs
                    df.at[j, 'Used'] += take
                    temp_qty -= take
        final_pl = (s_income_gross - s_comm_pln) - (cost_pln + buy_comm_sum)
        prev = df[(df['Symbol'] == ticker) & (df['Date'] <= row['Date'])]
        total_buy = prev[prev['Type'] == 'BUY']['Units'].sum()
        total_sell = prev[prev['Type'] == 'SELL']['Units'].sum()
        remaining = total_buy - total_sell
        status = "Pozycja zamknieta" if remaining <= 0.0001 else f"Pozostalo: {remaining:.4f} jedn."
        if remaining <= 0.0001: closed += 1
        else: open_pos += 1
        report_rows.append({
            "Ticker": ticker,
            "Kategoria": row.get('Asset Class', ''),
            "Podkategoria": row.get('SubCategory', ''),
            "Kraj emitenta": row.get('IssuerCountry', ''),
            "Data sprzedazy": row['Date'].date(),
            "Jednostki": qty_to_sell,
            "Przeplyw PLN": final_pl,
            "Status": status
        })
        total_income += s_income_gross
        total_costs += cost_pln + buy_comm_sum + s_comm_pln
    main_df = pd.DataFrame(report_rows)
    sales_summary = pd.DataFrame({" ": ["Sprzedaze calkowite", "Sprzedaze czesciowe", "Razem"], "Value": [closed, open_pos, closed + open_pos]})
    profit_summary = pd.DataFrame({" ": ["Koszt", "Przychod", "Przeplyw"], "Value": [-total_costs, total_income, total_income - total_costs]})
    return main_df, sales_summary, profit_summary

# ==============================================================================
# МОДУЛЬ 7: Податковий звіт по дивідендах
# ==============================================================================
def Module7_Dividend_Tax_Report(finance_df, rates_data, selected_year="Wszystkie lata"):
    if finance_df is None or finance_df.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = finance_df.copy()
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    dict_gross = defaultdict(float)
    dict_tax = defaultdict(float)
    dict_curr = {}
    dict_count = defaultdict(int)
    for _, row in df.iterrows():
        desc_upper = str(row.get('Description', '')).upper()
        if row.get('Type') != "Dividends" and "DIVIDEND" not in desc_upper: continue
        d_date = row['Date']
        d_year = str(d_date.year)
        if selected_year != "Wszystkie lata" and selected_year != d_year: continue
        ticker = str(row.get('Symbol', ''))
        amt = float(row.get('Amount', 0))
        curr = str(row.get('Currency', 'USD')).upper()
        key = (ticker, d_date, curr)
        if "TAX" in desc_upper or "WITHHOLDING" in desc_upper or amt < 0:
            dict_tax[key] += amt
        else:
            dict_gross[key] += amt
            dict_curr[key] = curr
            dict_count[key] += 1
    rates_df = rates_data.copy()
    rates_df['Date'] = pd.to_datetime(rates_df['Date']).dt.date
    rate_dict = {}
    for cur in [c for c in rates_df.columns if len(c) == 3 and c != "PLN"]:
        rate_dict[cur] = rates_df.set_index('Date')[cur].to_dict()
    report_rows = []
    total_gross = total_tax = 0.0
    total_pln_gross = total_pln_tax_source = total_pln_tax19 = total_pln_topup = 0.0
    for key in dict_gross.keys():
        ticker, current_date, current_curr = key
        gross = dict_gross[key]
        tax = dict_tax.get(key, 0.0)
        nbp_date = current_date - timedelta(days=1)
        ex_rate = rate_dict.get(current_curr, {}).get(nbp_date, 1.0)
        if pd.isna(ex_rate) or ex_rate == 0: ex_rate = 1.0
        pln_gross = gross * ex_rate
        pln_tax_source = abs(tax * ex_rate)
        pln_tax19 = pln_gross * 0.19
        pln_doplata = max(pln_tax19 - pln_tax_source, 0)
        pln_netto = pln_gross - pln_tax_source - pln_doplata
        report_rows.append({
            "Symbol": ticker, "Data": current_date, "Waluta": current_curr,
            "Przychod": gross, "Pod. zrodlo": abs(tax), "Netto (Wal)": gross + tax,
            "Stawka zr. %": abs(tax) / gross if gross != 0 else 0,
            "Data NBP": nbp_date, "Kurs": ex_rate,
            "Przychod (PLN)": pln_gross, "Pod. zr. (PLN)": pln_tax_source,
            "Pod. PL (19%)": pln_tax19, "Doplata (PLN)": pln_doplata, "Netto (PLN)": pln_netto
        })
        total_gross += gross
        total_tax += abs(tax)
        total_pln_gross += pln_gross
        total_pln_tax_source += pln_tax_source
        total_pln_tax19 += pln_tax19
        total_pln_topup += pln_doplata
    main_df = pd.DataFrame(report_rows)
    avg_rate = total_tax / total_gross if total_gross != 0 else 0
    summary_val = pd.DataFrame({" ": ["Прихід брутто", "Податок у джерела", "Середня ставка у джерела", "Сума нетто"], "Value": [total_gross, total_tax, avg_rate, total_gross - total_tax]})
    summary_pln = pd.DataFrame({" ": ["Przychod Brutto", "Pod. u zrodla", "Podatek w PL (19%)", "Doplata w PL", "Suma Netto"], "Value": [total_pln_gross, total_pln_tax_source, total_pln_tax19, total_pln_topup, total_pln_gross - total_pln_tax_source - total_pln_topup]})
    return main_df, summary_val, summary_pln

# ==============================================================================
# МОДУЛЬ 8: Податковий звіт по відсотках
# ==============================================================================
def Module8_Interest_Tax_Report(finance_df, rates_data, selected_year="Wszystkie lata"):
    if finance_df is None or finance_df.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = finance_df.copy()
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    report_rows = []
    total_gross = total_tax = 0.0
    total_pln_gross = total_pln_tax_source = total_pln_topup = 0.0
    rates_df = rates_data.copy()
    rates_df['Date'] = pd.to_datetime(rates_df['Date']).dt.date
    rate_dict = {cur: rates_df.set_index('Date')[cur].to_dict() for cur in [c for c in rates_df.columns if len(c)==3 and c!="PLN"]}
    for _, row in df.iterrows():
        desc = str(row.get('Description', '')).upper()
        if "INT" not in desc or "WITHHOLDING" in desc: continue
        d_date = row['Date']
        if selected_year != "Wszystkie lata" and str(d_date.year) != selected_year: continue
        amt = float(row.get('Amount', 0))
        curr = str(row.get('Currency', 'USD')).upper()
        tax = 0.0
        month_ref = desc[desc.find("FOR "):] if "FOR " in desc else ""
        for _, trow in df.iterrows():
            tdesc = str(trow.get('Description', '')).upper()
            if "WITHHOLDING" in tdesc and month_ref in tdesc and trow.get('Currency') == curr:
                tax = float(trow.get('Amount', 0))
                break
        nbp_date = d_date - timedelta(days=1)
        ex_rate = rate_dict.get(curr, {}).get(nbp_date, 1.0)
        if pd.isna(ex_rate) or ex_rate == 0: ex_rate = 1.0
        pln_gross = amt * ex_rate
        pln_tax_source = abs(tax * ex_rate)
        pln_tax19 = pln_gross * 0.19
        pln_doplata = max(pln_tax19 - pln_tax_source, 0)
        pln_netto = pln_gross - pln_tax_source - pln_doplata
        report_rows.append({
            "Data": d_date, "Opis": row.get('Description', ''), "Waluta": curr,
            "Przychod": amt, "Pod. zrodlo": abs(tax), "Netto": amt - abs(tax),
            "Stawka zr. %": abs(tax)/amt if amt != 0 else 0,
            "Data NBP": nbp_date, "Kurs": ex_rate,
            "Przychod (PLN)": pln_gross, "Pod. zr. (PLN)": pln_tax_source,
            "Pod. PL (19%)": pln_tax19, "Doplata (PLN)": pln_doplata, "Netto (PLN)": pln_netto
        })
        total_gross += amt
        total_tax += abs(tax)
        total_pln_gross += pln_gross
        total_pln_tax_source += pln_tax_source
        total_pln_topup += pln_doplata
    main_df = pd.DataFrame(report_rows)
    summary_val = pd.DataFrame({" ": ["Przychod Brutto", "Pod. u zrodla", "Sr. Stawka zr.", "Suma Netto"], "Value": [total_gross, total_tax, total_tax/total_gross if total_gross else 0, total_gross-total_tax]})
    total_pln_tax19 = total_pln_gross * 0.19
    summary_pln = pd.DataFrame({" ": ["Przychod Brutto", "Pod. u zrodla", "Podatek w PL (19%)", "Doplata w PL", "Suma Netto"], "Value": [total_pln_gross, total_pln_tax_source, total_pln_tax19, total_pln_topup, total_pln_gross - total_pln_tax_source - total_pln_topup]})
    return main_df, summary_val, summary_pln

# ==============================================================================
# МОДУЛЬ 9: Звіт по руху готівки
# ==============================================================================
def Module9_Cash_Report(finance_df, rates_data, selected_year="Wszystkie lata"):
    if finance_df is None or finance_df.empty: return pd.DataFrame(), pd.DataFrame()
    df = finance_df.copy()
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    report_rows = []
    total_in_pln = total_out_pln = total_in_usd = total_out_usd = 0.0
    rates_df = rates_data.copy()
    rates_df['Date'] = pd.to_datetime(rates_df['Date']).dt.date
    usd_rate = rates_df.set_index('Date').get('USD', pd.Series()).to_dict()
    for _, row in df.iterrows():
        desc = str(row.get('Description', '')).upper()
        typ = str(row.get('Type', ''))
        if not ("CASH RECEIPTS" in desc or "DISBURSEMENT" in desc or typ == "Deposits/Withdrawals"): continue
        d_date = row['Date']
        if selected_year != "Wszystkie lata" and str(d_date.year) != selected_year: continue
        amt = float(row.get('Amount', 0))
        curr = str(row.get('Currency', 'PLN')).upper()
        rate = usd_rate.get(d_date, 1.0) if curr == "PLN" else 1.0
        usd_amt = amt / rate if rate else 0
        report_rows.append({"Data": d_date, "Opis": row.get('Description', ''), "Waluta": curr, "Kwota (PLN)": amt, "Kurs (USD)": rate, "Kwota (USD)": usd_amt})
        if amt >= 0:
            total_in_pln += amt
            total_in_usd += usd_amt
        else:
            total_out_pln += amt
            total_out_usd += usd_amt
    main_df = pd.DataFrame(report_rows)
    summary = pd.DataFrame({
        " ": ["Сума вплат (PLN)", "Сума виплат (PLN)", "Сума вплат (USD)", "Сума виплат (USD)", "Середній курс вплат", "Середній курс виплат"],
        "Value": [total_in_pln, total_out_pln, total_in_usd, total_out_usd, total_in_pln/abs(total_in_usd) if total_in_usd else 0, total_out_pln/abs(total_out_usd) if total_out_usd else 0]
    })
    return main_df, summary

# ==============================================================================
# МОДУЛЬ 10: Звіт по транзакціях
# ==============================================================================
def Module10_Transactions_Report(fifo_df, selected_year="Wszystkie lata"):
    if fifo_df is None or fifo_df.empty: return pd.DataFrame()
    df = fifo_df[fifo_df['Asset Class'] == 'STK'].copy()
    if selected_year != "Wszystkie lata":
        df = df[df['Date'].dt.year == int(selected_year)]
    report_rows = []
    for _, row in df.iterrows():
        dt_full = str(row.get('DateTime Full', ''))
        if ";" in dt_full:
            d = dt_full[:8]
            t = dt_full.split(";")[1][:6]
            try:
                full_dt = pd.to_datetime(d + t, format='%Y%m%d%H%M%S')
            except:
                full_dt = row['Date']
        else:
            full_dt = row['Date']
        report_rows.append({
            "Ticker": row['Symbol'], "Asset Class": row['Asset Class'], "Data i Czas": full_dt,
            "Typ": row['Type'], "Jednostki": row['Units'], "Cena": row['Price'],
            "Kwota": row.get('Kwota', 0), "Prowizja": row['Comm'],
            "Kraj": row.get('IssuerCountry', ''), "Gielda": row.get('Exchange', '')
        })
    return pd.DataFrame(report_rows)

# ==============================================================================
# МОДУЛЬ 11: Поточний стан портфеля
# ==============================================================================
def Module11_Portfolio(fifo_df, rates_data):
    if fifo_df is None or fifo_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = fifo_df.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    dictUnits = defaultdict(float)
    dictCost = defaultdict(float)
    dictGielda = {}
    dictSymbCurr = {}
    dictKraj = {}
    dictType = {}
    dictSubCat = {}
    for _, row in df.iterrows():
        assetClass = str(row.get('Asset Class', '')).upper()
        if assetClass not in ['STK', 'ETF']: continue
        symbol = row['Symbol']
        units = row['Units']
        price = row['Price']
        if row['Type'] == 'BUY':
            dictUnits[symbol] += units
            dictCost[symbol] += units * price
            dictGielda[symbol] = row.get('Exchange', '')
            dictSymbCurr[symbol] = row['Currency']
            dictKraj[symbol] = row.get('IssuerCountry', '')
            dictType[symbol] = assetClass
            dictSubCat[symbol] = row.get('SubCategory', '')
        elif row['Type'] == 'SELL' and dictUnits[symbol] > 0:
            if dictUnits[symbol] > 0:
                avgPx = dictCost[symbol] / dictUnits[symbol]
                dictUnits[symbol] -= units
                dictCost[symbol] = dictUnits[symbol] * avgPx
    rates_df = rates_data.copy()
    rates_df['Date'] = pd.to_datetime(rates_df['Date'])
    dictRates = {}
    if not rates_df.empty:
        last_row = rates_df.iloc[-1]
        for col in rates_df.columns:
            if len(col) == 3 and col != "PLN":
                dictRates[col] = last_row[col]
    totalLong = 0.0
    dictCurr = defaultdict(float)
    for sym in dictUnits:
        if dictUnits[sym] > 0.0001:
            curr = dictSymbCurr.get(sym, 'USD')
            rate = dictRates.get(curr, 1.0)
            if not isinstance(rate, (int, float)) or pd.isna(rate): rate = 1.0
            currCost = dictCost[sym]
            plnVal = currCost * rate
            totalLong += plnVal
            dictCurr[curr] += currCost
    if totalLong == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    report_rows = []
    for sym in dictUnits:
        if dictUnits[sym] <= 0.0001: continue
        curr = dictSymbCurr.get(sym, 'USD')
        rate = dictRates.get(curr, 1.0)
        if not isinstance(rate, (int, float)) or pd.isna(rate): rate = 1.0
        plnVal = dictCost[sym] * rate
        report_rows.append({
            "Ticker": sym,
            "Typ": dictType.get(sym, ''),
            "Subcategory": dictSubCat.get(sym, ''),
            "Kraj": dictKraj.get(sym, ''),
            "Gielda": dictGielda.get(sym, ''),
            "Waluta": curr,
            "Ilosc": dictUnits[sym],
            "Koszt sredni": dictCost[sym] / dictUnits[sym] if dictUnits[sym] else 0,
            "Suma покупки": dictCost[sym],
            "Waga %": plnVal / totalLong
        })
    main_df = pd.DataFrame(report_rows)
    curr_df = pd.DataFrame([{"Waluta": k, "Udział %": (v * dictRates.get(k, 1.0)) / totalLong} for k, v in dictCurr.items()])
    curr_value_df = pd.DataFrame([{"Waluta": k, "Wartosc": v} for k, v in dictCurr.items()])
    return main_df, curr_df, curr_value_df

# ==============================================================================
# МОДУЛЬ 12: Підсумковий звіт PIT-38
# ==============================================================================
def Module12_PIT38_Report(fifo_df, finance_df, rates_data, selected_year="Wszystkie lata"):
    _, _, summary_profit = Module6_FIFO_Summary_Tax_Report(fifo_df, selected_year)
    _, _, dividend_summary_pln = Module7_Dividend_Tax_Report(finance_df, rates_data, selected_year)
    summary_df = Module6_FIFO_Summary_Tax_Report(fifo_df, selected_year)[0]
    if summary_profit is None or summary_profit.empty:
        przychod = 0
        koszt = 0
    else:
        przychod = summary_profit.loc[summary_profit[" "] == "Przychod", "Value"].iloc[0] if not summary_profit[summary_profit[" "] == "Przychod"].empty else 0
        koszt = abs(summary_profit.loc[summary_profit[" "] == "Koszt", "Value"].iloc[0]) if not summary_profit[summary_profit[" "] == "Koszt"].empty else 0
    akcje_data = {
        "Komorka": ["C.20", "C.21", "C.22", "C.23", "C.26", "C.27", "C.28", "C.29", "D.31", "D.32", "D.33", "D.34", "D.35"],
        "Nazwa": ["Przychody wykazane w części D informacji PIT-8C","Przychody wykazane w części D інформації PIT-8C","Inne przychody / Przychod","Inne przychody / Koszty отримання приchodow","Razem (suma kwot z wierszy 1 do 2) / Przychod","Razem (suma kwot z wierszy 1 do 2) / Koszty отримання przychodow","Dochod (b-c)","Strata (c-b)","Podstawa obliczenia podatku (po zaokragleniu do pełnych złotych)","Stawka podatku (należy podać w procentach)","Podatek od dochodów, o których mowa w art. 30b ust. 1 ustawy","Podatek zapłacony za granicą, o którym mowa w art. 30b ust. 5a i 5b ustawy","Podatek należny (po zaokrągleniu do pełnych złotych)"],
        "Wartosc": [0, 0, przychod, koszt, przychod, koszt, max(0, przychod - koszt), max(0, koszt - przychod), round(max(0, przychod - koszt)), 19, round(max(0, przychod - koszt) * 0.19), 0, round(max(0, przychod - koszt) * 0.19)]
    }
    df_akcje = pd.DataFrame(akcje_data)
    div_gross = 0
    div_podatek_zr = 0
    if dividend_summary_pln is not None and not dividend_summary_pln.empty:
        gross_row = dividend_summary_pln[dividend_summary_pln[" "] == "Przychod Brutto"]
        zr_row = dividend_summary_pln[dividend_summary_pln[" "] == "Pod. u zrodla"]
        div_gross = gross_row["Value"].iloc[0] if not gross_row.empty else 0
        div_podatek_zr = zr_row["Value"].iloc[0] if not zr_row.empty else 0
    div_podatek_pl = div_gross * 0.19
    div_doplata = max(0, div_podatek_pl - div_podatek_zr)
    dywidendy_data = {
        "Komorka": ["-", "G.47", "G.48", "-", "G.49"],
        "Nazwa": ["Suma wypłat dywidend zagranicznych - podstawa opodatkowania (wiersz pomocniczy)","Zryczałtowany podatek obliczony od przychodów (dochodów), o których mowa w art. 30a ust. 1 pkt 1–5 ustawy, uzyskanych poza granicami Rzeczypospolitej Polskiej (19%)","Podatek zapłacony za granicą, o którym mowa w art. 30a ust. 9 ustawy (przeliczony na złote)","Dokładna wartość podatku do dopłacenia (wiersz pomocniczy)","Różnica między zryczałtowanym podatkiem a podatkiem zapłaconym za granicą (G.47 - G.48, po zaokrągleniu do pełnych złotych)"],
        "Wartosc": [div_gross, round(div_gross * 0.19, 2), round(div_podatek_zr, 2), round(div_doplata, 2), round(div_doplata)]
    }
    df_dyw = pd.DataFrame(dywidendy_data)
    zg_group = pd.DataFrame(columns=["Państwo uzyskania przychodu", "Inne przychody, w tym uzyskane za granicą - Dochod", "Podatek od innych przychodów zapłacony za granicą"])
    if summary_df is not None and not summary_df.empty and "Kraj emitenta" in summary_df.columns:
        zg = summary_df[(summary_df["Kraj emitenta"].notna()) & (summary_df["Kraj emitenta"] != "") & (summary_df["Kraj emitenta"] != "PL")].copy()
        if not zg.empty:
            zg_group = zg.groupby("Kraj emitenta")["Przeplyw PLN"].sum().reset_index()
            zg_group = zg_group.rename(columns={"Kraj emitenta": "Państwo uzyskania przychodu", "Przeplyw PLN": "Inne przychody, w tym uzyskane za granicą - Dochod"})
            zg_group = zg_group[zg_group["Inne przychody, w tym uzyskane za granicą - Dochod"] > 0]
            zg_group["Podatek od innych przychodów zapłacony za granicą"] = 0
    return df_akcje, df_dyw, zg_group


# ==============================================================================
# SIDEBAR
# ==============================================================================
# ==============================================================================
# SIDEBAR — кнопка "Розрахувати все" тепер disabled для неавторизованих
# ==============================================================================
def update_file_list():
    new_files = st.session_state.hidden_uploader
    if new_files:
        for f in new_files:
            if f.name not in [file.name for file in st.session_state.get("my_files", [])]:
                st.session_state.setdefault("my_files", []).append(f)

def render_sidebar():
    with st.sidebar:
        st.title("🧮 Калькулятор податків FIFO")
        st.markdown("---")

        if "my_files" not in st.session_state:
            st.session_state.my_files = []

        st.file_uploader(" ", accept_multiple_files=True, key="hidden_uploader",
                         label_visibility="collapsed", on_change=update_file_list)

        if st.button("📁 Додати файли (CSV)", type="primary", use_container_width=True):
            components.html("""<script>window.parent.document.querySelector('input[type="file"]').click();</script>""", height=0)

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

            # Кнопка розрахунку — disabled якщо не залогінений
            disabled = not st.session_state.get("authenticated", False)
            if st.button("🔄 Розрахувати все", type="primary", use_container_width=True, disabled=disabled):
                with st.spinner("Виконується повний розрахунок..."):
                    st.session_state.broker_data, st.session_state.rates_data = Module1_Data_Import(st.session_state.my_files)
                    st.session_state.rates_data = Module2_Currency_Rates(st.session_state.rates_data)
                    st.session_state.fifo_df = Module3_FIFO_Data_Compiler(st.session_state.broker_data, st.session_state.rates_data)
                    st.session_state.finance_df = Module4_Finance_Data_Compiler(st.session_state.broker_data)
                    recalculate_reports("Wszystkie lata")
                st.success("✅ Усе розраховано!")
                st.rerun()
            if disabled:
                st.caption("🔒 Увійдіть, щоб розрахувати")
        else:
            st.info("Завантажте файли...")

    return st.session_state.my_files

# ==============================================================================
# РЕШТА ФУНКЦІЙ (render_..._Tab, recalculate_reports, render_main_tabs) — БЕЗ ЗМІН
# ==============================================================================
# (скопіюй їх усі зі свого старого app.py після цього коментаря)

# ==============================================================================
# ЗАПУСК
# ==============================================================================
require_auth()                  # тільки ініціалізує сесію, не блокує сторінку
check_subscription_status()

# Старий статус в сайдбарі залишаємо (можна видалити пізніше)
show_auth_status_and_logout()

uploaded_files = render_sidebar()

if st.session_state.broker_data is not None:
    render_global_year_selector()
    render_main_tabs()
else:
    st.markdown('<div style="margin-top: 30px;"></div>', unsafe_allow_html=True)
    st.info("Завантажте CSV файли брокера та натисніть «Розрахувати все» (після входу).")
