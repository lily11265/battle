# heroes/scarnel.py
"""스카넬 스킬 - 데미지 공유 및 퇴장시 운석"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional, List

class SkanelSkill(BaseSkill):
    """스카넬 스킬 - 데미지 공유 및 운석"""
    
    def __init__(self):
        super().__init__()
        self.name = "스카넬"
        self.description = {
            "user": "받는 데미지를 다른 유저와 공유. 퇴장 시 운석 공격(주사위 50 미만 시 20 데미지)",
            "monster": "이 스킬은 유저 전용입니다."
        }
        self.skill_type = SkillType.SPECIAL
        self.max_duration = 5
        self.min_duration = 1
        self.meteor_damage = 20
        self.meteor_threshold = 50
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        if caster_type == "monster":
            return {
                "success": False,
                "message": "스카넬 스킬은 유저만 사용할 수 있습니다."
            }
        
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
        
        return {
            "success": True,
            "message": f"스카넬 스킬 활성화! {self.remaining_rounds}라운드 동안 데미지 공유",
            "duration": self.remaining_rounds,
            "effect": {
                "type": "skanel_damage_share",
                "meteor_on_exit": True
            }
        }
    
    def process_damage_share(self, damage: int, alive_users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """데미지 공유 처리"""
        if not self.active:
            return []
        
        shared_damages = []
        
        # 시전자를 제외한 다른 유저들과 데미지 공유
        for user in alive_users:
            if user.get("id") != self.caster_id:
                shared_damages.append({
                    "user_id": user.get("id"),
                    "user_name": user.get("name"),
                    "damage": damage,
                    "reason": "스카넬 데미지 공유"
                })
        
        return shared_damages
    
    def trigger_meteor(self, user_dice_rolls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """운석 공격 발동 (퇴장 시)"""
        meteor_hits = []
        
        for roll in user_dice_rolls:
            if roll["dice"] < self.meteor_threshold:
                meteor_hits.append({
                    "user_id": roll["user_id"],
                    "user_name": roll["user_name"],
                    "damage": self.meteor_damage,
                    "dice": roll["dice"]
                })
        
        return {
            "success": True,
            "message": f"스카넬 운석 떨어짐! {len(meteor_hits)}명 피격",
            "effect": {
                "type": "meteor_strike",
                "hits": meteor_hits
            }
        }
    
    def on_exit(self, **kwargs) -> Optional[Dict[str, Any]]:
        """퇴장 시 호출"""
        if not self.active:
            return None
        
        # 운석 발동을 위한 정보 반환
        return {
            "trigger_meteor": True,
            "message": f"{self.name} 사용자가 퇴장하며 운석을 소환합니다!"
        }
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status.update({
            "damage_share": "active",
            "meteor_damage": self.meteor_damage,
            "meteor_threshold": self.meteor_threshold
        })
        return status