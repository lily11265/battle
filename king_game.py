# king_game.py
import discord
from discord import app_commands
import asyncio
import random
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# 왕게임 명령어 예시
KING_COMMANDS = [
    "{0}번이 {1}번에게 애교 부리기",
    "{0}번이 {1}번 어깨 마사지 해주기",
    "{0}번과 {1}번이 서로 칭찬 한 가지씩 하기",
    "{0}번이 {1}번의 장점 3가지 말하기",
    "{0}번이 {1}번에게 사랑 고백하기 (연기)",
    "{0}번과 {1}번이 10초간 서로 눈 마주치기",
    "{0}번이 {1}번 따라하기 1분간",
    "{0}번이 동물 성대모사하고 {1}번이 맞추기",
    "{0}번이 {1}번에게 간단한 퀴즈 내기",
    "{0}번과 {1}번이 가위바위보해서 진 사람이 이긴 사람 칭찬하기",
    "{0}번이 1분간 {1}번의 매니저 되기",
    "{0}번이 {1}번을 공주님/왕자님이라 부르며 대하기",
    "{0}번이 {1}번에게 재능 하나 보여주기",
    "{0}번과 {1}번이 2인 1조로 간단한 춤추기",
    "{0}번이 {1}번의 프로필 사진 칭찬하기"
]

@dataclass
class Player:
    """왕게임 플레이어"""
    user: discord.Member
    number: int  # 0은 왕
    is_king: bool = False

class KingGame:
    def __init__(self):
        self.active_games = {}  # channel_id: game_data
        self.MIN_PLAYERS = 3
        self.MAX_PLAYERS = 20
    
    async def start_game(self, interaction: discord.Interaction, players: List[discord.Member]):
        """왕게임 시작"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 왕게임이 있습니다!",
                ephemeral=True
            )
            return
        
        if not (self.MIN_PLAYERS <= len(players) <= self.MAX_PLAYERS):
            await interaction.response.send_message(
                f"플레이어 수는 {self.MIN_PLAYERS}~{self.MAX_PLAYERS}명이어야 합니다!",
                ephemeral=True
            )
            return
        
        # 게임 데이터 초기화
        game_data = {
            "channel": interaction.channel,
            "players": players,
            "round": 0,
            "message": None,
            "host": interaction.user.id
        }
        
        self.active_games[channel_id] = game_data
        
        # 시작 메시지
        embed = discord.Embed(
            title="👑 왕게임 시작!",
            description=f"참가자: {len(players)}명\n"
                       f"호스트: {interaction.user.mention}\n\n"
                       f"잠시 후 첫 라운드가 시작됩니다!",
            color=discord.Color.gold()
        )
        
        await interaction.response.send_message(embed=embed)
        
        # 3초 후 첫 라운드 시작
        await asyncio.sleep(3)
        await self.new_round(channel_id)
    
    async def new_round(self, channel_id: int):
        """새 라운드 시작"""
        if channel_id not in self.active_games:
            return
        
        game_data = self.active_games[channel_id]
        game_data["round"] += 1
        
        # 번호 섞기 (1번부터 시작, 0은 왕)
        numbers = list(range(len(game_data["players"])))
        random.shuffle(numbers)
        
        # 플레이어 데이터 생성
        player_data = {}
        king = None
        
        for i, player in enumerate(game_data["players"]):
            number = numbers[i]
            is_king = (number == 0)
            
            player_obj = Player(
                user=player,
                number=i + 1 if not is_king else 0,  # 왕은 0, 나머지는 1번부터
                is_king=is_king
            )
            
            player_data[player.id] = player_obj
            
            if is_king:
                king = player_obj
        
        game_data["player_data"] = player_data
        game_data["king"] = king
        
        # 번호 재배정 (왕을 제외한 나머지)
        non_king_players = [p for p in player_data.values() if not p.is_king]
        for i, player in enumerate(non_king_players):
            player.number = i + 1
        
        # DM으로 번호 전송
        for player in player_data.values():
            try:
                if player.is_king:
                    dm_embed = discord.Embed(
                        title="👑 당신은 왕입니다!",
                        description="번호로 명령을 내려주세요.\n"
                                   f"(1~{len(non_king_players)}번 중에서 선택)",
                        color=discord.Color.gold()
                    )
                else:
                    dm_embed = discord.Embed(
                        title=f"🎲 당신의 번호: {player.number}번",
                        description="왕의 명령을 기다려주세요!",
                        color=discord.Color.blue()
                    )
                
                await player.user.send(embed=dm_embed)
            except:
                logger.warning(f"Failed to send DM to {player.user.name}")
        
        # 채널에 라운드 시작 메시지
        round_embed = discord.Embed(
            title=f"👑 라운드 {game_data['round']}",
            description=f"**{king.user.mention}**님이 왕이 되었습니다!\n\n"
                       f"모두 DM으로 번호를 확인하세요!\n"
                       f"왕은 명령을 선택해주세요.",
            color=discord.Color.gold()
        )
        
        # 왕 전용 명령 선택 뷰
        view = KingCommandView(self, channel_id, king.user.id, len(non_king_players))
        
        msg = await game_data["channel"].send(embed=round_embed, view=view)
        game_data["message"] = msg
    
    async def execute_command(self, channel_id: int, command_template: str, num1: int, num2: int):
        """명령 실행"""
        if channel_id not in self.active_games:
            return
        
        game_data = self.active_games[channel_id]
        player_data = game_data["player_data"]
        
        # 번호에 해당하는 플레이어 찾기
        player1 = None
        player2 = None
        
        for player in player_data.values():
            if player.number == num1:
                player1 = player
            elif player.number == num2:
                player2 = player
        
        if not player1 or not player2:
            return
        
        # 명령 생성
        command = command_template.format(num1, num2)
        
        # 결과 임베드
        result_embed = discord.Embed(
            title="👑 왕의 명령",
            description=f"**{command}**\n\n"
                    f"{num1}번: {player1.user.mention}\n"
                    f"{num2}번: {player2.user.mention}",
            color=discord.Color.gold()
        )
        
        result_embed.add_field(
            name="📝 명령을 수행해주세요!",
            value="명령 수행 후:\n"
                "• 다음 라운드: `/게임 왕게임 action:다음라운드`\n"
                "• 게임 종료: `/게임 왕게임 action:게임종료`",
            inline=False
        )
        
        # 기존 메시지 편집 (버튼 뷰 없이)
        await game_data["message"].edit(embed=result_embed, view=None)

    async def end_game(self, channel_id: int):
        """게임 종료"""
        if channel_id not in self.active_games:
            return
        
        game_data = self.active_games[channel_id]
        
        # 종료 메시지
        end_embed = discord.Embed(
            title="👑 왕게임 종료!",
            description=f"총 {game_data['round']}라운드를 진행했습니다.\n"
                       f"다음에 또 만나요!",
            color=discord.Color.gold()
        )
        
        await game_data["channel"].send(embed=end_embed)
        
        # 게임 데이터 정리
        del self.active_games[channel_id]

    async def start_game_from_channel(self, channel: discord.TextChannel, players: List[discord.Member], host: discord.Member):
        """채널에서 직접 게임 시작 (interaction 없이)"""
        channel_id = channel.id
        
        if channel_id in self.active_games:
            await channel.send("이미 진행 중인 왕게임이 있습니다!")
            return
        
        # 게임 데이터 초기화
        game_data = {
            "channel": channel,
            "players": players,
            "round": 0,
            "message": None,
            "host": host.id
        }
        
        self.active_games[channel_id] = game_data
        
        # 시작 메시지
        embed = discord.Embed(
            title="👑 왕게임 시작!",
            description=f"참가자: {len(players)}명\n"
                    f"호스트: {host.mention}\n\n"
                    f"잠시 후 첫 라운드가 시작됩니다!",
            color=discord.Color.gold()
        )
        
        await channel.send(embed=embed)
        
        # 3초 후 첫 라운드 시작
        await asyncio.sleep(3)
        await self.new_round(channel_id)

# UI 컴포넌트
class KingJoinView(discord.ui.View):
    def __init__(self, game: KingGame, host: discord.Member):
        super().__init__(timeout=None)
        self.game = game
        self.host = host
        self.participants = [host]  # 호스트 자동 참가
    
    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, emoji="👑")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants:
            await interaction.response.send_message(
                "이미 참가하셨습니다!",
                ephemeral=True
            )
            return
        
        if len(self.participants) >= self.game.MAX_PLAYERS:
            await interaction.response.send_message(
                f"최대 인원({self.game.MAX_PLAYERS}명)에 도달했습니다!",
                ephemeral=True
            )
            return
        
        self.participants.append(interaction.user)
        
        # 임베드 업데이트
        embed = interaction.message.embeds[0]
        embed.set_field_at(
            0,
            name="현재 참가자",
            value=f"**{len(self.participants)}명** / {self.game.MAX_PLAYERS}명",
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed)
        await interaction.followup.send(
            f"{interaction.user.mention}님이 참가했습니다!",
            ephemeral=False
        )
    
    @discord.ui.button(label="게임 시작", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message(
                "게임 호스트만 시작할 수 있습니다!",
                ephemeral=True
            )
            return
        
        if len(self.participants) < self.game.MIN_PLAYERS:
            await interaction.response.send_message(
                f"최소 {self.game.MIN_PLAYERS}명이 필요합니다! (현재 {len(self.participants)}명)",
                ephemeral=True
            )
            return
        
        # 버튼 비활성화
        for item in self.children:
            item.disabled = True
        
        # 메시지 업데이트
        await interaction.response.edit_message(view=self)
        
        # 게임 시작 - interaction 대신 채널 직접 전달
        asyncio.create_task(self.game.start_game_from_channel(interaction.channel, self.participants, interaction.user))
        self.stop()

class KingCommandView(discord.ui.View):
    def __init__(self, game: KingGame, channel_id: int, king_id: int, max_number: int):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.king_id = king_id
        self.max_number = max_number
        
        # 랜덤 명령 버튼
        random_btn = discord.ui.Button(
            label="랜덤 명령",
            style=discord.ButtonStyle.primary,
            emoji="🎲"
        )
        random_btn.callback = self.random_command
        self.add_item(random_btn)
        
        # 커스텀 명령 버튼
        custom_btn = discord.ui.Button(
            label="직접 입력",
            style=discord.ButtonStyle.secondary,
            emoji="✏️"
        )
        custom_btn.callback = self.custom_command
        self.add_item(custom_btn)
    
    async def random_command(self, interaction: discord.Interaction):
        if interaction.user.id != self.king_id:
            await interaction.response.send_message(
                "왕만 명령을 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        # 랜덤 명령 선택
        command = random.choice(KING_COMMANDS)
        
        # 랜덤 번호 선택
        numbers = list(range(1, self.max_number + 1))
        random.shuffle(numbers)
        num1, num2 = numbers[0], numbers[1] if len(numbers) > 1 else numbers[0]
        
        # 명령 실행
        await self.game.execute_command(self.channel_id, command, num1, num2)
        
        await interaction.response.send_message(
            "명령을 선택했습니다!",
            ephemeral=True
        )
        self.stop()
    
    async def custom_command(self, interaction: discord.Interaction):
        if interaction.user.id != self.king_id:
            await interaction.response.send_message(
                "왕만 명령을 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        # 모달 표시
        modal = KingCommandModal(self.game, self.channel_id, self.max_number)
        await interaction.response.send_modal(modal)
        self.stop()

class KingCommandModal(discord.ui.Modal, title="왕의 명령 입력"):
    def __init__(self, game: KingGame, channel_id: int, max_number: int):
        super().__init__()
        self.game = game
        self.channel_id = channel_id
        self.max_number = max_number
        
        # 첫 번째 번호
        self.num1 = discord.ui.TextInput(
            label="첫 번째 번호",
            placeholder=f"1~{max_number} 중 입력",
            required=True,
            max_length=2
        )
        self.add_item(self.num1)
        
        # 두 번째 번호
        self.num2 = discord.ui.TextInput(
            label="두 번째 번호",
            placeholder=f"1~{max_number} 중 입력",
            required=True,
            max_length=2
        )
        self.add_item(self.num2)
        
        # 명령 내용
        self.command = discord.ui.TextInput(
            label="명령 내용",
            placeholder="예: 서로 하이파이브하기",
            required=True,
            max_length=100,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.command)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            num1 = int(self.num1.value)
            num2 = int(self.num2.value)
            
            # 번호 검증
            if not (1 <= num1 <= self.max_number and 1 <= num2 <= self.max_number):
                await interaction.response.send_message(
                    f"번호는 1~{self.max_number} 사이여야 합니다!",
                    ephemeral=True
                )
                return
            
            # 명령 템플릿 생성
            command_template = f"{num1}번과 {num2}번이 " + self.command.value
            
            # 명령 실행
            await self.game.execute_command(self.channel_id, command_template, num1, num2)
            
            await interaction.response.send_message(
                "명령을 설정했습니다!",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "번호는 숫자로 입력해주세요!",
                ephemeral=True
            )

# 전역 게임 인스턴스
king_game = KingGame()

def get_king_game():
    return king_game