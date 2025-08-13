# heroes/oriven.py
"""오리븐 스킬 - 주사위 값 보정"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class OrivenSkill(BaseSkill):
    """오리븐 스킬 - 주사위 보정"""
    
    def __init__(self):
        super().__init__()
        self.name = "오리븐"
        self.description = {
            "user": "모든 유저의 주사위 값에 +10 보정을 줍니다.",
            "monster": "모든 유저의 주사위 값에 -10 보정을 줍니다."
        }
        self.skill_type = SkillType.SUPPORT
        self.max_duration = 5
        self.min_duration = 1
        self.user_modifier = 10
        self.monster_modifier = -10
        
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
        
        modifier = self.user_modifier if caster_type == "user" else self.monster_modifier
        sign = "+" if modifier > 0 else ""
        
        return {
            "success": True,
            "message": f"오리븐 스킬 활성화! {self.remaining_rounds}라운드 동안 모든 유저 주사위 {sign}{modifier}",
            "duration": self.remaining_rounds,
            "effect": {
                "type": "dice_modifier",
                "target": "all_users",
                "value": modifier
            }
        }
    
    def apply_dice_modifier(self, original_value: int, is_user: bool) -> int:
        """주사위 값 수정"""
        if not self.active or not is_user:
            return original_value
        
        modifier = self.user_modifier if self.caster_type == "user" else self.monster_modifier
        modified_value = original_value + modifier
        
        # 0~100 범위 제한
        return max(0, min(100, modified_value))
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        modifier = self.user_modifier if self.caster_type == "user" else self.monster_modifier
        sign = "+" if modifier > 0 else ""
        
        status.update({
            "modifier": modifier,
            "effect": f"유저 주사위 {sign}{modifier}"
        })
        return status