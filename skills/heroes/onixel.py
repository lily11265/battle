# heroes/onixel.py
"""오닉셀 스킬 - 주사위 값 +50 보정"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class OnikselSkill(BaseSkill):
    """오닉셀 스킬 - 주사위 값 강화"""
    
    def __init__(self):
        super().__init__()
        self.name = "오닉셀"
        self.description = {
            "user": "모든 주사위 값에 +50 보정을 받습니다.",
            "monster": "모든 주사위 값에 +50 보정을 받습니다."
        }
        self.skill_type = SkillType.OFFENSIVE
        self.max_duration = 5
        self.min_duration = 1
        self.dice_bonus = 50
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        # 지속시간 검증
        duration_check = self.validate_duration(duration)
        if not duration_check["valid"]:
            return {
                "success": False,
                "message": duration_check["message"]
            }
        
        # 스킬 활성화
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration_check["duration"]
        self.total_uses += 1
        
        return {
            "success": True,
            "message": f"오닉셀 스킬이 활성화되었습니다! {self.remaining_rounds}라운드 동안 모든 주사위에 +{self.dice_bonus} 보정",
            "duration": self.remaining_rounds,
            "effect": {
                "type": "dice_modifier",
                "value": self.dice_bonus,
                "target": "self"
            }
        }
    
    def apply_dice_modifier(self, original_value: int, dice_type: str) -> int:
        """주사위 값 수정"""
        if not self.active:
            return original_value
        
        modified_value = original_value + self.dice_bonus
        return min(modified_value, 150)  # 최대값 100 제한
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status.update({
            "dice_bonus": self.dice_bonus,
            "effect": f"주사위 +{self.dice_bonus}"
        })
        return status