# heroes/aero.py
"""에이로 영웅 스킬 - 로봇 속성 버프/디버프"""

from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillType

class AeroSkill(BaseSkill):
    """에이로 스킬 - 로봇 속성 버프/디버프"""
    
    def __init__(self):
        super().__init__()
        self.name = "에이로의 전자기장"
        self.description = {
            "user": "로봇 속성 캐릭터들의 모든 주사위 값 +20",
            "monster": "로봇 속성 유저들의 모든 주사위 값 -20"
        }
        self.skill_type = SkillType.SUPPORT
        self.cooldown = 3
        self.max_duration = 4
        self.min_duration = 1
        self.robot_characters = [
            "펀처", "카라트예크", "코발트윈드", 
            "봉고3호", "퓨어메탈", "마크-112", "커피머신"
        ]
        self.effect_value = 20
        
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
        
        modifier = self.effect_value if caster_type == "user" else -self.effect_value
        effect_type = "버프" if caster_type == "user" else "디버프"
        
        return {
            "success": True,
            "message": f"{self.name} 발동! 로봇 속성 캐릭터들이 {effect_type}를 받습니다. ({modifier:+d})",
            "duration": self.remaining_rounds,
            "affected_robots": self.robot_characters,
            "effect": f"주사위 {modifier:+d}"
        }
    
    def is_robot(self, character_name: str) -> bool:
        """캐릭터가 로봇인지 확인"""
        return character_name in self.robot_characters
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type != "dice_modifier":
            return target
        
        character_name = kwargs.get("character_name")
        dice_value = kwargs.get("dice_value", target)
        
        if not self.active or self.remaining_rounds <= 0:
            return dice_value
        
        if self.is_robot(character_name):
            modifier = self.effect_value if self.caster_type == "user" else -self.effect_value
            modified_value = dice_value + modifier
            return max(1, min(100, modified_value))
        
        return dice_value
    
    def get_affected_users(self, battle_users: List[Dict[str, str]]) -> List[str]:
        """영향받는 로봇 유저 목록 반환"""
        affected = []
        for user in battle_users:
            if user.get("character") in self.robot_characters:
                affected.append(user.get("name", user.get("id")))
        return affected
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            modifier = self.effect_value if self.caster_type == "user" else -self.effect_value
            base_status.update({
                "effect": f"로봇 속성: 주사위 {modifier:+d}",
                "affected_count": len(self.robot_characters)
            })
        
        return base_status