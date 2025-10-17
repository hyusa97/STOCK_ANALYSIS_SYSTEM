import streamlit as st

st.set_page_config(page_title="Stock Analysis System", layout="centered")

# --- initialize session state ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

def do_login(username: str, password: str):
    # Simple demo credentials
    if username == "admin" and password == "1234":
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

# --- UI ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align:center;'>Please sign in</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            do_login(username.strip(), password)
else:
    st.markdown("<h1 style='text-align:center;'>Stock Analysis System</h1>", unsafe_allow_html=True)
    st.write("---")
    st.write(f"Logged in as: **{st.session_state.username}**")

    if st.button("Logout"):
        do_logout()
