# skills/heroes/__init__.py
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class BaseSkillHandler:
    """기본 스킬 핸들러 클래스"""
    
    def __init__(self, skill_name: str, needs_target: bool = False):
        self.skill_name = skill_name
        self.needs_target = needs_target
    
    async def activate(self, interaction, target_id: str, duration: int):
        """스킬 활성화 (하위 클래스에서 구현)"""
        raise NotImplementedError
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 호출 (값 보정)"""
        return dice_value
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 호출"""
        pass
    
    async def on_round_end(self, channel_id: str, round_num: int):
        """라운드 종료 시 호출"""
        pass
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시 호출"""
        pass

# 스킬 핸들러 레지스트리 (메모리 효율성)
_skill_handlers: Dict[str, BaseSkillHandler] = {}

def register_skill_handler(skill_name: str, handler: BaseSkillHandler):
    """스킬 핸들러 등록"""
    _skill_handlers[skill_name] = handler
    logger.debug(f"스킬 핸들러 등록: {skill_name}")

def get_skill_handler(skill_name: str) -> Optional[BaseSkillHandler]:
    """스킬 핸들러 조회"""
    if skill_name not in _skill_handlers:
        _load_skill_handler(skill_name)
    
    return _skill_handlers.get(skill_name)

def _load_skill_handler(skill_name: str):
    """스킬 핸들러 동적 로딩"""
    skill_module_map = {
        "오닉셀": "onixel",
        "피닉스": "phoenix", 
        "오리븐": "oriven",
        "카론": "karon"
    }
    
    module_name = skill_module_map.get(skill_name)
    if not module_name:
        logger.warning(f"알 수 없는 스킬: {skill_name}")
        return
    
    try:
        # 동적 import (성능 최적화: 필요할 때만 로딩)
        module = __import__(f"skills.heroes.{module_name}", fromlist=[module_name])
        
        # 모듈에서 핸들러 가져오기
        handler_name = f"{module_name.title()}Handler"
        handler_class = getattr(module, handler_name, None)
        
        if handler_class:
            handler = handler_class()
            register_skill_handler(skill_name, handler)
            logger.info(f"스킬 핸들러 로딩 완료: {skill_name}")
        else:
            logger.error(f"핸들러 클래스를 찾을 수 없음: {handler_name}")
            
    except Exception as e:
        logger.error(f"스킬 핸들러 로딩 실패 {skill_name}: {e}")

def get_all_available_skills() -> list:
    """사용 가능한 모든 스킬 목록"""
    return ["오닉셀", "피닉스", "오리븐", "카론"]

# Phase 1에서 사용할 스킬들 미리 로딩 (선택적)
def preload_phase1_skills():
    """Phase 1 스킬들 미리 로딩"""
    for skill_name in get_all_available_skills():
        try:
            get_skill_handler(skill_name)
        except Exception as e:
            logger.error(f"Phase 1 스킬 미리 로딩 실패 {skill_name}: {e}")