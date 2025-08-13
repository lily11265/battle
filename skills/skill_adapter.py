# skills/skill_adapter.py
"""
기존 시스템과 새로운 BaseSkill 시스템 간의 호환성 어댑터
"""

import logging
from typing import Dict, Any, Optional, List
from .heroes import get_skill_by_name, BaseSkill

logger = logging.getLogger(__name__)

class SkillAdapter:
    """기존 핸들러 시스템과 BaseSkill 간의 어댑터"""
    
    @staticmethod
    def convert_old_handler_to_baseskill(skill_name: str, handler_data: Dict) -> Optional[BaseSkill]:
        """기존 핸들러 데이터를 BaseSkill 인스턴스로 변환"""
        try:
            skill_class = get_skill_by_name(skill_name)
            if not skill_class:
                return None
            
            skill_instance = skill_class()
            
            # 기존 데이터 매핑
            if "user_id" in handler_data:
                skill_instance.caster_id = handler_data["user_id"]
            if "rounds_left" in handler_data:
                skill_instance.remaining_rounds = handler_data["rounds_left"]
            if "is_active" in handler_data:
                skill_instance.active = handler_data["is_active"]
            
            return skill_instance
            
        except Exception as e:
            logger.error(f"핸들러 변환 실패 ({skill_name}): {e}")
            return None
    
    @staticmethod
    def get_skill_priority(skill_name: str) -> int:
        """스킬 우선순위 반환 (기존 시스템 호환)"""
        priority_map = {
            # 즉시 적용 (최우선)
            "그림": 0,
            "피닉스": 1,
            
            # 강력한 변경 (높은 우선순위)
            "운명의주사위": 10,
            "콜폴드": 11,
            "제프로프": 12,
            
            # 고정값 설정
            "자보라": 20,
            "볼켄": 21,
            
            # 일반 버프/디버프
            "오닉셀": 30,
            "아젤론": 31,
            "소레인": 32,
            "에이로": 33,
            "오리븐": 34,
            "스트라보스": 35,
            
            # 특수 효과
            "카론": 40,
            "닉사라": 41,
            "비렐라": 42,
            "단목": 43,
            "제룬카": 44,
            
            # 소환/추가 행동
            "드레이언": 50,
            "리메스": 51,
            "황야": 52,
            
            # 지속 효과
            "반트로스": 60,
            "루센시아": 61,
            "스카넬": 62,
            
            # 메타 스킬
            "이그나": 70,
            "넥시스": 71,
        }
        
        return priority_map.get(skill_name, 100)
    
    @staticmethod
    def convert_skill_data_for_old_system(skill_instance: BaseSkill) -> Dict[str, Any]:
        """BaseSkill 인스턴스를 기존 시스템용 데이터로 변환"""
        try:
            status = skill_instance.get_status()
            if not status:
                return {}
            
            return {
                "name": skill_instance.name,
                "user_id": skill_instance.caster_id,
                "rounds_left": skill_instance.remaining_rounds,
                "is_active": skill_instance.active,
                "type": skill_instance.skill_type.value,
                "effect": status.get("effect", ""),
                "cooldown": skill_instance.current_cooldown
            }
            
        except Exception as e:
            logger.error(f"스킬 데이터 변환 실패: {e}")
            return {}
    
    @staticmethod
    async def apply_old_style_effect(skill_name: str, skill_data: Dict,
                                    user_id: str, dice_value: int) -> tuple[int, str]:
        """기존 스타일의 효과 적용 (하위 호환성)"""
        try:
            skill_class = get_skill_by_name(skill_name)
            if not skill_class:
                return dice_value, ""
            
            # 임시 인스턴스 생성
            temp_instance = skill_class()
            temp_instance.active = True
            temp_instance.caster_id = skill_data.get("user_id")
            temp_instance.remaining_rounds = skill_data.get("rounds_left", 0)
            
            # 효과 적용
            new_value = temp_instance.apply_effect(
                target=dice_value,
                effect_type="dice_modifier",
                user_id=user_id,
                dice_value=dice_value
            )
            
            message = ""
            if new_value != dice_value:
                message = f"{skill_name} 효과: {dice_value} → {new_value}"
            
            return new_value, message
            
        except Exception as e:
            logger.error(f"기존 스타일 효과 적용 실패: {e}")
            return dice_value, ""


class LegacySkillHandler:
    """기존 핸들러 인터페이스를 BaseSkill로 래핑"""
    
    def __init__(self, skill_instance: BaseSkill):
        self.skill = skill_instance
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict) -> int:
        """기존 on_dice_roll 인터페이스"""
        return self.skill.apply_effect(
            target=dice_value,
            effect_type="dice_modifier",
            user_id=user_id,
            dice_value=dice_value,
            **context
        )
    
    async def on_skill_start(self, channel_id: str, user_id: str, target_id: Optional[str] = None):
        """기존 on_skill_start 인터페이스"""
        result = await self.skill.activate(
            caster_type="user",
            duration=3,  # 기본값
            caster_id=user_id,
            target_user=target_id
        )
        return result
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """기존 on_skill_end 인터페이스"""
        self.skill.deactivate()
        return {"success": True}
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """기존 on_round_start 인터페이스"""
        message = self.skill.process_round()
        return {"message": message} if message else {}


def get_skill_handler(skill_name: str) -> Optional[LegacySkillHandler]:
    """기존 get_skill_handler 함수 호환성 래퍼"""
    skill_class = get_skill_by_name(skill_name)
    if skill_class:
        skill_instance = skill_class()
        return LegacySkillHandler(skill_instance)
    return None


def get_skill_priority(skill_name: str) -> int:
    """기존 get_skill_priority 함수 호환성 래퍼"""
    return SkillAdapter.get_skill_priority(skill_name)