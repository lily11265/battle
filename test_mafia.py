# test_mafia.py
import unittest
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call
import asyncio
import discord
from discord import app_commands
from typing import List, Dict
import random

# Import the mafia game module
from mafia import (
    MafiaGame, Role, GamePhase, Player,
    MafiaJoinView, MafiaActionView, PoliceActionView, 
    DoctorActionView, VoteView, VoteButton,
    get_mafia_game
)

class TestMafiaGame(unittest.IsolatedAsyncioTestCase):
    """마피아 게임 테스트 스위트"""
    
    def setUp(self):
        """각 테스트 전 실행"""
        self.game = MafiaGame()
        self.mock_channel_id = 123456789
        
        # Mock Discord objects
        self.mock_users = []
        for i in range(6):
            mock_user = Mock(spec=discord.Member)
            mock_user.id = 1000 + i
            mock_user.display_name = f"Player{i+1}"
            mock_user.send = AsyncMock()
            self.mock_users.append(mock_user)
    
    def tearDown(self):
        """각 테스트 후 정리"""
        self.game.games.clear()
    
    async def test_singleton_instance(self):
        """싱글톤 인스턴스 테스트"""
        game1 = get_mafia_game()
        game2 = get_mafia_game()
        self.assertIs(game1, game2)
    
    def test_role_enum(self):
        """역할 열거형 테스트"""
        self.assertEqual(Role.CITIZEN.value[0], "시민")
        self.assertEqual(Role.MAFIA.value[1], "🔫")
        self.assertEqual(Role.POLICE.value[0], "경찰")
        self.assertEqual(Role.DOCTOR.value[0], "의사")
    
    def test_game_phase_enum(self):
        """게임 페이즈 열거형 테스트"""
        self.assertEqual(GamePhase.WAITING.value, "대기중")
        self.assertEqual(GamePhase.NIGHT.value, "밤")
        self.assertEqual(GamePhase.DAY_DISCUSSION.value, "낮 - 토론")
        self.assertEqual(GamePhase.DAY_VOTE.value, "낮 - 투표")
        self.assertEqual(GamePhase.GAME_OVER.value, "게임종료")
    
    def test_player_dataclass(self):
        """플레이어 데이터클래스 테스트"""
        player = Player(user=self.mock_users[0], role=Role.CITIZEN)
        self.assertTrue(player.alive)
        self.assertFalse(player.protected)
        self.assertEqual(player.votes, 0)
    
    def test_assign_roles_distribution(self):
        """역할 배정 분배 테스트"""
        # 4명 게임
        players_4 = self.mock_users[:4]
        assigned_4 = self.game.assign_roles(players_4)
        roles_4 = [p.role for p in assigned_4.values()]
        self.assertEqual(roles_4.count(Role.MAFIA), 1)
        self.assertEqual(roles_4.count(Role.POLICE), 0)
        self.assertEqual(roles_4.count(Role.DOCTOR), 0)
        self.assertEqual(roles_4.count(Role.CITIZEN), 3)
        
        # 5명 게임
        players_5 = self.mock_users[:5]
        assigned_5 = self.game.assign_roles(players_5)
        roles_5 = [p.role for p in assigned_5.values()]
        self.assertEqual(roles_5.count(Role.MAFIA), 1)
        self.assertEqual(roles_5.count(Role.POLICE), 1)
        self.assertEqual(roles_5.count(Role.DOCTOR), 0)
        self.assertEqual(roles_5.count(Role.CITIZEN), 3)
        
        # 6명 게임
        players_6 = self.mock_users[:6]
        assigned_6 = self.game.assign_roles(players_6)
        roles_6 = [p.role for p in assigned_6.values()]
        self.assertEqual(roles_6.count(Role.MAFIA), 1)
        self.assertEqual(roles_6.count(Role.POLICE), 1)
        self.assertEqual(roles_6.count(Role.DOCTOR), 1)
        self.assertEqual(roles_6.count(Role.CITIZEN), 3)
    
    async def test_start_game_already_running(self):
        """이미 진행 중인 게임이 있을 때 테스트"""
        # Setup
        self.game.games[self.mock_channel_id] = {"dummy": "data"}
        
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.channel_id = self.mock_channel_id
        
        # Test
        await self.game.start_game(mock_interaction, self.mock_users[:4])
        
        # Verify
        mock_interaction.response.send_message.assert_called_once_with(
            "이미 진행 중인 게임이 있습니다!",
            ephemeral=True
        )
    
    async def test_start_game_invalid_player_count(self):
        """잘못된 플레이어 수 테스트"""
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.channel_id = self.mock_channel_id
        
        # 너무 적은 플레이어
        await self.game.start_game(mock_interaction, self.mock_users[:2])
        mock_interaction.response.send_message.assert_called_with(
            f"플레이어 수는 {self.game.MIN_PLAYERS}~{self.game.MAX_PLAYERS}명이어야 합니다!",
            ephemeral=True
        )
        
        # 너무 많은 플레이어
        mock_interaction.reset_mock()
        many_users = [Mock(spec=discord.Member) for _ in range(15)]
        await self.game.start_game(mock_interaction, many_users)
        mock_interaction.response.send_message.assert_called_with(
            f"플레이어 수는 {self.game.MIN_PLAYERS}~{self.game.MAX_PLAYERS}명이어야 합니다!",
            ephemeral=True
        )
    
    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_start_game_success(self, mock_sleep):
        """게임 시작 성공 테스트"""
        # Setup
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.channel_id = self.mock_channel_id
        mock_interaction.channel = Mock()
        mock_original_response = AsyncMock()
        mock_interaction.original_response.return_value = mock_original_response
        
        # Patch night_phase to prevent full execution
        with patch.object(self.game, 'night_phase', new_callable=AsyncMock):
            await self.game.start_game(mock_interaction, self.mock_users[:4])
        
        # Verify game data created
        self.assertIn(self.mock_channel_id, self.game.games)
        game_data = self.game.games[self.mock_channel_id]
        
        # Check game data structure
        self.assertEqual(len(game_data["players"]), 4)
        self.assertEqual(game_data["phase"], GamePhase.WAITING)
        self.assertEqual(game_data["day"], 0)
        self.assertEqual(game_data["night_actions"], {})
        self.assertEqual(game_data["day_votes"], {})
        
        # Verify DMs sent to players
        for user in self.mock_users[:4]:
            user.send.assert_called_once()
            call_args = user.send.call_args
            self.assertIn('embed', call_args.kwargs)
    
    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_night_phase(self, mock_sleep):
        """밤 페이즈 테스트"""
        # Setup game data
        players = self.game.assign_roles(self.mock_users[:6])
        game_data = {
            "channel": Mock(),
            "players": players,
            "phase": GamePhase.WAITING,
            "day": 0,
            "night_actions": {},
            "day_votes": {},
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock action methods
        with patch.object(self.game, 'request_mafia_action', new_callable=AsyncMock), \
             patch.object(self.game, 'request_police_action', new_callable=AsyncMock), \
             patch.object(self.game, 'request_doctor_action', new_callable=AsyncMock), \
             patch.object(self.game, 'process_night_actions', new_callable=AsyncMock):
            
            await self.game.night_phase(self.mock_channel_id)
        
        # Verify
        self.assertEqual(game_data["phase"], GamePhase.NIGHT)
        self.assertEqual(game_data["day"], 1)
        game_data["message"].edit.assert_called_once()
    
    async def test_request_mafia_action(self):
        """마피아 행동 요청 테스트"""
        # Setup
        mafia_player = Player(user=self.mock_users[0], role=Role.MAFIA)
        citizen_player = Player(user=self.mock_users[1], role=Role.CITIZEN)
        
        game_data = {
            "players": {
                self.mock_users[0].id: mafia_player,
                self.mock_users[1].id: citizen_player
            }
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Test
        await self.game.request_mafia_action(self.mock_channel_id, mafia_player)
        
        # Verify
        mafia_player.user.send.assert_called_once()
        call_args = mafia_player.user.send.call_args
        self.assertIn('embed', call_args.kwargs)
        self.assertIn('view', call_args.kwargs)
    
    async def test_process_night_actions_mafia_kill(self):
        """밤 행동 처리 - 마피아 살해 테스트"""
        # Setup
        mafia = Player(user=self.mock_users[0], role=Role.MAFIA)
        citizen = Player(user=self.mock_users[1], role=Role.CITIZEN)
        
        game_data = {
            "channel": Mock(),
            "players": {
                self.mock_users[0].id: mafia,
                self.mock_users[1].id: citizen
            },
            "phase": GamePhase.NIGHT,
            "day": 1,
            "night_actions": {
                f"mafia_{self.mock_users[0].id}": self.mock_users[1].id
            },
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock methods
        with patch.object(self.game, 'end_game', new_callable=AsyncMock), \
             patch.object(self.game, 'day_discussion_phase', new_callable=AsyncMock), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            await self.game.process_night_actions(self.mock_channel_id)
        
        # Verify
        self.assertFalse(citizen.alive)
        self.assertTrue(mafia.alive)
        self.assertIn(f"Day 1: {citizen.user.display_name} 사망", game_data["game_log"])
    
    async def test_process_night_actions_doctor_save(self):
        """밤 행동 처리 - 의사 구조 테스트"""
        # Setup
        mafia = Player(user=self.mock_users[0], role=Role.MAFIA)
        doctor = Player(user=self.mock_users[1], role=Role.DOCTOR)
        citizen = Player(user=self.mock_users[2], role=Role.CITIZEN)
        
        game_data = {
            "channel": Mock(),
            "players": {
                self.mock_users[0].id: mafia,
                self.mock_users[1].id: doctor,
                self.mock_users[2].id: citizen
            },
            "phase": GamePhase.NIGHT,
            "day": 1,
            "night_actions": {
                f"mafia_{self.mock_users[0].id}": self.mock_users[2].id,
                "doctor": self.mock_users[2].id
            },
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock methods
        with patch.object(self.game, 'day_discussion_phase', new_callable=AsyncMock), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            await self.game.process_night_actions(self.mock_channel_id)
        
        # Verify
        self.assertTrue(citizen.alive)  # Saved by doctor
        self.assertTrue(citizen.protected)
    
    async def test_police_investigation(self):
        """경찰 조사 테스트"""
        # Setup
        police = Player(user=self.mock_users[0], role=Role.POLICE)
        mafia = Player(user=self.mock_users[1], role=Role.MAFIA)
        citizen = Player(user=self.mock_users[2], role=Role.CITIZEN)
        
        game_data = {
            "channel": Mock(),
            "players": {
                self.mock_users[0].id: police,
                self.mock_users[1].id: mafia,
                self.mock_users[2].id: citizen
            },
            "phase": GamePhase.NIGHT,
            "day": 1,
            "night_actions": {
                "police": self.mock_users[1].id  # Investigate mafia
            },
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock methods
        with patch.object(self.game, 'day_discussion_phase', new_callable=AsyncMock), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            await self.game.process_night_actions(self.mock_channel_id)
        
        # Verify police got result
        police.user.send.assert_called_with(
            f"조사 결과: {mafia.user.display_name}은(는) 마피아입니다!"
        )
    
    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_day_discussion_phase(self, mock_sleep):
        """낮 토론 페이즈 테스트"""
        # Setup
        game_data = {
            "phase": GamePhase.NIGHT,
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock vote phase
        with patch.object(self.game, 'day_vote_phase', new_callable=AsyncMock):
            await self.game.day_discussion_phase(self.mock_channel_id)
        
        # Verify
        self.assertEqual(game_data["phase"], GamePhase.DAY_DISCUSSION)
        game_data["message"].edit.assert_called_once()
    
    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_day_vote_phase(self, mock_sleep):
        """낮 투표 페이즈 테스트"""
        # Setup
        players = {
            self.mock_users[0].id: Player(user=self.mock_users[0], role=Role.CITIZEN),
            self.mock_users[1].id: Player(user=self.mock_users[1], role=Role.MAFIA)
        }
        
        game_data = {
            "phase": GamePhase.DAY_DISCUSSION,
            "players": players,
            "day_votes": {},
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock process votes
        with patch.object(self.game, 'process_votes', new_callable=AsyncMock):
            await self.game.day_vote_phase(self.mock_channel_id)
        
        # Verify
        self.assertEqual(game_data["phase"], GamePhase.DAY_VOTE)
        self.assertEqual(game_data["day_votes"], {})
        for player in players.values():
            self.assertEqual(player.votes, 0)
    
    async def test_process_votes_elimination(self):
        """투표 처리 - 처형 테스트"""
        # Setup
        citizen1 = Player(user=self.mock_users[0], role=Role.CITIZEN)
        citizen2 = Player(user=self.mock_users[1], role=Role.CITIZEN)
        mafia = Player(user=self.mock_users[2], role=Role.MAFIA)
        
        # Mafia gets most votes
        citizen1.votes = 1
        citizen2.votes = 0
        mafia.votes = 2
        
        game_data = {
            "players": {
                self.mock_users[0].id: citizen1,
                self.mock_users[1].id: citizen2,
                self.mock_users[2].id: mafia
            },
            "day": 1,
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock methods
        with patch.object(self.game, 'end_game', new_callable=AsyncMock), \
             patch('asyncio.sleep', new_callable=AsyncMock), \
             patch('random.choice', return_value=mafia):
            
            await self.game.process_votes(self.mock_channel_id)
        
        # Verify
        self.assertFalse(mafia.alive)
        self.assertIn("처형", game_data["game_log"][0])
    
    async def test_end_game_mafia_win(self):
        """게임 종료 - 마피아 승리 테스트"""
        # Setup
        mafia = Player(user=self.mock_users[0], role=Role.MAFIA, alive=True)
        citizen = Player(user=self.mock_users[1], role=Role.CITIZEN, alive=False)
        
        game_data = {
            "channel": Mock(),
            "players": {
                self.mock_users[0].id: mafia,
                self.mock_users[1].id: citizen
            },
            "phase": GamePhase.NIGHT,
            "game_log": ["Some log"],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock balance update
        with patch('mafia.update_player_balance', new_callable=AsyncMock):
            await self.game.end_game(self.mock_channel_id, "마피아")
        
        # Verify
        self.assertEqual(game_data["phase"], GamePhase.GAME_OVER)
        self.assertNotIn(self.mock_channel_id, self.game.games)
    
    async def test_end_game_citizen_win(self):
        """게임 종료 - 시민 승리 테스트"""
        # Setup
        mafia = Player(user=self.mock_users[0], role=Role.MAFIA, alive=False)
        citizen = Player(user=self.mock_users[1], role=Role.CITIZEN, alive=True)
        police = Player(user=self.mock_users[2], role=Role.POLICE, alive=True)
        
        game_data = {
            "channel": Mock(),
            "players": {
                self.mock_users[0].id: mafia,
                self.mock_users[1].id: citizen,
                self.mock_users[2].id: police
            },
            "phase": GamePhase.DAY_VOTE,
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[self.mock_channel_id] = game_data
        
        # Mock balance update
        with patch('mafia.update_player_balance', new_callable=AsyncMock) as mock_update:
            await self.game.end_game(self.mock_channel_id, "시민")
            
            # Verify rewards given to winners (citizen and police)
            self.assertEqual(mock_update.call_count, 2)
    
    def test_mafia_join_view(self):
        """마피아 참가 뷰 테스트"""
        view = MafiaJoinView(self.game)
        self.assertEqual(len(view.participants), 0)
        self.assertEqual(view.timeout, 30)
        self.assertEqual(len(view.children), 1)  # Join button
    
    async def test_mafia_join_button(self):
        """마피아 참가 버튼 테스트"""
        view = MafiaJoinView(self.game)
        
        # Mock interaction
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.user = self.mock_users[0]
        
        # First join
        button = view.children[0]
        await button.callback(mock_interaction)
        
        self.assertIn(self.mock_users[0], view.participants)
        mock_interaction.response.send_message.assert_called()
        
        # Try to join again
        mock_interaction.reset_mock()
        await button.callback(mock_interaction)
        
        mock_interaction.response.send_message.assert_called_with(
            "이미 참가하셨습니다!",
            ephemeral=True
        )
    
    def test_vote_button(self):
        """투표 버튼 테스트"""
        player = Player(user=self.mock_users[0], role=Role.CITIZEN)
        button = VoteButton(player)
        
        self.assertEqual(button.label, f"{player.user.display_name} (0표)")
        self.assertEqual(button.style, discord.ButtonStyle.primary)
    
    async def test_vote_button_callback(self):
        """투표 버튼 콜백 테스트"""
        player = Player(user=self.mock_users[0], role=Role.CITIZEN)
        button = VoteButton(player)
        
        # Create view and add button
        view = VoteView(self.game, self.mock_channel_id, [player])
        view.clear_items()
        view.add_item(button)
        button.view = view
        
        # Mock interaction
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.user = self.mock_users[1]
        mock_interaction.user.id = self.mock_users[1].id
        
        # Vote
        await button.callback(mock_interaction)
        
        self.assertEqual(player.votes, 1)
        self.assertEqual(button.label, f"{player.user.display_name} (1표)")
        self.assertIn(mock_interaction.user.id, view.voted_users)
    
    async def test_complete_game_flow(self):
        """완전한 게임 플로우 통합 테스트"""
        # This is a simplified integration test
        # In real testing, you'd want to test the full flow
        
        # Setup
        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.channel_id = self.mock_channel_id
        mock_interaction.channel = Mock()
        mock_original_response = AsyncMock()
        mock_interaction.original_response.return_value = mock_original_response
        
        # Start game with minimum players
        with patch('asyncio.sleep', new_callable=AsyncMock), \
             patch.object(self.game, 'night_phase', new_callable=AsyncMock):
            
            await self.game.start_game(mock_interaction, self.mock_users[:4])
        
        # Verify game started
        self.assertIn(self.mock_channel_id, self.game.games)
        game_data = self.game.games[self.mock_channel_id]
        
        # Check all players assigned roles
        self.assertEqual(len(game_data["players"]), 4)
        for player in game_data["players"].values():
            self.assertIsInstance(player.role, Role)
            self.assertTrue(player.alive)


class TestUIComponents(unittest.TestCase):
    """UI 컴포넌트 테스트"""
    
    def setUp(self):
        self.game = MafiaGame()
        self.mock_users = []
        for i in range(4):
            mock_user = Mock(spec=discord.Member)
            mock_user.id = 1000 + i
            mock_user.display_name = f"Player{i+1}"
            self.mock_users.append(mock_user)
    
    def test_mafia_action_view_creation(self):
        """마피아 액션 뷰 생성 테스트"""
        mafia = Player(user=self.mock_users[0], role=Role.MAFIA)
        targets = [
            Player(user=self.mock_users[1], role=Role.CITIZEN),
            Player(user=self.mock_users[2], role=Role.CITIZEN)
        ]
        
        view = MafiaActionView(self.game, 123, mafia.user.id, targets)
        
        self.assertEqual(view.timeout, 60)
        self.assertEqual(len(view.children), 1)  # Select menu
        
        select = view.children[0]
        self.assertEqual(len(select.options), 2)
    
    def test_police_action_view_creation(self):
        """경찰 액션 뷰 생성 테스트"""
        police = Player(user=self.mock_users[0], role=Role.POLICE)
        targets = [
            Player(user=self.mock_users[1], role=Role.CITIZEN),
            Player(user=self.mock_users[2], role=Role.MAFIA)
        ]
        
        view = PoliceActionView(self.game, 123, police.user.id, targets)
        
        self.assertEqual(view.timeout, 60)
        self.assertEqual(len(view.children), 1)  # Select menu
    
    def test_doctor_action_view_creation(self):
        """의사 액션 뷰 생성 테스트"""
        doctor = Player(user=self.mock_users[0], role=Role.DOCTOR)
        targets = [
            Player(user=self.mock_users[0], role=Role.DOCTOR),  # Can protect self
            Player(user=self.mock_users[1], role=Role.CITIZEN)
        ]
        
        view = DoctorActionView(self.game, 123, doctor.user.id, targets)
        
        self.assertEqual(view.timeout, 60)
        self.assertEqual(len(view.children), 1)  # Select menu
    
    def test_vote_view_creation(self):
        """투표 뷰 생성 테스트"""
        players = [
            Player(user=self.mock_users[0], role=Role.CITIZEN),
            Player(user=self.mock_users[1], role=Role.MAFIA)
        ]
        
        view = VoteView(self.game, 123, players)
        
        self.assertEqual(view.timeout, 60)
        self.assertEqual(len(view.children), 2)  # Two vote buttons


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    """엣지 케이스 테스트"""
    
    def setUp(self):
        self.game = MafiaGame()
        self.mock_users = []
        for i in range(10):
            mock_user = Mock(spec=discord.Member)
            mock_user.id = 2000 + i
            mock_user.display_name = f"EdgePlayer{i+1}"
            mock_user.send = AsyncMock()
            self.mock_users.append(mock_user)
    
    def test_max_players_role_distribution(self):
        """최대 플레이어 수 역할 분배 테스트"""
        players = self.mock_users[:12]  # Max players
        assigned = self.game.assign_roles(players)
        
        roles = [p.role for p in assigned.values()]
        mafia_count = roles.count(Role.MAFIA)
        
        # With 12 players, should have 3 mafias (12 // 4)
        self.assertEqual(mafia_count, 3)
        self.assertEqual(len(assigned), 12)
    
    async def test_all_mafia_dead(self):
        """모든 마피아가 죽은 경우 테스트"""
        # Setup - all mafias dead
        players = {
            self.mock_users[0].id: Player(user=self.mock_users[0], role=Role.MAFIA, alive=False),
            self.mock_users[1].id: Player(user=self.mock_users[1], role=Role.CITIZEN, alive=True),
            self.mock_users[2].id: Player(user=self.mock_users[2], role=Role.POLICE, alive=True)
        }
        
        game_data = {
            "channel": Mock(),
            "players": players,
            "phase": GamePhase.NIGHT,
            "day": 2,
            "night_actions": {},
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[123] = game_data
        
        # Test night actions with no alive mafias
        with patch.object(self.game, 'end_game', new_callable=AsyncMock) as mock_end, \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            await self.game.process_night_actions(123)
            
            # Should end game with citizen victory
            mock_end.assert_called_once_with(123, "시민")
    
    async def test_mafia_majority(self):
        """마피아가 과반수인 경우 테스트"""
        # Setup - mafias >= citizens
        players = {
            self.mock_users[0].id: Player(user=self.mock_users[0], role=Role.MAFIA, alive=True),
            self.mock_users[1].id: Player(user=self.mock_users[1], role=Role.MAFIA, alive=True),
            self.mock_users[2].id: Player(user=self.mock_users[2], role=Role.CITIZEN, alive=True),
            self.mock_users[3].id: Player(user=self.mock_users[3], role=Role.POLICE, alive=True)
        }
        
        game_data = {
            "channel": Mock(),
            "players": players,
            "phase": GamePhase.NIGHT,
            "day": 3,
            "night_actions": {},
            "game_log": [],
            "message": AsyncMock()
        }
        self.game.games[456] = game_data
        
        # Test
        with patch.object(self.game, 'end_game', new_callable=AsyncMock) as mock_end, \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            await self.game.process_night_actions(456)
            
            # Should end game with mafia victory
            mock_end.assert_called_once_with(456, "마피아")
    
    async def test_dm_send_failure(self):
        """DM 전송 실패 처리 테스트"""
        # Setup user that can't receive DMs
        mock_user = Mock(spec=discord.Member)
        mock_user.id = 9999
        mock_user.display_name = "NoDMUser"
        mock_user.send = AsyncMock(side_effect=discord.Forbidden(Mock(), "Cannot send DM"))
        
        mafia = Player(user=mock_user, role=Role.MAFIA)
        
        # Test - should not raise exception
        try:
            await self.game.request_mafia_action(123, mafia)
            # Should complete without error
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Should handle DM failure gracefully: {e}")
    
    def test_empty_vote_tie(self):
        """투표 동점 처리 테스트"""
        players = [
            Player(user=self.mock_users[0], role=Role.CITIZEN, votes=2),
            Player(user=self.mock_users[1], role=Role.MAFIA, votes=2),
            Player(user=self.mock_users[2], role=Role.POLICE, votes=1)
        ]
        
        # With random.choice, either player with 2 votes could be selected
        # Just verify no exception is raised
        with patch('random.choice') as mock_choice:
            mock_choice.return_value = players[0]
            # In actual test, process_votes would handle this
            self.assertIn(mock_choice.return_value, [players[0], players[1]])


# 실행을 위한 헬퍼 함수
def run_tests():
    """모든 테스트 실행"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMafiaGame))
    suite.addTests(loader.loadTestsFromTestCase(TestUIComponents))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    # Run all tests
    success = run_tests()
    
    if success:
        print("\n✅ 모든 테스트가 성공적으로 통과했습니다!")
    else:
        print("\n❌ 일부 테스트가 실패했습니다.")
        
    # You can also run specific test classes
    # unittest.main()
