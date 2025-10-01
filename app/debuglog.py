# -*- coding: utf-8 -*-
# Enkel, återanvändbar debug-logg för Streamlit + journald
import datetime as _dt

try:
    import streamlit as st
except Exception:
    st = None

DEBUG_KEY = "debug_enabled"           # vår nya nyckel
COMPAT_KEYS = ("backtest_debug",)     # äldre nycklar vi respekterar

def setup_debug_ui(page_title: str = "") -> bool:
    """Rita debug-UI i sidopanelen och returnera om debug är aktivt."""
    if st is None:
        return False
    st.sidebar.subheader("🛠️ Debug")
    default = False
    for k in (DEBUG_KEY,) + COMPAT_KEYS:
        default = default or bool(st.session_state.get(k, False))
    enabled = st.sidebar.checkbox("Debug 0.2", value=default or True, key=DEBUG_KEY)
    # håll kompatibilitetsnycklar i fas
    for k in COMPAT_KEYS:
        st.session_state[k] = enabled
    if page_title:
        st.sidebar.caption(f"Sida: {page_title}")
    return enabled

def _emit(level: str, msg) -> None:
    ts = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    # -> journald
    try:
        print(line, flush=True)
    except Exception:
        pass
    # -> UI
    if st is not None and st.session_state.get(DEBUG_KEY, False):
        try:
            if level == "INFO":
                st.info(msg)
            elif level == "WARN":
                st.warning(msg)
            elif level == "ERROR":
                st.error(msg)
            else:
                st.write(msg)
        except Exception:
            pass

def log_info(msg):  _emit("INFO",  msg)
def log_warn(msg):  _emit("WARN",  msg)
def log_error(msg): _emit("ERROR", msg)

def df_brief(df, name="df"):
    """Kort rad om en DataFrame (för logg). Klarar None/fel."""
    try:
        import pandas as pd  # noqa
        if df is None:
            return f"{name}: None"
        r = getattr(df, "shape", None)
        n = len(df) if hasattr(df, "__len__") else "?"
        try:
            d0 = getattr(df.index.min(), "date", lambda: None)()
            d1 = getattr(df.index.max(), "date", lambda: None)()
        except Exception:
            d0 = d1 = None
        cols = list(getattr(df, "columns", []))[:8]
        return f"{name}: rows={n}, shape={r}, dates={d0}→{d1}, cols={cols}"
    except Exception as e:
        return f"{name}: (kunde inte summera: {e})"
