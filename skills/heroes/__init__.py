# heroes/__init__.py
"""영웅 스킬 모듈"""

# 기본 클래스들
from .base import BaseSkill, PassiveSkill, ToggleSkill, SkillType, CasterType

# 기존 스킬들 (아직 리팩토링 안됨)
from .onixel import OnikselSkill
from .coal_fold import CallFoldSkill
from .hwangya import HwangyaSkill
from .stravos import StrabosSkill
from .scarnel import SkanelSkill
from .lucencia import LucenciaSkill
from .virella import BirellaSkill
from .grim import GrimSkill
from .phoenix import PhoenixSkill
from .nixara import NiksaraSkill
from .jerrunka import JerunkaSkill
from .oriven import OrivenSkill
from .karon import KaronSkill
from .volken import VolkenSkill
from .danmok import DanmokSkill
from .nexis import NexisSkill

# 새로운 스킬들
from .sorain import SorainSkill
from .bantros import BantrosSkill
from .jeprof import JeprofSkill
from .igna import IgnaSkill
from .drayen import DrayenSkill
from .rimes import RimesSkill
from .aero import AeroSkill
from .destiny_dice import DestinyDiceSkill
from .azelon import AzelonSkill
from .zabora import ZaboraSkill

# 스킬 매핑 딕셔너리
SKILL_MAPPING = {
    # 기존 스킬들
    "오닉셀": OnikselSkill,
    "콜폴드": CallFoldSkill,
    "황야": HwangyaSkill,
    "스트라보스": StrabosSkill,
    "스카넬": SkanelSkill,
    "루센시아": LucenciaSkill,
    "비렐라": BirellaSkill,
    "그림": GrimSkill,
    "피닉스": PhoenixSkill,
    "닉사라": NiksaraSkill,
    "제룬카": JerunkaSkill,
    "오리븐": OrivenSkill,
    "카론": KaronSkill,
    "볼켄": VolkenSkill,
    "단목": DanmokSkill,
    "넥시스": NexisSkill,
    
    # 새로운 스킬들
    "소레인": SorainSkill,
    "반트로스": BantrosSkill,
    "제프로프": JeprofSkill,
    "이그나": IgnaSkill,
    "드레이언": DrayenSkill,
    "리메스": RimesSkill,
    "에이로": AeroSkill,
    "운명의주사위": DestinyDiceSkill,
    "아젤론": AzelonSkill,
    "자보라": ZaboraSkill
}

# 스킬 ID 매핑 (번호로도 접근 가능)
SKILL_ID_MAPPING = {
    1: "소레인",
    2: "반트로스",
    4: "카론",
    6: "황야",
    7: "제프로프",
    8: "닉사라",
    9: "단목",
    10: "이그나",
    12: "드레이언",
    13: "루센시아",
    14: "그림",
    15: "오닉셀",
    16: "볼켄",
    17: "리메스",
    19: "에이로",
    20: "제룬카",
    21: "스트라보스",
    22: "비렐라",
    23: "운명의주사위",
    24: "넥시스",
    25: "피닉스",
    26: "아젤론",
    31: "자보라",
    33: "스카넬",
    34: "오리븐"
}

def get_skill_by_name(name: str):
    """스킬 이름으로 스킬 클래스 가져오기"""
    return SKILL_MAPPING.get(name)

def get_skill_by_id(skill_id: int):
    """스킬 ID로 스킬 클래스 가져오기"""
    skill_name = SKILL_ID_MAPPING.get(skill_id)
    if skill_name:
        return SKILL_MAPPING.get(skill_name)
    return None

def get_all_skill_names():
    """모든 스킬 이름 목록 반환"""
    return list(SKILL_MAPPING.keys())

def get_all_skill_ids():
    """모든 스킬 ID 목록 반환"""
    return list(SKILL_ID_MAPPING.keys())

# 모든 스킬 클래스 export
__all__ = [
    # 기본 클래스들
    'BaseSkill', 'PassiveSkill', 'ToggleSkill', 'SkillType', 'CasterType',
    
    # 기존 스킬들
    'OnikselSkill', 'CallFoldSkill', 'HwangyaSkill', 'StrabosSkill',
    'SkanelSkill', 'LucenciaSkill', 'BirellaSkill', 'GrimSkill',
    'PhoenixSkill', 'NiksaraSkill', 'JerunkaSkill', 'OrivenSkill',
    'KaronSkill', 'VolkenSkill', 'DanmokSkill', 'NexisSkill',
    
    # 새로운 스킬들
    'SorainSkill', 'BantrosSkill', 'JeprofSkill', 'IgnaSkill',
    'DrayenSkill', 'RimesSkill', 'AeroSkill', 'DestinyDiceSkill',
    'AzelonSkill', 'ZaboraSkill',
    
    # 헬퍼 함수들
    'get_skill_by_name', 'get_skill_by_id', 
    'get_all_skill_names', 'get_all_skill_ids',
    
    # 매핑 딕셔너리
    'SKILL_MAPPING', 'SKILL_ID_MAPPING'
]