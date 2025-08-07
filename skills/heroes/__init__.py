# skills/heroes/__init__.py
"""
영웅 스킬 핸들러 시스템
모든 16개 영웅 스킬을 지원하는 완전한 구현
"""
import logging
from typing import Dict, Optional, Any, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseSkillHandler(ABC):
    """기본 스킬 핸들러 추상 클래스"""
    
    def __init__(self, skill_name: str, needs_target: bool = False, 
                 skill_type: str = "self", priority: int = 10):
        """
        Args:
            skill_name: 스킬 이름 (영웅 이름)
            needs_target: 대상 선택 필요 여부
            skill_type: 스킬 타입 (self, target, global, special)
            priority: 스킬 우선순위 (낮을수록 먼저 적용)
        """
        self.skill_name = skill_name
        self.needs_target = needs_target
        self.skill_type = skill_type
        self.priority = priority
    
    @abstractmethod
    async def activate(self, interaction, target_id: str, duration: int):
        """스킬 활성화 (하위 클래스에서 필수 구현)"""
        pass
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 호출 (값 보정)"""
        return dice_value
    
    async def on_damage_calculation(self, attacker_id: str, victim_id: str, 
                                   damage: int, context: Dict[str, Any]) -> int:
        """데미지 계산 시 호출"""
        return damage
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 호출"""
        pass
    
    async def on_round_end(self, channel_id: str, round_num: int):
        """라운드 종료 시 호출"""
        pass
    
    async def on_battle_start(self, channel_id: str):
        """전투 시작 시 호출"""
        pass
    
    async def on_battle_end(self, channel_id: str):
        """전투 종료 시 호출"""
        pass
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시 호출"""
        pass
    
    async def check_activation_condition(self, channel_id: str, user_id: str) -> bool:
        """스킬 활성화 조건 체크"""
        return True
    
    async def get_valid_targets(self, channel_id: str, user_id: str) -> List[Dict]:
        """유효한 타겟 목록 반환"""
        return []

# 스킬 핸들러 레지스트리
_skill_handlers: Dict[str, BaseSkillHandler] = {}
_handler_cache: Dict[str, BaseSkillHandler] = {}  # 인스턴스 캐시

# 스킬 모듈 매핑 (전체 16개 스킬)
SKILL_MODULE_MAP = {
    # Phase 1 기본 스킬
    "오닉셀": "onixel",
    "피닉스": "phoenix",
    "오리븐": "oriven",
    "카론": "karon",
    
    # Phase 2 대상 선택 스킬
    "스카넬": "scarnel",
    "루센시아": "lucencia",
    "비렐라": "virella",
    "그림": "grim",
    "닉사라": "nixara",
    "제룬카": "jerrunka",
    
    # Phase 3 특수 스킬
    "넥시스": "nexis",
    "볼켄": "volken",
    "단목": "danmok",
    "콜 폴드": "coal_fold",
    "황야": "hwangya",
    "스트라보스": "stravos"
}

# 스킬 타입 분류
SKILL_TYPES = {
    "self": ["오닉셀", "콜 폴드", "황야", "스트라보스"],
    "target": ["스카넬", "루센시아", "비렐라", "그림", "피닉스", "닉사라", "제룬카"],
    "global": ["오리븐", "카론"],
    "special": ["볼켄", "단목", "넥시스"]
}

# 스킬 우선순위 (낮을수록 먼저 적용)
SKILL_PRIORITIES = {
    "그림": 1,      # 즉사 효과 최우선
    "피닉스": 2,    # 그림 방어
    "콜 폴드": 3,   # 주사위 값 고정
    "볼켄": 4,      # 주사위 값 1로 고정
    "오닉셀": 5,    # 주사위 범위 제한
    "스트라보스": 6, # 주사위 범위 제한
    "오리븐": 7,    # 주사위 -10
    "제룬카": 8,    # 데미지 보정
    "카론": 9,      # 데미지 공유
    "스카넬": 10,   # 데미지 공유
    "비렐라": 11,   # 행동 차단
    "닉사라": 12,   # 행동 차단
    "단목": 13,     # 관통 공격
    "황야": 14,     # 이중 행동
    "루센시아": 15, # 부활
    "넥시스": 16    # 확정 데미지
}

def register_skill_handler(skill_name: str, handler: BaseSkillHandler):
    """스킬 핸들러 등록"""
    _skill_handlers[skill_name] = handler
    logger.debug(f"스킬 핸들러 등록: {skill_name}")

def get_skill_handler(skill_name: str) -> Optional[BaseSkillHandler]:
    """스킬 핸들러 조회 (동적 로딩 지원)"""
    # 캐시 확인
    if skill_name in _handler_cache:
        return _handler_cache[skill_name]
    
    # 레지스트리 확인
    if skill_name in _skill_handlers:
        return _skill_handlers[skill_name]
    
    # 동적 로딩 시도
    if skill_name in SKILL_MODULE_MAP:
        _load_skill_handler(skill_name)
        return _handler_cache.get(skill_name)
    
    logger.warning(f"알 수 없는 스킬: {skill_name}")
    return None

def _load_skill_handler(skill_name: str):
    """스킬 핸들러 동적 로딩"""
    module_name = SKILL_MODULE_MAP.get(skill_name)
    if not module_name:
        logger.error(f"스킬 모듈 매핑 없음: {skill_name}")
        return
    
    try:
        # 동적 import
        module = __import__(f"skills.heroes.{module_name}", fromlist=[module_name])
        
        # 핸들러 클래스명 추론
        class_name = f"{module_name.title().replace('_', '')}Handler"
        handler_class = getattr(module, class_name, None)
        
        if handler_class:
            # 인스턴스 생성 및 캐싱
            handler = handler_class()
            _handler_cache[skill_name] = handler
            register_skill_handler(skill_name, handler)
            logger.info(f"스킬 핸들러 로딩 완료: {skill_name}")
        else:
            logger.error(f"핸들러 클래스를 찾을 수 없음: {class_name} in {module_name}")
            
    except ImportError as e:
        logger.error(f"스킬 모듈 import 실패 {skill_name}: {e}")
    except Exception as e:
        logger.error(f"스킬 핸들러 로딩 실패 {skill_name}: {e}")

def get_all_available_skills() -> List[str]:
    """사용 가능한 모든 스킬 목록"""
    return list(SKILL_MODULE_MAP.keys())

def get_skills_by_type(skill_type: str) -> List[str]:
    """타입별 스킬 목록 조회"""
    return SKILL_TYPES.get(skill_type, [])

def get_skill_priority(skill_name: str) -> int:
    """스킬 우선순위 조회"""
    return SKILL_PRIORITIES.get(skill_name, 99)

def preload_all_skills():
    """모든 스킬 미리 로딩 (선택적)"""
    loaded = []
    failed = []
    
    for skill_name in SKILL_MODULE_MAP.keys():
        try:
            handler = get_skill_handler(skill_name)
            if handler:
                loaded.append(skill_name)
            else:
                failed.append(skill_name)
        except Exception as e:
            logger.error(f"스킬 미리 로딩 실패 {skill_name}: {e}")
            failed.append(skill_name)
    
    logger.info(f"스킬 로딩 완료: {len(loaded)}개 성공, {len(failed)}개 실패")
    if failed:
        logger.warning(f"로딩 실패 스킬: {', '.join(failed)}")
    
    return loaded, failed

def clear_handler_cache():
    """핸들러 캐시 초기화"""
    _handler_cache.clear()
    _skill_handlers.clear()
    logger.info("스킬 핸들러 캐시 초기화 완료")

# 스킬 검증 함수들
def validate_skill_target(skill_name: str, caster_id: str, target_id: str) -> bool:
    """스킬 대상 유효성 검증"""
    handler = get_skill_handler(skill_name)
    if not handler:
        return False
    
    # 자기 자신만 가능한 스킬
    if handler.skill_type == "self" and caster_id != target_id:
        return False
    
    # 전역 스킬은 특정 대상 불필요
    if handler.skill_type == "global" and target_id not in ["all_users", "all"]:
        return False
    
    return True

def get_skill_info(skill_name: str) -> Dict[str, Any]:
    """스킬 정보 조회"""
    handler = get_skill_handler(skill_name)
    if not handler:
        return {}
    
    return {
        "name": skill_name,
        "needs_target": handler.needs_target,
        "type": handler.skill_type,
        "priority": handler.priority,
        "module": SKILL_MODULE_MAP.get(skill_name, "unknown")
    }

# 초기화 시 Phase 1 스킬만 미리 로딩
def initialize_phase1():
    """Phase 1 스킬 초기화"""
    phase1_skills = ["오닉셀", "피닉스", "오리븐", "카론"]
    for skill in phase1_skills:
        try:
            get_skill_handler(skill)
        except Exception as e:
            logger.error(f"Phase 1 스킬 초기화 실패 {skill}: {e}")

# 모듈 로드 시 Phase 1 자동 초기화 (선택적)
# initialize_phase1()
