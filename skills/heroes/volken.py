# heroes/volken.py
"""볼켄 스킬 - 3라운드 방어 후 반격"""

from .base import BaseSkill, SkillType, CasterType
from typing import Dict, Any, Optional, List
import random

class VolkenSkill(BaseSkill):
    """볼켄 스킬 - 방어 후 강력한 반격"""
    
    def __init__(self):
        super().__init__()
        self.name = "볼켄"
        self.description = {
            "user": "이 스킬은 몬스터 전용입니다.",
            "monster": "3라운드 방어 자세 후 강력한 반격을 합니다. 20번 피격 시 취소됩니다."
        }
        self.skill_type = SkillType.SPECIAL
        self.max_duration = 1  # 한 번만 사용
        self.min_duration = 1
        self.defense_rounds = 3
        self.hit_counter = 0
        self.max_hits = 20
        self.counter_ready = False
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """스킬 활성화"""
        if caster_type != "monster":
            return {
                "success": False,
                "message": "볼켄 스킬은 몬스터만 사용할 수 있습니다."
            }
        
        # 유효성 검사
        can_activate = self.can_activate(caster_type)
        if not can_activate["can_activate"]:
            return {
                "success": False,
                "message": can_activate["reason"]
            }
        
        # 스킬 활성화
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.remaining_rounds = self.defense_rounds
        self.hit_counter = 0
        self.counter_ready = False
        self.total_uses += 1
        
        return {
            "success": True,
            "message": f"볼켄 스킬 발동! 3라운드 방어 자세 (공격 주사위 1 고정)",
            "duration": self.defense_rounds,
            "effect": {
                "type": "volken_defense",
                "attack_dice_override": 1,
                "max_hits": self.max_hits
            }
        }
    
    def register_hit(self) -> Optional[Dict[str, Any]]:
        """피격 등록"""
        if not self.active or self.counter_ready:
            return None
        
        self.hit_counter += 1
        
        if self.hit_counter >= self.max_hits:
            self.deactivate()
            return {
                "cancelled": True,
                "message": f"유저들이 {self.max_hits}번 공격에 성공! 볼켄 스킬 취소!"
            }
        
        return {
            "hits": self.hit_counter,
            "remaining": self.max_hits - self.hit_counter
        }
    
    def process_round(self) -> Optional[str]:
        """라운드 처리"""
        if self.active and not self.counter_ready:
            self.remaining_rounds -= 1
            
            if self.remaining_rounds <= 0:
                self.counter_ready = True
                return "볼켄 방어 종료! 반격 준비 완료!"
        
        return super().process_round()
    
    def execute_counter(self, failed_users: List[Dict[str, Any]]) -> Dict[str, Any]:
        """반격 실행"""
        if not self.counter_ready:
            return {
                "success": False,
                "message": "반격 준비가 되지 않았습니다."
            }
        
        attacks = []
        
        # 주사위 50 미만 유저들에게 2라운드 연속 랜덤 집중공격
        for round_num in range(2):
            for user in failed_users:
                attack_count = random.randint(1, 3)
                attacks.append({
                    "round": round_num + 1,
                    "target_id": user.get("id"),
                    "target_name": user.get("name"),
                    "attack_count": attack_count
                })
        
        self.deactivate()
        
        return {
            "success": True,
            "message": "볼켄 반격 발동!",
            "attacks": attacks
        }
    
    def get_attack_dice_override(self) -> Optional[int]:
        """공격 주사위 오버라이드 값"""
        if self.active and not self.counter_ready:
            return 1
        return None
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active:
            return None
        
        status = self.get_base_status()
        status.update({
            "phase": "counter" if self.counter_ready else "defense",
            "hit_counter": f"{self.hit_counter}/{self.max_hits}",
            "defense_rounds_left": self.remaining_rounds if not self.counter_ready else 0
        })
        return status