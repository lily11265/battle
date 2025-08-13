# heroes/jeprof.py
"""제프로프 영웅 스킬 - 집중 공격/확정 주사위"""

from typing import Dict, Any, Optional
from .base import BaseSkill, SkillType

class JeprofSkill(BaseSkill):
    """제프로프 스킬 - 집중 공격/확정 주사위"""
    
    def __init__(self):
        super().__init__()
        self.name = "제프로프의 일격"
        self.description = {
            "user": "설정된 라운드 동안 공격 주사위 값이 무조건 100이 됩니다. (혼자만 사용 가능)",
            "monster": "1턴 동안 1인 집중공격, 주사위 +30 보정 (준비시간 없음)"
        }
        self.skill_type = SkillType.OFFENSIVE
        self.cooldown = 5
        self.max_duration = 3
        self.min_duration = 1
        self.target_user: Optional[str] = None
        self.dice_bonus_monster = 30
        self.dice_fixed_user = 100
        self.max_uses_per_battle = 1  # 몬스터는 전투당 1회만
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 기본 활성화 체크
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {"success": False, "message": can_activate["reason"]}
        
        if caster_type == "monster":
            # 몬스터는 대상 지정 필요
            self.target_user = kwargs.get("target_user")
            if not self.target_user:
                return {"success": False, "message": "집중공격할 대상을 지정해야 합니다."}
            
            # 몬스터는 1턴만
            duration = 1
        else:
            # 유저는 지속시간 검증
            duration_check = self.validate_duration(duration)
            if not duration_check["valid"]:
                return {"success": False, "message": duration_check["message"]}
            duration = duration_check["duration"]
        
        # 스킬 활성화
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration
        self.total_uses += 1
        
        if caster_type == "monster":
            return {
                "success": True,
                "message": f"{self.name} 발동! {self.target_user}에게 집중공격! (주사위 +{self.dice_bonus_monster})",
                "target": self.target_user,
                "duration": duration,
                "effect": f"주사위 +{self.dice_bonus_monster}, 집중공격"
            }
        else:
            return {
                "success": True,
                "message": f"{self.name} 발동! {duration}라운드 동안 공격 주사위 {self.dice_fixed_user} 고정!",
                "duration": duration,
                "effect": f"공격 주사위 {self.dice_fixed_user} 고정"
            }
    
    def apply_dice_modifier(self, base_dice: int, is_attack: bool = True) -> int:
        """주사위 값 수정"""
        if not self.active or self.remaining_rounds <= 0 or not is_attack:
            return base_dice
        
        if self.caster_type == "monster":
            return min(100, base_dice + self.dice_bonus_monster)
        elif self.caster_type == "user":
            return self.dice_fixed_user
        
        return base_dice
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "dice_modifier":
            is_attack = kwargs.get("is_attack", True)
            return self.apply_dice_modifier(target, is_attack)
        elif effect_type == "get_target":
            return self.get_target()
        return target
    
    def get_target(self) -> Optional[str]:
        """몬스터의 집중공격 대상 반환"""
        if self.active and self.caster_type == "monster":
            return self.target_user
        return None
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            if self.caster_type == "monster":
                base_status["effect"] = f"집중공격 대상: {self.target_user}, 주사위 +{self.dice_bonus_monster}"
            else:
                base_status["effect"] = f"공격 주사위 {self.dice_fixed_user} 고정"
        
        return base_status
    
    def deactivate(self):
        """스킬 비활성화"""
        super().deactivate()
        self.target_user = None
    
    def reset(self):
        """스킬 초기화"""
        super().reset()
        self.target_user = None