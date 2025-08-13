# heroes/hwangya.py
"""황야 스킬 - 다중 행동"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class HwangyaSkill(BaseSkill):
    """황야 스킬 - 다중 행동 능력"""
    
    def __init__(self):
        super().__init__()
        self.name = "황야"
        self.description = {
            "user": "한 턴에 3가지 행동(공격/회복 조합)을 할 수 있습니다.",
            "monster": "한 턴에 2가지 행동(공격/회복 조합)을 할 수 있습니다."
        }
        self.skill_type = SkillType.SPECIAL
        self.max_duration = 5
        self.min_duration = 1
        self.action_counts = {
            "user": 3,
            "monster": 2
        }
        
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
        
        action_count = self.action_counts[caster_type]
        
        return {
            "success": True,
            "message": f"황야 스킬이 활성화되었습니다! {self.remaining_rounds}라운드 동안 한 턴에 {action_count}개 행동 가능",
            "duration": self.remaining_rounds,
            "effect": {
                "type": "multi_action",
                "action_count": action_count,
                "target": "self"
            }
        }
    
    def get_action_count(self) -> int:
        """현재 가능한 행동 횟수 반환"""
        if not self.active:
            return 1
        
        return self.action_counts.get(self.caster_type, 1)
    
    def get_available_actions(self) -> list:
        """사용 가능한 행동 조합 반환"""
        if not self.active:
            return ["공격", "회복"]
        
        action_count = self.get_action_count()
        
        if action_count == 2:
            return [
                ["공격", "공격"],
                ["공격", "회복"],
                ["회복", "회복"]
            ]
        elif action_count == 3:
            return [
                ["공격", "공격", "공격"],
                ["공격", "공격", "회복"],
                ["공격", "회복", "회복"],
                ["회복", "회복", "회복"]
            ]
        
        return ["공격", "회복"]
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status.update({
            "action_count": self.get_action_count(),
            "effect": f"한 턴에 {self.get_action_count()}개 행동"
        })
        return status