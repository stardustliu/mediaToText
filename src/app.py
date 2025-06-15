import streamlit as st
import torch
import time
import os
from pydub import AudioSegment
import psutil

torch.classes.__path__ = []

from download import download_podcast_audio, download_youtube_audio
from transcribe import transcribe_audio
from summarize import PodcastSummarizer

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
if "transcribe_completed" not in st.session_state:
    st.session_state.transcribe_completed = False
if "txt_path" not in st.session_state:
    st.session_state.txt_path = None
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None
if "output_format" not in st.session_state:
    st.session_state.output_format = "txt"
# 新增：总结功能相关状态
if "summarize_completed" not in st.session_state:
    st.session_state.summarize_completed = False
if "summary_data" not in st.session_state:
    st.session_state.summary_data = None
if "deep_analysis_result" not in st.session_state:
    st.session_state.deep_analysis_result = None
if "summarizer" not in st.session_state:
    st.session_state.summarizer = None
if "summary_mode" not in st.session_state:
    st.session_state.summary_mode = "structured"  # 新增：总结模式选择

# 初始化总结器
@st.cache_resource
def get_summarizer():
    """获取缓存的总结器实例"""
    return PodcastSummarizer()

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
    "第一步：获取音频", expanded=not st.session_state.download_completed
)
with download_expander:
    st.session_state.source_type = st.radio(
        "选择内容来源：",
        ("小宇宙播客", "YouTube 视频", "本地文件上传"),
        key="source_radio"
    )

    if st.session_state.source_type == "本地文件上传":
        st.info("📁 支持的文件格式：MP3, MP4, WAV, M4A, FLAC, OGG, AAC, MKV, AVI, MOV, WMV 等")
        
        uploaded_file = st.file_uploader(
            "选择音频或视频文件",
            type=['mp3', 'mp4', 'wav', 'm4a', 'flac', 'ogg', 'aac', 'mkv', 'avi', 'mov', 'wmv', 'webm'],
            help="支持常见的音频和视频格式，视频文件将自动提取音频进行转录"
        )
        
        if uploaded_file is not None:
            # 显示文件信息
            file_details = {
                "文件名": uploaded_file.name,
                "文件大小": f"{uploaded_file.size / 1024 / 1024:.2f} MB",
                "文件类型": uploaded_file.type
            }
            st.write("📄 **文件信息**：")
            for key, value in file_details.items():
                st.write(f"• {key}: {value}")
            
            if st.button("处理本地文件"):
                try:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text("正在保存文件...")
                    progress_bar.progress(20)
                    
                    # 创建临时目录（如果不存在）
                    temp_dir = "temp_uploads"
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    # 保存上传的文件
                    file_extension = os.path.splitext(uploaded_file.name)[1]
                    temp_file_path = os.path.join(temp_dir, f"uploaded_file{file_extension}")
                    
                    with open(temp_file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    progress_bar.progress(50)
                    status_text.text("正在处理文件...")
                    
                    # 检查是否是视频文件，如果是则转换为音频
                    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm']
                    audio_path = temp_file_path
                    
                    if file_extension.lower() in video_extensions:
                        status_text.text("检测到视频文件，正在提取音频...")
                        progress_bar.progress(70)
                        
                        # 使用 pydub 从视频中提取音频
                        try:
                            video = AudioSegment.from_file(temp_file_path)
                            audio_path = os.path.join(temp_dir, f"extracted_audio.wav")
                            video.export(audio_path, format="wav")
                            st.info("✅ 已从视频文件中提取音频")
                        except Exception as e:
                            st.error(f"提取音频失败：{e}")
                            st.info("💡 提示：如果遇到视频格式问题，建议先将视频转换为常见格式（如MP4）或直接上传音频文件")
                            raise e
                    
                    progress_bar.progress(90)
                    status_text.text("验证音频文件...")
                    
                    # 验证音频文件是否可以正常读取
                    try:
                        audio_test = AudioSegment.from_file(audio_path)
                        duration = audio_test.duration_seconds
                        
                        # 检查文件大小限制（建议不超过100MB或1小时）
                        file_size_mb = os.path.getsize(audio_path) / 1024 / 1024
                        if file_size_mb > 100:
                            st.warning(f"⚠️ 文件较大（{file_size_mb:.1f}MB），转录可能需要较长时间")
                        
                        if duration > 3600:  # 超过1小时
                            st.warning(f"⚠️ 音频较长（{format_duration(duration)}），转录可能需要较长时间")
                        
                    except Exception as e:
                        st.error(f"音频文件验证失败：{e}")
                        raise e
                    
                    progress_bar.progress(100)
                    status_text.text("文件处理完成！")
                    
                    # 设置会话状态
                    st.session_state.audio_path = audio_path
                    st.session_state.media_title = os.path.splitext(uploaded_file.name)[0]
                    st.session_state.download_completed = True
                    
                    st.success(f"✅ 文件上传成功：{uploaded_file.name}")
                    
                except Exception as e:
                    st.error(f"处理文件时发生错误：{str(e)}")
                    st.session_state.download_completed = False
                    st.session_state.audio_path = None
                    st.session_state.media_title = None
        else:
            st.info("👆 请选择要上传的音频或视频文件")
            
    else:
        # 原有的URL输入逻辑
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
    "第二步：转录音频", expanded=st.session_state.download_completed and not st.session_state.transcribe_completed
)
with transcribe_expander:
    if st.session_state.download_completed:
        st.info("提示: 一分钟的音频大约需要10秒钟转录时间(不同设备转录时间不同)")

        # 详细的设备检测和信息显示
        device_options = ["CPU"]
        device_info = {}
        
        # 检测CPU信息
        cpu_count = psutil.cpu_count()
        available_ram = psutil.virtual_memory().available / (1024**3)
        total_ram = psutil.virtual_memory().total / (1024**3)
        device_info["CPU"] = f"CPU ({cpu_count}核心, {available_ram:.1f}GB可用/{total_ram:.1f}GB总内存)"
        
        # 检测GPU信息
        try:
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                for i in range(gpu_count):
                    gpu_name = torch.cuda.get_device_name(i)
                    gpu_memory = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                    device_options.append(f"GPU (CUDA) - {gpu_name}")
                    device_info[f"GPU (CUDA) - {gpu_name}"] = f"GPU {i}: {gpu_name} ({gpu_memory:.1f}GB显存)"
        except Exception as e:
            st.warning(f"检测GPU时出错: {e}")
        
        # 检测 MPS (Apple Silicon)
        try:
            if torch.backends.mps.is_available():
                device_options.append("GPU (MPS) - Apple Silicon")
                device_info["GPU (MPS) - Apple Silicon"] = "Apple Silicon GPU (Metal Performance Shaders)"
        except Exception:
            pass
            
        selected_device_display = st.selectbox("选择运行设备：", device_options)
        
        # 显示选中设备的详细信息
        if selected_device_display in device_info:
            st.info(f"🖥️ 设备信息: {device_info[selected_device_display]}")
            
        # 根据设备推荐模型
        if "GPU" in selected_device_display and "16" in str(total_ram) and ("12" in selected_device_display or "RTX" in selected_device_display):
            st.success("🚀 检测到高性能配置，建议使用 large-v3 模型获得最佳转录效果")
        elif "GPU" in selected_device_display:
            st.info("💡 GPU模式将显著提升转录速度")
        else:
            st.warning("⚠️ CPU模式转录速度较慢，建议使用较小的音频文件")

        # 转换设备选择为程序可用的格式
        device_map = {
            "CPU": "cpu",
            **{opt: "cuda" for opt in device_options if "CUDA" in opt},
            **{opt: "mps" for opt in device_options if "MPS" in opt}
        }
        selected_device = device_map.get(selected_device_display, "cpu")

        # 格式选择
        output_format = st.selectbox("选择输出格式：", ["txt", "srt"], 
                                   index=0 if st.session_state.output_format == "txt" else 1)
        st.session_state.output_format = output_format

        # 模型大小选择
        model_options = ["base", "small", "medium", "large-v3"]
        model_descriptions = {
            "base": "基础模型 (290MB) - 速度快，准确率一般",
            "small": "小型模型 (967MB) - 平衡速度和准确率", 
            "medium": "中型模型 (3.1GB) - 准确率较高",
            "large-v3": "大型模型v3 (6.2GB) - 最高准确率，推荐用于重要内容"
        }
        
        # 根据设备推荐默认模型
        if "GPU" in selected_device_display and available_ram >= 12:
            default_model = "large-v3"
        elif "GPU" in selected_device_display and available_ram >= 8:
            default_model = "medium"
        elif available_ram >= 8:
            default_model = "small"
        else:
            default_model = "base"
            
        selected_model = st.selectbox(
            "选择转录模型：",
            model_options,
            index=model_options.index(default_model),
            format_func=lambda x: f"{x} - {model_descriptions[x]}"
        )
        
        # 显示模型兼容性提示
        if selected_model == "large-v3":
            if available_ram < 12:
                st.error("❌ 内存不足，large-v3 模型需要至少 12GB 内存")
            elif "CPU" in selected_device_display:
                st.warning("⚠️ CPU 模式使用 large-v3 会非常慢，建议使用 GPU 或选择较小模型")
            else:
                st.success("✅ 配置充足，可以使用 large-v3 模型")

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

                # 开始转录 - 传递模型参数
                txt_path, pdf_path = transcribe_audio(
                    st.session_state.audio_path,
                    output_file,
                    output_format,
                    selected_device,
                    selected_model  # 新增模型参数
                )

                # 保存文件路径到会话状态
                st.session_state.txt_path = txt_path
                st.session_state.pdf_path = pdf_path
                st.session_state.transcribe_completed = True

                # 计算耗时
                elapsed_time = time.time() - start_time
                status_text_transcribe.text("转录完成！")

                # 读取并显示转录结果
                with open(txt_path, "r", encoding="utf-8") as f:
                    st.session_state.transcript = f.read()

                st.success(f"转录完成！耗时：{elapsed_time:.2f}秒")
                st.session_state.is_transcribing = False

            except Exception as e:
                st.error(f"转录失败：{str(e)}")
                st.session_state.is_transcribing = False
    else:
        st.info("请先成功完成音频下载")

# 下载文件部分（独立显示，不会因为页面刷新而消失）
if st.session_state.transcribe_completed and st.session_state.transcript:
    # 第三步：AI总结功能
    summarize_expander = st.expander(
        "第三步：AI智能总结", expanded=st.session_state.transcribe_completed and not st.session_state.summarize_completed
    )
    with summarize_expander:
        st.info("📝 对转录文本进行智能分段总结和整体分析")
        
        # 初始化总结器
        if st.session_state.summarizer is None:
            try:
                st.session_state.summarizer = get_summarizer()
            except Exception as e:
                st.error(f"初始化AI总结器失败：{str(e)}")
                st.info("💡 请检查config.yaml配置文件是否存在并正确配置")
                st.stop()
        
        # 检查可用模型
        available_models = st.session_state.summarizer.get_available_models()
        
        if not available_models:
            st.warning("⚠️ 未检测到已配置的AI模型")
            st.info("请在config.yaml文件中配置至少一个AI模型的API密钥")
            
            # 显示配置示例
            show_config_help = st.checkbox("📖 查看配置说明", value=False)
            if show_config_help:
                st.code("""
# 在config.yaml中配置API密钥，例如：
ai_models:
  openai:
    api_key: "your_openai_api_key_here"
  claude:
    api_key: "your_claude_api_key_here"
                """)
        else:
            # 检查是否有未完成的任务
            incomplete_tasks = st.session_state.summarizer.list_incomplete_tasks()
            
            # 任务管理界面
            if incomplete_tasks:
                st.subheader("📋 任务管理")
                
                # 显示未完成任务
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"发现 {len(incomplete_tasks)} 个未完成的任务：")
                with col2:
                    if st.button("🗑️ 清理所有任务", help="删除所有未完成的任务"):
                        for task in incomplete_tasks:
                            st.session_state.summarizer.delete_task(task.task_id)
                        st.success("已清理所有任务")
                        st.rerun()
                
                # 选择任务
                task_options = {}
                for task in incomplete_tasks:
                    info = st.session_state.summarizer.progress_manager.format_task_display_info(task)
                    display_text = f"📄 {info['title'][:30]}... | {info['progress']} | {info['status']} | {info['updated']}"
                    task_options[display_text] = task.task_id
                
                selected_task_display = st.selectbox(
                    "选择要恢复的任务：",
                    ["创建新任务"] + list(task_options.keys()),
                    help="选择一个未完成的任务继续执行，或创建新任务"
                )
                
                if selected_task_display != "创建新任务":
                    selected_task_id = task_options[selected_task_display]
                    selected_task = st.session_state.summarizer.resume_task(selected_task_id)
                    
                    if selected_task:
                        # 显示任务详情
                        with st.container():
                            st.write("**任务详情：**")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("完成进度", f"{selected_task.get_progress_percentage():.1f}%")
                            with col2:
                                st.metric("完成分段", f"{len(selected_task.completed_segments)}/{selected_task.total_segments}")
                            with col3:
                                st.metric("失败分段", len(selected_task.failed_segments))
                            
                            if selected_task.failed_segments:
                                st.warning(f"有 {len(selected_task.failed_segments)} 个分段失败，将尝试重新处理")
                        
                        # 继续任务按钮
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("🔄 继续任务", key="continue_task"):
                                try:
                                    progress_bar = st.progress(selected_task.get_progress_percentage() / 100)
                                    status_text = st.empty()
                                    
                                    def update_progress(progress, message):
                                        progress_bar.progress(progress)
                                        status_text.text(message)
                                    
                                    # 继续执行任务
                                    summary_result = st.session_state.summarizer.summarize_transcript(
                                        st.session_state.transcript,
                                        selected_task.model_key,
                                        progress_callback=update_progress,
                                        task=selected_task
                                    )
                                    
                                    st.session_state.summary_data = summary_result
                                    st.session_state.summarize_completed = True
                                    
                                    status_text.text("任务完成！")
                                    st.success("✅ 任务继续执行完成")
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"继续任务失败：{str(e)}")
                        
                        with col2:
                            if st.button("🗑️ 删除任务", key="delete_selected_task"):
                                if st.session_state.summarizer.delete_task(selected_task.task_id):
                                    st.success("任务已删除")
                                    st.rerun()
                                else:
                                    st.error("删除任务失败")
                    
                    # 分隔线
                    st.divider()
            
            # AI模型选择
            selected_model = st.selectbox(
                "选择AI模型：",
                list(available_models.keys()),
                format_func=lambda x: available_models[x]
            )
            
            # 总结模式选择
            st.subheader("📝 选择总结模式")
            
            # 使用单选按钮选择总结模式
            summary_mode = st.radio(
                "请选择您需要的总结方式：",
                options=["structured", "deep_analysis"],
                format_func=lambda x: {
                    "structured": "📊 结构化总结 - 智能分段 + 关键词提取 + 主题分析",
                    "deep_analysis": "🧠 深度分析 - 基于自定义模板的专业内容分析"
                }[x],
                index=0 if st.session_state.summary_mode == "structured" else 1,
                help="结构化总结适合快速了解内容要点，深度分析适合生成专业技术文档"
            )
            
            # 更新会话状态
            st.session_state.summary_mode = summary_mode
            
            # 根据选择的模式显示不同的配置选项和说明
            if summary_mode == "structured":
                with st.container():
                    st.write("**结构化总结功能：**")
                    st.write("• 🎯 智能主题分段，自动识别内容转折点")
                    st.write("• 📝 每段1-2句话精准总结")
                    st.write("• 🔍 自动提取关键词和主要主题")
                    st.write("• 📊 生成完整的内容概览")
                    st.write("• 💾 支持断点续传，任务管理")
                    
                    # 结构化总结的配置选项
                    col1, col2 = st.columns(2)
                    with col1:
                        include_keywords = st.checkbox("包含关键词提取", value=True, help="为每个分段提取3-5个关键词")
                    with col2:
                        include_topics = st.checkbox("包含主题分析", value=True, help="分析整体内容的主要主题")
                    
                    # 显示是否支持断点续传
                    st.info("💡 结构化总结支持断点续传功能，如遇网络问题可随时恢复")
                    
            else:  # deep_analysis
                with st.container():
                    st.write("**深度分析功能：**")
                    st.write("• 📋 基于专业模板的结构化输出")
                    st.write("• 🎨 生成适合微信公众号的格式化内容")
                    st.write("• 📊 包含思维导图和可视化元素")
                    st.write("• 🔬 深度挖掘内容价值和见解")
                    st.write("• ✅ 内容质量控制和专业术语处理")
                    
                    # 检查prompt.txt文件
                    if os.path.exists("prompt.txt"):
                        show_template = st.checkbox("📄 查看分析模板内容", value=False)
                        if show_template:
                            with open("prompt.txt", "r", encoding="utf-8") as f:
                                prompt_content = f.read()
                            st.code(prompt_content, language="text")
                        
                        st.success("✅ 检测到深度分析模板文件 (prompt.txt)")
                    else:
                        st.error("❌ 未找到深度分析模板文件 (prompt.txt)")
                        st.info("请确保prompt.txt文件在项目根目录中，深度分析功能需要此模板文件")
                        st.stop()  # 阻止继续执行
            
            st.divider()
            
            # 统一的开始总结按钮
            if summary_mode == "structured":
                button_text = "🚀 开始结构化总结"
                button_key = "start_structured_summary"
            else:
                button_text = "🧠 开始深度分析"
                button_key = "start_deep_analysis"
            
            if st.button(button_text, key=button_key, type="primary"):
                if not st.session_state.transcript:
                    st.error("未找到转录文本")
                    st.stop()
                
                try:
                    if summary_mode == "structured":
                        # 结构化总结流程
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def update_progress(progress, message):
                            progress_bar.progress(progress)
                            status_text.text(message)
                        
                        # 创建新任务
                        new_task = st.session_state.summarizer.create_new_task(
                            st.session_state.media_title, 
                            selected_model
                        )
                        
                        # 执行结构化总结
                        summary_result = st.session_state.summarizer.summarize_transcript(
                            st.session_state.transcript,
                            selected_model,
                            progress_callback=update_progress,
                            task=new_task
                        )
                        
                        st.session_state.summary_data = summary_result
                        st.session_state.summarize_completed = True
                        st.session_state.deep_analysis_result = None  # 清除深度分析结果
                        
                        status_text.text("结构化总结完成！")
                        st.success("✅ 结构化总结已完成")
                        st.rerun()
                        
                    else:  # deep_analysis
                        # 深度分析流程
                        with st.spinner("正在进行深度分析，这可能需要较长时间..."):
                            deep_result = st.session_state.summarizer.deep_analysis(
                                st.session_state.transcript,
                                selected_model
                            )
                            
                            st.session_state.deep_analysis_result = deep_result
                            st.session_state.summarize_completed = False  # 深度分析使用不同的完成标记
                            st.session_state.summary_data = None  # 清除结构化总结结果
                            
                            st.success("✅ 深度分析已完成")
                            st.rerun()
                            
                except Exception as e:
                    st.error(f"总结失败：{str(e)}")
                    
                    # 根据错误类型给出不同的提示
                    error_msg = str(e).lower()
                    if "api" in error_msg or "key" in error_msg:
                        st.info("💡 请检查API密钥是否正确配置，以及网络连接是否正常")
                    elif "重试" in error_msg:
                        st.info("💡 任务已保存，您可以稍后从任务管理中继续执行")
                    elif "prompt" in error_msg or "文件" in error_msg:
                        st.info("💡 请检查prompt.txt文件是否存在且格式正确")
                    else:
                        st.info("💡 请检查网络连接和模型配置，或稍后重试")
    
    # 显示总结结果
    if st.session_state.summary_data or st.session_state.deep_analysis_result:
        results_expander = st.expander("📋 总结结果", expanded=True)
        with results_expander:
            # 根据不同的结果类型显示不同的内容
            if st.session_state.summary_data:
                # 显示结构化总结结果
                st.subheader("📊 结构化总结结果")
                summary = st.session_state.summary_data
                
                # 显示总体总结
                st.subheader("📝 总体总结")
                st.write(summary['overall_summary'])
                
                # 显示主题分析
                if summary['topics']:
                    st.subheader("🏷️ 主要主题")
                    for i, topic in enumerate(summary['topics'], 1):
                        st.write(f"{i}. {topic}")
                
                # 显示分段总结
                st.subheader("📑 分段总结")
                for segment in summary['segments']:
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**第{segment['index']}段**")
                            if segment['start_time']:
                                st.caption(f"时间: {segment['start_time']}")
                            st.write(segment['summary'])
                        with col2:
                            if segment['keywords']:
                                st.write("**关键词:**")
                                keywords_html = ""
                                for kw in segment['keywords']:
                                    keywords_html += f'<span style="background-color: #f0f2f6; color: #262730; padding: 2px 8px; margin: 2px; border-radius: 12px; font-size: 12px; display: inline-block;">{kw}</span> '
                                st.markdown(keywords_html, unsafe_allow_html=True)
                        st.divider()
                
                # 结构化总结的导出选项
                st.subheader("💾 导出结构化总结")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("📄 导出为TXT", key="export_structured_txt"):
                        try:
                            txt_path = st.session_state.summarizer.export_summary(
                                summary, "txt", st.session_state.media_title
                            )
                            with open(txt_path, 'r', encoding='utf-8') as f:
                                txt_content = f.read()
                            st.download_button(
                                "下载TXT文件",
                                txt_content,
                                file_name=os.path.basename(txt_path),
                                mime="text/plain"
                            )
                            st.success("TXT文件已生成")
                        except Exception as e:
                            st.error(f"导出TXT失败：{str(e)}")
                
                with col2:
                    if st.button("📝 导出为Markdown", key="export_structured_md"):
                        try:
                            md_path = st.session_state.summarizer.export_summary(
                                summary, "markdown", st.session_state.media_title
                            )
                            with open(md_path, 'r', encoding='utf-8') as f:
                                md_content = f.read()
                            st.download_button(
                                "下载Markdown文件",
                                md_content,
                                file_name=os.path.basename(md_path),
                                mime="text/markdown"
                            )
                            st.success("Markdown文件已生成")
                        except Exception as e:
                            st.error(f"导出Markdown失败：{str(e)}")
                
                with col3:
                    if st.button("📑 导出为PDF", key="export_structured_pdf"):
                        try:
                            pdf_path = st.session_state.summarizer.export_summary(
                                summary, "pdf", st.session_state.media_title
                            )
                            with open(pdf_path, 'rb') as f:
                                pdf_content = f.read()
                            st.download_button(
                                "下载PDF文件",
                                pdf_content,
                                file_name=os.path.basename(pdf_path),
                                mime="application/pdf"
                            )
                            st.success("PDF文件已生成")
                        except Exception as e:
                            st.error(f"导出PDF失败：{str(e)}")
            
            elif st.session_state.deep_analysis_result:
                # 显示深度分析结果
                st.subheader("🧠 深度分析结果")
                st.write(st.session_state.deep_analysis_result)
                
                # 深度分析的导出选项
                st.subheader("💾 导出深度分析")
                col1, col2 = st.columns(2)
                
                with col1:
                    # 下载为TXT格式
                    st.download_button(
                        "📄 下载深度分析报告 (TXT)",
                        st.session_state.deep_analysis_result,
                        file_name=f"{st.session_state.media_title}_深度分析.txt",
                        mime="text/plain",
                        key="download_deep_analysis_txt"
                    )
                
                with col2:
                    # 下载为Markdown格式（适合公众号使用）
                    st.download_button(
                        "📝 下载深度分析报告 (Markdown)",
                        st.session_state.deep_analysis_result,
                        file_name=f"{st.session_state.media_title}_深度分析.md",
                        mime="text/markdown",
                        key="download_deep_analysis_md"
                    )
                
                # 添加清空结果的选项
                st.divider()
                if st.button("🗑️ 清空当前结果", key="clear_deep_analysis", help="清空当前显示的深度分析结果"):
                    st.session_state.deep_analysis_result = None
                    st.success("已清空深度分析结果")
                    st.rerun()
            
            # 通用功能：重新选择总结模式
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 重新选择总结模式", key="change_summary_mode"):
                    # 清空所有结果，让用户重新选择
                    st.session_state.summary_data = None
                    st.session_state.deep_analysis_result = None
                    st.session_state.summarize_completed = False
                    st.success("已重置，请重新选择总结模式")
                    st.rerun()
            
            with col2:
                if st.button("📊 切换到另一种总结模式", key="switch_summary_mode"):
                    # 切换到另一种模式（但保留当前结果）
                    current_mode = st.session_state.summary_mode
                    new_mode = "deep_analysis" if current_mode == "structured" else "structured"
                    st.session_state.summary_mode = new_mode
                    
                    mode_names = {
                        "structured": "结构化总结",
                        "deep_analysis": "深度分析"
                    }
                    st.info(f"已切换到 {mode_names[new_mode]} 模式，您可以对同一份内容进行不同类型的分析")
                    st.rerun()

    # 第四步：下载转录文件功能
    download_expander = st.expander("第四步：下载原始转录文件", expanded=False)
    with download_expander:
        st.success("✅ 转录已完成，可以下载原始转录文件")
        
        # 创建下载按钮容器
        col1, col2 = st.columns(2)
        
        with col1:
            if st.session_state.txt_path and os.path.exists(st.session_state.txt_path):
                st.download_button(
                    label="📄 下载转录文件 (TXT)",
                    data=st.session_state.transcript,
                    file_name=os.path.basename(st.session_state.txt_path),
                    mime="text/plain",
                    key="download_original_txt"
                )
            else:
                st.warning("TXT 文件不可用")
        
        with col2:
            # PDF下载按钮
            if (st.session_state.output_format == "txt" and 
                st.session_state.pdf_path and 
                os.path.exists(st.session_state.pdf_path)):
                try:
                    with open(st.session_state.pdf_path, "rb") as pdf_file:
                        pdf_data = pdf_file.read()
                    st.download_button(
                        label="📑 下载转录文件 (PDF)",
                        data=pdf_data,
                        file_name=os.path.basename(st.session_state.pdf_path),
                        mime="application/pdf",
                        key="download_original_pdf"
                    )
                except Exception as e:
                    st.error(f"读取PDF文件失败: {e}")
            elif st.session_state.output_format == "srt":
                st.info("SRT格式不生成PDF文件")
            else:
                st.warning("PDF 文件不可用")
        
        # 添加重新转录选项
        st.divider()
        if st.button("🔄 重新转录", key="retranscribe"):
            st.session_state.transcribe_completed = False
            st.session_state.transcript = None
            st.session_state.txt_path = None
            st.session_state.pdf_path = None
            # 同时重置总结相关状态
            st.session_state.summarize_completed = False
            st.session_state.summary_data = None
            st.session_state.deep_analysis_result = None
            st.success("已重置转录状态，可以重新开始转录")
            st.rerun()

# 转录结果显示
if st.session_state.transcript:
    st.subheader("转录文稿预览")
    st.text_area("转录内容", st.session_state.transcript, height=300, key="transcript_preview")

# 清理功能和侧边栏工具
def cleanup_temp_files():
    """清理临时上传文件"""
    temp_dir = "temp_uploads"
    if os.path.exists(temp_dir):
        try:
            import shutil
            shutil.rmtree(temp_dir)
            return True
        except Exception as e:
            st.warning(f"清理临时文件时出错：{e}")
            return False
    return True

# 侧边栏工具
with st.sidebar:
    st.subheader("🛠️ 工具")
    
    # 显示当前使用的内容来源
    if "source_type" in st.session_state:
        st.info(f"当前内容来源：{st.session_state.source_type}")
    
    # 显示当前进度
    progress_info = []
    if st.session_state.download_completed:
        progress_info.append("✅ 音频下载")
    if st.session_state.transcribe_completed:
        progress_info.append("✅ 音频转录")
    if st.session_state.summarize_completed:
        progress_info.append("✅ AI总结")
    if st.session_state.deep_analysis_result:
        progress_info.append("✅ 深度分析")
    
    if progress_info:
        st.write("**当前进度：**")
        for info in progress_info:
            st.write(info)
    
    st.divider()
    
    # 配置管理
    st.subheader("⚙️ 配置管理")
    
    # 检查配置文件状态
    if os.path.exists("config.yaml"):
        st.success("✅ 配置文件已存在")
        if st.button("📝 编辑配置"):
            st.info("请直接编辑项目根目录下的 config.yaml 文件")
    else:
        st.warning("⚠️ 配置文件不存在")
        if st.button("📝 创建配置文件"):
            st.info("配置文件已在项目启动时创建，请刷新页面")
    
    # AI模型状态
    if st.session_state.summarizer:
        models = st.session_state.summarizer.get_available_models()
        if models:
            st.success(f"✅ 已配置 {len(models)} 个AI模型")
            with st.expander("查看可用模型"):
                for key, name in models.items():
                    st.write(f"• {name}")
        else:
            st.warning("⚠️ 未配置AI模型")
    
    st.divider()
    
    # 清理和重置功能
    st.subheader("🧹 清理工具")
    
    # 清理临时文件按钮
    if st.button("🗑️ 清理临时文件"):
        if cleanup_temp_files():
            st.success("临时文件已清理")
        else:
            st.error("清理失败")
    
    # 重置所有状态
    if st.button("🔄 重置所有状态"):
        for key in list(st.session_state.keys()):
            if key not in ['summarizer']:  # 保留缓存的总结器
                del st.session_state[key]
        cleanup_temp_files()
        st.success("状态已重置")
        st.rerun()
    
    st.divider()
    
    # 显示支持的文件格式
    with st.expander("📋 支持的文件格式"):
        st.write("**音频格式：**")
        st.write("MP3, WAV, M4A, FLAC, OGG, AAC")
        st.write("**视频格式：**")
        st.write("MP4, MKV, AVI, MOV, WMV, WebM")
        st.write("**导出格式：**")
        st.write("TXT, SRT, PDF, Markdown")
    
    # 帮助信息
    with st.expander("❓ 使用帮助"):
        st.write("**第一步：** 获取音频文件")
        st.write("- 支持小宇宙播客链接")
        st.write("- 支持YouTube视频链接")
        st.write("- 支持本地文件上传")
        
        st.write("**第二步：** 音频转录")
        st.write("- 选择适合的设备和模型")
        st.write("- 支持多种输出格式")
        
        st.write("**第三步：** AI智能总结")
        st.write("- 基础总结：智能分段和概览")
        st.write("- 高级分析：深度内容分析")
        
        st.write("**第四步：** 下载文件")
        st.write("- 原始转录文件")
        st.write("- AI总结报告")
        st.write("- 深度分析报告")
