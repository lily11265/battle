# heroes/nixara.py
"""닉사라 스킬 - 전투 배제"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional
import math

class NiksaraSkill(BaseSkill):
    """닉사라 스킬 - 전투 배제"""
    
    def __init__(self):
        super().__init__()
        self.name = "닉사라"
        self.description = {
            "user": "몬스터를 배제하거나 모든 유저의 방어 주사위에 +10 보정을 줍니다.",
            "monster": "주사위 값 차이에 따라 랜덤 유저를 전투에서 배제합니다."
        }
        self.skill_type = SkillType.SPECIAL
        self.max_duration = 5
        self.min_duration = 1
        self.defense_bonus = 10
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        # 주사위 굴리기
        caster_dice = kwargs.get("caster_dice", 50)
        
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.total_uses += 1
        
        if caster_type == "monster":
            # 몬스터가 사용: 유저 배제
            target_user_id = kwargs.get("target_user_id")
            target_dice = kwargs.get("target_dice", 50)
            
            exclude_rounds = math.floor(abs(caster_dice - target_dice) / 10)
            
            if exclude_rounds > 0:
                self.active = True
                self.remaining_rounds = exclude_rounds
                
                return {
                    "success": True,
                    "message": f"닉사라 발동! 주사위 차이 {abs(caster_dice - target_dice)} → {exclude_rounds}라운드 배제",
                    "duration": exclude_rounds,
                    "effect": {
                        "type": "combat_exclusion",
                        "target_id": target_user_id,
                        "rounds": exclude_rounds
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "주사위 차이가 부족하여 배제 실패!"
                }
        else:
            # 유저가 사용: 선택
            choice = kwargs.get("choice", "defense")
            
            if choice == "monster_exclusion":
                monster_dice = kwargs.get("monster_dice", 50)
                exclude_rounds = math.floor(abs(caster_dice - monster_dice) / 10)
                
                if exclude_rounds > 0:
                    self.active = True
                    self.remaining_rounds = exclude_rounds
                    
                    return {
                        "success": True,
                        "message": f"닉사라 발동! 몬스터를 {exclude_rounds}라운드 배제! (유저 공격 주사위 0)",
                        "duration": exclude_rounds,
                        "effect": {
                            "type": "monster_exclusion",
                            "rounds": exclude_rounds,
                            "user_attack_penalty": True
                        }
                    }
                else:
                    return {
                        "success": False,
                        "message": "주사위 차이가 부족하여 배제 실패!"
                    }
            else:
                # 방어 버프 선택
                duration_check = self.validate_duration(duration)
                self.active = True
                self.remaining_rounds = duration_check["duration"]
                
                return {
                    "success": True,
                    "message": f"닉사라 발동! {self.remaining_rounds}라운드 동안 모든 유저 방어 +{self.defense_bonus}",
                    "duration": self.remaining_rounds,
                    "effect": {
                        "type": "defense_buff",
                        "value": self.defense_bonus,
                        "target": "all_users"
                    }
                }
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status["effect"] = "배제 효과 활성"
        return status