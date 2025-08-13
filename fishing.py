# fishing_horror.py - 저주받은 뜰채 (공포 버전) - 수정된 버전
import re
import discord
from discord import app_commands
import asyncio
import random
import logging
import time
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import gspread
from google.oauth2.service_account import Credentials
from debug_config import debug_log, debug_config

logger = logging.getLogger(__name__)

# Google Sheets 설정
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
ITEM_SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1p4x6mpUqiCPK7gB6Tk_Ju1PWkRn-DoqoPTeEfgoOl4E/edit?usp=sharing"

# 플레이어 이름 목록
PLAYER_NAMES = [
    "아카시 하지메", "펀처", "유진석", "휘슬", "배달기사", "페이",
    "로메즈 아가레스", "레이나 하트베인", "비비", "오카미 나오하",
    "카라트에크", "토트", "처용", "멀 플리시", "코발트윈드", "옥타",
    "베레니케", "안드라 블랙", "봉고 3호", "몰", "베니", "백야",
    "루치페르", "벨사이르 드라켄리트", "불스", "퓨어 메탈", "노 단투",
    "라록", "아카이브", "베터", "메르쿠리", "마크-112", "스푸트니크 2세",
    "이터니티", "커피머신"
]

# 이동 가능한 카테고리 ID들
TELEPORT_CATEGORIES = [
    1383079921164882002,
    1383101637920423977,
    1383079881130381372,
    1391014017606225950,
    1383105005950865418
]

class CreatureType(Enum):
    """잡을 수 있는 것들"""
    # 일반 물고기 (기존) - display_duration 증가
    COMMON = ("붕어", "🐠", 10, 4.0, "normal", 0)      # 2.5 -> 4.0
    RANCHU = ("란추", "🐡", 20, 3.5, "normal", 0)      # 2.0 -> 3.5
    RYUKIN = ("류킨", "🦈", 30, 3.0, "normal", 0)      # 1.8 -> 3.0
    ORANDA = ("오란다", "🐟", 40, 2.8, "normal", 0)    # 1.5 -> 2.8
    DEMEKIN = ("데메킨", "✨", 50, 2.5, "normal", 0)   # 1.2 -> 2.5
    GOLDEN = ("황금붕어", "👑", 100, 2.0, "normal", 0) # 1.0 -> 2.0
    
    # 위험한 것들 - display_duration 증가
    HAND = ("익사자의 손", "🤲", -20, 3.0, "danger", 20)  # 1.5 -> 3.0
    KNIFE = ("녹슨 칼날", "🔪", -30, 2.5, "danger", 30)   # 1.0 -> 2.5
    GHOST = ("유령", "👻", -10, 3.5, "danger", 15)        # 2.0 -> 3.5
    SKULL = ("해골붕어", "💀", 5, 3.0, "danger", 10)      # 1.8 -> 3.0
    EYE = ("눈동자", "👁️", 0, 2.8, "danger", 25)         # 1.2 -> 2.8
    MASK = ("부서진 가면", "🎭", -50, 2.0, "danger", 40)  # 0.8 -> 2.0

@dataclass
class ActiveCreature:
    """활성화된 생물"""
    position: int
    type: CreatureType
    appear_time: float
    display_duration: float
    caught: bool = False

@dataclass
class Player:
    """플레이어 정보"""
    user: discord.Member
    display_name: str
    real_name: str
    dice_modifier: int
    score: int = 0
    creatures_caught: List[CreatureType] = None
    poi_durability: int = 100
    poi_used: int = 0
    sanity: int = 100  # 정신력 추가
    total_catches: int = 0
    danger_catches: int = 0  # 위험한 것 잡은 횟수
    last_result: str = ""
    
    def __post_init__(self):
        if self.creatures_caught is None:
            self.creatures_caught = []

class HorrorFishingGame:
    def __init__(self):
        self.active_games = {}
        self.grid_size = 5
        self.game_duration = 90  # 60초에서 90초로 증가
        self.max_poi = 3
        self.base_dice = 100
        self.horror_messages = [
            "물 속에서 차가운 손이 당신을 향해 뻗어옵니다.",
            "무언가가 당신을 지켜보고 있습니다.",
            "속삭임이 들립니다. 도망쳐.",
            "물이 점점 붉어지고 있습니다.",
            "당신의 그림자가 이상하게 움직입니다.",
            "뒤를 돌아보지 마세요.",
            "그것이 다가오고 있습니다.",
            "포이가 무언가에 잡아당겨집니다.",
            "물 속에서 비명소리가 들립니다.",
            "당신의 이름을 부르는 소리가 들립니다",
            "거울에 비친 당신의 얼굴이 웃고 있습니다.",
            "발밑에서 무언가가 기어오릅니다.",
            "숨을 쉬어지지 않습니다.",
            "그들이 당신을 노리고 있습니다.",
            "이미 늦었습니다.",
        ]
        self.chat_reactions = ["🇭", "🇪", "⏸", "🅾"]  # H-E-L-L-O
        self.last_chat_reaction = {}
        self.dice_waiting_players = {}  # {channel_id: {player_id: {"start_time": time, "message": message}}}
        self.message_delete_delay = 0.5  # 메시지 삭제 간 지연 시간
        self.max_event_messages = 5  # 최대 이벤트 메시지 수
        self.delete_tasks = {} 
        # 게임 종료 중복 방지
        self.ending_games = set()  # 종료 처리 중인 게임 추적        
        # 버튼 업데이트 관리
        self.last_button_update = {}  # {channel_id: timestamp}
        self.min_button_update_interval = 0.2  # 최소 업데이트 간격
        self.pending_button_updates = {}  # {channel_id: set(positions)}
        self.button_update_tasks = {}  # {channel_id: task}
        
    def extract_player_name(self, display_name: str) -> str:
        """닉네임에서 실제 플레이어 이름 추출"""
        for player_name in PLAYER_NAMES:
            if player_name in display_name:
                return player_name
        return display_name
    
    def calculate_dice_modifier(self, display_name: str) -> int:
        """닉네임에서 주사위 보정값 계산"""
        modifier = 0
        if "각성" in display_name:
            modifier += 50
        if "만취" in display_name:
            modifier -= 40
        elif "취함" in display_name:
            modifier -= 20
        return modifier
    
    def get_random_creature_type(self, sanity: int) -> CreatureType:
        """생물 종류 선택 - 정신력과 무관하게 독립적으로 선택"""
        # 기본 확률 설정
        # 물고기 70%, 위험한 것 30%
        base_fish_chance = 0.7
        base_danger_chance = 0.3
        
        # 정신력이 낮을 때 약간의 보정만 추가 (완전히 바뀌지 않도록)
        # 정신력 0%일 때도 물고기가 50%는 나오도록
        sanity_modifier = (100 - sanity) / 200  # 최대 0.5 보정
        
        # 최종 확률 계산
        danger_chance = min(0.5, base_danger_chance + sanity_modifier * 0.2)  # 최대 50%
        
        debug_log("FISHING", f"Creature spawn - Sanity: {sanity}%, Danger chance: {danger_chance:.2%}")
        
        if random.random() < danger_chance:
            # 위험한 것들 중에서 랜덤 선택
            dangerous_creatures = [
                (CreatureType.HAND, 0.20),     # 20%
                (CreatureType.KNIFE, 0.15),    # 15%
                (CreatureType.GHOST, 0.25),    # 25%
                (CreatureType.SKULL, 0.20),    # 20%
                (CreatureType.EYE, 0.10),      # 10%
                (CreatureType.MASK, 0.10)      # 10%
            ]
            
            # 가중치 기반 선택
            creatures, weights = zip(*dangerous_creatures)
            selected = random.choices(creatures, weights=weights)[0]
            debug_log("FISHING", f"Spawned dangerous creature: {selected.value[0]}")
            return selected
        else:
            # 일반 물고기 - 기존 확률 유지
            rand = random.random()
            if rand < 0.4:
                selected = CreatureType.COMMON
            elif rand < 0.7:
                selected = CreatureType.RANCHU
            elif rand < 0.85:
                selected = CreatureType.RYUKIN
            elif rand < 0.95:
                selected = CreatureType.ORANDA
            elif rand < 0.99:
                selected = CreatureType.DEMEKIN
            else:
                selected = CreatureType.GOLDEN
            
            debug_log("FISHING", f"Spawned fish: {selected.value[0]}")
            return selected

    def get_embed_color(self, elapsed_time: int) -> discord.Color:
        """시간에 따른 색상 변화"""
        # 0초: 진한 빨간색 -> 60초: 검은색
        if elapsed_time >= 60:
            return discord.Color.from_rgb(0, 0, 0)
        
        # 선형 보간
        ratio = elapsed_time / 60
        red = int(139 * (1 - ratio))  # 139 -> 0
        return discord.Color.from_rgb(red, 0, 0)
    
    def get_sanity_bar(self, sanity: int) -> str:
        """정신력 바"""
        if sanity >= 75:
            return "████████ "
        elif sanity >= 50:
            return "██████░░ "
        elif sanity >= 25:
            return "████░░░░ "
        elif sanity > 0:
            return "██░░░░░░ "
        else:
            return "░░░░░░░░ "
    
    def get_disabled_buttons_count(self, avg_sanity: float) -> int:
        """평균 정신력에 따른 비활성화할 버튼 수"""
        if avg_sanity >= 80:
            return 0
        elif avg_sanity >= 60:
            return 3
        elif avg_sanity >= 40:
            return 6
        elif avg_sanity >= 20:
            return 10
        else:
            return 15
    
    async def process_chat_message(self, message: discord.Message):
        """채팅 메시지 처리 및 반응"""
        channel_id = message.channel.id
        
        # 게임이 진행 중인 채널인지 확인
        if channel_id not in self.active_games:
            return
        
        game_data = self.active_games[channel_id]
        if game_data["phase"] != "playing":
            return
        
        # 봇 메시지나 게임 참여자가 아닌 경우 무시
        if message.author.bot or message.author.id not in game_data["players"]:
            return
        
        # 마지막 반응으로부터 15초 경과 확인
        current_time = time.time()
        if channel_id in self.last_chat_reaction:
            if current_time - self.last_chat_reaction[channel_id] < 15:
                return
        
        # 50% 확률로 반응
        if random.random() > 0.5:
            return
        
        self.last_chat_reaction[channel_id] = current_time
        
        debug_log("FISHING", f"Adding HELLO reactions to message from {message.author.display_name}")
        
        # H-E-L-L-O 순서로 반응 추가
        for i, reaction in enumerate(self.chat_reactions):
            try:
                await message.add_reaction(reaction)
                await asyncio.sleep(0.3)  # 각 이모지 사이 간격
                debug_log("FISHING", f"Added reaction {i+1}/5: {reaction}")
            except discord.HTTPException as e:
                debug_log("FISHING", f"Failed to add reaction {reaction}: {e}")
                pass
            except Exception as e:
                debug_log("FISHING", f"Unexpected error adding reaction: {e}")
                pass
        
        # 랜덤 이벤트 발생 (기존과 동일하지만 메시지 대신 임베드 업데이트)
        await self.trigger_random_event(channel_id, message)

    # trigger_random_event 메서드도 수정
    async def trigger_random_event(self, channel_id: int, message: discord.Message):
        """랜덤 이벤트 발생"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        event_type = random.choice(["sanity_drain", "poi_damage", "spawn_danger", "blackout"])
        
        debug_log("FISHING", f"Chat triggered random event: {event_type}")
        
        if event_type == "sanity_drain":
            # 모든 플레이어 정신력 감소
            for player in game_data["players"].values():
                player.sanity = max(0, player.sanity - 10)
            game_data["current_event"] = "그것이 당신들을 주시합니다. 모든 플레이어 정신력 -10"
            
        elif event_type == "poi_damage":
            # 랜덤 플레이어 포이 손상
            player = random.choice(list(game_data["players"].values()))
            player.poi_durability = max(0, player.poi_durability - 30)
            game_data["current_event"] = f"무언가가 {player.real_name}의 포이를 갉아먹었습니다."
            
        elif event_type == "spawn_danger":
            # 위험한 것들 대량 스폰
            for _ in range(5):
                available_positions = [i for i in range(25) if i not in game_data["active_creatures"]]
                if available_positions:
                    position = random.choice(available_positions)
                    creature = ActiveCreature(
                        position=position,
                        type=random.choice([CreatureType.HAND, CreatureType.GHOST, CreatureType.EYE]),
                        appear_time=time.time(),
                        display_duration=2.0
                    )
                    game_data["active_creatures"][position] = creature
            game_data["current_event"] = "물이 요동칩니다. 무언가가 떠오릅니다."
            
        elif event_type == "blackout":
            # 모든 버튼 일시적으로 ❓로 변경
            game_data["blackout"] = True
            game_data["current_event"] = "어둠이 내려앉습니다."
            await asyncio.sleep(3)
            game_data["blackout"] = False
        
        # 이벤트 히스토리에 추가
        game_data["event_history"].append(game_data["current_event"][:20] + "...")
        if len(game_data["event_history"]) > 5:
            game_data["event_history"] = game_data["event_history"][-5:]

    async def start_fishing(self, interaction: discord.Interaction):
        """금붕어 잡기 시작"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        game_data = {
            "players": {},
            "active_creatures": {},
            "phase": "waiting",
            "host": interaction.user,
            "start_time": None,
            "message": None,
            "view": None,
            "is_multiplayer": False,
            "blackout": False,
            "disabled_buttons": set(),
            "event_messages": [],  # 이벤트 메시지 리스트
            "current_event": "",  # 현재 이벤트 메시지
            "event_history": []  # 이벤트 히스토리 (최근 3개만 유지)
        }
        self.active_games[channel_id] = game_data
        
        embed = discord.Embed(
            title="🎏 금붕어 잡기",
            description=f"{interaction.user.display_name}님이 금붕어 잡기를 시작합니다!\n"
                       f"혼자 하시려면 '시작하기'를,\n"
                       f"여러명이 하시려면 '멀티플레이'를 눌러주세요.\n\n"
                       f"**게임 방법**:\n"
                       f"• 물 위로 올라온 금붕어를 빠르게 클릭하세요!\n"
                       f"• 빨리 클릭할수록 포이가 덜 찢어집니다\n"
                       f"• 주사위를 굴려 성공 여부가 결정됩니다",
            color=discord.Color.blue()
        )
        
        view = GameModeSelectView(self, channel_id, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)
        game_data["message"] = await interaction.original_response()
    
    async def start_fishing_direct(self, channel: discord.TextChannel, user: discord.Member):
        """직접 게임 시작 (interaction 없이)"""
        channel_id = channel.id
        
        if channel_id in self.active_games:
            await channel.send(f"{user.mention} 이미 진행 중인 게임이 있습니다!")
            return
        
        game_data = {
            "players": {},
            "active_creatures": {},
            "phase": "waiting",
            "host": user,
            "start_time": None,
            "message": None,
            "view": None,
            "is_multiplayer": False,
            "blackout": False,
            "disabled_buttons": set(),
            "event_messages": []
        }
        
        self.active_games[channel_id] = game_data
        
        embed = discord.Embed(
            title="🎏 금붕어 잡기",
            description=f"{user.display_name}님이 금붕어 잡기를 시작합니다!\n"
                       f"혼자 하시려면 '시작하기'를,\n"
                       f"여러명이 하시려면 '멀티플레이'를 눌러주세요.",
            color=discord.Color.blue()
        )
        
        view = GameModeSelectView(self, channel_id, user)
        message = await channel.send(embed=embed, view=view)
        game_data["message"] = message
    
    async def start_single_player(self, channel_id: int, player: discord.Member):
        """싱글플레이어 게임 시작"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        real_name = self.extract_player_name(player.display_name)
        dice_modifier = self.calculate_dice_modifier(player.display_name)
        
        game_data["players"][player.id] = Player(
            user=player,
            display_name=player.display_name,
            real_name=real_name,
            dice_modifier=dice_modifier
        )
        game_data["phase"] = "playing"
        game_data["start_time"] = time.time()
        
        await self.run_game(channel_id)
    
    async def setup_multiplayer(self, channel_id: int):
        """멀티플레이어 설정"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        game_data["is_multiplayer"] = True
        
        embed = discord.Embed(
            title="🎏 금붕어 잡기 - 멀티플레이어",
            description="참가하려면 아래 버튼을 누르세요!\n"
                       f"최대 4명까지 참가 가능합니다.",
            color=discord.Color.blue()
        )
        
        view = MultiplayerLobbyView(self, channel_id)
        await game_data["message"].edit(embed=embed, view=view)
    
    async def add_player(self, channel_id: int, user: discord.Member) -> bool:
        """플레이어 추가"""
        game_data = self.active_games.get(channel_id)
        if not game_data or game_data["phase"] != "waiting":
            return False
        
        if user.id in game_data["players"]:
            return False
        
        if len(game_data["players"]) >= 4:
            return False
        
        real_name = self.extract_player_name(user.display_name)
        dice_modifier = self.calculate_dice_modifier(user.display_name)
        
        game_data["players"][user.id] = Player(
            user=user,
            display_name=user.display_name,
            real_name=real_name,
            dice_modifier=dice_modifier
        )
        
        return True
    
    async def start_multiplayer_game(self, channel_id: int):
        """멀티플레이어 게임 시작"""
        game_data = self.active_games.get(channel_id)
        if not game_data or len(game_data["players"]) < 2:
            return
        
        game_data["phase"] = "playing"
        game_data["start_time"] = time.time()
        
        await self.run_game(channel_id)

    async def _check_all_poi_broken(self, channel_id: int):
        """모든 플레이어의 포이가 다 찢어졌는지 확인"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return False
        
        all_broken = True
        for player in game_data["players"].values():
            if player.poi_used < self.max_poi:
                all_broken = False
                break
        
        if all_broken:
            debug_log("FISHING", "All poi broken - ending game early")
            # 중복 호출 방지
            if channel_id in self.active_games:
                await self.end_game(channel_id)
            return True
        return False

    async def _auto_sanity_drain(self, channel_id: int):
        """자동으로 정신력 감소 - 속도 완화"""
        drain_count = 0
        
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data["phase"] != "playing":
                break
            
            # 8초마다 정신력 1-3 감소 (기존 5초마다 2-4)
            await asyncio.sleep(8)
            
            for player in game_data["players"].values():
                # 정신력이 이미 낮으면 감소 속도 더 완화
                if player.sanity < 30:
                    drain_amount = random.randint(1, 2)
                else:
                    drain_amount = random.randint(1, 3)
                
                player.sanity = max(0, player.sanity - drain_amount)
                
                # 정신력 메시지
                if player.sanity == 50:
                    player.last_result = "⚠️ 머리가 아파옵니다."
                elif player.sanity == 25:
                    player.last_result = "⚠️ 환각이 보이는 것 같습니다."
                elif player.sanity == 10:
                    player.last_result = "⚠️ 저기...누군가 있습니다."
                elif player.sanity == 0:
                    player.last_result = "⚠️ ..."
            
            drain_count += 1
            if debug_config.debug_enabled and drain_count % 5 == 0:
                avg_sanity = sum(p.sanity for p in game_data["players"].values()) / len(game_data["players"])
                debug_log("FISHING", f"Sanity drain #{drain_count}, Average sanity: {avg_sanity:.1f}%")

    async def _progressive_button_disable(self, channel_id: int):
        """게임 진행에 따라 버튼을 점진적으로 비활성화"""
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data["phase"] != "playing":
                break
            
            # 20-25초마다 1개의 버튼 영구 비활성화
            await asyncio.sleep(random.uniform(20, 25))
            
            # 아직 활성화된 버튼 중에서 선택
            all_positions = set(range(25))
            already_disabled = game_data.get("permanent_disabled_buttons", set())
            available = all_positions - already_disabled
            
            if len(available) > 5:  # 최소 5개는 남겨둠
                # 1개 버튼만 비활성화
                to_disable = random.sample(list(available), 1)
                
                for position in to_disable:
                    game_data["permanent_disabled_buttons"].add(position)
                    # 즉시 버튼 업데이트
                    await self._update_button(channel_id, position, False)
                
                # 이벤트 메시지로 변경
                game_data["current_event"] = "어둠이 하나의 공간을 삼켰습니다."
                game_data["event_history"].append("어둠이 공간을 삼킴")
                if len(game_data["event_history"]) > 5:
                    game_data["event_history"] = game_data["event_history"][-5:]
                
                debug_log("FISHING", f"Permanently disabled button at position {position}")

    async def _teleport_player(self, player: Player):
        """플레이어를 랜덤 채널로 순간이동"""
        try:
            guild = player.user.guild
            if not guild:
                debug_log("FISHING", "Failed to get guild for teleportation")
                return
            
            # 현재 채널 ID 저장
            current_channel_id = None
            for channel_id, game_data in self.active_games.items():
                if player.user.id in game_data["players"]:
                    current_channel_id = channel_id
                    break
            
            # 랜덤 카테고리 선택
            category_id = random.choice(TELEPORT_CATEGORIES)
            category = guild.get_channel(category_id)
            
            if not category or not isinstance(category, discord.CategoryChannel):
                debug_log("FISHING", f"Failed to get category {category_id}")
                return
            
            # 카테고리 내 텍스트 채널 목록
            text_channels = [ch for ch in category.channels if isinstance(ch, discord.TextChannel)]
            
            if not text_channels:
                debug_log("FISHING", f"No text channels in category {category_id}")
                return
            
            # 랜덤 채널 선택
            target_channel = random.choice(text_channels)
            
            # 메시지 전송
            await target_channel.send(
                f"{player.user.mention} **{player.real_name}이(가) 갑자기 하늘에서 떨어집니다!**"
            )
            
            debug_log("FISHING", f"Teleported {player.real_name} to {target_channel.name}")
            
            # 게임에서 플레이어 제거 및 게임 종료 체크
            if current_channel_id and current_channel_id in self.active_games:
                game_data = self.active_games[current_channel_id]
                
                # 플레이어를 게임에서 제거
                if player.user.id in game_data["players"]:
                    del game_data["players"][player.user.id]
                    debug_log("FISHING", f"Removed {player.real_name} from game")
                    
                    # 남은 플레이어가 없으면 게임 종료
                    if len(game_data["players"]) == 0:
                        debug_log("FISHING", "No players left, ending game")
                        await self.end_game(current_channel_id)
                    else:
                        # 게임 계속 진행 메시지
                        try:
                            await game_data["message"].channel.send(
                                f"⚠️ **{player.real_name}님이 게임에서 제외되었습니다.**\n"
                                f"남은 플레이어: {len(game_data['players'])}명"
                            )
                        except:
                            pass
            
        except Exception as e:
            logger.error(f"Teleportation failed: {e}")
            debug_log("FISHING", f"Teleportation error: {e}")

    # fishing.py의 _handle_dragged_event 메서드에 디버그 추가
    async def _handle_dragged_event(self, channel_id: int, player: Player):
        """물속으로 끌려들어가는 이벤트 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        debug_log("FISHING", f"Drag event started for {player.real_name}")
        debug_log("FISHING", f"Player details - ID: {player.user.id}, Display: '{player.user.display_name}', Real: '{player.real_name}'")
        
        # 대기 중인 플레이어 등록
        if channel_id not in self.dice_waiting_players:
            self.dice_waiting_players[channel_id] = {}
        
        self.dice_waiting_players[channel_id][player.user.id] = {
            "start_time": time.time(),
            "player": player
        }
        
        debug_log("FISHING", f"Registered {player.real_name} in dice waiting list with ID {player.user.id}")
        
        # 경고 메시지
        msg = await game_data["message"].channel.send(
            f"🤲 ***{player.real_name}님! 물속에서 차가운 손이 당신을 끌어당기고 있습니다!***\n"
            f"**40초 내에 `/주사위` 명령어를 입력하세요! (50 이상 필요)**\n"
            f"⚠️ 실패 시 다른 채널로 순간이동됩니다!"
        )
        
        # 40초 대기
        await asyncio.sleep(40)
        
        # 시간 초과 확인
        if (channel_id in self.dice_waiting_players and 
            player.user.id in self.dice_waiting_players[channel_id]):
            
            debug_log("FISHING", f"{player.real_name} failed to roll dice in time")
            
            # 실패 메시지
            try:
                await game_data["message"].channel.send(
                    f"💀 **{player.real_name}님이 주사위를 굴리지 못했습니다!**"
                )
            except:
                pass
            
            # 실패 처리 - 순간이동
            await self._teleport_player(player)
            
            # 대기 목록에서 제거
            del self.dice_waiting_players[channel_id][player.user.id]
            if not self.dice_waiting_players[channel_id]:
                del self.dice_waiting_players[channel_id]
        else:
            debug_log("FISHING", f"{player.real_name} already processed dice roll")

    async def process_dice_message(self, message: discord.Message):
        """주사위 메시지 처리"""
        channel_id = message.channel.id
        
        debug_log("FISHING", f"Processing dice message in channel {channel_id}")
        
        if channel_id not in self.dice_waiting_players:
            debug_log("FISHING", f"No waiting players in channel {channel_id}")
            return
        
        content = message.content
        debug_log("FISHING", f"Dice message content: {content}")
        
        # 공백 정규화
        normalized_content = ' '.join(content.split())
        
        # 백틱으로 감싸진 닉네임을 우선적으로 찾는 패턴
        patterns = [
            r"`([^`]+)`님이.*?주사위를\s*굴\s*려.*?\*\*(\d+)\*\*.*?나왔습니다",  # 백틱 패턴 (최우선)
            r'(.+?)님이.*주사위를\s*굴려\s*\*+(\d+)\*+\s*나왔습니다',  # 기존 패턴
            r'(.+?)님이.*:game_die:.*주사위를\s*굴려\s*\*+(\d+)\*+',
            r'(.+?)님이.*굴려\s*\*+(\d+)\*+',
            r'(.+?)님이.*?(\d+)\s*나왔습니다',
        ]
        
        match = None
        for pattern in patterns:
            match = re.search(pattern, normalized_content)
            if match:
                debug_log("FISHING", f"Matched with pattern: {pattern}")
                break
        
        if not match:
            debug_log("FISHING", f"Failed to parse dice message with any pattern")
            return
        
        try:
            player_nick = match.group(1).strip()
            dice_value = int(match.group(2))
            
            debug_log("FISHING", f"Parsed: {player_nick} rolled {dice_value}")
            
            # 대기 중인 플레이어 찾기 - 더 유연한 매칭
            waiting_player = None
            player_id = None
            
            for pid, data in self.dice_waiting_players[channel_id].items():
                player_display_name = data["player"].user.display_name
                player_real_name = data["player"].real_name
                
                debug_log("FISHING", f"Checking against waiting player: display_name='{player_display_name}', real_name='{player_real_name}'")
                
                # 다양한 매칭 시도
                # 1. 정확한 매칭 (백틱에서 추출한 닉네임과 정확히 일치)
                if player_nick == player_display_name:
                    waiting_player = data
                    player_id = pid
                    debug_log("FISHING", f"Exact match found for {player_nick}")
                    break
                
                # 2. 실제 이름이 파싱된 닉네임에 포함되어 있는지 확인
                if player_real_name in player_nick:
                    waiting_player = data
                    player_id = pid
                    debug_log("FISHING", f"Real name '{player_real_name}' found in parsed nick '{player_nick}'")
                    break
                
                # 3. 파싱된 닉네임이 display_name에 포함되어 있는지 확인
                if player_nick in player_display_name:
                    waiting_player = data
                    player_id = pid
                    debug_log("FISHING", f"Parsed nick '{player_nick}' found in display_name '{player_display_name}'")
                    break
                
                # 4. 특수문자를 제거한 비교
                clean_nick = re.sub(r'[^\w가-힣\s]', '', player_nick)
                clean_display = re.sub(r'[^\w가-힣\s]', '', player_display_name)
                
                if clean_nick and (clean_nick == clean_display or player_real_name in clean_nick):
                    waiting_player = data
                    player_id = pid
                    debug_log("FISHING", f"Match found after cleaning special chars: '{clean_nick}' vs '{clean_display}'")
                    break
                
                # 5. 알려진 이름 패턴 확인
                for known_name in PLAYER_NAMES:
                    if known_name in player_nick and known_name == player_real_name:
                        waiting_player = data
                        player_id = pid
                        debug_log("FISHING", f"Known name match: {known_name}")
                        break
            
            if not waiting_player:
                debug_log("FISHING", f"No waiting player found for {player_nick}")
                # 디버그를 위해 모든 대기 중인 플레이어 출력
                debug_log("FISHING", "All waiting players:")
                for pid, data in self.dice_waiting_players[channel_id].items():
                    debug_log("FISHING", f"  - ID: {pid}, Display: '{data['player'].user.display_name}', Real: '{data['player'].real_name}'")
                return
            
            # 시간 체크
            elapsed = time.time() - waiting_player["start_time"]
            if elapsed > 40:
                debug_log("FISHING", f"Dice roll too late: {elapsed:.1f}s")
                return
            
            # 결과 처리
            player = waiting_player["player"]
            
            if dice_value >= 50:
                # 성공
                await message.channel.send(
                    f"✨ **{player.real_name}님이 손을 뿌리쳤습니다!** (주사위: {dice_value})"
                )
                player.last_result = f"🤲 물속의 손을 뿌리쳤습니다! (+10점)"
                player.score += 10
                debug_log("FISHING", f"{player.real_name} succeeded with dice {dice_value}")
            else:
                # 실패
                await message.channel.send(
                    f"💀 **{player.real_name}님이 물속으로 끌려들어갑니다!** (주사위: {dice_value})"
                )
                await self._teleport_player(player)
                debug_log("FISHING", f"{player.real_name} failed with dice {dice_value}")
            
            # 대기 목록에서 제거
            del self.dice_waiting_players[channel_id][player_id]
            if not self.dice_waiting_players[channel_id]:
                del self.dice_waiting_players[channel_id]
            
            debug_log("FISHING", f"Removed {player.real_name} from waiting list")
            
        except Exception as e:
            logger.error(f"Error processing dice message: {e}")
            debug_log("FISHING", f"Dice processing error: {e}")
            import traceback
            debug_log("FISHING", f"Traceback: {traceback.format_exc()}")

    async def run_game(self, channel_id: int):
        """게임 실행"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            debug_log("FISHING", f"No game data found for channel {channel_id}")
            return
        
        if game_data.get("game_running", False):
            debug_log("FISHING", f"Game already running for channel {channel_id}")
            return
        
        game_data["game_running"] = True
        game_data["permanent_disabled_buttons"] = set()
        
        embed = self._create_game_embed(channel_id)
        view = HorrorGameView(self, channel_id)
        game_data["view"] = view
        
        try:
            await game_data["message"].edit(embed=embed, view=view)
        except Exception as e:
            debug_log("FISHING", f"Failed to update game message: {e}")
            return
        
        # 태스크 생성
        spawn_task = asyncio.create_task(self._spawn_creatures(channel_id))
        game_data["spawn_task"] = spawn_task
        
        update_task = asyncio.create_task(self._update_game_display(channel_id))
        game_data["update_task"] = update_task
        
        event_task = asyncio.create_task(self._periodic_events(channel_id))
        game_data["event_task"] = event_task
        
        sanity_drain_task = asyncio.create_task(self._auto_sanity_drain(channel_id))
        game_data["sanity_drain_task"] = sanity_drain_task
        
        button_disable_task = asyncio.create_task(self._progressive_button_disable(channel_id))
        game_data["button_disable_task"] = button_disable_task
        
        # 버튼 업데이트 배치 처리 태스크 추가
        button_batch_task = asyncio.create_task(self._process_button_updates(channel_id))
        game_data["button_batch_task"] = button_batch_task
        self.button_update_tasks[channel_id] = button_batch_task
        
        try:
            await asyncio.sleep(self.game_duration)
            debug_log("FISHING", f"Game timer expired for channel {channel_id}")
        except asyncio.CancelledError:
            debug_log("FISHING", f"Game cancelled for channel {channel_id}")
        
        if channel_id in self.active_games:
            await self.end_game(channel_id)

    async def _process_button_updates(self, channel_id: int):
        """버튼 업데이트 배치 처리"""
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data["phase"] != "playing":
                break
            
            # 대기 중인 업데이트가 있는지 확인
            if channel_id in self.pending_button_updates and self.pending_button_updates[channel_id]:
                positions = list(self.pending_button_updates[channel_id])
                self.pending_button_updates[channel_id].clear()
                
                # View 업데이트 실행
                await self._execute_button_update(channel_id)
                
                debug_log("FISHING", f"Batch updated {len(positions)} buttons")
            
            await asyncio.sleep(0.3)  # 0.3초마다 배치 처리
    
    async def _execute_button_update(self, channel_id: int):
        """실제 버튼 업데이트 실행"""
        game_data = self.active_games.get(channel_id)
        if not game_data or "view" not in game_data or not game_data.get("message"):
            return
        
        view = game_data["view"]
        
        try:
            # Rate limit 체크
            current_time = time.time()
            last_update = self.last_button_update.get(channel_id, 0)
            
            if current_time - last_update < self.min_button_update_interval:
                await asyncio.sleep(self.min_button_update_interval - (current_time - last_update))
            
            await game_data["message"].edit(view=view)
            self.last_button_update[channel_id] = time.time()
            
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 1)
                debug_log("FISHING", f"Rate limited on button update, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                # 재시도
                try:
                    await game_data["message"].edit(view=view)
                    self.last_button_update[channel_id] = time.time()
                except:
                    pass
            else:
                debug_log("FISHING", f"Failed to update buttons: {e}")
        except Exception as e:
            debug_log("FISHING", f"Error updating buttons: {e}")
    

    async def _safe_delete_message(self, message):
        """안전한 메시지 삭제 (rate limit 방지)"""
        try:
            await asyncio.sleep(self.message_delete_delay)
            await message.delete()
            debug_log("FISHING", f"Deleted message safely")
        except discord.NotFound:
            debug_log("FISHING", "Message already deleted")
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                debug_log("FISHING", f"Rate limited, waiting {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
                try:
                    await message.delete()
                except:
                    pass
            else:
                debug_log("FISHING", f"Failed to delete message: {e}")
        except Exception as e:
            debug_log("FISHING", f"Error deleting message: {e}")
    
    async def _periodic_events(self, channel_id: int):
        """주기적 이벤트"""
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data["phase"] != "playing":
                break
            
            # 10-20초마다 이벤트
            await asyncio.sleep(random.uniform(10, 20))
            
            # 이벤트 선택
            event_weights = [
                ("whisper", 15),
                ("all_eyes", 10),
                ("mass_spawn", 15),
                ("sanity_drain", 15),
                ("poi_damage", 15),
                ("blackout", 10),
                ("blood_rain", 15),
                ("drag_into_water", 5)
            ]
            
            event = random.choices(
                [e[0] for e in event_weights],
                weights=[e[1] for e in event_weights]
            )[0]
            
            debug_log("FISHING", f"Triggered event: {event}")
            
            # 이벤트 처리 - 채팅 대신 임베드 업데이트
            if event == "whisper":
                message = random.choice(self.horror_messages)
                game_data["current_event"] = message
                game_data["event_history"].append(message[:20] + "...")  # 짧게 저장
                if len(game_data["event_history"]) > 5:
                    game_data["event_history"] = game_data["event_history"][-5:]
                
            elif event == "all_eyes":
                game_data["all_eyes"] = True
                game_data["current_event"] = "모든 것이 당신을 바라봅니다."
                
                # 모든 버튼을 눈 이모지로 즉시 업데이트
                debug_log("FISHING", "All eyes event - updating all buttons to eye emoji")
                
                # View가 있는지 확인
                if "view" in game_data and game_data["view"]:
                    view = game_data["view"]
                    
                    # 모든 버튼을 눈 이모지로 변경
                    for item in view.children:
                        if isinstance(item, HorrorButton):
                            item.style = discord.ButtonStyle.success
                            item.emoji = "👁️"
                    
                    # 즉시 메시지 업데이트
                    try:
                        await game_data["message"].edit(view=view)
                        debug_log("FISHING", "All buttons updated to eye emoji")
                    except discord.HTTPException as e:
                        debug_log("FISHING", f"Failed to update buttons to eye: {e}")
                
                # 3초 대기
                await asyncio.sleep(3)
                
                # 원래 상태로 복구
                game_data["all_eyes"] = False
                debug_log("FISHING", "All eyes event ending - restoring button states")
                
                # 모든 버튼을 원래 상태로 복구
                if "view" in game_data and game_data["view"]:
                    view = game_data["view"]
                    
                    for item in view.children:
                        if isinstance(item, HorrorButton):
                            position = item.position
                            
                            # 영구 비활성화 버튼 체크
                            if position in game_data.get("permanent_disabled_buttons", set()):
                                item.style = discord.ButtonStyle.secondary
                                item.emoji = "⚫"
                                item.disabled = True
                            elif position in game_data["active_creatures"]:
                                # 생물이 있는 경우
                                creature = game_data["active_creatures"][position]
                                item.style = discord.ButtonStyle.success
                                item.emoji = creature.type.value[1]
                            else:
                                # 빈 공간
                                item.style = discord.ButtonStyle.danger
                                item.emoji = "🩸"
                                item.disabled = False
                    
                    # 다시 메시지 업데이트
                    try:
                        await game_data["message"].edit(view=view)
                        debug_log("FISHING", "Buttons restored to original state")
                    except discord.HTTPException as e:
                        debug_log("FISHING", f"Failed to restore buttons: {e}")
                
            elif event == "sanity_drain":
                for player in game_data["players"].values():
                    player.sanity = max(0, player.sanity - 15)
                game_data["current_event"] = "정신이 무너져 내립니다. 모든 플레이어 정신력 -15"
                
            elif event == "poi_damage":
                for player in game_data["players"].values():
                    player.poi_durability = max(0, player.poi_durability - 20)
                game_data["current_event"] = "물이 일순간 산성이 됩니다. 모든 포이가 녹아내립니다."
                
            elif event == "blackout":
                game_data["blackout"] = True
                game_data["current_event"] = "세상이 어둠에 잠깁니다. 아무것도 보이지 않습니다."
                
                # 모든 버튼을 물음표로 즉시 업데이트
                debug_log("FISHING", "Blackout event - updating all buttons to question mark")
                
                if "view" in game_data and game_data["view"]:
                    view = game_data["view"]
                    
                    # 모든 버튼을 물음표로 변경
                    for item in view.children:
                        if isinstance(item, HorrorButton):
                            item.style = discord.ButtonStyle.success
                            item.emoji = "❓"
                    
                    # 즉시 메시지 업데이트
                    try:
                        await game_data["message"].edit(view=view)
                        debug_log("FISHING", "All buttons updated to question mark")
                    except discord.HTTPException as e:
                        debug_log("FISHING", f"Failed to update buttons to question mark: {e}")
                
                # 4초 대기
                await asyncio.sleep(4)
                
                # 원래 상태로 복구
                game_data["blackout"] = False
                debug_log("FISHING", "Blackout event ending - restoring button states")
                
                # 버튼 복구 로직 (all_eyes와 동일)
                if "view" in game_data and game_data["view"]:
                    view = game_data["view"]
                    
                    for item in view.children:
                        if isinstance(item, HorrorButton):
                            position = item.position
                            
                            # 영구 비활성화 버튼 체크
                            if position in game_data.get("permanent_disabled_buttons", set()):
                                item.style = discord.ButtonStyle.secondary
                                item.emoji = "⚫"
                                item.disabled = True
                            elif position in game_data["active_creatures"]:
                                # 생물이 있는 경우
                                creature = game_data["active_creatures"][position]
                                item.style = discord.ButtonStyle.success
                                item.emoji = creature.type.value[1]
                            else:
                                # 빈 공간
                                item.style = discord.ButtonStyle.danger
                                item.emoji = "🩸"
                                item.disabled = False
                    
                    # 다시 메시지 업데이트
                    try:
                        await game_data["message"].edit(view=view)
                        debug_log("FISHING", "Buttons restored from blackout")
                    except discord.HTTPException as e:
                        debug_log("FISHING", f"Failed to restore buttons from blackout: {e}")

                
            elif event == "blood_rain":
                game_data["current_event"] = "빨간 물에서 피냄새가 올라오기 시작합니다."
                for _ in range(7):
                    available_positions = [i for i in range(25) if i not in game_data["active_creatures"]]
                    if available_positions:
                        position = random.choice(available_positions)
                        creature = ActiveCreature(
                            position=position,
                            type=random.choice([
                                CreatureType.HAND, CreatureType.KNIFE, 
                                CreatureType.GHOST, CreatureType.EYE, 
                                CreatureType.MASK
                            ]),
                            appear_time=time.time(),
                            display_duration=2.5
                        )
                        game_data["active_creatures"][position] = creature
                
            elif event == "drag_into_water":
                if game_data["players"]:
                    target_player = random.choice(list(game_data["players"].values()))
                    game_data["current_event"] = f"{target_player.real_name}님이 물속으로 끌려들어가고 있습니다!"
                    asyncio.create_task(self._handle_dragged_event(channel_id, target_player))
            
            # 3초 후 현재 이벤트 메시지 제거
            await asyncio.sleep(3)
            game_data["current_event"] = ""

    async def _update_game_display(self, channel_id: int):
        """게임 화면 주기적 업데이트"""
        update_count = 0
        last_update_time = 0
        
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data["phase"] != "playing":
                break
            
            # Rate limit 방지를 위한 업데이트 간격 조절
            current_time = time.time()
            if current_time - last_update_time < 1.5:  # 최소 1.5초 간격
                await asyncio.sleep(1.5 - (current_time - last_update_time))
            
            # disabled_buttons를 permanent_disabled_buttons로 변경
            game_data["disabled_buttons"] = game_data.get("permanent_disabled_buttons", set()).copy()
            
            embed = self._create_game_embed(channel_id)
            try:
                await game_data["message"].edit(embed=embed)
                last_update_time = time.time()
                update_count += 1
                
                if debug_config.debug_enabled and update_count % 10 == 0:
                    debug_log("FISHING", f"Game display updated {update_count} times")
                    
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = getattr(e, 'retry_after', 5)
                    debug_log("FISHING", f"Rate limited on display update, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                else:
                    debug_log("FISHING", f"Failed to update display: {e}")
            except Exception as e:
                debug_log("FISHING", f"Error updating display: {e}")
            
            await asyncio.sleep(2.5)  # 업데이트 주기를 더 늘림
    
    async def _spawn_creatures(self, channel_id: int):
        """생물 스폰 - 더 자주 스폰되도록"""
        spawn_count = 0
        
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data["phase"] != "playing":
                continue
            
            # 현재 활성 생물 수 확인
            active_count = len(game_data["active_creatures"])
            
            # 활성 생물이 적으면 스폰 주기를 더 짧게
            if active_count < 3:
                spawn_delay = random.uniform(0.2, 0.8)  # 매우 빠름
            elif active_count < 6:
                spawn_delay = random.uniform(0.3, 1.2)  # 빠름
            elif active_count < 10:
                spawn_delay = random.uniform(0.5, 1.5)  # 보통
            else:
                spawn_delay = random.uniform(1.0, 2.0)  # 느림
            
            await asyncio.sleep(spawn_delay)
            
            # 게임 후반부에는 스폰 속도 증가
            if game_data.get("start_time"):
                elapsed = time.time() - game_data["start_time"]
                if elapsed > 60:  # 60초 이후
                    spawn_delay *= 0.7  # 30% 더 빠르게
                    debug_log("FISHING", "Late game - increased spawn rate")
            
            await self._spawn_single_creature(channel_id)
            
            spawn_count += 1
            if debug_config.debug_enabled and spawn_count % 20 == 0:
                debug_log("FISHING", f"Total spawns: {spawn_count}, Active creatures: {active_count}")

    async def _spawn_single_creature(self, channel_id: int):
        """단일 생물 스폰"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        available_positions = [
            i for i in range(25) 
            if i not in game_data["active_creatures"] and i not in game_data.get("disabled_buttons", set())
        ]
        if not available_positions:
            return
        
        position = random.choice(available_positions)
        
        # 평균 정신력 계산
        avg_sanity = 100
        if game_data["players"]:
            avg_sanity = sum(p.sanity for p in game_data["players"].values()) / len(game_data["players"])
        
        creature_type = self.get_random_creature_type(avg_sanity)
        
        creature = ActiveCreature(
            position=position,
            type=creature_type,
            appear_time=time.time(),
            display_duration=creature_type.value[3]
        )
        
        game_data["active_creatures"][position] = creature
        
        # 생물 출현은 즉시 업데이트
        await self._update_button(channel_id, position, True)
        
        # 생물 사라짐 예약
        await asyncio.sleep(creature.display_duration)
        
        if position in game_data["active_creatures"] and not game_data["active_creatures"][position].caught:
            del game_data["active_creatures"][position]
            await self._update_button(channel_id, position, False)    

    async def _update_button(self, channel_id: int, position: int, show_creature: bool):
        """버튼 업데이트 (배치 처리용)"""
        game_data = self.active_games.get(channel_id)
        if not game_data or "view" not in game_data:
            return
        
        view = game_data["view"]
        if not view:
            return
        
        # 버튼 상태 업데이트
        for item in view.children:
            if isinstance(item, HorrorButton) and item.position == position:
                # 영구 비활성화 버튼 체크
                if position in game_data.get("permanent_disabled_buttons", set()):
                    item.style = discord.ButtonStyle.secondary
                    item.emoji = "⚫"
                    item.disabled = True
                elif game_data.get("blackout", False) or game_data.get("all_eyes", False):
                    # 특수 상태
                    item.style = discord.ButtonStyle.success
                    item.emoji = "❓" if game_data.get("blackout") else "👁️"
                elif show_creature and position in game_data["active_creatures"]:
                    creature = game_data["active_creatures"][position]
                    if creature.type.value[4] == "danger":
                        item.style = discord.ButtonStyle.success
                    else:
                        item.style = discord.ButtonStyle.success
                    item.emoji = creature.type.value[1]
                else:
                    item.style = discord.ButtonStyle.danger
                    item.emoji = "🩸"
                    item.disabled = False
                break
        
        # 즉시 업데이트가 필요한 경우 (생물 출현)
        if show_creature:
            # 바로 업데이트
            await self._execute_button_update(channel_id)
        else:
            # 배치 처리로 예약
            if channel_id not in self.pending_button_updates:
                self.pending_button_updates[channel_id] = set()
            self.pending_button_updates[channel_id].add(position)
 
    def _create_game_embed(self, channel_id: int) -> discord.Embed:
        """게임 화면 생성"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return discord.Embed(title="오류")
        
        # 남은 시간
        if game_data["start_time"]:
            elapsed = int(time.time() - game_data["start_time"])
            remaining = max(0, self.game_duration - elapsed)
        else:
            elapsed = 0
            remaining = self.game_duration
        
        # 색상 변화
        color = self.get_embed_color(elapsed)
        
        embed = discord.Embed(
            title="🩸 영원 속 금붕어 잡기",
            description="붉은 물 속에서 무언가가 떠오릅니다.",
            color=color
        )
        
        embed.add_field(
            name="⏱️ 남은 시간",
            value=f"{remaining}초",
            inline=True
        )
        
        # 플레이어 정보
        if game_data["is_multiplayer"]:
            # 평균 정신력
            avg_sanity = 0
            if game_data["players"]:
                avg_sanity = sum(p.sanity for p in game_data["players"].values()) / len(game_data["players"])
            
            sanity_text = self.get_sanity_bar(avg_sanity) + f"{int(avg_sanity)}%"
            embed.add_field(
                name="👁️ 전체 정신력",
                value=sanity_text,
                inline=True
            )
            
            scores = []
            for player in sorted(game_data["players"].values(), key=lambda p: p.score, reverse=True):
                sanity_bar = self.get_sanity_bar(player.sanity)
                scores.append(f"{player.real_name}: {player.score}점 | 정신: {sanity_bar}{player.sanity}%")
            
            embed.add_field(
                name="📋 상태",
                value="\n".join(scores),
                inline=False
            )
            
            # 최근 결과
            recent_results = []
            for player in game_data["players"].values():
                if player.last_result:
                    recent_results.append(f"**{player.real_name}**: {player.last_result}")
            
            if recent_results:
                embed.add_field(
                    name="최근 낚은 것",
                    value="\n".join(recent_results[-3:]),
                    inline=False
                )
        else:
            player = list(game_data["players"].values())[0]
            sanity_bar = self.get_sanity_bar(player.sanity)
            poi_bar = self._get_poi_bar(player.poi_durability)
            
            embed.add_field(
                name="📊 상태",
                value=f"점수: {player.score}점\n"
                    f"정신력: {sanity_bar}{player.sanity}%\n"
                    f"포이: {poi_bar} ({player.poi_durability}%)\n"
                    f"남은 포이: {self.max_poi - player.poi_used}개",
                inline=True
            )
            
            if player.last_result:
                embed.add_field(
                    name="최근 낚은 것",
                    value=player.last_result,
                    inline=False
                )
        
        # 이벤트 메시지를 footer 또는 field로 표시
        current_event = game_data.get("current_event", "")
        event_history = game_data.get("event_history", [])
        
        # 현재 이벤트가 있으면 표시
        if current_event:
            embed.add_field(
                name="⚠️ 현재 상황",
                value=f"***{current_event}***",
                inline=False
            )
        
        # 이벤트 히스토리가 있으면 footer에 표시
        if event_history:
            footer_text = " | ".join(event_history[-3:])  # 최근 3개만
            embed.set_footer(text=footer_text)
        else:
            # 정신력에 따른 기본 footer
            if game_data["players"]:
                avg_sanity = sum(p.sanity for p in game_data["players"].values()) / len(game_data["players"])
                if avg_sanity < 30:
                    embed.set_footer(text="그것이 가까이 있습니다.")
                elif avg_sanity < 50:
                    embed.set_footer(text="무언가 잘못되었습니다.")
        
        return embed
    
    def _get_poi_bar(self, durability: int) -> str:
        """포이 내구도 바"""
        if durability >= 75:
            return "🟥🟥🟥🟥"
        elif durability >= 50:
            return "🟥🟥🟥⬛"
        elif durability >= 25:
            return "🟥🟥⬛⬛"
        else:
            return "🟥⬛⬛⬛"
    
    async def catch_attempt(self, interaction: discord.Interaction, position: int):
        """잡기 시도"""
        channel_id = interaction.channel_id
        game_data = self.active_games.get(channel_id)
        
        if not game_data or game_data["phase"] != "playing":
            await interaction.response.defer()
            return
        
        player = game_data["players"].get(interaction.user.id)
        if not player:
            await interaction.response.defer()
            return
        
        # defer를 먼저 처리하여 3초 제한 해결
        await interaction.response.defer()
        
        debug_log("FISHING", f"Catch attempt by {player.real_name} at position {position}")
        
        # 영구 비활성화된 버튼 클릭
        if position in game_data.get("permanent_disabled_buttons", set()):
            player.last_result = "⚫ 영원한 어둠. 이곳은 이미 죽었습니다."
            player.sanity = max(0, player.sanity - 3)
            debug_log("FISHING", f"Clicked on permanently disabled button at {position}")
            return
        
        # 블랙아웃 상태
        if game_data.get("blackout", False):
            if random.random() < 0.5:
                player.sanity = max(0, player.sanity - 20)
                player.last_result = "❓ 어둠 속에서 무언가가 당신을 붙잡았습니다. 정신력 -20"
            else:
                player.last_result = "❓ 어둠 속에서 허우적거립니다."
            debug_log("FISHING", f"Blackout state - sanity: {player.sanity}")
            return
        
        # 해당 위치에 생물이 있는지 확인
        if position not in game_data["active_creatures"]:
            player.last_result = "🩸 붉은 물만 출렁입니다."
            debug_log("FISHING", f"No creature at position {position}")
            return
        
        creature = game_data["active_creatures"][position]
        if creature.caught:
            player.last_result = "이미 사라진 곳입니다."
            debug_log("FISHING", f"Creature already caught at position {position}")
            return
        
        # 생물을 즉시 caught로 표시하여 중복 클릭 방지
        creature.caught = True
        debug_log("FISHING", f"Marked creature as caught at position {position}")
        
        # 포이 확인
        if player.poi_durability <= 0:
            if player.poi_used >= self.max_poi:
                player.last_result = "모든 포이가 찢어졌습니다. 🩸"
                await self._check_all_poi_broken(channel_id)
                return
            else:
                player.poi_used += 1
                player.poi_durability = 100
                debug_log("FISHING", f"New poi used. Total: {player.poi_used}/{self.max_poi}")
        
        # 반응 속도 계산
        reaction_time = time.time() - creature.appear_time
        
        # 정신력에 따른 주사위 보정
        sanity_modifier = -((100 - player.sanity) // 2)
        
        # 주사위 굴리기
        max_dice = self.base_dice + player.dice_modifier + sanity_modifier
        max_dice = max(20, max_dice)
        dice_roll = random.randint(1, max_dice)
        
        debug_log("FISHING", f"Dice roll: {dice_roll}/{max_dice}, reaction time: {reaction_time:.2f}s")
        
        result_msg = f"🎲 주사위: {dice_roll} (1d{max_dice}) "
        
        if creature.type.value[4] == "danger":
            # 위험한 것을 잡은 경우
            player.sanity = max(0, player.sanity - creature.type.value[5])
            player.danger_catches += 1
            
            if creature.type == CreatureType.KNIFE:
                player.poi_durability = 0
                result_msg += f"🔪 녹슨 칼날이 포이를 갈기갈기 찢었습니다. 정신력 -{creature.type.value[5]}"
            elif creature.type == CreatureType.HAND:
                result_msg += f"🤲 차가운 손이 당신을 잡아당깁니다. 정신력 -{creature.type.value[5]}"
            elif creature.type == CreatureType.GHOST:
                result_msg += f"👻 유령이 당신을 통과합니다. 정신력 -{creature.type.value[5]}"
            elif creature.type == CreatureType.SKULL:
                player.score += creature.type.value[2]
                result_msg += f"💀 해골붕어. 불길하지만 점수를 얻었습니다. +{creature.type.value[2]}점, 정신력 -{creature.type.value[5]}"
            elif creature.type == CreatureType.EYE:
                result_msg += f"👁️ 눈동자가 당신을 응시합니다. 정신력 -{creature.type.value[5]}"
            elif creature.type == CreatureType.MASK:
                result_msg += f"🎭 가면에서 웃음소리가. 정신력 -{creature.type.value[5]}"
            
            player.score += creature.type.value[2]
            
        else:
            # 일반 물고기
            base_damage = 10
            damage = base_damage + int(reaction_time * 8)
            damage = min(damage, 40)
            
            if dice_roll <= 5:
                player.poi_durability = 0
                result_msg += f"💔 포이가 찢어졌습니다! (남은: {self.max_poi - player.poi_used}개)"
            elif dice_roll < 40:
                player.poi_durability = max(0, player.poi_durability - damage)
                result_msg += f"💨 {creature.type.value[0]}이(가) 붉은 물 속으로 사라집니다."
            elif dice_roll < 85:
                player.score += creature.type.value[2]
                player.creatures_caught.append(creature.type)
                player.total_catches += 1
                player.poi_durability = max(0, player.poi_durability - damage)
                result_msg += f"🎣 {creature.type.value[0]} +{creature.type.value[2]}점"
            else:
                player.score += creature.type.value[2] * 2
                player.creatures_caught.extend([creature.type, creature.type])
                player.total_catches += 2
                player.poi_durability = max(0, player.poi_durability - damage)
                result_msg += f"🎊 {creature.type.value[0]} 2마리! +{creature.type.value[2] * 2}점"
        
        if player.sanity <= 0:
            result_msg += "\n⚠️ **정신이 무너집니다.**"
        
        player.last_result = result_msg
        
        # 생물 제거
        del game_data["active_creatures"][position]
        debug_log("FISHING", f"Removed creature from position {position}")
        
        # 버튼을 즉시 빈 상태로 업데이트 (배치 처리 대신 즉시 실행)
        view = game_data.get("view")
        if view:
            for item in view.children:
                if isinstance(item, HorrorButton) and item.position == position:
                    item.style = discord.ButtonStyle.danger
                    item.emoji = "🩸"
                    item.disabled = False
                    debug_log("FISHING", f"Updated button at position {position} to empty state")
                    break
            
            # 즉시 메시지 업데이트
            try:
                await game_data["message"].edit(view=view)
                debug_log("FISHING", "Updated game view immediately after catch")
            except discord.HTTPException as e:
                debug_log("FISHING", f"Failed to update view immediately: {e}")
        
        # 포이 체크
        if player.poi_durability <= 0 and player.poi_used >= self.max_poi:
            await self._check_all_poi_broken(channel_id)

    # fishing.py의 end_game 메서드 수정
    async def end_game(self, channel_id: int):
        """게임 종료"""
        # 중복 종료 방지
        if channel_id in self.ending_games:
            debug_log("FISHING", f"Game already ending for channel {channel_id}")
            return
        
        self.ending_games.add(channel_id)
        debug_log("FISHING", f"Starting end_game for channel {channel_id}")
        
        # 게임 데이터 확인
        game_data = self.active_games.get(channel_id)
        if not game_data:
            debug_log("FISHING", f"No game data found for channel {channel_id} during end_game")
            self.ending_games.discard(channel_id)
            return
        
        # 게임 상태를 먼저 종료로 변경
        game_data["phase"] = "ended"
        
        # 버튼 업데이트 태스크 정리
        if channel_id in self.button_update_tasks:
            self.button_update_tasks[channel_id].cancel()
            del self.button_update_tasks[channel_id]
        
        # 대기 중인 버튼 업데이트 정리
        if channel_id in self.pending_button_updates:
            del self.pending_button_updates[channel_id]
        
        # 모든 태스크 취소
        tasks_to_cancel = ["spawn_task", "update_task", "event_task", 
                        "sanity_drain_task", "button_disable_task", "button_batch_task"]
        
        for task_name in tasks_to_cancel:
            if task_name in game_data and game_data[task_name]:
                try:
                    game_data[task_name].cancel()
                    debug_log("FISHING", f"Cancelled task: {task_name}")
                except Exception as e:
                    debug_log("FISHING", f"Error cancelling task {task_name}: {e}")
        
        # 잠시 대기하여 태스크들이 정리되도록 함
        await asyncio.sleep(0.5)
        
        # 이벤트 메시지 삭제
        event_messages = game_data.get("event_messages", [])
        if event_messages:
            debug_log("FISHING", f"Scheduling cleanup of {len(event_messages)} event messages")
            
            async def cleanup_messages():
                for msg in event_messages:
                    try:
                        await asyncio.sleep(0.5)
                        await msg.delete()
                    except:
                        pass
            
            asyncio.create_task(cleanup_messages())
        
        # 게임 결과 표시
        try:
            # 플레이어가 있는지 확인
            if not game_data["players"]:
                debug_log("FISHING", "No players in game, skipping results")
                # 플레이어가 없어도 메시지는 업데이트
                embed = discord.Embed(
                    title="🎏 금붕어 잡기 종료!",
                    description="모든 플레이어가 게임을 떠났습니다.",
                    color=discord.Color.red()
                )
                if game_data.get("message"):
                    await game_data["message"].edit(embed=embed, view=None)
            else:
                # 순위 정렬
                players_list = list(game_data["players"].values())
                players_list.sort(key=lambda p: (p.score, p.total_catches, -p.danger_catches), reverse=True)
                
                debug_log("FISHING", f"Calculating results for {len(players_list)} players")
                
                # 순위 계산
                ranked_players = []
                current_rank = 1
                for i, player in enumerate(players_list):
                    if i > 0:
                        prev_player = players_list[i-1]
                        if prev_player.score != player.score:
                            current_rank = i + 1
                    ranked_players.append((current_rank, player))
                
                # 결과 임베드 생성
                embed = discord.Embed(
                    title="🎏 영원의 금붕어 잡기 - 게임 종료!",
                    description="붉은 물이 다시 잠잠해집니다...",
                    color=discord.Color.dark_red()
                )
                
                # 순위 표시
                ranking_text = []
                for rank, player in ranked_players:
                    # 잡은 생물 집계
                    catches = {}
                    for creature_type in player.creatures_caught:
                        catches[creature_type.value[0]] = catches.get(creature_type.value[0], 0) + 1
                    
                    catch_text = ", ".join([f"{name} {count}마리" for name, count in catches.items()])
                    
                    ranking_text.append(
                        f"**{rank}위. {player.real_name}**: {player.score}점\n"
                        f"   └ 총 {player.total_catches}마리 | 정신력 {player.sanity}% | 위험 조우 {player.danger_catches}회\n"
                        f"   └ 잡은 것: {catch_text if catch_text else '없음'}"
                    )
                
                embed.add_field(
                    name="🏆 최종 순위",
                    value="\n\n".join(ranking_text) if ranking_text else "참가자 없음",
                    inline=False
                )
                
                # 게임 통계
                total_time = int(time.time() - game_data["start_time"]) if game_data.get("start_time") else 0
                minutes = total_time // 60
                seconds = total_time % 60
                
                total_catches = sum(p.total_catches for p in players_list)
                total_dangers = sum(p.danger_catches for p in players_list)
                avg_sanity = sum(p.sanity for p in players_list) / len(players_list) if players_list else 0
                
                embed.add_field(
                    name="📊 게임 통계",
                    value=f"게임 시간: {minutes}분 {seconds}초\n"
                        f"총 잡은 수: {total_catches}마리\n"
                        f"위험 조우: {total_dangers}회\n"
                        f"평균 정신력: {avg_sanity:.1f}%",
                    inline=False
                )
                
                # 특별 메시지
                if avg_sanity < 30:
                    embed.add_field(
                        name="⚠️ 경고",
                        value=" 정신력이 많이 감소했습니다. 어지러움이 느껴집니다.",
                        inline=False
                    )
                
                # 보상 안내
                embed.add_field(
                    name="💝 보상",
                    value="이번 게임에서는 보상이 지급되지 않습니다.\n",
                    inline=False
                )
                                
                # 메시지 업데이트
                if game_data.get("message"):
                    try:
                        await game_data["message"].edit(embed=embed, view=None)
                        debug_log("FISHING", "Successfully updated game end message")
                    except Exception as e:
                        debug_log("FISHING", f"Failed to update end message: {e}")
                        # 실패 시 새 메시지로 전송
                        try:
                            await game_data["message"].channel.send(embed=embed)
                            debug_log("FISHING", "Sent new end message instead")
                        except:
                            pass
            
        except Exception as e:
            debug_log("FISHING", f"Error displaying game results: {e}")
            logger.error(f"Game end error: {e}")
            # 오류 발생 시에도 기본 메시지는 표시
            try:
                if game_data.get("message"):
                    embed = discord.Embed(
                        title="🎏 게임 종료",
                        description="게임이 종료되었습니다.",
                        color=discord.Color.red()
                    )
                    await game_data["message"].edit(embed=embed, view=None)
            except:
                pass
        
        # active_games에서 제거
        if channel_id in self.active_games:
            del self.active_games[channel_id]
            debug_log("FISHING", f"Game removed from active_games for channel {channel_id}")
        
        # ending_games에서 제거
        self.ending_games.discard(channel_id)
        debug_log("FISHING", "Game ended successfully")

# UI 컴포넌트들
class GameModeSelectView(discord.ui.View):
    def __init__(self, game: HorrorFishingGame, channel_id: int, host: discord.Member):
        super().__init__(timeout=30)
        self.game = game
        self.channel_id = channel_id
        self.host = host
    
    @discord.ui.button(label="시작하기", style=discord.ButtonStyle.primary, emoji="🎣")
    async def single_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message(
                "게임을 시작한 사람만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self.game.start_single_player(self.channel_id, interaction.user)
        self.stop()
    
    @discord.ui.button(label="멀티플레이", style=discord.ButtonStyle.success, emoji="👥")
    async def multiplayer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message(
                "게임을 시작한 사람만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self.game.setup_multiplayer(self.channel_id)
        self.stop()

class MultiplayerLobbyView(discord.ui.View):
    def __init__(self, game: HorrorFishingGame, channel_id: int):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
    
    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, emoji="🎏")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        success = await self.game.add_player(self.channel_id, interaction.user)
        
        if success:
            game_data = self.game.active_games.get(self.channel_id)
            player = game_data["players"][interaction.user.id]
            await interaction.response.send_message(
                f"{player.real_name}님이 참가했습니다! "
                f"({len(game_data['players'])}/4)",
                ephemeral=False
            )
        else:
            await interaction.response.send_message(
                "참가할 수 없습니다!",
                ephemeral=True
            )
    
    @discord.ui.button(label="시작하기", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_data = self.game.active_games.get(self.channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "게임을 찾을 수 없습니다.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game_data["host"].id:
            await interaction.response.send_message(
                "호스트만 게임을 시작할 수 있습니다!",
                ephemeral=True
            )
            return
        
        if len(game_data["players"]) < 2:
            await interaction.response.send_message(
                "최소 2명이 필요합니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self.game.start_multiplayer_game(self.channel_id)
        self.stop()

class HorrorGameView(discord.ui.View):
    def __init__(self, game: HorrorFishingGame, channel_id: int):
        super().__init__(timeout=90)  # 게임시간 90초 + 여유
        self.game = game
        self.channel_id = channel_id
        
        for i in range(25):
            row = i // 5
            button = HorrorButton(i, row)
            self.add_item(button)

class HorrorButton(discord.ui.Button):
    def __init__(self, position: int, row: int):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="\u200b",
            emoji="🩸",
            row=row
        )
        self.position = position
    
    async def callback(self, interaction: discord.Interaction):
        view: HorrorGameView = self.view
        await view.game.catch_attempt(interaction, self.position)

# 전역 게임 인스턴스
horror_fishing_game = HorrorFishingGame()

def get_horror_fishing_game():
    return horror_fishing_game

# 호환성을 위한 별칭 함수 추가
def get_fishing_game():
    """기존 코드와의 호환성을 위한 함수"""
    return horror_fishing_game

# 채팅 메시지 처리를 위한 이벤트 핸들러 (bot.py에서 호출)
async def on_message_horror_fishing(message: discord.Message):
    """채팅 메시지 처리"""
    await horror_fishing_game.process_chat_message(message)