import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
import json

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
    if username == "admin" and password == "123":
        st.session_state.logged_in = True
        st.session_state.username = username
        st.success("Login successful")
        st.rerun()
    else:
        st.error("Invalid username or password")

def do_logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

# -----------------------
#  Stock list
# -----------------------
@st.cache_data(ttl=86400, show_spinner=False)
def load_all_stocks():
    """Try fetching NSE stock list with multiple fallbacks."""
    try:
        # 1️⃣ Try nsepython
        from nsepython import nse_eq_symbols
        symbols = nse_eq_symbols()
        if symbols:
            st.info("✅ Loaded list via nsepython")
            return sorted(symbols)
    except Exception as e1:
        st.warning(f"nsepython failed: {e1}")

    try:
        # 2️⃣ Try nsetools
        from nsetools import Nse
        nse = Nse()
        all_stocks = nse.get_stock_codes()
        symbols = list(all_stocks.keys())[1:]  # skip header
        if symbols:
            st.info("✅ Loaded list via nsetools")
            return sorted(symbols)
    except Exception as e2:
        st.warning(f"nsetools failed: {e2}")

    try:
        # 3️⃣ GitHub fallback CSV
        df = pd.read_csv(
            "https://raw.githubusercontent.com/saahiluppal/nse-listed-stocks/main/nse_stocks.csv"
        )
        if "Symbol" in df.columns:
            symbols = df["Symbol"].dropna().unique().tolist()
            st.info("✅ Loaded list via GitHub CSV")
            return sorted(symbols)
    except Exception as e3:
        st.warning(f"GitHub CSV fallback failed: {e3}")

    # 4️⃣ Final static fallback
    st.error("⚠️ All sources failed. Using minimal fallback list.")
    return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

# Optional: Cache locally in file for offline use
def cache_stock_list_locally(symbols):
    try:
        with open("stocks_cache.json", "w") as f:
            json.dump(symbols, f)
    except Exception:
        pass

def load_cached_stocks():
    if os.path.exists("stocks_cache.json"):
        try:
            with open("stocks_cache.json", "r") as f:
                return json.load(f)
        except Exception:
            return []

# -----------------------
# Stock Search Section
# -----------------------
def show_stock_search():
    st.subheader("🔍 Search for any NSE Stock")

    cached_symbols = load_cached_stocks()
    stock_list = cached_symbols if cached_symbols else load_all_stocks()
    if not cached_symbols:
        cache_stock_list_locally(stock_list)

    query = st.text_input("Type to search (e.g., RELIANCE, NHPC, TCS):").strip()
    filtered = [s for s in stock_list if query.upper() in s.upper()] if query else stock_list
    selected_stock = st.selectbox("Select a stock", filtered if filtered else ["No Match Found"])

    if st.button("Search"):
        if selected_stock == "No Match Found":
            st.error("Your search returned no results. Try again.")
            return
        try:
            stock_symbol = f"{selected_stock}.NS"
            stock = yf.Ticker(stock_symbol)
            info = getattr(stock, "info", {}) or {}

            if not info or "currentPrice" not in info:
                st.error("⚠️ No data found for this stock. Try another.")
                return

            st.write(f"### 📊 {info.get('longName', selected_stock)}")
            st.metric("Current Price (₹)", round(info.get("currentPrice", 0), 2))
            st.write(f"**Market Cap:** {info.get('marketCap', 'N/A')}")
            st.write(f"**PE Ratio:** {info.get('trailingPE', 'N/A')}")
            st.write(f"**52 Week High:** {info.get('fiftyTwoWeekHigh', 'N/A')}")
            st.write(f"**52 Week Low:** {info.get('fiftyTwoWeekLow', 'N/A')}")
            st.write(f"**Volume:** {info.get('volume', 'N/A')}")
            st.write(f"**Sector:** {info.get('sector', 'N/A')}")
            st.write(f"**Industry:** {info.get('industry', 'N/A')}")

            website = info.get("website")
            if website:
                st.write(f"**Website:** [{website}]({website})")

            hist = stock.history(period="1mo")
            if not hist.empty:
                st.write("#### Price Chart (Last 1 Month)")
                st.line_chart(hist["Close"])
            else:
                st.info("No recent historical data available for this stock.")
        except Exception as e:
            st.error(f"Error fetching stock details: {e}")

# -----------------------
# LOGIN PAGE
# -----------------------
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align:center;'>Please sign in</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            do_login(username.strip(), password)

# -----------------------
# MAIN APP (after login)
# -----------------------
else:
    st.markdown("<h1 style='text-align:center;'>SAS: Stock Analysis System</h1>", unsafe_allow_html=True)
    st.write("---")
    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")

    if st.sidebar.button("Logout"):
        do_logout()

    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Go To:", ["Dashboard", "Portfolio", "Predict", "Compare"])

    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=60000, key="refresh_counter")
    except ImportError:
        pass

    # -----------------------
    # PAGE: Dashboard
    # -----------------------
    if page == "Dashboard":
        try:
            nifty = yf.Ticker("^NSEI")
            banknifty = yf.Ticker("^NSEBANK")
            nif_price = nifty.history(period="1d")["Close"].iloc[-1]
            bn_price = banknifty.history(period="1d")["Close"].iloc[-1]

            col1, col2 = st.columns(2)
            col1.metric(label="NIFTY 50 📈", value=round(nif_price, 2))
            col2.metric(label="BANK NIFTY 📈", value=round(bn_price, 2))
        except Exception as e:
            st.error(f"Error fetching index data: {e}")

        show_stock_search()

    elif page == "Portfolio":
        st.write("Portfolio page under construction.")
        # Optional: show_stock_search()

    elif page == "Predict":
        st.write("Predict page under construction.")

    elif page == "Compare":
        st.write("Compare page under construction.")
