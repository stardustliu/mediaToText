# 小宇宙播客下载与转录工具

这是一个基于 Streamlit 开发的工具，可以帮助用户下载小宇宙播客音频并将其转录为文字，并通过AI进行智能总结。（个人自用）

## 功能特点

- 🎵 支持小宇宙播客音频下载
- 🎬 支持YouTube视频音频下载
- 📁 支持本地音频/视频文件上传
- 📝 音频转文字转录功能
- 🤖 **AI智能总结功能**
  - 智能主题分段
  - 分段简洁总结（1-2句话）
  - 整体内容概览
  - 关键词和主题提取
  - 深度分析（基于prompt.txt）
- 🔄 **强大的容错机制**
  - 自动重试机制（可配置次数和间隔）
  - 断点续传功能，API超时后可继续
  - 分段进度实时保存，避免重复工作
  - 任务状态管理，支持恢复未完成任务
- 🎯 支持导出 TXT、SRT、PDF、Markdown 格式
- 💻 简洁直观的 Web 界面
- ⏱️ 实时显示下载和转录进度
- 📊 显示音频时长和文件大小信息
- 🔧 支持多种AI模型（OpenAI、Claude、本地模型等）

## 截图
<img src="https://raw.githubusercontent.com/limboinf/xiaoyuzhoufm/refs/heads/main/usage1.png" width="600"/>

<img src="https://raw.githubusercontent.com/limboinf/xiaoyuzhoufm/refs/heads/main/usage2.png" width="600"/>

## 安装说明

1. 克隆项目到本地：

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置AI模型（可选，用于总结功能）：
```bash
# 复制配置模板并编辑
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入您的API密钥
```

## AI总结功能配置

为了使用AI总结功能，您需要配置至少一个AI模型的API密钥。在项目根目录的 `config.yaml` 文件中：

```yaml
ai_models:
  # OpenAI GPT
  openai:
    api_key: "your_openai_api_key_here"
    model: "gpt-4o-mini"  # 或其他模型
  
  # Claude (Anthropic)
  claude:
    api_key: "your_claude_api_key_here"
    model: "claude-3-haiku-20240307"
  
  # 自定义OpenAI兼容API（如ollama等本地模型）
  custom:
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"
    model: "qwen2.5:7b"

# 容错机制配置
retry:
  max_attempts: 3           # 最大重试次数
  delay_seconds: 5          # 重试间隔秒数
  exponential_backoff: true # 是否使用指数退避
  timeout_seconds: 60       # API调用超时时间

# 进度管理配置
progress:
  save_directory: "progress"     # 进度文件保存目录
  auto_save: true                # 是否自动保存进度
  keep_completed_tasks: 7        # 保留已完成任务的天数
  task_cleanup_enabled: true     # 是否启用任务清理
```

### 支持的AI模型

- **OpenAI**: GPT-3.5、GPT-4、GPT-4o等
- **Claude**: Claude-3-haiku、Claude-3-sonnet等
- **本地模型**: 任何支持OpenAI API格式的本地部署模型（如ollama、vLLM等）
- **其他**: 任何兼容OpenAI API格式的第三方服务

## 使用方法

1. 启动应用：
```bash
streamlit run src/app.py
```

2. 在浏览器中打开显示的地址（通常是 http://localhost:8501）

3. 使用步骤：

### 第一步：获取音频
- 在输入框中粘贴小宇宙播客链接、YouTube链接
- 或上传本地音频/视频文件
- 点击"开始下载"或"处理本地文件"

### 第二步：转录音频
- 选择转录设备（CPU/GPU）和输出格式（TXT/SRT）
- 选择适合的Whisper模型
- 点击"开始转录"进行音频转文字

### 第三步：AI智能总结（新功能）
- **任务管理**：
  - 自动检测未完成的任务
  - 支持恢复中断的总结任务
  - 显示任务进度和状态
  - 失败重试和错误处理

- **基础总结**：
  - 选择AI模型
  - 点击"开始智能总结"
  - 获得智能分段总结、整体概览、关键词和主题分析
  - 支持导出为TXT、Markdown、PDF格式
  - **断点续传**：API超时或失败时，已完成的分段会保存，可以继续执行

- **高级分析**：
  - 基于 `prompt.txt` 进行深度内容分析
  - 生成结构化的专业文档
  - 适合制作公众号文章等用途

### 第四步：下载文件
- 下载原始转录文件
- 下载AI总结报告
- 下载深度分析报告

## 容错机制说明

本工具内置了强大的容错机制，确保长时间运行的AI总结任务的稳定性：

### 1. 自动重试机制
- API调用失败时自动重试（默认3次）
- 支持指数退避策略，减少服务器压力
- 可配置重试次数和间隔时间

### 2. 断点续传功能
- 每个分段完成后立即保存进度
- API超时或网络中断时，已完成的工作不会丢失
- 可以从中断点继续执行，避免重复计算

### 3. 任务状态管理
- 任务保存在 `progress/` 目录中
- 使用媒体标题+UUID作为唯一标识
- 支持查看和管理未完成的任务

### 4. 智能错误处理
- 区分不同类型的错误（网络、API限制、服务器错误等）
- 对可恢复的错误进行重试
- 对不可恢复的错误立即停止并保存状态

## 文件结构

```
├── src/
│   ├── app.py              # 主应用程序
│   ├── download.py         # 下载功能模块
│   ├── transcribe.py       # 转录功能模块
│   ├── summarize.py        # AI总结功能模块
│   └── progress_manager.py # 进度管理模块
├── progress/               # 任务进度保存目录
├── config.yaml             # AI模型配置文件
├── prompt.txt              # 深度分析提示词模板
├── requirements.txt        # 依赖项列表
├── test_progress_manager.py # 容错机制测试脚本
└── README.md              # 使用说明
```

## 注意事项

- 转录速度与设备性能相关，一分钟音频约需要 10 秒转录时间
- AI总结功能需要网络连接和有效的API密钥
- 大型音频文件的总结可能需要较长时间，但支持断点续传
- 请确保API密钥安全，不要在公共场所暴露
- `progress/` 目录包含任务进度文件，请不要手动修改

## 技术栈

- Python
- Streamlit
- PyDub
- Torch
- Fast-Whisper
- OpenAI API / Anthropic API
- ReportLab (PDF生成)
- PyYAML (配置管理)

## Prompt

见prompt.txt, 配合 deepseek r1 对播客内容进行总结和分析，示例：

<img width="1191" alt="image" src="https://github.com/user-attachments/assets/d4c69b9a-e654-4ea6-8289-f973705f6a48" />

## 更新日志

### v2.1 (容错机制增强版)
- 🔄 新增强大的容错机制
- 📂 任务进度保存到 progress/ 目录
- 🆔 使用媒体标题+UUID生成任务标识
- 🔁 自动重试机制（可配置次数和间隔）
- ⏸️ 断点续传功能，API超时后可继续
- 📋 任务管理界面，支持恢复未完成任务
- 🧪 添加测试脚本验证功能

### v2.0 (新增AI总结功能)
- ✨ 新增AI智能总结功能
- 🤖 支持多种AI模型（OpenAI、Claude、本地模型）
- 📊 智能主题分段和关键词提取
- 📑 多格式导出（Markdown、PDF、TXT）
- 🧠 深度分析功能
- ⚙️ 配置文件管理
- 🎨 优化用户界面，支持四步流程

### v1.0 (基础版本)
- 🎵 播客下载和转录功能
- 📝 基础文件导出功能

