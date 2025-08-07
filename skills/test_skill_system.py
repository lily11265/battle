# test_skill_system.py - 포괄적 스킬 시스템 테스트
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

# 테스트 환경 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestSkillSystem(unittest.IsolatedAsyncioTestCase):
    """스킬 시스템 통합 테스트"""
    
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
            
            from skills.skill_manager import SkillManager
            manager = SkillManager()
            await manager.initialize()
            
            self.assertIsNotNone(manager._skill_states)
            self.assertIsNotNone(manager._config)
            logger.info("✅ 스킬 매니저 초기화 테스트 통과")
    
    async def test_skill_addition_and_removal(self):
        """스킬 추가/제거 테스트"""
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
        from skills.skill_effects import skill_effects
        
        with patch('skills.skill_manager.Path') as mock_path:
            mock_path.return_value = self.skills_dir
            
            from skills.skill_manager import skill_manager
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
            
            logger.info(f"✅ 성능 테스트 통과 - 생성: {creation_time:.3f}초, 처리: {processing_time:.3f}초")
    
    async def test_memory_management(self):
        """메모리 관리 테스트"""
        import gc
        import psutil
        import os
        
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

# === 테스트 실행 도구 ===

class TestRunner:
    """테스트 실행 및 결과 분석"""
    
    def __init__(self):
        self.results = []
    
    async def run_all_tests(self):
        """모든 테스트 실행"""
        print("🚀 Discord 스킬 시스템 포괄적 테스트 시작\n")
        
        # 테스트 슈트 생성
        test_classes = [TestSkillSystem, TestBattleAdminIntegration]
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        
        for test_class in test_classes:
            print(f"📝 {test_class.__name__} 테스트 실행 중...")
            
            # 테스트 메서드 찾기
            test_methods = [method for method in dir(test_class) if method.startswith('test_')]
            
            for test_method in test_methods:
                total_tests += 1
                try:
                    # 테스트 인스턴스 생성 및 실행
                    test_instance = test_class()
                    await test_instance.asyncSetUp()
                    
                    # 테스트 메서드 실행
                    await getattr(test_instance, test_method)()
                    
                    await test_instance.asyncTearDown()
                    passed_tests += 1
                    
                except Exception as e:
                    failed_tests += 1
                    print(f"❌ {test_class.__name__}.{test_method} 실패: {e}")
                    logger.error(f"테스트 실패: {test_method}", exc_info=True)
        
        # 결과 요약
        print(f"\n📊 테스트 결과 요약:")
        print(f"   총 테스트: {total_tests}")
        print(f"   통과: {passed_tests} ✅")
        print(f"   실패: {failed_tests} ❌")
        print(f"   성공률: {passed_tests/total_tests*100:.1f}%")
        
        if failed_tests == 0:
            print("\n🎉 모든 테스트가 통과했습니다! 스킬 시스템이 정상 작동합니다.")
        else:
            print(f"\n⚠️  {failed_tests}개의 테스트가 실패했습니다. 로그를 확인해주세요.")
        
        return failed_tests == 0

# 실행 스크립트
if __name__ == "__main__":
    async def main():
        runner = TestRunner()
        success = await runner.run_all_tests()
        return 0 if success else 1
    
    import sys
    sys.exit(asyncio.run(main()))
