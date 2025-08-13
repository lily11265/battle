# minigames_commands.py - 수정된 버전 (눈사람 게임 추가)
import discord
from discord import Role, app_commands
from discord.ext import commands
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Optional, List, Set
import asyncio
import json
import os
from pathlib import Path

# 게임 모듈 임포트
from dart import get_dart_game
from fishing import get_fishing_game
from dalgona import get_dalgona_game
from mafia import get_mafia_game, MafiaJoinView
from wanage import get_wanage_game
from matsuri_bingo import get_matsuri_bingo_game, BingoType, initialize_bingo_system
from snowman import get_snowman_game  # 눈사람 게임 추가
from unittest.mock import AsyncMock, Mock
import random
from mafia import GamePhase

# 디버그 설정
from debug_config import debug_config, debug_log

logger = logging.getLogger(__name__)

class DailyGameTracker:
    """일일 게임 플레이 추적 - JSON 파일 기반"""
    def __init__(self):
        self.free_limit = float('inf')
        self.data_file = Path("daily_game_data.json")
        self.game_plays = self._load_data()
        self.last_cleanup = datetime.now()
        self._save_lock = asyncio.Lock()  # 저장 동시성 제어
        
        debug_log("DAILY_TRACKER", f"Initialized with data file: {self.data_file}")
    
    def _load_data(self) -> Dict:
        """JSON 파일에서 데이터 로드"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 날짜 문자열을 date 객체로 변환
                    converted_data = {}
                    for user_id, games in data.items():
                        converted_data[user_id] = {}
                        for game_type, dates in games.items():
                            converted_data[user_id][game_type] = {}
                            for date_str, count in dates.items():
                                try:
                                    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                                    converted_data[user_id][game_type][date_obj] = count
                                except:
                                    pass
                    debug_log("DAILY_TRACKER", f"Loaded data for {len(converted_data)} users")
                    return converted_data
            except Exception as e:
                logger.error(f"Failed to load daily game data: {e}")
                return {}
        else:
            debug_log("DAILY_TRACKER", "No existing data file found")
            return {}
    
    async def _save_data(self):
        """데이터를 JSON 파일에 저장"""
        async with self._save_lock:
            try:
                # date 객체를 문자열로 변환
                converted_data = {}
                for user_id, games in self.game_plays.items():
                    converted_data[user_id] = {}
                    for game_type, dates in games.items():
                        converted_data[user_id][game_type] = {}
                        for date_obj, count in dates.items():
                            date_str = date_obj.strftime("%Y-%m-%d")
                            converted_data[user_id][game_type][date_str] = count
                
                # 임시 파일에 먼저 쓰고 원자적으로 교체
                temp_file = self.data_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(converted_data, f, ensure_ascii=False, indent=2)
                
                # 원자적 파일 교체
                temp_file.replace(self.data_file)
                debug_log("DAILY_TRACKER", "Data saved successfully")
            except Exception as e:
                logger.error(f"Failed to save daily game data: {e}")
    
    async def cleanup_old_data(self):
        """오래된 데이터 정리"""
        current_time = datetime.now()
        if (current_time - self.last_cleanup).days >= 1:
            today = date.today()
            cutoff_date = today - timedelta(days=7)
            
            # 7일 이상 지난 데이터 삭제
            changed = False
            for user_id in list(self.game_plays.keys()):
                for game_type in list(self.game_plays[user_id].keys()):
                    old_dates = [d for d in self.game_plays[user_id][game_type].keys() if d < cutoff_date]
                    for old_date in old_dates:
                        del self.game_plays[user_id][game_type][old_date]
                        changed = True
                    
                    # 빈 게임 타입 삭제
                    if not self.game_plays[user_id][game_type]:
                        del self.game_plays[user_id][game_type]
                
                # 빈 유저 삭제
                if not self.game_plays[user_id]:
                    del self.game_plays[user_id]
            
            self.last_cleanup = current_time
            
            # 변경사항이 있으면 저장
            if changed:
                await self._save_data()
            
            debug_log("DAILY_TRACKER", f"Cleaned up old data. Remaining users: {len(self.game_plays)}")
    
    async def check_eligibility(self, user_id: str, game_type: str) -> tuple[bool, str]:
        """게임 참가 자격 확인 (차감하지 않음)"""
        # 정기 정리
        await self.cleanup_old_data()
        
        today = date.today()
        
        # 사용자 게임 기록 초기화
        if user_id not in self.game_plays:
            self.game_plays[user_id] = {}
        if game_type not in self.game_plays[user_id]:
            self.game_plays[user_id][game_type] = {}
        
        # 오늘 플레이 횟수
        plays_today = self.game_plays[user_id][game_type].get(today, 0)
        
        if plays_today < self.free_limit:
            return True, "free"
        else:
            # 코인 확인
            try:
                from utility import get_user_inventory
                user_data = await get_user_inventory(user_id)
                
                if not user_data:
                    return False, "유저 정보를 찾을 수 없습니다."
                
                if user_data.get("coins", 0) < 1:
                    remaining_text = f"오늘의 무료 {game_type} 게임을 모두 사용했습니다. ({self.free_limit}/{self.free_limit})\n"
                    remaining_text += "게임을 계속하려면 1코인이 필요합니다."
                    return False, remaining_text
                
                return True, "paid"
            except Exception as e:
                logger.error(f"Failed to check user inventory: {e}")
                return False, "유저 정보 조회 중 오류가 발생했습니다."
    
    async def consume_play(self, user_id: str, game_type: str, play_type: str):
        """게임 플레이 소비 (실제 차감)"""
        today = date.today()
        
        # 플레이 카운트 증가
        if today not in self.game_plays[user_id][game_type]:
            self.game_plays[user_id][game_type][today] = 0
        
        self.game_plays[user_id][game_type][today] += 1
        
        # 데이터 저장
        await self._save_data()
        
        # 유료 게임인 경우 코인 차감
        if play_type == "paid":
            from utility import update_player_balance
            await update_player_balance(user_id, -1)
            debug_log("GAME", f"User {user_id} paid 1 coin for {game_type}")
    
    def get_remaining_free_games(self, user_id: str, game_type: str) -> int:
        """남은 무료 게임 수 조회 - 항상 무한대"""
        return float('inf')
    
    async def refund_play(self, user_id: str, game_type: str, play_type: str):
        """게임 플레이 환불 (에러 발생 시)"""
        today = date.today()
        
        # 플레이 카운트가 있는 경우에만 감소
        if (user_id in self.game_plays and 
            game_type in self.game_plays[user_id] and
            today in self.game_plays[user_id][game_type] and
            self.game_plays[user_id][game_type][today] > 0):
            
            self.game_plays[user_id][game_type][today] -= 1
            await self._save_data()
            
            debug_log("DAILY_TRACKER", f"Refunded play for user {user_id}, game {game_type}")
        
        # 유료 게임인 경우 코인 환불
        if play_type == "paid":
            from utility import update_player_balance
            await update_player_balance(user_id, 1)
            debug_log("GAME", f"Refunded 1 coin to user {user_id} for {game_type}")

# 전역 일일 게임 추적기
daily_tracker = DailyGameTracker()

class MinigamesCog(commands.Cog):
    """일본 축제 테마 미니게임 모음"""
    
    def __init__(self, bot):
        self.bot = bot
        self.dart_game = get_dart_game()
        self.fishing_game = get_fishing_game()
        self.dalgona_game = get_dalgona_game()
        self.mafia_game = get_mafia_game()
        self.wanage_game = get_wanage_game()
        self.bingo_game = get_matsuri_bingo_game()
        self.snowman_game = get_snowman_game()  # 눈사람 게임
        
        # 빙고 시스템 초기화 태스크
        self.bot.loop.create_task(self._initialize_bingo())
    
    async def _initialize_bingo(self):
        """빙고 시스템 초기화"""
        await self.bot.wait_until_ready()
        await initialize_bingo_system()
        logger.info("빙고 시스템 초기화 완료")
    
    # 게임 그룹
    game_group = app_commands.Group(name="게임", description="축제 미니게임")
    
    @game_group.command(name="사격", description="🎯 사격 게임을 시작합니다")
    @app_commands.describe(multiplayer="멀티플레이어 모드로 시작")
    async def dart(self, interaction: discord.Interaction, multiplayer: bool = False):
        """사격 게임"""
        user_id = str(interaction.user.id)
        
        # 먼저 빠른 체크 (메모리에서)
        today = date.today()
        if (user_id in daily_tracker.game_plays and 
            "사격" in daily_tracker.game_plays[user_id] and
            daily_tracker.game_plays[user_id]["사격"].get(today, 0) >= daily_tracker.free_limit):
            # 유료 게임일 가능성이 있으므로 defer
            await interaction.response.defer()
            
            eligible, status = await daily_tracker.check_eligibility(user_id, "사격")
            
            if not eligible:
                await interaction.followup.send(status, ephemeral=True)
                return
            
            # 코인 차감
            await daily_tracker.consume_play(user_id, "사격", status)
            
            # 새 인터랙션 생성을 위해 채널에서 게임 시작
            game_channel = interaction.channel
            game_message = await interaction.followup.send("사격 게임을 시작합니다...")
            
            # 기존 메시지 삭제하고 게임 시작
            await game_message.delete()
            
            # 새로운 인터랙션 없이 직접 게임 시작 메시지 전송
            await self.dart_game.start_game_direct(game_channel, interaction.user, is_multiplayer=multiplayer)
        else:
            # 무료 게임 - defer 없이 바로 시작
            eligible, status = await daily_tracker.check_eligibility(user_id, "사격")
            
            if not eligible:
                await interaction.response.send_message(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "사격", status)
            
            # 남은 무료 게임 표시
            if status == "free":
                remaining = daily_tracker.get_remaining_free_games(user_id, "사격")
                if remaining > 0:
                    asyncio.create_task(interaction.channel.send(
                        f"💡 {interaction.user.mention}님의 오늘 남은 무료 사격: {remaining}회",
                        delete_after=10
                    ))
            
            await self.dart_game.start_game(interaction, is_multiplayer=multiplayer)
    
    @game_group.command(name="금붕어잡기", description="🐠 금붕어 잡기를 시작합니다")
    async def fishing(self, interaction: discord.Interaction):
        """금붕어잡기 게임"""
        user_id = str(interaction.user.id)
        
        # 빠른 체크
        today = date.today()
        if (user_id in daily_tracker.game_plays and 
            "금붕어잡기" in daily_tracker.game_plays[user_id] and
            daily_tracker.game_plays[user_id]["금붕어잡기"].get(today, 0) >= daily_tracker.free_limit):
            # 유료 게임일 가능성
            await interaction.response.defer()
            
            eligible, status = await daily_tracker.check_eligibility(user_id, "금붕어잡기")
            
            if not eligible:
                await interaction.followup.send(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "금붕어잡기", status)
            
            # 게임 시작
            game_channel = interaction.channel
            game_message = await interaction.followup.send("낚싯대를 준비합니다...")
            await game_message.delete()
            
            # 채널에 직접 메시지 전송하여 게임 시작
            await self.fishing_game.start_fishing_direct(game_channel, interaction.user)
        else:
            # 무료 게임
            eligible, status = await daily_tracker.check_eligibility(user_id, "금붕어잡기")
            
            if not eligible:
                await interaction.response.send_message(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "금붕어잡기", status)
            
            if status == "free":
                remaining = daily_tracker.get_remaining_free_games(user_id, "금붕어잡기")
                if remaining > 0:
                    asyncio.create_task(interaction.channel.send(
                        f"💡 {interaction.user.mention}님의 오늘 남은 무료 금붕어잡기: {remaining}회",
                        delete_after=10
                    ))
            
            await self.fishing_game.start_fishing(interaction)
    
    @game_group.command(name="달고나", description="🍪 달고나 뽑기를 시작합니다")
    async def dalgona(self, interaction: discord.Interaction):
        """달고나 게임"""
        user_id = str(interaction.user.id)
        
        today = date.today()
        if (user_id in daily_tracker.game_plays and 
            "달고나" in daily_tracker.game_plays[user_id] and
            daily_tracker.game_plays[user_id]["달고나"].get(today, 0) >= daily_tracker.free_limit):
            await interaction.response.defer()
            
            eligible, status = await daily_tracker.check_eligibility(user_id, "달고나")
            
            if not eligible:
                await interaction.followup.send(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "달고나", status)
            
            game_channel = interaction.channel
            game_message = await interaction.followup.send("달고나를 준비합니다...")
            await game_message.delete()
            
            await self.dalgona_game.start_game_direct(game_channel, interaction.user)
        else:
            eligible, status = await daily_tracker.check_eligibility(user_id, "달고나")
            
            if not eligible:
                await interaction.response.send_message(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "달고나", status)
            
            if status == "free":
                remaining = daily_tracker.get_remaining_free_games(user_id, "달고나")
                if remaining > 0:
                    asyncio.create_task(interaction.channel.send(
                        f"💡 {interaction.user.mention}님의 오늘 남은 무료 달고나: {remaining}회",
                        delete_after=10
                    ))
            
            await self.dalgona_game.start_game(interaction)

    @game_group.command(name="눈사람", description="❄️ 눈사람 만들기 게임을 시작합니다")
    async def snowman(self, interaction: discord.Interaction):
        """눈사람 게임"""
        user_id = str(interaction.user.id)
        
        today = date.today()
        if (user_id in daily_tracker.game_plays and 
            "눈사람" in daily_tracker.game_plays[user_id] and
            daily_tracker.game_plays[user_id]["눈사람"].get(today, 0) >= daily_tracker.free_limit):
            await interaction.response.defer()
            
            eligible, status = await daily_tracker.check_eligibility(user_id, "눈사람")
            
            if not eligible:
                await interaction.followup.send(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "눈사람", status)
            
            game_channel = interaction.channel
            game_message = await interaction.followup.send("눈을 준비합니다...")
            await game_message.delete()
            
            await self.snowman_game.start_game_direct(game_channel, interaction.user)
        else:
            eligible, status = await daily_tracker.check_eligibility(user_id, "눈사람")
            
            if not eligible:
                await interaction.response.send_message(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "눈사람", status)
            
            if status == "free":
                remaining = daily_tracker.get_remaining_free_games(user_id, "눈사람")
                if remaining > 0:
                    asyncio.create_task(interaction.channel.send(
                        f"💡 {interaction.user.mention}님의 오늘 남은 무료 눈사람: {remaining}회",
                        delete_after=10
                    ))
            
            await self.snowman_game.start_game(interaction)

    mafia_test_group = app_commands.Group(
        name="마피아테스트", 
        description="마피아 게임 테스트 (관리자 전용)",
        default_permissions=discord.Permissions(administrator=True)
    )
    
    @mafia_test_group.command(name="시작", description="가상 플레이어로 마피아 게임 테스트")
    @app_commands.describe(
        player_count="테스트할 플레이어 수 (4-35)",
        with_real_players="실제 플레이어 포함 여부"
    )
    async def test_start(
        self, 
        interaction: discord.Interaction, 
        player_count: int = 10,
        with_real_players: bool = False
    ):
        """가상 플레이어로 마피아 게임 시작"""
        # 플레이어 수 확인
        if not (4 <= player_count <= 35):
            await interaction.response.send_message(
                "플레이어 수는 4-35명 사이여야 합니다.",
                ephemeral=True
            )
            return
        
        channel_id = interaction.channel_id
        
        # 이미 진행 중인 게임 확인
        if channel_id in self.mafia_game.games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        # 가상 플레이어 생성
        test_players = []
        
        # 실제 플레이어 추가
        if with_real_players:
            test_players.append(interaction.user)
            player_count -= 1
        
        # 가상 플레이어 생성
        for i in range(player_count):
            mock_user = Mock(spec=discord.Member)
            mock_user.id = 900000 + i  # 가상 ID
            mock_user.display_name = f"TestPlayer{i+1}"
            mock_user.mention = f"<@{mock_user.id}>"
            mock_user.send = AsyncMock()  # DM 전송 모킹
            test_players.append(mock_user)
        
        # 역할 배정
        player_data = self.mafia_game.assign_roles(test_players)
        
        # 게임 데이터 생성
        game_data = {
            "channel": interaction.channel,
            "players": player_data,
            "phase": GamePhase.WAITING,
            "day": 0,
            "night_actions": {},
            "day_votes": {},
            "game_log": ["[TEST MODE] 게임이 테스트 모드로 시작되었습니다."],
            "message": None,
            "test_mode": True  # 테스트 모드 표시
        }
        
        self.mafia_game.games[channel_id] = game_data
        
        # 시작 메시지
        embed = discord.Embed(
            title="🧪 마피아 게임 테스트 모드",
            description=f"**테스트 플레이어**: {len(test_players)}명\n"
                       f"**실제 플레이어 포함**: {'예' if with_real_players else '아니오'}",
            color=discord.Color.purple()
        )
        
        # 역할 분포
        role_counts = {}
        for player in player_data.values():
            role_name = player.role.value[0]
            role_counts[role_name] = role_counts.get(role_name, 0) + 1
        
        role_info = "\n".join([
            f"{role}: {count}명" 
            for role, count in role_counts.items()
        ])
        
        embed.add_field(
            name="역할 분포",
            value=role_info,
            inline=False
        )
        
        # 플레이어 목록 (처음 10명만)
        player_list = []
        for i, (pid, player) in enumerate(player_data.items()):
            if i < 10:
                player_list.append(
                    f"{player.user.display_name} - {player.role.value[1]} {player.role.value[0]}"
                )
            elif i == 10:
                player_list.append(f"... 외 {len(player_data) - 10}명")
                break
        
        embed.add_field(
            name="플레이어 목록",
            value="\n".join(player_list),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
        game_data["message"] = await interaction.original_response()
        
        # 자동으로 첫 밤 시작
        await asyncio.sleep(3)
        await self.mafia_game.night_phase(channel_id)
    
    @mafia_test_group.command(name="상태", description="현재 마피아 게임 상태 확인")
    async def test_status(self, interaction: discord.Interaction):
        """게임 상태 확인"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        game_data = self.mafia_game.games[channel_id]
        
        embed = discord.Embed(
            title="🔍 마피아 게임 상태",
            color=discord.Color.blue()
        )
        
        # 기본 정보
        embed.add_field(
            name="게임 정보",
            value=f"**단계**: {game_data['phase'].value}\n"
                  f"**일차**: {game_data['day']}일\n"
                  f"**테스트 모드**: {'예' if game_data.get('test_mode') else '아니오'}",
            inline=False
        )
        
        # 생존자 통계
        alive_players = [p for p in game_data["players"].values() if p.alive]
        dead_players = [p for p in game_data["players"].values() if not p.alive]
        
        role_stats = {}
        for player in alive_players:
            role = player.role.value[0]
            role_stats[role] = role_stats.get(role, 0) + 1
        
        stats_text = f"**총 생존자**: {len(alive_players)}명\n"
        for role, count in role_stats.items():
            stats_text += f"- {role}: {count}명\n"
        stats_text += f"**사망자**: {len(dead_players)}명"
        
        embed.add_field(
            name="생존자 통계",
            value=stats_text,
            inline=False
        )
        
        # 최근 행동 (밤 페이즈인 경우)
        if game_data["phase"] == GamePhase.NIGHT and game_data["night_actions"]:
            actions_text = []
            for action, target_id in list(game_data["night_actions"].items())[:5]:
                if action.startswith("mafia_"):
                    actor_id = int(action.split("_")[1])
                    if actor_id in game_data["players"]:
                        actor = game_data["players"][actor_id].user.display_name
                        target = game_data["players"].get(target_id)
                        if target:
                            actions_text.append(
                                f"🔫 {actor} → {target.user.display_name}"
                            )
            
            if actions_text:
                embed.add_field(
                    name="현재 밤 행동",
                    value="\n".join(actions_text[:5]),
                    inline=False
                )
        
        # 최근 로그
        if game_data["game_log"]:
            recent_logs = game_data["game_log"][-5:]
            embed.add_field(
                name="최근 로그",
                value="\n".join(recent_logs),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @mafia_test_group.command(name="페이즈", description="게임 페이즈 강제 전환")
    @app_commands.describe(phase="전환할 페이즈")
    @app_commands.choices(phase=[
        app_commands.Choice(name="밤", value="night"),
        app_commands.Choice(name="낮 토론", value="discussion"),
        app_commands.Choice(name="낮 투표", value="vote")
    ])
    async def test_phase(self, interaction: discord.Interaction, phase: str):
        """페이즈 강제 전환"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        if phase == "night":
            await self.mafia_game.night_phase(channel_id)
            phase_name = "밤"
        elif phase == "discussion":
            await self.mafia_game.day_discussion_phase(channel_id)
            phase_name = "낮 토론"
        else:  # vote
            await self.mafia_game.day_vote_phase(channel_id)
            phase_name = "낮 투표"
        
        await interaction.followup.send(
            f"페이즈를 {phase_name}으로 전환했습니다.",
            ephemeral=True
        )
    
    @mafia_test_group.command(name="제거", description="플레이어 강제 제거")
    @app_commands.describe(
        player_name="제거할 플레이어 이름",
        revive="부활 여부"
    )
    async def test_eliminate(
        self, 
        interaction: discord.Interaction, 
        player_name: str,
        revive: bool = False
    ):
        """플레이어 제거/부활"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        game_data = self.mafia_game.games[channel_id]
        
        # 플레이어 찾기
        target_player = None
        for player in game_data["players"].values():
            if player.user.display_name.lower() == player_name.lower():
                target_player = player
                break
        
        if not target_player:
            # 부분 일치 검색
            for player in game_data["players"].values():
                if player_name.lower() in player.user.display_name.lower():
                    target_player = player
                    break
        
        if not target_player:
            await interaction.response.send_message(
                f"플레이어 '{player_name}'을(를) 찾을 수 없습니다.",
                ephemeral=True
            )
            return
        
        # 상태 변경
        if revive:
            target_player.alive = True
            action = "부활"
        else:
            target_player.alive = False
            action = "제거"
        
        game_data["game_log"].append(
            f"[ADMIN] {target_player.user.display_name} {action}"
        )
        
        embed = discord.Embed(
            title=f"플레이어 {action}",
            description=f"{target_player.user.display_name} ({target_player.role.value[0]})을(를) {action}했습니다.",
            color=discord.Color.green() if revive else discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @mafia_test_group.command(name="행동", description="밤 행동 시뮬레이션")
    @app_commands.describe(
        auto_actions="자동으로 모든 행동 생성"
    )
    async def test_actions(self, interaction: discord.Interaction, auto_actions: bool = True):
        """밤 행동 시뮬레이션"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        game_data = self.mafia_game.games[channel_id]
        
        if game_data["phase"] != GamePhase.NIGHT:
            await interaction.response.send_message(
                "밤 페이즈에서만 사용 가능합니다.",
                ephemeral=True
            )
            return
        
        if auto_actions:
            # 자동으로 행동 생성
            alive_players = [p for p in game_data["players"].values() if p.alive]
            non_mafia = [p for p in alive_players if p.role != Role.MAFIA]
            
            actions_generated = []
            
            # 마피아 행동
            mafias = [p for p in alive_players if p.role == Role.MAFIA]
            if mafias and non_mafia:
                target = random.choice(non_mafia)
                for mafia in mafias:
                    game_data["night_actions"][f"mafia_{mafia.user.id}"] = target.user.id
                actions_generated.append(
                    f"🔫 마피아들이 {target.user.display_name}을(를) 목표로 선택"
                )
            
            # 경찰 행동
            police_list = [p for p in alive_players if p.role == Role.POLICE]
            for police in police_list:
                others = [p for p in alive_players if p.user.id != police.user.id]
                if others:
                    target = random.choice(others)
                    game_data["night_actions"][f"police_{police.user.id}"] = target.user.id
                    actions_generated.append(
                        f"👮 {police.user.display_name}이(가) {target.user.display_name}을(를) 조사"
                    )
            
            # 의사 행동
            doctors = [p for p in alive_players if p.role == Role.DOCTOR]
            for doctor in doctors:
                if alive_players:
                    target = random.choice(alive_players)
                    game_data["night_actions"][f"doctor_{doctor.user.id}"] = target.user.id
                    actions_generated.append(
                        f"👨‍⚕️ {doctor.user.display_name}이(가) {target.user.display_name}을(를) 보호"
                    )
            
            embed = discord.Embed(
                title="🌙 밤 행동 시뮬레이션",
                description="다음 행동들이 자동 생성되었습니다:",
                color=discord.Color.dark_purple()
            )
            
            if actions_generated:
                embed.add_field(
                    name="생성된 행동",
                    value="\n".join(actions_generated[:10]),  # 최대 10개
                    inline=False
                )
            else:
                embed.add_field(
                    name="결과",
                    value="생성할 행동이 없습니다.",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # 3초 후 자동으로 밤 행동 처리
            await asyncio.sleep(3)
            await self.mafia_game.process_night_actions(channel_id)
        else:
            await interaction.response.send_message(
                "수동 행동 설정은 아직 구현되지 않았습니다.",
                ephemeral=True
            )
    
    @mafia_test_group.command(name="투표", description="투표 시뮬레이션")
    @app_commands.describe(
        target_name="투표 대상",
        vote_count="투표 수"
    )
    async def test_vote(
        self, 
        interaction: discord.Interaction, 
        target_name: str,
        vote_count: int = 5
    ):
        """투표 시뮬레이션"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        game_data = self.mafia_game.games[channel_id]
        
        if game_data["phase"] != GamePhase.DAY_VOTE:
            await interaction.response.send_message(
                "투표 페이즈에서만 사용 가능합니다.",
                ephemeral=True
            )
            return
        
        # 대상 찾기
        target_player = None
        for player in game_data["players"].values():
            if player.alive and target_name.lower() in player.user.display_name.lower():
                target_player = player
                break
        
        if not target_player:
            await interaction.response.send_message(
                f"생존한 플레이어 '{target_name}'을(를) 찾을 수 없습니다.",
                ephemeral=True
            )
            return
        
        # 투표 추가
        target_player.votes += vote_count
        
        embed = discord.Embed(
            title="🗳️ 투표 시뮬레이션",
            description=f"{target_player.user.display_name}에게 {vote_count}표 추가\n"
                       f"현재 득표수: {target_player.votes}표",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @mafia_test_group.command(name="종료", description="게임 강제 종료")
    @app_commands.describe(winner="승리팀 지정")
    @app_commands.choices(winner=[
        app_commands.Choice(name="마피아", value="마피아"),
        app_commands.Choice(name="시민", value="시민"),
        app_commands.Choice(name="강제종료", value="force")
    ])
    async def test_end(self, interaction: discord.Interaction, winner: str = "force"):
        """게임 종료"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        if winner == "force":
            # 단순 강제 종료
            del self.mafia_game.games[channel_id]
            await interaction.response.send_message(
                "게임을 강제 종료했습니다.",
                ephemeral=True
            )
        else:
            # 정상 종료 처리
            await interaction.response.defer()
            await self.mafia_game.end_game(channel_id, winner)
            await interaction.followup.send(
                f"{winner} 팀 승리로 게임을 종료했습니다.",
                ephemeral=True
            )
    
    @mafia_test_group.command(name="목록", description="모든 플레이어 목록 확인")
    async def test_list(self, interaction: discord.Interaction):
        """플레이어 목록"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.mafia_game.games:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다.",
                ephemeral=True
            )
            return
        
        game_data = self.mafia_game.games[channel_id]
        
        # 역할별로 그룹화
        role_groups = {
            Role.MAFIA: [],
            Role.POLICE: [],
            Role.DOCTOR: [],
            Role.CITIZEN: []
        }
        
        for player in game_data["players"].values():
            role_groups[player.role].append(player)
        
        # 여러 임베드로 나누기
        embeds = []
        
        for role, players in role_groups.items():
            if not players:
                continue
            
            embed = discord.Embed(
                title=f"{role.value[1]} {role.value[0]} ({len(players)}명)",
                color=discord.Color.red() if role == Role.MAFIA else discord.Color.blue()
            )
            
            # 25명씩 필드 나누기
            for i in range(0, len(players), 25):
                chunk = players[i:i+25]
                player_list = []
                
                for player in chunk:
                    status = "✅" if player.alive else "💀"
                    votes = f" ({player.votes}표)" if hasattr(player, 'votes') and player.votes > 0 else ""
                    player_list.append(
                        f"{status} {player.user.display_name}{votes}"
                    )
                
                field_name = f"목록" if i == 0 else f"목록 (계속)"
                embed.add_field(
                    name=field_name,
                    value="\n".join(player_list),
                    inline=False
                )
            
            embeds.append(embed)
        
        # 최대 10개 임베드만 전송
        await interaction.response.send_message(
            embeds=embeds[:10],
            ephemeral=True
        )


    @game_group.command(name="마피아", description="🔫 마피아 게임을 시작하거나 진행합니다")
    @app_commands.describe(action="게임 액션")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="페이즈전환", value="phase")
        ]
    )
    async def mafia(self, interaction: discord.Interaction, action: str = None):
        """마피아 게임 - 무료"""
        channel_id = interaction.channel_id
        
        if action == "phase":
            # 페이즈 전환
            if channel_id not in self.mafia_game.games:
                await interaction.response.send_message(
                    "진행 중인 게임이 없습니다!",
                    ephemeral=True
                )
                return
            
            game_data = self.mafia_game.games[channel_id]
            
            # 호스트 확인
            if interaction.user.id != game_data.get('host'):
                await interaction.response.send_message(
                    "게임 호스트만 페이즈를 전환할 수 있습니다!",
                    ephemeral=True
                )
                return
            
            # 다음 페이즈로 전환
            await interaction.response.defer()
            await self.mafia_game.next_phase(channel_id)
            await interaction.followup.send("다음 페이즈로 전환했습니다.", ephemeral=True)
        
        else:
            # 기본 동작: 게임 모집
            if channel_id in self.mafia_game.games:
                await interaction.response.send_message(
                    "이미 진행 중인 게임이 있습니다!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🔫 마피아 게임 모집",
                description=f"{interaction.user.display_name}님이 마피아 게임을 시작합니다!\n"
                        f"참가하려면 아래 버튼을 누르세요.\n\n"
                        f"최소 인원: {self.mafia_game.MIN_PLAYERS}명\n"
                        f"최대 인원: {self.mafia_game.MAX_PLAYERS}명\n\n"
                        f"⏰ **시간 제한 없음** - 호스트가 직접 시작",
                color=discord.Color.dark_red()
            )
            
            # 현재 참가자 필드 추가
            embed.add_field(
                name="현재 참가자",
                value=f"**1명** / {self.mafia_game.MAX_PLAYERS}명 (호스트 자동 참가)",
                inline=False
            )
            
            # 수정된 JoinView 생성 (timeout 없음, 호스트 정보 추가)
            view = MafiaJoinView(self.mafia_game, interaction.user)
            await interaction.response.send_message(embed=embed, view=view)
        
    @game_group.command(name="와나게", description="⭕ 링 던지기 게임을 시작합니다")
    async def wanage(self, interaction: discord.Interaction):
        """와나게 (링 던지기) 게임"""
        user_id = str(interaction.user.id)
        
        today = date.today()
        if (user_id in daily_tracker.game_plays and 
            "와나게" in daily_tracker.game_plays[user_id] and
            daily_tracker.game_plays[user_id]["와나게"].get(today, 0) >= daily_tracker.free_limit):
            await interaction.response.defer()
            
            eligible, status = await daily_tracker.check_eligibility(user_id, "와나게")
            
            if not eligible:
                await interaction.followup.send(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "와나게", status)
            
            game_channel = interaction.channel
            game_message = await interaction.followup.send("링을 준비합니다...")
            await game_message.delete()
            
            await self.wanage_game.start_game_direct(game_channel, interaction.user)
        else:
            eligible, status = await daily_tracker.check_eligibility(user_id, "와나게")
            
            if not eligible:
                await interaction.response.send_message(status, ephemeral=True)
                return
            
            await daily_tracker.consume_play(user_id, "와나게", status)
            
            if status == "free":
                remaining = daily_tracker.get_remaining_free_games(user_id, "와나게")
                if remaining > 0:
                    asyncio.create_task(interaction.channel.send(
                        f"💡 {interaction.user.mention}님의 오늘 남은 무료 와나게: {remaining}회",
                        delete_after=10
                    ))
            
            await self.wanage_game.start_game(interaction)
    
    @game_group.command(name="빙고", description="🎊 마츠리 빙고 게임을 만듭니다")
    async def bingo(self, interaction: discord.Interaction):
        """마츠리 빙고 게임 - 참가 시 개별 코인 체크"""
        await self.bingo_game.create_game(interaction)
    

    
    @game_group.command(name="강제종료", description="🛑 현재 채널의 진행중인 게임을 강제 종료합니다")
    @app_commands.describe(game_type="종료할 게임 종류")
    @app_commands.choices(game_type=[
        app_commands.Choice(name="전체(주의할것. all stop button)", value="all"),
        app_commands.Choice(name="사격", value="dart"),
        app_commands.Choice(name="금붕어잡기", value="fishing"),
        app_commands.Choice(name="달고나", value="dalgona"),
        app_commands.Choice(name="마피아", value="mafia"),
        app_commands.Choice(name="와나게", value="wanage"),
        app_commands.Choice(name="빙고", value="bingo"),
        app_commands.Choice(name="눈사람", value="snowman"),
    ])
    async def force_stop(self, interaction: discord.Interaction, game_type: str = "all"):
        """게임 강제 종료"""
        channel_id = interaction.channel_id
        terminated = []
        blocked = []  # 종료가 차단된 게임들
        
        # 각 게임 확인 및 종료
        if game_type in ["all", "dart"] and channel_id in self.dart_game.active_games:
            # 업데이트 태스크 정리
            game_data = self.dart_game.active_games[channel_id]
            if "update_task" in game_data:
                game_data["update_task"].cancel()
                try:
                    await game_data["update_task"]
                except asyncio.CancelledError:
                    pass
            
            del self.dart_game.active_games[channel_id]
            terminated.append("사격")
            debug_log("FORCE_STOP", f"Terminated dart game in channel {channel_id}")
        
        if game_type in ["all", "fishing"]:
            # 금붕어잡기 게임 종료 (active_fishing이 아닌 active_games 사용)
            if channel_id in self.fishing_game.active_games:
                fishing_data = self.fishing_game.active_games[channel_id]
                
                # 태스크 정리
                if "spawn_task" in fishing_data:
                    fishing_data["spawn_task"].cancel()
                if "update_task" in fishing_data:
                    fishing_data["update_task"].cancel()
                
                del self.fishing_game.active_games[channel_id]
                terminated.append("금붕어잡기")
                debug_log("FORCE_STOP", f"Terminated fishing game in channel {channel_id}")
        
        if game_type in ["all", "dalgona"] and channel_id in self.dalgona_game.active_games:
            del self.dalgona_game.active_games[channel_id]
            terminated.append("달고나")
            debug_log("FORCE_STOP", f"Terminated dalgona game in channel {channel_id}")
        
        if game_type in ["all", "mafia"] and channel_id in self.mafia_game.games:
            del self.mafia_game.games[channel_id]
            terminated.append("마피아")
            debug_log("FORCE_STOP", f"Terminated mafia game in channel {channel_id}")
        
        if game_type in ["all", "wanage"] and channel_id in self.wanage_game.active_games:
            game_data = self.wanage_game.active_games[channel_id]
            
            # 괴수가 접근 중인지 확인
            if game_data.get("approaching_monster"):
                blocked.append("와나게")
                debug_log("FORCE_STOP", f"Cannot terminate wanage game - monster approaching!")
            else:
                # 괴수 태스크 정리
                if "monster_task" in game_data and game_data["monster_task"]:
                    game_data["monster_task"].cancel()
                    try:
                        await game_data["monster_task"]
                    except asyncio.CancelledError:
                        pass
                
                del self.wanage_game.active_games[channel_id]
                terminated.append("와나게")
                debug_log("FORCE_STOP", f"Terminated wanage game in channel {channel_id}")
        
        if game_type in ["all", "bingo"] and channel_id in self.bingo_game.active_games:
            del self.bingo_game.active_games[channel_id]
            terminated.append("빙고")
            debug_log("FORCE_STOP", f"Terminated bingo game in channel {channel_id}")
        
        if game_type in ["all", "snowman"] and channel_id in self.snowman_game.active_games:
            game_data = self.snowman_game.active_games[channel_id]
            
            # 모든 태스크 정리
            tasks_to_cancel = []
            if "move_task" in game_data and game_data["move_task"]:
                tasks_to_cancel.append(game_data["move_task"])
            
            # 태스크 취소
            for task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"Task cleanup error: {e}")
            
            # View 비활성화
            if game_data.get("view"):
                game_data["view"].stop()
            
            # 메시지의 View 제거
            if game_data.get("message"):
                try:
                    await game_data["message"].edit(view=None)
                except Exception as e:
                    logger.warning(f"Failed to remove view: {e}")
            
            del self.snowman_game.active_games[channel_id]
            terminated.append("눈사람")
            debug_log("FORCE_STOP", f"Terminated snowman game in channel {channel_id}")
        
        # 전투 게임 종료 추가
        if game_type in ["all", "battle"]:
            if hasattr(self, 'battle_game') and channel_id in self.battle_game.active_battles:
                battle_data = self.battle_game.active_battles[channel_id]
                
                del self.battle_game.active_battles[channel_id]
                terminated.append("전투")
                debug_log("FORCE_STOP", f"Terminated battle game in channel {channel_id}")
            
            # 대기 중인 다이스 정리
            if hasattr(self, 'battle_game') and channel_id in self.battle_game.pending_dice:
                del self.battle_game.pending_dice[channel_id]
        
        # 결과 메시지
        if terminated or blocked:
            embed = discord.Embed(
                title="🛑 게임 강제 종료",
                color=discord.Color.red()
            )
            
            if terminated:
                embed.add_field(
                    name="✅ 종료된 게임",
                    value=", ".join(terminated),
                    inline=False
                )
            
            if blocked:
                embed.add_field(
                    name="❌ 종료할 수 없는 게임",
                    value=f"{', '.join(blocked)}\n⚠️ 괴수가 접근 중이어서 종료할 수 없습니다!",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "현재 채널에서 진행 중인 게임이 없습니다.",
                ephemeral=True
            )
    
    @game_group.command(name="게임상태", description="📊 오늘의 게임 플레이 상태를 확인합니다")
    async def game_status(self, interaction: discord.Interaction):
        """게임 플레이 상태 확인"""
        # 먼저 defer로 응답 시간 연장
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        today = date.today()
        
        embed = discord.Embed(
            title="📊 오늘의 게임 플레이 상태",
            description=f"{interaction.user.mention}님의 {today} 플레이 기록",
            color=discord.Color.blue()
        )
        
        game_types = ["사격", "금붕어잡기", "달고나", "와나게", "눈사람"]
        total_plays = 0
        total_remaining = 0
        
        for game in game_types:
            remaining = daily_tracker.get_remaining_free_games(user_id, game)
            plays = daily_tracker.free_limit - remaining
            total_plays += plays
            total_remaining += remaining
            
            status = f"플레이: {plays}회\n"
            if remaining > 0:
                status += f"무료 남음: {remaining}회"
            else:
                status += "무료 소진 (1코인 필요)"
            
            # 이모지 추가
            game_emoji = {
                "사격": "🎯",
                "금붕어잡기": "🐠",
                "달고나": "🍪",
                "와나게": "⭕",
                "눈사람": "❄️"
            }.get(game, "🎮")
            
            embed.add_field(
                name=f"{game_emoji} {game}",
                value=status,
                inline=True
            )
        
        # 무료 게임 추가
        embed.add_field(
            name="🆓 무료 게임",
            value="⚔️ 전투 - 항상 무료\n🔫 마피아 - 항상 무료\n🎊 빙고 - 참가비 별도",
            inline=True
        )
        
        # 전체 통계
        embed.add_field(
            name="📈 오늘의 전체 통계",
            value=f"총 플레이: {total_plays}회\n"
                  f"남은 무료 게임: {total_remaining}회",
            inline=False
        )
        
        # 현재 코인
        try:
            from utility import get_user_inventory
            user_data = await get_user_inventory(user_id)
            if user_data:
                coins = user_data.get("coins", 0)
                embed.add_field(
                    name="💰 보유 코인",
                    value=f"{coins}코인",
                    inline=False
                )
                
                # 코인이 부족한 경우 안내
                if coins == 0 and total_remaining == 0:
                    embed.add_field(
                        name="💡 팁",
                        value="무료 게임을 모두 사용했고 코인이 없습니다.\n"
                              "내일 다시 무료로 플레이하거나 코인을 획득하세요!",
                        inline=False
                    )
        except Exception as e:
            logger.error(f"Failed to get user inventory: {e}")
            embed.add_field(
                name="💰 보유 코인",
                value="조회 실패",
                inline=False
            )
        
        # followup으로 메시지 전송
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @game_group.command(name="도움말", description="📖 게임 도움말을 표시합니다")
    async def help(self, interaction: discord.Interaction):
        """게임 도움말"""
        embed = discord.Embed(
            title="🎌 일본 축제 미니게임 도움말",
            description="다양한 축제 게임을 즐겨보세요!\n\n"
                       "**일일 무료 플레이**: 각 게임마다 하루 5회 무료\n"
                       "**추가 플레이**: 1코인 필요",
            color=discord.Color.blue()
        )
        
        games_info = [
            ("🎯 사격", "움직이는 목표물을 맞춰 점수를 얻으세요", "/게임 사격", "무료 5회/일"),
            ("🐠 금붕어잡기", "금붕어가 수면위로 떠오르면 재빠르게 잡으세요", "/게임 금붕어잡기", "무료 5회/일"),
            ("🍪 달고나", "모양을 따라 조심히 뜯어내세요", "/게임 달고나", "무료 5회/일"),
            ("🔫 마피아", "마피아를 찾아내는 추리 게임", "/게임 마피아", "항상 무료"),
            ("⭕ 와나게", "거리와 각도를 조절해 링을 던지세요", "/게임 와나게", "무료 5회/일"),
            ("🎊 빙고", "멀티플레이어 빙고 게임", "/게임 빙고", "참가비 별도"),
            ("❄️ 눈사람", "눈을 굴려 눈사람을 만들어보세요", "/게임 눈사람", "무료 5회/일"),
            ("⚔️ 전투", "다른 플레이어와 다이스 전투", "/전투 @상대", "항상 무료")
        ]
        
        for name, desc, command, cost in games_info:
            embed.add_field(
                name=f"{name}",
                value=f"{desc}\n`{command}`\n{cost}",
                inline=True
            )
        
        # 추가 명령어
        embed.add_field(
            name="🛠️ 유틸리티 명령어",
            value="`/게임 게임상태` - 오늘의 플레이 현황\n"
                  "`/게임 강제종료` - 막힌 게임 강제 종료",
            inline=False
        )
        
        # 전투 게임 특별 안내 추가
        embed.add_field(
            name="⚔️ 전투 게임 특별 안내",
            value="전투 게임은 **봇**의 `/주사위` 명령어를 사용합니다.\n"
                  "전투 중 다이스 요청이 나오면 `/주사위`를 입력하세요!",
            inline=False
        )
        
        # 눈사람 게임 특별 안내 추가
        embed.add_field(
            name="❄️ 눈사람 게임 특별 안내",
            value="1단계: 버튼으로 눈을 굴려 크게 만들기\n"
                  "2단계: 타이밍에 맞춰 눈공을 쌓아올리기\n"
                  "서버별 리더보드에서 다른 플레이어와 경쟁!",
            inline=False
        )
        
        embed.set_footer(text="💰 각 게임마다 코인과 아이템을 획득할 수 있습니다! (전투 제외)")
        
        await interaction.response.send_message(embed=embed)
    
    # 디버그 명령어 (관리자 전용)
    @game_group.command(name="디버그", description="🔧 디버그 모드 설정 (관리자 전용)")
    @app_commands.describe(
        mode="디버그 모드",
        level="로그 레벨"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="켜기", value="on"),
            app_commands.Choice(name="끄기", value="off"),
            app_commands.Choice(name="상태", value="status")
        ],
        level=[
            app_commands.Choice(name="OFF", value="OFF"),
            app_commands.Choice(name="ERROR", value="ERROR"),
            app_commands.Choice(name="WARNING", value="WARNING"),
            app_commands.Choice(name="INFO", value="INFO"),
            app_commands.Choice(name="DEBUG", value="DEBUG")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def debug(self, interaction: discord.Interaction, mode: str, level: str = "INFO"):
        """디버그 설정"""
        if mode == "on":
            debug_config.debug_enabled = True
            debug_config.performance_tracking = True
            debug_config.detailed_logging = True
            debug_config.set_debug_level(level)
            
            embed = discord.Embed(
                title="🔧 디버그 모드 활성화",
                description=f"디버그 레벨: {level}\n전투 시스템 디버그도 활성화되었습니다.",
                color=discord.Color.green()
            )
        elif mode == "off":
            debug_config.debug_enabled = False
            debug_config.performance_tracking = False
            debug_config.detailed_logging = False
            
            embed = discord.Embed(
                title="🔧 디버그 모드 비활성화",
                color=discord.Color.red()
            )
        else:  # status
            embed = discord.Embed(
                title="🔧 디버그 상태",
                color=discord.Color.blue()
            )
            embed.add_field(name="디버그 모드", value="✅ 켜짐" if debug_config.debug_enabled else "❌ 꺼짐")
            embed.add_field(name="성능 추적", value="✅ 켜짐" if debug_config.performance_tracking else "❌ 꺼짐")
            embed.add_field(name="상세 로깅", value="✅ 켜짐" if debug_config.detailed_logging else "❌ 꺼짐")
            
            # 활성 게임 상태 추가
            if hasattr(self, 'battle_game'):
                active_battles = len(self.battle_game.active_battles)
                pending_dice = len(self.battle_game.pending_dice)
                embed.add_field(
                    name="⚔️ 전투 게임 상태",
                    value=f"활성 전투: {active_battles}개\n대기 다이스: {pending_dice}개"
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Cog 설정"""
    await bot.add_cog(MinigamesCog(bot))
    logger.info("Minigames cog loaded")