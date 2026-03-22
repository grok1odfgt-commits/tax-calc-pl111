st.markdown("""
<style>
    /* Забезпечуємо повну висоту таблиць */
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
    /* Приховуємо верхню панель (з анімацією завантаження) */
    header[data-testid="stHeader"] {
        display: none;
    }
    /* Видаляємо всі верхні відступи контейнера */
    .main > div:first-child {
        padding-top: 0rem;
    }
    .block-container {
        padding-top: 0rem;
        margin-top: -0.5rem;  /* зсуваємо ще трохи, якщо залишився зазор */
    }
</style>
""", unsafe_allow_html=True)
