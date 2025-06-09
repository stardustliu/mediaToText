import os
import json
import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import streamlit as st


class TaskProgress:
    """任务进度数据类"""
    
    def __init__(self, task_id: str, media_title: str, model_key: str):
        self.task_id = task_id
        self.media_title = media_title
        self.model_key = model_key
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.total_segments = 0
        self.completed_segments = []
        self.failed_segments = []
        self.overall_summary = None
        self.topics = None
        self.status = "initialized"  # initialized, segments_in_progress, segments_completed, overall_completed, failed
        self.error_info = None
    
    def to_dict(self) -> Dict:
        """转换为字典格式用于JSON序列化"""
        return {
            "task_id": self.task_id,
            "media_title": self.media_title,
            "model_key": self.model_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_segments": self.total_segments,
            "completed_segments": self.completed_segments,
            "failed_segments": self.failed_segments,
            "overall_summary": self.overall_summary,
            "topics": self.topics,
            "status": self.status,
            "error_info": self.error_info
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TaskProgress':
        """从字典创建TaskProgress实例"""
        task = cls(data["task_id"], data["media_title"], data["model_key"])
        task.created_at = data.get("created_at", task.created_at)
        task.updated_at = data.get("updated_at", task.updated_at)
        task.total_segments = data.get("total_segments", 0)
        task.completed_segments = data.get("completed_segments", [])
        task.failed_segments = data.get("failed_segments", [])
        task.overall_summary = data.get("overall_summary")
        task.topics = data.get("topics")
        task.status = data.get("status", "initialized")
        task.error_info = data.get("error_info")
        return task
    
    def get_progress_percentage(self) -> float:
        """获取进度百分比"""
        if self.total_segments == 0:
            return 0.0
        return len(self.completed_segments) / self.total_segments * 100
    
    def is_segment_completed(self, segment_index: int) -> bool:
        """检查指定分段是否已完成"""
        return any(s["index"] == segment_index for s in self.completed_segments)
    
    def add_completed_segment(self, segment_data: Dict):
        """添加已完成的分段"""
        segment_data["completed_at"] = datetime.now().isoformat()
        # 避免重复添加
        if not self.is_segment_completed(segment_data["index"]):
            self.completed_segments.append(segment_data)
        self.updated_at = datetime.now().isoformat()
    
    def add_failed_segment(self, segment_index: int, error: str):
        """添加失败的分段"""
        failed_info = {
            "index": segment_index,
            "error": error,
            "failed_at": datetime.now().isoformat()
        }
        # 避免重复添加
        if not any(s["index"] == segment_index for s in self.failed_segments):
            self.failed_segments.append(failed_info)
        self.updated_at = datetime.now().isoformat()


class ProgressManager:
    """进度管理器，负责任务状态的保存、恢复和管理"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.progress_dir = config.get("progress", {}).get("save_directory", "progress")
        self.auto_save = config.get("progress", {}).get("auto_save", True)
        self.keep_days = config.get("progress", {}).get("keep_completed_tasks", 7)
        self.cleanup_enabled = config.get("progress", {}).get("task_cleanup_enabled", True)
        
        # 确保进度目录存在
        Path(self.progress_dir).mkdir(exist_ok=True)
    
    def generate_task_id(self, media_title: str) -> str:
        """生成任务ID: 媒体标题 + UUID"""
        # 清理标题中的特殊字符
        clean_title = "".join(c for c in media_title if c.isalnum() or c in (' ', '-', '_')).strip()
        clean_title = clean_title.replace(' ', '_')[:50]  # 限制长度
        task_uuid = str(uuid.uuid4())[:8]  # 使用前8位UUID
        return f"{clean_title}_{task_uuid}"
    
    def get_task_file_path(self, task_id: str) -> str:
        """获取任务文件路径"""
        return os.path.join(self.progress_dir, f"{task_id}.json")
    
    def save_task(self, task: TaskProgress) -> bool:
        """保存任务进度"""
        try:
            if not self.auto_save:
                return True
            
            file_path = self.get_task_file_path(task.task_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            st.error(f"保存任务进度失败: {str(e)}")
            return False
    
    def load_task(self, task_id: str) -> Optional[TaskProgress]:
        """加载任务进度"""
        try:
            file_path = self.get_task_file_path(task_id)
            if not os.path.exists(file_path):
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return TaskProgress.from_dict(data)
        except Exception as e:
            st.error(f"加载任务进度失败: {str(e)}")
            return None
    
    def list_incomplete_tasks(self) -> List[TaskProgress]:
        """列出所有未完成的任务"""
        incomplete_tasks = []
        
        if not os.path.exists(self.progress_dir):
            return incomplete_tasks
        
        try:
            for filename in os.listdir(self.progress_dir):
                if filename.endswith('.json'):
                    task_id = filename[:-5]  # 去掉.json后缀
                    task = self.load_task(task_id)
                    if task and task.status not in ["overall_completed"]:
                        incomplete_tasks.append(task)
            
            # 按更新时间排序，最新的在前
            incomplete_tasks.sort(key=lambda x: x.updated_at, reverse=True)
            
        except Exception as e:
            st.error(f"列出未完成任务失败: {str(e)}")
        
        return incomplete_tasks
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务文件"""
        try:
            file_path = self.get_task_file_path(task_id)
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception as e:
            st.error(f"删除任务失败: {str(e)}")
            return False
    
    def cleanup_old_tasks(self) -> int:
        """清理过期的已完成任务"""
        if not self.cleanup_enabled:
            return 0
        
        cleaned_count = 0
        cutoff_date = datetime.now() - timedelta(days=self.keep_days)
        
        try:
            if not os.path.exists(self.progress_dir):
                return 0
            
            for filename in os.listdir(self.progress_dir):
                if filename.endswith('.json'):
                    task_id = filename[:-5]
                    task = self.load_task(task_id)
                    
                    if task and task.status == "overall_completed":
                        updated_time = datetime.fromisoformat(task.updated_at)
                        if updated_time < cutoff_date:
                            if self.delete_task(task_id):
                                cleaned_count += 1
            
        except Exception as e:
            st.error(f"清理任务失败: {str(e)}")
        
        return cleaned_count
    
    def get_next_segments_to_process(self, task: TaskProgress, segments: List[Dict]) -> List[Dict]:
        """获取下一批需要处理的分段"""
        remaining_segments = []
        
        for segment in segments:
            segment_index = segment["index"]
            
            # 跳过已完成的分段
            if task.is_segment_completed(segment_index):
                continue
            
            # 包含失败的分段（用于重试）
            remaining_segments.append(segment)
        
        return remaining_segments
    
    def create_summary_result_from_task(self, task: TaskProgress) -> Dict:
        """从任务进度创建总结结果"""
        return {
            'segments': task.completed_segments,
            'overall_summary': task.overall_summary or "总体总结尚未完成",
            'topics': task.topics or [],
            'metadata': {
                'total_segments': task.total_segments,
                'completed_segments_count': len(task.completed_segments),
                'original_length': 0,  # 这个值需要从原始文本获取
                'model_used': task.model_key,
                'generated_at': task.updated_at,
                'task_id': task.task_id,
                'progress_percentage': task.get_progress_percentage()
            }
        }
    
    def format_task_display_info(self, task: TaskProgress) -> Dict[str, str]:
        """格式化任务显示信息"""
        completed_count = len(task.completed_segments)
        total_count = task.total_segments
        progress_pct = task.get_progress_percentage()
        
        status_map = {
            "initialized": "已初始化",
            "segments_in_progress": "分段总结中",
            "segments_completed": "分段完成",
            "overall_completed": "全部完成",
            "failed": "失败"
        }
        
        return {
            "title": task.media_title,
            "progress": f"{completed_count}/{total_count} 段 ({progress_pct:.1f}%)",
            "status": status_map.get(task.status, task.status),
            "updated": datetime.fromisoformat(task.updated_at).strftime("%Y-%m-%d %H:%M"),
            "model": task.model_key
        } 