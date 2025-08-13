# heroes/rimes.py
"""리메스 영웅 스킬 - 군대 소환"""

import random
from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillType

class RimesSkill(BaseSkill):
    """리메스 스킬 - 군대 소환"""
    
    def __init__(self):
        super().__init__()
        self.name = "리메스의 군대"
        self.description = {
            "user": "모든 유저가 추가 공격 기회를 얻고 방어 주사위 +10 보정",
            "monster": "매 공격턴마다 추가 집중공격, 방어 주사위 +10 보정"
        }
        self.skill_type = SkillType.SUMMON
        self.cooldown = 4
        self.max_duration = 4
        self.min_duration = 1
        self.defense_bonus = 10
        
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
        
        if caster_type == "monster":
            effect = f"매 공격턴마다 추가 집중공격 + 방어 주사위 +{self.defense_bonus}"
        else:
            effect = f"모든 유저 추가 공격 기회 + 방어 주사위 +{self.defense_bonus}"
        
        return {
            "success": True,
            "message": f"{self.name} 소환! {self.remaining_rounds}라운드 동안 {effect}",
            "duration": self.remaining_rounds,
            "effect": effect
        }
    
    def get_extra_attacks(self, battle_users: List[str]) -> List[Dict[str, Any]]:
        """추가 공격 정보 반환"""
        if not self.active or self.remaining_rounds <= 0:
            return []
        
        extra_attacks = []
        
        if self.caster_type == "monster":
            # 몬스터: 랜덤 유저에게 집중공격
            if battle_users:
                target = random.choice(battle_users)
                extra_attacks.append({
                    "type": "focused",
                    "target": target,
                    "message": f"{self.name}의 군대가 {target}에게 집중공격!"
                })
        
        else:  # user
            # 유저: 모든 유저가 추가 공격
            for user in battle_users:
                extra_attacks.append({
                    "type": "extra",
                    "attacker": user,
                    "message": f"{user}의 추가 공격!"
                })
        
        return extra_attacks
    
    def apply_defense_bonus(self, base_dice: int, is_defense: bool = True) -> int:
        """방어 주사위 보너스 적용"""
        if not self.active or self.remaining_rounds <= 0 or not is_defense:
            return base_dice
        
        return min(100, base_dice + self.defense_bonus)
    
    def should_double_attack(self) -> bool:
        """유저의 더블 공격 여부"""
        return self.active and self.caster_type == "user" and self.remaining_rounds > 0
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "dice_modifier":
            is_defense = kwargs.get("is_defense", False)
            if is_defense:
                return self.apply_defense_bonus(target, is_defense)
        elif effect_type == "extra_attacks":
            battle_users = kwargs.get("battle_users", [])
            return self.get_extra_attacks(battle_users)
        elif effect_type == "should_double":
            return self.should_double_attack()
        return target
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            if self.caster_type == "monster":
                effect = f"추가 집중공격 + 방어 +{self.defense_bonus}"
            else:
                effect = f"추가 공격 기회 + 방어 +{self.defense_bonus}"
            base_status["effect"] = effect
        
        return base_status