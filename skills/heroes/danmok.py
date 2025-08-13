# heroes/danmok.py
"""단목 스킬 - 관통공격"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional, List

class DanmokSkill(BaseSkill):
    """단목 스킬 - 관통공격"""
    
    def __init__(self):
        super().__init__()
        self.name = "단목"
        self.description = {
            "user": "이 스킬은 몬스터 전용입니다.",
            "monster": "주사위 50 미만 유저와 다음 순서 유저에게 관통공격 (20/10 데미지)"
        }
        self.skill_type = SkillType.OFFENSIVE
        self.max_duration = 1
        self.min_duration = 1
        self.threshold = 50
        self.primary_damage = 20
        self.secondary_damage = 10
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        if caster_type != "monster":
            return {
                "success": False,
                "message": "단목 스킬은 몬스터만 사용할 수 있습니다."
            }
        
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        # 유저들의 주사위 결과 받기
        user_rolls = kwargs.get("user_rolls", [])
        
        if len(user_rolls) < 2:
            return {
                "success": False,
                "message": "관통공격을 할 유저가 부족합니다. (최소 2명 필요)"
            }
        
        # 관통공격 대상 결정
        targets = []
        
        for i, roll in enumerate(user_rolls):
            if roll["dice"] < self.threshold:
                # 현재 유저 (직접 타격)
                targets.append({
                    "user_id": roll["user_id"],
                    "user_name": roll["user_name"],
                    "damage": self.primary_damage,
                    "type": "primary",
                    "dice": roll["dice"]
                })
                
                # 다음 유저 (관통 타격)
                next_index = (i + 1) % len(user_rolls)
                next_user = user_rolls[next_index]
                
                # 이미 타겟에 있는지 확인
                if not any(t["user_id"] == next_user["user_id"] for t in targets):
                    targets.append({
                        "user_id": next_user["user_id"],
                        "user_name": next_user["user_name"],
                        "damage": self.secondary_damage,
                        "type": "secondary",
                        "dice": next_user["dice"]
                    })
        
        if not targets:
            return {
                "success": False,
                "message": "모든 유저가 관통공격을 회피했습니다! (주사위 50 이상)"
            }
        
        self.total_uses += 1
        
        return {
            "success": True,
            "message": f"단목 관통공격 발동! {len(targets)}명 피격",
            "effect": {
                "type": "penetration_attack",
                "targets": targets
            }
        }
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        status = self.get_base_status()
        status.update({
            "threshold": self.threshold,
            "damages": f"{self.primary_damage}/{self.secondary_damage}"
        })
        return status