# heroes/destiny_dice.py
"""운명의 주사위 스킬 - 극단적 주사위 값"""

import random
from typing import Dict, Any, Optional
from .base import BaseSkill, SkillType

class DestinyDiceSkill(BaseSkill):
    """운명의 주사위 스킬 - 극단적 주사위 값"""
    
    def __init__(self):
        super().__init__()
        self.name = "운명의 주사위"
        self.description = {
            "user": "설정된 라운드 동안 모든 주사위 값이 0 또는 100만 나옵니다. (0: 30%, 100: 70%)",
            "monster": "설정된 라운드 동안 모든 주사위 값이 0 또는 100만 나옵니다. (0: 30%, 100: 70%)"
        }
        self.skill_type = SkillType.SPECIAL
        self.cooldown = 5
        self.max_duration = 3
        self.min_duration = 1
        self.zero_probability = 0.3
        self.hundred_probability = 0.7
        self.roll_statistics = {"zeros": 0, "hundreds": 0, "total": 0}
        
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
        self.roll_statistics = {"zeros": 0, "hundreds": 0, "total": 0}
        
        return {
            "success": True,
            "message": f"{self.name} 발동! {self.remaining_rounds}라운드 동안 극단적인 운명이 기다립니다.",
            "duration": self.remaining_rounds,
            "probabilities": {
                "0": f"{self.zero_probability*100:.0f}%",
                "100": f"{self.hundred_probability*100:.0f}%"
            },
            "caster": self.caster_id
        }
    
    def roll_destiny_dice(self) -> int:
        """운명의 주사위 굴리기"""
        if not self.active or self.remaining_rounds <= 0:
            return random.randint(1, 100)
        
        # 통계 업데이트
        self.roll_statistics["total"] += 1
        
        # 가중치 기반 선택
        if random.random() < self.zero_probability:
            self.roll_statistics["zeros"] += 1
            return 0
        else:
            self.roll_statistics["hundreds"] += 1
            return 100
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "dice_modifier":
            dice_owner = kwargs.get("dice_owner")
            
            if not self.active or self.remaining_rounds <= 0:
                return target
            
            if dice_owner != self.caster_id:
                return target
            
            # 시전자의 주사위만 운명의 주사위로 변경
            return self.roll_destiny_dice()
        
        elif effect_type == "roll_dice":
            dice_owner = kwargs.get("dice_owner")
            if self.active and dice_owner == self.caster_id:
                value = self.roll_destiny_dice()
                if value == 0:
                    message = "운명이 등을 돌렸다! (0)"
                else:
                    message = "운명이 미소짓는다! (100)"
                
                return {
                    "value": value,
                    "message": message,
                    "is_destiny": True
                }
        
        return target
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            base_status.update({
                "effect": "주사위 값: 0(30%) or 100(70%)",
                "statistics": self.roll_statistics
            })
        
        return base_status
    
    def deactivate(self):
        """스킬 비활성화"""
        super().deactivate()
        self.roll_statistics = {"zeros": 0, "hundreds": 0, "total": 0}