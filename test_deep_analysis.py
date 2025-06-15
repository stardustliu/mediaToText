#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度分析功能测试脚本
用于验证配置和API连接是否正常
"""

import yaml
import time
from src.summarize import AIModelClient, PodcastSummarizer

def load_config():
    """加载配置文件"""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ 加载配置文件失败：{e}")
        return None

def test_api_connection(config, model_key):
    """测试API连接"""
    print(f"\n🌐 测试 {model_key} API连接...")
    
    try:
        model_config = config['ai_models'][model_key]
        retry_config = config.get('retry', {})
        client = AIModelClient(model_config, retry_config)
        
        # 简单的测试消息
        test_messages = [{"role": "user", "content": "请简单回复'连接成功'"}]
        start_time = time.time()
        response = client.call_api(test_messages, "你是一个测试助手。")
        end_time = time.time()
        
        print(f"✅ API连接成功")
        print(f"📊 响应时间：{end_time - start_time:.2f}秒")
        print(f"📝 响应内容：{response[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ API连接失败：{e}")
        return False

def test_deep_analysis_simple(config, model_key):
    """测试简化的深度分析"""
    print(f"\n🧠 测试简化深度分析...")
    
    try:
        summarizer = PodcastSummarizer()
        
        # 简短的测试文本
        test_text = """
        这是一段测试播客内容。主持人谈到了人工智能的发展趋势，
        提到了机器学习在各个行业的应用。嘉宾分享了一些关于技术创新的观点，
        强调了数据安全和隐私保护的重要性。整个对话持续了大约30分钟。
        """
        
        print(f"📝 测试文本长度：{len(test_text)}字符")
        
        start_time = time.time()
        result = summarizer.deep_analysis(test_text, model_key)
        end_time = time.time()
        
        print(f"✅ 深度分析完成")
        print(f"📊 处理时间：{end_time - start_time:.2f}秒")
        print(f"📄 结果长度：{len(result)}字符")
        print(f"📝 结果预览：{result[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 深度分析失败：{e}")
        return False

def main():
    """主函数"""
    print("🚀 深度分析功能测试开始")
    print("=" * 50)
    
    # 1. 加载配置
    config = load_config()
    if not config:
        return
    
    print("✅ 配置文件加载成功")
    
    # 2. 检查可用的模型
    available_models = config.get('ai_models', {})
    model_keys = [key for key, value in available_models.items() 
                  if value.get('api_key') and value.get('api_key').strip()]
    
    if not model_keys:
        print("❌ 没有找到配置完整的模型")
        return
    
    print(f"📋 找到 {len(model_keys)} 个配置完整的模型：{', '.join(model_keys)}")
    
    # 3. 显示当前配置
    retry_config = config.get('retry', {})
    print(f"\n⚙️ 当前超时配置：{retry_config.get('timeout_seconds', 60)}秒")
    print(f"⚙️ 最大重试次数：{retry_config.get('max_attempts', 3)}")
    
    # 4. 测试每个模型
    for model_key in model_keys:
        print(f"\n{'='*20} 测试 {model_key} {'='*20}")
        
        # 测试API连接
        if test_api_connection(config, model_key):
            # 测试深度分析
            test_deep_analysis_simple(config, model_key)
        
        print()
    
    print("🎉 测试完成")
    print("\n💡 使用建议：")
    print("- 如果连接测试成功但深度分析失败，尝试:")
    print("  1. 进一步增加timeout_seconds（如300秒）")
    print("  2. 减少max_tokens设置")
    print("  3. 启用分块处理功能")
    print("- 如果连接测试就失败，请检查API密钥和网络连接")

if __name__ == "__main__":
    main() 