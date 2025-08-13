# debug_config.py
import logging
import functools
import time
import asyncio
from typing import Any, Callable
import json
from datetime import datetime

class DebugConfig:
    """디버그 설정 관리 클래스"""
    def __init__(self):
        self.debug_enabled = False
        self.performance_tracking = False
        self.memory_tracking = False
        self.detailed_logging = False
        self.log_file = "minigame_debug.log"
        
    def toggle_debug(self):
        """디버그 모드 토글"""
        self.debug_enabled = not self.debug_enabled
        return self.debug_enabled
    
    def set_debug_level(self, level: str):
        """디버그 레벨 설정"""
        levels = {
            "OFF": logging.CRITICAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG
        }
        logging.getLogger().setLevel(levels.get(level, logging.INFO))

# 전역 디버그 설정
debug_config = DebugConfig()

def debug_log(category: str, message: str, data: Any = None):
    """조건부 디버그 로깅"""
    if not debug_config.debug_enabled:
        return
    
    logger = logging.getLogger(category)
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "message": message
    }
    
    if data is not None:
        log_entry["data"] = str(data)
    
    if debug_config.detailed_logging:
        logger.debug(json.dumps(log_entry, ensure_ascii=False))
    else:
        logger.debug(f"{category}: {message}")

def performance_tracker(func):
    """성능 추적 데코레이터"""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        if not debug_config.performance_tracking:
            return await func(*args, **kwargs)
        
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            end_time = time.perf_counter()
            debug_log("PERFORMANCE", f"{func.__name__} took {end_time - start_time:.4f}s")
            return result
        except Exception as e:
            end_time = time.perf_counter()
            debug_log("PERFORMANCE", f"{func.__name__} failed after {end_time - start_time:.4f}s: {e}")
            raise
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        if not debug_config.performance_tracking:
            return func(*args, **kwargs)
        
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            debug_log("PERFORMANCE", f"{func.__name__} took {end_time - start_time:.4f}s")
            return result
        except Exception as e:
            end_time = time.perf_counter()
            debug_log("PERFORMANCE", f"{func.__name__} failed after {end_time - start_time:.4f}s: {e}")
            raise
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper

def memory_tracker(obj_name: str):
    """메모리 사용량 추적"""
    if not debug_config.memory_tracking:
        return
    
    import sys
    import gc
    
    # 객체 크기 추정
    obj_count = len(gc.get_objects())
    debug_log("MEMORY", f"{obj_name} - Total objects: {obj_count}")