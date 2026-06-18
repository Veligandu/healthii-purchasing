import streamlit as st

pg = st.navigation([
    st.Page("pages/1_Purchasing_Agent.py",    title="Purchasing Agent",      icon=":material/shopping_cart:"),
    st.Page("pages/2_GH_Rechnungskontrolle.py", title="GH-Rechnungskontrolle", icon=":material/description:"),
    st.Page("pages/3_Pricing.py",             title="Pricing",              icon=":material/payments:"),
])
pg.run()
