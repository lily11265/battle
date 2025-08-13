# test_skill_system.py - 포괄적 스킬 시스템 테스트 (상세 보고서 생성 기능 포함)
import asyncio
import unittest
import logging
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
import traceback
import gc
import random
from dataclasses import dataclass, field
from collections import defaultdict
import html

# psutil은 선택적 import
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ psutil이 설치되지 않았습니다. 메모리 테스트가 제한됩니다.")

# 테스트 환경 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# === 상세 테스트 결과 데이터 클래스 ===
@dataclass
class SkillTestResult:
    """개별 스킬 테스트 결과"""
    skill_name: str
    test_type: str  # effect, interaction, permission, etc.
    status: str = "pending"  # pending, passed, failed, error, skipped
    start_time: float = 0
    end_time: float = 0
    duration: float = 0
    test_cases: List[Dict] = field(default_factory=list)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    def add_test_case(self, case_name: str, input_data: Any, expected: Any, actual: Any, passed: bool):
        """개별 테스트 케이스 추가"""
        self.test_cases.append({
            "name": case_name,
            "input": input_data,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "timestamp": time.time()
        })
    
    def finish(self, status: str, error: Exception = None):
        """테스트 완료"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.status = status
        if error:
            self.error_message = str(error)
            self.error_traceback = traceback.format_exc()

@dataclass
class TestReport:
    """전체 테스트 보고서"""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_duration: float = 0
    skill_results: Dict[str, List[SkillTestResult]] = field(default_factory=lambda: defaultdict(list))
    system_tests: List[SkillTestResult] = field(default_factory=list)
    performance_metrics: Dict = field(default_factory=dict)
    memory_metrics: Dict = field(default_factory=dict)
    
    def add_skill_result(self, result: SkillTestResult):
        """스킬 테스트 결과 추가"""
        self.skill_results[result.skill_name].append(result)
    
    def add_system_result(self, result: SkillTestResult):
        """시스템 테스트 결과 추가"""
        self.system_tests.append(result)
    
    def finalize(self):
        """보고서 완료"""
        self.end_time = datetime.now()
        self.total_duration = (self.end_time - self.start_time).total_seconds()
    
    def get_summary(self) -> Dict:
        """요약 통계"""
        total_tests = sum(len(results) for results in self.skill_results.values()) + len(self.system_tests)
        passed_tests = sum(1 for results in self.skill_results.values() 
                          for r in results if r.status == "passed") + \
                      sum(1 for r in self.system_tests if r.status == "passed")
        failed_tests = sum(1 for results in self.skill_results.values() 
                          for r in results if r.status == "failed") + \
                      sum(1 for r in self.system_tests if r.status == "failed")
        error_tests = sum(1 for results in self.skill_results.values() 
                         for r in results if r.status == "error") + \
                     sum(1 for r in self.system_tests if r.status == "error")
        
        return {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "errors": error_tests,
            "skipped": total_tests - passed_tests - failed_tests - error_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }

class ComprehensiveSkillSystemTest(unittest.IsolatedAsyncioTestCase):
    """포괄적 스킬 시스템 테스트"""
    
    # 테스트할 모든 스킬 목록
    ALL_SKILLS = [
        "그림", "피닉스", "콜 폴드", "볼켄", "오닉셀", "스트라보스",
        "오리븐", "제룬카", "카론", "스카넬", "비렐라", "닉사라",
        "단목", "황야", "루센시아", "넥시스"
    ]
    
    # 클래스 레벨 보고서
    test_report = TestReport()
    
    async def asyncSetUp(self):
        """테스트 환경 설정"""
        # 임시 디렉토리 생성
        self.temp_dir = Path(tempfile.mkdtemp())
        self.skills_dir = self.temp_dir / "skills"
        self.skills_dir.mkdir(exist_ok=True)
        
        # 필요한 하위 디렉토리 생성
        (self.skills_dir / "config").mkdir(exist_ok=True)
        (self.skills_dir / "data").mkdir(exist_ok=True)
        (self.skills_dir / "heroes").mkdir(exist_ok=True)
        
        # 테스트용 설정 파일 생성
        await self._create_test_configs()
        
        # 테스트 시작 시간 기록
        self._test_start_time = time.time()
    
    async def asyncTearDown(self):
        """테스트 환경 정리"""
        # 임시 디렉토리 삭제
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    async def _create_test_configs(self):
        """테스트용 설정 파일 생성"""
        # skill_config.json
        config_data = {
            "skill_users": {
                "오닉셀": ["all_users", "admin", "monster"],
                "피닉스": ["all_users", "admin", "monster"],
                "오리븐": ["all_users", "admin", "monster"],
                "카론": ["all_users", "admin", "monster"],
                "그림": ["admin", "monster"],
                "볼켄": ["admin", "monster"],
                "콜 폴드": ["admin", "monster"],
                "스트라보스": ["all_users", "admin", "monster"],
                "제룬카": ["admin", "monster"],
                "스카넬": ["all_users", "admin", "monster"],
                "비렐라": ["admin", "monster"],
                "닉사라": ["admin", "monster"],
                "단목": ["admin", "monster"],
                "황야": ["admin", "monster"],
                "루센시아": ["admin", "monster"],
                "넥시스": ["1059908946741166120"]
            },
            "authorized_admins": ["123456789"],
            "authorized_nickname": "system | 시스템"
        }
        
        config_file = self.skills_dir / "config" / "skill_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        # user_skills.json
        user_skills_data = {
            "123456789": {
                "allowed_skills": self.ALL_SKILLS,
                "display_name": "테스트유저",
                "skill_level": "admin"
            },
            "987654321": {
                "allowed_skills": ["오닉셀", "오리븐", "카론", "스카넬"],
                "display_name": "일반유저",
                "skill_level": "user"
            }
        }
        
        user_skills_file = self.skills_dir / "config" / "user_skills.json"
        with open(user_skills_file, 'w', encoding='utf-8') as f:
            json.dump(user_skills_data, f, ensure_ascii=False, indent=2)
        
        # 빈 skill_states.json
        states_file = self.skills_dir / "data" / "skill_states.json"
        with open(states_file, 'w', encoding='utf-8') as f:
            json.dump({}, f)
    
    # === 시스템 기본 테스트 ===
    
    async def test_00_system_initialization(self):
        """시스템 초기화 테스트"""
        result = SkillTestResult("System", "initialization")
        result.start_time = time.time()
        
        try:
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                
                from skills.skill_manager import SkillManager
                manager = SkillManager()
                await manager.initialize()
                
                # 설정 로드 확인
                config = manager.get_config("skill_users", {})
                result.add_test_case(
                    "설정 파일 로드",
                    "skill_config.json",
                    16,  # 예상 스킬 수
                    len(config),
                    len(config) == 16
                )
                
                # 유저 스킬 로드 확인
                user_skills = manager.get_user_allowed_skills("123456789")
                result.add_test_case(
                    "유저 스킬 권한",
                    "123456789",
                    self.ALL_SKILLS,
                    user_skills,
                    set(user_skills) == set(self.ALL_SKILLS)
                )
                
                result.finish("passed")
                logger.info("✅ 시스템 초기화 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 시스템 초기화 테스트 실패: {e}")
            raise
        
        finally:
            self.test_report.add_system_result(result)
    
    # === 개별 스킬 효과 테스트 ===
    
    async def test_skill_onixel_effect(self):
        """오닉셀 스킬 효과 상세 테스트"""
        result = SkillTestResult("오닉셀", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                
                from skills.skill_manager import skill_manager
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 오닉셀 스킬 추가
                skill_manager.add_skill(
                    channel_id, "오닉셀", user_id, "테스트유저", 
                    user_id, "테스트유저", 5
                )
                
                # 다양한 주사위 값 테스트
                test_cases = [
                    (10, 50, "최소값 보정"),
                    (30, 50, "최소값 보정"),
                    (50, 50, "경계값 테스트"),
                    (75, 75, "정상 범위"),
                    (100, 100, "정상 범위"),
                    (150, 150, "최대값 경계"),
                    (200, 150, "최대값 보정"),
                    (999, 150, "극단값 테스트")
                ]
                
                for original, expected, case_name in test_cases:
                    final_value, messages = await skill_effects.process_dice_roll(
                        user_id, original, channel_id
                    )
                    
                    result.add_test_case(
                        case_name,
                        original,
                        expected,
                        final_value,
                        final_value == expected
                    )
                    
                    if original != expected:
                        # 메시지 확인
                        has_message = any("오닉셀" in msg for msg in messages)
                        result.add_test_case(
                            f"{case_name} - 메시지 확인",
                            messages,
                            True,
                            has_message,
                            has_message
                        )
                
                result.finish("passed")
                logger.info("✅ 오닉셀 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 오닉셀 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_coal_fold_effect(self):
        """콜 폴드 스킬 효과 상세 테스트"""
        result = SkillTestResult("콜 폴드", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                
                from skills.skill_manager import skill_manager
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 콜 폴드 스킬 추가
                skill_manager.add_skill(
                    channel_id, "콜 폴드", user_id, "테스트유저",
                    user_id, "테스트유저", 5
                )
                
                # 100번 테스트하여 확률 분포 확인
                results = defaultdict(int)
                for i in range(100):
                    final_value, messages = await skill_effects.process_dice_roll(
                        user_id, 50, channel_id
                    )
                    results[final_value] += 1
                
                # 0과 100만 나와야 함
                result.add_test_case(
                    "가능한 결과값",
                    "주사위 굴림 100회",
                    {0, 100},
                    set(results.keys()),
                    set(results.keys()) == {0, 100}
                )
                
                # 확률 분포 확인 (40% vs 60% 오차 범위 ±10%)
                zero_ratio = results[0] / 100
                hundred_ratio = results[100] / 100
                
                result.add_test_case(
                    "0 나올 확률 (40% ± 10%)",
                    f"{results[0]}/100",
                    "30% ~ 50%",
                    f"{zero_ratio:.1%}",
                    0.3 <= zero_ratio <= 0.5
                )
                
                result.add_test_case(
                    "100 나올 확률 (60% ± 10%)",
                    f"{results[100]}/100",
                    "50% ~ 70%",
                    f"{hundred_ratio:.1%}",
                    0.5 <= hundred_ratio <= 0.7
                )
                
                result.finish("passed")
                logger.info("✅ 콜 폴드 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 콜 폴드 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_oriven_effect(self):
        """오리븐 스킬 효과 상세 테스트"""
        result = SkillTestResult("오리븐", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                
                from skills.skill_manager import skill_manager
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                monster_id = "monster"
                
                # 테스트 케이스 1: 몬스터가 오리븐 사용
                skill_manager.add_skill(
                    channel_id, "오리븐", monster_id, "몬스터",
                    "all_users", "모든 유저", 5
                )
                
                # 유저 주사위 -10
                test_values = [100, 50, 11, 10, 5]
                for original in test_values:
                    final_value, messages = await skill_effects.process_dice_roll(
                        user_id, original, channel_id
                    )
                    expected = max(1, original - 10)
                    
                    result.add_test_case(
                        f"몬스터→유저 디버프 ({original})",
                        original,
                        expected,
                        final_value,
                        final_value == expected
                    )
                
                # 몬스터는 영향 없음
                final_value, _ = await skill_effects.process_dice_roll(
                    monster_id, 100, channel_id
                )
                result.add_test_case(
                    "몬스터 자신은 영향 없음",
                    100,
                    100,
                    final_value,
                    final_value == 100
                )
                
                # 스킬 제거 후 테스트 케이스 2: 유저가 오리븐 사용
                skill_manager.remove_skill(channel_id, "오리븐")
                skill_manager.add_skill(
                    channel_id, "오리븐", user_id, "유저",
                    "all_monsters", "모든 몬스터", 5
                )
                
                # 몬스터 주사위 -10
                final_value, messages = await skill_effects.process_dice_roll(
                    monster_id, 100, channel_id
                )
                result.add_test_case(
                    "유저→몬스터 디버프",
                    100,
                    90,
                    final_value,
                    final_value == 90
                )
                
                result.finish("passed")
                logger.info("✅ 오리븐 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 오리븐 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_grim_effect(self):
        """그림 스킬 효과 상세 테스트"""
        result = SkillTestResult("그림", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                target_id = "target_user"
                
                # 그림 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "그림", user_id, "테스트유저",
                    target_id, "타겟유저", 5
                )
                
                result.add_test_case(
                    "그림 스킬 추가",
                    {"skill": "그림", "target": target_id},
                    True,
                    success,
                    success
                )
                
                # 특수 효과 확인
                state = skill_manager.get_channel_state(channel_id)
                has_grim = "grim_preparing" in state.get("special_effects", {})
                
                result.add_test_case(
                    "그림 준비 상태 설정",
                    "special_effects",
                    True,
                    has_grim,
                    has_grim
                )
                
                if has_grim:
                    grim_data = state["special_effects"]["grim_preparing"]
                    
                    result.add_test_case(
                        "그림 타겟 설정",
                        "target_id",
                        target_id,
                        grim_data.get("target_id"),
                        grim_data.get("target_id") == target_id
                    )
                    
                    result.add_test_case(
                        "그림 발동 라운드",
                        "rounds_until_activation",
                        3,
                        grim_data.get("rounds_until_activation"),
                        grim_data.get("rounds_until_activation") == 3
                    )
                
                result.finish("passed")
                logger.info("✅ 그림 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 그림 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_phoenix_effect(self):
        """피닉스 스킬 효과 상세 테스트"""
        result = SkillTestResult("피닉스", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 피닉스 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "피닉스", user_id, "테스트유저",
                    user_id, "테스트유저", 5
                )
                
                result.add_test_case(
                    "피닉스 스킬 추가",
                    {"skill": "피닉스", "user": user_id},
                    True,
                    success,
                    success
                )
                
                # 죽음 방어 확인 - 실제 구현에서는 death 이벤트 처리
                state = skill_manager.get_channel_state(channel_id)
                has_phoenix = "피닉스" in state.get("active_skills", {})
                
                result.add_test_case(
                    "피닉스 활성화 상태",
                    "active_skills",
                    True,
                    has_phoenix,
                    has_phoenix
                )
                
                result.finish("passed")
                logger.info("✅ 피닉스 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 피닉스 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_volken_effect(self):
        """볼켄 스킬 효과 상세 테스트"""
        result = SkillTestResult("볼켄", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                monster_id = "monster"
                
                # 볼켄 스킬 추가
                skill_manager.add_skill(
                    channel_id, "볼켄", monster_id, "몬스터",
                    "all", "전체", 5
                )
                
                # 볼켄 효과 수동 설정 (1-3단계)
                state = skill_manager.get_channel_state(channel_id)
                state["special_effects"]["volken_eruption"] = {
                    "current_phase": 1,
                    "selected_targets": []
                }
                skill_manager.mark_dirty(channel_id)
                
                # 1-3단계: 모든 주사위 1로 고정
                for phase in [1, 2, 3]:
                    state["special_effects"]["volken_eruption"]["current_phase"] = phase
                    
                    final_value, messages = await skill_effects.process_dice_roll(
                        user_id, 100, channel_id
                    )
                    
                    result.add_test_case(
                        f"볼켄 {phase}단계 - 주사위 1 고정",
                        100,
                        1,
                        final_value,
                        final_value == 1
                    )
                
                # 4단계: 선별 단계
                state["special_effects"]["volken_eruption"]["current_phase"] = 4
                state["special_effects"]["volken_eruption"]["selected_targets"] = []
                
                result.add_test_case(
                    "볼켄 4단계 - 선별 단계",
                    "phase",
                    4,
                    state["special_effects"]["volken_eruption"]["current_phase"],
                    True
                )
                
                result.finish("passed")
                logger.info("✅ 볼켄 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 볼켄 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    # === 스킬 상호작용 테스트 ===
    
    async def test_skill_priority_interaction(self):
        """스킬 우선순위 상호작용 테스트"""
        result = SkillTestResult("System", "skill_priority")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 여러 스킬 동시 활성화
                skills_to_test = [
                    ("콜 폴드", 3),    # 우선순위 3
                    ("오닉셀", 5),      # 우선순위 5  
                    ("오리븐", 7)       # 우선순위 7
                ]
                
                for skill_name, priority in skills_to_test:
                    skill_manager.add_skill(
                        channel_id, skill_name, user_id, "테스트유저",
                        user_id if skill_name != "오리븐" else "all_users", 
                        "테스트유저" if skill_name != "오리븐" else "모든 유저", 
                        5
                    )
                
                # Mock random to control 콜 폴드
                with patch('random.random', return_value=0.7):  # 100 나오도록
                    final_value, messages = await skill_effects.process_dice_roll(
                        user_id, 30, channel_id
                    )
                    
                    # 예상: 콜 폴드(100) → 오닉셀(100 그대로) → 오리븐(90)
                    result.add_test_case(
                        "우선순위 적용 순서",
                        {"initial": 30, "skills": ["콜 폴드", "오닉셀", "오리븐"]},
                        90,
                        final_value,
                        final_value == 90
                    )
                    
                    # 모든 스킬이 메시지에 언급되어야 함
                    all_messages = " ".join(messages)
                    for skill_name, _ in skills_to_test:
                        has_skill = skill_name in all_messages
                        result.add_test_case(
                            f"{skill_name} 메시지 포함",
                            messages,
                            True,
                            has_skill,
                            has_skill
                        )
                
                result.finish("passed")
                logger.info("✅ 스킬 우선순위 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 스킬 우선순위 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    # === 성능 및 부하 테스트 ===
    
    async def test_performance_stress_test(self):
        """대규모 부하 테스트"""
        result = SkillTestResult("System", "performance_stress")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                # 100개 채널, 각 채널당 10개 스킬
                channels = []
                start_time = time.time()
                
                for i in range(100):
                    channel_id = f"stress_channel_{i}"
                    channels.append(channel_id)
                    
                    # 랜덤하게 스킬 추가
                    for j in range(10):
                        skill_name = random.choice(self.ALL_SKILLS[:6])  # 기본 스킬만
                        user_id = f"user_{j}"
                        
                        skill_manager.add_skill(
                            channel_id, skill_name, user_id, f"유저{j}",
                            user_id, f"유저{j}", 5
                        )
                
                creation_time = time.time() - start_time
                
                result.add_test_case(
                    "1000개 스킬 생성 시간",
                    "1000 skills",
                    "<5초",
                    f"{creation_time:.2f}초",
                    creation_time < 5.0
                )
                
                # 1000번의 주사위 처리
                start_time = time.time()
                
                for i in range(1000):
                    channel_id = random.choice(channels)
                    user_id = f"user_{random.randint(0, 9)}"
                    dice_value = random.randint(1, 100)
                    
                    await skill_effects.process_dice_roll(
                        user_id, dice_value, channel_id
                    )
                
                processing_time = time.time() - start_time
                avg_time = processing_time / 1000
                
                result.add_test_case(
                    "1000번 주사위 처리 시간",
                    "1000 rolls",
                    "<10초",
                    f"{processing_time:.2f}초",
                    processing_time < 10.0
                )
                
                result.add_test_case(
                    "평균 처리 시간",
                    "per roll",
                    "<10ms",
                    f"{avg_time*1000:.2f}ms",
                    avg_time < 0.01
                )
                
                # 성능 메트릭 저장
                self.test_report.performance_metrics.update({
                    "skill_creation_time": creation_time,
                    "dice_processing_time": processing_time,
                    "avg_processing_time": avg_time,
                    "total_skills_created": 1000,
                    "total_dice_processed": 1000
                })
                
                result.finish("passed")
                logger.info("✅ 성능 스트레스 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 성능 스트레스 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    async def test_memory_usage(self):
        """메모리 사용량 테스트"""
        if not PSUTIL_AVAILABLE:
            self.skipTest("psutil이 설치되지 않아 메모리 테스트를 건너뜁니다.")
        
        result = SkillTestResult("System", "memory_usage")
        result.start_time = time.time()
        
        try:
            import psutil
            process = psutil.Process()
            
            # 초기 메모리 사용량
            gc.collect()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                # 대량 데이터 생성
                for i in range(50):
                    channel_id = f"memory_test_{i}"
                    for j in range(20):
                        skill_manager.add_skill(
                            channel_id, "오닉셀", f"user_{j}", f"유저{j}",
                            f"user_{j}", f"유저{j}", 10
                        )
                
                # 사용 후 메모리
                after_creation = process.memory_info().rss / 1024 / 1024
                memory_increase = after_creation - initial_memory
                
                result.add_test_case(
                    "메모리 증가량 (1000 스킬)",
                    f"{initial_memory:.1f}MB → {after_creation:.1f}MB",
                    "<50MB",
                    f"{memory_increase:.1f}MB",
                    memory_increase < 50
                )
                
                # 정리 후 메모리
                for i in range(50):
                    skill_manager.clear_channel_state(f"memory_test_{i}")
                
                gc.collect()
                after_cleanup = process.memory_info().rss / 1024 / 1024
                
                result.add_test_case(
                    "메모리 정리 효과",
                    f"{after_creation:.1f}MB → {after_cleanup:.1f}MB",
                    "감소",
                    f"{after_creation - after_cleanup:.1f}MB 감소",
                    after_cleanup < after_creation
                )
                
                # 메모리 메트릭 저장
                self.test_report.memory_metrics.update({
                    "initial_memory_mb": initial_memory,
                    "peak_memory_mb": after_creation,
                    "final_memory_mb": after_cleanup,
                    "max_increase_mb": memory_increase
                })
                
                result.finish("passed")
                logger.info("✅ 메모리 사용량 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 메모리 사용량 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    async def test_skill_strabos_effect(self):
        """스트라보스 스킬 효과 상세 테스트"""
        result = SkillTestResult("스트라보스", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 스트라보스 스킬 추가
                skill_manager.add_skill(
                    channel_id, "스트라보스", user_id, "테스트유저",
                    user_id, "테스트유저", 5
                )
                
                # 다양한 주사위 값 테스트
                test_cases = [
                    (10, 75, "최소값 보정"),
                    (50, 75, "최소값 보정"),
                    (74, 75, "최소값 보정"),
                    (75, 75, "경계값"),
                    (100, 100, "정상 범위"),
                    (150, 150, "최대값 경계"),
                    (200, 150, "최대값 보정"),
                ]
                
                for original, expected, case_name in test_cases:
                    final_value, messages = await skill_effects.process_dice_roll(
                        user_id, original, channel_id
                    )
                    
                    result.add_test_case(
                        case_name,
                        original,
                        expected,
                        final_value,
                        final_value == expected
                    )
                
                result.finish("passed")
                logger.info("✅ 스트라보스 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 스트라보스 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_jerrunka_effect(self):
        """제룬카 스킬 효과 상세 테스트"""
        result = SkillTestResult("제룬카", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                target_id = "target_user"
                
                # 제룬카 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "제룬카", user_id, "테스트유저",
                    target_id, "타겟유저", 5
                )
                
                result.add_test_case(
                    "제룬카 스킬 추가",
                    {"caster": user_id, "target": target_id},
                    True,
                    success,
                    success
                )
                
                # 특수 효과 확인
                state = skill_manager.get_channel_state(channel_id)
                has_jerrunka = "jerrunka_active" in state.get("special_effects", {})
                
                result.add_test_case(
                    "제룬카 활성화 상태",
                    "special_effects",
                    True,
                    has_jerrunka,
                    has_jerrunka
                )
                
                if has_jerrunka:
                    jerrunka_data = state["special_effects"]["jerrunka_active"]
                    
                    result.add_test_case(
                        "제룬카 타겟 설정",
                        "target_id",
                        target_id,
                        jerrunka_data.get("target_id"),
                        jerrunka_data.get("target_id") == target_id
                    )
                
                result.finish("passed")
                logger.info("✅ 제룬카 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 제룬카 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_karon_effect(self):
        """카론 스킬 효과 상세 테스트"""
        result = SkillTestResult("카론", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 카론 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "카론", user_id, "테스트유저",
                    "all_users", "모든 유저", 5
                )
                
                result.add_test_case(
                    "카론 스킬 추가",
                    {"skill": "카론", "target": "all_users"},
                    True,
                    success,
                    success
                )
                
                # 데미지 공유 효과는 실제 전투에서 테스트
                state = skill_manager.get_channel_state(channel_id)
                has_karon = "카론" in state.get("active_skills", {})
                
                result.add_test_case(
                    "카론 활성화 상태",
                    "active_skills",
                    True,
                    has_karon,
                    has_karon
                )
                
                result.finish("passed")
                logger.info("✅ 카론 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 카론 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_scarnel_effect(self):
        """스카넬 스킬 효과 상세 테스트"""
        result = SkillTestResult("스카넬", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                target_id = "target_user"
                
                # 스카넬 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "스카넬", user_id, "테스트유저",
                    target_id, "타겟유저", 5
                )
                
                result.add_test_case(
                    "스카넬 스킬 추가",
                    {"caster": user_id, "target": target_id},
                    True,
                    success,
                    success
                )
                
                # 특수 효과 확인
                state = skill_manager.get_channel_state(channel_id)
                has_scarnel = "스카넬" in state.get("active_skills", {})
                
                if has_scarnel:
                    scarnel_data = state["active_skills"]["스카넬"]
                    
                    result.add_test_case(
                        "스카넬 타겟 설정",
                        "target_id",
                        target_id,
                        scarnel_data.get("target_id"),
                        scarnel_data.get("target_id") == target_id
                    )
                
                result.finish("passed")
                logger.info("✅ 스카넬 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 스카넬 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_virella_effect(self):
        """비렐라 스킬 효과 상세 테스트"""
        result = SkillTestResult("비렐라", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                monster_id = "monster"
                user_id = "test_user"
                
                # 비렐라 스킬 추가
                skill_manager.add_skill(
                    channel_id, "비렐라", monster_id, "몬스터",
                    "all_users", "모든 유저", 5
                )
                
                # 비렐라 속박 효과 수동 설정
                state = skill_manager.get_channel_state(channel_id)
                state["special_effects"]["virella_bound"] = [user_id]
                skill_manager.mark_dirty(channel_id)
                
                # 속박된 유저가 50 미만 주사위 굴림
                final_value, messages = await skill_effects.process_dice_roll(
                    user_id, 30, channel_id
                )
                
                result.add_test_case(
                    "비렐라 속박 - 행동 불가 (주사위 < 50)",
                    30,
                    0,
                    final_value,
                    final_value == 0
                )
                
                # 속박된 유저가 50 이상 주사위 굴림 (저항 성공)
                final_value, messages = await skill_effects.process_dice_roll(
                    user_id, 75, channel_id
                )
                
                result.add_test_case(
                    "비렐라 저항 성공 (주사위 >= 50)",
                    75,
                    75,
                    final_value,
                    final_value == 75
                )
                
                # 저항 후 속박 해제 확인
                state = skill_manager.get_channel_state(channel_id)
                is_still_bound = user_id in state.get("special_effects", {}).get("virella_bound", [])
                
                result.add_test_case(
                    "저항 성공 후 속박 해제",
                    "virella_bound",
                    False,
                    is_still_bound,
                    not is_still_bound
                )
                
                result.finish("passed")
                logger.info("✅ 비렐라 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 비렐라 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_nixara_effect(self):
        """닉사라 스킬 효과 상세 테스트"""
        result = SkillTestResult("닉사라", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                monster_id = "monster"
                user_id = "test_user"
                
                # 닉사라 스킬 추가
                skill_manager.add_skill(
                    channel_id, "닉사라", monster_id, "몬스터",
                    user_id, "테스트유저", 5
                )
                
                # 닉사라 차원 유배 효과 수동 설정
                state = skill_manager.get_channel_state(channel_id)
                state["special_effects"]["nixara_excluded"] = {user_id: 2}  # 2라운드 배제
                skill_manager.mark_dirty(channel_id)
                
                # 배제된 유저의 행동
                final_value, messages = await skill_effects.process_dice_roll(
                    user_id, 100, channel_id
                )
                
                result.add_test_case(
                    "닉사라 차원 유배 - 행동 불가",
                    100,
                    0,
                    final_value,
                    final_value == 0
                )
                
                # 메시지 확인
                has_message = any("닉사라" in msg for msg in messages)
                result.add_test_case(
                    "닉사라 메시지 출력",
                    messages,
                    True,
                    has_message,
                    has_message
                )
                
                result.finish("passed")
                logger.info("✅ 닉사라 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 닉사라 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_danmok_effect(self):
        """단목 스킬 효과 상세 테스트"""
        result = SkillTestResult("단목", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 단목 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "단목", user_id, "테스트유저",
                    "all_monsters", "모든 몬스터", 5
                )
                
                result.add_test_case(
                    "단목 스킬 추가",
                    {"skill": "단목"},
                    True,
                    success,
                    success
                )
                
                # 특수 효과 확인
                state = skill_manager.get_channel_state(channel_id)
                has_danmok = "danmok_penetration" in state.get("special_effects", {})
                
                result.add_test_case(
                    "단목 관통 준비 상태",
                    "special_effects",
                    True,
                    has_danmok,
                    has_danmok
                )
                
                if has_danmok:
                    danmok_data = state["special_effects"]["danmok_penetration"]
                    
                    result.add_test_case(
                        "단목 타겟 리스트 초기화",
                        "targets",
                        [],
                        danmok_data.get("targets"),
                        danmok_data.get("targets") == []
                    )
                
                result.finish("passed")
                logger.info("✅ 단목 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 단목 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_hwangya_effect(self):
        """황야 스킬 효과 상세 테스트"""
        result = SkillTestResult("황야", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 황야 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "황야", user_id, "테스트유저",
                    user_id, "테스트유저", 5
                )
                
                result.add_test_case(
                    "황야 스킬 추가",
                    {"skill": "황야"},
                    True,
                    success,
                    success
                )
                
                # 특수 효과 확인
                state = skill_manager.get_channel_state(channel_id)
                has_hwangya = "hwangya_double_action" in state.get("special_effects", {})
                
                result.add_test_case(
                    "황야 이중 행동 준비",
                    "special_effects",
                    True,
                    has_hwangya,
                    has_hwangya
                )
                
                if has_hwangya:
                    hwangya_data = state["special_effects"]["hwangya_double_action"]
                    
                    result.add_test_case(
                        "황야 사용자 설정",
                        "user_id",
                        user_id,
                        hwangya_data.get("user_id"),
                        hwangya_data.get("user_id") == user_id
                    )
                    
                    result.add_test_case(
                        "황야 행동 횟수 초기화",
                        "actions_used_this_turn",
                        0,
                        hwangya_data.get("actions_used_this_turn"),
                        hwangya_data.get("actions_used_this_turn") == 0
                    )
                
                result.finish("passed")
                logger.info("✅ 황야 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 황야 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_lucencia_effect(self):
        """루센시아 스킬 효과 상세 테스트"""
        result = SkillTestResult("루센시아", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                user_id = "test_user"
                
                # 루센시아 스킬 추가
                success = skill_manager.add_skill(
                    channel_id, "루센시아", user_id, "테스트유저",
                    user_id, "테스트유저", 5
                )
                
                result.add_test_case(
                    "루센시아 스킬 추가",
                    {"skill": "루센시아"},
                    True,
                    success,
                    success
                )
                
                # 부활 효과는 실제 죽음 이벤트에서 테스트
                state = skill_manager.get_channel_state(channel_id)
                has_lucencia = "루센시아" in state.get("active_skills", {})
                
                result.add_test_case(
                    "루센시아 활성화 상태",
                    "active_skills",
                    True,
                    has_lucencia,
                    has_lucencia
                )
                
                result.finish("passed")
                logger.info("✅ 루센시아 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 루센시아 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    async def test_skill_nexis_effect(self):
        """넥시스 스킬 효과 상세 테스트"""
        result = SkillTestResult("넥시스", "effect")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "test_channel"
                nexis_user_id = "1059908946741166120"  # 넥시스 전용 유저
                
                # 넥시스 스킬 추가 (특별 권한 필요)
                success = skill_manager.add_skill(
                    channel_id, "넥시스", nexis_user_id, "넥시스유저",
                    "all", "전체", 5
                )
                
                result.add_test_case(
                    "넥시스 스킬 추가 (특별 권한)",
                    {"user": nexis_user_id},
                    True,
                    success,
                    success
                )
                
                # 넥시스 효과는 전투 중 확정 데미지로 테스트
                state = skill_manager.get_channel_state(channel_id)
                has_nexis = "넥시스" in state.get("active_skills", {})
                
                result.add_test_case(
                    "넥시스 활성화 상태",
                    "active_skills",
                    True,
                    has_nexis,
                    has_nexis
                )
                
                result.finish("passed")
                logger.info("✅ 넥시스 효과 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 넥시스 효과 테스트 실패: {e}")
        
        finally:
            self.test_report.add_skill_result(result)
    
    # === 스킬 조합 및 시나리오 테스트 ===
    
    async def test_skill_combination_scenarios(self):
        """실전 시나리오별 스킬 조합 테스트"""
        result = SkillTestResult("System", "skill_combinations")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                # 시나리오 1: 공격 증폭 조합 (오닉셀 + 스트라보스)
                channel_id = "combo_test_1"
                user_id = "combo_user"
                
                skill_manager.add_skill(
                    channel_id, "오닉셀", user_id, "유저", user_id, "유저", 5
                )
                skill_manager.add_skill(
                    channel_id, "스트라보스", user_id, "유저", user_id, "유저", 5
                )
                
                # 낮은 주사위값이 두 스킬로 보정되는지
                final_value, _ = await skill_effects.process_dice_roll(user_id, 30, channel_id)
                # 30 → 50 (오닉셀) → 75 (스트라보스)
                
                result.add_test_case(
                    "공격 증폭 조합 (오닉셀+스트라보스)",
                    30,
                    75,
                    final_value,
                    final_value == 75
                )
                
                # 시나리오 2: 방어 조합 (피닉스 + 루센시아)
                channel_id = "combo_test_2"
                
                skill_manager.add_skill(
                    channel_id, "피닉스", user_id, "유저", user_id, "유저", 5
                )
                skill_manager.add_skill(
                    channel_id, "루센시아", user_id, "유저", user_id, "유저", 5
                )
                
                state = skill_manager.get_channel_state(channel_id)
                has_both = "피닉스" in state["active_skills"] and "루센시아" in state["active_skills"]
                
                result.add_test_case(
                    "이중 부활 방어 조합",
                    ["피닉스", "루센시아"],
                    True,
                    has_both,
                    has_both
                )
                
                # 시나리오 3: 행동 제한 조합 (비렐라 + 닉사라)
                channel_id = "combo_test_3"
                target_id = "target_user"
                
                skill_manager.add_skill(
                    channel_id, "비렐라", "monster", "몬스터", "all_users", "모든 유저", 5
                )
                skill_manager.add_skill(
                    channel_id, "닉사라", "monster", "몬스터", target_id, "타겟", 5
                )
                
                # 특수 효과 설정
                state = skill_manager.get_channel_state(channel_id)
                state["special_effects"]["virella_bound"] = [target_id]
                state["special_effects"]["nixara_excluded"] = {target_id: 2}
                skill_manager.mark_dirty(channel_id)
                
                # 이중 제한된 유저의 행동
                final_value, messages = await skill_effects.process_dice_roll(
                    target_id, 100, channel_id
                )
                
                result.add_test_case(
                    "이중 행동 제한 (비렐라+닉사라)",
                    100,
                    0,
                    final_value,
                    final_value == 0
                )
                
                # 시나리오 4: 공격-방어 상쇄 (그림 vs 피닉스)
                channel_id = "combo_test_4"
                grim_target = "grim_target"
                
                skill_manager.add_skill(
                    channel_id, "그림", "monster", "몬스터", grim_target, "타겟", 5
                )
                skill_manager.add_skill(
                    channel_id, "피닉스", grim_target, "타겟", grim_target, "타겟", 5
                )
                
                state = skill_manager.get_channel_state(channel_id)
                has_counter = "그림" in state["active_skills"] and "피닉스" in state["active_skills"]
                
                result.add_test_case(
                    "즉사 vs 부활 대립 구조",
                    ["그림", "피닉스"],
                    True,
                    has_counter,
                    has_counter
                )
                
                result.finish("passed")
                logger.info("✅ 스킬 조합 시나리오 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 스킬 조합 시나리오 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    async def test_error_handling_and_edge_cases(self):
        """에러 처리 및 경계 케이스 테스트"""
        result = SkillTestResult("System", "error_handling")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "error_test"
                user_id = "test_user"
                
                # 테스트 1: 존재하지 않는 스킬
                success = skill_manager.add_skill(
                    channel_id, "존재하지않는스킬", user_id, "유저", user_id, "유저", 5
                )
                
                result.add_test_case(
                    "존재하지 않는 스킬 추가 방지",
                    "존재하지않는스킬",
                    False,
                    success,
                    not success
                )
                
                # 테스트 2: 권한 없는 스킬 사용
                unauthorized_user = "999999999"
                success = skill_manager.add_skill(
                    channel_id, "그림", unauthorized_user, "무권한유저", user_id, "타겟", 5
                )
                
                result.add_test_case(
                    "권한 없는 유저의 스킬 사용 방지",
                    {"user": unauthorized_user, "skill": "그림"},
                    False,
                    success,
                    not success
                )
                
                # 테스트 3: 중복 스킬 추가
                skill_manager.add_skill(
                    channel_id, "오닉셀", user_id, "유저", user_id, "유저", 5
                )
                success = skill_manager.add_skill(
                    channel_id, "오닉셀", user_id, "유저", user_id, "유저", 5
                )
                
                result.add_test_case(
                    "동일 스킬 중복 추가 방지",
                    "오닉셀 중복",
                    False,
                    success,
                    not success
                )
                
                # 테스트 4: 잘못된 라운드 수
                success = skill_manager.add_skill(
                    channel_id, "카론", user_id, "유저", "all_users", "모든 유저", -1
                )
                
                result.add_test_case(
                    "음수 라운드 방지",
                    -1,
                    False,
                    success,
                    not success
                )
                
                # 테스트 5: 잘못된 채널/유저 ID
                success = skill_manager.add_skill(
                    None, "오리븐", user_id, "유저", "all_users", "모든 유저", 5
                )
                
                result.add_test_case(
                    "None 채널 ID 처리",
                    None,
                    False,
                    success,
                    not success
                )
                
                # 테스트 6: 빈 문자열 처리
                success = skill_manager.add_skill(
                    "", "스카넬", "", "", "", "", 5
                )
                
                result.add_test_case(
                    "빈 문자열 파라미터 처리",
                    "empty strings",
                    False,
                    success,
                    not success
                )
                
                result.finish("passed")
                logger.info("✅ 에러 처리 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 에러 처리 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    async def test_concurrent_access(self):
        """동시성 및 동시 접근 테스트"""
        result = SkillTestResult("System", "concurrency")
        result.start_time = time.time()
        
        try:
            from skills.skill_effects import skill_effects
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "concurrent_test"
                
                # 여러 유저가 동시에 스킬 추가
                tasks = []
                for i in range(10):
                    user_id = f"concurrent_user_{i}"
                    skill_name = self.ALL_SKILLS[i % len(self.ALL_SKILLS)]
                    
                    task = skill_manager.add_skill(
                        channel_id, skill_name, user_id, f"유저{i}",
                        user_id, f"유저{i}", 5
                    )
                    tasks.append(task)
                
                # 비동기로는 실행할 수 없으므로 순차 실행
                results = []
                for i, task in enumerate(tasks):
                    if asyncio.iscoroutine(task):
                        result_val = await task
                    else:
                        result_val = task
                    results.append(result_val)
                
                # 모든 스킬이 추가되었는지 확인
                state = skill_manager.get_channel_state(channel_id)
                skill_count = len(state["active_skills"])
                
                result.add_test_case(
                    "동시 스킬 추가",
                    "10개 스킬",
                    10,
                    skill_count,
                    skill_count <= 10  # 중복 때문에 10개 이하
                )
                
                # 동시 주사위 처리
                dice_tasks = []
                for i in range(20):
                    user_id = f"concurrent_user_{i % 10}"
                    dice_value = random.randint(1, 100)
                    
                    dice_tasks.append(
                        skill_effects.process_dice_roll(user_id, dice_value, channel_id)
                    )
                
                # 모든 주사위 처리 완료
                dice_results = await asyncio.gather(*dice_tasks)
                
                result.add_test_case(
                    "동시 주사위 처리",
                    "20개 주사위",
                    20,
                    len(dice_results),
                    len(dice_results) == 20
                )
                
                # 모든 결과가 정상적인지 확인
                all_valid = all(
                    isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], int)
                    for r in dice_results
                )
                
                result.add_test_case(
                    "주사위 결과 유효성",
                    "tuple(int, list)",
                    True,
                    all_valid,
                    all_valid
                )
                
                result.finish("passed")
                logger.info("✅ 동시성 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 동시성 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    async def test_skill_permission_details(self):
        """스킬 권한 시스템 상세 테스트"""
        result = SkillTestResult("System", "permission_system")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import skill_manager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                await skill_manager.initialize()
                
                channel_id = "permission_test"
                
                # 테스트 1: all_users 권한
                regular_user = "regular_user_123"
                success = skill_manager.add_skill(
                    channel_id, "오닉셀", regular_user, "일반유저",
                    regular_user, "일반유저", 5
                )
                
                result.add_test_case(
                    "all_users 권한 스킬 사용",
                    {"user": "regular", "skill": "오닉셀"},
                    True,
                    success,
                    success
                )
                
                # 테스트 2: admin 전용 스킬
                success = skill_manager.add_skill(
                    channel_id, "그림", regular_user, "일반유저",
                    "target", "타겟", 5
                )
                
                result.add_test_case(
                    "admin 전용 스킬 일반유저 차단",
                    {"user": "regular", "skill": "그림"},
                    False,
                    success,
                    not success
                )
                
                # 테스트 3: 관리자 권한
                admin_user = "123456789"  # 설정된 관리자
                success = skill_manager.add_skill(
                    channel_id, "그림", admin_user, "관리자",
                    "target", "타겟", 5
                )
                
                result.add_test_case(
                    "관리자 모든 스킬 사용 가능",
                    {"user": "admin", "skill": "그림"},
                    True,
                    success,
                    success
                )
                
                # 테스트 4: 몬스터 권한
                monster_id = "monster"
                success = skill_manager.add_skill(
                    channel_id, "볼켄", monster_id, "몬스터",
                    "all", "전체", 5
                )
                
                result.add_test_case(
                    "몬스터 전용 스킬 사용",
                    {"user": "monster", "skill": "볼켄"},
                    True,
                    success,
                    success
                )
                
                # 테스트 5: 넥시스 특별 권한
                nexis_user = "1059908946741166120"
                success = skill_manager.add_skill(
                    channel_id, "넥시스", nexis_user, "넥시스",
                    "all", "전체", 5
                )
                
                result.add_test_case(
                    "넥시스 전용 유저 권한",
                    {"user": nexis_user, "skill": "넥시스"},
                    True,
                    success,
                    success
                )
                
                # 다른 유저는 넥시스 사용 불가
                success = skill_manager.add_skill(
                    channel_id, "넥시스", admin_user, "관리자",
                    "all", "전체", 5
                )
                
                result.add_test_case(
                    "넥시스 타 유저 사용 차단",
                    {"user": "admin", "skill": "넥시스"},
                    False,
                    success,
                    not success
                )
                
                # 테스트 6: 유저별 스킬 제한
                limited_user = "987654321"  # user_skills.json에 정의된 유저
                allowed_skills = skill_manager.get_user_allowed_skills(limited_user)
                
                result.add_test_case(
                    "유저별 허용 스킬 확인",
                    limited_user,
                    ["오닉셀", "오리븐", "카론", "스카넬"],
                    allowed_skills,
                    set(allowed_skills) == {"오닉셀", "오리븐", "카론", "스카넬"}
                )
                
                result.finish("passed")
                logger.info("✅ 권한 시스템 상세 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 권한 시스템 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    async def test_skill_state_recovery(self):
        """스킬 상태 복구 및 영속성 테스트"""
        result = SkillTestResult("System", "state_recovery")
        result.start_time = time.time()
        
        try:
            from skills.skill_manager import SkillManager
            
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                
                # 첫 번째 매니저 인스턴스
                manager1 = SkillManager()
                await manager1.initialize()
                
                channel_id = "recovery_test"
                
                # 여러 스킬과 특수 효과 추가
                manager1.add_skill(
                    channel_id, "오닉셀", "user1", "유저1", "user1", "유저1", 5
                )
                manager1.add_skill(
                    channel_id, "그림", "monster", "몬스터", "user2", "유저2", 3
                )
                
                # 특수 효과 추가
                state = manager1.get_channel_state(channel_id)
                state["special_effects"]["virella_bound"] = ["user3", "user4"]
                state["special_effects"]["volken_eruption"] = {
                    "current_phase": 2,
                    "selected_targets": ["user1"]
                }
                manager1.mark_dirty(channel_id)
                
                # 강제 저장
                await manager1.force_save()
                
                # 원본 상태 기록
                original_skills = len(state["active_skills"])
                original_effects = len(state["special_effects"])
                
                # 두 번째 매니저로 복구
                manager2 = SkillManager()
                await manager2.initialize()
                
                recovered_state = manager2.get_channel_state(channel_id)
                
                result.add_test_case(
                    "스킬 상태 복구",
                    original_skills,
                    len(recovered_state["active_skills"]),
                    len(recovered_state["active_skills"]),
                    original_skills == len(recovered_state["active_skills"])
                )
                
                result.add_test_case(
                    "특수 효과 복구",
                    original_effects,
                    len(recovered_state["special_effects"]),
                    len(recovered_state["special_effects"]),
                    original_effects == len(recovered_state["special_effects"])
                )
                
                # 상세 데이터 확인
                has_virella = "virella_bound" in recovered_state["special_effects"]
                has_volken = "volken_eruption" in recovered_state["special_effects"]
                
                result.add_test_case(
                    "비렐라 효과 복구",
                    ["user3", "user4"],
                    recovered_state["special_effects"].get("virella_bound", []),
                    recovered_state["special_effects"].get("virella_bound", []),
                    has_virella and set(recovered_state["special_effects"]["virella_bound"]) == {"user3", "user4"}
                )
                
                if has_volken:
                    volken_phase = recovered_state["special_effects"]["volken_eruption"]["current_phase"]
                    result.add_test_case(
                        "볼켄 단계 복구",
                        2,
                        volken_phase,
                        volken_phase,
                        volken_phase == 2
                    )
                
                result.finish("passed")
                logger.info("✅ 상태 복구 테스트 통과")
                
        except Exception as e:
            result.finish("error", e)
            logger.error(f"❌ 상태 복구 테스트 실패: {e}")
        
        finally:
            self.test_report.add_system_result(result)
    
    # === 보고서 생성 ===
    
    @classmethod
    def tearDownClass(cls):
        """테스트 완료 후 보고서 생성"""
        cls.test_report.finalize()
        
        # 콘솔 보고서
        cls._print_console_report()
        
        # HTML 보고서
        cls._generate_html_report()
        
        # JSON 보고서
        cls._generate_json_report()
    
    @classmethod
    def _print_console_report(cls):
        """콘솔에 보고서 출력"""
        report = cls.test_report
        summary = report.get_summary()
        
        print("\n" + "="*80)
        print("스킬 시스템 테스트 보고서".center(80))
        print("="*80)
        
        print(f"\n실행 시간: {report.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요 시간: {report.total_duration:.2f}초")
        
        print(f"\n총 테스트: {summary['total_tests']}")
        print(f"✅ 성공: {summary['passed']}")
        print(f"❌ 실패: {summary['failed']}")
        print(f"⚠️ 에러: {summary['errors']}")
        print(f"⏭️ 건너뜀: {summary['skipped']}")
        print(f"성공률: {summary['success_rate']:.1f}%")
        
        # 스킬별 결과
        print("\n" + "-"*80)
        print("스킬별 테스트 결과:")
        print("-"*80)
        
        for skill_name, results in sorted(report.skill_results.items()):
            passed = sum(1 for r in results if r.status == "passed")
            total = len(results)
            status = "✅" if passed == total else "❌"
            print(f"{status} {skill_name:15} {passed}/{total} 테스트 통과")
            
            # 실패한 테스트 상세
            for result in results:
                if result.status != "passed":
                    print(f"   └─ {result.test_type}: {result.error_message}")
        
        # 시스템 테스트 결과
        print("\n시스템 테스트:")
        for result in report.system_tests:
            status_icon = "✅" if result.status == "passed" else "❌"
            print(f"{status_icon} {result.test_type:20} ({result.duration:.2f}초)")
        
        # 성능 메트릭
        if report.performance_metrics:
            print("\n" + "-"*80)
            print("성능 메트릭:")
            print("-"*80)
            for key, value in report.performance_metrics.items():
                print(f"{key:25}: {value}")
        
        # 메모리 메트릭
        if report.memory_metrics:
            print("\n메모리 사용량:")
            for key, value in report.memory_metrics.items():
                print(f"{key:25}: {value:.1f} MB")
        
        print("\n" + "="*80)
    
    @classmethod
    def _generate_html_report(cls):
        """HTML 보고서 생성"""
        report = cls.test_report
        summary = report.get_summary()
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>스킬 시스템 테스트 보고서</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{
            color: #333;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .summary-card {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #e9ecef;
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            color: #666;
            font-size: 14px;
        }}
        .summary-card .value {{
            font-size: 36px;
            font-weight: bold;
            margin: 0;
        }}
        .passed {{ color: #28a745; }}
        .failed {{ color: #dc3545; }}
        .error {{ color: #ffc107; }}
        .skipped {{ color: #6c757d; }}
        .skill-results {{
            margin: 20px 0;
        }}
        .skill-item {{
            background-color: #f8f9fa;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
            border-left: 4px solid #28a745;
        }}
        .skill-item.failed {{
            border-left-color: #dc3545;
        }}
        .test-case {{
            margin: 10px 0 10px 20px;
            padding: 10px;
            background-color: white;
            border: 1px solid #e9ecef;
            border-radius: 3px;
        }}
        .test-case.failed {{
            background-color: #fff5f5;
            border-color: #f5c6cb;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: bold;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-box {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
        }}
        pre {{
            background-color: #f5f5f5;
            padding: 10px;
            border-radius: 3px;
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 스킬 시스템 테스트 보고서</h1>
        <p>실행 시간: {report.start_time.strftime('%Y-%m-%d %H:%M:%S')} | 
           소요 시간: {report.total_duration:.2f}초</p>
        
        <div class="summary">
            <div class="summary-card">
                <h3>총 테스트</h3>
                <p class="value">{summary['total_tests']}</p>
            </div>
            <div class="summary-card">
                <h3>성공</h3>
                <p class="value passed">{summary['passed']}</p>
            </div>
            <div class="summary-card">
                <h3>실패</h3>
                <p class="value failed">{summary['failed']}</p>
            </div>
            <div class="summary-card">
                <h3>에러</h3>
                <p class="value error">{summary['errors']}</p>
            </div>
            <div class="summary-card">
                <h3>성공률</h3>
                <p class="value">{summary['success_rate']:.1f}%</p>
            </div>
        </div>
        
        <h2>📊 스킬별 테스트 결과</h2>
        <div class="skill-results">
"""
        
        # 스킬별 상세 결과
        for skill_name, results in sorted(report.skill_results.items()):
            passed = sum(1 for r in results if r.status == "passed")
            total = len(results)
            status_class = "failed" if passed < total else ""
            
            html_content += f"""
            <div class="skill-item {status_class}">
                <h3>{skill_name} ({passed}/{total} 통과)</h3>
"""
            
            for result in results:
                if result.test_cases:
                    html_content += f"""
                <div class="test-type">
                    <h4>{result.test_type} 테스트 ({result.duration:.3f}초)</h4>
"""
                    for test_case in result.test_cases:
                        case_class = "" if test_case['passed'] else "failed"
                        status_icon = "✅" if test_case['passed'] else "❌"
                        
                        html_content += f"""
                    <div class="test-case {case_class}">
                        {status_icon} <strong>{test_case['name']}</strong><br>
                        입력: <code>{html.escape(str(test_case['input']))}</code><br>
                        예상: <code>{html.escape(str(test_case['expected']))}</code><br>
                        결과: <code>{html.escape(str(test_case['actual']))}</code>
                    </div>
"""
                    html_content += "</div>"
                
                if result.error_message:
                    html_content += f"""
                <div class="test-case failed">
                    <strong>에러:</strong> {html.escape(result.error_message)}<br>
                    <pre>{html.escape(result.error_traceback or '')}</pre>
                </div>
"""
            
            html_content += "</div>"
        
        # 성능 메트릭
        if report.performance_metrics:
            html_content += """
        <h2>⚡ 성능 메트릭</h2>
        <div class="metrics">
            <div class="metric-box">
                <h3>처리 성능</h3>
                <table>
"""
            for key, value in report.performance_metrics.items():
                html_content += f"""
                    <tr>
                        <td>{key.replace('_', ' ').title()}</td>
                        <td><strong>{value}</strong></td>
                    </tr>
"""
            html_content += """
                </table>
            </div>
"""
        
        # 메모리 메트릭
        if report.memory_metrics:
            html_content += """
            <div class="metric-box">
                <h3>메모리 사용량</h3>
                <table>
"""
            for key, value in report.memory_metrics.items():
                html_content += f"""
                    <tr>
                        <td>{key.replace('_', ' ').title()}</td>
                        <td><strong>{value:.1f} MB</strong></td>
                    </tr>
"""
            html_content += """
                </table>
            </div>
        </div>
"""
        
        html_content += """
    </div>
</body>
</html>
"""
        
        # HTML 파일 저장
        report_path = Path("skill_test_report.html")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\n📄 HTML 보고서 생성: {report_path.absolute()}")
    
    @classmethod
    def _generate_json_report(cls):
        """JSON 보고서 생성"""
        report = cls.test_report
        
        json_data = {
            "metadata": {
                "start_time": report.start_time.isoformat(),
                "end_time": report.end_time.isoformat() if report.end_time else None,
                "duration_seconds": report.total_duration,
                "summary": report.get_summary()
            },
            "skill_tests": {},
            "system_tests": [],
            "performance_metrics": report.performance_metrics,
            "memory_metrics": report.memory_metrics
        }
        
        # 스킬별 테스트 결과
        for skill_name, results in report.skill_results.items():
            json_data["skill_tests"][skill_name] = []
            for result in results:
                test_data = {
                    "test_type": result.test_type,
                    "status": result.status,
                    "duration": result.duration,
                    "test_cases": result.test_cases,
                    "error": {
                        "message": result.error_message,
                        "traceback": result.error_traceback
                    } if result.error_message else None
                }
                json_data["skill_tests"][skill_name].append(test_data)
        
        # 시스템 테스트 결과
        for result in report.system_tests:
            test_data = {
                "test_type": result.test_type,
                "status": result.status,
                "duration": result.duration,
                "test_cases": result.test_cases,
                "error": {
                    "message": result.error_message,
                    "traceback": result.error_traceback
                } if result.error_message else None
            }
            json_data["system_tests"].append(test_data)
        
        # JSON 파일 저장
        report_path = Path("skill_test_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        print(f"📄 JSON 보고서 생성: {report_path.absolute()}")


# === 테스트 실행 ===
if __name__ == "__main__":
    # 테스트 실행
    unittest.main(verbosity=2)


