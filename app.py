import streamlit as st
import cv2
import tempfile
import os
import zipfile
import io
from PIL import Image
import yt_dlp

# Page Config
st.set_page_config(
    page_title="Video Screenshot Extractor",
    page_icon="📸",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: #FF4B4B;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        font-size: 1.1rem;
        text-align: center;
        color: #555555;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.6rem;
    }
    .stButton>button:hover {
        background-color: #FF2B2B;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📸 Video Screenshot Extractor</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Video upload karein ya online link daalein — 1 second me screenshots tayar!</div>', unsafe_allow_html=True)

# Settings Sidebar
st.sidebar.header("⚙️ Settings")
interval_sec = st.sidebar.number_input("Screenshot Interval (Seconds)", min_value=0.1, max_value=60.0, value=1.0, step=0.5, help="Default is 1.0 second")
max_frames = st.sidebar.number_input("Max Screenshots Limit", min_value=5, max_value=500, value=100, step=10, help="Standard memory limit for cloud")
image_format = st.sidebar.selectbox("Image Format", ["JPG", "PNG"])

def format_timestamp(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    if mins > 0:
        return f"{mins:02d}m_{secs:02d}s"
    return f"{secs:02d}s_{millis:03d}ms" if millis > 0 else f"{secs:02d}s"

def extract_frames(video_path, interval, max_limit):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        st.error("❌ Video open nahi ho pa rahi hai. Kripya file ya link dobara check karein.")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if fps <= 0 or not fps:
        fps = 30.0 # Default fallback

    frame_step = max(1, int(fps * interval))
    
    extracted = []
    current_frame = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    count = 0
    while cap.isOpened() and count < max_limit:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            break
            
        timestamp_sec = current_frame / fps
        time_label = format_timestamp(timestamp_sec)
        
        # Convert BGR (OpenCV) to RGB (PIL/Streamlit)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        
        extracted.append({
            "image": pil_img,
            "timestamp": time_label,
            "seconds": timestamp_sec
        })
        
        count += 1
        current_frame += frame_step
        
        # Progress calculation
        progress_val = min(1.0, current_frame / total_frames) if total_frames > 0 else 0.5
        progress_bar.progress(progress_val)
        status_text.text(f"Processing... Screenshot #{count} extracted at {time_label}")
        
    cap.release()
    progress_bar.empty()
    status_text.empty()
    return extracted

# Tab layout
tab1, tab2 = st.tabs(["📁 Upload Video File", "🔗 Online Video Link (YouTube / URL)"])

video_file_path = None

with tab1:
    uploaded_file = st.file_uploader("Video File Select Karein", type=["mp4", "mov", "avi", "mkv", "webm"])
    if uploaded_file is not None:
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(temp_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        video_file_path = temp_file_path

with tab2:
    online_url = st.text_input("Online Video Link Paste Karein (YouTube, Direct MP4 URL, etc.)")
    if online_url:
        if st.button("🔗 Load Video Link"):
            with st.spinner("Video stream fetch ho raha hai... Please wait..."):
                try:
                    ydl_opts = {
                        'format': 'best[ext=mp4]/best',
                        'quiet': True,
                        'no_warnings': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(online_url, download=False)
                        video_url = info.get('url', None)
                        if video_url:
                            st.session_state['online_video_path'] = video_url
                            st.session_state['video_title'] = info.get('title', 'Online Video')
                            st.success(f"✅ Video stream loaded: {info.get('title', 'Online Video')}")
                        else:
                            st.error("❌ Is link se video extract nahi ho payi.")
                except Exception as e:
                    st.error(f"❌ Error loading video link: {str(e)}")

    if 'online_video_path' in st.session_state and not video_file_path:
        video_file_path = st.session_state['online_video_path']

# Processing Trigger
if video_file_path:
    st.markdown("---")
    st.subheader("⚡ Ready to Process")
    
    if st.button("🚀 Extract Screenshots Now", key="process_btn"):
        with st.spinner("Screenshots extract ho rahe hain..."):
            frames = extract_frames(video_file_path, interval_sec, max_frames)
            st.session_state['frames'] = frames

# Display Extracted Screenshots
if 'frames' in st.session_state and st.session_state['frames']:
    frames = st.session_state['frames']
    st.success(f"✅ Kul {len(frames)} Screenshots Extract Ho Gaye!")
    
    # ZIP File Generator
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for idx, item in enumerate(frames):
            img_byte_arr = io.BytesIO()
            fmt = "JPEG" if image_format == "JPG" else "PNG"
            ext = "jpg" if image_format == "JPG" else "png"
            item['image'].save(img_byte_arr, format=fmt)
            filename = f"screenshot_{idx+1:03d}_{item['timestamp']}.{ext}"
            zip_file.writestr(filename, img_byte_arr.getvalue())
            
    st.download_button(
        label="📦 Download All Screenshots (ZIP File)",
        data=zip_buffer.getvalue(),
        file_name="video_screenshots.zip",
        mime="application/zip"
    )
    
    st.markdown("---")
    st.subheader("🖼️ Screenshots Preview")
    
    # Grid of screenshots
    cols_per_row = 4
    for i in range(0, len(frames), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            if i + j < len(frames):
                item = frames[i + j]
                with cols[j]:
                    st.image(item['image'], caption=f"Time: {item['timestamp']}", use_column_width=True)
                    img_byte_arr = io.BytesIO()
                    fmt = "JPEG" if image_format == "JPG" else "PNG"
                    ext = "jpg" if image_format == "JPG" else "png"
                    item['image'].save(img_byte_arr, format=fmt)
                    st.download_button(
                        label=f"⬇️ Download {item['timestamp']}",
                        data=img_byte_arr.getvalue(),
                        file_name=f"frame_{item['timestamp']}.{ext}",
                        mime=f"image/{ext}",
                        key=f"dl_{i+j}"
                    )
