# mob_ai.py - 몬스터 AI 핵심 모듈 (주사위 보정 난이도)
"""
몬스터 전투 AI 시스템
- 기본 전략 AI: 타겟 우선순위 결정
- 행동 결정 AI: 상황별 최적 행동 선택
- 페이즈 기반 AI: 체력에 따른 행동 패턴 변화
- 난이도: 주사위 보정 시스템
"""

import random
import asyncio
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ===== 열거형 정의 =====
class AIPersonality(Enum):
    """AI 성격 타입"""
    AGGRESSIVE = "aggressive"     # 공격적 - 높은 공격 빈도
    DEFENSIVE = "defensive"       # 방어적 - 신중한 행동
    TACTICAL = "tactical"         # 전술적 - 균형잡힌 판단
    BERSERKER = "berserker"      # 광전사 - 낮은 HP시 공격력 증가
    OPPORTUNIST = "opportunist"   # 기회주의 - 약한 적 우선 공격

class AIPhase(Enum):
    """AI 행동 페이즈"""
    NORMAL = "normal"           # 체력 70% 이상
    CAUTIOUS = "cautious"       # 체력 30-70%
    DESPERATE = "desperate"     # 체력 30% 미만

class ActionType(Enum):
    """행동 타입"""
    BASIC_ATTACK = "basic_attack"           # 기본 공격
    FOCUSED_ATTACK = "focused_attack"       # 집중공격
    DEFENSIVE_STANCE = "defensive_stance"   # 방어 태세
    POWER_ATTACK = "power_attack"           # 강력한 공격
    WAIT = "wait"                          # 대기

# ===== 데이터 클래스 =====
@dataclass
class CombatAction:
    """전투 행동"""
    type: ActionType
    target: Optional[Any] = None
    parameters: Dict = field(default_factory=dict)
    priority: float = 1.0
    
@dataclass
class Gambit:
    """조건-행동 쌍"""
    conditions: List[Any]  # 조건 함수 리스트
    action: CombatAction
    priority: int
    name: str = ""

# ===== 난이도별 주사위 보정 시스템 =====
class DifficultyManager:
    """난이도 관리자"""
    
    # 난이도별 주사위 보정값 (기존 동일)
    DICE_MODIFIERS = {
        'easy': {
            'attack_modifier': -15,
            'defense_modifier': -10,
            'recovery_modifier': -10
        },
        'normal': {
            'attack_modifier': 0,
            'defense_modifier': 0,
            'recovery_modifier': 0
        },
        'hard': {
            'attack_modifier': 10,
            'defense_modifier': 5,
            'recovery_modifier': 5
        },
        'nightmare': {
            'attack_modifier': 15,
            'defense_modifier': 10,
            'recovery_modifier': 10
        }
    }
    
    # 난이도별 AI 최적화 설정 (집중공격 최대 4회로 수정)
    OPTIMIZATION_RATES = {
        'easy': {
            'optimal_target_rate': 0.3,
            'optimal_action_rate': 0.4,
            'focused_attack_max': 2,  # 최대 2회
            'mistake_rate': 0.4,
            'mistake_types': ['skip_turn', 'wrong_dice', 'wrong_target']  # 실수 타입 추가
        },
        'normal': {
            'optimal_target_rate': 0.7,
            'optimal_action_rate': 0.7,
            'focused_attack_max': 3,  # 최대 3회
            'mistake_rate': 0.2,
            'mistake_types': ['skip_turn', 'wrong_target']
        },
        'hard': {
            'optimal_target_rate': 0.9,
            'optimal_action_rate': 0.85,
            'focused_attack_max': 4,  # 최대 4회로 감소
            'mistake_rate': 0.1,
            'mistake_types': ['wrong_target']
        },
        'nightmare': {
            'optimal_target_rate': 0.98,
            'optimal_action_rate': 0.95,
            'focused_attack_max': 4,  # 최대 4회로 감소
            'mistake_rate': 0.05,
            'mistake_types': []
        }
    }
    
    @staticmethod
    def apply_dice_modifier(base_roll: int, difficulty: str, roll_type: str) -> int:
        """주사위 값에 난이도 보정 적용"""
        modifiers = DifficultyManager.DICE_MODIFIERS.get(difficulty, {})
        
        if roll_type == 'attack':
            modifier = modifiers.get('attack_modifier', 0)
        elif roll_type == 'defense':
            modifier = modifiers.get('defense_modifier', 0)
        elif roll_type == 'recovery':
            modifier = modifiers.get('recovery_modifier', 0)
        else:
            modifier = 0
        
        # 보정 적용 (1-100 범위 유지)
        modified_roll = base_roll + modifier
        return max(1, min(100, modified_roll))
    
    @staticmethod
    def should_optimize(difficulty: str, optimization_type: str) -> bool:
        """최적화 여부 결정"""
        rates = DifficultyManager.OPTIMIZATION_RATES.get(difficulty, {})
        rate = rates.get(optimization_type, 0.5)
        return random.random() < rate

    @staticmethod
    def get_mistake_type(difficulty: str) -> Optional[str]:
        """실수 타입 결정"""
        rates = DifficultyManager.OPTIMIZATION_RATES.get(difficulty, {})
        if random.random() < rates.get('mistake_rate', 0):
            mistake_types = rates.get('mistake_types', [])
            if mistake_types:
                return random.choice(mistake_types)
        return None

# ===== 타겟 우선순위 시스템 =====
# mob_ai.py의 TargetPrioritizer 클래스 전체를 다음으로 교체하세요:

# ===== 타겟 우선순위 시스템 =====
class TargetPrioritizer:
    """타겟 선택 AI"""
    
    def __init__(self, ai_parameters: Dict, difficulty: str):
        self.parameters = ai_parameters
        self.difficulty = difficulty
    
    def calculate_target_priority(self, target: Any, battle: Any, current_target: Any = None) -> float:
        """타겟의 우선순위 점수 계산"""
        priority_score = 0.0
        
        # 1. 체력 비율 (낮을수록 높은 점수)
        current_hp = target.max_health - target.hits_received
        hp_ratio = current_hp / target.max_health if target.max_health > 0 else 0
        priority_score += (1.0 - hp_ratio) * 40  # 최대 40점
        
        # 2. 위협도 평가 (가한 피해 기준)
        threat_level = min(target.hits_dealt * 10, 30)  # 최대 30점
        priority_score += threat_level
        
        # 3. 탈락 임박 보너스
        if current_hp <= 1:
            priority_score += 25  # 한 대만 더 맞으면 탈락
        
        # 4. 현재 타겟 유지 보너스
        if current_target and current_target == target:
            priority_score += 15 * (1 - self.parameters.get('target_switching', 0.3))
        
        # 5. 성격별 보너스
        if self.parameters.get('personality') == AIPersonality.OPPORTUNIST:
            # 기회주의자는 약한 적에게 추가 보너스
            if hp_ratio < 0.3:
                priority_score += 20
        
        return priority_score
    
    def select_best_target(self, available_targets: List[Any], battle: Any, 
                          current_target: Any = None) -> Optional[Any]:
        """최적의 타겟 선택"""
        if not available_targets:
            return None
        
        # 탈락하지 않은 타겟만 선택
        valid_targets = [t for t in available_targets if not t.is_eliminated]
        if not valid_targets:
            return None
        
        # 난이도에 따른 최적 타겟 선택
        if DifficultyManager.should_optimize(self.difficulty, 'optimal_target_rate'):
            # 최적 타겟 선택 - 리스트 방식으로 수정
            target_scores = []
            for target in valid_targets:
                score = self.calculate_target_priority(target, battle, current_target)
                target_scores.append((target, score))
            
            # 점수가 가장 높은 타겟 선택
            if target_scores:
                best_target = max(target_scores, key=lambda x: x[1])[0]
                return best_target
            else:
                return random.choice(valid_targets)
        else:
            # 랜덤 타겟 선택 (쉬운 난이도)
            return random.choice(valid_targets)

# ===== 행동 결정 AI =====
class DecisionMaker:
    """AI 의사결정 시스템"""
    
    def __init__(self, mob_ai: 'MobAI'):
        self.ai = mob_ai
        self.gambits = self._create_gambits()
    
    # mob_ai.py의 DecisionMaker._create_gambits 메서드에서 Gambit 조건들을 더 안전하게 수정하세요:

    def _create_gambits(self) -> List[Gambit]:
        """AI 성격에 맞는 Gambit 목록 생성"""
        gambits = []
        
        # 난이도별 최대 집중공격 횟수
        max_focused = DifficultyManager.OPTIMIZATION_RATES[self.ai.difficulty]['focused_attack_max']
        
        # 난이도별 체력 임계값 조정
        health_thresholds = {
            'easy': {'low': 0.3, 'mid': 0.5, 'high': 0.7},
            'normal': {'low': 0.3, 'mid': 0.5, 'high': 0.7},
            'hard': {'low': 0.4, 'mid': 0.6, 'high': 0.8},
            'nightmare': {'low': 0.5, 'mid': 0.7, 'high': 0.9}
        }
        
        thresholds = health_thresholds.get(self.ai.difficulty, health_thresholds['normal'])
        
        # 공통 Gambit
        gambits.extend([
            # 체력이 낮을 때 필살기 (난이도별 임계값)
            Gambit(
                conditions=[
                    lambda b: self.ai.get_health_percentage() < thresholds['low'],
                    lambda b: DifficultyManager.should_optimize(self.ai.difficulty, 'optimal_action_rate')
                ],
                action=CombatAction(
                    ActionType.FOCUSED_ATTACK,
                    parameters={'attacks': max_focused, 'mode': 'each'}
                ),
                priority=100,
                name="필살기"
            ),
            
            # 중간 체력에서도 집중공격 (난이도가 높을수록)
            Gambit(
                conditions=[
                    lambda b: self.ai.get_health_percentage() < thresholds['mid'],
                    lambda b: self.ai.difficulty in ['hard', 'nightmare'],
                    lambda b: DifficultyManager.should_optimize(self.ai.difficulty, 'optimal_action_rate')
                ],
                action=CombatAction(
                    ActionType.FOCUSED_ATTACK,
                    parameters={'attacks': max(2, max_focused // 2), 'mode': 'each'}
                ),
                priority=85,
                name="중간 집중공격"
            ),
            
            # 약한 적 마무리 (조건 완화)
            Gambit(
                conditions=[
                    lambda b: any((t.max_health - t.hits_received) <= 2 
                                for t in getattr(b, 'users', []) if not t.is_eliminated) if getattr(b, 'users', []) else False,
                    lambda b: DifficultyManager.should_optimize(self.ai.difficulty, 'optimal_action_rate')
                ],
                action=CombatAction(ActionType.FOCUSED_ATTACK, parameters={'attacks': 2}),
                priority=90,
                name="마무리 일격"
            ),
            
            # 기본 공격
            Gambit(
                conditions=[lambda b: True],
                action=CombatAction(ActionType.BASIC_ATTACK),
                priority=10,
                name="기본 공격"
            )
        ])
        
        # 성격별 추가 Gambit (조건 완화)
        if self.ai.personality == AIPersonality.AGGRESSIVE:
            gambits.insert(0, Gambit(
                conditions=[
                    lambda b: self.ai.get_health_percentage() > thresholds['mid'],
                    lambda b: random.random() < 0.3  # 30% 확률로 공격적 행동
                ],
                action=CombatAction(
                    ActionType.FOCUSED_ATTACK,
                    parameters={'attacks': min(3, max_focused), 'mode': 'each'}
                ),
                priority=80,
                name="공격적 연타"
            ))
        
        elif self.ai.personality == AIPersonality.BERSERKER:
            gambits.insert(0, Gambit(
                conditions=[
                    lambda b: self.ai.get_health_percentage() < thresholds['mid'],
                    lambda b: True  # 항상 발동
                ],
                action=CombatAction(
                    ActionType.FOCUSED_ATTACK,
                    parameters={'attacks': max_focused, 'mode': 'once'}
                ),
                priority=95,
                name="광폭화"
            ))
        
        # nightmare 난이도 특별 Gambit
        if self.ai.difficulty == 'nightmare':
            gambits.insert(0, Gambit(
                conditions=[
                    lambda b: self.ai.get_health_percentage() < thresholds['high'],
                    lambda b: random.random() < 0.5  # 50% 확률
                ],
                action=CombatAction(
                    ActionType.FOCUSED_ATTACK,
                    parameters={'attacks': min(4, max_focused), 'mode': 'each', 'add_normal': True}
                ),
                priority=88,
                name="악몽 연속공격"
            ))
        
        return gambits
        
    # mob_ai.py의 DecisionMaker 클래스의 make_decision 메서드를 다음으로 수정하세요:

    async def make_decision(self, battle: Any) -> Tuple[CombatAction, Dict[str, Any]]:
        """최적의 행동 결정 (집중공격 제한 포함)"""
        ai_log = {
            "phase": self.ai.current_phase.value,
            "health_percentage": self.ai.get_health_percentage(),
            "difficulty": self.ai.difficulty,
            "personality": self.ai.personality.value,
            "decision": None,
            "mistake": None,
            "focused_attack_count": self.ai.focused_attack_count,
            "focused_attack_cooldown": self.ai.focused_attack_cooldown,
            "is_preparing": self.ai.is_preparing_focused
        }
        
        # 준비 중이면 WAIT 반환
        if self.ai.is_preparing_focused:
            ai_log["decision"] = "PREPARING_FOCUSED_ATTACK"
            return CombatAction(ActionType.WAIT), ai_log
        
        # 실수 체크
        mistake_type = DifficultyManager.get_mistake_type(self.ai.difficulty)
        if mistake_type:
            ai_log["mistake"] = mistake_type
            
            if mistake_type == 'skip_turn':
                ai_log["decision"] = "WAIT (mistake: skip turn)"
                return CombatAction(ActionType.WAIT), ai_log
        
        # 유효한 Gambit 찾기 (집중공격 제한 확인)
        valid_gambits = []
        for gambit in self.gambits:
            try:
                # 집중공격 Gambit인 경우 추가 조건 확인
                if gambit.action.type == ActionType.FOCUSED_ATTACK:
                    if not self.ai.can_use_focused_attack():
                        continue  # 사용 불가능하면 스킵
                
                if all(condition(battle) for condition in gambit.conditions):
                    valid_gambits.append(gambit)
            except Exception as e:
                logger.error(f"Gambit 조건 평가 실패: {e}")
                continue
        
        if not valid_gambits:
            ai_log["decision"] = "BASIC_ATTACK (no valid gambits)"
            return CombatAction(ActionType.BASIC_ATTACK), ai_log
        
        # 최적 선택
        selected_gambit = max(valid_gambits, key=lambda g: g.priority)
        action = selected_gambit.action
        ai_log["decision"] = f"{selected_gambit.name} ({action.type.value})"
        
        # 집중공격이 선택되면 준비 시작
        if action.type == ActionType.FOCUSED_ATTACK:
            self.ai.start_focused_preparation()
            # 액션 저장 (수정)
            self.ai.prepared_action = action
            ai_log["decision"] = f"PREPARE_FOCUSED_ATTACK (will attack in {self.ai.prepare_turns} turns)"
            
            # 회피 방식 랜덤 결정
            action.parameters['mode'] = random.choice(['each', 'once'])
            ai_log["focused_mode"] = action.parameters['mode']
        
        # 타겟 선택
        if action.type in [ActionType.BASIC_ATTACK, ActionType.FOCUSED_ATTACK]:
            prioritizer = TargetPrioritizer(self.ai.parameters, self.ai.difficulty)
            
            available_targets = []
            if hasattr(battle, 'users') and battle.users:
                available_targets = battle.users
            elif hasattr(battle, 'players') and battle.players:
                available_targets = battle.players
            
            # 활성 타겟 필터링
            active_targets = [t for t in available_targets if not getattr(t, 'is_eliminated', False)]
            
            if active_targets:
                # 실수로 잘못된 타겟 선택
                if mistake_type == 'wrong_target' and len(active_targets) > 1:
                    # 체력이 가장 많은 타겟 선택 (최악의 선택)
                    target = max(active_targets, key=lambda t: t.max_health - t.hits_received)
                    ai_log["mistake_detail"] = f"wrong target: {target.real_name} (highest health)"
                else:
                    target = prioritizer.select_best_target(
                        active_targets,
                        battle,
                        self.ai.current_target
                    )
                
                if target:
                    action.target = target
                    self.ai.current_target = target
                    ai_log["target"] = target.real_name
                else:
                    action = CombatAction(ActionType.WAIT)
                    ai_log["decision"] = "WAIT (no valid target)"
            else:
                action = CombatAction(ActionType.WAIT)
                ai_log["decision"] = "WAIT (no active targets)"
        
        logger.info(f"AI Decision Log: {ai_log}")
        
        return action, ai_log

# ===== 페이즈 기반 AI =====
class PhaseBasedAI:
    """체력 기반 행동 페이즈 관리"""
    
    def __init__(self, mob_ai: 'MobAI'):
        self.ai = mob_ai
        self.phase_transitions = {
            AIPhase.NORMAL: {
                'hp_threshold': 0.7,
                'behavior_modifiers': {
                    'aggression': 1.0,
                    'caution': 1.0,
                    'skill_usage': 1.0
                }
            },
            AIPhase.CAUTIOUS: {
                'hp_threshold': 0.3,
                'behavior_modifiers': {
                    'aggression': 0.7,
                    'caution': 1.5,
                    'skill_usage': 1.2
                }
            },
            AIPhase.DESPERATE: {
                'hp_threshold': 0.0,
                'behavior_modifiers': {
                    'aggression': 1.8,
                    'caution': 0.3,
                    'skill_usage': 2.0
                }
            }
        }
    
    def update_phase(self) -> Tuple[bool, Optional[str]]:
        """현재 체력에 따른 페이즈 업데이트"""
        hp_ratio = self.ai.get_health_percentage()
        old_phase = self.ai.current_phase
        
        # 페이즈 결정
        if hp_ratio >= 0.7:
            self.ai.current_phase = AIPhase.NORMAL
        elif hp_ratio >= 0.3:
            self.ai.current_phase = AIPhase.CAUTIOUS
        else:
            self.ai.current_phase = AIPhase.DESPERATE
        
        # 페이즈 변경 시
        if old_phase != self.ai.current_phase:
            self._apply_phase_modifiers()
            
            # 페이즈 변경 메시지
            phase_messages = {
                AIPhase.CAUTIOUS: f"{self.ai.mob_name}이(가) 신중해지기 시작했다!",
                AIPhase.DESPERATE: f"{self.ai.mob_name}이(가) 필사적으로 저항한다!"
            }
            
            return True, phase_messages.get(self.ai.current_phase)
        
        return False, None
    
    def _apply_phase_modifiers(self):
        """페이즈에 따른 행동 수정자 적용"""
        modifiers = self.phase_transitions[self.ai.current_phase]['behavior_modifiers']
        
        for param, modifier in modifiers.items():
            if param in self.ai.base_parameters:
                # 기본값에 수정자 곱하기
                base_value = self.ai.base_parameters[param]
                self.ai.parameters[param] = base_value * modifier

# ===== AI 성격 관리자 =====
class AIPersonalityManager:
    """AI 성격 관리"""
    
    def __init__(self):
        self.personality_configs = {
            AIPersonality.AGGRESSIVE: {
                'aggression': 0.9,
                'caution': 0.2,
                'tactical_thinking': 0.4,
                'target_switching': 0.5,
                'skill_usage': 0.8
            },
            AIPersonality.DEFENSIVE: {
                'aggression': 0.3,
                'caution': 0.9,
                'tactical_thinking': 0.7,
                'target_switching': 0.2,
                'skill_usage': 0.4
            },
            AIPersonality.TACTICAL: {
                'aggression': 0.6,
                'caution': 0.6,
                'tactical_thinking': 0.9,
                'target_switching': 0.4,
                'skill_usage': 0.6
            },
            AIPersonality.BERSERKER: {
                'aggression': 1.0,
                'caution': 0.1,
                'tactical_thinking': 0.2,
                'target_switching': 0.7,
                'skill_usage': 0.9
            },
            AIPersonality.OPPORTUNIST: {
                'aggression': 0.5,
                'caution': 0.5,
                'tactical_thinking': 0.8,
                'target_switching': 0.8,
                'skill_usage': 0.7
            }
        }

# ===== 메인 AI 클래스 =====
class MobAI:
    """몬스터 AI 메인 클래스"""
    
    def __init__(self, mob_name: str, mob_health: int, 
                 personality: AIPersonality = AIPersonality.TACTICAL,
                 difficulty: str = "normal"):
        # 기본 정보
        self.mob_name = mob_name
        self.mob_health = mob_health
        self.mob_current_health = mob_health
        self.personality = personality
        self.difficulty = difficulty
        self.current_phase = AIPhase.NORMAL
        
        # AI 파라미터
        self.parameters = {}
        self.base_parameters = {}
        self._initialize_parameters()
        
        # 전투 상태
        self.current_target = None
        self.last_action_time = None
        self.target_memory = {}  # 타겟별 정보 기억
        
        # 컴포넌트
        self.phase_ai = PhaseBasedAI(self)
        self.decision_maker = DecisionMaker(self)
        self.personality_manager = AIPersonalityManager()

        # 집중공격 제한 관련 필드
        self.focused_attack_count = 0
        self.focused_attack_cooldown = 0
        self.is_preparing_focused = False
        self.prepare_turns_left = 0
        
        # 준비된 액션 저장 필드 추가
        self.prepared_action = None

        # 성격별 최대 사용 횟수 설정
        self.max_focused_attacks = {
            AIPersonality.DEFENSIVE: 1,      # 방어적: 전투당 1회
            AIPersonality.TACTICAL: 2,       # 전술적: 전투당 2회
            AIPersonality.OPPORTUNIST: 2,    # 기회주의: 전투당 2회
            AIPersonality.AGGRESSIVE: 3,     # 공격적: 전투당 3회
            AIPersonality.BERSERKER: 4       # 광전사: 전투당 4회
        }.get(personality, 2)

        # 난이도별 준비 턴 설정
        self.prepare_turns = {
            'easy': 3,      # 쉬움: 3턴 준비
            'normal': 2,    # 보통: 2턴 준비
            'hard': 1,      # 어려움: 1턴 준비
            'nightmare': 1  # 악몽: 1턴 준비
        }.get(difficulty, 2)

        # 난이도별 쿨타임 설정
        self.cooldown_turns = {
            'easy': 4,      # 쉬움: 4턴 쿨타임
            'normal': 3,    # 보통: 3턴 쿨타임
            'hard': 2,      # 어려움: 2턴 쿨타임
            'nightmare': 1  # 악몽: 1턴 쿨타임
        }.get(difficulty, 3)

    def _initialize_parameters(self):
        """AI 파라미터 초기화"""
        # 기본값
        self.base_parameters = {
            'aggression': 0.5,
            'caution': 0.5,
            'tactical_thinking': 0.5,
            'target_switching': 0.3,
            'skill_usage': 0.5
        }
        
        # 성격 적용
        manager = AIPersonalityManager()
        if self.personality in manager.personality_configs:
            personality_params = manager.personality_configs[self.personality]
            self.base_parameters.update(personality_params)
        
        # 현재 파라미터 초기화
        self.parameters = self.base_parameters.copy()
        self.parameters['personality'] = self.personality
    
    def get_health_percentage(self) -> float:
        """현재 체력 퍼센트 반환"""
        if self.mob_health <= 0:
            return 0.0
        return self.mob_current_health / self.mob_health
    
    def take_damage(self, damage: int):
        """피해 받기"""
        self.mob_current_health = max(0, self.mob_current_health - damage)
    
    async def decide_action(self, battle: Any) -> Tuple[CombatAction, Optional[str], Dict[str, Any]]:
        """AI 행동 결정"""
        # 페이즈 업데이트
        phase_changed, phase_message = self.phase_ai.update_phase()
        
        # 의사결정 (AI 로그 포함)
        action, ai_log = await self.decision_maker.make_decision(battle)
        
        return action, phase_message, ai_log
    
    def should_use_recovery(self) -> bool:
        """회복 사용 여부 결정"""
        hp_ratio = self.get_health_percentage()
        
        # 성격별 회복 사용 기준
        recovery_thresholds = {
            AIPersonality.DEFENSIVE: 0.7,      # 방어적은 일찍 회복
            AIPersonality.TACTICAL: 0.5,       # 전술적은 중간에
            AIPersonality.AGGRESSIVE: 0.3,     # 공격적은 늦게
            AIPersonality.BERSERKER: 0.2,     # 광전사는 아주 늦게
            AIPersonality.OPPORTUNIST: 0.4    # 기회주의는 적당히
        }
        
        threshold = recovery_thresholds.get(self.personality, 0.4)
        
        # 페이즈별 조정
        if self.current_phase == AIPhase.DESPERATE:
            threshold += 0.3  # 필사적일 때는 더 적극적으로 회복
        elif self.current_phase == AIPhase.CAUTIOUS:
            threshold += 0.1
        
        # 난이도별 회복 최적화 - 수정: 더 확실한 회복 사용
        if self.difficulty == 'nightmare':
            # 악몽 난이도는 최적의 타이밍에 회복
            return hp_ratio <= threshold
        elif self.difficulty == 'hard':
            # 어려움은 높은 확률로 최적 타이밍
            return hp_ratio <= threshold or (hp_ratio <= threshold * 1.2 and random.random() < 0.85)
        elif self.difficulty == 'easy':
            # 쉬움은 종종 회복 타이밍 놓침
            return hp_ratio <= threshold * 0.7 and random.random() < 0.5
        else:
            # 보통은 적절한 확률
            return hp_ratio <= threshold or (hp_ratio <= threshold * 1.1 and random.random() < 0.7)


    def roll_dice(self, roll_type: str = 'attack') -> Tuple[int, bool]:
        """난이도 보정이 적용된 주사위 굴리기"""
        logger.info(f"[DEBUG] roll_dice called - type: {roll_type}, is_preparing: {self.is_preparing_focused}, prepare_turns_left: {self.prepare_turns_left}")
        
        # 집중공격 준비 중이면 항상 1
        if self.is_preparing_focused and roll_type == 'attack' and self.prepare_turns_left > 0:
            logger.info(f"[DEBUG] AI is preparing focused attack! Auto-roll: 1 (prepare_turns_left: {self.prepare_turns_left})")
            return 1, False
        
        # 실수 체크
        mistake_type = DifficultyManager.get_mistake_type(self.difficulty)
        
        if mistake_type == 'wrong_dice':
            # 1d10으로 잘못 굴림
            base_roll = random.randint(1, 10)
            logger.info(f"[DEBUG] AI Mistake: Rolled 1d10 instead of 1d100! Result: {base_roll}")
            return base_roll, True  # 실수 플래그
        
        # 정상적인 주사위
        base_roll = random.randint(1, 100)
        modified_roll = DifficultyManager.apply_dice_modifier(base_roll, self.difficulty, roll_type)
        logger.info(f"[DEBUG] Normal dice roll - base: {base_roll}, modified: {modified_roll}")
        return modified_roll, False

    def start_focused_preparation(self):
        """집중공격 준비 시작"""
        logger.info(f"[DEBUG] start_focused_preparation called - current state: is_preparing={self.is_preparing_focused}, prepare_turns={self.prepare_turns}")
        self.is_preparing_focused = True
        self.prepare_turns_left = self.prepare_turns
        logger.info(f"[DEBUG] Preparation started - is_preparing={self.is_preparing_focused}, prepare_turns_left={self.prepare_turns_left}")

    def use_focused_attack(self):
        """집중공격 사용"""
        logger.info(f"[DEBUG] use_focused_attack called - before: is_preparing={self.is_preparing_focused}, count={self.focused_attack_count}")
        self.focused_attack_count += 1
        self.focused_attack_cooldown = self.cooldown_turns
        self.is_preparing_focused = False  # 준비 상태 해제
        self.prepare_turns_left = 0
        logger.info(f"[DEBUG] use_focused_attack done - after: is_preparing={self.is_preparing_focused}, count={self.focused_attack_count}, cooldown={self.focused_attack_cooldown}")

    def update_turn(self):
        """턴 업데이트 (쿨타임 감소)"""
        logger.info(f"[DEBUG] update_turn called - before: cooldown={self.focused_attack_cooldown}, prepare_turns_left={self.prepare_turns_left}")
        if self.focused_attack_cooldown > 0:
            self.focused_attack_cooldown -= 1
        if self.prepare_turns_left > 0:
            self.prepare_turns_left -= 1
        logger.info(f"[DEBUG] update_turn done - after: cooldown={self.focused_attack_cooldown}, prepare_turns_left={self.prepare_turns_left}")
        
    def can_use_focused_attack(self) -> bool:
        """집중공격 사용 가능 여부 확인"""
        return (
            self.focused_attack_count < self.max_focused_attacks and
            self.focused_attack_cooldown == 0 and
            not self.is_preparing_focused
        )


# ===== 자율 행동 컨트롤러 =====
class AutonomousAIController:
    """AI 자율 행동 시스템"""
    
    def __init__(self, mob_ai: MobAI):
        self.ai = mob_ai
        self.is_active = False
        self.action_queue = asyncio.Queue()
    
    async def process_turn(self, battle: Any) -> Tuple[CombatAction, Optional[str], Dict[str, Any]]:
        """AI 턴 처리"""
        # 행동 결정 - 3개의 값을 받도록 수정
        action, phase_message, ai_log = await self.ai.decide_action(battle)
        
        # 행동 타입별 처리
        if action.type == ActionType.FOCUSED_ATTACK:
            # 집중공격 파라미터 설정
            action.parameters['mob_name'] = self.ai.mob_name
            if 'mode' not in action.parameters:
                action.parameters['mode'] = 'each'
            if 'add_normal' not in action.parameters:
                action.parameters['add_normal'] = False
        
        # 3개의 값을 반환하도록 수정
        return action, phase_message, ai_log
    
    def format_action_parameters(self, action: CombatAction) -> Dict:
        """행동을 전투 시스템 형식으로 변환"""
        if action.type == ActionType.FOCUSED_ATTACK:
            return {
                'type': 'focused_attack',
                'target': action.target,
                'attacks': action.parameters.get('attacks', 2),
                'mode': action.parameters.get('mode', 'each'),
                'add_normal_attack': action.parameters.get('add_normal', False)
            }
        elif action.type == ActionType.BASIC_ATTACK:
            return {
                'type': 'basic_attack',
                'target': action.target
            }
        else:
            return {
                'type': action.type.value,
                'target': action.target
            }

# ===== 전역 함수 =====
def create_mob_ai(mob_name: str, mob_health: int, 
                  personality: str = "tactical", 
                  difficulty: str = "normal") -> MobAI:
    """몹 AI 인스턴스 생성"""
    # 성격 문자열을 열거형으로 변환
    try:
        ai_personality = AIPersonality(personality.lower())
    except ValueError:
        ai_personality = AIPersonality.TACTICAL
    
    return MobAI(mob_name, mob_health, ai_personality, difficulty)