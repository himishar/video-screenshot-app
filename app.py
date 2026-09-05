import streamlit as st
import cv2
import tempfile
import os
import zipfile
import io
import re
import glob
import urllib.request
import json
from PIL import Image
import yt_dlp

# Page Config
st.set_page_config(
    page_title="Video Toolkit - Screenshots & Voice AI Script Extractor",
    page_icon="🎬",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>
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
    lines = vtt_text.splitlines()
    entries = []
    time_pattern = re.compile(r'(\d{2}:)?\d{2}:\d{2}[\.,]\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}[\.,]\d{3}')
    current_time = None
    current_text = []
    seen_lines = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or line.startswith('Kind:') or line.startswith('Language:') or line.isdigit():
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

def parse_json3_captions(json_data):
    events = json_data.get('events', [])
    entries = []
    seen = set()
    for ev in events:
        start_ms = ev.get('tStartMs', 0)
        d_ms = ev.get('dDurationMs', 0)
        segs = ev.get('segs', [])
        if not segs:
            continue
        text = "".join([s.get('utf8', '') for s in segs]).strip()
        text = re.sub(r'\n+', ' ', text)
        if not text or text in seen:
            continue
        start_sec = start_ms / 1000.0
        end_sec = (start_ms + d_ms) / 1000.0
        time_str = f"[{format_timestamp(start_sec)} - {format_timestamp(end_sec)}]"
        entries.append((time_str, text))
        seen.add(text)
    return entries

def get_video_caption_info(video_url):
    ydl_opts = {
        'skip_download': True,
        'writeautosub': True,
        'writesubtitles': True,
        'subtitleslangs': ['all'],
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        raw_title = info.get('title', 'video')
        subtitles = info.get('subtitles', {})
        auto_captions = info.get('automatic_captions', {})
        
        all_langs = {}
        if subtitles:
            for lang, formats in subtitles.items():
                all_langs[lang] = {'type': 'Manual Subtitle', 'formats': formats}
        if auto_captions:
            for lang, formats in auto_captions.items():
                if lang not in all_langs:
                    all_langs[lang] = {'type': 'Auto-Generated', 'formats': formats}
                    
        return raw_title, all_langs

def extract_captions_for_lang(all_langs, selected_lang):
    if selected_lang not in all_langs:
        return []
    formats_list = all_langs[selected_lang]['formats']
    vtt_url = None
    json_url = None
    for fmt in formats_list:
        if fmt.get('ext') == 'vtt':
            vtt_url = fmt.get('url')
            break
        elif fmt.get('ext') == 'json3':
            json_url = fmt.get('url')

    entries = []
    try:
        if vtt_url:
            req = urllib.request.Request(vtt_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                vtt_content = resp.read().decode('utf-8', errors='ignore')
                entries = parse_vtt_subtitles(vtt_content)
        elif json_url:
            req = urllib.request.Request(json_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                json_data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                entries = parse_json3_captions(json_data)
    except Exception as e:
        st.error(f"Error fetching caption content: {str(e)}")
    return entries

# AI Speech-to-Text Transcriber Model Loader
@st.cache_resource
def get_whisper_model():
    try:
        from faster_whisper import WhisperModel
        # Load lightweight CPU model
        return WhisperModel("tiny", device="cpu", compute_type="int8")
    except Exception as e:
        return None

def process_reel_audio_and_transcribe(video_input_source, is_url=True):
    temp_dir = tempfile.mkdtemp()
    target_media_path = None
    raw_title = "instagram_reel"

    if is_url:
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(temp_dir, 'reel_media.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_input_source, download=True)
            raw_title = info.get('title', 'instagram_reel')
        
        media_files = glob.glob(os.path.join(temp_dir, "reel_media.*"))
        if media_files:
            target_media_path = media_files[0]
    else:
        # Uploaded file
        target_media_path = os.path.join(temp_dir, video_input_source.name)
        with open(target_media_path, "wb") as f:
            f.write(video_input_source.getbuffer())
        raw_title = os.path.splitext(video_input_source.name)[0]

    if not target_media_path or not os.path.exists(target_media_path):
        return raw_title, None, "Unknown", []

    # Read audio bytes for player/download
    with open(target_media_path, "rb") as f:
        audio_bytes = f.read()

    # Transcribe via Whisper AI
    model = get_whisper_model()
    if model is None:
        return raw_title, audio_bytes, "Error", [("[00:00 - 00:00]", "Whisper AI model loading failed. Please install faster-whisper.")]

    segments, info = model.transcribe(target_media_path, beam_size=5)
    detected_lang = info.language.upper() if info and info.language else "AUTO"
    
    entries = []
    for segment in segments:
        start_str = format_timestamp(segment.start)
        end_str = format_timestamp(segment.end)
        time_str = f"[{start_str} - {end_str}]"
        text = segment.text.strip()
        if text:
            entries.append((time_str, text))

    return raw_title, audio_bytes, detected_lang, entries

# TOP NAVIGATION BAR
st.markdown('<div class="main-title">🎬 Video Toolkit Hub</div>', unsafe_allow_html=True)

nav_choice = st.radio(
    "Navigation Menu",
    [
        "📸 Video Screenshot Extractor", 
        "📜 YouTube Subtitles Extractor", 
        "🎙️ Instagram Reel & Voice AI Script Extractor"
    ],
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
# APP 2: YOUTUBE SUBTITLES EXTRACTOR
# ==============================================================================
elif nav_choice == "📜 YouTube Subtitles Extractor":
    st.subheader("📜 YouTube Subtitles & Script Extractor")
    st.markdown("YouTube Video URL daalein — Manual & Auto-Generated Subtitles me se Timestamped Script nikaley!")

    script_url = st.text_input("YouTube Video Link Paste Karein", key="yt_sub_input")
    
    if script_url:
        if st.button("🔎 Search Video Subtitles", key="search_yt_sub_btn"):
            with st.spinner("Subtitles search ho rahe hain..."):
                try:
                    title, all_langs = get_video_caption_info(script_url)
                    st.session_state['yt_caption_res'] = {
                        'title': title,
                        'slug': slugify(title),
                        'langs': all_langs
                    }
                except Exception as e:
                    st.error(f"❌ Error fetching captions: {str(e)}")

    if 'yt_caption_res' in st.session_state:
        res = st.session_state['yt_caption_res']
        title = res['title']
        slug = res['slug']
        all_langs = res['langs']

        st.markdown("---")
        st.subheader(f"🎬 Video: {title}")

        if not all_langs:
            st.warning("⚠️ Is video me koi subtitles nahi mile.")
        else:
            lang_options = list(all_langs.keys())
            default_index = 0
            for idx, l in enumerate(lang_options):
                if l in ['hi', 'hi-orig', 'en', 'en-orig']:
                    default_index = idx
                    break
                    
            selected_lang = st.selectbox(
                "🌐 Select Subtitle Language:",
                options=lang_options,
                index=default_index,
                format_func=lambda l: f"{l.upper()} ({all_langs[l]['type']})"
            )
            
            if st.button("⚡ Extract Script for Selected Language"):
                with st.spinner("Extracting transcript lines..."):
                    entries = extract_captions_for_lang(all_langs, selected_lang)
                    st.session_state['yt_entries'] = entries
                    st.session_state['yt_cur_lang'] = selected_lang

        if 'yt_entries' in st.session_state and st.session_state['yt_entries']:
            entries = st.session_state['yt_entries']
            cur_lang = st.session_state.get('yt_cur_lang', 'lang')
            
            st.success(f"✅ Total {len(entries)} Timestamped Script Lines Extracted!")
            formatted_text_lines = [f"{time_str} {text}" for time_str, text in entries]
            full_transcript_str = "\n".join(formatted_text_lines)
            plain_text = "\n".join([text for _, text in entries])
            
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label=f"📄 Download Script (.TXT with Timestamps)",
                    data=full_transcript_str,
                    file_name=f"{slug}_script_{cur_lang}.txt",
                    mime="text/plain"
                )
            with col2:
                st.download_button(
                    label=f"📝 Download Plain Text (Without Timestamps)",
                    data=plain_text,
                    file_name=f"{slug}_transcript_plain_{cur_lang}.txt",
                    mime="text/plain"
                )

            st.markdown("---")
            st.subheader("📜 Timestamped Script Preview")
            script_html = "<br>".join([f"<b>{t}</b> {x}" for t, x in entries])
            st.markdown(f'<div class="transcript-box">{script_html}</div>', unsafe_allow_html=True)
            st.text_area("📋 Copy Full Script Below:", value=full_transcript_str, height=250)

# ==============================================================================
# APP 3: INSTAGRAM REEL & VOICE AI SCRIPT EXTRACTOR (AUDIO EXTRACT + WHISPER AI)
# ==============================================================================
else:
    st.subheader("🎙️ Instagram Reel & Voice AI Script Extractor")
    st.markdown("Instagram Reels, Shorts, ya audio/video files ki **Voice Extract Karein (MP3)** aur **AI se Timestamped Script Transcribe** karein!")

    tab_reel1, tab_reel2 = st.tabs(["🔗 Instagram Reel / Video Link", "📁 Upload Video / Audio File"])

    reel_input_source = None
    is_url_mode = True

    with tab_reel1:
        reel_url = st.text_input("Instagram Reel Link / Video URL Paste Karein", key="reel_url_input")
        if reel_url:
            reel_input_source = reel_url
            is_url_mode = True

    with tab_reel2:
        uploaded_reel_file = st.file_uploader("Reel Video ya Audio File Upload Karein", type=["mp4", "mov", "mp3", "m4a", "wav"], key="reel_file_input")
        if uploaded_reel_file:
            reel_input_source = uploaded_reel_file
            is_url_mode = False

    if reel_input_source:
        st.markdown("---")
        if st.button("🚀 Extract Voice Audio & Generate AI Script", key="process_reel_btn"):
            with st.spinner("1️⃣ Audio extract ho raha hai & 2️⃣ AI Voice-to-Text Script generate ho rahi hai..."):
                try:
                    title, audio_data, lang, entries = process_reel_audio_and_transcribe(reel_input_source, is_url=is_url_mode)
                    st.session_state['reel_res'] = {
                        'title': title,
                        'slug': slugify(title),
                        'audio_data': audio_data,
                        'lang': lang,
                        'entries': entries
                    }
                except Exception as e:
                    st.error(f"❌ Error processing reel audio: {str(e)}")

    if 'reel_res' in st.session_state:
        r_data = st.session_state['reel_res']
        title = r_data['title']
        slug = r_data['slug']
        audio_bytes = r_data['audio_data']
        lang = r_data['lang']
        entries = r_data['entries']

        st.markdown("---")
        st.subheader(f"🎬 Media: {title}")
        st.info(f"🌐 AI Detected Audio Language: **{lang}** | 🏷️ File Slug: `{slug}`")

        # 1. EXTRACTED VOICE AUDIO PLAYER & DOWNLOAD
        if audio_bytes:
            st.subheader("🎵 Extracted Voice Audio (MP3)")
            st.audio(audio_bytes, format="audio/mp3")
            st.download_button(
                label=f"⬇️ Download Extracted Voice Audio (.MP3)",
                data=audio_bytes,
                file_name=f"{slug}_voice_audio.mp3",
                mime="audio/mp3"
            )

        # 2. AI TIMESTAMPED SCRIPT EXTRACTOR
        st.markdown("---")
        st.subheader("📜 AI Generated Timestamped Script")
        
        if not entries:
            st.warning("⚠️ Voice audio me koi clear speech detect nahi hui.")
        else:
            st.success(f"✅ AI Total {len(entries)} Voice Lines Transcribe Ki!")
            formatted_text_lines = [f"{time_str} {text}" for time_str, text in entries]
            full_transcript_str = "\n".join(formatted_text_lines)
            plain_text = "\n".join([text for _, text in entries])

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label=f"📄 Download AI Script (.TXT with Timestamps)",
                    data=full_transcript_str,
                    file_name=f"{slug}_ai_script_{lang.lower()}.txt",
                    mime="text/plain"
                )
            with col2:
                st.download_button(
                    label=f"📝 Download Plain Text (Without Timestamps)",
                    data=plain_text,
                    file_name=f"{slug}_ai_transcript_plain_{lang.lower()}.txt",
                    mime="text/plain"
                )

            st.markdown("---")
            st.subheader("📜 Timestamped AI Script Preview")
            script_html = "<br>".join([f"<b>{t}</b> {x}" for t, x in entries])
            st.markdown(f'<div class="transcript-box">{script_html}</div>', unsafe_allow_html=True)
            st.text_area("📋 Copy Full AI Script Below:", value=full_transcript_str, height=250)
