# heroes/zabora.py
"""자보라 영웅 스킬 - 주사위 값 사전 설정"""

import random
from typing import Dict, Any, Optional
from .base import BaseSkill, SkillType

class ZaboraSkill(BaseSkill):
    """자보라 스킬 - 주사위 값 사전 설정"""
    
    def __init__(self):
        super().__init__()
        self.name = "자보라의 예언"
        self.description = {
            "user": "원하는 주사위 값을 미리 설정. 50 이상 나오면 설정값으로 변경 (지속시간 2배)",
            "monster": "원하는 주사위 값을 미리 설정. 50 이상 나오면 설정값으로 변경 (지속시간 2배)"
        }
        self.skill_type = SkillType.SPECIAL
        self.cooldown = 4
        self.max_duration = 3
        self.min_duration = 1
        self.preset_value: Optional[int] = None
        self.base_duration = 0
        self.trigger_threshold = 50
        self.duration_multiplier = 2
        
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
        
        # 사전 설정값 가져오기
        preset_value = kwargs.get("preset_value")
        if preset_value is None:
            return {
                "success": False,
                "message": "주사위 값을 설정해주세요.",
                "request_input": self.request_preset_value()
            }
        
        # 주사위 값 유효성 검사
        if not 1 <= preset_value <= 100:
            return {
                "success": False,
                "message": "주사위 값은 1~100 사이여야 합니다."
            }
        
        self.active = True
        self.caster_type = caster_type
        self.caster_id = kwargs.get("caster_id")
        self.preset_value = preset_value
        self.base_duration = duration_check["duration"]
        self.remaining_rounds = self.base_duration * self.duration_multiplier
        self.total_uses += 1
        
        return {
            "success": True,
            "message": f"{self.name} 발동! {self.remaining_rounds}라운드 동안 {self.trigger_threshold} 이상 시 {preset_value}로 고정",
            "duration": self.remaining_rounds,
            "preset_value": preset_value,
            "trigger_condition": f"주사위 {self.trigger_threshold} 이상",
            "caster": self.caster_id
        }
    
    def request_preset_value(self) -> Dict[str, Any]:
        """사전 설정값 입력 요청 (모달)"""
        return {
            "type": "modal",
            "title": f"{self.name} - 주사위 값 설정",
            "fields": [
                {
                    "name": "preset_value",
                    "label": "원하는 주사위 값 (1-100)",
                    "type": "number",
                    "min": 1,
                    "max": 100,
                    "required": True,
                    "placeholder": "예: 85"
                }
            ],
            "message": f"{self.trigger_threshold} 이상의 주사위가 나올 때 변경될 값을 입력하세요."
        }
    
    def apply_preset(self, original_value: int, dice_owner: str) -> int:
        """주사위 값에 예언 효과 적용"""
        if not self.active or self.remaining_rounds <= 0:
            return original_value
        
        if dice_owner != self.caster_id:
            return original_value
        
        # 원래 주사위가 threshold 이상이면 설정값으로 변경
        if original_value >= self.trigger_threshold:
            return self.preset_value
        
        return original_value
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """효과 적용"""
        if effect_type == "dice_modifier":
            dice_owner = kwargs.get("dice_owner")
            return self.apply_preset(target, dice_owner)
        
        elif effect_type == "roll_dice":
            dice_owner = kwargs.get("dice_owner")
            if not self.active or dice_owner != self.caster_id:
                return None
            
            original = random.randint(1, 100)
            final = self.apply_preset(original, dice_owner)
            
            result = {
                "original": original,
                "final": final,
                "preset_applied": original >= self.trigger_threshold and original != final
            }
            
            if result["preset_applied"]:
                result["message"] = f"{self.name} 발동! {original} → {final}"
            
            return result
        
        return target
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        if not self.active and self.current_cooldown <= 0:
            return None
            
        base_status = self.get_base_status()
        
        if self.active:
            base_status.update({
                "total_duration": self.base_duration * self.duration_multiplier,
                "preset_value": self.preset_value,
                "trigger": f"주사위 {self.trigger_threshold}+",
                "effect": f"{self.trigger_threshold}+ → {self.preset_value}"
            })
        
        return base_status
    
    def deactivate(self):
        """스킬 비활성화"""
        super().deactivate()
        self.preset_value = None
        self.base_duration = 0
    
    def reset(self):
        """스킬 초기화"""
        super().reset()
        self.preset_value = None
        self.base_duration = 0