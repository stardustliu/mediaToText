import argparse
from faster_whisper import WhisperModel
from fpdf import FPDF
import os
import glob
import platform
import re  # <-- 新增导入

from datetime import timedelta


def sanitize_filename(filename):
    """清理文件名，移除或替换不合法的字符"""
    # Windows 不允许的字符：< > : " | ? * \ /
    # 同时处理其他可能有问题的字符
    illegal_chars = r'[<>:"|?*\\/]'
    # 替换为下划线
    clean_name = re.sub(illegal_chars, '_', filename)
    # 移除多余的空格和点
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    # 移除结尾的点（Windows不允许）
    clean_name = clean_name.rstrip('.')
    return clean_name


def format_timestamp(seconds):
    """将秒转换为 SRT 时间格式：HH:MM:SS,mmm"""
    millisec = int((seconds - int(seconds)) * 1000)
    return str(timedelta(seconds=int(seconds))) + f",{millisec:03d}"


def generate_srt(segments):
    """将转录片段转换为 SRT 格式"""
    srt = []
    for i, segment in enumerate(segments, start=1):
        start_time = format_timestamp(segment.start)
        end_time = format_timestamp(segment.end)
        text = segment.text.strip()
        srt.append(f"{i}\n{start_time} --> {end_time}\n{text}\n")
    return "\n".join(srt)


def generate_txt(segments):
    """将转录片段转换为纯文本格式"""
    return "\n".join(segment.text.strip() for segment in segments)


def transcribe_audio(audio_path, output_file, output_format="txt", device_option='cpu', model_size='base'):
    print(f"audio path: {audio_path}, output file: {output_file}, output format: {output_format}, device option: {device_option}, model: {model_size}")

    # 根据设备设置计算类型：GPU 使用 float16，其它使用 int8
    compute_type = "float16" if device_option == "cuda" else "int8"

    # 加载指定大小的模型
    model = WhisperModel(model_size, device=device_option, compute_type=compute_type)
    print(f"Whisper {model_size} 模型已加载。")

    # 优化转录参数，特别是对中文的支持
    segments, info = model.transcribe(
        audio_path, 
        beam_size=5,
        language="zh",  # 明确指定中文
        task="transcribe",
        temperature=0.0,  # 降低随机性
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        vad_filter=True,  # 启用语音活动检测
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    print("音频转录完成。")
    print("检测到语言：%s (概率: %f)" % (info.language, info.language_probability))

    # 根据输出格式生成内容
    if output_format.lower() == "srt":
        content = generate_srt(segments)
    else:  # 默认为 txt 格式
        content = generate_txt(segments)

    # 清理输出文件名
    clean_output_file = sanitize_filename(output_file)
    
    # 将内容保存到文件
    with open(clean_output_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"转录文本已保存到文件：{clean_output_file}")

    # 如果输出格式是 txt，额外生成 PDF
    pdf_file_path = None
    if output_format.lower() == "txt":
        pdf_output_file = os.path.splitext(clean_output_file)[0] + ".pdf"
        try:
            pdf = FPDF()
            pdf.add_page()
            
            # 改进的字体处理逻辑
            font_loaded = False
            
            # 1. Windows 系统字体
            if os.name == 'nt':  # Windows 系统
                windows_fonts = [
                    ("simhei", "C:/Windows/Fonts/simhei.ttf"),  # 黑体
                    ("simsun", "C:/Windows/Fonts/simsun.ttc"),  # 宋体
                    ("msyh", "C:/Windows/Fonts/msyh.ttf"),      # 微软雅黑
                    ("msyhbd", "C:/Windows/Fonts/msyhbd.ttf"),  # 微软雅黑粗体
                ]
                for font_name, font_path in windows_fonts:
                    if os.path.exists(font_path):
                        try:
                            pdf.add_font(font_name, "", font_path, uni=True)
                            pdf.set_font(font_name, size=12)
                            font_loaded = True
                            print(f"成功加载字体：{font_name}")
                            break
                        except Exception as e:
                            print(f"尝试加载字体 {font_name} 失败：{e}")
                            continue
            
            # 2. macOS 系统字体
            elif platform.system() == 'Darwin':  # macOS 系统
                macos_fonts = [
                    ("pingfang", "/System/Library/Fonts/PingFang.ttc"),           # 苹方
                    ("pingfang_sc", "/System/Library/Fonts/Supplemental/Songti.ttc"), # 宋体
                    ("hiragino", "/System/Library/Fonts/Hiragino Sans GB.ttc"),  # 冬青黑体
                    ("stheiti", "/System/Library/Fonts/STHeiti Light.ttc"),      # 华文黑体
                    ("stsong", "/Library/Fonts/Songti.ttc"),                     # 华文宋体
                    ("arial_unicode", "/Library/Fonts/Arial Unicode.ttf"),       # Arial Unicode MS
                ]
                
                # 检查用户字体目录
                user_font_dir = os.path.expanduser("~/Library/Fonts")
                if os.path.exists(user_font_dir):
                    user_fonts = glob.glob(f"{user_font_dir}/*[Cc]hinese*.ttf") + \
                                glob.glob(f"{user_font_dir}/*[Ss]ong*.ttf") + \
                                glob.glob(f"{user_font_dir}/*[Hh]ei*.ttf")
                    for user_font in user_fonts:
                        font_name = os.path.splitext(os.path.basename(user_font))[0].lower()
                        macos_fonts.append((font_name, user_font))
                
                for font_name, font_path in macos_fonts:
                    if os.path.exists(font_path):
                        try:
                            pdf.add_font(font_name, "", font_path, uni=True)
                            pdf.set_font(font_name, size=12)
                            font_loaded = True
                            print(f"成功加载字体：{font_name} ({font_path})")
                            break
                        except Exception as e:
                            print(f"尝试加载字体 {font_name} 失败：{e}")
                            continue
            
            # 3. 备选方案（其他系统或字体加载失败）
            if not font_loaded:
                try:
                    pdf.set_font("Arial", size=12)
                    font_loaded = True
                    print("使用 Arial 字体（可能无法正确显示中文）")
                except Exception:
                    pdf.set_font("helvetica", size=12)
                    font_loaded = True
                    print("使用 helvetica 字体（可能无法正确显示中文）")

            # 将文本写入 PDF，按行分割以支持换行
            lines = content.split('\n')
            for line in lines:
                if line.strip():  # 跳过空行
                    try:
                        pdf.multi_cell(0, 10, txt=line, align='L')
                    except UnicodeEncodeError:
                        # 如果字符编码有问题，尝试用替换字符
                        safe_line = line.encode('ascii', 'replace').decode('ascii')
                        pdf.multi_cell(0, 10, txt=f"[包含特殊字符] {safe_line}", align='L')
                pdf.ln(3)  # 添加行间距

            pdf.output(pdf_output_file)
            if os.path.exists(pdf_output_file):
                pdf_file_path = pdf_output_file
                print(f"转录文本已额外保存到 PDF 文件：{pdf_output_file}")
                print(f"PDF 文件完整路径：{os.path.abspath(pdf_output_file)}")
            else:
                print(f"警告：PDF 文件可能因文件名特殊字符而保存失败：{pdf_output_file}")
            
        except Exception as e:
            print(f"错误：无法生成 PDF 文件 {pdf_output_file}: {e}")
            print("提示：txt 文件已正常生成，PDF 生成失败不影响主要功能。")

    # 返回文件路径，供 Streamlit 使用
    return clean_output_file, pdf_file_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="使用 faster‑whisper 模型进行音频转录。")
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="输入音频文件的路径，例如：audio_files/episode_audio.mp3"
    )
    parser.add_argument(
        "-o", "--output",
        default="transcription_output.txt",
        help="转录文本的输出文件路径，默认为 transcription_output.txt"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["txt", "srt"],
        default="txt",
        help="输出文件格式，支持 txt（纯文本）或 srt（字幕文件格式），默认为 txt。选择 txt 会同时生成 PDF。"
    )
    parser.add_argument(
        "-d", "--device",
        default=None,
        help="指定使用的设备，例如：cuda、cpu 或 mps（MPS 可能因部分算子不支持而自动回退使用 CPU）"
    )
    args = parser.parse_args()

    transcribe_audio(args.input, args.output, args.format, args.device)
