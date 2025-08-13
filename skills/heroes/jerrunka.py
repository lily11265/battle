# heroes/jerrunka.py
"""제룬카 스킬 - 타겟팅 추가 데미지"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class JerunkaSkill(BaseSkill):
    """제룬카 스킬 - 타겟 집중 공격"""
    
    def __init__(self):
        super().__init__()
        self.name = "제룬카"
        self.description = {
            "user": "이 스킬은 몬스터 전용입니다.",
            "monster": "가장 체력이 낮거나 스킬 미사용 유저를 타겟. 받는 데미지 -10 → -20"
        }
        self.skill_type = SkillType.OFFENSIVE
        self.max_duration = 5
        self.min_duration = 1
        self.damage_multiplier = 2  # 데미지 2배 (-10 → -20)
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        if caster_type != "monster":
            return {
                "success": False,
                "message": "제룬카 스킬은 몬스터만 사용할 수 있습니다."
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
        
        # 타겟 선정
        alive_users = kwargs.get("alive_users", [])
        users_with_skills = kwargs.get("users_with_skills", [])
        
        if not alive_users:
            return {
                "success": False,
                "message": "타겟팅할 유저가 없습니다."
            }
        
        # 스킬 미사용 유저 우선
        no_skill_users = [u for u in alive_users if u["id"] not in users_with_skills]
        
        if no_skill_users:
            # 스킬 미사용 유저 중 체력 최소
            target = min(no_skill_users, key=lambda u: u.get("hp", 100))
        else:
            # 전체 유저 중 체력 최소
            target = min(alive_users, key=lambda u: u.get("hp", 100))
        
        # 스킬 활성화
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration_check["duration"]
        self.target_id = target["id"]
        self.target_name = target.get("name", "유저")
        self.total_uses += 1
        
        return {
            "success": True,
            "message": f"제룬카 발동! {self.target_name}을(를) 타겟팅! {self.remaining_rounds}라운드 동안 데미지 2배",
            "duration": self.remaining_rounds,
            "effect": {
                "type": "damage_amplification",
                "target_id": self.target_id,
                "multiplier": self.damage_multiplier
            }
        }
    
    def get_damage_multiplier(self, target_id: str) -> float:
        """데미지 배율 반환"""
        if self.active and target_id == self.target_id:
            return self.damage_multiplier
        return 1.0
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status.update({
            "target_id": self.target_id,
            "target_name": self.target_name,
            "damage_multiplier": self.damage_multiplier
        })
        return status