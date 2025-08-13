# heroes/grim.py
"""그림 스킬 - 즉사 공격"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class GrimSkill(BaseSkill):
    """그림 스킬 - 즉사 공격"""
    
    def __init__(self):
        super().__init__()
        self.name = "그림"
        self.description = {
            "user": "몬스터 체력이 10% 이하일 때, 1라운드 준비 후 체력을 1로 만듭니다.",
            "monster": "1라운드 준비 후 가장 체력이 낮은 유저를 즉사시킵니다. (피닉스로만 방어 가능)"
        }
        self.skill_type = SkillType.SPECIAL
        self.preparation_time = 1
        self.max_duration = 1
        self.min_duration = 1
        self.preparing = False
        self.target_id = None
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        # 유저가 사용 시 몬스터 체력 체크
        if caster_type == "user":
            monster_hp_percent = kwargs.get("monster_hp_percent", 100)
            if monster_hp_percent > 10:
                return {
                    "success": False,
                    "message": "죽을 운명이 아닙니다. (몬스터 체력이 10% 초과)"
                }
        
        # 스킬 준비 시작
        self.active = True
        self.preparing = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = self.preparation_time
        self.total_uses += 1
        
        # 몬스터가 사용 시 타겟 설정
        if caster_type == "monster":
            self.target_id = kwargs.get("lowest_hp_user_id")
            message = f"그림 스킬 준비 중... 1라운드 후 가장 체력이 낮은 유저를 즉사시킵니다!"
        else:
            message = f"그림 스킬 준비 중... 1라운드 후 몬스터의 체력을 1로 만듭니다!"
        
        return {
            "success": True,
            "message": message,
            "preparing": True,
            "preparation_rounds": self.preparation_time,
            "effect": {
                "type": "instant_death_preparation",
                "target": "lowest_hp_user" if caster_type == "monster" else "monster"
            }
        }
    
    def trigger_effect(self, **kwargs) -> Dict[str, Any]:
        """준비 완료 후 효과 발동"""
        if not self.active or not self.preparing:
            return {
                "success": False,
                "message": "스킬이 준비되지 않았습니다."
            }
        
        self.preparing = False
        
        if self.caster_type == "monster":
            # 피닉스 보호 체크
            has_phoenix_protection = kwargs.get("has_phoenix_protection", False)
            
            if has_phoenix_protection:
                self.deactivate()
                return {
                    "success": False,
                    "message": "피닉스의 보호로 즉사를 막았습니다!",
                    "blocked": True
                }
            
            self.deactivate()
            return {
                "success": True,
                "message": "그림 스킬 발동! 대상이 즉사했습니다!",
                "effect": {
                    "type": "instant_death",
                    "target_id": self.target_id,
                    "damage": 9999
                }
            }
        else:
            # 유저가 사용
            self.deactivate()
            return {
                "success": True,
                "message": "그림 스킬 발동! 몬스터의 체력이 1이 되었습니다!",
                "effect": {
                    "type": "set_hp",
                    "target": "monster",
                    "hp": 1
                }
            }
    
    def process_round(self) -> Optional[str]:
        """라운드 처리"""
        if self.preparing and self.remaining_rounds > 0:
            self.remaining_rounds -= 1
            if self.remaining_rounds == 0:
                return "그림 스킬 준비 완료! 효과를 발동합니다."
        
        return super().process_round()
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status.update({
            "preparing": self.preparing,
            "target_id": self.target_id,
            "effect": "즉사 준비 중" if self.preparing else "즉사 대기"
        })
        return status