# battle_utils.py - 전투 관련 유틸리티 함수들
import re
import math
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# 알려진 이름 목록 (전역 상수)
KNOWN_NAMES = [
    "아카시 하지메", "펀처", "유진석", "휘슬", "배달기사", "페이",
    "로메즈 아가레스", "레이나 하트베인", "비비", "오카미 나오하",
    "카라트에크", "토트", "처용", "멀 플리시", "코발트윈드", "옥타",
    "베레니케", "안드라 블랙", "봉고 3호", "몰", "베니", "백야",
    "루치페르", "벨사이르 드라켄리트", "불스", "퓨어 메탈",
    "노 단투", "라록", "아카이브", "베터", "메르쿠리",
    "마크-112", "스푸트니크 2세", "이터니티", "커피머신"
]

def extract_health_from_nickname(display_name: str) -> Optional[int]:
    """
    닉네임에서 체력값 추출
    
    구조: [효과들] 이름 구분자 체력 [구분자 타락도]
    - 알려진 이름 목록을 기반으로 정확한 이름 위치 파악
    - 이름 바로 뒤에 오는 1-100 사이의 숫자를 체력으로 인식
    - % 붙은 숫자는 타락도로 인식하여 제외
    
    Args:
        display_name (str): Discord 닉네임
        
    Returns:
        Optional[int]: 추출된 체력값 (1-100), 없으면 None
    """
    if not display_name:
        return None
    
    # 이름들을 길이 순으로 정렬 (긴 이름부터 매칭하여 부분 매칭 방지)
    sorted_names = sorted(KNOWN_NAMES, key=len, reverse=True)
    
    for name in sorted_names:
        # 이름이 닉네임에 있는지 확인
        name_index = display_name.find(name)
        if name_index != -1:
            # 이름 뒤의 부분에서 체력 찾기
            after_name = display_name[name_index + len(name):]
            
            # 이름 바로 뒤에 오는 1-100 사이의 숫자를 체력으로 인식
            # 구분자: 공백, /, |, ·, ⟊
            pattern = r'[\s/|·⟊]+(\d{1,3})(?!\d)'
            match = re.search(pattern, after_name)
            
            if match:
                health = int(match.group(1))
                if 1 <= health <= 100:  # 체력 범위 확인
                    logger.debug(f"Extracted health {health} from nickname: {display_name} (name: {name})")
                    return health
    
    # 알려진 이름을 찾지 못한 경우, 기존 패턴들로 시도
    fallback_patterns = [
        r'(\d{1,3})\s*(?:/|$)',  # 마지막 숫자
        r'(?:/|\||⟊|·)\s*(\d{1,3})(?!\s*%)',  # 구분자 뒤 숫자 (% 앞 제외)
        r'\[\w*/(\d{1,3})\]',  # 대괄호 안 숫자 (예: [마크/100])
    ]
    
    for pattern in fallback_patterns:
        match = re.search(pattern, display_name)
        if match:
            health = int(match.group(1))
            if 1 <= health <= 100:
                logger.debug(f"Extracted health {health} from nickname (fallback): {display_name}")
                return health
    
    logger.debug(f"No health value found in nickname: {display_name}")
    return None

def calculate_battle_health(real_health: int) -> int:
    """
    실제 체력에서 전투 체력 계산
    
    실제 체력을 10으로 나누고 올림하여 전투 체력 산정
    예: 85 HP → 9 전투 체력, 100 HP → 10 전투 체력
    
    Args:
        real_health (int): 실제 체력 (1-100)
        
    Returns:
        int: 전투 체력 (1-10)
    """
    if real_health <= 0:
        return 1
    return math.ceil(real_health / 10)

def update_nickname_health(display_name: str, new_health: int) -> str:
    """
    닉네임의 체력값 업데이트
    
    알려진 이름을 기반으로 정확한 체력 위치를 찾아 업데이트
    타락도(% 붙은 숫자)는 건드리지 않음
    
    Args:
        display_name (str): 현재 닉네임
        new_health (int): 새로운 체력값
        
    Returns:
        str: 업데이트된 닉네임 (최대 32자)
    """
    if not display_name:
        return f"Unknown / {new_health}"[:32]
    
    # 체력 범위 검증
    new_health = max(0, min(100, new_health))
    
    # 이름들을 길이 순으로 정렬 (긴 이름부터 매칭)
    sorted_names = sorted(KNOWN_NAMES, key=len, reverse=True)
    
    for name in sorted_names:
        # 이름이 닉네임에 있는지 확인
        name_index = display_name.find(name)
        if name_index != -1:
            # 이름 뒤의 부분에서 체력 패턴 찾기
            after_name_start = name_index + len(name)
            after_name = display_name[after_name_start:]
            
            # 이름 바로 뒤에 오는 체력 패턴
            pattern = r'([\s/|·⟊]+)(\d{1,3})(?!\d)'
            match = re.search(pattern, after_name)
            
            if match:
                current_health = int(match.group(2))
                if 1 <= current_health <= 100:  # 체력 범위 확인
                    # 체력 부분을 새로운 값으로 교체
                    separator = match.group(1)
                    new_health_part = separator + str(new_health)
                    
                    # 전체 닉네임에서 해당 부분 교체
                    match_start = after_name_start + match.start()
                    match_end = after_name_start + match.end()
                    new_name = display_name[:match_start] + new_health_part + display_name[match_end:]
                    
                    logger.debug(f"Updated nickname health: {display_name} -> {new_name}")
                    return new_name[:32]  # Discord 닉네임 길이 제한
    
    # 알려진 이름을 찾지 못한 경우, 기존 패턴들로 시도
    fallback_patterns = [
        # (패턴, 체력이 있는 그룹 인덱스)
        (r'(\[.*?/)(\d{1,3})(\])', 2),  # 대괄호 안 체력
        (r'(\s*/)(\s*)(\d{1,3})(?!\s*%)', 3),  # 슬래시 뒤 체력
        (r'(\|\s*)(\d{1,3})(?!\s*%)', 2),  # 파이프 뒤 체력
        (r'(·\s*)(\d{1,3})(?!\s*%)', 2),  # 중점 뒤 체력
        (r'(⟊\s*)(\d{1,3})', 2),  # ⟊ 뒤 체력
        (r'(\s+)(\d{1,3})$', 2),  # 끝의 숫자
    ]
    
    for pattern, health_group_index in fallback_patterns:
        match = re.search(pattern, display_name)
        if match:
            current_health = int(match.group(health_group_index))
            if 1 <= current_health <= 100:  # 체력 범위 확인
                groups = list(match.groups())
                groups[health_group_index - 1] = str(new_health)
                
                new_matched_part = ''.join(groups)
                new_name = display_name[:match.start()] + new_matched_part + display_name[match.end():]
                
                logger.debug(f"Updated nickname health (fallback): {display_name} -> {new_name}")
                return new_name[:32]
    
    # 체력값을 찾지 못한 경우 끝에 추가
    new_name = f"{display_name} / {new_health}"
    logger.debug(f"No health pattern found, appending: {display_name} -> {new_name}")
    return new_name[:32]

def extract_recovery_items(items: List[str]) -> List[Dict[str, Any]]:
    """
    아이템 목록에서 회복 아이템 추출
    
    회복 아이템 형태: "아이템명(회복량)"
    예: "상급 치유 물약(30)", "응급처치 키트(15)"
    
    Args:
        items (List[str]): 아이템 목록
        
    Returns:
        List[Dict[str, Any]]: 회복 아이템 정보 리스트
            - full_name: 전체 아이템 이름
            - name: 아이템 이름 (괄호 제외)
            - value: 회복량
    """
    if not items:
        return []
    
    recovery_items = []
    pattern = r'^(.+)\((\d+)\)$'
    
    for item in items:
        if not isinstance(item, str):
            continue
            
        item = item.strip()
        if not item:
            continue
            
        match = re.match(pattern, item)
        if match:
            item_name = match.group(1).strip()
            try:
                recovery_value = int(match.group(2))
                if recovery_value > 0:  # 회복량이 양수인 경우만
                    recovery_items.append({
                        'full_name': item,
                        'name': item_name,
                        'value': recovery_value
                    })
                    logger.debug(f"Found recovery item: {item_name} (+{recovery_value} HP)")
            except ValueError:
                logger.warning(f"Invalid recovery value in item: {item}")
                continue
    
    return recovery_items

def extract_real_name(display_name: str) -> str:
    """
    닉네임에서 실제 이름 추출
    
    닉네임 구조: [효과들] 이름 구분자 체력 [구분자 타락도]
    알려진 이름 목록에서 매칭되는 이름을 찾아 반환
    
    Args:
        display_name (str): Discord 닉네임
        
    Returns:
        str: 추출된 실제 이름, 못 찾으면 원본 닉네임 반환
    """
    if not display_name:
        return "Unknown"
    
    # 공백과 언더스코어 정규화해서 매칭 시도
    normalized_display = display_name.replace(" ", "").replace("_", "")
    
    # 이름들을 길이 순으로 정렬 (긴 이름부터 매칭)
    sorted_names = sorted(KNOWN_NAMES, key=len, reverse=True)
    
    for known_name in sorted_names:
        # 원본 이름으로 직접 매칭 시도
        if known_name in display_name:
            logger.debug(f"Found known name '{known_name}' in nickname: {display_name}")
            return known_name
        
        # 정규화된 이름으로 매칭 시도
        normalized_known = known_name.replace(" ", "").replace("_", "")
        if normalized_known in normalized_display:
            logger.debug(f"Found known name '{known_name}' (normalized) in nickname: {display_name}")
            return known_name
    
    # 못 찾으면 원본 반환
    logger.debug(f"No known name found, using original: {display_name}")
    return display_name

def validate_health_value(health: Any) -> int:
    """
    체력값 검증 및 정규화
    
    Args:
        health: 체력값 (문자열, 숫자 등)
        
    Returns:
        int: 검증된 체력값 (1-100 범위)
    """
    try:
        if isinstance(health, str):
            # 문자열에서 숫자만 추출
            numbers = re.findall(r'\d+', health)
            if numbers:
                health = int(numbers[0])
            else:
                return 100  # 기본값
        
        health = int(health)
        return max(1, min(100, health))  # 1-100 범위로 제한
        
    except (ValueError, TypeError):
        logger.warning(f"Invalid health value: {health}, using default (100)")
        return 100

def parse_nickname_components(display_name: str) -> Dict[str, Any]:
    """
    닉네임을 구성 요소별로 파싱
    
    구조: [효과들] 이름 구분자 체력 [구분자 타락도]
    
    Args:
        display_name (str): Discord 닉네임
        
    Returns:
        Dict[str, Any]: 파싱된 구성 요소
            - effects: 효과 목록
            - name: 실제 이름
            - health: 체력값
            - corruption: 타락도 (있는 경우)
            - raw_name: 원본 닉네임
    """
    result = {
        'effects': [],
        'name': display_name,
        'health': None,
        'corruption': None,
        'raw_name': display_name
    }
    
    if not display_name:
        return result
    
    # 효과 추출 (대괄호 안의 내용)
    effect_pattern = r'\[([^\]]+)\]'
    effect_matches = re.findall(effect_pattern, display_name)
    
    if effect_matches:
        for effect_group in effect_matches:
            # 슬래시로 구분된 여러 효과 처리
            effects = [effect.strip() for effect in effect_group.split('/')]
            result['effects'].extend(effects)
    
    # 실제 이름 추출
    result['name'] = extract_real_name(display_name)
    
    # 체력 추출
    health = extract_health_from_nickname(display_name)
    if health:
        result['health'] = health
    
    # 타락도 추출 (% 앞의 숫자)
    corruption_pattern = r'(\d{1,3})%'
    corruption_match = re.search(corruption_pattern, display_name)
    if corruption_match:
        result['corruption'] = int(corruption_match.group(1))
    
    logger.debug(f"Parsed nickname components: {result}")
    return result

def format_health_display(current_health: int, max_health: int, use_emoji: bool = True) -> str:
    """
    체력을 시각적으로 표시
    
    Args:
        current_health (int): 현재 체력
        max_health (int): 최대 체력
        use_emoji (bool): 이모지 사용 여부
        
    Returns:
        str: 포맷된 체력 표시
    """
    if use_emoji:
        green_hearts = max(0, current_health)
        broken_hearts = max(0, max_health - current_health)
        return "💚" * green_hearts + "💔" * broken_hearts
    else:
        return f"{current_health}/{max_health}"

def is_valid_nickname_format(display_name: str) -> bool:
    """
    닉네임 형식이 유효한지 확인
    
    Args:
        display_name (str): 확인할 닉네임
        
    Returns:
        bool: 유효한 형식인지 여부
    """
    if not display_name or len(display_name) > 32:
        return False
    
    # 알려진 이름이 포함되어 있고 체력값이 있는지 확인
    real_name = extract_real_name(display_name)
    health = extract_health_from_nickname(display_name)
    
    return real_name in KNOWN_NAMES and health is not None