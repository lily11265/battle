# heroes/baseskill.py
"""기본 스킬 클래스 - 모든 영웅 스킬의 부모 클래스"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum

class SkillType(Enum):
    """스킬 타입 열거형"""
    OFFENSIVE = "offensive"      # 공격형
    DEFENSIVE = "defensive"      # 방어형
    SUPPORT = "support"          # 지원형
    SUMMON = "summon"           # 소환형
    SPECIAL = "special"         # 특수형
    PASSIVE = "passive"         # 패시브형

class CasterType(Enum):
    """시전자 타입 열거형"""
    USER = "user"
    MONSTER = "monster"
    BOTH = "both"

class BaseSkill(ABC):
    """모든 스킬의 기본 클래스"""
    
    def __init__(self):
        """기본 초기화"""
        self.name: str = "Unknown Skill"
        self.description: Dict[str, str] = {
            "user": "설명 없음",
            "monster": "설명 없음"
        }
        self.skill_type: SkillType = SkillType.SPECIAL
        self.cooldown: int = 0  # 쿨다운 (라운드)
        self.current_cooldown: int = 0
        self.max_duration: int = 10  # 최대 지속시간
        self.min_duration: int = 1   # 최소 지속시간
        self.preparation_time: int = 0  # 준비 시간
        self.active: bool = False
        self.caster_type: Optional[str] = None
        self.caster_id: Optional[str] = None
        self.remaining_rounds: int = 0
        self.total_uses: int = 0  # 전투 중 총 사용 횟수
        self.max_uses_per_battle: Optional[int] = None  # 전투당 최대 사용 횟수
        
    @abstractmethod
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """
        스킬 활성화
        
        Args:
            caster_type: 시전자 타입 ("user" 또는 "monster")
            duration: 지속 시간 (라운드)
            **kwargs: 스킬별 추가 매개변수
            
        Returns:
            활성화 결과 딕셔너리
        """
        pass
    
    def can_activate(self, caster_type: str, current_round: int = 0) -> Dict[str, bool]:
        """
        스킬 활성화 가능 여부 확인
        
        Args:
            caster_type: 시전자 타입
            current_round: 현재 라운드
            
        Returns:
            {"can_activate": bool, "reason": str}
        """
        # 이미 활성화된 경우
        if self.active:
            return {
                "can_activate": False,
                "reason": f"{self.name}은(는) 이미 활성화되어 있습니다."
            }
        
        # 쿨다운 체크
        if self.current_cooldown > 0:
            return {
                "can_activate": False,
                "reason": f"{self.name}은(는) {self.current_cooldown}라운드 후 사용 가능합니다."
            }
        
        # 최대 사용 횟수 체크
        if self.max_uses_per_battle and self.total_uses >= self.max_uses_per_battle:
            return {
                "can_activate": False,
                "reason": f"{self.name}은(는) 전투당 {self.max_uses_per_battle}회만 사용 가능합니다."
            }
        
        return {
            "can_activate": True,
            "reason": "사용 가능"
        }
    
    def process_round(self) -> Optional[str]:
        """
        라운드 처리 (매 라운드마다 호출)
        
        Returns:
            처리 결과 메시지 (없으면 None)
        """
        message = None
        
        # 쿨다운 감소
        if self.current_cooldown > 0:
            self.current_cooldown -= 1
            if self.current_cooldown == 0:
                message = f"{self.name} 쿨다운이 끝났습니다."
        
        # 활성 스킬 지속시간 감소
        if self.active and self.remaining_rounds > 0:
            self.remaining_rounds -= 1
            if self.remaining_rounds == 0:
                self.deactivate()
                return f"{self.name} 효과가 종료되었습니다."
        
        return message
    
    def deactivate(self):
        """스킬 비활성화"""
        self.active = False
        self.caster_type = None
        self.caster_id = None
        self.remaining_rounds = 0
        
        # 쿨다운 적용
        if self.cooldown > 0:
            self.current_cooldown = self.cooldown
    
    @abstractmethod
    def get_status(self) -> Optional[Dict[str, Any]]:
        """
        현재 스킬 상태 반환
        
        Returns:
            상태 정보 딕셔너리 (비활성 시 None)
        """
        pass
    
    def get_base_status(self) -> Dict[str, Any]:
        """기본 상태 정보 반환"""
        status = {
            "name": self.name,
            "type": self.skill_type.value,
            "active": self.active
        }
        
        if self.active:
            status.update({
                "remaining_rounds": self.remaining_rounds,
                "caster_type": self.caster_type,
                "caster_id": self.caster_id
            })
        
        if self.current_cooldown > 0:
            status["cooldown_remaining"] = self.current_cooldown
        
        if self.max_uses_per_battle:
            status["uses"] = f"{self.total_uses}/{self.max_uses_per_battle}"
        
        return status
    
    def reset(self):
        """
        스킬 완전 초기화 (전투 종료 시)
        """
        self.active = False
        self.caster_type = None
        self.caster_id = None
        self.remaining_rounds = 0
        self.current_cooldown = 0
        self.total_uses = 0
    
    def validate_duration(self, duration: int) -> Dict[str, Any]:
        """
        지속시간 유효성 검사
        
        Args:
            duration: 요청된 지속시간
            
        Returns:
            {"valid": bool, "duration": int, "message": str}
        """
        if duration < self.min_duration:
            return {
                "valid": False,
                "duration": self.min_duration,
                "message": f"최소 {self.min_duration}라운드 이상이어야 합니다."
            }
        
        if duration > self.max_duration:
            return {
                "valid": False,
                "duration": self.max_duration,
                "message": f"최대 {self.max_duration}라운드까지 가능합니다."
            }
        
        return {
            "valid": True,
            "duration": duration,
            "message": "유효한 지속시간"
        }
    
    def apply_effect(self, target: Any, effect_type: str, **kwargs) -> Any:
        """
        효과 적용 (하위 클래스에서 필요시 오버라이드)
        
        Args:
            target: 효과 대상
            effect_type: 효과 타입
            **kwargs: 추가 매개변수
            
        Returns:
            적용 결과
        """
        return target
    
    def get_description(self, caster_type: str = "user") -> str:
        """
        스킬 설명 반환
        
        Args:
            caster_type: 시전자 타입
            
        Returns:
            스킬 설명 문자열
        """
        if isinstance(self.description, dict):
            return self.description.get(caster_type, self.description.get("user", "설명 없음"))
        return self.description
    
    def get_info(self) -> Dict[str, Any]:
        """
        스킬 전체 정보 반환
        
        Returns:
            스킬 정보 딕셔너리
        """
        return {
            "name": self.name,
            "type": self.skill_type.value,
            "description": self.description,
            "cooldown": self.cooldown,
            "max_duration": self.max_duration,
            "min_duration": self.min_duration,
            "preparation_time": self.preparation_time,
            "max_uses": self.max_uses_per_battle,
            "current_status": self.get_base_status()
        }
    
    def __str__(self) -> str:
        """문자열 표현"""
        status = "활성" if self.active else "비활성"
        return f"{self.name} ({self.skill_type.value}) - {status}"
    
    def __repr__(self) -> str:
        """개발자용 문자열 표현"""
        return f"<{self.__class__.__name__}(name='{self.name}', active={self.active})>"


class PassiveSkill(BaseSkill):
    """패시브 스킬 기본 클래스"""
    
    def __init__(self):
        super().__init__()
        self.skill_type = SkillType.PASSIVE
        self.always_active = True
        
    def activate(self, caster_type: str, duration: int, **kwargs) -> Dict[str, Any]:
        """패시브 스킬은 항상 활성화"""
        return {
            "success": True,
            "message": f"{self.name}은(는) 패시브 스킬로 항상 활성화되어 있습니다."
        }
    
    def can_activate(self, caster_type: str, current_round: int = 0) -> Dict[str, bool]:
        """패시브 스킬은 별도 활성화 불필요"""
        return {
            "can_activate": False,
            "reason": "패시브 스킬은 자동으로 적용됩니다."
        }


class ToggleSkill(BaseSkill):
    """토글형 스킬 기본 클래스"""
    
    def __init__(self):
        super().__init__()
        self.toggle_cost = 0  # 토글 시 소모 비용
        
    def toggle(self) -> Dict[str, Any]:
        """스킬 토글"""
        if self.active:
            self.deactivate()
            return {
                "success": True,
                "message": f"{self.name}을(를) 비활성화했습니다.",
                "active": False
            }
        else:
            # 활성화 가능 여부 체크는 별도로
            self.active = True
            return {
                "success": True,
                "message": f"{self.name}을(를) 활성화했습니다.",
                "active": True
            }