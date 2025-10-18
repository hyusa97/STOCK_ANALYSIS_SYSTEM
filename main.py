import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# -----------------------
# Page config
# -----------------------
st.set_page_config(page_title="Stock Analysis System", layout="centered")

# -----------------------
# Initialize session state
# -----------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

# -----------------------
# Login / Logout functions
# -----------------------
def do_login(username: str, password: str):
    if username == "admin" and password == "1234":  # demo credentials
        st.session_state.logged_in = True
        st.session_state.username = username
        st.success("Login successful")
        st.rerun()  # updated for latest Streamlit
    else:
        st.error("Invalid username or password")

def do_logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()  # updated for latest Streamlit

# -----------------------
# Login Page
# -----------------------
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align:center;'>Please sign in</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            do_login(username.strip(), password)

else:
    st.markdown("<h1 style='text-align:center;'>SAS: Stock Analysis System</h1>", unsafe_allow_html=True)
    st.write("---")
    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")

    if st.sidebar.button("Logout"):
        do_logout()

    # Sidebar navigation
    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Go To:", ["Dashboard", "Portfolio", "Predict", "Compare"])

    # Auto-refresh every 60 seconds (optional)
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=60000, key="refresh_counter")
    except ImportError:
        pass  # ignore if package not installed

    # -----------------------
    # Dashboard
    # -----------------------
    if page == "Dashboard":
        
        try:
            nifty = yf.Ticker("^NSEI")
            banknifty = yf.Ticker("^NSEBANK")

            nif_data = nifty.history(period="1d")
            bn_data = banknifty.history(period="1d")

            nif_price = nif_data['Close'].iloc[-1]
            bn_price = bn_data['Close'].iloc[-1]

            col1, col2 = st.columns(2)
            col1.metric(label="NIFTY 50 📈", value=round(nif_price, 2))
            col2.metric(label="BANK NIFTY 📈", value=round(bn_price, 2))
        except Exception as e:
            st.error(f"Error fetching stock data: {e}")

    # -----------------------
    # Placeholder pages
    # -----------------------
    elif page == "Portfolio":
        st.write("Portfolio page under construction.")
    elif page == "Predict":
        st.write("Predict page under construction.")
    elif page == "Compare":
        st.write("Compare page under construction.")
