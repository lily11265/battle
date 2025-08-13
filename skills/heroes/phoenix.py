# heroes/phoenix.py
"""피닉스 스킬 - 회복 및 부활"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class PhoenixSkill(BaseSkill):
    """피닉스 스킬 - 회복 및 부활"""
    
    def __init__(self):
        super().__init__()
        self.name = "피닉스"
        self.description = {
            "user": "죽은 유저를 체력 10으로 부활시키거나 그림 스킬을 방어합니다.",
            "monster": "체력을 50 회복하고 그림 스킬을 무효화할 수 있습니다."
        }
        self.skill_type = SkillType.SUPPORT
        self.max_duration = 1
        self.min_duration = 1
        self.auto_revive_user_id = "1248095905240842261"
        self.auto_revive_used = False
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.total_uses += 1
        
        if caster_type == "monster":
            # 몬스터가 사용: 체력 회복
            heal_amount = 50
            
            # 그림 스킬 무효화 체크
            has_grim = kwargs.get("has_active_grim", False)
            grim_cancelled = False
            
            if has_grim:
                grim_cancelled = True
                message = f"피닉스 스킬 발동! 체력 {heal_amount} 회복, 그림 스킬 무효화!"
            else:
                message = f"피닉스 스킬 발동! 체력 {heal_amount} 회복!"
            
            return {
                "success": True,
                "message": message,
                "effect": {
                    "type": "heal",
                    "amount": heal_amount,
                    "grim_cancelled": grim_cancelled
                }
            }
        else:
            # 유저가 사용
            target_user_id = kwargs.get("target_user_id")
            is_dead = kwargs.get("is_dead", False)
            is_grim_target = kwargs.get("is_grim_target", False)
            
            if is_dead:
                # 죽은 유저 부활
                return {
                    "success": True,
                    "message": f"피닉스의 힘으로 부활! 체력 10 회복",
                    "effect": {
                        "type": "revive",
                        "target_id": target_user_id,
                        "hp": 10
                    }
                }
            elif is_grim_target:
                # 그림 방어
                return {
                    "success": True,
                    "message": "피닉스의 보호막이 그림 스킬을 막아냅니다!",
                    "effect": {
                        "type": "grim_protection",
                        "target_id": target_user_id
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "대상이 죽어있지 않고 그림 타겟도 아닙니다."
                }
    
    def check_auto_revive(self, user_id: str) -> Optional[Dict[str, Any]]:
        """자동 부활 체크"""
        if user_id == self.auto_revive_user_id and not self.auto_revive_used:
            self.auto_revive_used = True
            return {
                "auto_revive": True,
                "hp": 100,
                "message": f"피닉스의 축복으로 자동 부활! 체력 100"
            }
        return None
    
    def reset(self):
        """스킬 초기화"""
        super().reset()
        self.auto_revive_used = False
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        status = self.get_base_status()
        status.update({
            "auto_revive_available": not self.auto_revive_used,
            "auto_revive_user": self.auto_revive_user_id
        })
        return status