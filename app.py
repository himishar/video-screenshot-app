import streamlit as st
import cv2
import tempfile
import os
import zipfile
import io
import re
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
st.markdown('<div class="sub-title">Fixed 1-Second Interval ya Auto Scene/Frame Change Detection se Screenshots lein!</div>', unsafe_allow_html=True)

# Settings Sidebar
st.sidebar.header("⚙️ Extraction Settings")

extraction_mode = st.sidebar.radio(
    "Select Extraction Mode",
    ["⏱️ Fixed Time Interval (e.g. Every 1 Sec)", "🎬 Auto Scene / Frame Change Detection"]
)

if "Fixed Time" in extraction_mode:
    interval_sec = st.sidebar.number_input("Screenshot Interval (Seconds)", min_value=0.1, max_value=60.0, value=1.0, step=0.5, help="Default is 1.0 second")
    sensitivity_threshold = 20.0
else:
    interval_sec = 0.5 # Minimum gap check for scene change
    sensitivity = st.sidebar.select_slider(
        "Scene Change Sensitivity",
        options=["Low (Major Cuts)", "Medium (Standard)", "High (Subtle Slide Changes)"],
        value="Medium (Standard)"
    )
    if "Low" in sensitivity:
        sensitivity_threshold = 35.0
    elif "High" in sensitivity:
        sensitivity_threshold = 12.0
    else:
        sensitivity_threshold = 20.0

max_frames = st.sidebar.number_input("Max Screenshots Limit", min_value=5, max_value=500, value=100, step=10, help="Standard memory limit for cloud")
image_format = st.sidebar.selectbox("Image Format", ["JPG", "PNG"])

def slugify(text):
    """
    Title ko clean format me convert karta hai:
    - Smallcase (lowercase)
    - Space ki jagah '-'
    - Special characters remove
    """
    if not text:
        return "video"
    text = text.lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    text = re.sub(r'\-+', '-', text).strip('-')
    return text if text else "video"

def format_timestamp(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    if mins > 0:
        return f"{mins:02d}m_{secs:02d}s"
    return f"{secs:02d}s_{millis:03d}ms" if millis > 0 else f"{secs:02d}s"

def extract_frames_fixed_interval(video_path, interval, max_limit):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        st.error("❌ Video open nahi ho pa rahi hai. Kripya file ya link dobara check karein.")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or not fps:
        fps = 30.0

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
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        
        extracted.append({
            "image": pil_img,
            "timestamp": time_label,
            "seconds": timestamp_sec
        })
        
        count += 1
        current_frame += frame_step
        
        progress_val = min(1.0, current_frame / total_frames) if total_frames > 0 else 0.5
        progress_bar.progress(progress_val)
        status_text.text(f"Extracting... Screenshot #{count} at {time_label}")
        
    cap.release()
    progress_bar.empty()
    status_text.empty()
    return extracted

def extract_frames_scene_change(video_path, threshold_percent, max_limit):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        st.error("❌ Video open nahi ho pa rahi hai.")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or not fps:
        fps = 30.0

    # Sample video every ~0.2 seconds for scene change detection
    sample_step = max(1, int(fps * 0.2))
    min_capture_gap = int(fps * 0.8) # Min 0.8s gap between detected scene changes
    
    extracted = []
    prev_gray_small = None
    last_captured_frame = -min_capture_gap
    current_frame = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    count = 0
    while cap.isOpened() and count < max_limit:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            break
            
        # Convert to small gray image for fast diff check
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_small = cv2.resize(gray, (160, 90))
        
        timestamp_sec = current_frame / fps
        time_label = format_timestamp(timestamp_sec)
        
        is_new_scene = False
        if prev_gray_small is None:
            is_new_scene = True # Always capture 1st frame
        else:
            # Absolute difference
            diff = cv2.absdiff(prev_gray_small, gray_small)
            diff_percent = (diff.mean() / 255.0) * 100.0
            
            if diff_percent >= threshold_percent and (current_frame - last_captured_frame) >= min_capture_gap:
                is_new_scene = True

        if is_new_scene:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            extracted.append({
                "image": pil_img,
                "timestamp": time_label,
                "seconds": timestamp_sec
            })
            count += 1
            last_captured_frame = current_frame
            prev_gray_small = gray_small

        current_frame += sample_step
        
        progress_val = min(1.0, current_frame / total_frames) if total_frames > 0 else 0.5
        progress_bar.progress(progress_val)
        status_text.text(f"Auto Detecting Scene Changes... Found {count} scenes (Time: {time_label})")
        
    cap.release()
    progress_bar.empty()
    status_text.empty()
    return extracted

# Tab layout
tab1, tab2 = st.tabs(["🔗 Online Video Link (YouTube / URL)", "📁 Upload Video File"])

video_file_path = None

with tab1:
    online_url = st.text_input("Online Video Link Paste Karein (YouTube, Direct MP4 URL, etc.)")
    if online_url:
        if st.button("🔗 Load Video Link"):
            with st.spinner("Video stream & title fetch ho raha hai... Please wait..."):
                try:
                    ydl_opts = {
                        'format': 'best[ext=mp4]/best',
                        'quiet': True,
                        'no_warnings': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(online_url, download=False)
                        video_url = info.get('url', None)
                        raw_title = info.get('title', 'online-video')
                        if video_url:
                            st.session_state['online_video_path'] = video_url
                            st.session_state['video_title'] = slugify(raw_title)
                            st.session_state['raw_title'] = raw_title
                            st.success(f"✅ Video Loaded: **{raw_title}**")
                        else:
                            st.error("❌ Is link se video extract nahi ho payi.")
                except Exception as e:
                    st.error(f"❌ Error loading video link: {str(e)}")

    if 'online_video_path' in st.session_state and not video_file_path:
        video_file_path = st.session_state['online_video_path']

with tab2:
    uploaded_file = st.file_uploader("Video File Select Karein", type=["mp4", "mov", "avi", "mkv", "webm"])
    if uploaded_file is not None:
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(temp_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        video_file_path = temp_file_path
        base_name = os.path.splitext(uploaded_file.name)[0]
        st.session_state['video_title'] = slugify(base_name)
        st.session_state['raw_title'] = base_name

# Processing Trigger
if video_file_path:
    st.markdown("---")
    video_title_slug = st.session_state.get('video_title', 'video')
    display_title = st.session_state.get('raw_title', 'video')
    st.subheader(f"⚡ Ready: {display_title}")
    st.info(f"📌 Mode: **{extraction_mode}** | 🏷️ File Slug: `{video_title_slug}`")
    
    if st.button("🚀 Extract Screenshots Now", key="process_btn"):
        with st.spinner("Processing video..."):
            if "Fixed Time" in extraction_mode:
                frames = extract_frames_fixed_interval(video_file_path, interval_sec, max_frames)
            else:
                frames = extract_frames_scene_change(video_file_path, sensitivity_threshold, max_frames)
            st.session_state['frames'] = frames

# Display Extracted Screenshots
if 'frames' in st.session_state and st.session_state['frames']:
    frames = st.session_state['frames']
    video_title_slug = st.session_state.get('video_title', 'video')
    
    st.success(f"✅ Kul {len(frames)} Screenshots Extract Ho Gaye!")
    
    # ZIP File Generator
    zip_buffer = io.BytesIO()
    fmt = "JPEG" if image_format == "JPG" else "PNG"
    ext = "jpg" if image_format == "JPG" else "png"
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for idx, item in enumerate(frames):
            img_byte_arr = io.BytesIO()
            item['image'].save(img_byte_arr, format=fmt)
            filename = f"{video_title_slug}_{item['timestamp']}.{ext}"
            zip_file.writestr(filename, img_byte_arr.getvalue())
            
    st.download_button(
        label=f"📦 Download All Screenshots (ZIP: {video_title_slug}_screenshots.zip)",
        data=zip_buffer.getvalue(),
        file_name=f"{video_title_slug}_screenshots.zip",
        mime="application/zip"
    )
    
    st.markdown("---")
    st.subheader("🖼️ Screenshots Preview")
    
    cols_per_row = 4
    for i in range(0, len(frames), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            if i + j < len(frames):
                item = frames[i + j]
                with cols[j]:
                    st.image(item['image'], caption=f"Time: {item['timestamp']}", use_container_width=True)
                    img_byte_arr = io.BytesIO()
                    item['image'].save(img_byte_arr, format=fmt)
                    single_filename = f"{video_title_slug}_{item['timestamp']}.{ext}"
                    st.download_button(
                        label=f"⬇️ {item['timestamp']}",
                        data=img_byte_arr.getvalue(),
                        file_name=single_filename,
                        mime=f"image/{ext}",
                        key=f"dl_{i+j}"
                    )
