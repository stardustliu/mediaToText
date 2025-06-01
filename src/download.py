import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import os
from tqdm import tqdm
# from pytube import YouTube # 移除 pytube 导入
import re
import subprocess # 新增导入 subprocess
import json # 新增导入 json 用于获取元数据


def download_podcast_audio(url, progress_callback=None):
    print(f"downloading podcast from {url}")
    # 设置Selenium的Chrome浏览器选项
    start_time = time.time()
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 无头模式，不显示浏览器界面
    chrome_options.add_argument("--disable-gpu")  # 禁用GPU加速
    chrome_options.add_argument("--no-sandbox")  # 禁用沙盒模式
    # 添加新的选项以提高稳定性
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    # 不指定Service，让Selenium自动查找chromedriver（需确保chromedriver在环境变量中）
    driver = webdriver.Chrome(options=chrome_options)
    end_time = time.time()
    print(f"driver init time: {end_time - start_time} seconds")
    # # 设置页面加载超时时间
    # driver.set_page_load_timeout(30)
    # # 设置脚本执行超时时间
    # driver.set_script_timeout(60)

    try:
        # 加载目标网页
        print("正在加载播客页面...")
        driver.get(url)
        end_time = time.time()
        print(f"page load time: {end_time - start_time} seconds")

        # 1. 获取播客标题
        #   - 如果 class 名称中包含较多动态信息（如 "jsx-399326063 title"），
        #     建议用 XPATH 的方式做部分匹配，避免以后 class 变化导致抓取失败。
        #   - 例如: //h1[contains(@class,'title')]
        title_element = driver.find_element(By.XPATH, "//h1[contains(@class,'title')]")
        podcast_title = title_element.text
        print("播客标题:", podcast_title)

        # 2. 查找网页中的 <audio> 标签，获取音频 URL
        audio_element = driver.find_element(By.TAG_NAME, "audio")
        audio_url = audio_element.get_attribute("src")
        if not audio_url:
            print("网页中未找到音频文件。")
            return None, None # 返回 None 表示失败

        # 3. 下载音频文件
        response = requests.get(audio_url, stream=True, verify=False)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        
        os.makedirs("audio_files", exist_ok=True)
        # 清理标题中的非法字符，用于文件名
        safe_title = re.sub(r'[\/*?:"<>|]', "", podcast_title)
        audio_path = os.path.join("audio_files", f"{safe_title}-podcast_audio.mp3") # 调整文件名

        downloaded = 0
        print(f"开始下载音频文件到 {audio_path}...")
        with open(audio_path, 'wb') as audio_file:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                audio_file.write(data)
                if progress_callback and total_size > 0:
                    progress = (downloaded / total_size)
                    progress_callback(progress)
        
        print(f"播客音频文件已保存到 {audio_path}")
        return audio_path, podcast_title

    except Exception as e:
        print(f"下载播客时出错: {e}")
        return None, None # 返回 None 表示失败
    finally:
        driver.quit()


# 重写 YouTube 音频下载函数，使用 yt-dlp
def download_youtube_audio(url, progress_callback=None, cookies_path=None): # 添加 cookies_path 参数
    print(f"downloading youtube audio from {url} using yt-dlp")
    if cookies_path and os.path.exists(cookies_path):
        print(f"使用 Cookies 文件: {cookies_path}")
        cookies_arg = ["--cookies", cookies_path]
    else:
        if cookies_path:
             print(f"警告: 提供的 Cookies 文件路径无效或不存在: {cookies_path}")
        cookies_arg = []

    try:
        # 1. 获取视频标题和清理文件名
        # 优先尝试使用 --get-title 获取标题，更简单稳定
        video_title = None
        try:
            # 在获取标题时也使用 cookies
            info_command = ['yt-dlp', '--get-title'] + cookies_arg + [url]
            result = subprocess.run(info_command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
            video_title = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"使用 --get-title 获取标题失败: {e}")
            # 如果 --get-title 失败，尝试回退到 --print
            try:
                # 在备选方案中也使用 cookies
                info_command = [
                    'yt-dlp',
                    '--print', '%(.{title})j' # 只打印标题的 JSON 格式
                ] + cookies_arg + [url]
                result = subprocess.run(info_command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
                # 输出可能是 JSON 字符串 (带引号)，需要解析或清理
                raw_title = result.stdout.strip()
                if raw_title.startswith('"') and raw_title.endswith('"'):
                    video_title = raw_title[1:-1]
                else:
                     video_title = raw_title # 直接使用，以防不是预期的JSON
            except subprocess.CalledProcessError as e_print:
                 print(f"使用 --print 获取标题也失败: {e_print}")
                 print("Stderr:", e_print.stderr) # 尝试打印原始 stderr
                 return None, None # 两种方法都失败
            except Exception as e_fallback:
                 print(f"尝试 --print 时发生其他错误: {e_fallback}")
                 return None, None
        except Exception as e_get_title:
            print(f"尝试 --get-title 时发生其他错误: {e_get_title}")
            return None, None

        if not video_title:
            print("无法获取视频标题。")
            return None, None
        
        print(f"YouTube 视频标题: {video_title}")
        safe_title = re.sub(r'[\/*?:"<>|]', "", video_title)
        output_filename = f"{safe_title}-youtube_audio.mp3" # 指定输出为 mp3
        audio_path = os.path.join("audio_files", output_filename)

        # 2. 构建 yt-dlp 下载命令
        #    -f ba: 选择最佳质量的纯音频流
        #    -o: 指定输出模板 (使用 %(ext)s 让 yt-dlp 决定扩展名)
        #    --progress: 显示进度
        #    --no-playlist: 如果是播放列表链接，只下载单个视频
        #    --no-warnings: 减少不必要的输出
        download_command = [
            'yt-dlp',
            '-f', 'ba', # 请求最佳音频 (bestaudio)
            '-o', os.path.join("audio_files", f"{safe_title}-youtube_audio.%(ext)s"), # 输出模板，扩展名由 yt-dlp 决定
            '--progress',
            '--no-playlist',
            '--no-warnings',
        ] + cookies_arg + [url] # 添加 cookies 参数到下载命令

        print(f"执行 yt-dlp 命令: {' '.join(download_command)}")
        
        # 使用 progress_callback 更新状态，但不显示具体百分比
        if progress_callback:
            progress_callback(0.0) # 表示开始

        # 3. 执行下载命令
        process = subprocess.Popen(download_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            print(f"yt-dlp 下载成功。音频文件已保存到 {audio_path}")
            # 确保最终路径是 mp3 后缀
            if not os.path.exists(audio_path):
                expected_prefix = os.path.join("audio_files", f"{safe_title}-youtube_audio")
                found_files = [f for f in os.listdir("audio_files") if f.startswith(f"{safe_title}-youtube_audio")]
                if found_files:
                     actual_filename = found_files[0]
                     audio_path = os.path.join("audio_files", actual_filename) # 使用实际找到的文件名
                     print(f"实际文件路径为: {audio_path}")
                else:
                     print("警告：yt-dlp 运行成功，但未找到预期的输出文件！")
                     return None, None
                     
            if progress_callback:
                progress_callback(1.0) # 表示完成
            return audio_path, video_title
        else:
            print("yt-dlp 下载失败。")
            # 在打印 stdout 和 stderr 时使用 errors='ignore'
            print("yt-dlp stdout:", stdout.decode('utf-8', errors='ignore'))
            print("yt-dlp stderr:", stderr.decode('utf-8', errors='ignore'))
            if progress_callback:
                 progress_callback(-1.0) # 使用负数表示错误
            return None, None

    except subprocess.CalledProcessError as e: # 这个顶层 except 可能不会被触发了，因为内部处理了
        print(f"执行 yt-dlp 时出错: {e}")
        # 尝试用 ignore 解码 stderr
        stderr_decoded = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "None"
        print("Stderr:", stderr_decoded)
        if progress_callback:
            progress_callback(-1.0)
        return None, None
    except FileNotFoundError:
        print("错误: 找不到 'yt-dlp' 命令。请确保 yt-dlp 已安装并添加到系统 PATH 中。")
        if progress_callback:
            progress_callback(-1.0)
        return None, None
    except Exception as e:
        print(f"下载 YouTube 音频时发生未知错误: {e}")
        if progress_callback:
            progress_callback(-1.0)
        return None, None


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="下载小宇宙播客音频文件")
#     parser.add_argument(
#         "-u", "--url",
#         type=str,
#         help="播客页面 URL",
#         required=True
#     )
#     args = parser.parse_args()
#     download_podcast_audio(args.url) # 更新调用

