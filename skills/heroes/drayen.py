# heroes/drayen.py
"""드레이언 영웅 스킬 - 더미 유저 소환"""

import random
from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillType

class DrayenSkill(BaseSkill):
    """드레이언 스킬 - 더미 유저 소환"""
    
    def __init__(self):
        super().__init__()
        self.name = "드레이언의 환영"
        self.description = {
            "user": "더미 유저 2~4명을 소환합니다. 더미는 25~75 주사위, 체력 5. 더미가 죽으면 시전자가 30 데미지를 받습니다.",
            "monster": "더미 유저 2~4명을 소환합니다. 더미는 25~75 주사위, 체력 5. 더미가 죽으면 시전자가 30 데미지를 받습니다."
        }
        self.skill_type = SkillType.SUMMON
        self.cooldown = 4
        self.max_duration = 5
        self.min_duration = 2
        self.dummy_users: List[Dict] = []
        self.death_penalty = 30
        
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
        
        # 2~4명의 더미 생성
        dummy_count = random.randint(2, 4)
        
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = duration_check["duration"]
        self.total_uses += 1
        self.dummy_users = []
        
        for i in range(dummy_count):
            dummy = {
                "id": f"dummy_{self.caster_id}_{i+1}",
                "name": f"환영 {i+1}",
                "hp": 5,
                "max_hp": 5,
                "is_alive": True,
                "dice_range": (25, 75)
            }
            self.dummy_users.append(dummy)
        
        return {
            "success": True,
            "message": f"{self.name} 발동! {dummy_count}명의 환영이 소환되었습니다. ({self.remaining_rounds}라운드)",
            "dummy_count": dummy_count,
            "dummies": [d["name"] for d in self.dummy_users],
            "duration": self.remaining_rounds
        }
    
    def roll_dummy_dice(self, dummy_id: str, dice_type: str = "attack") -> Optional[int]:
        """더미 유저의 주사위 굴리기"""
        dummy = self.get_dummy_by_id(dummy_id)
        if dummy and dummy["is_alive"]:
            min_val, max_val = dummy["dice_range"]
            return random.randint(min_val, max_val)
        return None
    
    def damage_dummy(self, dummy_id: str, damage: int) -> Dict[str, Any]:
        """더미에게 데미지 적용"""
        dummy = self.get_dummy_by_id(dummy_id)
        if not dummy or not dummy["is_alive"]:
            return {"success": False, "message": "유효하지 않은 더미입니다."}
        
        dummy["hp"] -= damage
        result = {
            "dummy_name": dummy["name"],
            "damage": damage,
            "remaining_hp": max(0, dummy["hp"])
        }
        
        if dummy["hp"] <= 0:
            dummy["is_alive"] = False
            result["died"] = True
            result["caster_damage"] = self.death_penalty
            result["caster_id"] = self.caster_id
            result["message"] = f"{dummy['name']}이(가) 소멸! 시전자가 {self.death_penalty} 데미지를 받습니다!"
        
        return result
    
    def get_dummy_by_id(self, dummy_id: str) -> Optional[Dict]:
        """ID로 더미 찾기"""
        for dummy in self.dummy_users:
            if dummy["id"] == dummy_id:
                return dummy
        return None
    
    def get_active_dummies(self) -> List[Dict]:
        """살아있는 더미 목록"""
        if not self.active:
            return []
        return [d for d in self.dummy_users if d["is_alive"]]
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "roll_dice":
            dummy_id = kwargs.get("dummy_id")
            dice_type = kwargs.get("dice_type", "attack")
            return self.roll_dummy_dice(dummy_id, dice_type)
        elif effect_type == "damage_dummy":
            dummy_id = kwargs.get("dummy_id")
            damage = kwargs.get("damage", 0)
            return self.damage_dummy(dummy_id, damage)
        elif effect_type == "get_dummies":
            return self.get_active_dummies()
        return target
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            alive_dummies = self.get_active_dummies()
            base_status.update({
                "active_dummies": len(alive_dummies),
                "dummies": [{"name": d["name"], "hp": d["hp"]} for d in alive_dummies]
            })
        
        return base_status
    
    def deactivate(self):
        """스킬 비활성화"""
        alive_count = len(self.get_active_dummies())
        super().deactivate()
        self.dummy_users = []
        
        if alive_count > 0:
            return f"{self.name} 종료. {alive_count}명의 환영이 사라졌습니다."
    
    def reset(self):
        """스킬 초기화"""
        super().reset()
        self.dummy_users = []