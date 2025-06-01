import streamlit as st
import torch
import time
import os
from pydub import AudioSegment

torch.classes.__path__ = []

from download import download_podcast_audio, download_youtube_audio
from transcribe import transcribe_audio

st.title("xiaoyuzhou FM / YouTube 音频下载与转录工具")

# 初始化会话状态
if "download_completed" not in st.session_state:
    st.session_state.download_completed = False
if "audio_path" not in st.session_state:
    st.session_state.audio_path = None
if "media_title" not in st.session_state:
    st.session_state.media_title = None
if "transcript" not in st.session_state:
    st.session_state.transcript = None
if "source_type" not in st.session_state:
    st.session_state.source_type = "小宇宙播客"
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None


def format_duration(seconds: float) -> str:
    """将秒数转换为可读的时分秒格式"""
    seconds = round(seconds)  # 四舍五入到整数秒
    
    hours = seconds // 3600
    remaining = seconds % 3600
    minutes = remaining // 60
    seconds = remaining % 60
    
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours}小时")
    if minutes > 0 or hours > 0:  # 如果有小时也显示分钟
        time_parts.append(f"{minutes}分")
    time_parts.append(f"{seconds}秒")
    
    return "".join(time_parts)

# 下载部分
download_expander = st.expander(
    "第一步：下载音频", expanded=not st.session_state.download_completed
)
with download_expander:
    st.session_state.source_type = st.radio(
        "选择内容来源：",
        ("小宇宙播客", "YouTube 视频"),
        key="source_radio"
    )

    url_label = f"请输入{st.session_state.source_type}链接："
    url = st.text_input(url_label)

    # 添加 Cookies 文件路径输入 (仅 YouTube)
    cookies_path = None
    if st.session_state.source_type == "YouTube 视频":
        cookies_path = st.text_input(
            "YouTube Cookies 文件路径 (可选):", 
            help="如果 YouTube 下载失败或需要登录，请在此处提供从浏览器导出的 cookies.txt 文件路径。"
        )

    if st.button("开始下载"):
        if url:
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                def update_progress(progress):
                    # 根据 progress 的值更新状态
                    # 0.0: 开始下载
                    # 1.0: 下载完成
                    # -1.0: 下载出错
                    # 其他值: 播客下载时的百分比
                    if progress == 0.0:
                        progress_bar.progress(0)
                        status_text.text(f"正在开始下载 {st.session_state.source_type} 音频...")
                    elif progress == 1.0:
                        progress_bar.progress(100)
                        status_text.text("下载完成！")
                    elif progress == -1.0:
                        status_text.text("下载出错，请查看控制台日志。")
                        # 可以考虑显示一个错误状态，或者清除进度条
                        progress_bar.progress(0) # 或 progress_bar.empty()
                    elif 0 < progress < 1:
                        progress_percentage = int(progress * 100)
                        progress_bar.progress(progress_percentage)
                        status_text.text(f"下载进度：{progress_percentage}%")
                    # 对于 yt-dlp，我们可能只收到 0.0 和 1.0 (或 -1.0)

                # 初始化状态
                status_text.text(f"准备下载 {st.session_state.source_type} 音频...")
                progress_bar.progress(0)

                audio_path = None
                media_title = None

                if st.session_state.source_type == "小宇宙播客":
                    audio_path, media_title = download_podcast_audio(url, update_progress)
                elif st.session_state.source_type == "YouTube 视频":
                    audio_path, media_title = download_youtube_audio(url, update_progress, cookies_path=cookies_path)

                if audio_path and media_title:
                    st.session_state.audio_path = audio_path
                    st.session_state.media_title = media_title
                    st.session_state.download_completed = True
                    status_text.text("下载完成！")
                    st.success(f"成功下载音频：{st.session_state.media_title}")
                else:
                    st.error(f"下载失败，请检查链接或查看控制台输出。")
                    st.session_state.download_completed = False
                    st.session_state.audio_path = None
                    st.session_state.media_title = None

            except Exception as e:
                st.error(f"下载过程中发生错误：{str(e)}")
                st.session_state.download_completed = False
                st.session_state.audio_path = None
                st.session_state.media_title = None
        else:
            st.warning(f"请输入有效的{st.session_state.source_type}链接")

# 常驻显示下载后的音频播放器
if st.session_state.download_completed:
    st.text(st.session_state.media_title)
    # 获取音频时长
    try:
        audio = AudioSegment.from_file(st.session_state.audio_path)
        duration = audio.duration_seconds
        readable_duration = format_duration(duration)
        st.text(f"音频长度：{readable_duration}")
        st.text(f"音频大小：{os.path.getsize(st.session_state.audio_path) / 1024 / 1024:.2f} MB")
        st.audio(st.session_state.audio_path)
    except Exception as e:
        st.error(f"加载音频信息时出错: {e}")
        st.session_state.download_completed = False 

# 转录部分
transcribe_expander = st.expander(
    "第二步：转录音频", expanded=st.session_state.download_completed
)
with transcribe_expander:
    if st.session_state.download_completed:
        st.info("提示: 一分钟的音频大约需要10秒钟转录时间(不同设备转录时间不同)")

        # 设备选择
        device_options = ["CPU"]
        try:
            if torch.cuda.is_available():
                device_options.append("GPU (CUDA)")
        except Exception as e:
            st.warning(f"检测可用设备时出错: {e}")
            
        selected_device_display = st.selectbox("选择运行设备：", device_options)

        # 转换设备选择为程序可用的格式
        device_map = {"CPU": "cpu", "GPU (CUDA)": "cuda", "GPU (MPS)": "mps"}
        selected_device = device_map.get(selected_device_display, "cpu")

        # 格式选择
        output_format = st.selectbox("选择输出格式：", ["txt", "srt"])

        if st.button("开始转录", disabled=st.session_state.get('is_transcribing', False)):
            try:
                status_text_transcribe = st.empty()
                st.session_state.is_transcribing = True
                status_text_transcribe.text("转录中...")

                # 设置输出文件名
                output_file = f"{st.session_state.media_title}.{output_format}"

                # 记录开始时间
                start_time = time.time()

                try:
                    audio = AudioSegment.from_file(st.session_state.audio_path)
                    duration = audio.duration_seconds
                    audio_length_minutes = duration / 60
                    estimated_time_factor = 10 if selected_device == "cpu" else 3
                    estimated_time = audio_length_minutes * estimated_time_factor
                    st.info(f"预计转录时间：约 {estimated_time/60:.1f} 分钟")
                except Exception as e:
                     st.warning(f"无法计算预计时间: {e}")

                # 开始转录 - 修改这里获取返回的PDF路径
                txt_path, pdf_path = transcribe_audio(
                    st.session_state.audio_path,
                    output_file,
                    output_format,
                    selected_device,
                )

                # 保存PDF路径到会话状态
                st.session_state.pdf_path = pdf_path

                # 计算耗时
                elapsed_time = time.time() - start_time
                status_text_transcribe.text("转录完成！")

                # 读取并显示转录结果
                with open(txt_path, "r", encoding="utf-8") as f:
                    st.session_state.transcript = f.read()

                st.success(f"转录完成！耗时：{elapsed_time:.2f}秒")
                
                # 创建下载按钮容器
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        label="📄 下载转录文件 (TXT)",
                        data=st.session_state.transcript,
                        file_name=os.path.basename(txt_path),
                        mime="text/plain",
                    )
                
                with col2:
                    # PDF下载按钮
                    if pdf_path and os.path.exists(pdf_path):
                        with open(pdf_path, "rb") as pdf_file:
                            pdf_data = pdf_file.read()
                        st.download_button(
                            label="📑 下载转录文件 (PDF)",
                            data=pdf_data,
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf",
                        )
                    else:
                        st.info("PDF 文件生成失败或不可用")

                st.session_state.is_transcribing = False

            except Exception as e:
                st.error(f"转录失败：{str(e)}")
                st.session_state.is_transcribing = False
    else:
        st.info("请先成功完成音频下载")

# 转录结果显示
if st.session_state.transcript:
    st.subheader("转录文稿")
    st.text_area("转录预览", st.session_state.transcript, height=300)
