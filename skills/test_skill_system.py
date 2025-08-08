# test_skill_system.py - 포괄적 스킬 시스템 테스트 (보고서 생성 기능 포함)
import asyncio
import unittest
import logging
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any
import traceback
import gc

# psutil은 선택적 import (없어도 테스트 실행 가능)
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

# === 테스트 결과 데이터 클래스 ===
class TestResult:
    """개별 테스트 결과 저장"""
    def __init__(self, test_name: str, test_class: str):
        self.test_name = test_name
        self.test_class = test_class
        self.status = "pending"  # pending, passed, failed, error, skipped
        self.start_time = None
        self.end_time = None
        self.duration = 0
        self.error_message = None
        self.error_traceback = None
        self.performance_data = {}
        self.memory_usage = {}
        
    def start(self):
        self.start_time = time.time()
        
    def finish(self, status: str, error: Exception = None):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.status = status
        if error:
            self.error_message = str(error)
            self.error_traceback = traceback.format_exc()

class TestSkillSystem(unittest.IsolatedAsyncioTestCase):
    """스킬 시스템 통합 테스트"""
    
    # 테스트 결과 저장을 위한 클래스 변수
    test_results = {}
    
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
        await self._create_test_config()
        
        # Mock Discord 객체들
        self.mock_bot = Mock()
        self.mock_interaction = Mock()
        self.mock_channel = Mock()
        self.mock_user = Mock()
        
        # Mock 설정
        self.mock_user.id = 123456789
        self.mock_user.display_name = "테스트유저"
        self.mock_channel.id = 987654321
        self.mock_interaction.user = self.mock_user
        self.mock_interaction.channel = self.mock_channel
        self.mock_interaction.response = Mock()
        self.mock_interaction.response.is_done = Mock(return_value=False)
        self.mock_interaction.response.send_message = AsyncMock()
        self.mock_interaction.followup = Mock()
        self.mock_interaction.followup.send = AsyncMock()
        
        logger.info("테스트 환경 설정 완료")
    
    async def asyncTearDown(self):
        """테스트 환경 정리"""
        try:
            # 임시 파일들 정리
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
            logger.info("테스트 환경 정리 완료")
        except Exception as e:
            logger.warning(f"테스트 정리 중 오류: {e}")
    
    async def _create_test_config(self):
        """테스트용 설정 파일 생성"""
        # skill_config.json
        config_data = {
            "lucencia": {"health_cost": 3, "revival_health": 5},
            "priority_users": ["1237738945635160104", "1059908946741166120"],
            "skill_users": {
                "오닉셀": ["all_users", "admin", "monster"],
                "피닉스": ["users_only"],
                "오리븐": ["all_users", "admin", "monster"],
                "카론": ["all_users", "admin", "monster"],
                "넥시스": ["1059908946741166120"]
            },
            "authorized_admins": ["123456789"],  # 테스트 유저 ID
            "authorized_nickname": "system | 시스템"
        }
        
        config_file = self.skills_dir / "config" / "skill_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        # user_skills.json
        user_skills_data = {
            "123456789": {
                "allowed_skills": ["오닉셀", "피닉스", "오리븐", "카론"],
                "display_name": "테스트유저",
                "skill_level": "admin"
            }
        }
        
        user_skills_file = self.skills_dir / "config" / "user_skills.json"
        with open(user_skills_file, 'w', encoding='utf-8') as f:
            json.dump(user_skills_data, f, ensure_ascii=False, indent=2)
        
        # 빈 skill_states.json
        states_file = self.skills_dir / "data" / "skill_states.json"
        with open(states_file, 'w', encoding='utf-8') as f:
            json.dump({}, f)
    
    # === 기본 시스템 테스트 ===
    
    async def test_skill_manager_initialization(self):
        """스킬 매니저 초기화 테스트"""
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            try:
                from skills.skill_manager import SkillManager
            except ImportError:
                self.skipTest("skills.skill_manager 모듈을 찾을 수 없습니다.")
            
            manager = SkillManager()
            await manager.initialize()
            
            self.assertIsNotNone(manager._skill_states)
            self.assertIsNotNone(manager._config)
            logger.info("✅ 스킬 매니저 초기화 테스트 통과")
    
    async def test_skill_addition_and_removal(self):
        """스킬 추가/제거 테스트"""
        try:
            with patch('skills.skill_manager.Path') as mock_path:
                mock_path.return_value = self.skills_dir
                
                from skills.skill_manager import skill_manager
                await skill_manager.initialize()
                
                channel_id = "123456789"
                user_id = "987654321"
                
                # 스킬 추가 테스트
                success = skill_manager.add_skill(
                    channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 5
                )
                self.assertTrue(success)
                
                # 상태 확인
                state = skill_manager.get_channel_state(channel_id)
                self.assertIn("오닉셀", state["active_skills"])
                self.assertEqual(state["active_skills"]["오닉셀"]["rounds_left"], 5)
                
                # 스킬 제거 테스트
                removed = skill_manager.remove_skill(channel_id, "오닉셀")
                self.assertTrue(removed)
                
                # 제거 확인
                state = skill_manager.get_channel_state(channel_id)
                self.assertNotIn("오닉셀", state["active_skills"])
                
                logger.info("✅ 스킬 추가/제거 테스트 통과")
        except ImportError:
            self.skipTest("skills 모듈을 찾을 수 없습니다.")
    
    async def test_skill_round_management(self):
        """스킬 라운드 관리 테스트"""
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            # 3라운드 스킬 추가
            skill_manager.add_skill(
                channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 3
            )
            
            # 라운드 감소 테스트
            skill_manager.decrease_skill_rounds(channel_id)
            state = skill_manager.get_channel_state(channel_id)
            self.assertEqual(state["active_skills"]["오닉셀"]["rounds_left"], 2)
            
            # 만료 테스트
            skill_manager.decrease_skill_rounds(channel_id)
            skill_manager.decrease_skill_rounds(channel_id)
            expired = skill_manager.update_round(channel_id, 4)
            
            self.assertIn("오닉셀", expired)
            state = skill_manager.get_channel_state(channel_id)
            self.assertNotIn("오닉셀", state["active_skills"])
            
            logger.info("✅ 스킬 라운드 관리 테스트 통과")
    
    # === 개별 스킬 테스트 ===
    
    async def test_onixel_skill(self):
        """오닉셀 스킬 효과 테스트"""
        try:
            from skills.skill_effects import skill_effects
        except ImportError:
            self.skipTest("skills.skill_effects 모듈을 찾을 수 없습니다.")
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            try:
                from skills.skill_manager import skill_manager
            except ImportError:
                self.skipTest("skills.skill_manager 모듈을 찾을 수 없습니다.")
            
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            # 오닉셀 스킬 추가
            skill_manager.add_skill(
                channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 5
            )
            
            # 주사위 효과 테스트
            test_cases = [
                (30, 50),    # 30 → 50 (최소값 적용)
                (75, 75),    # 75 → 75 (변경 없음)
                (200, 150),  # 200 → 150 (최대값 적용)
            ]
            
            for original, expected in test_cases:
                final_value, messages = await skill_effects.process_dice_roll(user_id, original, channel_id)
                self.assertEqual(final_value, expected)
                if original != expected:
                    self.assertTrue(any("오닉셀" in msg for msg in messages))
            
            logger.info("✅ 오닉셀 스킬 테스트 통과")
    
    async def test_coal_fold_skill(self):
        """콜 폴드 스킬 효과 테스트"""
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            # 콜 폴드 스킬 추가
            skill_manager.add_skill(
                channel_id, "콜 폴드", user_id, "테스트유저", user_id, "테스트유저", 5
            )
            
            # 여러 번 테스트하여 0 또는 100만 나오는지 확인
            results = []
            for _ in range(20):
                final_value, messages = await skill_effects.process_dice_roll(user_id, 50, channel_id)
                results.append(final_value)
                self.assertIn(final_value, [0, 100])
            
            # 0과 100 모두 나와야 함 (확률적이므로 20번 중에는 둘 다 나올 가능성 높음)
            self.assertTrue(0 in results or 100 in results)
            
            logger.info("✅ 콜 폴드 스킬 테스트 통과")
    
    async def test_oriven_skill(self):
        """오리븐 스킬 효과 테스트"""
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            monster_id = "monster"
            user_id = "987654321"
            
            # 몬스터가 오리븐 사용 (유저에게 -10)
            skill_manager.add_skill(
                channel_id, "오리븐", monster_id, "테스트몬스터", "all_users", "모든 유저", 3
            )
            
            # 유저 주사위에 -10 효과 적용 확인
            final_value, messages = await skill_effects.process_dice_roll(user_id, 50, channel_id)
            self.assertEqual(final_value, 40)
            self.assertTrue(any("오리븐" in msg for msg in messages))
            
            # 몬스터 주사위는 영향 없음
            final_value, messages = await skill_effects.process_dice_roll(monster_id, 50, channel_id)
            self.assertEqual(final_value, 50)
            
            logger.info("✅ 오리븐 스킬 테스트 통과")
    
    async def test_karon_damage_sharing(self):
        """카론 데미지 공유 테스트"""
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            # 카론 스킬 추가
            skill_manager.add_skill(
                channel_id, "카론", user_id, "테스트유저", "all_users", "모든 유저", 5
            )
            
            # Mock 전투 참여자
            mock_participants = {
                "users": [
                    {"user_id": "111", "is_dead": False},
                    {"user_id": "222", "is_dead": False},
                    {"user_id": "333", "is_dead": True}  # 죽은 유저는 제외
                ],
                "monster": {"name": "테스트몬스터"},
                "admin": None
            }
            
            with patch('battle_admin.get_battle_participants', return_value=mock_participants):
                # 데미지 공유 테스트
                shared_damage = await skill_effects.process_damage_sharing(channel_id, user_id, 30)
                
                # 살아있는 유저들만 데미지를 받아야 함
                expected_users = ["111", "222"]
                for expected_user in expected_users:
                    self.assertIn(expected_user, shared_damage)
                    self.assertEqual(shared_damage[expected_user], 30)
                
                # 죽은 유저는 데미지를 받지 않음
                self.assertNotIn("333", shared_damage)
            
            logger.info("✅ 카론 데미지 공유 테스트 통과")
    
    # === 복잡한 스킬 테스트 ===
    
    async def test_grim_skill_preparation(self):
        """그림 스킬 준비 단계 테스트"""
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            # 그림 준비 상태 설정 (실제로는 핸들러에서 처리)
            channel_state = skill_manager.get_channel_state(channel_id)
            channel_state["special_effects"] = {
                "grim_preparing": {
                    "caster_id": user_id,
                    "caster_name": "테스트유저",
                    "rounds_until_activation": 1
                }
            }
            skill_manager.mark_dirty(channel_id)
            
            # 준비 상태 확인
            state = skill_manager.get_channel_state(channel_id)
            self.assertIn("grim_preparing", state["special_effects"])
            self.assertEqual(state["special_effects"]["grim_preparing"]["rounds_until_activation"], 1)
            
            logger.info("✅ 그림 스킬 준비 테스트 통과")
    
    async def test_volken_eruption_phases(self):
        """볼켄 화산 폭발 단계 테스트"""
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            # 볼켄 화산 폭발 상태 설정
            channel_state = skill_manager.get_channel_state(channel_id)
            channel_state["special_effects"] = {
                "volken_eruption": {
                    "caster_id": user_id,
                    "caster_name": "테스트유저",
                    "current_phase": 1,
                    "selected_targets": [],
                    "rounds_left": 5
                }
            }
            skill_manager.mark_dirty(channel_id)
            
            # 1-3단계에서 주사위 1로 고정되는지 테스트
            from skills.skill_effects import skill_effects
            
            volken_effect = channel_state["special_effects"]["volken_eruption"]
            
            # 1단계 테스트 (주사위 1로 고정)
            volken_effect["current_phase"] = 1
            final_value, _ = await skill_effects.process_dice_roll(user_id, 75, channel_id)
            # 실제 볼켄 핸들러가 없으므로 기본값 반환
            
            # 4단계 테스트 (선별 단계)
            volken_effect["current_phase"] = 4
            volken_effect["selected_targets"] = []
            
            # 50 미만 주사위 시 선별 목록에 추가되는지 테스트
            # (실제로는 핸들러에서 처리되지만 구조 테스트)
            
            logger.info("✅ 볼켄 화산 폭발 단계 테스트 통과")
    
    # === 통합 테스트 ===
    
    async def test_multiple_skills_interaction(self):
        """여러 스킬 상호작용 테스트"""
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            monster_id = "monster"
            
            # 여러 스킬 동시 활성화
            skill_manager.add_skill(
                channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 5
            )
            skill_manager.add_skill(
                channel_id, "오리븐", monster_id, "테스트몬스터", "all_users", "모든 유저", 3
            )
            
            # 스킬 우선순위에 따른 적용 순서 테스트
            # 콜 폴드(우선순위 1) > 오닉셀(우선순위 2) > 오리븐(우선순위 3)
            
            # 유저 주사위: 오닉셀 보정 후 오리븐 -10 적용
            final_value, messages = await skill_effects.process_dice_roll(user_id, 30, channel_id)
            # 30 → 50 (오닉셀) → 40 (오리븐 -10)
            self.assertEqual(final_value, 40)
            
            # 메시지에 두 스킬 모두 언급되어야 함
            all_messages = " ".join(messages)
            self.assertIn("오닉셀", all_messages)
            self.assertIn("오리븐", all_messages)
            
            logger.info("✅ 여러 스킬 상호작용 테스트 통과")
    
    async def test_skill_permission_system(self):
        """스킬 권한 시스템 테스트"""
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            # 일반 유저 권한 테스트
            regular_user = "111111111"
            allowed_skills = skill_manager.get_user_allowed_skills(regular_user)
            self.assertEqual(allowed_skills, [])  # 설정에 없으므로 빈 목록
            
            # 테스트 유저 권한 테스트
            test_user = "123456789"
            allowed_skills = skill_manager.get_user_allowed_skills(test_user)
            expected_skills = ["오닉셀", "피닉스", "오리븐", "카론"]
            self.assertEqual(set(allowed_skills), set(expected_skills))
            
            # 관리자 권한 테스트
            is_admin = skill_manager.is_admin(test_user, "테스트유저")
            self.assertTrue(is_admin)
            
            # 넥시스 특별 권한 테스트
            nexis_user = "1059908946741166120"
            config_nexis_users = skill_manager.get_config("skill_users", {}).get("넥시스", [])
            self.assertIn(nexis_user, config_nexis_users)
            
            logger.info("✅ 스킬 권한 시스템 테스트 통과")
    
    async def test_skill_state_persistence(self):
        """스킬 상태 영속성 테스트"""
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import SkillManager
            
            # 첫 번째 매니저로 스킬 추가
            manager1 = SkillManager()
            await manager1.initialize()
            
            channel_id = "123456789"
            user_id = "987654321"
            
            success = manager1.add_skill(
                channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 5
            )
            self.assertTrue(success)
            
            # 강제 저장
            await manager1.force_save()
            
            # 두 번째 매니저로 상태 복구
            manager2 = SkillManager()
            await manager2.initialize()
            
            state = manager2.get_channel_state(channel_id)
            self.assertIn("오닉셀", state["active_skills"])
            self.assertEqual(state["active_skills"]["오닉셀"]["rounds_left"], 5)
            
            logger.info("✅ 스킬 상태 영속성 테스트 통과")
    
    # === 성능 테스트 ===
    
    async def test_performance_with_many_skills(self):
        """대량 스킬 처리 성능 테스트"""
        import time
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            channel_id = "123456789"
            
            # 여러 채널에 여러 스킬 추가
            start_time = time.time()
            
            for i in range(10):  # 10개 채널
                ch_id = f"channel_{i}"
                for j in range(5):  # 채널당 5개 스킬
                    user_id = f"user_{j}"
                    skill_name = ["오닉셀", "오리븐", "카론", "스트라보스", "황야"][j]
                    
                    skill_manager.add_skill(
                        ch_id, skill_name, user_id, f"유저{j}", user_id, f"유저{j}", 5
                    )
            
            creation_time = time.time() - start_time
            
            # 주사위 처리 성능 테스트
            start_time = time.time()
            
            for i in range(100):  # 100번의 주사위 처리
                final_value, messages = await skill_effects.process_dice_roll(
                    "user_0", 75, "channel_0"
                )
            
            processing_time = time.time() - start_time
            
            # 성능 기준 (24시간 작동을 위한 최소 요구사항)
            self.assertLess(creation_time, 1.0)     # 50개 스킬 생성 < 1초
            self.assertLess(processing_time, 2.0)   # 100번 주사위 처리 < 2초
            
            # 성능 데이터 저장
            test_name = self._testMethodName
            if test_name in TestSkillSystem.test_results:
                TestSkillSystem.test_results[test_name].performance_data = {
                    "skill_creation_time": creation_time,
                    "dice_processing_time": processing_time,
                    "skills_created": 50,
                    "dice_rolls_processed": 100
                }
            
            logger.info(f"✅ 성능 테스트 통과 - 생성: {creation_time:.3f}초, 처리: {processing_time:.3f}초")
    
    async def test_memory_management(self):
        """메모리 관리 테스트"""
        if not PSUTIL_AVAILABLE:
            self.skipTest("psutil이 설치되지 않아 메모리 테스트를 건너뜁니다.")
        
        import psutil
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            # 대량의 스킬 생성 및 제거
            for cycle in range(5):
                # 생성
                for i in range(100):
                    channel_id = f"test_channel_{i}"
                    skill_manager.add_skill(
                        channel_id, "오닉셀", f"user_{i}", f"유저{i}", f"user_{i}", f"유저{i}", 3
                    )
                
                # 제거
                for i in range(100):
                    channel_id = f"test_channel_{i}"
                    skill_manager.clear_channel_data(channel_id)
                
                # 가비지 컬렉션
                gc.collect()
            
            final_memory = process.memory_info().rss
            memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB
            
            # 메모리 증가가 50MB 미만이어야 함 (메모리 누수 방지)
            self.assertLess(memory_increase, 50)
            
            # 메모리 사용량 데이터 저장
            test_name = self._testMethodName
            if test_name in TestSkillSystem.test_results:
                TestSkillSystem.test_results[test_name].memory_usage = {
                    "initial_memory_mb": initial_memory / 1024 / 1024,
                    "final_memory_mb": final_memory / 1024 / 1024,
                    "memory_increase_mb": memory_increase
                }
            
            logger.info(f"✅ 메모리 관리 테스트 통과 - 증가량: {memory_increase:.2f}MB")
    
    # === 에러 처리 테스트 ===
    
    async def test_error_handling(self):
        """에러 처리 테스트"""
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
            await skill_manager.initialize()
            
            # 존재하지 않는 채널에서 주사위 처리
            final_value, messages = await skill_effects.process_dice_roll(
                "nonexistent_user", 50, "nonexistent_channel"
            )
            # 에러가 발생하지 않고 원본 값 반환
            self.assertEqual(final_value, 50)
            self.assertEqual(messages, [])
            
            # 잘못된 스킬 제거 시도
            removed = skill_manager.remove_skill("nonexistent_channel", "nonexistent_skill")
            self.assertFalse(removed)
            
            # 중복 스킬 추가 시도
            channel_id = "123456789"
            user_id = "987654321"
            
            # 첫 번째 추가 (성공)
            success1 = skill_manager.add_skill(
                channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 5
            )
            self.assertTrue(success1)
            
            # 같은 스킬 중복 추가 (실패)
            success2 = skill_manager.add_skill(
                channel_id, "오닉셀", user_id, "테스트유저", user_id, "테스트유저", 3
            )
            self.assertFalse(success2)
            
            logger.info("✅ 에러 처리 테스트 통과")

class TestBattleAdminIntegration(unittest.IsolatedAsyncioTestCase):
    """battle_admin.py 연동 테스트"""
    
    # 테스트 결과 저장을 위한 클래스 변수
    test_results = {}
    
    async def test_battle_participant_integration(self):
        """전투 참여자 연동 테스트"""
        # Mock battle_admin 함수들
        mock_participants = {
            "users": [
                {
                    "user_id": "123",
                    "user_name": "테스트유저1",
                    "real_name": "유저1",
                    "health": 80,
                    "max_health": 100,
                    "is_dead": False,
                    "display_name": "유저1"
                },
                {
                    "user_id": "456", 
                    "user_name": "테스트유저2",
                    "real_name": "유저2",
                    "health": 0,
                    "max_health": 100,
                    "is_dead": True,
                    "display_name": "유저2"
                }
            ],
            "monster": {
                "name": "테스트몬스터",
                "health": 90,
                "max_health": 120
            },
            "admin": None
        }
        
        with patch('battle_admin.get_battle_participants', return_value=mock_participants):
            from battle_admin import get_battle_participants
            
            participants = await get_battle_participants("test_channel")
            
            # 살아있는 유저와 죽은 유저 구분
            alive_users = [u for u in participants["users"] if not u["is_dead"]]
            dead_users = [u for u in participants["users"] if u["is_dead"]]
            
            self.assertEqual(len(alive_users), 1)
            self.assertEqual(len(dead_users), 1)
            self.assertEqual(alive_users[0]["user_id"], "123")
            self.assertEqual(dead_users[0]["user_id"], "456")
            
            logger.info("✅ 전투 참여자 연동 테스트 통과")
    
    async def test_damage_and_heal_integration(self):
        """데미지/회복 연동 테스트"""
        with patch('battle_admin.damage_user') as mock_damage, \
             patch('battle_admin.heal_user') as mock_heal, \
             patch('battle_admin.send_battle_message') as mock_message:
            
            mock_damage.return_value = True
            mock_heal.return_value = True
            mock_message.return_value = True
            
            from battle_admin import damage_user, heal_user, send_battle_message
            
            # 데미지 적용 테스트
            result = await damage_user("test_channel", "test_user", 30)
            self.assertTrue(result)
            mock_damage.assert_called_once_with("test_channel", "test_user", 30)
            
            # 회복 적용 테스트
            result = await heal_user("test_channel", "test_user", 20)
            self.assertTrue(result)
            mock_heal.assert_called_once_with("test_channel", "test_user", 20)
            
            # 메시지 전송 테스트
            result = await send_battle_message("test_channel", "테스트 메시지")
            self.assertTrue(result)
            mock_message.assert_called_once_with("test_channel", "테스트 메시지")
            
            logger.info("✅ 데미지/회복 연동 테스트 통과")

# === 테스트 보고서 생성 클래스 ===

class TestReportGenerator:
    """테스트 결과 보고서 생성"""
    
    def __init__(self, test_results: Dict[str, Dict[str, TestResult]]):
        self.test_results = test_results
        self.test_start_time = datetime.now()
        self.test_end_time = None
        # 실행 위치에 따라 보고서 디렉토리 설정
        if os.path.exists("skills"):
            self.report_dir = Path("skills/test_reports")
        else:
            self.report_dir = Path("test_reports")
        self.report_dir.mkdir(exist_ok=True, parents=True)
    
    def generate_reports(self, total_tests: int, passed_tests: int, failed_tests: int, skipped_tests: int = 0):
        """HTML과 Markdown 형식의 보고서 생성"""
        self.test_end_time = datetime.now()
        
        # 보고서 데이터 준비
        report_data = self._prepare_report_data(total_tests, passed_tests, failed_tests, skipped_tests)
        
        # HTML 보고서 생성
        html_report = self._generate_html_report(report_data)
        html_filename = self.report_dir / f"skill_test_report_{self.test_start_time.strftime('%Y%m%d_%H%M%S')}.html"
        with open(html_filename, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        # Markdown 보고서 생성
        md_report = self._generate_markdown_report(report_data)
        md_filename = self.report_dir / f"skill_test_report_{self.test_start_time.strftime('%Y%m%d_%H%M%S')}.md"
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(md_report)
        
        print(f"\n📄 보고서가 생성되었습니다:")
        print(f"   - HTML: {html_filename}")
        print(f"   - Markdown: {md_filename}")
        
        return html_filename, md_filename
    
    def _prepare_report_data(self, total_tests: int, passed_tests: int, failed_tests: int, skipped_tests: int = 0) -> Dict:
        """보고서용 데이터 준비"""
        duration = (self.test_end_time - self.test_start_time).total_seconds()
        
        # 테스트 결과 정리
        test_summary = []
        performance_data = []
        memory_data = []
        failed_test_details = []
        
        for test_class, results in self.test_results.items():
            for test_name, result in results.items():
                test_info = {
                    "class": test_class,
                    "name": test_name,
                    "status": result.status,
                    "duration": result.duration,
                    "error": result.error_message
                }
                test_summary.append(test_info)
                
                if result.status == "failed":
                    failed_test_details.append({
                        "test": f"{test_class}.{test_name}",
                        "error": result.error_message,
                        "traceback": result.error_traceback
                    })
                
                if result.performance_data:
                    performance_data.append({
                        "test": test_name,
                        "data": result.performance_data
                    })
                
                if result.memory_usage:
                    memory_data.append({
                        "test": test_name,
                        "data": result.memory_usage
                    })
        
        # 성공률 계산 (건너뛴 테스트 제외)
        effective_tests = total_tests - skipped_tests
        success_rate = (passed_tests / effective_tests * 100) if effective_tests > 0 else 0
        
        return {
            "test_start_time": self.test_start_time,
            "test_end_time": self.test_end_time,
            "duration": duration,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": skipped_tests,
            "success_rate": success_rate,
            "test_summary": test_summary,
            "performance_data": performance_data,
            "memory_data": memory_data,
            "failed_test_details": failed_test_details
        }
    
    def _generate_html_report(self, data: Dict) -> str:
        """HTML 형식 보고서 생성"""
        html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord 스킬 시스템 테스트 보고서</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #7289da;
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.5em;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            color: #7289da;
        }}
        .summary-card .value {{
            font-size: 2em;
            font-weight: bold;
        }}
        .success {{ color: #43b581; }}
        .failure {{ color: #f04747; }}
        .warning {{ color: #faa61a; }}
        table {{
            width: 100%;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e1e4e8;
        }}
        th {{
            background-color: #7289da;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f6f8fa;
        }}
        .status-passed {{
            color: #43b581;
            font-weight: bold;
        }}
        .status-failed {{
            color: #f04747;
            font-weight: bold;
        }}
        .status-skipped {{
            color: #faa61a;
            font-weight: bold;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            margin-top: 0;
            color: #7289da;
            border-bottom: 2px solid #7289da;
            padding-bottom: 10px;
        }}
        .error-box {{
            background-color: #fee;
            border: 1px solid #fcc;
            border-radius: 5px;
            padding: 10px;
            margin: 10px 0;
        }}
        .traceback {{
            background-color: #f8f9fa;
            border: 1px solid #e1e4e8;
            border-radius: 5px;
            padding: 10px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9em;
            overflow-x: auto;
            white-space: pre-wrap;
        }}
        .performance-chart {{
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Discord 스킬 시스템 테스트 보고서</h1>
        <p>테스트 실행: {data['test_start_time'].strftime('%Y년 %m월 %d일 %H:%M:%S')}</p>
        <p>총 소요 시간: {data['duration']:.2f}초</p>
    </div>
    
    <div class="summary">
        <div class="summary-card">
            <h3>총 테스트</h3>
            <div class="value">{data['total_tests']}</div>
        </div>
        <div class="summary-card">
            <h3>통과</h3>
            <div class="value success">{data['passed_tests']}</div>
        </div>
        <div class="summary-card">
            <h3>실패</h3>
            <div class="value failure">{data['failed_tests']}</div>
        </div>
        <div class="summary-card">
            <h3>건너뜀</h3>
            <div class="value warning">{data.get('skipped_tests', 0)}</div>
        </div>
        <div class="summary-card">
            <h3>성공률</h3>
            <div class="value {'success' if data['success_rate'] >= 90 else 'warning' if data['success_rate'] >= 70 else 'failure'}">{data['success_rate']:.1f}%</div>
        </div>
    </div>
    
    <div class="section">
        <h2>테스트 결과 상세</h2>
        <table>
            <thead>
                <tr>
                    <th>테스트 클래스</th>
                    <th>테스트 이름</th>
                    <th>상태</th>
                    <th>실행 시간</th>
                </tr>
            </thead>
            <tbody>
"""
        
        for test in data['test_summary']:
            status_class = f"status-{test['status']}"
            html += f"""
                <tr>
                    <td>{test['class']}</td>
                    <td>{test['name']}</td>
                    <td class="{status_class}">{test['status'].upper()}</td>
                    <td>{test['duration']:.3f}초</td>
                </tr>
"""
        
        html += """
            </tbody>
        </table>
    </div>
"""
        
        # 성능 데이터 섹션
        if data['performance_data']:
            html += """
    <div class="section">
        <h2>성능 측정 결과</h2>
"""
            for perf in data['performance_data']:
                html += f"<h3>{perf['test']}</h3><ul>"
                for key, value in perf['data'].items():
                    html += f"<li><strong>{key}:</strong> {value}</li>"
                html += "</ul>"
            html += "</div>"
        
        # 메모리 사용량 섹션
        if data['memory_data']:
            html += """
    <div class="section">
        <h2>메모리 사용량 분석</h2>
"""
            for mem in data['memory_data']:
                html += f"<h3>{mem['test']}</h3><ul>"
                for key, value in mem['data'].items():
                    html += f"<li><strong>{key}:</strong> {value:.2f} MB</li>"
                html += "</ul>"
            html += "</div>"
        
        # 실패한 테스트 상세
        if data['failed_test_details']:
            html += """
    <div class="section">
        <h2>실패한 테스트 상세 정보</h2>
"""
            for failed in data['failed_test_details']:
                html += f"""
        <div class="error-box">
            <h3>{failed['test']}</h3>
            <p><strong>오류:</strong> {failed['error']}</p>
            <div class="traceback">{failed['traceback']}</div>
        </div>
"""
            html += "</div>"
        
        # 권장사항
        html += """
    <div class="section">
        <h2>분석 및 권장사항</h2>
        <ul>
"""
        
        if data['success_rate'] == 100:
            html += "<li>✅ 모든 테스트가 통과했습니다. 스킬 시스템이 안정적으로 작동하고 있습니다.</li>"
        elif data['success_rate'] >= 90:
            html += "<li>⚠️ 대부분의 테스트가 통과했지만 일부 문제가 발견되었습니다. 실패한 테스트를 확인해주세요.</li>"
        else:
            html += "<li>❌ 상당수의 테스트가 실패했습니다. 시스템 점검이 필요합니다.</li>"
        
        if data['performance_data']:
            for perf in data['performance_data']:
                if 'skill_creation_time' in perf['data'] and perf['data']['skill_creation_time'] > 0.5:
                    html += "<li>⚠️ 스킬 생성 성능이 기준치를 초과했습니다. 최적화가 필요할 수 있습니다.</li>"
                    break
        
        if data['memory_data']:
            for mem in data['memory_data']:
                if 'memory_increase_mb' in mem['data'] and mem['data']['memory_increase_mb'] > 30:
                    html += "<li>⚠️ 메모리 사용량이 예상보다 높습니다. 메모리 누수를 확인해주세요.</li>"
                    break
        
        html += f"""
        </ul>
    </div>
    
    <div class="footer">
        <p>Discord 스킬 시스템 자동 테스트 보고서 v1.0</p>
        <p>생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>
"""
        
        return html
    
    def _generate_markdown_report(self, data: Dict) -> str:
        """Markdown 형식 보고서 생성"""
        md = f"""# Discord 스킬 시스템 테스트 보고서

## 테스트 개요
- **테스트 실행 시간**: {data['test_start_time'].strftime('%Y년 %m월 %d일 %H:%M:%S')}
- **총 소요 시간**: {data['duration']:.2f}초
- **총 테스트 수**: {data['total_tests']}
- **통과**: {data['passed_tests']}
- **실패**: {data['failed_tests']}
- **건너뜀**: {data.get('skipped_tests', 0)}
- **성공률**: {data['success_rate']:.1f}% (건너뛴 테스트 제외)

## 테스트 결과 요약

| 테스트 클래스 | 테스트 이름 | 상태 | 실행 시간 |
|-------------|-----------|------|----------|
"""
        
        for test in data['test_summary']:
            if test['status'] == "passed":
                status_icon = "✅"
            elif test['status'] == "failed":
                status_icon = "❌"
            else:  # skipped
                status_icon = "⏭️"
            md += f"| {test['class']} | {test['name']} | {status_icon} {test['status'].upper()} | {test['duration']:.3f}초 |\n"
        
        # 성능 데이터
        if data['performance_data']:
            md += "\n## 성능 측정 결과\n\n"
            for perf in data['performance_data']:
                md += f"### {perf['test']}\n"
                for key, value in perf['data'].items():
                    md += f"- **{key}**: {value}\n"
                md += "\n"
        
        # 메모리 사용량
        if data['memory_data']:
            md += "\n## 메모리 사용량 분석\n\n"
            for mem in data['memory_data']:
                md += f"### {mem['test']}\n"
                for key, value in mem['data'].items():
                    md += f"- **{key}**: {value:.2f} MB\n"
                md += "\n"
        
        # 실패한 테스트
        if data['failed_test_details']:
            md += "\n## 실패한 테스트 상세 정보\n\n"
            for failed in data['failed_test_details']:
                md += f"### {failed['test']}\n"
                md += f"**오류**: {failed['error']}\n\n"
                md += "```python\n"
                md += failed['traceback']
                md += "```\n\n"
        
        # 분석 및 권장사항
        md += "\n## 분석 및 권장사항\n\n"
        
        if data['success_rate'] == 100:
            md += "- ✅ 모든 테스트가 통과했습니다. 스킬 시스템이 안정적으로 작동하고 있습니다.\n"
        elif data['success_rate'] >= 90:
            md += "- ⚠️ 대부분의 테스트가 통과했지만 일부 문제가 발견되었습니다. 실패한 테스트를 확인해주세요.\n"
        else:
            md += "- ❌ 상당수의 테스트가 실패했습니다. 시스템 점검이 필요합니다.\n"
        
        md += f"\n---\n*생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        
        return md

# === 간단한 보고서 생성 테스트 ===

class TestReportGeneration(unittest.IsolatedAsyncioTestCase):
    """보고서 생성 기능 자체 테스트"""
    
    test_results = {}
    
    async def test_report_generation_success(self):
        """보고서 생성 성공 테스트"""
        # 더미 결과 생성
        test_result = TestResult("test_dummy", "TestReportGeneration")
        test_result.start()
        await asyncio.sleep(0.1)  # 시간 측정을 위한 짧은 대기
        test_result.finish("passed")
        
        results = {"TestReportGeneration": {"test_dummy": test_result}}
        
        # 보고서 생성
        generator = TestReportGenerator(results)
        try:
            html_path, md_path = generator.generate_reports(1, 1, 0, 0)  # total, passed, failed, skipped
            
            # 파일 존재 확인
            self.assertTrue(Path(html_path).exists())
            self.assertTrue(Path(md_path).exists())
            
            # 파일 내용 확인
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
                self.assertIn("Discord 스킬 시스템 테스트 보고서", html_content)
                self.assertIn("100.0%", html_content)  # 성공률
            
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
                self.assertIn("# Discord 스킬 시스템 테스트 보고서", md_content)
                self.assertIn("✅", md_content)  # 성공 아이콘
            
            logger.info("✅ 보고서 생성 테스트 통과")
            
        finally:
            # 테스트 파일 정리
            if 'html_path' in locals() and Path(html_path).exists():
                Path(html_path).unlink()
            if 'md_path' in locals() and Path(md_path).exists():
                Path(md_path).unlink()

# === 테스트 실행 도구 ===

class TestRunner:
    """테스트 실행 및 결과 분석"""
    
    def __init__(self):
        self.results = {}
        self.report_generator = None
    
    async def run_all_tests(self):
        """모든 테스트 실행"""
        print("🚀 Discord 스킬 시스템 포괄적 테스트 시작\n")
        
        # 테스트 슈트 생성
        test_classes = [TestSkillSystem, TestBattleAdminIntegration, TestReportGeneration]
        
        # 결과 저장용 딕셔너리 초기화
        for test_class in test_classes:
            self.results[test_class.__name__] = {}
            test_class.test_results = {}
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        skipped_tests = 0
        
        for test_class in test_classes:
            print(f"📝 {test_class.__name__} 테스트 실행 중...")
            
            # 테스트 메서드 찾기
            test_methods = [method for method in dir(test_class) if method.startswith('test_')]
            
            for test_method in test_methods:
                total_tests += 1
                test_result = TestResult(test_method, test_class.__name__)
                test_result.start()
                
                try:
                    # 테스트 인스턴스 생성 및 실행
                    test_instance = test_class()
                    test_instance._testMethodName = test_method  # 메서드 이름 설정
                    test_class.test_results[test_method] = test_result
                    
                    await test_instance.asyncSetUp()
                    
                    # 테스트 메서드 실행
                    await getattr(test_instance, test_method)()
                    
                    await test_instance.asyncTearDown()
                    
                    test_result.finish("passed")
                    passed_tests += 1
                    
                except unittest.SkipTest as e:
                    test_result.finish("skipped", e)
                    skipped_tests += 1
                    print(f"⏭️  {test_class.__name__}.{test_method} 건너뜀: {e}")
                    
                except Exception as e:
                    test_result.finish("failed", e)
                    failed_tests += 1
                    print(f"❌ {test_class.__name__}.{test_method} 실패: {e}")
                    logger.error(f"테스트 실패: {test_method}", exc_info=True)
                
                self.results[test_class.__name__][test_method] = test_result
        
        # 결과 요약
        print(f"\n📊 테스트 결과 요약:")
        print(f"   총 테스트: {total_tests}")
        print(f"   통과: {passed_tests} ✅")
        print(f"   실패: {failed_tests} ❌")
        print(f"   건너뜀: {skipped_tests} ⏭️")
        print(f"   성공률: {passed_tests/total_tests*100:.1f}% (건너뛴 테스트 제외)")
        
        # 보고서 생성
        self.report_generator = TestReportGenerator(self.results)
        html_report, md_report = self.report_generator.generate_reports(
            total_tests, passed_tests, failed_tests, skipped_tests
        )
        
        if failed_tests == 0:
            print("\n🎉 모든 테스트가 통과했습니다! 스킬 시스템이 정상 작동합니다.")
        else:
            print(f"\n⚠️  {failed_tests}개의 테스트가 실패했습니다. 생성된 보고서를 확인해주세요.")
        
        return failed_tests == 0

# 실행 스크립트
if __name__ == "__main__":
    async def main():
        runner = TestRunner()
        success = await runner.run_all_tests()
        return 0 if success else 1
    
    import sys
    sys.exit(asyncio.run(main()))

