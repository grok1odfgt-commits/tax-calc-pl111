# ==============================================================================
# app.py — Головний UI Streamlit-застосунку (НОВИЙ ДИЗАЙН + МОДАЛЬНИЙ ЛОГІН + КАСТОМ TOP-BAR)
# ==============================================================================
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

# ====================== СУЧАСНИЙ CSS ======================
st.markdown("""
<style>
    header[data-testid="stHeader"] {
        display: none !important;
    }
    button[data-testid="collapsedControl"] {
        display: block !important;
        visibility: visible !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        z-index: 1001 !important;
        background: rgba(255, 255, 255, 0.95) !important;
        border: 1px solid #d0d4d8 !important;
        border-radius: 50% !important;
        width: 44px !important;
        height: 44px !important;
        box-shadow: 0 3px 10px rgba(0,0,0,0.15) !important;
        font-size: 20px !important;
        color: #1a3c5e !important;
        transition: all 0.2s ease;
    }
    button[data-testid="collapsedControl"]:hover {
        background: #e0e7ff !important;
        transform: scale(1.05);
    }
    section[data-testid="stSidebar"][aria-expanded="true"] button {
        display: block !important;
    }
    button[data-testid^="baseButton-header"],
    button[kind="header"]:not([data-testid="collapsedControl"]),
    button[aria-label*="menu"],
    button[aria-label*="More options"] {
        display: none !important;
    }
    .main > div:first-child {
        padding-top: 70px !important;
    }
    .block-container {
        padding-top: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    @media (max-width: 768px) {
        button[data-testid="collapsedControl"] {
            top: 16px !important;
            left: 16px !important;
            width: 52px !important;
            height: 52px !important;
            font-size: 24px !important;
            background: #4e8cff !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25) !important;
        }
        .main > div:first-child {
            padding-top: 80px !important;
        }
    }
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

# ====================== КАСТОМНИЙ TOP-BAR ======================
status_text = "✅ PRO" if st.session_state.get("is_pro", False) else "🔓 Free"
user_text = " • " + st.session_state.user.email.split('@')[0] if st.session_state.get("authenticated", False) else " • Гість"

logout_button_html = ""
if st.session_state.get("authenticated", False):
    logout_button_html = '<button id="top-logout-btn" style="background: rgba(255,255,255,0.18); color: white; border: 1px solid rgba(255,255,255,0.4); padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.98rem; transition: all 0.18s; display: flex; align-items: center; justify-content: center; height: 36px;">Вийти</button>'

top_bar_template = """
<div style="position: fixed; top: 0; left: 0; right: 0; height: 56px; background: linear-gradient(90deg, #1e40af, #3b82f6); color: white; z-index: 999; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-family: system-ui, sans-serif;">
    <div style="font-size: 1.45rem; font-weight: 700; display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.6rem;">🧮</span> FIFO Tax Calculator
    </div>
    <div style="display: flex; align-items: center; gap: 24px;">
        <span style="font-weight: 600; font-size: 1.05rem;">{}</span>
        <span style="font-size: 1.05rem; opacity: 0.95;">{}</span>
        {}
    </div>
</div>

<script>
    const btn = document.getElementById('top-logout-btn');
    if (btn) {
        btn.addEventListener('click', () => {
            const buttons = window.parent.document.querySelectorAll('button');
            for (let b of buttons) {
                if (b.textContent.trim() === 'Вийти') {
                    b.click();
                    return;
                }
            }
            setTimeout(() => window.parent.location.reload(), 300);
        });
    }
</script>
"""

top_bar_html = top_bar_template.format(status_text, user_text, logout_button_html)

st.markdown(top_bar_html, unsafe_allow_html=True)

# ====================== ІНІЦІАЛІЗАЦІЯ ======================
st.set_page_config(layout="wide", page_title="FIFO Tax Calculator", page_icon="🧮")
init_auth_session()
show_auth_status_and_logout()

# ====================== КЛЮЧІ СЕСІЇ ======================
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

# ====================== ФУНКЦІЇ ВКЛАДОК ======================
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

# (всі інші функції render_... залишаються без змін, як у твоєму коді)

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
