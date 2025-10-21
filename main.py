import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import sqlite3
from datetime import datetime, time
from nsepython import nse_eq, nse_eq_symbols

# ============================================================
#  STREAMLIT CONFIGURATION
# ============================================================
st.set_page_config(page_title="Stock Analysis System", layout="centered")

# ============================================================
#  SESSION STATE INITIALIZATION
# ============================================================
# These keep user data persistent across Streamlit reruns
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

# ============================================================
#  LOGIN / LOGOUT SYSTEM
# ============================================================

def do_login(username: str, password: str):
    """
    Simple login validation (static credentials for demo).
    On success: updates session state and reruns the app.
    """
    if username == "admin" and password == "123":
        st.session_state.logged_in = True
        st.session_state.username = username
        st.success("Login successful ✅")
        st.rerun()
    else:
        st.error("Invalid username or password ❌")

def do_logout():
    """Clears session data and logs out the user."""
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

# ============================================================
#  DATABASE INITIALIZATION & MIGRATION
# ============================================================

DB_FILE = "portfolio.db"

def init_db():
    """
    Initializes or upgrades the SQLite database.

    - Creates the base table if not present
    - Adds new columns if missing (migration)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # --- Base Table ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            stock_symbol TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # --- Migration Logic: Add new columns if missing ---
    cursor.execute("PRAGMA table_info('transactions')")
    cols = [r[1] for r in cursor.fetchall()]  # Extract column names

    # Add 'bid_price' column if not present
    if "bid_price" not in cols:
        try:
            cursor.execute("ALTER TABLE transactions ADD COLUMN bid_price REAL")
            conn.commit()
        except Exception as e:
            st.warning(f"Migration failed for 'bid_price' — {e}")
            conn.rollback()

    # Add 'status' column if not present
    if "status" not in cols:
        try:
            cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'EXECUTED'")
            conn.commit()
        except Exception as e:
            st.warning(f"Migration failed for 'status' — {e}")
            conn.rollback()

    conn.close()

# Initialize DB once
init_db()

# ============================================================
#  DATABASE HELPER FUNCTIONS
# ============================================================

def record_trade(username, stock_symbol, action, quantity, price, bid_price):
    """
    Records a trade into the database.
    
     ACID properties:
    - **Atomicity:** Uses a transaction (BEGIN ... COMMIT/ROLLBACK)
    - **Consistency:** Ensures valid numeric and status values
    - **Isolation:** Uses EXCLUSIVE lock to prevent concurrent conflicts
    - **Durability:** Changes are committed to disk permanently
    """

    # Validate numeric input
    try:
        quantity = int(quantity)
        price = float(price)
        bid_price = float(bid_price) if bid_price is not None else price
    except Exception:
        st.error("Invalid numeric inputs for quantity/price.")
        return
    
    if quantity <= 0:
        st.error("Quantity must be greater than zero.")
        return
    
    if action == "SELL":
        holdings = fetch_holdings(username)
        current_qty = 0

        if stock_symbol in holdings['stock_symbol'].values:
            current_qty = holdings.loc[holdings['stock_symbol'] == stock_symbol, "Quantity"].values[0]
        else:
            st.error(f"You do not own any shares of {stock_symbol} to sell.")
            return

        if quantity > current_qty:
            st.error(f"Cannot sell {quantity} shares. You only have {current_qty} shares.")
            return

    total = quantity * price
    status = "EXECUTED" if abs(price - bid_price) < 0.01 else "PENDING"

    try:
        # --- Begin Transaction ---
        conn = sqlite3.connect(DB_FILE, isolation_level="EXCLUSIVE")  # Ensures isolation
        cursor = conn.cursor()
        cursor.execute("BEGIN")

        # --- Insert trade ---
        cursor.execute("""
            INSERT INTO transactions (username, stock_symbol, action, quantity, price, total, bid_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, stock_symbol, action, quantity, price, total, bid_price, status))

        conn.commit()  # ✅ COMMIT ensures Atomicity & Durability

        # --- Feedback to user ---
        if status == "PENDING":
            st.info(f"📊 {action} order for {stock_symbol} placed at ₹{bid_price} — Pending execution.")
        else:
            st.success(f"✅ {action} order for {stock_symbol} executed at ₹{price}")

    except Exception as e:
        conn.rollback()  # ❌ ROLLBACK ensures Atomicity
        st.error(f"⚠️ Failed to record trade: {e}")
    finally:
        conn.close()

def fetch_transactions(username):
    """Fetches all transactions for a given user."""
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM transactions WHERE username=? ORDER BY timestamp DESC",
            conn, params=(username,)
        )
    except Exception as e:
        st.warning(f"DB read error: {e}")
        df = pd.DataFrame()
    conn.close()
    return df

def fetch_holdings(username):
    """
    Summarizes user holdings based on executed trades.
    Calculates net quantity and average buy price.
    """
    df = fetch_transactions(username)
    if df.empty:
        return pd.DataFrame()

    # Consider only executed trades
    df_exec = df[df["status"] == "EXECUTED"] if "status" in df.columns else df
    if df_exec.empty:
        return pd.DataFrame()

    # Helper: signed quantity (+ for BUY, - for SELL)
    def qty_signed(row):
        return row["quantity"] if row["action"] == "BUY" else -row["quantity"]

    # Aggregate holdings
    holdings = (
        df_exec.groupby("stock_symbol")
               .apply(lambda x: pd.Series({
                   "Quantity": x.apply(qty_signed, axis=1).sum(),
                   "Avg Price": (
                       x[x["action"] == "BUY"].apply(lambda r: r["quantity"] * r["price"], axis=1).sum()
                       / x[x["action"] == "BUY"]["quantity"].sum()
                       if x[x["action"] == "BUY"]["quantity"].sum() != 0 else 0
                   )
               }))
               .reset_index()
    )
    return holdings

# ============================================================
#  AUTO-UPDATER: PENDING ORDERS
# ============================================================

def update_pending_orders():
    """
    Checks and updates all pending orders automatically.

    - Executes pending orders if market price meets conditions
    - Cancels unexecuted orders after 3:30 PM (NSE close time)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Fetch pending trades
    try:
        df_pending = pd.read_sql_query("SELECT * FROM transactions WHERE status='PENDING'", conn)
    except Exception:
        df_pending = pd.DataFrame()

    now = datetime.now().time()

    if df_pending.empty:
        conn.close()
        return

    # --- Process each pending order ---
    for _, row in df_pending.iterrows():
        try:
            symbol = row["stock_symbol"]
            data = nse_eq(symbol)
            price_info = data.get("priceInfo", {})
            last = price_info.get("lastPrice", None)
            if last is None:
                continue

            current_price = float(last)

            # Execute if bid condition met
            if (row["action"] == "BUY" and current_price <= float(row["bid_price"])) or \
               (row["action"] == "SELL" and current_price >= float(row["bid_price"])):

                new_total = current_price * int(row["quantity"])
                cursor.execute("""
                    UPDATE transactions
                    SET status='EXECUTED', price=?, total=?
                    WHERE id=?
                """, (current_price, new_total, row["id"]))

            # Cancel after market close
            elif now >= time(15, 30):
                cursor.execute("""
                    UPDATE transactions
                    SET status='CANCELLED'
                    WHERE id=?
                """, (row["id"],))
        except Exception:
            continue

    conn.commit()
    conn.close()

# ============================================================
#  LOAD NSE STOCK SYMBOLS
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_all_stocks():
    """Loads all NSE stock symbols (cached for 1 day)."""
    try:
        symbols = nse_eq_symbols()
        if symbols:
            return sorted(symbols)
    except Exception:
        # Fallback symbols
        return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

# ============================================================
#  STOCK SEARCH & DISPLAY
# ============================================================

def show_stock_search():
    """Provides a search bar with live NSE data display."""
    st.subheader("🔍 Search for any NSE Stock")
    stock_list = load_all_stocks()

    # Dynamic search input
    query = st.text_input("Type to search (e.g., RELIANCE, NHPC, TCS):", key="stock_query").strip()
    filtered = [s for s in stock_list if query.upper() in s.upper()] if query else stock_list
    selected_stock = st.selectbox("Select a stock", filtered if filtered else ["No Match Found"], key="selected_stock_box")

    # Maintain selected stock state
    if "searched_stock" not in st.session_state:
        st.session_state.searched_stock = None

    # When user clicks search
    if st.button("Search"):
        if selected_stock == "No Match Found":
            st.error("No results found.")
            st.session_state.searched_stock = None
        else:
            st.session_state.searched_stock = selected_stock

    # Show stock info if searched
    if st.session_state.searched_stock:
        selected_stock = st.session_state.searched_stock
        try:
            data = nse_eq(selected_stock)
            price_info = data.get("priceInfo", {})
            meta_info = data.get("info", {})
            current_price = price_info.get("lastPrice", 0) or 0

            # --- Display Stock Information ---
            st.write(f"### 📊 {meta_info.get('companyName', selected_stock)}")
            st.metric("Current Price (₹)", round(float(current_price), 2))
            st.write(f"**Previous Close:** {price_info.get('previousClose', 'N/A')}")
            st.write(f"**Open:** {price_info.get('open', 'N/A')}")

            # Day high/low
            try:
                day_high = price_info.get("intraDayHighLow", {}).get("max", "N/A")
                day_low = price_info.get("intraDayHighLow", {}).get("min", "N/A")
                st.write(f"**Day High:** {day_high}")
                st.write(f"**Day Low:** {day_low}")
            except Exception:
                pass

            st.session_state["selected_stock_price"] = float(current_price)

            # --- Display 1-Month Price Chart ---
            try:
                stock = yf.Ticker(f"{selected_stock}.NS")
                hist = stock.history(period="1mo")
                if not hist.empty:
                    st.write("#### Price Chart (Last 1 Month)")
                    st.line_chart(hist["Close"])
            except Exception:
                pass

        except Exception as e:
            st.error(f"Error fetching stock details: {e}")

# ============================================================
#  MAIN APP FLOW
# ============================================================

# --- LOGIN SCREEN ---
if not st.session_state.logged_in:
    st.title("🔐 Please sign in")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        do_login(username.strip(), password)

# --- AFTER LOGIN ---
else:
    st.title("📈 SAS: Stock Analysis System")
    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")

    # Logout button
    if st.sidebar.button("Logout"):
        do_logout()

    # Navigation menu
    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Go To:", ["Dashboard", "Portfolio", "Trade", "Predict", "Compare", "Transaction History"])

    # Auto-refresh every minute to update prices/orders
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=60000, key="refresh_counter")
    except Exception:
        pass

    # Update pending orders before rendering
    update_pending_orders()

    # ========================================================
    # DASHBOARD PAGE
    # ========================================================
    if page == "Dashboard":
        try:
            # Fetch live NIFTY and BANKNIFTY prices
            nifty = yf.Ticker("^NSEI")
            banknifty = yf.Ticker("^NSEBANK")
            nif_price = nifty.history(period="1d")["Close"].iloc[-1]
            bn_price = banknifty.history(period="1d")["Close"].iloc[-1]

            col1, col2 = st.columns(2)
            col1.metric(label="NIFTY 50 📈", value=round(nif_price, 2))
            col2.metric(label="BANK NIFTY 📈", value=round(bn_price, 2))
        except Exception:
            pass
        show_stock_search()

    # ========================================================
    # PORTFOLIO PAGE
    # ========================================================
    elif page == "Portfolio":
        st.subheader("💼 Your Portfolio")
        holdings = fetch_holdings(st.session_state.username)
        if not holdings.empty:
            st.dataframe(holdings)
        else:
            st.info("No executed holdings yet.")

    # ========================================================
    # TRADE PAGE
    # ========================================================
    elif page == "Trade":
        left, right = st.columns([2, 1])
        with left:
            show_stock_search()
        with right:
            st.markdown("### 💹 Trade Action")

            selected_stock = st.session_state.get("searched_stock", None)
            current_price = st.session_state.get("selected_stock_price", 0.0)

            if selected_stock:
                # Trade form
                st.write(f"Current Price: ₹{current_price}")
                action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
                qty = st.number_input("Quantity", min_value=1, value=1)
                bid_price = st.number_input("Your Bid Price (₹)", min_value=0.0, value=float(current_price), step=0.5)
                total = qty * bid_price
                st.metric("Total Value (₹)", f"{total:,.2f}")

                # Place order
                if st.button("Place Order"):
                    record_trade(st.session_state.username, selected_stock, action, qty, current_price, bid_price)
            else:
                st.info("Select a stock to trade.")

    # ========================================================
    # PLACEHOLDER PAGES
    # ========================================================
    elif page == "Predict":
        st.write("Predict page under construction.")

    elif page == "Compare":
        st.write("Compare page under construction.")

    # ========================================================
    # TRANSACTION HISTORY PAGE
    # ========================================================
    elif page == "Transaction History":
        st.subheader("🧾 Transaction History")
        df = fetch_transactions(st.session_state.username)
        if not df.empty:
            st.dataframe(df)
        else:
            st.info("No transactions yet.")
