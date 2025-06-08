#!/usr/bin/env python3
"""
AI总结功能测试脚本
用于验证总结模块是否正常工作
"""

import os
import sys
from pathlib import Path

# 添加src目录到路径
sys.path.append('src')

from summarize import PodcastSummarizer

def test_configuration():
    """测试配置文件加载"""
    print("🔧 测试配置文件加载...")
    
    if not os.path.exists("config.yaml"):
        print("❌ config.yaml 文件不存在")
        print("💡 请先复制 config.yaml.example 为 config.yaml 并配置API密钥")
        return False
    
    try:
        summarizer = PodcastSummarizer()
        available_models = summarizer.get_available_models()
        
        if not available_models:
            print("⚠️  未检测到已配置的AI模型")
            print("💡 请在 config.yaml 中配置至少一个模型的API密钥")
            return False
        
        print(f"✅ 配置加载成功，发现 {len(available_models)} 个可用模型：")
        for key, name in available_models.items():
            print(f"   • {name} ({key})")
        
        return True, summarizer, available_models
        
    except Exception as e:
        print(f"❌ 配置加载失败：{e}")
        return False

def test_segmentation():
    """测试文本分段功能"""
    print("\n📝 测试文本分段功能...")
    
    # 示例文本
    sample_text = """
    这是第一段内容，主要讨论人工智能的发展历程。人工智能从最初的概念提出到现在的广泛应用，经历了几十年的发展。

    接下来我们谈谈机器学习。机器学习是人工智能的一个重要分支，它通过算法让计算机从数据中学习模式。

    另外，深度学习作为机器学习的一个子集，在图像识别、自然语言处理等领域取得了突破性进展。

    最后，我们来看看AI的未来发展趋势。随着计算能力的提升和数据量的增长，AI将在更多领域发挥重要作用。
    """
    
    try:
        summarizer = PodcastSummarizer()
        segments = summarizer.segmenter.segment_by_topic(sample_text)
        
        print(f"✅ 分段成功，共生成 {len(segments)} 个段落：")
        for i, segment in enumerate(segments, 1):
            print(f"   段落 {i}: {len(segment['content'])} 字符")
            print(f"   内容预览: {segment['content'][:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 分段测试失败：{e}")
        return False

def test_api_connection(summarizer, model_key):
    """测试API连接"""
    print(f"\n🌐 测试 {model_key} API连接...")
    
    try:
        from summarize import AIModelClient
        
        model_config = summarizer.config['ai_models'][model_key]
        client = AIModelClient(model_config)
        
        # 简单的测试消息
        test_messages = [{"role": "user", "content": "请回复'连接成功'"}]
        response = client.call_api(test_messages, "你是一个测试助手。")
        
        print(f"✅ API连接成功，响应：{response[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ API连接失败：{e}")
        if "401" in str(e) or "api_key" in str(e).lower():
            print("💡 可能是API密钥无效，请检查配置")
        elif "network" in str(e).lower() or "timeout" in str(e).lower():
            print("💡 可能是网络连接问题，请检查网络设置")
        return False

def main():
    print("🚀 开始AI总结功能测试\n")
    
    # 测试配置加载
    config_result = test_configuration()
    if not config_result:
        return
    
    success, summarizer, available_models = config_result
    
    # 测试分段功能
    if not test_segmentation():
        return
    
    # 测试API连接（选择第一个可用模型）
    first_model = list(available_models.keys())[0]
    if test_api_connection(summarizer, first_model):
        print(f"\n🎉 所有测试通过！可以使用 {available_models[first_model]} 进行总结。")
    else:
        print(f"\n⚠️  配置和分段功能正常，但API连接失败。请检查API密钥和网络连接。")
    
    print("\n📖 使用说明：")
    print("1. 运行 streamlit run src/app.py 启动应用")
    print("2. 上传音频文件或输入播客链接")
    print("3. 完成转录后使用AI总结功能")

if __name__ == "__main__":
    main() 