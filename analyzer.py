import streamlit as st
import cv2
import numpy as np
import tempfile
import os
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Page Configuration
st.set_page_config(
    page_title="CricDeCode Local | Line, Length & Speed",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button {
        width: 100%; border-radius: 8px; height: 3em;
        background-color: #00c853; color: white; font-weight: bold; border: none;
    }
    .stButton>button:hover { background-color: #009624; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #00e676; }
    </style>
""", unsafe_allow_html=True)

st.title("🏏 CricDeCode Local: Telemetry & Pitch Map")
st.caption("Ball Speed, Line & Length Analyzer")
st.divider()

log_file = "session_log.csv"

def draw_pitch_map(df=None, current_point=None):
    """Draws a cricket pitch diagram and plots bounce locations."""
    fig, ax = plt.subplots(figsize=(4, 7))
    fig.patch.set_facecolor('#0e1117')
    ax.set_facecolor('#c2b280') # Pitch turf color

    # Pitch dimensions (normalized: X from -1.5 to 1.5 meters, Y from 0 to 20.12 meters)
    ax.set_xlim(-1.8, 1.8)
    ax.set_ylim(0, 21)

    # Length Zone Shading (from batsman's end at Y=0)
    ax.axhspan(0, 2, color='#ff5252', alpha=0.25, label='Yorker (0-2m)')
    ax.axhspan(2, 6, color='#ffab40', alpha=0.25, label='Full (2-6m)')
    ax.axhspan(6, 8, color='#00e676', alpha=0.30, label='Good Length (6-8m)')
    ax.axhspan(8, 14, color='#40c4ff', alpha=0.25, label='Short (8m+)')

    # Crease lines
    ax.axhline(1.22, color='white', linewidth=2) # Popping crease
    ax.axhline(0, color='white', linewidth=2)    # Bowling/Stump crease
    ax.plot([-0.8, -0.8], [0, 1.22], color='white', linewidth=1.5) # Return crease L
    ax.plot([0.8, 0.8], [0, 1.22], color='white', linewidth=1.5)   # Return crease R

    # Stumps (3 stumps at Y=0)
    for x_pos in [-0.11, 0, 0.11]:
        ax.plot(x_pos, 0.1, marker='o', markersize=6, color='#ff1744')

    # Plot historical points
    if df is not None and not df.empty and "Pitch_X" in df.columns:
        ax.scatter(df["Pitch_X"], df["Pitch_Y"], color='#ffffff', edgecolors='black', s=60, alpha=0.7, zorder=4)

    # Plot current delivery highlight
    if current_point is not None:
        ax.scatter(current_point[0], current_point[1], color='#ff1744', edgecolors='white', s=140, zorder=5, label='Latest Ball')

    ax.set_title("Pitch Map (Batsman's End at Bottom)", color='white', fontsize=10, pad=10)
    ax.set_ylabel("Distance from Batsman Stumps (m)", color='white', fontsize=9)
    ax.set_xticks([-1.0, 0, 1.0])
    ax.set_xticklabels(["Off Side", "Stumps", "Leg Side"], color='white', fontsize=9)
    ax.tick_params(axis='y', colors='white')
    
    # Legend outside
    ax.legend(loc='upper right', fontsize=7, facecolor='#1e222b', edgecolor='none', labelcolor='white')
    return fig

# Sidebar: Session History
with st.sidebar:
    st.header("📊 Session Telemetry")
    history_df = pd.read_csv(log_file) if os.path.exists(log_file) else pd.DataFrame()
    
    if not history_df.empty:
        st.metric("Top Speed", f"{history_df['Speed (km/h)'].max():.1f} km/h")
        st.metric("Avg Speed", f"{history_df['Speed (km/h)'].mean():.1f} km/h")
        st.divider()
        st.subheader("Delivery Log")
        st.dataframe(history_df[["Time", "Speed (km/h)", "Line", "Length"]], use_container_width=True, hide_index=True)
        
        if st.button("🗑️ Clear Session Log"):
            os.remove(log_file)
            st.rerun()
    else:
        st.info("No deliveries logged yet.")

# Main Layout: 3 Columns (Video, Controls/Metrics, Pitch Map)
col1, col2, col3 = st.columns([1.2, 1, 1], gap="medium")

latest_coords = None

with col1:
    st.subheader("1. Net Video")
    uploaded_file = st.file_uploader("Upload delivery (.mp4 or .mov)", type=["mp4", "mov"])
    if uploaded_file is not None:
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tfile.write(uploaded_file.read())
        video_path = tfile.name
        st.video(video_path)

with col2:
    st.subheader("2. Calibration & Telemetry")
    distance_meters = st.slider("Tracking Distance (m)", 5.0, 22.0, 18.0, 0.5)
    stump_center_ratio = st.slider(
        "Stump Center Position (Left ↔ Right)", 
        0.2, 0.8, 0.5, 0.05,
        help="Adjust if the camera isn't dead-center behind the stumps (0.5 = exact center of video)."
    )
    batting_hand = st.radio("Batsman Handedness", ["Right-Handed", "Left-Handed"], horizontal=True)

    if uploaded_file is not None and st.button("🚀 Analyze Delivery"):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if total_frames == 0:
            st.error("Could not read video.")
        else:
            progress_bar = st.progress(0)
            trajectory = [] # Stores (frame_num, center_x, center_y)
            frame_count = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                frame_count += 1
                if frame_count % 10 == 0:
                    progress_bar.progress(min(frame_count / total_frames, 1.0))

                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([180, 255, 255]))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    if 15 < area < 450:
                        x, y, w, h = cv2.boundingRect(cnt)
                        cx, cy = x + w / 2, y + h / 2
                        trajectory.append((frame_count, cx, cy))
                        break # Track primary ball candidate per frame

            cap.release()
            progress_bar.empty()

            if len(trajectory) > 5:
                # 1. Speed Calculation
                start_f = trajectory[0][0]
                end_f = trajectory[-1][0]
                time_sec = max((end_f - start_f) / fps, 0.1)
                speed_kmh = (distance_meters / time_sec) * 3.6

                # 2. Bounce Point Detection (Lowest point on screen = highest Y pixel value)
                bounce_point = max(trajectory, key=lambda item: item[2])
                _, bx, by = bounce_point

                # Map pixel X to Pitch X (-1.5m to +1.5m relative to stumps)
                stump_pixel_x = frame_width * stump_center_ratio
                norm_x = ((bx - stump_pixel_x) / (frame_width * 0.35)) * 1.5
                if batting_hand == "Left-Handed":
                    norm_x = -norm_x # Flip off/leg side for left-handers

                # Classify Line
                if norm_x < -0.35:
                    line_label = "Outside Off"
                elif -0.35 <= norm_x < -0.12:
                    line_label = "Off Stump"
                elif -0.12 <= norm_x <= 0.12:
                    line_label = "Middle Stump"
                elif 0.12 < norm_x <= 0.35:
                    line_label = "Leg Stump"
                else:
                    line_label = "Down Leg"

                # Map pixel Y to Length from batsman's stumps (0m to 14m)
                # Lower on screen (larger Y) means closer to batsman (smaller distance from stumps)
                pitch_y_meters = max(0.5, min(14.0, (1.0 - (by / frame_height)) * 16.0))

                # Classify Length
                if pitch_y_meters < 2.0:
                    length_label = "Yorker"
                elif pitch_y_meters < 6.0:
                    length_label = "Full"
                elif pitch_y_meters < 8.0:
                    length_label = "Good Length"
                else:
                    length_label = "Short"

                latest_coords = (norm_x, pitch_y_meters)

                # Display Metrics
                st.success("Telemetry Extracted!")
                m1, m2, m3 = st.columns(3)
                m1.metric("Speed", f"{speed_kmh:.1f} km/h")
                m2.metric("Line", line_label)
                m3.metric("Length", length_label)

                # Save to CSV
                new_row = pd.DataFrame({
                    "Time": [datetime.now().strftime("%H:%M:%S")],
                    "Speed (km/h)": [round(speed_kmh, 1)],
                    "Line": [line_label],
                    "Length": [length_label],
                    "Pitch_X": [round(norm_x, 2)],
                    "Pitch_Y": [round(pitch_y_meters, 2)]
                })
                if os.path.exists(log_file):
                    new_row.to_csv(log_file, mode='a', header=False, index=False)
                else:
                    new_row.to_csv(log_file, index=False)
                
                # Reload history for map update
                history_df = pd.read_csv(log_file)
            else:
                st.warning("Could not track a clear bounce trajectory. Try a clip filmed from behind the bowler or batsman.")

with col3:
    st.subheader("3. Pitch Map")
    fig = draw_pitch_map(history_df, latest_coords)
    st.pyplot(fig)