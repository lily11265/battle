# battle.py - 전투 시스템 (수정된 버전)
import discord
from discord import app_commands
import asyncio
import random
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from debug_config import debug_log, performance_tracker, debug_config
from collections import deque
from battle_utils import extract_health_from_nickname, calculate_battle_health, update_nickname_health

logger = logging.getLogger(__name__)

class BattlePhase(Enum):
    """전투 단계"""
    WAITING = "대기중"
    INIT_ROLL = "선공 결정"
    ATTACK_ROLL = "공격 다이스"
    DEFEND_ROLL = "회피 다이스"
    RESULT = "결과 처리"
    FINISHED = "전투 종료"

class BattleAction(Enum):
    """전투 행동"""
    ATTACK = "공격"
    DEFEND = "회피"

@dataclass
class BattlePlayer:
    """전투 참가자 (수정됨)"""
    user: discord.Member
    real_name: str
    hits_received: int = 0
    hits_dealt: int = 0
    total_attack_rolls: int = 0
    total_defend_rolls: int = 0
    attack_sum: int = 0
    defend_sum: int = 0
    is_first_attacker: bool = False
    max_health: int = 10  # 전투 체력 (기본 10)
    real_health: int = 100  # 실제 체력
    skip_turn: bool = False  # 턴 넘김 여부

@dataclass
class DiceResult:
    """다이스 결과"""
    player_name: str
    dice_value: int
    user_id: Optional[int] = None

@dataclass
class BattleRecord:
    """전투 기록"""
    player1_name: str
    player2_name: str
    winner_name: Optional[str]
    loser_name: Optional[str]
    rounds: int
    start_time: datetime
    end_time: Optional[datetime]
    channel_id: int
    is_active: bool = True

class BattleGame:
    """전투 게임 관리자 (수정됨)"""
    
    def __init__(self):
        self.active_battles = {}
        self.pending_dice = {}
        self.win_condition = 10
        self.battle_history = deque(maxlen=10)
        self.health_sync_enabled = {}  # channel_id: bool
        
        # 실제 이름 목록
        self.known_names = {
            "아카시하지메", "아카시 하지메", "아카시_하지메",
            "펀처", "유진석", "휘슬", "배달기사", "페이",
            "로메즈아가레스", "로메즈 아가레스", "로메즈_아가레스",
            "레이나하트베인", "레이나 하트베인", "레이나_하트베인",
            "비비", "오카미나오하", "오카미 나오하", "오카미_나오하",
            "카라트에크", "토트", "처용", "멀플리시", "멀 플리시", "멀_플리시",
            "코발트윈드", "옥타", "베레니케", "안드라블랙", "안드라 블랙", "안드라_블랙",
            "봉고3호", "봉고 3호", "봉고_3호", "몰", "베니", "백야", "루치페르",
            "벨사이르드라켄리트", "벨사이르 드라켄리트", "벨사이르_드라켄리트",
            "불스", "퓨어메탈", "퓨어 메탈", "퓨어_메탈",
            "노단투", "노 단투", "노_단투", "라록", "아카이브", "베터", "메르쿠리",
            "마크-112", "마크112", "스푸트니크2세", "스푸트니크 2세", "스푸트니크_2세",
            "이터니티", "커피머신"
        }
    
    @performance_tracker
    def extract_real_name(self, display_name: str) -> str:
        """닉네임에서 실제 이름 추출"""
        debug_log("BATTLE", f"Extracting name from: {display_name}")
        
        # 정규화: 공백, 언더스코어 제거
        normalized = display_name.replace(" ", "").replace("_", "")
        
        # 알려진 이름들과 매칭
        for known_name in self.known_names:
            normalized_known = known_name.replace(" ", "").replace("_", "")
            if normalized_known in normalized:
                debug_log("BATTLE", f"Found known name: {known_name}")
                return known_name
        
        # 못 찾으면 원본 반환
        debug_log("BATTLE", f"No known name found, using original: {display_name}")
        return display_name
    
    def _get_health_bar(self, current_health: int, max_health: int) -> str:
        """체력바 생성"""
        green_hearts = current_health
        broken_hearts = max_health - current_health
        return "💚" * green_hearts + "💔" * broken_hearts
    
    @performance_tracker
    def parse_dice_message(self, message_content: str) -> Optional[DiceResult]:
        """다이스 메시지 파싱"""
        debug_log("BATTLE", f"Parsing dice message: {message_content}")
        
        # 공백 정규화 - 연속된 공백을 하나로
        normalized_content = ' '.join(message_content.split())
        
        # 패턴 수정: 공백이 있을 수 있는 경우 처리
        pattern = r"`([^`]+)`님이.*?주사위를\s*굴\s*려.*?\*\*(\d+)\*\*.*?나왔습니다"
        
        match = re.search(pattern, normalized_content)
        if match:
            player_name = match.group(1).strip()
            dice_value = int(match.group(2))
            
            debug_log("BATTLE", f"Parsed dice result - Player: {player_name}, Value: {dice_value}")
            
            return DiceResult(
                player_name=player_name,
                dice_value=dice_value
            )
        
        debug_log("BATTLE", f"Failed to parse dice message: {normalized_content[:100]}...")
        return None
    
    async def start_battle(self, interaction: discord.Interaction, opponent: discord.Member):
        """전투 시작 (체력 감지 추가)"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_battles:
            await interaction.response.send_message(
                "이미 진행 중인 전투가 있습니다!",
                ephemeral=True
            )
            return
        
        if interaction.user.id == opponent.id:
            await interaction.response.send_message(
                "자기 자신과는 전투할 수 없습니다!",
                ephemeral=True
            )
            return
        
        # 체력 추출
        player1_real_health = extract_health_from_nickname(interaction.user.display_name) or 100
        player2_real_health = extract_health_from_nickname(opponent.display_name) or 100
        
        # 플레이어 정보 생성
        player1 = BattlePlayer(
            user=interaction.user,
            real_name=self.extract_real_name(interaction.user.display_name),
            real_health=player1_real_health,
            max_health=10  # 일단 기본값
        )
        
        player2 = BattlePlayer(
            user=opponent,
            real_name=self.extract_real_name(opponent.display_name),
            real_health=player2_real_health,
            max_health=10  # 일단 기본값
        )
        
        # BattleRecord 생성
        battle_record = BattleRecord(
            player1_name=player1.real_name,
            player2_name=player2.real_name,
            winner_name=None,
            loser_name=None,
            rounds=0,
            start_time=datetime.now(),
            end_time=None,
            channel_id=channel_id,
            is_active=True
        )
        
        # 전투 기록 추가
        self.battle_history.append(battle_record)
        
        # 전투 데이터 초기화
        battle_data = {
            "player1": player1,
            "player2": player2,
            "phase": BattlePhase.WAITING,
            "current_attacker": None,
            "current_defender": None,
            "round": 0,
            "start_time": datetime.now(),
            "message": None,
            "last_dice_request": None,
            "battle_log": [],
            "battle_record": battle_record,
            "health_sync": False
        }
        
        self.active_battles[channel_id] = battle_data
        
        # 체력 동기화 선택 임베드
        embed = discord.Embed(
            title="⚔️ 전투 시작 확인",
            description=f"{player1.real_name} VS {player2.real_name}",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="체력 정보",
            value=f"{player1.real_name}: {player1_real_health} HP → 전투 체력 {calculate_battle_health(player1_real_health)}\n"
                  f"{player2.real_name}: {player2_real_health} HP → 전투 체력 {calculate_battle_health(player2_real_health)}",
            inline=False
        )
        
        embed.add_field(
            name="체력 동기화",
            value="체력을 동기화하면 현재 체력에 맞춰 전투가 진행됩니다.\n"
                  "동기화하지 않으면 기본 10번으로 진행됩니다.",
            inline=False
        )
        
        view = BattleStartView(self, channel_id, with_sync=True)
        await interaction.response.send_message(embed=embed, view=view)
        battle_data["message"] = await interaction.original_response()

    async def handle_surrender(self, channel_id: int, winner: BattlePlayer, loser: BattlePlayer):
        """항복 처리"""
        battle_data = self.active_battles.get(channel_id)
        if not battle_data:
            return
        
        battle_data["phase"] = BattlePhase.FINISHED
        
        # 전투 기록 업데이트
        battle_data["battle_record"].winner_name = winner.real_name
        battle_data["battle_record"].loser_name = loser.real_name
        battle_data["battle_record"].end_time = datetime.now()
        battle_data["battle_record"].is_active = False
        
        # 결과 임베드
        embed = discord.Embed(
            title="🏳️ 전투 종료 - 항복",
            description=f"**{loser.real_name}**님이 항복했습니다.\n\n**🎉 {winner.real_name}님의 승리! 🎉**",
            color=discord.Color.red()
        )
        
        # 전투 시간
        battle_duration = datetime.now() - battle_data["start_time"]
        embed.add_field(
            name="전투 정보",
            value=f"총 라운드: {battle_data['round']}라운드\n"
                f"전투 시간: {battle_duration.seconds // 60}분 {battle_duration.seconds % 60}초\n"
                f"종료 사유: 항복",
            inline=False
        )
        
        # 메시지 전송
        await battle_data["message"].channel.send(embed=embed)
        
        # 원래 메시지 업데이트
        simple_embed = discord.Embed(
            title="전투 종료",
            description=f"{winner.real_name} 승리! (상대 항복)",
            color=discord.Color.blue()
        )
        await battle_data["message"].edit(embed=simple_embed, view=None)
        
        # 정리
        del self.active_battles[channel_id]

    async def handle_turn_skip(self, message: discord.Message):
        """턴 넘김 처리"""
        channel_id = message.channel.id
        
        if channel_id not in self.active_battles:
            return
        
        battle_data = self.active_battles[channel_id]
        
        # 현재 턴의 플레이어인지 확인
        current_player = None
        if battle_data["phase"] == BattlePhase.ATTACK_ROLL:
            if battle_data["current_attacker"].user.id == message.author.id:
                current_player = battle_data["current_attacker"]
            elif battle_data["current_defender"].user.id == message.author.id:
                current_player = battle_data["current_defender"]
        
        if not current_player:
            return
        
        # 턴 스킵 처리
        current_player.skip_turn = True
        
        # 대기 중인 다이스에서 제거
        if channel_id in self.pending_dice:
            pending = self.pending_dice[channel_id]
            if message.author.id in pending["waiting_for"]:
                pending["waiting_for"].remove(message.author.id)
                
                # 가상의 다이스 결과 추가 (0으로 처리)
                pending["results"][message.author.id] = DiceResult(
                    player_name=current_player.real_name,
                    dice_value=0,
                    user_id=message.author.id
                )
                
                await message.channel.send(f"⏭️ {current_player.real_name}님이 턴을 넘겼습니다.")
                
                # 모두 행동했는지 확인
                if not pending["waiting_for"]:
                    await self._process_dice_results(channel_id)
    
    async def handle_recovery_update(self, user_id: int, old_health: int, new_health: int):
        """회복으로 인한 전투 체력 업데이트"""
        for channel_id, battle_data in self.active_battles.items():
            if battle_data["health_sync"]:
                player = None
                if battle_data["player1"].user.id == user_id:
                    player = battle_data["player1"]
                elif battle_data["player2"].user.id == user_id:
                    player = battle_data["player2"]
                
                if player:
                    old_battle_health = calculate_battle_health(old_health)
                    new_battle_health = calculate_battle_health(new_health)
                    
                    if new_battle_health > old_battle_health:
                        health_increase = new_battle_health - old_battle_health
                        player.max_health += health_increase
                        player.real_health = new_health
                        
                        await battle_data["message"].channel.send(
                            f"💚 {player.real_name}님의 회복으로 전투 체력이 {health_increase} 증가했습니다! "
                            f"(전투 체력: {player.max_health - player.hits_received}/{player.max_health})"
                        )

    async def accept_battle(self, channel_id: int, from_sync: bool = False):
        """전투 수락"""
        battle_data = self.active_battles.get(channel_id)
        if not battle_data:
            return
        
        debug_log("BATTLE", f"Battle accepted")
        
        # 선공 결정 단계로 이동
        await self._start_init_phase(channel_id)
        
        # from_sync가 True면 이미 메시지가 생성되었으므로 스킵
        if not from_sync:
            embed = self._create_battle_embed(channel_id)
            # 새로운 일반 메시지 생성
            new_message = await battle_data["message"].channel.send(embed=embed)
            battle_data["message"] = new_message
    
    async def decline_battle(self, interaction: discord.Interaction, channel_id: int):
        """전투 거절"""
        battle_data = self.active_battles.get(channel_id)
        if not battle_data:
            await interaction.response.send_message(
                "전투를 찾을 수 없습니다.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != battle_data["player2"].user.id:
            await interaction.response.send_message(
                "상대방만 전투를 거절할 수 있습니다!",
                ephemeral=True
            )
            return
        
        debug_log("BATTLE", f"Battle declined by {interaction.user.display_name}")
        
        # 전투 기록 업데이트
        battle_data["battle_record"].is_active = False
        battle_data["battle_record"].end_time = datetime.now()
        
        embed = discord.Embed(
            title="❌ 전투 거절",
            description=f"{battle_data['player2'].real_name}님이 전투를 거절했습니다.",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
        del self.active_battles[channel_id]
    
    async def _start_init_phase(self, channel_id: int):
        """선공 결정 단계 시작"""
        battle_data = self.active_battles[channel_id]
        battle_data["phase"] = BattlePhase.INIT_ROLL
        
        debug_log("BATTLE", "Starting initiative phase")
        
        # 양쪽 플레이어가 다이스를 굴도록 요청
        self.pending_dice[channel_id] = {
            "phase": BattlePhase.INIT_ROLL,
            "waiting_for": [battle_data["player1"].user.id, battle_data["player2"].user.id],
            "results": {},
        }
        
        # 다이스 요청 메시지
        await battle_data["message"].channel.send(
            f"🎲 {battle_data['player1'].real_name}님과 {battle_data['player2'].real_name}님, "
            f"선공을 정하기 위해 `/주사위`를 굴려주세요!"
        )
    
    async def process_dice_message(self, message: discord.Message):
        """다이스 메시지 처리"""
        channel_id = message.channel.id
        
        debug_log("BATTLE", f"process_dice_message called for channel {channel_id}")
        
        # 전투가 진행 중이고 다이스를 기다리는 상태인지 확인
        if channel_id not in self.active_battles:
            debug_log("BATTLE", f"No active battle in channel {channel_id}")
            return
            
        if channel_id not in self.pending_dice:
            debug_log("BATTLE", f"Not waiting for dice in channel {channel_id}")
            return
        
        debug_log("BATTLE", f"Processing dice message in channel {channel_id}")
        
        # 메시지 파싱
        dice_result = self.parse_dice_message(message.content)
        if not dice_result:
            debug_log("BATTLE", "Failed to parse dice message")
            return
        
        # 플레이어 매칭
        battle_data = self.active_battles[channel_id]
        pending_data = self.pending_dice[channel_id]
        
        # 현재 대기 중인 플레이어 정보 디버그
        debug_log("BATTLE", f"Current phase: {pending_data['phase'].value}")
        debug_log("BATTLE", f"Waiting for users: {pending_data['waiting_for']}")
        
        # 다이스 메시지의 플레이어 이름을 실제 이름으로 변환
        dice_real_name = self.extract_real_name(dice_result.player_name)
        debug_log("BATTLE", f"Dice player name '{dice_result.player_name}' converted to real name '{dice_real_name}'")
        
        user_id = None
        if dice_real_name == battle_data["player1"].real_name:
            user_id = battle_data["player1"].user.id
            debug_log("BATTLE", f"Matched to player1: {battle_data['player1'].real_name}")
        elif dice_real_name == battle_data["player2"].real_name:
            user_id = battle_data["player2"].user.id
            debug_log("BATTLE", f"Matched to player2: {battle_data['player2'].real_name}")
        
        if user_id is None:
            debug_log("BATTLE", f"Player matching failed for name: '{dice_real_name}'")
            debug_log("BATTLE", f"  - Player1: '{battle_data['player1'].real_name}' (ID: {battle_data['player1'].user.id})")
            debug_log("BATTLE", f"  - Player2: '{battle_data['player2'].real_name}' (ID: {battle_data['player2'].user.id})")
            return
            
        if user_id not in pending_data["waiting_for"]:
            debug_log("BATTLE", f"User {user_id} not in waiting list: {pending_data['waiting_for']}")
            return
        
        # 결과 저장
        dice_result.player_name = dice_real_name
        pending_data["results"][user_id] = dice_result
        pending_data["waiting_for"].remove(user_id)
        
        debug_log("BATTLE", f"Dice result recorded for {dice_real_name} (user_id: {user_id}): {dice_result.dice_value}")
        debug_log("BATTLE", f"Still waiting for: {pending_data['waiting_for']}")
        
        # 모든 플레이어가 굴렸는지 확인
        if not pending_data["waiting_for"]:
            debug_log("BATTLE", "All players rolled, processing results")
            await self._process_dice_results(channel_id)
        else:
            debug_log("BATTLE", f"Still waiting for {len(pending_data['waiting_for'])} player(s)")
    
    async def _process_dice_results(self, channel_id: int):
        """다이스 결과 처리"""
        battle_data = self.active_battles[channel_id]
        pending_data = self.pending_dice[channel_id]
        
        debug_log("BATTLE", "Processing dice results")
        
        # 현재 phase와 결과 미리 저장
        current_phase = pending_data["phase"]
        results = pending_data["results"].copy()
        
        # 대기 중인 다이스 정보 삭제
        del self.pending_dice[channel_id]
        
        # phase에 따라 처리
        if current_phase == BattlePhase.INIT_ROLL:
            await self._process_init_results(channel_id, results)
        elif current_phase == BattlePhase.ATTACK_ROLL:
            await self._process_attack_defend_results(channel_id, results)
    
    async def _process_init_results(self, channel_id: int, results: Dict):
        """선공 결정 결과 처리"""
        battle_data = self.active_battles[channel_id]
        
        player1_result = results[battle_data["player1"].user.id]
        player2_result = results[battle_data["player2"].user.id]
        
        debug_log("BATTLE", f"Init results - P1: {player1_result.dice_value}, P2: {player2_result.dice_value}")
        
        # 선공 결정
        if player1_result.dice_value > player2_result.dice_value:
            battle_data["current_attacker"] = battle_data["player1"]
            battle_data["current_defender"] = battle_data["player2"]
            battle_data["player1"].is_first_attacker = True
        elif player2_result.dice_value > player1_result.dice_value:
            battle_data["current_attacker"] = battle_data["player2"]
            battle_data["current_defender"] = battle_data["player1"]
            battle_data["player2"].is_first_attacker = True
        else:
            # 동점일 경우 다시
            debug_log("BATTLE", "Tie in initiative, rolling again")
            await battle_data["message"].channel.send(
                f"🎲 동점입니다! 다시 굴려주세요!"
            )
            await self._start_init_phase(channel_id)
            return
        
        # 전투 로그에 기록
        battle_data["battle_log"].append(
            f"🎲 선공 결정: {battle_data['current_attacker'].real_name} {player1_result.dice_value if battle_data['current_attacker'] == battle_data['player1'] else player2_result.dice_value} "
            f"vs {battle_data['current_defender'].real_name} {player2_result.dice_value if battle_data['current_attacker'] == battle_data['player1'] else player1_result.dice_value}"
        )
        
        # 첫 번째 라운드 시작
        await self._start_combat_round(channel_id)
    
    async def _start_combat_round(self, channel_id: int):
        """전투 라운드 시작"""
        battle_data = self.active_battles[channel_id]
        battle_data["round"] += 1
        battle_data["phase"] = BattlePhase.ATTACK_ROLL
        
        # 전투 기록 업데이트
        battle_data["battle_record"].rounds = battle_data["round"]
        
        debug_log("BATTLE", f"Starting combat round {battle_data['round']}")
        
        # 다이스 요청
        self.pending_dice[channel_id] = {
            "phase": BattlePhase.ATTACK_ROLL,
            "waiting_for": [battle_data["current_attacker"].user.id, battle_data["current_defender"].user.id],
            "results": {},
        }
        
        debug_log("BATTLE", f"Set pending_dice for channel {channel_id}: waiting for {self.pending_dice[channel_id]['waiting_for']}")
        
        # 메시지 업데이트 (webhook 토큰 만료 처리)
        try:
            await battle_data["message"].edit(embed=self._create_battle_embed(channel_id))
        except discord.errors.HTTPException as e:
            # 토큰 만료 시 새 메시지 생성
            if e.code == 50027:  # Invalid Webhook Token
                channel = battle_data["message"].channel
                battle_data["message"] = await channel.send(embed=self._create_battle_embed(channel_id))
            else:
                raise
        
        # 체력 상태 계산
        p1_health = battle_data["player1"].max_health - battle_data["player1"].hits_received
        p2_health = battle_data["player2"].max_health - battle_data["player2"].hits_received
        
        # 체력바 생성
        p1_bar = self._get_health_bar(p1_health, battle_data["player1"].max_health)
        p2_bar = self._get_health_bar(p2_health, battle_data["player2"].max_health)
        
        # 라운드 메시지에 체력 상태 추가
        await battle_data["message"].channel.send(
            f"⚔️ **라운드 {battle_data['round']}**\n"
            f"💚 {battle_data['player1'].real_name}: {p1_bar} ({p1_health}/{battle_data['player1'].max_health})\n"
            f"💚 {battle_data['player2'].real_name}: {p2_bar} ({p2_health}/{battle_data['player2'].max_health})\n\n"
            f"🗡️ {battle_data['current_attacker'].real_name}님, 공격 다이스를 굴려주세요!\n"
            f"🛡️ {battle_data['current_defender'].real_name}님, 회피 다이스를 굴려주세요!"
        )
    
    async def _process_attack_defend_results(self, channel_id: int, results: Dict):
        """공격/회피 결과 처리"""
        battle_data = self.active_battles[channel_id]
        
        attacker_result = results[battle_data["current_attacker"].user.id]
        defender_result = results[battle_data["current_defender"].user.id]
        
        debug_log("BATTLE", f"Combat results - Attack: {attacker_result.dice_value}, Defend: {defender_result.dice_value}")
        
        # 통계 업데이트
        battle_data["current_attacker"].total_attack_rolls += 1
        battle_data["current_attacker"].attack_sum += attacker_result.dice_value
        battle_data["current_defender"].total_defend_rolls += 1
        battle_data["current_defender"].defend_sum += defender_result.dice_value
        
        # 결과 판정
        hit = attacker_result.dice_value > defender_result.dice_value
        
        if hit:
            battle_data["current_defender"].hits_received += 1
            battle_data["current_attacker"].hits_dealt += 1
            result_text = f"🎯 **명중!** {battle_data['current_attacker'].real_name}({attacker_result.dice_value})이 {battle_data['current_defender'].real_name}({defender_result.dice_value})에게 명중!"
            
            # 체력 동기화가 활성화된 경우 닉네임 업데이트
            if battle_data.get("health_sync", False):
                defender = battle_data["current_defender"]
                # 새로운 실제 체력 계산
                new_real_health = defender.real_health - 10  # 전투 체력 1 = 실제 체력 10
                new_real_health = max(0, new_real_health)  # 최소 0
                
                # 닉네임 업데이트
                new_nickname = update_nickname_health(defender.user.display_name, new_real_health)
                try:
                    await defender.user.edit(nick=new_nickname)
                    defender.real_health = new_real_health
                    debug_log("BATTLE", f"Updated {defender.real_name}'s nickname health to {new_real_health}")
                except discord.Forbidden:
                    logger.error(f"닉네임 변경 권한 없음: {defender.real_name}")
                except Exception as e:
                    logger.error(f"닉네임 업데이트 실패: {e}")
        else:
            result_text = f"🛡️ **회피!** {battle_data['current_defender'].real_name}({defender_result.dice_value})이 {battle_data['current_attacker'].real_name}({attacker_result.dice_value})의 공격을 회피!"
        
        # 전투 로그에 기록
        battle_data["battle_log"].append(
            f"R{battle_data['round']}: {battle_data['current_attacker'].real_name}({attacker_result.dice_value}) vs "
            f"{battle_data['current_defender'].real_name}({defender_result.dice_value}) - {'명중' if hit else '회피'}"
        )
        
        # 승부 체크
        if battle_data["current_defender"].hits_received >= battle_data["current_defender"].max_health:
            await self._end_battle(channel_id, result_text)
            return
        
        # 공수 교대
        battle_data["current_attacker"], battle_data["current_defender"] = \
            battle_data["current_defender"], battle_data["current_attacker"]
        
        # 결과 메시지
        await battle_data["message"].channel.send(result_text)
        
        # 다음 라운드
        await asyncio.sleep(2)
        await self._start_combat_round(channel_id)
    
    async def _end_battle(self, channel_id: int, final_result: str):
        """전투 종료"""
        battle_data = self.active_battles[channel_id]
        battle_data["phase"] = BattlePhase.FINISHED
        
        # 승자 결정
        if battle_data["player1"].hits_received >= battle_data["player1"].max_health:
            winner = battle_data["player2"]
            loser = battle_data["player1"]
        else:
            winner = battle_data["player1"]
            loser = battle_data["player2"]
        
        # 전투 기록 업데이트
        battle_data["battle_record"].winner_name = winner.real_name
        battle_data["battle_record"].loser_name = loser.real_name
        battle_data["battle_record"].end_time = datetime.now()
        battle_data["battle_record"].is_active = False
        
        debug_log("BATTLE", f"Battle ended - Winner: {winner.real_name}, Loser: {loser.real_name}")
        
        # 결과 임베드
        embed = discord.Embed(
            title="🏆 전투 종료!",
            description=f"{final_result}\n\n**🎉 {winner.real_name}님의 승리! 🎉**",
            color=discord.Color.gold()
        )
        
        # 통계
        embed.add_field(
            name=f"{battle_data['player1'].real_name}의 전투 기록",
            value=f"받은 피해: {battle_data['player1'].hits_received}/{battle_data['player1'].max_health}\n"
                f"가한 피해: {battle_data['player1'].hits_dealt}\n"
                f"평균 공격력: {battle_data['player1'].attack_sum / max(1, battle_data['player1'].total_attack_rolls):.1f}\n"
                f"평균 회피력: {battle_data['player1'].defend_sum / max(1, battle_data['player1'].total_defend_rolls):.1f}",
            inline=True
        )
        
        embed.add_field(
            name=f"{battle_data['player2'].real_name}의 전투 기록",
            value=f"받은 피해: {battle_data['player2'].hits_received}/{battle_data['player2'].max_health}\n"
                f"가한 피해: {battle_data['player2'].hits_dealt}\n"
                f"평균 공격력: {battle_data['player2'].attack_sum / max(1, battle_data['player2'].total_attack_rolls):.1f}\n"
                f"평균 회피력: {battle_data['player2'].defend_sum / max(1, battle_data['player2'].total_defend_rolls):.1f}",
            inline=True
        )
        
        # 전투 시간
        battle_duration = datetime.now() - battle_data["start_time"]
        embed.add_field(
            name="전투 정보",
            value=f"총 라운드: {battle_data['round']}라운드\n"
                  f"전투 시간: {battle_duration.seconds // 60}분 {battle_duration.seconds % 60}초\n"
                  f"선공: {battle_data['player1'].real_name if battle_data['player1'].is_first_attacker else battle_data['player2'].real_name}",
            inline=False
        )
        
        # 전투 기록 표시
        embed.add_field(
            name="📊 전투 기록",
            value=self._get_battle_history_text(),
            inline=False
        )
        
        # 새로운 메시지로 결과 전송
        await battle_data["message"].channel.send(embed=embed)
        
        # 원래 메시지는 간단하게 업데이트
        simple_embed = discord.Embed(
            title="전투 종료",
            description=f"{winner.real_name} 승리!",
            color=discord.Color.blue()
        )
        
        try:
            await battle_data["message"].edit(embed=simple_embed, view=None)
        except discord.errors.HTTPException:
            # 토큰 만료 시 무시
            pass
        
        # 정리
        del self.active_battles[channel_id]
    
    def _get_battle_history_text(self) -> str:
        """전투 기록 텍스트 생성"""
        if not self.battle_history:
            return "아직 전투 기록이 없습니다."
        
        lines = []
        current_time = datetime.now()
        
        # 최근 5개의 전투 기록만 표시
        for i, record in enumerate(list(self.battle_history)[-5:]):
            if record.is_active:
                # 진행 중인 전투
                duration = current_time - record.start_time
                lines.append(
                    f"⚔️ **진행중** {record.player1_name} vs {record.player2_name} "
                    f"(R{record.rounds}, {duration.seconds // 60}분)"
                )
            else:
                # 종료된 전투
                if record.winner_name:
                    lines.append(
                        f"✅ {record.winner_name} > {record.loser_name} "
                        f"(R{record.rounds})"
                    )
                else:
                    # 거절된 전투
                    lines.append(
                        f"❌ {record.player1_name} vs {record.player2_name} (거절)"
                    )
        
        return "\n".join(lines) if lines else "전투 기록이 없습니다."
    
    def _create_battle_embed(self, channel_id: int) -> discord.Embed:
        """전투 상태 임베드 생성"""
        battle_data = self.active_battles[channel_id]
        
        if battle_data["phase"] == BattlePhase.INIT_ROLL:
            embed = discord.Embed(
                title="🎲 선공 결정 중",
                description="양 플레이어가 다이스를 굴려 선공을 정합니다.",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title=f"⚔️ 전투 진행 중 - 라운드 {battle_data['round']}",
                description=f"🗡️ **공격자**: {battle_data['current_attacker'].real_name}\n"
                           f"🛡️ **방어자**: {battle_data['current_defender'].real_name}",
                color=discord.Color.red()
            )
        
        # 체력 바
        p1_health = battle_data["player1"].max_health - battle_data["player1"].hits_received
        p2_health = battle_data["player2"].max_health - battle_data["player2"].hits_received
        
        p1_bar = self._get_health_bar(p1_health, battle_data["player1"].max_health)
        p2_bar = self._get_health_bar(p2_health, battle_data["player2"].max_health)
        
        embed.add_field(
            name=f"{battle_data['player1'].real_name}",
            value=f"{p1_bar}\n체력: {p1_health}/{battle_data['player1'].max_health}",
            inline=True
        )
        
        embed.add_field(
            name=f"{battle_data['player2'].real_name}",
            value=f"{p2_bar}\n체력: {p2_health}/{battle_data['player2'].max_health}",
            inline=True
        )
        
        # 현재 단계 설명
        if battle_data["phase"] == BattlePhase.ATTACK_ROLL:
            embed.add_field(
                name="현재 상황",
                value=f"🗡️ {battle_data['current_attacker'].real_name}님의 공격 차례\n"
                      f"🛡️ {battle_data['current_defender'].real_name}님의 회피 차례\n"
                      f"양쪽 모두 `/주사위`를 굴려주세요!",
                inline=False
            )
        
        return embed

# UI 컴포넌트들
class BattleStartView(discord.ui.View):
    def __init__(self, game: BattleGame, channel_id: int, with_sync: bool = False):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.with_sync = with_sync
    
    @discord.ui.button(label="체력 동기화하여 시작", style=discord.ButtonStyle.primary, emoji="💚")
    async def sync_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.with_sync:
            battle_data = self.game.active_battles[self.channel_id]
            battle_data["health_sync"] = True
            
            # 체력 동기화
            battle_data["player1"].max_health = calculate_battle_health(battle_data["player1"].real_health)
            battle_data["player2"].max_health = calculate_battle_health(battle_data["player2"].real_health)
            
            # interaction 응답
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="전투 시작",
                    description="체력 동기화하여 전투를 시작합니다...",
                    color=discord.Color.blue()
                ),
                view=None
            )
            
            # 새로운 일반 메시지 생성
            new_message = await interaction.followup.send(
                embed=discord.Embed(
                    title="⚔️ 전투 진행 중",
                    description="전투가 시작되었습니다!",
                    color=discord.Color.blue()
                )
            )
            battle_data["message"] = new_message
            
            # from_sync=True로 호출
            await self.game.accept_battle(self.channel_id, from_sync=True)
        
    @discord.ui.button(label="기본으로 시작", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def normal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        battle_data = self.game.active_battles[self.channel_id]
        battle_data["health_sync"] = False
        
        # interaction 응답
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="전투 시작",
                description="기본 체력으로 전투를 시작합니다...",
                color=discord.Color.blue()
            ),
            view=None
        )
        
        # 새로운 일반 메시지 생성
        new_message = await interaction.followup.send(
            embed=discord.Embed(
                title="⚔️ 전투 진행 중",
                description="전투가 시작되었습니다!",
                color=discord.Color.blue()
            )
        )
        battle_data["message"] = new_message
        
        # from_sync=True로 호출
        await self.game.accept_battle(self.channel_id, from_sync=True)
    
    @discord.ui.button(label="전투 거절", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.game.decline_battle(interaction, self.channel_id)

# 전역 게임 인스턴스
battle_game = BattleGame()

def get_battle_game():
    return battle_game