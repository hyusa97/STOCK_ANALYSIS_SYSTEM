def validate_user(username, password):
    # Simple demo user validation
    return username == "admin" and password == "1234"

def check_login():
    return "logged_in" in st.session_state and st.session_state.logged_in
