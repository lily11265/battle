# heroes/stravos.py
"""스트라보스 스킬 - 강화 효과"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class StrabosSkill(BaseSkill):
    """스트라보스 스킬 - 강력한 버프/디버프"""
    
    def __init__(self):
        super().__init__()
        self.name = "스트라보스"
        self.description = {
            "user": "모든 유저의 주사위에 +20 보정을 줍니다.",
            "monster": "공격 주사위 +30, 모든 유저 주사위 -15 보정"
        }
        self.skill_type = SkillType.SPECIAL
        self.max_duration = 5
        self.min_duration = 1
        self.monster_attack_bonus = 30
        self.monster_user_debuff = -15
        self.user_team_buff = 20
        
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
        
        if caster_type == "monster":
            return {
                "success": True,
                "message": f"스트라보스 발동! {self.remaining_rounds}라운드 동안 강화",
                "duration": self.remaining_rounds,
                "effect": {
                    "type": "strabos_buff",
                    "monster_attack": self.monster_attack_bonus,
                    "user_debuff": self.monster_user_debuff
                },
                "details": [
                    f"몬스터 공격 주사위 +{self.monster_attack_bonus}",
                    f"모든 유저 주사위 {self.monster_user_debuff}"
                ]
            }
        else:
            return {
                "success": True,
                "message": f"스트라보스 발동! {self.remaining_rounds}라운드 동안 팀 버프",
                "duration": self.remaining_rounds,
                "effect": {
                    "type": "team_buff",
                    "value": self.user_team_buff
                },
                "details": [
                    f"모든 유저 주사위 +{self.user_team_buff}"
                ]
            }
    
    def get_dice_modifier(self, entity_type: str, dice_type: str = "all") -> int:
        """주사위 수정값 반환"""
        if not self.active:
            return 0
        
        if self.caster_type == "monster":
            if entity_type == "monster" and dice_type == "attack":
                return self.monster_attack_bonus
            elif entity_type == "user":
                return self.monster_user_debuff
        else:
            if entity_type == "user":
                return self.user_team_buff
        
        return 0
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        
        if self.caster_type == "monster":
            status["effects"] = {
                "monster_attack": f"+{self.monster_attack_bonus}",
                "user_dice": f"{self.monster_user_debuff}"
            }
        else:
            status["effects"] = {
                "user_dice": f"+{self.user_team_buff}"
            }
        
        return status