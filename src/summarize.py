import os
import re
import yaml
import requests
import json
import time
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

from progress_manager import ProgressManager, TaskProgress


class AIModelClient:
    """统一的AI模型客户端，支持OpenAI API风格的多种模型"""
    
    def __init__(self, model_config: Dict, retry_config: Dict = None):
        self.config = model_config
        self.base_url = model_config['base_url'].rstrip('/')
        self.api_key = model_config['api_key']
        self.model = model_config['model']
        self.max_tokens = model_config.get('max_tokens', 4000)
        self.temperature = model_config.get('temperature', 0.3)
        
        # 重试配置
        self.retry_config = retry_config or {}
        self.max_attempts = self.retry_config.get('max_attempts', 3)
        self.delay_seconds = self.retry_config.get('delay_seconds', 5)
        self.exponential_backoff = self.retry_config.get('exponential_backoff', True)
        self.timeout_seconds = self.retry_config.get('timeout_seconds', 60)
    
    def _is_anthropic_api(self) -> bool:
        """检查是否为Anthropic Claude API"""
        return 'anthropic.com' in self.base_url
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟时间"""
        if self.exponential_backoff:
            return self.delay_seconds * (2 ** (attempt - 1))
        return self.delay_seconds
    
    def call_api(self, messages: List[Dict], system_prompt: str = "") -> str:
        """调用AI API进行文本生成，包含重试机制"""
        last_error = None
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                headers = {
                    'Content-Type': 'application/json'
                }
                
                # 根据不同API设置认证头
                if self._is_anthropic_api():
                    headers['x-api-key'] = self.api_key
                    headers['anthropic-version'] = '2023-06-01'
                    
                    # Claude API格式
                    data = {
                        'model': self.model,
                        'max_tokens': self.max_tokens,
                        'temperature': self.temperature,
                        'messages': messages
                    }
                    if system_prompt:
                        data['system'] = system_prompt
                    
                    url = f"{self.base_url}/messages"
                else:
                    # OpenAI API格式
                    headers['Authorization'] = f'Bearer {self.api_key}'
                    
                    # 构建消息列表
                    api_messages = []
                    if system_prompt:
                        api_messages.append({"role": "system", "content": system_prompt})
                    api_messages.extend(messages)
                    
                    data = {
                        'model': self.model,
                        'messages': api_messages,
                        'max_tokens': self.max_tokens,
                        'temperature': self.temperature
                    }
                    
                    url = f"{self.base_url}/chat/completions"
                
                response = requests.post(url, headers=headers, json=data, timeout=self.timeout_seconds)
                response.raise_for_status()
                
                result = response.json()
                
                # 解析不同API的响应格式
                if self._is_anthropic_api():
                    return result['content'][0]['text']
                else:
                    return result['choices'][0]['message']['content']
                    
            except requests.exceptions.Timeout as e:
                last_error = f"请求超时 (第{attempt}次尝试): {str(e)}"
                
            except requests.exceptions.RequestException as e:
                # 检查是否为速率限制错误
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 429:  # 速率限制
                        last_error = f"API速率限制 (第{attempt}次尝试): {str(e)}"
                    elif e.response.status_code >= 500:  # 服务器错误
                        last_error = f"服务器错误 (第{attempt}次尝试): {str(e)}"
                    else:
                        # 客户端错误，通常不需要重试
                        raise Exception(f"API调用失败: {str(e)}")
                else:
                    last_error = f"网络错误 (第{attempt}次尝试): {str(e)}"
                    
            except KeyError as e:
                raise Exception(f"API响应格式错误: {str(e)}")
                
            except Exception as e:
                last_error = f"未知错误 (第{attempt}次尝试): {str(e)}"
            
            # 如果不是最后一次尝试，则等待后重试
            if attempt < self.max_attempts:
                delay = self._calculate_delay(attempt)
                st.info(f"第{attempt}次尝试失败，{delay:.1f}秒后重试... ({last_error})")
                time.sleep(delay)
        
        # 所有重试都失败了
        raise Exception(f"API调用失败，已重试{self.max_attempts}次: {last_error}")


class TextSegmenter:
    """智能文本分段器，基于主题进行分段"""
    
    def __init__(self, min_length: int = 300, max_length: int = 1500, overlap_ratio: float = 0.1):
        self.min_length = min_length
        self.max_length = max_length
        self.overlap_ratio = overlap_ratio
    
    def segment_by_topic(self, text: str) -> List[Dict]:
        """基于主题智能分段"""
        # 首先按段落分割
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        segments = []
        current_segment = ""
        current_length = 0
        segment_start_time = None
        
        for i, paragraph in enumerate(paragraphs):
            # 检测时间戳（用于播客转录）
            time_match = re.search(r'\[(\d{1,2}):(\d{2}):(\d{2})\]', paragraph)
            if time_match and not segment_start_time:
                segment_start_time = f"{time_match.group(1)}:{time_match.group(2)}:{time_match.group(3)}"
            
            paragraph_length = len(paragraph)
            
            # 检查是否为主题转换点
            is_topic_change = self._detect_topic_change(paragraph)
            
            # 分段条件：
            # 1. 达到最大长度
            # 2. 检测到主题转换且已达到最小长度
            # 3. 是最后一个段落
            should_split = (
                current_length + paragraph_length > self.max_length or
                (is_topic_change and current_length >= self.min_length) or
                i == len(paragraphs) - 1
            )
            
            if should_split and current_segment:
                # 添加当前段落到分段中
                if i < len(paragraphs) - 1:  # 不是最后一个段落
                    current_segment += "\n" + paragraph
                
                segments.append({
                    'content': current_segment.strip(),
                    'start_time': segment_start_time,
                    'length': len(current_segment),
                    'index': len(segments) + 1
                })
                
                # 重置并开始新分段
                if i < len(paragraphs) - 1:  # 不是最后一个段落
                    overlap_length = int(len(current_segment) * self.overlap_ratio)
                    current_segment = current_segment[-overlap_length:] + "\n" + paragraph
                    current_length = len(current_segment)
                    segment_start_time = None
                else:
                    # 最后一个段落，添加到当前段落
                    current_segment += "\n" + paragraph
                    segments[-1]['content'] = current_segment.strip()
                    segments[-1]['length'] = len(current_segment)
            else:
                # 继续添加到当前分段
                if current_segment:
                    current_segment += "\n" + paragraph
                else:
                    current_segment = paragraph
                current_length = len(current_segment)
        
        # 处理剩余内容
        if current_segment and not segments:
            segments.append({
                'content': current_segment.strip(),
                'start_time': segment_start_time,
                'length': len(current_segment),
                'index': 1
            })
        
        return segments
    
    def _detect_topic_change(self, paragraph: str) -> bool:
        """检测主题转换的简单规则"""
        # 主题转换指示词
        topic_indicators = [
            '接下来', '然后', '另外', '此外', '换个话题', '说到', 
            '谈到', '关于', '我们再来看', '下面', '现在', '最后',
            '总结', '总的来说', '综上'
        ]
        
        # 问答模式检测
        qa_patterns = [
            r'^[问题|提问|主持人|嘉宾][:：]',
            r'^Q[:：]',
            r'^A[:：]',
            r'那么.*问题是',
            r'你觉得.*吗[？?]',
            r'怎么.*看.*[？?]'
        ]
        
        paragraph_lower = paragraph.lower()
        
        # 检查主题指示词
        for indicator in topic_indicators:
            if indicator in paragraph_lower:
                return True
        
        # 检查问答模式
        for pattern in qa_patterns:
            if re.search(pattern, paragraph):
                return True
        
        return False


class PodcastSummarizer:
    """播客总结器主类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        if not self.config:
            return
            
        self.segmenter = TextSegmenter(
            min_length=self.config['summarization']['segmentation']['min_segment_length'],
            max_length=self.config['summarization']['segmentation']['max_segment_length'],
            overlap_ratio=self.config['summarization']['segmentation']['overlap_ratio']
        )
        
        # 初始化进度管理器
        self.progress_manager = ProgressManager(self.config)
        
        # 获取重试配置
        self.retry_config = self.config.get('retry', {})
        
        # 失败分段重试配置
        self.failed_segment_retry = {
            'max_attempts': 3,  # 失败分段最大重试次数
            'base_delay': 10,   # 基础延迟时间（秒）
            'max_delay': 60,    # 最大延迟时间（秒）
            'error_types': {    # 错误类型对应的重试策略
                'timeout': {'retry': True, 'delay_multiplier': 2},
                'rate_limit': {'retry': True, 'delay_multiplier': 3},
                'server_error': {'retry': True, 'delay_multiplier': 1.5},
                'network_error': {'retry': True, 'delay_multiplier': 1.2}
            }
        }
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            st.error(f"配置文件 {config_path} 不存在，请先创建配置文件")
            return {}
        except yaml.YAMLError as e:
            st.error(f"配置文件格式错误: {str(e)}")
            return {}
    
    def get_available_models(self) -> Dict[str, str]:
        """获取可用的AI模型列表"""
        models = {}
        for key, model_config in self.config.get('ai_models', {}).items():
            if model_config.get('api_key'):  # 只返回已配置API密钥的模型
                models[key] = model_config['name']
        return models
    
    def list_incomplete_tasks(self) -> List[TaskProgress]:
        """获取未完成的任务列表"""
        return self.progress_manager.list_incomplete_tasks()
    
    def create_new_task(self, media_title: str, model_key: str) -> TaskProgress:
        """创建新的总结任务"""
        task_id = self.progress_manager.generate_task_id(media_title)
        task = TaskProgress(task_id, media_title, model_key)
        self.progress_manager.save_task(task)
        return task
    
    def resume_task(self, task_id: str) -> Optional[TaskProgress]:
        """恢复已存在的任务"""
        return self.progress_manager.load_task(task_id)
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        return self.progress_manager.delete_task(task_id)
    
    def _should_retry_failed_segment(self, error_msg: str) -> Tuple[bool, float]:
        """判断是否应该重试失败的分段，并返回延迟时间"""
        error_msg = error_msg.lower()
        
        # 根据错误信息判断错误类型
        error_type = None
        if 'timeout' in error_msg or 'timed out' in error_msg:
            error_type = 'timeout'
        elif 'rate limit' in error_msg or 'too many requests' in error_msg:
            error_type = 'rate_limit'
        elif 'server error' in error_msg or '500' in error_msg:
            error_type = 'server_error'
        elif 'network' in error_msg or 'connection' in error_msg:
            error_type = 'network_error'
        
        if error_type and error_type in self.failed_segment_retry['error_types']:
            strategy = self.failed_segment_retry['error_types'][error_type]
            if strategy['retry']:
                # 计算延迟时间，使用指数退避
                delay = min(
                    self.failed_segment_retry['base_delay'] * strategy['delay_multiplier'],
                    self.failed_segment_retry['max_delay']
                )
                return True, delay
        
        return False, 0

    def _retry_failed_segments(self, client: AIModelClient, task: TaskProgress, progress_callback=None) -> None:
        """重试失败的分段"""
        if not task.failed_segments:
            return
        
        if progress_callback:
            progress_callback(0.8, f"正在重试 {len(task.failed_segments)} 个失败的分段...")
        
        # 按失败时间排序，优先处理最近失败的分段
        task.failed_segments.sort(key=lambda x: x.get('failed_at', ''), reverse=True)
        
        for failed_segment in task.failed_segments[:]:
            segment_index = failed_segment['index']
            error_msg = failed_segment['error']
            
            # 检查是否应该重试
            should_retry, delay = self._should_retry_failed_segment(error_msg)
            if not should_retry:
                continue
            
            # 等待延迟时间
            if delay > 0:
                time.sleep(delay)
            
            try:
                # 获取分段内容
                segment_content = self.segmenter.get_segment_content(segment_index)
                if not segment_content:
                    continue
                
                # 重试总结
                summary = self._summarize_segment(client, segment_content, segment_index)
                keywords = []
                
                # 提取关键词（如果启用）
                if self.config['summarization']['summary']['include_keywords']:
                    try:
                        keywords = self._extract_keywords(client, segment_content)
                    except Exception as e:
                        st.warning(f"第{segment_index}段关键词提取失败: {str(e)}")
                
                # 保存分段结果
                segment_data = {
                    'index': segment_index,
                    'original_length': len(segment_content),
                    'summary': summary,
                    'keywords': keywords
                }
                
                task.add_completed_segment(segment_data)
                # 从失败列表中移除
                task.failed_segments.remove(failed_segment)
                self.progress_manager.save_task(task)
                
                if progress_callback:
                    completed_percentage = len(task.completed_segments) / task.total_segments * 100
                    progress_callback(0.8 + (completed_percentage * 0.1), f"第 {segment_index} 段重试成功")
            
            except Exception as e:
                # 更新失败信息
                failed_segment['error'] = str(e)
                failed_segment['failed_at'] = datetime.now().isoformat()
                self.progress_manager.save_task(task)
                
                if progress_callback:
                    progress_callback(0.8, f"第 {segment_index} 段重试失败: {str(e)}")

    def summarize_transcript(self, text: str, model_key: str, progress_callback=None, task: TaskProgress = None) -> Dict:
        """对转录文本进行总结，支持断点续传"""
        if not self.config:
            raise Exception("配置文件加载失败")
        
        if model_key not in self.config['ai_models']:
            raise Exception(f"未找到模型配置: {model_key}")
        
        model_config = self.config['ai_models'][model_key]
        if not model_config.get('api_key'):
            raise Exception(f"模型 {model_key} 的API密钥未配置")
        
        client = AIModelClient(model_config, self.retry_config)
        
        # 如果没有传入任务，创建新任务
        if task is None:
            # 这里应该从外部传入media_title，暂时使用截取的文本前50字符
            media_title = text[:50].replace('\n', ' ').strip()
            task = self.create_new_task(media_title, model_key)
        
        try:
            # 1. 智能分段（如果还没有分段过）
            if task.total_segments == 0:
                if progress_callback:
                    progress_callback(0.05, "正在进行智能分段...")
                
                segments = self.segmenter.segment_by_topic(text)
                task.total_segments = len(segments)
                task.status = "segments_in_progress"
                self.progress_manager.save_task(task)
            else:
                # 重新分段（用于恢复任务）
                segments = self.segmenter.segment_by_topic(text)
            
            # 2. 分段总结（支持断点续传）
            remaining_segments = self.progress_manager.get_next_segments_to_process(task, segments)
            total_segments = len(segments)
            completed_count = len(task.completed_segments)
            
            if progress_callback:
                progress_callback(0.1, f"准备处理剩余 {len(remaining_segments)} 个分段...")
            
            for i, segment in enumerate(remaining_segments):
                try:
                    if progress_callback:
                        current_progress = 0.1 + ((completed_count + i) / total_segments) * 0.7  # 10%-80%用于分段总结
                        progress_callback(current_progress, f"正在总结第 {segment['index']}/{total_segments} 段...")
                    
                    # 总结单个分段
                    summary = self._summarize_segment(client, segment['content'], segment['index'])
                    keywords = []
                    
                    # 提取关键词（如果启用）
                    if self.config['summarization']['summary']['include_keywords']:
                        try:
                            keywords = self._extract_keywords(client, segment['content'])
                        except Exception as e:
                            st.warning(f"第{segment['index']}段关键词提取失败: {str(e)}")
                    
                    # 保存分段结果
                    segment_data = {
                        'index': segment['index'],
                        'start_time': segment.get('start_time'),
                        'original_length': segment['length'],
                        'summary': summary,
                        'keywords': keywords
                    }
                    
                    task.add_completed_segment(segment_data)
                    self.progress_manager.save_task(task)  # 立即保存进度
                    
                    if progress_callback:
                        completed_percentage = len(task.completed_segments) / total_segments * 100
                        progress_callback(current_progress, f"第 {segment['index']} 段完成 ({completed_percentage:.1f}%)")
                
                except Exception as e:
                    error_msg = str(e)
                    st.error(f"第{segment['index']}段总结失败: {error_msg}")
                    task.add_failed_segment(segment['index'], error_msg)
                    self.progress_manager.save_task(task)
                    
                    # 继续处理下一个分段，不中断整个流程
                    continue
            
            # 3. 重试失败的分段
            if task.failed_segments:
                self._retry_failed_segments(client, task, progress_callback)
            
            # 4. 检查分段总结是否完成
            all_segments_completed = len(task.completed_segments) == total_segments
            if not all_segments_completed:
                # 更新任务状态但不继续总体总结
                failed_count = len(task.failed_segments)
                completed_count = len(task.completed_segments)
                
                if failed_count > 0:
                    task.status = "segments_in_progress"  # 有失败的分段
                    if progress_callback:
                        progress_callback(0.8, f"分段总结部分完成: {completed_count}/{total_segments} 成功, {failed_count} 失败")
                else:
                    task.status = "segments_completed"
                    if progress_callback:
                        progress_callback(0.8, f"分段总结完成: {completed_count}/{total_segments}")
                
                self.progress_manager.save_task(task)
                
                # 返回部分结果
                return self._create_partial_result(task, text)
            
            # 5. 总体总结（只有在所有分段都完成时才执行）
            if task.overall_summary is None:
                try:
                    if progress_callback:
                        progress_callback(0.85, "正在生成总体总结...")
                    
                    task.overall_summary = self._generate_overall_summary(client, task.completed_segments, text)
                    self.progress_manager.save_task(task)
                    
                except Exception as e:
                    st.error(f"总体总结失败: {str(e)}")
                    task.status = "segments_completed"  # 分段完成但总体总结失败
                    self.progress_manager.save_task(task)
                    return self._create_partial_result(task, text)
            
            # 6. 主题分析（如果启用且还没完成）
            if task.topics is None and self.config['summarization']['summary']['include_topics']:
                try:
                    if progress_callback:
                        progress_callback(0.95, "正在进行主题分析...")
                    
                    task.topics = self._analyze_topics(client, text)
                    self.progress_manager.save_task(task)
                    
                except Exception as e:
                    st.warning(f"主题分析失败: {str(e)}")
                    task.topics = []  # 设置为空列表表示已尝试过
                    self.progress_manager.save_task(task)
            
            # 7. 完成任务
            task.status = "overall_completed"
            self.progress_manager.save_task(task)
            
            if progress_callback:
                progress_callback(1.0, "总结完成！")
            
            return self._create_final_result(task, text)
            
        except Exception as e:
            # 保存错误信息
            task.error_info = str(e)
            task.status = "failed"
            self.progress_manager.save_task(task)
            raise e
    
    def _create_partial_result(self, task: TaskProgress, original_text: str) -> Dict:
        """创建部分结果（用于分段总结完成但总体总结未完成的情况）"""
        return {
            'segments': task.completed_segments,
            'overall_summary': task.overall_summary or "总体总结尚未完成，请继续任务以生成完整总结",
            'topics': task.topics or [],
            'metadata': {
                'total_segments': task.total_segments,
                'completed_segments_count': len(task.completed_segments),
                'failed_segments_count': len(task.failed_segments),
                'original_length': len(original_text),
                'model_used': self.config['ai_models'][task.model_key]['name'],
                'generated_at': task.updated_at,
                'task_id': task.task_id,
                'progress_percentage': task.get_progress_percentage(),
                'status': task.status,
                'is_partial': True
            }
        }
    
    def _create_final_result(self, task: TaskProgress, original_text: str) -> Dict:
        """创建最终结果"""
        return {
            'segments': task.completed_segments,
            'overall_summary': task.overall_summary,
            'topics': task.topics or [],
            'metadata': {
                'total_segments': task.total_segments,
                'completed_segments_count': len(task.completed_segments),
                'failed_segments_count': len(task.failed_segments),
                'original_length': len(original_text),
                'model_used': self.config['ai_models'][task.model_key]['name'],
                'generated_at': task.updated_at,
                'task_id': task.task_id,
                'progress_percentage': 100.0,
                'status': task.status,
                'is_partial': False
            }
        }
    
    def _summarize_segment(self, client: AIModelClient, content: str, segment_index: int) -> str:
        """总结单个分段"""
        system_prompt = """你是一个专业的文本总结专家。请对给定的播客转录片段进行简洁总结。
要求：
1. 用1-2句话概括主要内容
2. 保留关键信息和观点
3. 语言简洁明了
4. 保持中文输出"""
        
        messages = [{
            "role": "user",
            "content": f"请总结以下播客片段（第{segment_index}段）：\n\n{content}"
        }]
        
        return client.call_api(messages, system_prompt)
    
    def _extract_keywords(self, client: AIModelClient, content: str) -> List[str]:
        """提取关键词"""
        system_prompt = """你是一个关键词提取专家。请从给定文本中提取3-5个最重要的关键词。
要求：
1. 只输出关键词，用逗号分隔
2. 关键词应该是名词或专业术语
3. 按重要性排序"""
        
        messages = [{
            "role": "user",
            "content": f"请从以下文本中提取关键词：\n\n{content}"
        }]
        
        try:
            result = client.call_api(messages, system_prompt)
            return [kw.strip() for kw in result.split(',') if kw.strip()]
        except:
            return []
    
    def _generate_overall_summary(self, client: AIModelClient, segment_summaries: List[Dict], original_text: str) -> str:
        """生成总体总结"""
        summaries_text = "\n".join([f"{i+1}. {summary['summary']}" for i, summary in enumerate(segment_summaries)])
        
        system_prompt = """你是一个专业的内容总结专家。基于各个分段的总结，生成一个整体的综合总结。
要求：
1. 200-300字的总结
2. 概括全文的主要主题和观点
3. 保持逻辑清晰，结构完整
4. 突出最重要的见解和结论
5. 使用中文输出"""
        
        messages = [{
            "role": "user",
            "content": f"基于以下分段总结，请生成一个整体总结：\n\n{summaries_text}"
        }]
        
        return client.call_api(messages, system_prompt)
    
    def _analyze_topics(self, client: AIModelClient, content: str) -> List[str]:
        """分析主要主题"""
        system_prompt = """你是一个主题分析专家。请分析给定文本的主要主题。
要求：
1. 识别3-5个主要主题
2. 每个主题用简短的词组表示
3. 按重要性排序
4. 只输出主题列表，用换行符分隔"""
        
        # 为避免文本过长，取前2000字进行主题分析
        content_sample = content[:2000] if len(content) > 2000 else content
        
        messages = [{
            "role": "user",
            "content": f"请分析以下文本的主要主题：\n\n{content_sample}"
        }]
        
        try:
            result = client.call_api(messages, system_prompt)
            return [topic.strip() for topic in result.split('\n') if topic.strip()]
        except:
            return []
    
    def deep_analysis(self, text: str, model_key: str) -> str:
        """基于prompt.txt进行深度分析，支持分块处理"""
        # 首先检查prompt.txt文件是否存在（优先级最高）
        prompt_file = "prompt.txt"  # 默认路径
        
        # 如果配置文件存在且有自定义路径，则使用配置的路径
        if (self.config and 
            'advanced_features' in self.config and 
            'deep_analysis' in self.config['advanced_features'] and 
            'prompt_file_path' in self.config['advanced_features']['deep_analysis']):
            prompt_file = self.config['advanced_features']['deep_analysis']['prompt_file_path']
        
        # 检查prompt文件是否存在
        if not os.path.exists(prompt_file):
            raise Exception(f"深度分析模板文件不存在：{prompt_file}")
        
        # 检查配置文件中的启用设置（如果存在配置）
        if (self.config and 
            'advanced_features' in self.config and 
            'deep_analysis' in self.config['advanced_features'] and 
            'enabled' in self.config['advanced_features']['deep_analysis'] and 
            not self.config['advanced_features']['deep_analysis']['enabled']):
            raise Exception("深度分析功能在配置文件中被禁用，如需使用请在config.yaml中设置 advanced_features.deep_analysis.enabled: true")
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                custom_prompt = f.read()
        except Exception as e:
            raise Exception(f"读取深度分析模板文件失败：{str(e)}")
        
        if not custom_prompt.strip():
            raise Exception("深度分析模板文件内容为空")
        
        model_config = self.config['ai_models'][model_key]
        client = AIModelClient(model_config, self.retry_config)
        
        # 检查是否启用分块处理
        enable_chunking = (self.config and 
                          'advanced_features' in self.config and 
                          'deep_analysis' in self.config['advanced_features'] and 
                          self.config['advanced_features']['deep_analysis'].get('enable_chunking', False))
        
        chunk_size = (self.config and 
                     'advanced_features' in self.config and 
                     'deep_analysis' in self.config['advanced_features'] and 
                     self.config['advanced_features']['deep_analysis'].get('chunk_size', 3000))
        
        # 如果文本较长且启用分块处理
        if enable_chunking and len(text) > chunk_size:
            st.info(f"💡 文本较长（{len(text)}字符），将采用分块处理以提高成功率...")
            
            # 将文本分块
            chunks = []
            words = text.split()
            current_chunk = []
            current_length = 0
            
            for word in words:
                word_length = len(word)
                if current_length + word_length > chunk_size and current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = [word]
                    current_length = word_length
                else:
                    current_chunk.append(word)
                    current_length += word_length
            
            if current_chunk:
                chunks.append(' '.join(current_chunk))
            
            st.info(f"📊 文本已分为 {len(chunks)} 块进行处理")
            
            # 处理每个块
            chunk_results = []
            for i, chunk in enumerate(chunks):
                try:
                    st.info(f"🔄 正在处理第 {i+1}/{len(chunks)} 块...")
                    
                    messages = [{
                        "role": "user",
                        "content": f"请对以下播客内容片段进行分析，这是第{i+1}部分，共{len(chunks)}部分：\n\n【分析指导】\n{custom_prompt}\n\n【播客内容片段】\n{chunk}"
                    }]
                    
                    chunk_result = client.call_api(messages, f"你是一个专业的内容分析专家。这是多段内容中的第{i+1}段，请按照指导原则进行分析。")
                    chunk_results.append(f"## 第{i+1}部分分析\n\n{chunk_result}")
                    
                except Exception as e:
                    st.warning(f"⚠️ 第 {i+1} 块处理失败：{str(e)}")
                    chunk_results.append(f"## 第{i+1}部分分析\n\n[处理失败: {str(e)}]")
            
            # 合并结果
            if chunk_results:
                final_result = "\n\n".join(chunk_results)
                
                # 如果所有块都处理成功，尝试生成整体总结
                if len([r for r in chunk_results if "[处理失败" not in r]) == len(chunks):
                    try:
                        st.info("🔄 正在生成整体总结...")
                        summary_messages = [{
                            "role": "user",
                            "content": f"请基于以下各部分的分析，生成一篇完整统一的深度分析文章：\n\n{final_result}"
                        }]
                        
                        overall_summary = client.call_api(summary_messages, "你是一个专业的内容整合专家，请将分段分析整合为一篇连贯的完整文章。")
                        return overall_summary
                        
                    except Exception as e:
                        st.warning(f"⚠️ 整体总结生成失败，返回分块结果：{str(e)}")
                        return final_result
                else:
                    return final_result
            else:
                raise Exception("所有分块处理都失败了")
        else:
            # 正常处理（不分块）
            messages = [{
                "role": "user",
                "content": f"请根据以下指导原则对播客内容进行深度分析：\n\n【分析指导】\n{custom_prompt}\n\n【播客内容】\n{text}"
            }]
            
            return client.call_api(messages, "你是一个专业的内容分析专家，请严格按照给定的指导原则进行分析。")
    
    def export_summary(self, summary_data: Dict, format_type: str, filename: str) -> str:
        """导出总结到不同格式"""
        if format_type == "markdown":
            return self._export_to_markdown(summary_data, filename)
        elif format_type == "pdf":
            return self._export_to_pdf(summary_data, filename)
        elif format_type == "txt":
            return self._export_to_txt(summary_data, filename)
        else:
            raise ValueError(f"不支持的导出格式: {format_type}")
    
    def _export_to_markdown(self, summary_data: Dict, filename: str) -> str:
        """导出为Markdown格式"""
        md_content = f"""# 播客总结报告

## 基本信息
- **生成时间**: {summary_data['metadata']['generated_at']}
- **使用模型**: {summary_data['metadata']['model_used']}
- **分段数量**: {summary_data['metadata']['total_segments']}
- **原文长度**: {summary_data['metadata']['original_length']}字

## 总体总结

{summary_data['overall_summary']}

## 主要主题
"""
        
        if summary_data['topics']:
            for i, topic in enumerate(summary_data['topics'], 1):
                md_content += f"{i}. {topic}\n"
        else:
            md_content += "暂无主题分析\n"
        
        md_content += "\n## 分段总结\n\n"
        
        for segment in summary_data['segments']:
            md_content += f"### 第{segment['index']}段"
            if segment['start_time']:
                md_content += f" ({segment['start_time']})"
            md_content += "\n\n"
            md_content += f"{segment['summary']}\n\n"
            
            if segment['keywords']:
                md_content += f"**关键词**: {', '.join(segment['keywords'])}\n\n"
        
        # 保存文件
        output_path = f"{filename}_summary.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return output_path
    
    def _export_to_txt(self, summary_data: Dict, filename: str) -> str:
        """导出为纯文本格式"""
        txt_content = f"""播客总结报告

基本信息：
生成时间: {summary_data['metadata']['generated_at']}
使用模型: {summary_data['metadata']['model_used']}
分段数量: {summary_data['metadata']['total_segments']}
原文长度: {summary_data['metadata']['original_length']}字

总体总结：
{summary_data['overall_summary']}

主要主题：
"""
        
        if summary_data['topics']:
            for i, topic in enumerate(summary_data['topics'], 1):
                txt_content += f"{i}. {topic}\n"
        else:
            txt_content += "暂无主题分析\n"
        
        txt_content += "\n分段总结：\n\n"
        
        for segment in summary_data['segments']:
            txt_content += f"第{segment['index']}段"
            if segment['start_time']:
                txt_content += f" ({segment['start_time']})"
            txt_content += "：\n"
            txt_content += f"{segment['summary']}\n"
            
            if segment['keywords']:
                txt_content += f"关键词: {', '.join(segment['keywords'])}\n"
            txt_content += "\n"
        
        # 保存文件
        output_path = f"{filename}_summary.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        
        return output_path
    
    def _export_to_pdf(self, summary_data: Dict, filename: str) -> str:
        """导出为PDF格式"""
        output_path = f"{filename}_summary.pdf"
        
        # 创建PDF文档
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # 尝试注册中文字体（如果可用）
        try:
            # 这里可以根据系统添加中文字体路径
            # pdfmetrics.registerFont(TTFont('SimSun', 'SimSun.ttf'))
            pass
        except:
            pass
        
        # 标题
        title = Paragraph("播客总结报告", styles['Title'])
        story.append(title)
        story.append(Spacer(1, 12))
        
        # 基本信息
        info_text = f"""生成时间: {summary_data['metadata']['generated_at']}<br/>
使用模型: {summary_data['metadata']['model_used']}<br/>
分段数量: {summary_data['metadata']['total_segments']}<br/>
原文长度: {summary_data['metadata']['original_length']}字"""
        
        info = Paragraph(info_text, styles['Normal'])
        story.append(info)
        story.append(Spacer(1, 12))
        
        # 总体总结
        summary_title = Paragraph("总体总结", styles['Heading2'])
        story.append(summary_title)
        summary_content = Paragraph(summary_data['overall_summary'], styles['Normal'])
        story.append(summary_content)
        story.append(Spacer(1, 12))
        
        # 主要主题
        if summary_data['topics']:
            topics_title = Paragraph("主要主题", styles['Heading2'])
            story.append(topics_title)
            topics_text = "<br/>".join([f"{i}. {topic}" for i, topic in enumerate(summary_data['topics'], 1)])
            topics_content = Paragraph(topics_text, styles['Normal'])
            story.append(topics_content)
            story.append(Spacer(1, 12))
        
        # 分段总结
        segments_title = Paragraph("分段总结", styles['Heading2'])
        story.append(segments_title)
        
        for segment in summary_data['segments']:
            segment_title_text = f"第{segment['index']}段"
            if segment['start_time']:
                segment_title_text += f" ({segment['start_time']})"
            
            segment_title = Paragraph(segment_title_text, styles['Heading3'])
            story.append(segment_title)
            
            segment_content = Paragraph(segment['summary'], styles['Normal'])
            story.append(segment_content)
            
            if segment['keywords']:
                keywords_text = f"关键词: {', '.join(segment['keywords'])}"
                keywords = Paragraph(keywords_text, styles['Normal'])
                story.append(keywords)
            
            story.append(Spacer(1, 12))
        
        # 构建PDF
        doc.build(story)
        return output_path 