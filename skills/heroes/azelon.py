# heroes/azelon.py
"""아젤론 영웅 스킬 - 주사위 버프 및 자동 부활"""

from typing import Dict, Any, Optional
from .base import BaseSkill, SkillType

class AzelonSkill(BaseSkill):
    """아젤론 스킬 - 주사위 버프 및 자동 부활"""
    
    def __init__(self):
        super().__init__()
        self.name = "아젤론의 가호"
        self.description = {
            "user": "설정된 라운드 동안 모든 주사위 값 +20. 특정 유저는 사망 시 자동 부활.",
            "monster": "설정된 라운드 동안 모든 주사위 값 +20."
        }
        self.skill_type = SkillType.DEFENSIVE
        self.cooldown = 5
        self.max_duration = 4
        self.min_duration = 1
        self.dice_bonus = 20
        self.special_user_id = "1127398721529843712"
        self.auto_revive_used = False
        self.revive_hp = 70
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 기본 활성화 체크
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {"success": False, "message": can_activate["reason"]}
        
        # 지속시간 검증
        duration_check = self.validate_duration(duration)
        if not duration_check["valid"]:
            return {"success": False, "message": duration_check["message"]}
        
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration_check["duration"]
        self.total_uses += 1
        
        special_effect = ""
        if self.caster_id == self.special_user_id and caster_type == "user":
            special_effect = f" (사망 시 체력 {self.revive_hp}으로 자동 부활)"
        
        return {
            "success": True,
            "message": f"{self.name} 발동! {self.remaining_rounds}라운드 동안 모든 주사위 +{self.dice_bonus}{special_effect}",
            "duration": self.remaining_rounds,
            "effect": f"모든 주사위 +{self.dice_bonus}",
            "caster": self.caster_id,
            "has_auto_revive": self.caster_id == self.special_user_id
        }
    
    def apply_dice_bonus(self, base_dice: int, dice_owner: str) -> int:
        """주사위 보너스 적용"""
        if not self.active or self.remaining_rounds <= 0:
            return base_dice
        
        if dice_owner == self.caster_id:
            return min(100, base_dice + self.dice_bonus)
        
        return base_dice
    
    def check_auto_revive(self, dead_user_id: str) -> Optional[Dict[str, Any]]:
        """자동 부활 체크"""
        # 특정 유저가 사망했고, 아직 자동 부활을 사용하지 않았을 때
        if (dead_user_id == self.special_user_id and 
            not self.auto_revive_used and 
            self.caster_id == self.special_user_id):
            
            self.auto_revive_used = True
            
            # 부활과 동시에 스킬 활성화 (아직 활성화되지 않았다면)
            if not self.active:
                self.active = True
                self.remaining_rounds = 3  # 기본 3라운드
                self.total_uses += 1
            
            return {
                "revive": True,
                "user_id": dead_user_id,
                "new_hp": self.revive_hp,
                "message": f"{self.name}로 자동 부활! (체력: {self.revive_hp})",
                "skill_activated": True,
                "skill_duration": self.remaining_rounds
            }
        
        return None
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "dice_modifier":
            dice_owner = kwargs.get("dice_owner")
            return self.apply_dice_bonus(target, dice_owner)
        elif effect_type == "check_revive":
            dead_user_id = kwargs.get("user_id")
            return self.check_auto_revive(dead_user_id)
        return target
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            base_status["effect"] = f"모든 주사위 +{self.dice_bonus}"
            
            if self.caster_id == self.special_user_id and not self.auto_revive_used:
                base_status["special"] = "사망 시 자동 부활 대기 중"
            elif self.auto_revive_used:
                base_status["special"] = "자동 부활 사용됨"
        
        return base_status
    
    def reset(self):
        """스킬 초기화"""
        super().reset()
        self.auto_revive_used = False