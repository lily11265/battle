# heroes/nexis.py
"""넥시스 스킬 - 특정 유저 전용 고정 데미지"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class NexisSkill(BaseSkill):
    """넥시스 스킬 - 특정 유저 전용"""
    
    def __init__(self):
        super().__init__()
        self.name = "넥시스"
        self.description = {
            "user": "특정 유저만 사용 가능. 적에게 30의 고정 데미지를 입힙니다.",
            "monster": "이 스킬은 유저 전용입니다."
        }
        self.skill_type = SkillType.OFFENSIVE
        self.max_duration = 1
        self.min_duration = 1
        self.allowed_user_id = "1059908946741166120"
        self.fixed_damage = 30
        
    def can_activate(self, caster_type: str, current_round: int = 0) -> Dict[str, bool]:
        """스킬 활성화 가능 여부 확인"""
        if caster_type == "monster":
            return {
                "can_activate": False,
                "reason": "넥시스 스킬은 유저 전용입니다."
            }
        
        return super().can_activate(caster_type, current_round)
    
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 사용자 ID 확인
        caster_id = kwargs.get("caster_id")
        
        if caster_id != self.allowed_user_id:
            return {
                "success": False,
                "message": f"넥시스 스킬은 특정 유저({self.allowed_user_id})만 사용할 수 있습니다."
            }
        
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        # 대상 확인
        target_id = kwargs.get("target_id")
        target_name = kwargs.get("target_name", "몬스터")
        
        if not target_id:
            return {
                "success": False,
                "message": "공격할 대상이 없습니다."
            }
        
        self.total_uses += 1
        
        return {
            "success": True,
            "message": f"넥시스 스킬 발동! {target_name}에게 {self.fixed_damage}의 고정 데미지!",
            "effect": {
                "type": "fixed_damage",
                "target_id": target_id,
                "damage": self.fixed_damage
            }
        }
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        status = self.get_base_status()
        status.update({
            "allowed_user": self.allowed_user_id,
            "damage": self.fixed_damage
        })
        return status