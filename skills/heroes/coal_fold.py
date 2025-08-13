# heroes/coal_fold.py
"""콜폴드 스킬 - 방어 강화"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class CallFoldSkill(BaseSkill):
    """콜폴드 스킬 - 강력한 방어"""
    
    def __init__(self):
        super().__init__()
        self.name = "콜폴드"
        self.description = {
            "user": "모든 유저의 방어 주사위에 +15 보정을 줍니다.",
            "monster": "방어력 증가 및 받는 데미지 30% 감소"
        }
        self.skill_type = SkillType.DEFENSIVE
        self.max_duration = 5
        self.min_duration = 1
        self.user_defense_bonus = 15
        self.monster_defense_bonus = 30
        self.damage_reduction = 0.3  # 30% 감소
        
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
                "message": f"콜폴드 발동! {self.remaining_rounds}라운드 동안 강력한 방어",
                "duration": self.remaining_rounds,
                "effect": {
                    "type": "defense_enhancement",
                    "defense_bonus": self.monster_defense_bonus,
                    "damage_reduction": self.damage_reduction
                },
                "details": [
                    f"방어 주사위 +{self.monster_defense_bonus}",
                    f"받는 데미지 {int(self.damage_reduction * 100)}% 감소"
                ]
            }
        else:
            return {
                "success": True,
                "message": f"콜폴드 발동! {self.remaining_rounds}라운드 동안 팀 방어 강화",
                "duration": self.remaining_rounds,
                "effect": {
                    "type": "team_defense",
                    "value": self.user_defense_bonus
                },
                "details": [
                    f"모든 유저 방어 주사위 +{self.user_defense_bonus}"
                ]
            }
    
    def get_defense_modifier(self, entity_type: str) -> int:
        """방어 주사위 수정값"""
        if not self.active:
            return 0
        
        if self.caster_type == "monster" and entity_type == "monster":
            return self.monster_defense_bonus
        elif self.caster_type == "user" and entity_type == "user":
            return self.user_defense_bonus
        
        return 0
    
    def calculate_damage_reduction(self, original_damage: int, target_type: str) -> int:
        """데미지 감소 계산"""
        if not self.active:
            return original_damage
        
        if self.caster_type == "monster" and target_type == "monster":
            reduced_damage = int(original_damage * (1 - self.damage_reduction))
            return reduced_damage
        
        return original_damage
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        
        if self.caster_type == "monster":
            status["effects"] = {
                "defense_bonus": f"+{self.monster_defense_bonus}",
                "damage_reduction": f"{int(self.damage_reduction * 100)}%"
            }
        else:
            status["effects"] = {
                "team_defense": f"+{self.user_defense_bonus}"
            }
        
        return status