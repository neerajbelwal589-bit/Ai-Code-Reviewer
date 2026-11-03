
import streamlit as st
from auth import create_table, register_user, login_user


def render_auth_page():

    create_table()

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        return True

    st.title("🔐 AI Code Reviewer")
    st.write("Login or create your account")

    login_tab, register_tab = st.tabs(
        ["Login", "Registration"]
    )

    # LOGIN SECTION
    with login_tab:

        st.subheader("Welcome Back")

        with st.form("login_form"):

            email = st.text_input("Email")
            password = st.text_input(
                "Password",
                type="password"
            )

            login_btn = st.form_submit_button("Login")

        if login_btn:

            user = login_user(email, password)

            if user:

                st.session_state.logged_in = True
                st.session_state.user = user

                st.success("Login Successful!")
                st.rerun()

            else:
                st.error("Invalid Email or Password")

    # REGISTRATION SECTION
    with register_tab:

        st.subheader("Create New Account")

        with st.form("register_form"):

            name = st.text_input("Full Name")
            email = st.text_input("Email")
            password = st.text_input(
                "Password",
                type="password"
            )

            confirm_password = st.text_input(
                "Confirm Password",
                type="password"
            )

            register_btn = st.form_submit_button(
                "Create Account"
            )

        if register_btn:

            if password != confirm_password:

                st.error("Passwords do not match")

            else:

                success, message = register_user(
                    name, email, password
                )

                if success:
                    st.success(message)
                else:
                    st.error(message)

    return False
