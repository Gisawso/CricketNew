import hashlib
import sqlite3
import pandas as pd
import streamlit as st

# --- 1. DATABASE SETUP (Stores users & approval status) ---
conn = sqlite3.connect("users_access.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        role TEXT,
        status TEXT
    )
""")
conn.commit()


def hash_pw(password):
  return hashlib.sha256(str.encode(password)).hexdigest()


# Automatically create your Owner account if it doesn't exist yet
# CHANGE "admin123" to your own private password!
OWNER_USER = "owner"
OWNER_PASS = hash_pw("admin123")
c.execute(
    "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)",
    (OWNER_USER, OWNER_PASS, "owner", "approved"),
)
conn.commit()

# --- 2. SESSION STATE INITIALIZATION ---
if "logged_in" not in st.session_state:
  st.session_state.logged_in = False
  st.session_state.username = ""
  st.session_state.role = ""

# --- 3. SIGN-IN / SIGN-UP GATEWALL ---
if not st.session_state.logged_in:
  st.title("🏏 CricDeCode Pro — Access Portal")
  st.info("Sign in or request access from the owner to launch the analyzer.")

  tab_login, tab_signup = st.tabs(["🔐 Sign In", "📝 Request Access"])

  with tab_login:
    login_user = st.text_input("Username", key="login_u")
    login_pass = st.text_input("Password", type="password", key="login_p")

    if st.button("Sign In", type="primary"):
      c.execute(
          "SELECT password, role, status FROM users WHERE username = ?",
          (login_user,),
      )
      record = c.fetchone()

      if record and record[0] == hash_pw(login_pass):
        if record[2] == "approved":
          st.session_state.logged_in = True
          st.session_state.username = login_user
          st.session_state.role = record[1]
          st.rerun()
        elif record[2] == "pending":
          st.warning(
              "⏳ Your account is still pending owner approval. Check back"
              " soon!"
          )
        else:
          st.error("🚫 Your access request was denied.")
      else:
        st.error("❌ Invalid username or password.")

  with tab_signup:
    new_user = st.text_input("Choose a Username", key="reg_u")
    new_pass = st.text_input("Choose a Password", type="password", key="reg_p")

    if st.button("Request Access"):
      if new_user and new_pass:
        try:
          c.execute(
              "INSERT INTO users VALUES (?, ?, ?, ?)",
              (new_user, hash_pw(new_pass), "user", "pending"),
          )
          conn.commit()
          st.success(
              "✅ Request sent! You can sign in once the owner approves your"
              " account."
          )
        except sqlite3.IntegrityError:
          st.error("That username is already taken.")
      else:
        st.warning("Please enter both a username and password.")

  # STOPS THE ENTIRE APP FROM LOADING BELOW THIS LINE UNTIL APPROVED & LOGGED IN
  st.stop()

# ==============================================================================
# EVERYTHING BELOW THIS LINE ONLY LOADS FOR APPROVED, SIGNED-IN USERS
# ==============================================================================

# --- 4. SIDEBAR ACCOUNT & OWNER APPROVAL PANEL ---
st.sidebar.success(
    f"Signed in as: **{st.session_state.username}** ({st.session_state.role})"
)
if st.sidebar.button("Log Out"):
  st.session_state.logged_in = False
  st.session_state.username = ""
  st.session_state.role = ""
  st.rerun()

# Owner-Only Approval Dashboard
if st.session_state.role == "owner":
  with st.expander(
      "👑 OWNER ADMIN PANEL — Approve / Manage Users", expanded=True
  ):
    st.subheader("Pending Access Requests")
    pending_df = pd.read_sql_query(
        "SELECT username, role, status FROM users WHERE status = 'pending'",
        conn,
    )

    if pending_df.empty:
      st.caption("No pending requests right now.")
    else:
      for idx, row in pending_df.iterrows():
        col1, col2, col3 = st.columns([2, 1, 1])
        col1.write(f"**{row['username']}**")
        if col2.button("✅ Approve", key=f"app_{row['username']}"):
          c.execute(
              "UPDATE users SET status = 'approved' WHERE username = ?",
              (row["username"],),
          )
          conn.commit()
          st.rerun()
        if col3.button("❌ Deny", key=f"den_{row['username']}"):
          c.execute(
              "UPDATE users SET status = 'denied' WHERE username = ?",
              (row["username"],),
          )
          conn.commit()
          st.rerun()

    st.markdown("---")
    st.subheader("All Registered Users")
    all_users = pd.read_sql_query(
        "SELECT username, role, status FROM users", conn
    )
    st.dataframe(all_users, use_container_width=True)

# --- YOUR EXISTING TELEMETRY & ANALYZER CODE GOES RIGHT BELOW HERE ---
from datetime import datetime
import pandas as pd
import streamlit as st

# --- INITIALIZE SESSION STATE ---
if "telemetry_log" not in st.session_state:
  st.session_state.telemetry_log = []

if "logged_in" not in st.session_state:
  st.session_state.logged_in = False
  st.session_state.is_owner = False

# --- SIDEBAR: AUTHENTICATION & ACCESS ---
st.sidebar.header("🔐 User Portal")

if not st.session_state.logged_in:
  username = st.sidebar.text_input("Username")
  password = st.sidebar.text_input("Password", type="password")

  if st.sidebar.button("Log In"):
    # Mock authentication (replace with secure storage for production)
    if username == "owner" and password == "admin123":
      st.session_state.logged_in = True
      st.session_state.is_owner = True
      st.success("Logged in as Owner!")
      st.rerun()
    elif username:
      st.session_state.logged_in = True
      st.session_state.is_owner = False
      st.success(f"Welcome, {username}!")
      st.rerun()
    else:
      st.sidebar.error("Please enter valid credentials.")
else:
  role_badge = "👑 Owner / Admin" if st.session_state.is_owner else "👤 Standard User"
  st.sidebar.write(f"Status: **{role_badge}**")
  if st.sidebar.button("Log Out"):
    st.session_state.logged_in = False
    st.session_state.is_owner = False
    st.rerun()

# --- SIDEBAR: UNITS & CONFIGURATION ---
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Telemetry Settings")

unit_system = st.sidebar.radio("Distance Units", ["Meters (m)", "Feet (ft)"])
unit_multiplier = 3.28084 if "Feet" in unit_system else 1.0
unit_suffix = "ft" if "Feet" in unit_system else "m"

pitch_length_input = st.sidebar.slider(
    f"Pitch Length ({unit_suffix})",
    min_value=40.0 if "Feet" in unit_system else 12.0,
    max_value=72.0 if "Feet" in unit_system else 22.12,
    value=66.0 if "Feet" in unit_system else 20.12,
    step=0.5,
)

# --- OWNER-EXCLUSIVE CONTROLS ---
if st.session_state.is_owner:
  st.sidebar.markdown("---")
  st.sidebar.subheader("👑 Owner Tools")
  if st.sidebar.button("🗑️ Reset All Session Telemetry"):
    st.session_state.telemetry_log = []
    st.sidebar.success("Session reset successfully!")
    st.rerun()

  calibration_mode = st.sidebar.checkbox(
      "Enable Pro High-Speed Frame Sampling", value=True
  )

# --- MAIN APP METRICS DEMO ---
st.title("🏏 CricDeCode Pro Telemetry Engine")

# Example calculated values from CV model
speed_kmh = 134.8
raw_pitch_y_m = 6.25
display_pitch_y = raw_pitch_y_m * unit_multiplier

col1, col2, col3 = st.columns(3)
col1.metric("Delivery Speed", f"{speed_kmh} KM/H")
col2.metric("Impact Distance", f"{display_pitch_y:.1f} {unit_suffix}")
col3.metric("Length Classification", "Good Length")