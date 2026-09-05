import streamlit as st
import cv2
import tempfile
import os
import zipfile
import io
import re
import glob
from PIL import Image
import yt_dlp

# Page Config
st.set_page_config(
    page_title="Video Toolkit - Screenshots & Script Extractor",
    page_icon="🎬",
    layout="wide"
)

# Custom CSS styling for top navbar and theme
st.markdown("""
<style>
    .top-nav {
        background-color: #1E1E2E;
        padding: 10px;
        border-radius: 10px;
        margin-bottom: 20px;
        text-align: center;
    }
    .main-title {
        font-size: 2.3rem;
        font-weight: 700;
        color: #FF4B4B;
        text-align: center;
        margin-bottom: 0.3rem;
    }
    .sub-title {
        font-size: 1.05rem;
        text-align: center;
        color: #555555;
        margin-bottom: 1.5rem;
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
    .transcript-box {
        background-color: #F8F9FA;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #E9ECEF;
        max-height: 450px;
        overflow-y: auto;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# Helper Functions
def slugify(text):
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

def parse_vtt_subtitles(vtt_text):
    """
    VTT file contents ko clean timestamped script me parse karta hai
    """
    lines = vtt_text.splitlines()
    entries = []
    time_pattern = re.compile(r'(\d{2}:)?\d{2}:\d{2}[\.,]\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}[\.,]\d{3}')
    
    current_time = None
    current_text = []
    seen_lines = set()
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or line.isdigit():
            continue
            
        match = time_pattern.search(line)
        if match:
            if current_time and current_text:
                full_line = " ".join(current_text).strip()
                full_line = re.sub(r'<[^>]+>', '', full_line)
                if full_line and full_line not in seen_lines:
                    entries.append((current_time, full_line))
                    seen_lines.add(full_line)
                current_text = []
            
            parts = line.split('-->')
            start_t = parts[0].strip().split('.')[0]
            end_t = parts[1].strip().split('.')[0]
            current_time = f"[{start_t} - {end_t}]"
        else:
            clean_line = re.sub(r'<[^>]+>', '', line).strip()
            if clean_line and clean_line not in current_text:
                current_text.append(clean_line)
                
    if current_time and current_text:
        full_line = " ".join(current_text).strip()
        full_line = re.sub(r'<[^>]+>', '', full_line)
        if full_line and full_line not in seen_lines:
            entries.append((current_time, full_line))
            
    return entries

def fetch_video_transcript(video_url):
    temp_dir = tempfile.mkdtemp()
    ydl_opts = {
        'skip_download': True,
        'writeautosub': True,
        'writesubtitles': True,
        'subtitlesformat': 'vtt',
        'outtmpl': os.path.join(temp_dir, 'sub'),
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        raw_title = info.get('title', 'video')
        detected_lang = info.get('language', None)
        
        # Check downloaded vtt files
        vtt_files = glob.glob(os.path.join(temp_dir, "*.vtt"))
        if not vtt_files:
            return raw_title, detected_lang or "Unknown", []
            
        # Try to infer language from filename e.g. sub.hi.vtt
        first_vtt = vtt_files[0]
        filename_parts = os.path.basename(first_vtt).split('.')
        if len(filename_parts) > 2:
            detected_lang = filename_parts[1]
            
        with open(first_vtt, 'r', encoding='utf-8', errors='ignore') as f:
            vtt_content = f.read()
            
        entries = parse_vtt_subtitles(vtt_content)
        return raw_title, detected_lang or "Auto-Detected", entries

# TOP NAVIGATION BAR (App Selector)
st.markdown('<div class="main-title">🎬 Video Toolkit Hub</div>', unsafe_allow_html=True)

nav_choice = st.radio(
    "Navigation Menu",
    ["📸 Video Screenshot Extractor", "📜 Video Script / Subtitles Extractor"],
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("---")

# ==============================================================================
# APP 1: VIDEO SCREENSHOT EXTRACTOR
# ==============================================================================
if nav_choice == "📸 Video Screenshot Extractor":
    st.subheader("📸 Video Screenshot Extractor")
    st.markdown("Fixed Time Interval (e.g. 1 sec) ya Auto Scene Change Detection se Screenshots lein.")

    # Sidebar settings
    st.sidebar.header("⚙️ Screenshot Settings")
    extraction_mode = st.sidebar.radio(
        "Select Mode",
        ["⏱️ Fixed Time Interval (e.g. Every 1 Sec)", "🎬 Auto Scene / Frame Change Detection"]
    )

    if "Fixed Time" in extraction_mode:
        interval_sec = st.sidebar.number_input("Interval (Seconds)", min_value=0.1, max_value=60.0, value=1.0, step=0.5)
        sensitivity_threshold = 20.0
    else:
        interval_sec = 0.5
        sensitivity = st.sidebar.select_slider(
            "Scene Sensitivity",
            options=["Low (Major Cuts)", "Medium (Standard)", "High (Subtle Slide Changes)"],
            value="Medium (Standard)"
        )
        if "Low" in sensitivity:
            sensitivity_threshold = 35.0
        elif "High" in sensitivity:
            sensitivity_threshold = 12.0
        else:
            sensitivity_threshold = 20.0

    max_frames = st.sidebar.number_input("Max Screenshots Limit", min_value=5, max_value=500, value=100, step=10)
    image_format = st.sidebar.selectbox("Image Format", ["JPG", "PNG"])

    def extract_frames_fixed_interval(video_path, interval, max_limit):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            st.error("❌ Video open nahi ho pa rahi hai.")
            return []
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
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
            extracted.append({
                "image": Image.fromarray(frame_rgb),
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
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_step = max(1, int(fps * 0.2))
        min_capture_gap = int(fps * 0.8)
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
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_small = cv2.resize(gray, (160, 90))
            timestamp_sec = current_frame / fps
            time_label = format_timestamp(timestamp_sec)
            is_new_scene = False
            if prev_gray_small is None:
                is_new_scene = True
            else:
                diff = cv2.absdiff(prev_gray_small, gray_small)
                diff_percent = (diff.mean() / 255.0) * 100.0
                if diff_percent >= threshold_percent and (current_frame - last_captured_frame) >= min_capture_gap:
                    is_new_scene = True
            if is_new_scene:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                extracted.append({
                    "image": Image.fromarray(frame_rgb),
                    "timestamp": time_label,
                    "seconds": timestamp_sec
                })
                count += 1
                last_captured_frame = current_frame
                prev_gray_small = gray_small
            current_frame += sample_step
            progress_val = min(1.0, current_frame / total_frames) if total_frames > 0 else 0.5
            progress_bar.progress(progress_val)
            status_text.text(f"Auto Detecting... Found {count} scenes at {time_label}")
        cap.release()
        progress_bar.empty()
        status_text.empty()
        return extracted

    tab1, tab2 = st.tabs(["🔗 Online Video Link (YouTube / URL)", "📁 Upload Video File"])
    video_file_path = None

    with tab1:
        online_url = st.text_input("Online Video Link Paste Karein")
        if online_url:
            if st.button("🔗 Load Video Link"):
                with st.spinner("Loading video stream..."):
                    try:
                        ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True, 'no_warnings': True}
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(online_url, download=False)
                            video_url = info.get('url', None)
                            raw_title = info.get('title', 'online-video')
                            if video_url:
                                st.session_state['online_video_path'] = video_url
                                st.session_state['video_title'] = slugify(raw_title)
                                st.session_state['raw_title'] = raw_title
                                st.success(f"✅ Loaded: **{raw_title}**")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

        if 'online_video_path' in st.session_state and not video_file_path:
            video_file_path = st.session_state['online_video_path']

    with tab2:
        uploaded_file = st.file_uploader("Video File Upload", type=["mp4", "mov", "avi", "mkv", "webm"])
        if uploaded_file is not None:
            temp_dir = tempfile.mkdtemp()
            temp_file_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            video_file_path = temp_file_path
            base_name = os.path.splitext(uploaded_file.name)[0]
            st.session_state['video_title'] = slugify(base_name)
            st.session_state['raw_title'] = base_name

    if video_file_path:
        st.markdown("---")
        video_title_slug = st.session_state.get('video_title', 'video')
        display_title = st.session_state.get('raw_title', 'video')
        st.subheader(f"⚡ Ready: {display_title}")
        
        if st.button("🚀 Extract Screenshots Now", key="process_btn"):
            with st.spinner("Extracting screenshots..."):
                if "Fixed Time" in extraction_mode:
                    frames = extract_frames_fixed_interval(video_file_path, interval_sec, max_frames)
                else:
                    frames = extract_frames_scene_change(video_file_path, sensitivity_threshold, max_frames)
                st.session_state['frames'] = frames

    if 'frames' in st.session_state and st.session_state['frames']:
        frames = st.session_state['frames']
        video_title_slug = st.session_state.get('video_title', 'video')
        st.success(f"✅ Total {len(frames)} Screenshots Extracted!")
        
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
                        st.download_button(
                            label=f"⬇️ {item['timestamp']}",
                            data=img_byte_arr.getvalue(),
                            file_name=f"{video_title_slug}_{item['timestamp']}.{ext}",
                            mime=f"image/{ext}",
                            key=f"dl_{i+j}"
                        )

# ==============================================================================
# APP 2: VIDEO SCRIPT / TRANSCRIPT EXTRACTOR (WITH TIMESTAMPS & AUTO LANG)
# ==============================================================================
else:
    st.subheader("📜 Video Script & Subtitles Extractor")
    st.markdown("Video ka URL paste karein — Auto Language Detect karke Timestamped Script nikaley!")

    script_url = st.text_input("Online Video Link (YouTube, Vimeo, etc.) Paste Karein", key="script_url_input")
    
    if script_url:
        if st.button("🚀 Extract Video Script & Subtitles", key="extract_script_btn"):
            with st.spinner("Subtitles & Script extract ho rahe hain... Please wait..."):
                try:
                    title, lang, entries = fetch_video_transcript(script_url)
                    st.session_state['script_data'] = {
                        'title': title,
                        'slug': slugify(title),
                        'lang': lang,
                        'entries': entries
                    }
                except Exception as e:
                    st.error(f"❌ Subtitles extract karne me error: {str(e)}")

    if 'script_data' in st.session_state:
        data = st.session_state['script_data']
        title = data['title']
        slug = data['slug']
        lang = data['lang']
        entries = data['entries']

        st.markdown("---")
        st.subheader(f"🎬 Video: {title}")
        st.info(f"🌐 Auto Detected Language: **{lang.upper()}** | 🏷️ File Slug: `{slug}`")

        if not entries:
            st.warning("⚠️ Is video me koi subtitles/captions nahi mile. (Ensure video has captions on YouTube).")
        else:
            st.success(f"✅ Kul {len(entries)} Transcript Lines Extract Ho Gayi!")
            
            # Format text output with timestamps
            formatted_text_lines = [f"{time_str} {text}" for time_str, text in entries]
            full_transcript_str = "\n".join(formatted_text_lines)
            
            # Action Buttons: Download TXT
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label=f"📄 Download Script (.TXT with Timestamps)",
                    data=full_transcript_str,
                    file_name=f"{slug}_script_{lang}.txt",
                    mime="text/plain"
                )
            with col2:
                plain_text = "\n".join([text for _, text in entries])
                st.download_button(
                    label=f"📝 Download Plain Text (Without Timestamps)",
                    data=plain_text,
                    file_name=f"{slug}_transcript_plain_{lang}.txt",
                    mime="text/plain"
                )

            st.markdown("---")
            st.subheader("📜 Timestamped Script Preview")
            
            # Display inside scrollable box
            script_html = "<br>".join([f"<b>{t}</b> {x}" for t, x in entries])
            st.markdown(f'<div class="transcript-box">{script_html}</div>', unsafe_allow_html=True)
            
            st.text_area("📋 Copy Full Script Below:", value=full_transcript_str, height=250)
