import streamlit as st

st.set_page_config(page_title="Dalatraderbot", layout="centered")

st.title("Dalatraderbot ✅")
st.write(
    "Det här är en minimal testapp. "
    "Om du ser denna sida kör containern korrekt."
)

with st.form("echo"):
    text = st.text_input("Skriv något")
    submitted = st.form_submit_button("Skicka")
    if submitted:
        st.success(f"Du skrev: {text}")
