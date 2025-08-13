# heroes/virella.py
"""비렐라 스킬 - 식물 속박 또는 회복"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional

class BirellaSkill(BaseSkill):
    """비렐라 스킬 - 속박/회복"""
    
    def __init__(self):
        super().__init__()
        self.name = "비렐라"
        self.description = {
            "user": "모든 유저의 체력을 20 회복시킵니다. (즉시 발동, 턴 종료)",
            "monster": "랜덤 유저를 식물로 속박. 매 턴 주사위 50 이상으로 탈출 (최대 3라운드)"
        }
        self.skill_type = SkillType.SUPPORT
        self.max_duration = 3
        self.min_duration = 1
        self.heal_amount = 20
        self.escape_threshold = 50
        self.bind_duration = 3
        
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
            # 몬스터가 사용: 유저 속박
            target_user_id = kwargs.get("target_user_id")
            target_user_name = kwargs.get("target_user_name", "유저")
            
            if not target_user_id:
                return {
                    "success": False,
                    "message": "속박할 대상이 없습니다."
                }
            
            self.active = True
            self.remaining_rounds = self.bind_duration
            
            return {
                "success": True,
                "message": f"비렐라 발동! {target_user_name}을(를) 식물로 속박!",
                "duration": self.bind_duration,
                "effect": {
                    "type": "plant_bind",
                    "target_id": target_user_id,
                    "escape_threshold": self.escape_threshold,
                    "max_duration": self.bind_duration
                }
            }
        else:
            # 유저가 사용: 즉시 회복
            alive_users = kwargs.get("alive_users", [])
            
            healed_users = []
            for user in alive_users:
                healed_users.append({
                    "user_id": user.get("id"),
                    "user_name": user.get("name"),
                    "heal_amount": self.heal_amount
                })
            
            return {
                "success": True,
                "message": f"비렐라 발동! 모든 유저 체력 {self.heal_amount} 회복!",
                "instant": True,  # 즉시 발동
                "end_turn": True,  # 턴 종료
                "effect": {
                    "type": "instant_heal",
                    "targets": healed_users,
                    "amount": self.heal_amount
                }
            }
    
    def check_escape(self, dice_value: int) -> Dict[str, Any]:
        """탈출 시도 체크"""
        if not self.active:
            return {
                "bound": False,
                "message": "속박되지 않음"
            }
        
        if dice_value >= self.escape_threshold:
            self.deactivate()
            return {
                "escaped": True,
                "message": f"저항 성공! (주사위: {dice_value}) 속박에서 탈출!"
            }
        else:
            return {
                "escaped": False,
                "message": f"저항 실패! (주사위: {dice_value}) 이번 턴 행동 불가!",
                "action_blocked": True
            }
    
    def process_round(self) -> Optional[str]:
        """라운드 처리"""
        if self.active and self.caster_type == "monster":
            self.remaining_rounds -= 1
            
            if self.remaining_rounds <= 0:
                self.deactivate()
                return "식물 속박이 자연적으로 풀렸습니다."
        
        return super().process_round()
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        
        if self.caster_type == "monster":
            status.update({
                "bind_remaining": self.remaining_rounds,
                "escape_threshold": self.escape_threshold
            })
        
        return status