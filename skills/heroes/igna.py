# heroes/igna.py
# heroes/igna.py
"""이그나 영웅 스킬 - 스킬 재사용/복사"""

from typing import Dict, Any, Optional, List
from .base import BaseSkill, SkillType

class IgnaSkill(BaseSkill):
    """이그나 스킬 - 스킬 재사용/복사"""
    
    def __init__(self):
        super().__init__()
        self.name = "이그나의 메아리"
        self.description = {
            "user": "피닉스, 그림을 제외한 다른 스킬을 하나 선택해 사용할 수 있습니다.",
            "monster": "마지막 사용 스킬을 다시 사용하거나 현재 스킬의 지속시간을 2배로 늘립니다."
        }
        self.skill_type = SkillType.SPECIAL
        self.cooldown = 5
        self.max_duration = 5
        self.min_duration = 1
        self.last_used_skill: Optional[Dict] = None
        self.excluded_skills = ["피닉스", "그림", "이그나"]
        
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
        
        if caster_type == "monster":
            current_skill = kwargs.get("current_skill")
            
            if current_skill and current_skill.get("active"):
                # 현재 활성화된 스킬의 지속시간 2배로
                original_duration = current_skill.get("remaining_rounds", 0)
                new_duration = original_duration * 2
                
                self.total_uses += 1
                
                return {
                    "success": True,
                    "message": f"{self.name}로 {current_skill['name']}의 지속시간이 {new_duration}라운드로 연장!",
                    "action": "extend",
                    "skill_name": current_skill['name'],
                    "new_duration": new_duration
                }
            
            elif self.last_used_skill:
                # 마지막 스킬 재사용
                self.total_uses += 1
                
                return {
                    "success": True,
                    "message": f"{self.name}로 {self.last_used_skill['name']}을(를) 다시 사용!",
                    "action": "repeat",
                    "skill_to_repeat": self.last_used_skill,
                    "duration": duration_check["duration"]
                }
            
            else:
                return {
                    "success": False,
                    "message": "재사용할 스킬이나 연장할 활성 스킬이 없습니다."
                }
        
        else:  # user
            copy_skill = kwargs.get("copy_skill")
            
            if not copy_skill:
                return {
                    "success": False,
                    "message": "복사할 스킬을 선택해주세요.",
                    "available_skills": self.get_available_skills()
                }
            
            if copy_skill in self.excluded_skills:
                return {
                    "success": False,
                    "message": f"{copy_skill}은(는) 복사할 수 없는 스킬입니다."
                }
            
            self.total_uses += 1
            
            return {
                "success": True,
                "message": f"{self.name}로 {copy_skill}을(를) 복사하여 사용!",
                "action": "copy",
                "skill_to_copy": copy_skill,
                "duration": duration_check["duration"]
            }
    
    def record_skill_usage(self, skill_info: Dict[str, Any]):
        """몬스터가 사용한 스킬 기록"""
        if skill_info.get("name") != self.name:
            self.last_used_skill = skill_info
    
    def get_available_skills(self) -> List[str]:
        """유저가 복사 가능한 스킬 목록"""
        all_skills = [
            "소레인", "반트로스", "카론", "오라스", "황야", 
            "제프로프", "닉사라", "단목", "드레이언", "루센시아",
            "오닉셀", "볼켄", "리메스", "에이로", "제룬카",
            "스트라보스", "비렐라", "운명의 주사위", "넥시스",
            "아젤론", "에오스와 셀레네", "라브릭스", "자보라",
            "스카넬", "오리븐"
        ]
        
        return [skill for skill in all_skills if skill not in self.excluded_skills]
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """현재 스킬 상태 반환"""
        base_status = self.get_base_status()
        
        if self.last_used_skill:
            base_status["last_skill"] = self.last_used_skill.get("name", "없음")
            base_status["can_repeat"] = True
        
        if self.current_cooldown > 0 or self.last_used_skill:
            return base_status
        
        return None
    
    def reset(self):
        """스킬 초기화"""
        super().reset()
        self.last_used_skill = None