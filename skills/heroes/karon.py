# heroes/karon.py
"""카론 스킬 - 데미지 공유 또는 실수 확률 증가"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional, List

class KaronSkill(BaseSkill):
    """카론 스킬 - 데미지 공유/실수 확률"""
    
    def __init__(self):
        super().__init__()
        self.name = "카론"
        self.description = {
            "user": "몬스터의 실수 확률을 50% 증가시킵니다.",
            "monster": "유저들이 받는 데미지를 서로 공유합니다. (한 명이 받으면 모두가 받음)"
        }
        self.skill_type = SkillType.SPECIAL
        self.max_duration = 5
        self.min_duration = 1
        self.mistake_increase = 0.5  # 50% 증가
        
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
                "message": f"카론 스킬 활성화! {self.remaining_rounds}라운드 동안 유저간 데미지 공유",
                "duration": self.remaining_rounds,
                "effect": {
                    "type": "damage_share",
                    "target": "all_users"
                }
            }
        else:
            return {
                "success": True,
                "message": f"카론 스킬 활성화! {self.remaining_rounds}라운드 동안 몬스터 실수 확률 50% 증가",
                "duration": self.remaining_rounds,
                "effect": {
                    "type": "mistake_chance",
                    "target": "monster",
                    "increase": self.mistake_increase
                }
            }
    
    def process_damage_share(self, original_target_id: str, damage: int, 
                           alive_users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """데미지 공유 처리"""
        if not self.active or self.caster_type != "monster":
            return []
        
        shared_damages = []
        for user in alive_users:
            if user.get("id") != original_target_id:
                shared_damages.append({
                    "user_id": user.get("id"),
                    "user_name": user.get("name"),
                    "damage": damage,
                    "reason": "카론 데미지 공유"
                })
        
        return shared_damages
    
    def get_mistake_modifier(self) -> float:
        """실수 확률 수정값"""
        if self.active and self.caster_type == "user":
            return self.mistake_increase
        return 0.0
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        
        if self.caster_type == "monster":
            status["effect"] = "유저간 데미지 공유"
        else:
            status["effect"] = f"몬스터 실수 확률 +{int(self.mistake_increase * 100)}%"
        
        return status