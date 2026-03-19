# ==============================================================================
# КАЛЬКУЛЯТОР ПОДАТКІВ FIFO — ВСІ ТАБЛИЦІ ПОКАЗУЮТЬ ВСІ РЯДКИ (height="content")
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
    msg = "✅ Dane zostały obliczone, ale za wybrany rok brak operacji tego typu."
    if section_name:
        msg = f"✅ {section_name} — dane zostały obliczone, ale za wybrany rok brak operacji."
    st.info(msg)

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
# МОДУЛЬ 4: Компіляція Finance даних (дивіденди, відсотки, cash)
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
        "Nazwa": ["Suma wypłat dywidend zagranicznych - podstawa opodatkowania (wiersz pomocniczy)","Zryczałtowany podatek obliczony od przychodów (dochodów), o których mowa в art. 30a ust. 1 pkt 1–5 ustawy, uzyskanych poza granicami Rzeczypospolitej Polskiej (19%)","Podatek zapłacony za granicą, o którym mowa в art. 30a ust. 9 ustawy (przeliczony на złote)","Dokładna wartość podatku до dopłacenia (wiersz pomocniczy)","Różnica między zryczałtowanym podatkiem a podatkiem zapłaconym za granicą (G.47 - G.48, po zaokrągleniu до повних złotych)"],
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
            zg_group["Podatek od innych przychodów zapłacony за granicą"] = 0
    return df_akcje, df_dyw, zg_group

# ==============================================================================
# SIDEBAR (твій оригінальний код)
# ==============================================================================
# ==============================================================================
# SIDEBAR (твій оригінальний код)
# ==============================================================================
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

# ==============================================================================
# RENDER ФУНКЦІЇ — вивід вкладок з обмеженнями для FREE
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
        limited_block = apply_free_limits(block, "Tax_Detailed_Report")
        def safe_format(x):
            if pd.isna(x) or isinstance(x, str): return x if isinstance(x, str) else ""
            return f"{float(x):,.7f}"
        styled = limited_block.style.map(lambda v: 'color: #9c0006' if isinstance(v, (int, float)) and v < 0 else 'color: #006100', subset=['Przepływ [PLN]']).format({"Cena": safe_format, "Kwota": safe_format, "Prowizja": safe_format, "Jednostki": safe_format, "Przychod [PLN]": safe_format, "Koszt [PLN]": safe_format, "Przepływ [PLN]": safe_format, "Kurs NBP": safe_format})
        styled = styled.set_table_styles([{'selector': 'tr:last-child td:nth-child(n+2):nth-child(-n+10)', 'props': [('display', 'none')]}])
        st.dataframe(styled, use_container_width=True, height="content")

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Detailed Report)", key="dl_tax_detailed"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Блоки
                for idx, block in enumerate(st.session_state.report_blocks):
                    block.to_excel(writer, sheet_name=f"Block_{idx+1}", index=False)
                # Підсумки
                if st.session_state.sales_summary is not None:
                    st.session_state.sales_summary.to_excel(writer, sheet_name="Sales Summary", index=False)
                if st.session_state.profit_summary is not None:
                    st.session_state.profit_summary.to_excel(writer, sheet_name="Profit Summary", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Tax_Detailed_Report_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def render_Tax_Summary_Report_Tab():
    st.subheader("📊 Tax Report — підсумковий податковий звіт (FIFO Summary)")
    df = st.session_state.get('summary_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Summary Report")
        return

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

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Summary Report)", key="dl_tax_summary"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.summary_df is not None:
                    st.session_state.summary_df.to_excel(writer, sheet_name="Summary", index=False)
                if st.session_state.summary_sales is not None:
                    st.session_state.summary_sales.to_excel(writer, sheet_name="Sales Summary", index=False)
                if st.session_state.summary_profit is not None:
                    st.session_state.summary_profit.to_excel(writer, sheet_name="Profit Summary", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Tax_Summary_Report_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def render_Tax_Dividend_Report_Tab():
    st.subheader("💰 Tax Dividend — податковий звіт по дивідендах")
    df = st.session_state.get('dividend_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Dividend")
        return

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

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Dividend Report)", key="dl_tax_dividend"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.dividend_df is not None:
                    st.session_state.dividend_df.to_excel(writer, sheet_name="Dividends", index=False)
                if st.session_state.dividend_summary_val is not None:
                    st.session_state.dividend_summary_val.to_excel(writer, sheet_name="Summary (Val)", index=False)
                if st.session_state.dividend_summary_pln is not None:
                    st.session_state.dividend_summary_pln.to_excel(writer, sheet_name="Summary (PLN)", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Tax_Dividend_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def render_Tax_Interest_Report_Tab():
    st.subheader("📈 Tax Interest — податковий звіт по відсотках")
    df = st.session_state.get('interest_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Tax Interest")
        return

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

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Tax Interest Report)", key="dl_tax_interest"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.interest_df is not None:
                    st.session_state.interest_df.to_excel(writer, sheet_name="Interest", index=False)
                if st.session_state.interest_summary_val is not None:
                    st.session_state.interest_summary_val.to_excel(writer, sheet_name="Summary (Val)", index=False)
                if st.session_state.interest_summary_pln is not None:
                    st.session_state.interest_summary_pln.to_excel(writer, sheet_name="Summary (PLN)", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Tax_Interest_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

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

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Cash Report)", key="dl_cash"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.cash_df is not None:
                    st.session_state.cash_df.to_excel(writer, sheet_name="Cash", index=False)
                if st.session_state.cash_summary is not None:
                    st.session_state.cash_summary.to_excel(writer, sheet_name="Summary", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Cash_Report_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def render_Transactions_Report_Tab():
    st.subheader("📋 Transactions Report")
    df = st.session_state.get('transactions_df')
    if df is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return
    if df.empty:
        show_no_data_message("Transactions Report")
        return

    # Для цієї вкладки обмежень немає, але кнопка тільки для PRO
    styled = st.session_state.transactions_df.style.format({
        "Data i Czas": lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(x) else "",
        "Jednostki": "{:,.4f}", "Cena": "{:,.4f}", "Kwota": "{:,.2f}", "Prowizja": "{:,.2f}"
    })
    st.dataframe(styled, use_container_width=True, height="content")

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Transactions Report)", key="dl_transactions"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.transactions_df is not None:
                    st.session_state.transactions_df.to_excel(writer, sheet_name="Transactions", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Transactions_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

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

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (Portfolio)", key="dl_portfolio"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.portfolio_df is not None:
                    st.session_state.portfolio_df.to_excel(writer, sheet_name="Portfolio", index=False)
                if st.session_state.portfolio_currency_percent is not None:
                    st.session_state.portfolio_currency_percent.to_excel(writer, sheet_name="Currency Percent", index=False)
                if st.session_state.portfolio_currency_value is not None:
                    st.session_state.portfolio_currency_value.to_excel(writer, sheet_name="Currency Value", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"Portfolio_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def render_PIT38_Tab():
    st.subheader("📋 PIT-38 — підсумковий податковий звіт")

    akcje = st.session_state.get('pit38_akcje')
    if akcje is None:
        st.info("Натисніть «Розрахувати все» в боковій панелі")
        return

    # Для free показуємо замасковані дані, для pro – повні
    if st.session_state.get("is_pro", False):
        akcje_display = akcje
        dyw_display = st.session_state.pit38_dywidendy
        zg_display = st.session_state.pit38_zg
    else:
        akcje_display = apply_free_limits(akcje, "PIT38")
        dyw_display = apply_free_limits(st.session_state.pit38_dywidendy, "PIT38")
        zg_display = apply_free_limits(st.session_state.pit38_zg, "PIT38")
        st.info("🔒 Дані PIT-38 приховані для free-користувачів. Купіть підписку для доступу.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PIT-38 - Akcje i Koszty**")
        st.dataframe(akcje_display.style.format({"Wartosc": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")
    with col2:
        st.markdown("**PIT-38 - Dywidendy**")
        st.dataframe(dyw_display.style.format({"Wartosc": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")

    st.markdown("**PIT-38 - Podatek do zaplaty**")
    if st.session_state.get("is_pro", False):
        podatek_do_zaplaty = max(0, akcje.loc[12, "Wartosc"] + st.session_state.pit38_dywidendy.loc[4, "Wartosc"])
        podatek_df = pd.DataFrame({"Komorka": ["G.51"], "Nazwa": ["PODATEK DO ZAPLATY<br>Od sumy kwot z poz. 35, 45, 46 i 49 należy odjąć kwotę z poz. 50. Jeżeli różnica jest liczbą ujemną, należy wpisać 0."], "Wartosc": [podatek_do_zaplaty]})
    else:
        podatek_df = pd.DataFrame({"Komorka": ["G.51"], "Nazwa": ["PODATEK DO ZAPLATY"], "Wartosc": ["X"]})
    st.dataframe(podatek_df.style.format({"Wartosc": "{:,.2f}"}).set_properties(**{'font-weight': 'bold'}), hide_index=True, height="content")

    st.markdown("**PIT/ZG — Zagraniczne przychody**")
    st.dataframe(zg_display.style.format({"Inne przychody, w tym uzyskane za granicą - Dochod": "{:,.2f}", "Podatek od innych przychodów zapłacony za granicą": "{:,.2f}"}), hide_index=True, height="content")

    # Кнопка завантаження Excel
    st.markdown("---")
    if st.button("📥 Завантажити Excel (PIT-38)", key="dl_pit38"):
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Завантаження доступне тільки для PRO-підписників")
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if st.session_state.pit38_akcje is not None:
                    st.session_state.pit38_akcje.to_excel(writer, sheet_name="Akcje", index=False)
                if st.session_state.pit38_dywidendy is not None:
                    st.session_state.pit38_dywidendy.to_excel(writer, sheet_name="Dywidendy", index=False)
                if st.session_state.pit38_zg is not None:
                    st.session_state.pit38_zg.to_excel(writer, sheet_name="PIT_ZG", index=False)
            output.seek(0)
            st.download_button(
                label="⬇️ Завантажити Excel",
                data=output,
                file_name=f"PIT-38_{st.session_state.selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ==============================================================================
# recalculate_reports + селектор року (МОДИФІКОВАНО)
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
    
    # Визначаємо поточний індекс
    current_index = 0
    if st.session_state.selected_year in year_options:
        current_index = year_options.index(st.session_state.selected_year)
    
    # Функція, яка викликається при зміні року
    def on_year_change():
        new_year = st.session_state.global_year
        # Якщо користувач не PRO – показуємо попередження і повертаємо старе значення
        if not st.session_state.get("is_pro", False):
            st.warning("🔒 Зміна року доступна тільки для PRO-підписників")
            # Примусово встановлюємо назад попереднє значення
            st.session_state.global_year = st.session_state.selected_year
        else:
            if new_year != st.session_state.selected_year:
                recalculate_reports(new_year)
    
    col_left, _ = st.columns([1, 5])
    with col_left:
        st.selectbox(
            "Wybierz rok:",
            options=year_options,
            key="global_year",
            index=current_index,
            on_change=on_year_change
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

# ==============================================================================
# ЗАПУСК
# ==============================================================================
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator")
# ====================== АВТОРИЗАЦІЯ ======================
require_auth()                     # якщо не увійшов – зупинить програму
check_subscription_status()        # оновлює статус підписки в session_state

# ====================== БОКОВА ПАНЕЛЬ ======================
show_auth_status_and_logout()      # показує статус і кнопку виходу
uploaded_files = render_sidebar()

# ====================== ОСНОВНИЙ ВМІСТ ======================
if st.session_state.broker_data is not None:
    # Видалено виклик require_pro_for_feature("Вибір року") – тепер він всередині on_year_change
    render_global_year_selector()
    render_main_tabs()
else:
    st.info("Будь ласка, завантажте CSV файли брокера та натисніть «Розрахувати все».")
