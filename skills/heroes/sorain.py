# heroes/sorain.py
"""소레인 영웅 스킬 - 랜덤 버프/디버프"""

import random
from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillType

class SorainSkill(BaseSkill):
    """소레인 스킬 - 랜덤 버프/디버프"""
    
    def __init__(self):
        super().__init__()
        self.name = "소레인의 축복"
        self.description = {
            "user": "스킬 지속 동안 랜덤한 전투 유저들이 주사위 값에 +10 버프를 받습니다.",
            "monster": "랜덤한 전투 유저들의 주사위 값을 -10 감소시킵니다."
        }
        self.skill_type = SkillType.SUPPORT
        self.cooldown = 3
        self.max_duration = 5
        self.min_duration = 1
        self.affected_users: List[str] = []
        self.effect_value: int = 0
        
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
        
        # 전투 유저 목록 가져오기
        battle_users = kwargs.get("battle_users", [])
        if not battle_users:
            return {"success": False, "message": "전투 중인 유저가 없습니다."}
        
        # 랜덤하게 영향받을 유저 선택 (전체의 30~70%)
        affected_count = max(1, int(len(battle_users) * random.uniform(0.3, 0.7)))
        self.affected_users = random.sample(battle_users, affected_count)
        
        # 스킬 활성화
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration_check["duration"]
        self.effect_value = 10 if caster_type == "user" else -10
        self.total_uses += 1
        
        effect_type = "버프" if caster_type == "user" else "디버프"
        
        return {
            "success": True,
            "message": f"{self.name} 발동! {len(self.affected_users)}명의 유저가 {effect_type}를 받습니다.",
            "affected_users": self.affected_users,
            "effect": f"주사위 {self.effect_value:+d}",
            "duration": self.remaining_rounds
        }
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """주사위 값에 효과 적용"""
        if effect_type != "dice_modifier":
            return target
            
        user_id = kwargs.get("user_id")
        dice_value = kwargs.get("dice_value", target)
        
        if not self.active or self.remaining_rounds <= 0:
            return dice_value
            
        if user_id in self.affected_users:
            modified_value = dice_value + self.effect_value
            return max(1, min(100, modified_value))
        
        return dice_value
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        base_status = self.get_base_status()
        
        if self.active and self.remaining_rounds > 0:
            base_status.update({
                "affected_users": len(self.affected_users),
                "effect": f"주사위 {self.effect_value:+d}",
                "affected_list": self.affected_users
            })
            return base_status
        
        elif self.current_cooldown > 0:
            return base_status
        
        return None
    
    def deactivate(self):
        """스킬 비활성화"""
        super().deactivate()
        self.affected_users = []
        self.effect_value = 0
    
    def reset(self):
        """스킬 완전 초기화"""
        super().reset()
        self.affected_users = []
        self.effect_value = 0