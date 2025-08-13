# heroes/bantros.py
"""반트로스 영웅 스킬 - 지속 데미지/추가 공격"""

from typing import Dict, Any, Optional
from .base import BaseSkill, SkillType

class BantrosSkill(BaseSkill):
    """반트로스 스킬 - 지속 데미지/추가 공격"""
    
    def __init__(self):
        super().__init__()
        self.name = "반트로스의 분노"
        self.description = {
            "user": "스킬 지속 동안 매 라운드마다 적에게 30의 고정 데미지를 입힙니다.",
            "monster": "스킬 지속 동안 매 라운드마다 추가 전체공격을 합니다."
        }
        self.skill_type = SkillType.OFFENSIVE
        self.cooldown = 4
        self.max_duration = 5
        self.min_duration = 1
        self.fixed_damage = 30
        
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
        
        # 스킬 활성화
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration_check["duration"]
        self.total_uses += 1
        
        effect_desc = f"{self.fixed_damage} 고정 데미지/라운드" if caster_type == "user" else "추가 전체공격/라운드"
        
        return {
            "success": True,
            "message": f"{self.name} 발동! {self.remaining_rounds}라운드 동안 {effect_desc}",
            "duration": self.remaining_rounds,
            "effect": effect_desc
        }
    
    def process_round_damage(self) -> Optional[Dict[str, Any]]:
        """라운드별 데미지 처리 (유저가 시전한 경우)"""
        if not self.active or self.remaining_rounds <= 0:
            return None
            
        if self.caster_type == "user":
            return {
                "type": "fixed_damage",
                "target": "monster",
                "damage": self.fixed_damage,
                "message": f"{self.name}로 몬스터에게 {self.fixed_damage}의 고정 데미지!"
            }
        
        return None
    
    def should_extra_attack(self) -> bool:
        """추가 공격 여부 확인 (몬스터가 시전한 경우)"""
        return self.active and self.caster_type == "monster" and self.remaining_rounds > 0
    
    def get_extra_attack(self) -> Optional[Dict[str, Any]]:
        """추가 전체공격 정보 반환"""
        if self.should_extra_attack():
            return {
                "type": "all_attack",
                "message": f"{self.name}로 추가 전체공격!",
                "dice_modifier": 0
            }
        return None
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "round_damage":
            return self.process_round_damage()
        elif effect_type == "extra_attack":
            return self.get_extra_attack()
        return target
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            effect = f"{self.fixed_damage} 고정 데미지/라운드" if self.caster_type == "user" else "추가 전체공격/라운드"
            base_status["effect"] = effect
        
        return base_status