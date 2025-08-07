# battle_admin.py - Admin 전용 전투 시스템 (팀 전투 지원)
"""
Admin 전용 전투 시스템
- 1대1, 1대다, 팀 대 팀 전투 지원
- 커스텀 몬스터 이름 지원
- 체력 동기화 옵션
- 턴제 전투 시스템
"""

import discord
from discord import app_commands
import asyncio
import random
import logging
import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
from battle_utils import extract_health_from_nickname, calculate_battle_health, update_nickname_health

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== 열거형 정의 =====
class BattlePhase(Enum):
    """전투 진행 단계"""
    WAITING = "대기중"        # 전투 수락 대기
    INIT_ROLL = "선공 결정"   # 선공 결정 다이스
    COMBAT = "전투 진행"      # 실제 전투
    FINISHED = "전투 종료"    # 전투 완료

class TurnPhase(Enum):
    """턴 내 세부 단계"""
    USER_ATTACK = "유저 공격"
    ADMIN_DEFEND = "Admin 회피"
    ADMIN_ATTACK = "Admin 공격"
    USER_DEFEND = "유저 회피"
    TEAM_BATTLE = "팀 전투"

# ===== 데이터 클래스 =====
@dataclass
class BattlePlayer:
    """
    전투 참가자 정보
    """
    user: discord.Member
    real_name: str
    hits_received: int = 0
    hits_dealt: int = 0
    max_health: int = 10
    real_health: int = 100
    is_eliminated: bool = False
    init_roll: int = 0
    skip_turn: bool = False
    has_acted_this_turn: bool = False
    team: str = "A"  # 팀 정보 ("A" 또는 "B")
    current_target: Optional[int] = None  # 현재 타겟 ID

@dataclass
class DiceResult:
    """
    다이스 결과 정보
    """
    player_name: str
    dice_value: int
    user_id: Optional[int] = None

@dataclass
class MultiUserBattle:
    """
    다중 유저 전투 정보 (팀 전투 지원)
    """
    battle_name: str
    channel_id: int
    admin: Optional[BattlePlayer]  # 1대다 전투용 (팀 전투시 None)
    users: List[BattlePlayer]  # 모든 유저
    phase: BattlePhase
    current_round: int
    current_turn_index: int
    turn_phase: TurnPhase
    message: Optional[discord.Message]
    battle_log: List[str]
    is_active: bool = True
    pending_dice: Dict = field(default_factory=dict)
    last_admin_attack: Optional[int] = None
    users_acted_this_round: int = 0
    health_sync: bool = False
    monster_name: str = "시스템"
    is_team_battle: bool = False  # 팀 전투 여부
    team_a_users: List[BattlePlayer] = field(default_factory=list)  # 팀 A
    team_b_users: List[BattlePlayer] = field(default_factory=list)  # 팀 B
    current_attackers: List[int] = field(default_factory=list)  # 현재 공격자들
    focused_attack: Optional[Dict] = None  # 집중공격 정보 추가
    admin_actions_remaining: int = 1  # Admin 행동 횟수 추가

# ===== 메인 관리자 클래스 =====
class AdminBattleManager:
    """
    Admin 전투 시스템 관리자
    """
    
    def __init__(self):
        """관리자 초기화"""
        self.active_battles = {}  # channel_id: MultiUserBattle
        self.battle_history = deque(maxlen=50)
        self.pending_battles = {}  # 대기 중인 전투
        
        # 알려진 캐릭터 이름 목록
        self.known_names = [
            "system", "시스템", "admin", "운영자", "GM",
            "몬스터", "보스", "적", "Enemy", "Boss",
            "드래곤", "Dragon", "슬라임", "Slime",
            "고블린", "Goblin", "오크", "Orc",
            "마왕", "Demon Lord", "용사", "Hero"
        ]




    # ===== 유틸리티 메서드 =====
    def extract_real_name(self, display_name: str) -> str:
        """닉네임에서 실제 캐릭터 이름 추출"""
        # 알려진 캐릭터 이름 목록
        known_names = {
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
            "이터니티", "커피머신", "system | 시스템", "system", "시스템"
        }
        
        # 공백과 언더스코어를 제거하여 정규화
        normalized = display_name.replace(" ", "").replace("_", "")
        
        # 알려진 이름과 매칭 시도
        for known_name in known_names:
            normalized_known = known_name.replace(" ", "").replace("_", "")
            if normalized_known in normalized:
                return known_name
        
        # 체력 정보 제거 시도
        cleaned = re.sub(r'[⚡💚💛🧡❤️💔].*$', '', display_name).strip()
        return cleaned if cleaned else display_name
    
    # ===== Admin 전투 명령어 처리 =====
    async def handle_admin_battle_command(self, message: discord.Message):
        """!전투 명령어 처리 (1대1, 1대다, 팀전)"""
        if message.author.display_name not in ["system | 시스템", "system", "시스템"]:
            return
        
        content = message.content.strip()
        
        # 팀 전투 체크 (vs가 포함되어 있는 경우)
        if " vs " in content:
            await self._parse_team_battle(message)
            return
        
        # 1대1 또는 1대다 전투
        parts = content.split()
        
        if len(parts) < 2:
            await message.channel.send("사용법: `!전투 @유저1 [@유저2 ...] [체력1 체력2 ...] [이름]`")
            return
        
        users = []
        health_values = []
        monster_name = "시스템"
        
        # 파싱
        for part in parts[1:]:
            if part.startswith('<@') and part.endswith('>'):
                # 유저 멘션
                user_id = int(part[2:-1].replace('!', ''))
                member = message.guild.get_member(user_id)
                if member and member != message.author:
                    users.append(member)
            elif part.isdigit():
                # 체력값
                health_values.append(int(part))
            else:
                # 몬스터 이름
                monster_name = part
        
        if not users:
            await message.channel.send("최소 한 명의 상대를 지정해야 합니다!")
            return
        
        # 단일 유저 전투
        if len(users) == 1:
            await self._start_single_battle(message, users[0], 
                                         health_values[0] if health_values else 10,
                                         monster_name)
        else:
            # 다중 유저 전투
            view = MultiBattleSyncView(self, message, users, 
                                     health_values[0] if health_values else 10,
                                     monster_name)
            
            embed = discord.Embed(
                title="⚔️ 전투 준비",
                description=f"{monster_name} vs {', '.join([u.display_name for u in users])}\n\n"
                           f"체력 동기화 옵션을 선택해주세요.",
                color=discord.Color.red()
            )
            
            if health_values:
                embed.add_field(
                    name="설정된 전투 체력",
                    value="\n".join([f"{users[i].display_name}: {health_values[i] if i < len(health_values) else 10}HP" 
                                   for i in range(len(users))]),
                    inline=False
                )
            
            await message.channel.send(embed=embed, view=view)
    
    async def _parse_team_battle(self, message: discord.Message):
        """팀 전투 파싱 및 시작"""
        content = message.content.strip()
        
        # !전투 팀A vs 팀B [체력들...] 형식
        main_parts = content.split(" vs ")
        if len(main_parts) != 2:
            await message.channel.send("팀 전투 형식: `!전투 @유저1 @유저2 vs @유저3 @유저4 [체력1 체력2 ...]`")
            return
        
        # 왼쪽 파트 처리 (팀 A)
        left_parts = main_parts[0].split()
        team_a_users = []
        team_a_has_admin = False
        
        for part in left_parts[1:]:  # !전투 제외
            if part.startswith('<@') and part.endswith('>'):
                user_id = int(part[2:-1].replace('!', ''))
                member = message.guild.get_member(user_id)
                if member:
                    if member == message.author:
                        team_a_has_admin = True
                    else:
                        team_a_users.append(member)
        
        # 오른쪽 파트 처리 (팀 B와 체력값)
        right_parts = main_parts[1].split()
        team_b_users = []
        team_b_has_admin = False
        health_values = []
        
        for part in right_parts:
            if part.startswith('<@') and part.endswith('>'):
                user_id = int(part[2:-1].replace('!', ''))
                member = message.guild.get_member(user_id)
                if member:
                    if member == message.author:
                        team_b_has_admin = True
                    else:
                        team_b_users.append(member)
            elif part.isdigit():
                health_values.append(int(part))
        
        # 유효성 검사
        if not team_a_users and not team_a_has_admin:
            await message.channel.send("팀 A에 최소 한 명이 있어야 합니다!")
            return
        
        if not team_b_users and not team_b_has_admin:
            await message.channel.send("팀 B에 최소 한 명이 있어야 합니다!")
            return
        
        # Admin이 한 팀에만 있는 경우
        if team_a_has_admin or team_b_has_admin:
            view = TeamBattleWithAdminSyncView(
                self, message, team_a_users, team_b_users, health_values,
                team_a_has_admin, team_b_has_admin
            )
            
            team_a_names = []
            if team_a_has_admin:
                team_a_names.append("시스템")
            team_a_names.extend([u.display_name for u in team_a_users])
            
            team_b_names = []
            if team_b_has_admin:
                team_b_names.append("시스템")
            team_b_names.extend([u.display_name for u in team_b_users])
            
            embed = discord.Embed(
                title="⚔️ 팀 전투 준비",
                description=f"**팀 A**: {', '.join(team_a_names)}\n"
                           f"**팀 B**: {', '.join(team_b_names)}\n\n"
                           f"체력 동기화 옵션을 선택해주세요.",
                color=discord.Color.red()
            )
            
            if health_values:
                all_users = team_a_users + team_b_users
                embed.add_field(
                    name="설정된 전투 체력",
                    value="\n".join([f"{all_users[i].display_name if i < len(all_users) else '시스템'}: "
                                   f"{health_values[i] if i < len(health_values) else 10}HP" 
                                   for i in range(len(all_users) + (1 if team_a_has_admin or team_b_has_admin else 0))]),
                    inline=False
                )
            
            await message.channel.send(embed=embed, view=view)
        else:
            # 일반 팀 전투 (Admin 없음)
            view = TeamBattleSyncView(self, message, team_a_users, team_b_users, health_values)
            
            embed = discord.Embed(
                title="⚔️ 팀 전투 준비",
                description=f"**팀 A**: {', '.join([u.display_name for u in team_a_users])}\n"
                           f"**팀 B**: {', '.join([u.display_name for u in team_b_users])}\n\n"
                           f"체력 동기화 옵션을 선택해주세요.",
                color=discord.Color.red()
            )
            
            if health_values:
                all_users = team_a_users + team_b_users
                embed.add_field(
                    name="설정된 전투 체력",
                    value="\n".join([f"{all_users[i].display_name}: {health_values[i] if i < len(health_values) else 10}HP" 
                                   for i in range(len(all_users))]),
                    inline=False
                )
            
            await message.channel.send(embed=embed, view=view)
    
    async def _start_single_battle(self, message: discord.Message, opponent: discord.Member, 
                                 health: int, monster_name: str):
        """1대1 전투 시작"""
        channel_id = message.channel.id
        
        if channel_id in self.active_battles:
            await message.channel.send("이미 진행 중인 전투가 있습니다!")
            return
        
        admin_real_health = extract_health_from_nickname(message.author.display_name) or 100
        opponent_real_health = extract_health_from_nickname(opponent.display_name) or 100
        
        admin_player = BattlePlayer(
            user=message.author,
            real_name=monster_name,
            max_health=health,
            real_health=admin_real_health
        )
        
        opponent_player = BattlePlayer(
            user=opponent,
            real_name=self.extract_real_name(opponent.display_name),
            max_health=10,
            real_health=opponent_real_health
        )
        
        battle = MultiUserBattle(
            battle_name=f"{monster_name} vs {opponent_player.real_name}",
            channel_id=channel_id,
            admin=admin_player,
            users=[opponent_player],
            phase=BattlePhase.WAITING,
            current_round=1,
            current_turn_index=0,
            turn_phase=TurnPhase.USER_ATTACK,
            message=None,
            battle_log=[],
            monster_name=monster_name
        )
        
        self.active_battles[channel_id] = battle
        
        # 체력 동기화 옵션 제공
        view = BattleStartWithSyncView(self, channel_id, opponent)
        
        embed = discord.Embed(
            title="⚔️ 전투 도전!",
            description=f"{monster_name}이(가) {opponent.mention}에게 전투를 신청했습니다!\n\n"
                       f"체력 동기화 옵션을 선택해주세요.",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="전투 체력",
            value=f"{monster_name}: {health}HP\n"
                  f"{opponent_player.real_name}: 10HP (기본)",
            inline=False
        )
        
        await message.channel.send(embed=embed, view=view)

    async def handle_turn_skip(self, message: discord.Message):
        """
        턴 넘김 처리 (!턴넘김 명령어)
        
        Args:
            message: 사용자 메시지
        """
        channel_id = message.channel.id
        
        if channel_id not in self.active_battles:
            return
        
        battle = self.active_battles[channel_id]
        
        # 대기 중인 플레이어인지 확인
        if battle.pending_dice and message.author.id in battle.pending_dice["waiting_for"]:
            battle.pending_dice["waiting_for"].remove(message.author.id)
            battle.pending_dice["results"][message.author.id] = 0
            
            # 플레이어 이름 찾기
            player_name = battle.monster_name if message.author.id == battle.admin.user.id else None
            if not player_name:
                for player in battle.users:
                    if player.user.id == message.author.id:
                        player_name = player.real_name
                        player.skip_turn = True
                        break
            
            await message.channel.send(f"⏭️ {player_name}님이 턴을 넘겼습니다.")
            
            # 모두 행동했는지 확인
            if not battle.pending_dice["waiting_for"]:
                if battle.pending_dice["phase"] == "init":
                    await self._process_init_results(channel_id)
                else:
                    await self._process_combat_results(channel_id)

    # battle_admin.py의 AdminBattleManager 클래스에 추가

    def parse_dice_message(self, message_content: str) -> Optional[DiceResult]:
        """
        다이스 봇 메시지를 파싱하여 결과 추출
        """
        # 여러 공백을 하나로 정규화
        normalized_content = ' '.join(message_content.split())
        
        # 다이스 메시지 패턴: `플레이어명`님이 ... 주사위를 굴려 ... **숫자** ... 나왔습니다
        pattern = r"`([^`]+)`님이.*?주사위를\s*굴\s*려.*?\*\*(\d+)\*\*.*?나왔습니다"
        match = re.search(pattern, normalized_content)
        
        if match:
            player_name = match.group(1).strip()
            dice_value = int(match.group(2))
            return DiceResult(player_name=player_name, dice_value=dice_value)
        
        return None

    async def handle_dice_roll(self, user_id: int, channel_id: int, dice_value: int):
        """주사위 결과를 직접 처리"""
        print(f"[DEBUG] handle_dice_roll called - User: {user_id}, Channel: {channel_id}, Value: {dice_value}")
        
        battle = self.active_battles.get(channel_id)
        if not battle or not battle.pending_dice:
            print(f"[DEBUG] No battle or pending dice for channel {channel_id}")
            return
        
        print(f"[DEBUG] Current phase: {battle.pending_dice.get('phase')}")
        print(f"[DEBUG] Waiting for: {battle.pending_dice.get('waiting_for')}")
        
        # 대기 중인 플레이어인지 확인
        if user_id not in battle.pending_dice["waiting_for"]:
            print(f"[DEBUG] User {user_id} not in waiting list")
            return
        
        # 결과 저장
        battle.pending_dice["results"][user_id] = dice_value
        battle.pending_dice["waiting_for"].remove(user_id)
        
        print(f"[DEBUG] Results so far: {battle.pending_dice['results']}")
        print(f"[DEBUG] Still waiting for: {battle.pending_dice['waiting_for']}")
        
        # 모두 굴렸는지 확인
        if not battle.pending_dice["waiting_for"]:
            print(f"[DEBUG] All dice rolled, processing results for phase: {battle.pending_dice['phase']}")
            if battle.pending_dice["phase"] == "init":
                await self._process_init_results(channel_id)
            else:
                await self._process_combat_results(channel_id)

    async def process_dice_message(self, message: discord.Message):
        """다이스 봇 메시지 처리"""
        channel_id = message.channel.id
        
        print(f"[DEBUG] process_dice_message called for channel {channel_id}")
        print(f"[DEBUG] Message content: {message.content}")
        
        # 활성 전투 확인
        if channel_id not in self.active_battles:
            print(f"[DEBUG] No active battle in channel {channel_id}")
            return
        
        battle = self.active_battles[channel_id]
        
        # pending_dice 확인
        if not battle.pending_dice:
            print(f"[DEBUG] No pending dice in battle")
            return
        
        print(f"[DEBUG] Current pending dice: {battle.pending_dice}")
        
        dice_result = self.parse_dice_message(message.content)
        
        if not dice_result:
            print(f"[DEBUG] Failed to parse dice message")
            return
        
        print(f"[DEBUG] Parsed dice result: {dice_result.player_name} rolled {dice_result.dice_value}")
        
        # 실제 이름으로 변환
        dice_real_name = self.extract_real_name(dice_result.player_name)
        print(f"[DEBUG] Real name: {dice_real_name}, Monster name: {battle.monster_name}")
        
        # 플레이어 매칭
        user_id = None
        if dice_real_name == battle.monster_name or dice_real_name in ["system | 시스템", "system", "시스템"]:
            if battle.admin:  # 팀 전투가 아닌 경우에만
                user_id = battle.admin.user.id
                print(f"[DEBUG] Matched admin: {user_id}")
        else:
            for player in battle.users:
                if dice_real_name == player.real_name:
                    user_id = player.user.id
                    print(f"[DEBUG] Matched user: {player.real_name} -> {user_id}")
                    break
        
        if not user_id:
            print(f"[DEBUG] Could not match user for {dice_real_name}")
            return
        
        # 대기 중인 플레이어인지 확인
        if user_id in battle.pending_dice["waiting_for"]:
            print(f"[DEBUG] User {user_id} is in waiting list, processing dice")
            await self.handle_dice_roll(user_id, channel_id, dice_result.dice_value)
        else:
            print(f"[DEBUG] User {user_id} is NOT in waiting list")

    async def _process_init_results(self, channel_id: int):
        """
        선공 결정 결과 처리
        """
        battle = self.active_battles[channel_id]
        results = battle.pending_dice["results"]
        
        # 각 플레이어의 초기 다이스 저장
        if battle.admin:
            battle.admin.init_roll = results.get(battle.admin.user.id, 0)
        
        for player in battle.users:
            player.init_roll = results.get(player.user.id, 0)
        
        # 유저들을 다이스 값 기준으로 정렬 (높은 순)
        sorted_users = sorted(battle.users, key=lambda p: p.init_roll, reverse=True)
        battle.users = sorted_users
        
        # 결과 메시지 생성
        init_results = []
        if battle.admin:
            init_results.append(f"{battle.monster_name}: {battle.admin.init_roll}")
        for player in battle.users:
            init_results.append(f"{player.real_name}: {player.init_roll}")
        
        embed = discord.Embed(
            title=f"🎲 선공 결정 완료",
            description=f"**결과:**\n" + "\n".join(init_results) + "\n\n"
                    f"**턴 순서:** {' → '.join([p.real_name for p in battle.users])}",
            color=discord.Color.green()
        )
        
        if battle.admin:
            embed.description += f" → {battle.monster_name}"
        
        await battle.message.channel.send(embed=embed)
        
        # 전투 단계로 전환
        battle.phase = BattlePhase.COMBAT
        battle.pending_dice = None
        battle.current_round = 1
        await asyncio.sleep(2)
        await self._start_next_turn(channel_id)

    async def accept_battle_with_sync(self, interaction: discord.Interaction, 
                                    channel_id: int, sync: bool):
        """전투 수락 (체력 동기화 옵션 포함)"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        battle.health_sync = sync
        
        if sync:
            # 체력 동기화
            for player in battle.users:
                player.max_health = calculate_battle_health(player.real_health)
            
            if battle.admin:
                battle.admin.max_health = calculate_battle_health(battle.admin.real_health)
        
        await self._initialize_battle(channel_id)
    
    async def start_multi_battle(self, message: discord.Message, users: List[discord.Member], 
                            admin_health: int, sync_health: bool, monster_name: str):
        """다중 유저 전투 시작"""
        channel_id = message.channel.id
        
        if channel_id in self.active_battles:
            await message.channel.send("이미 진행 중인 전투가 있습니다!")
            return
        
        # Admin 플레이어 생성
        admin_real_health = extract_health_from_nickname(message.author.display_name) or 100
        
        # 수정된 부분: 체력 동기화 시에도 설정된 admin_health를 우선 사용
        if sync_health:
            # admin_health가 명시적으로 설정되었다면 그 값을 사용
            if admin_health != 10:  # 기본값이 아닌 경우
                admin_battle_health = admin_health
                logger.debug(f"Admin 체력 동기화: 설정된 체력 {admin_health} 사용")
            else:
                # 기본값인 경우에만 calculate_battle_health 사용
                admin_battle_health = calculate_battle_health(admin_real_health)
                logger.debug(f"Admin 체력 동기화: 계산된 체력 {admin_battle_health} 사용 (실제 체력: {admin_real_health})")
        else:
            admin_battle_health = admin_health
            logger.debug(f"Admin 체력 동기화 안함: 설정된 체력 {admin_health} 사용")
        
        admin_player = BattlePlayer(
            user=message.author,
            real_name=monster_name,
            max_health=admin_battle_health,
            real_health=admin_real_health
        )
        
        # 유저 플레이어들 생성
        user_players = []
        for user in users:
            real_health = extract_health_from_nickname(user.display_name) or 100
            battle_health = calculate_battle_health(real_health) if sync_health else 10
            
            logger.debug(f"유저 {user.display_name} - 실제 체력: {real_health}, 전투 체력: {battle_health}")
            
            player = BattlePlayer(
                user=user,
                real_name=self.extract_real_name(user.display_name),
                max_health=battle_health,
                real_health=real_health
            )
            user_players.append(player)
        
        battle = MultiUserBattle(
            battle_name=f"{monster_name} vs {len(users)}명",
            channel_id=channel_id,
            admin=admin_player,
            users=user_players,
            phase=BattlePhase.INIT_ROLL,
            current_round=1,
            current_turn_index=0,
            turn_phase=TurnPhase.USER_ATTACK,
            message=None,
            battle_log=[],
            health_sync=sync_health,
            monster_name=monster_name
        )
        
        logger.info(f"전투 시작 - Admin 체력: {admin_battle_health}, 체력 동기화: {sync_health}")
        
        self.active_battles[channel_id] = battle
        
        # 선공 결정
        all_players = [admin_player] + user_players
        
        embed = discord.Embed(
            title="⚔️ 전투 시작!",
            description=f"**{monster_name}** vs **{', '.join([p.real_name for p in user_players])}**\n\n"
                       f"선공 결정을 위해 모두 주사위를 굴려주세요!",
            color=discord.Color.red()
        )
        
        battle.message = await message.channel.send(embed=embed)
        
        battle.pending_dice = {
            "phase": "init",
            "waiting_for": [p.user.id for p in all_players],
            "results": {}
        }
    
    async def start_team_battle(self, message: discord.Message,
                              team_a_users: List[discord.Member],
                              team_b_users: List[discord.Member],
                              health_values: List[int],
                              sync_health: bool):
        """일반 팀 전투 시작 (Admin 없음)"""
        channel_id = message.channel.id
        
        if channel_id in self.active_battles:
            await message.channel.send("이미 진행 중인 전투가 있습니다!")
            return
        
        all_players = []
        team_a_players = []
        team_b_players = []
        
        # 팀 A 플레이어 생성
        for i, user in enumerate(team_a_users):
            real_health = extract_health_from_nickname(user.display_name) or 100
            if sync_health:
                battle_health = calculate_battle_health(real_health)
            else:
                battle_health = health_values[i] if i < len(health_values) else 10
            
            player = BattlePlayer(
                user=user,
                real_name=self.extract_real_name(user.display_name),
                max_health=battle_health,
                real_health=real_health,
                team="A"
            )
            team_a_players.append(player)
            all_players.append(player)
        
        # 팀 B 플레이어 생성
        offset = len(team_a_users)
        for i, user in enumerate(team_b_users):
            real_health = extract_health_from_nickname(user.display_name) or 100
            if sync_health:
                battle_health = calculate_battle_health(real_health)
            else:
                idx = offset + i
                battle_health = health_values[idx] if idx < len(health_values) else 10
            
            player = BattlePlayer(
                user=user,
                real_name=self.extract_real_name(user.display_name),
                max_health=battle_health,
                real_health=real_health,
                team="B"
            )
            team_b_players.append(player)
            all_players.append(player)
        
        battle = MultiUserBattle(
            battle_name=f"팀 A vs 팀 B",
            channel_id=channel_id,
            admin=None,  # 팀 전투는 Admin 없음
            users=all_players,
            phase=BattlePhase.INIT_ROLL,
            current_round=1,
            current_turn_index=0,
            turn_phase=TurnPhase.TEAM_BATTLE,
            message=None,
            battle_log=[],
            health_sync=sync_health,
            is_team_battle=True,
            team_a_users=team_a_players,
            team_b_users=team_b_players
        )
        
        self.active_battles[channel_id] = battle
        
        # 선공 결정
        embed = discord.Embed(
            title="⚔️ 팀 전투 시작!",
            description=f"**팀 A**: {', '.join([p.real_name for p in team_a_players])}\n"
                       f"**팀 B**: {', '.join([p.real_name for p in team_b_players])}\n\n"
                       f"선공 결정을 위해 모두 주사위를 굴려주세요!",
            color=discord.Color.red()
        )
        
        battle.message = await message.channel.send(embed=embed)
        
        battle.pending_dice = {
            "phase": "init",
            "waiting_for": [p.user.id for p in all_players],
            "results": {}
        }
    
    async def start_team_battle_with_admin(self, message: discord.Message,
                                         team_a_users: List[discord.Member],
                                         team_b_users: List[discord.Member],
                                         health_values: List[int],
                                         sync_health: bool,
                                         team_a_has_admin: bool,
                                         team_b_has_admin: bool):
        """Admin을 포함한 팀 전투 실제 시작"""
        channel_id = message.channel.id
        
        if channel_id in self.active_battles:
            await message.channel.send("이미 진행 중인 전투가 있습니다!")
            return
        
        all_players = []
        team_a_players = []
        team_b_players = []
        user_index = 0
        
        # 팀 A 플레이어 생성
        for user in team_a_users:
            real_health = extract_health_from_nickname(user.display_name) or 100
            if sync_health:
                battle_health = calculate_battle_health(real_health)
            else:
                battle_health = health_values[user_index] if user_index < len(health_values) else 10
            
            player = BattlePlayer(
                user=user,
                real_name=self.extract_real_name(user.display_name),
                max_health=battle_health,
                real_health=real_health,
                team="A"
            )
            team_a_players.append(player)
            all_players.append(player)
            user_index += 1
        
        # 팀 A에 Admin 추가
        if team_a_has_admin:
            battle_health = health_values[user_index] if user_index < len(health_values) else 10
            admin_player = BattlePlayer(
                user=message.author,
                real_name="시스템",
                max_health=battle_health,
                real_health=100,
                team="A"
            )
            team_a_players.append(admin_player)
            all_players.append(admin_player)
            user_index += 1
        
        # 팀 B 플레이어 생성
        for user in team_b_users:
            real_health = extract_health_from_nickname(user.display_name) or 100
            if sync_health:
                battle_health = calculate_battle_health(real_health)
            else:
                battle_health = health_values[user_index] if user_index < len(health_values) else 10
            
            player = BattlePlayer(
                user=user,
                real_name=self.extract_real_name(user.display_name),
                max_health=battle_health,
                real_health=real_health,
                team="B"
            )
            team_b_players.append(player)
            all_players.append(player)
            user_index += 1
        
        # 팀 B에 Admin 추가
        if team_b_has_admin:
            battle_health = health_values[user_index] if user_index < len(health_values) else 10
            admin_player = BattlePlayer(
                user=message.author,
                real_name="시스템",
                max_health=battle_health,
                real_health=100,
                team="B"
            )
            team_b_players.append(admin_player)
            all_players.append(admin_player)
        
        battle = MultiUserBattle(
            battle_name=f"팀 A vs 팀 B",
            channel_id=channel_id,
            admin=None,  # 팀 전투는 admin 필드 사용 안함
            users=all_players,
            phase=BattlePhase.INIT_ROLL,
            current_round=1,
            current_turn_index=0,
            turn_phase=TurnPhase.TEAM_BATTLE,
            message=None,
            battle_log=[],
            health_sync=sync_health,
            is_team_battle=True,
            team_a_users=team_a_players,
            team_b_users=team_b_players
        )
        
        self.active_battles[channel_id] = battle
        
        # 선공 결정
        embed = discord.Embed(
            title="⚔️ 팀 전투 시작!",
            description=f"**팀 A**: {', '.join([p.real_name for p in team_a_players])}\n"
                       f"**팀 B**: {', '.join([p.real_name for p in team_b_players])}\n\n"
                       f"선공 결정을 위해 모두 주사위를 굴려주세요!",
            color=discord.Color.red()
        )
        
        battle.message = await message.channel.send(embed=embed)
        
        battle.pending_dice = {
            "phase": "init",
            "waiting_for": [p.user.id for p in all_players],
            "results": {}
        }
    
    # ===== 전투 진행 메서드 =====
    async def _initialize_battle(self, channel_id: int):
        """전투 초기화 및 시작"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        battle.phase = BattlePhase.INIT_ROLL
        
        # 모든 참가자
        all_players = [battle.admin] + battle.users if battle.admin else battle.users
        
        embed = discord.Embed(
            title="⚔️ 전투 시작!",
            description=f"**{battle.battle_name}**\n\n"
                       f"선공 결정을 위해 모두 주사위를 굴려주세요!",
            color=discord.Color.red()
        )
        
        health_info = []
        for player in all_players:
            health_info.append(f"{player.real_name}: {player.max_health}HP")
        
        embed.add_field(
            name="전투 체력",
            value="\n".join(health_info),
            inline=False
        )
        
        if battle.health_sync:
            embed.add_field(
                name="체력 동기화",
                value="✅ 활성화됨",
                inline=False
            )
        
        try:
            await battle.message.edit(embed=embed)
        except:
            battle.message = await battle.message.channel.send(embed=embed)
        
        battle.pending_dice = {
            "phase": "init",
            "waiting_for": [p.user.id for p in all_players],
            "results": {}
        }
    
    async def _process_dice_phase(self, channel_id: int):
        """주사위 단계 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        phase = battle.pending_dice["phase"]
        results = battle.pending_dice["results"]
        
        if phase == "init":
            # 선공 결정
            all_players = []
            if battle.admin:
                all_players.append((battle.admin, results.get(battle.admin.user.id, 0)))
            for player in battle.users:
                all_players.append((player, results.get(player.user.id, 0)))
            
            # 주사위 값으로 정렬
            all_players.sort(key=lambda x: x[1], reverse=True)
            
            # 턴 순서 설정
            battle.users = [p[0] for p in all_players if p[0] != battle.admin]
            
            result_msg = "🎲 **선공 결정 결과**\n"
            for player, roll in all_players:
                result_msg += f"{player.real_name}: {roll}\n"
            
            await battle.message.channel.send(result_msg)
            
            battle.phase = BattlePhase.COMBAT
            battle.pending_dice = None
            
            await asyncio.sleep(1)
            await self._start_next_turn(channel_id)
        else:
            # 전투 결과 처리
            await self._process_combat_results(channel_id)
    
    async def _start_next_turn(self, channel_id: int):
        """다음 턴 시작"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        # 팀 전투인 경우
        if battle.is_team_battle:
            await self._start_team_turn(channel_id)
            return
        
        # 1대다 전투
        active_users = [p for p in battle.users if not p.is_eliminated]
        
        if not active_users or battle.admin.hits_received >= battle.admin.max_health:
            await self._end_battle(channel_id)
            return
        
        embed = self._create_battle_status_embed(battle)
        
        try:
            await battle.message.edit(embed=embed)
        except discord.errors.HTTPException as e:
            if e.code == 50027:
                channel = battle.message.channel
                await battle.message.delete()
                battle.message = await channel.send(embed=embed)
            else:
                raise
        
        health_info = self._create_health_info(battle)
        
        if battle.turn_phase == TurnPhase.USER_ATTACK:
            while battle.current_turn_index < len(battle.users) and battle.users[battle.current_turn_index].is_eliminated:
                battle.current_turn_index += 1
            
            if battle.current_turn_index >= len(battle.users):
                battle.turn_phase = TurnPhase.ADMIN_ATTACK
                await self._start_next_turn(channel_id)
                return
            
            current_user = battle.users[battle.current_turn_index]
            
            await battle.message.channel.send(
                f"⚔️ **라운드 {battle.current_round} - {current_user.real_name}의 공격**\n"
                f"{health_info}\n\n"
                f"🗡️ {current_user.real_name}님, 공격 다이스를 굴려주세요!\n"
                f"🛡️ {battle.monster_name}님, 회피 다이스를 굴려주세요!"
            )
            
            battle.pending_dice = {
                "phase": "user_attack",
                "waiting_for": [current_user.user.id, battle.admin.user.id],
                "results": {},
                "attacker": current_user.user.id
            }
        
        elif battle.turn_phase == TurnPhase.ADMIN_ATTACK:
            print(f"[DEBUG] Starting admin attack phase")
            print(f"[DEBUG] Active users: {[p.real_name for p in active_users]}")
            print(f"[DEBUG] Admin user ID: {battle.admin.user.id}")
            
            # 메시지 전송 전 상태 확인
            print(f"[DEBUG] Creating pending dice for admin attack")
            await battle.message.channel.send(
                f"⚔️ **라운드 {battle.current_round} - {battle.monster_name}의 반격**\n"
                f"{health_info}\n\n"
                f"🗡️ {battle.monster_name}님, 공격 다이스를 굴려주세요!\n"
                f"🛡️ 모든 유저는 회피 다이스를 굴려주세요!"
            )
            
            waiting_users = [p.user.id for p in active_users]
            battle.pending_dice = {
                "phase": "admin_attack",
                "waiting_for": [battle.admin.user.id] + waiting_users,
                "results": {}
            }
            print(f"[DEBUG] Pending dice created: {battle.pending_dice}")


    async def _start_team_turn(self, channel_id: int):
        """팀 전투 턴 시작"""
        battle = self.active_battles[channel_id]
        
        active_team_a = [p for p in battle.team_a_users if not p.is_eliminated]
        active_team_b = [p for p in battle.team_b_users if not p.is_eliminated]
        
        if not active_team_a or not active_team_b:
            await self._end_team_battle(channel_id)
            return
        
        embed = self._create_battle_status_embed(battle)
        await battle.message.edit(embed=embed)
        
        health_info = self._create_health_info(battle)
        
        # 탈락한 플레이어 건너뛰기
        while battle.current_turn_index < len(battle.users) and battle.users[battle.current_turn_index].is_eliminated:
            battle.current_turn_index += 1
        
        if battle.current_turn_index >= len(battle.users):
            battle.current_round += 1
            battle.current_turn_index = 0
            await self._start_next_turn(channel_id)
            return
        
        current_player = battle.users[battle.current_turn_index]
        
        # 타겟이 설정되어 있는지 확인
        if current_player.current_target is None:
            await battle.message.channel.send(
                f"⚔️ **라운드 {battle.current_round} - {current_player.real_name}의 턴**\n"
                f"{health_info}\n\n"
                f"🎯 {current_player.real_name}님, `!타격 @대상`으로 타겟을 지정해주세요!"
            )
            
            # 타겟 지정 대기 (30초)
            await asyncio.sleep(30)
            
            if current_player.current_target is None:
                await battle.message.channel.send(f"⏭️ {current_player.real_name}님이 타겟을 지정하지 않아 턴을 넘깁니다.")
                battle.current_turn_index += 1
                await self._start_next_turn(channel_id)
                return
        
        # 타겟 플레이어 찾기
        target_player = None
        for player in battle.users:
            if player.user.id == current_player.current_target:
                target_player = player
                break
        
        if target_player and not target_player.is_eliminated:
            await battle.message.channel.send(
                f"⚔️ **라운드 {battle.current_round} - 전투**\n"
                f"{health_info}\n\n"
                f"🗡️ {current_player.real_name}님이 {target_player.real_name}을(를) 공격합니다!\n"
                f"두 분 모두 주사위를 굴려주세요!"
            )
            
            battle.pending_dice = {
                "phase": "team_attack",
                "waiting_for": [current_player.user.id, target_player.user.id],
                "results": {},
                "attacker": current_player.user.id,
                "target": target_player.user.id
            }
        else:
            await battle.message.channel.send(f"❌ 타겟이 유효하지 않습니다. 턴을 넘깁니다.")
            battle.current_turn_index += 1
            await self._start_next_turn(channel_id)
    
    async def _process_combat_results(self, channel_id: int):
        """전투 결과 처리"""
        print(f"[DEBUG] _process_combat_results called for channel {channel_id}")
        battle = self.active_battles[channel_id]
        results = battle.pending_dice["results"]
        phase = battle.pending_dice["phase"]
        print(f"[DEBUG] Processing phase: {phase}")
        print(f"[DEBUG] Results: {results}")
        
        # 집중공격 단일 판정
        if phase == "focused_single":
            focused = battle.focused_attack
            target_player = next(p for p in battle.users if p.user.id == focused["target"])
            
            attack_value = results.get(battle.admin.user.id, 0)
            defend_value = results.get(target_player.user.id, 0)
            
            if attack_value > defend_value:
                # 모든 공격 성공
                hits = min(focused["total_attacks"], target_player.max_health - target_player.hits_received)
                target_player.hits_received += hits
                battle.admin.hits_dealt += hits
                
                result_msg = f"💥 **대성공!** {battle.monster_name}의 공격({attack_value})이 "
                result_msg += f"{target_player.real_name}({defend_value})에게 {hits}회 모두 명중!"
                
                # 닉네임 업데이트
                await self._update_user_health_nickname(target_player)
                
                if target_player.hits_received >= target_player.max_health:
                    target_player.is_eliminated = True
                    result_msg += f"\n💀 **{target_player.real_name} 탈락!**"
            else:
                # 모든 공격 실패
                result_msg = f"🛡️ **완벽한 회피!** {target_player.real_name}({defend_value})이 "
                result_msg += f"{battle.monster_name}의 모든 공격({attack_value})을 회피!"
            
            await battle.message.channel.send(result_msg)
            
            # pending_dice 초기화
            battle.pending_dice = None
            
            # 추가 전체 공격 확인
            if focused["add_normal_attack"] and [p for p in battle.users if not p.is_eliminated]:
                await battle.message.channel.send("이어서 전체 공격을 시작합니다...")
                await asyncio.sleep(1)
                await self._start_normal_admin_attack(channel_id)
            else:
                # 턴 종료
                battle.focused_attack = None
                battle.current_round += 1
                battle.turn_phase = TurnPhase.USER_ATTACK
                battle.current_turn_index = 0
                await asyncio.sleep(1)
                await self._start_next_turn(channel_id)
            
            return
        
        # 집중공격 각각 회피 처리
        elif phase == "focused_each":
            focused = battle.focused_attack
            target_player = next(p for p in battle.users if p.user.id == focused["target"])
            
            attack_value = results.get(battle.admin.user.id, 0)
            defend_value = results.get(target_player.user.id, 0)
            
            current_attack = focused["current_attack"]  # ✅ 변수를 먼저 선언
            
            # 공격 결과 저장
            if attack_value > defend_value:
                focused["results"].append({
                    "attack": current_attack,  # ✅ 변수 사용
                    "hit": True,
                    "attack_value": attack_value,
                    "defend_value": defend_value
                })
                target_player.hits_received += 1
                battle.admin.hits_dealt += 1
                
                result_msg = f"🎯 **{current_attack}회차 명중!** {battle.monster_name}의 공격({attack_value})이 "
                result_msg += f"{target_player.real_name}({defend_value})에게 명중!"
                
                # 닉네임 업데이트
                await self._update_user_health_nickname(target_player)
                
                # 탈락 체크
                if target_player.hits_received >= target_player.max_health:
                    target_player.is_eliminated = True
                    result_msg += f"\n💀 **{target_player.real_name} 탈락!**"
            else:
                focused["results"].append({
                    "attack": current_attack,  # ✅ 변수 사용
                    "hit": False,
                    "attack_value": attack_value,
                    "defend_value": defend_value
                })
                result_msg = f"🛡️ **{current_attack}회차 회피!** {target_player.real_name}({defend_value})이 "
                result_msg += f"{battle.monster_name}의 공격({attack_value})을 회피!"
            
            await battle.message.channel.send(result_msg)
            
            # pending_dice 초기화
            battle.pending_dice = None
            
            # 다음 공격 확인
            focused["current_attack"] += 1
            
            if focused["current_attack"] <= focused["total_attacks"] and not target_player.is_eliminated:
                # 다음 공격 진행
                await asyncio.sleep(1.5)
                await self._start_focused_attack_round(channel_id)
            else:
                # 집중공격 종료
                hits = sum(1 for r in focused["results"] if r["hit"])
                await battle.message.channel.send(
                    f"\n💥 **집중공격 종료!**\n"
                    f"총 {focused['total_attacks']}회 공격 중 {hits}회 명중!"
                )
                
                # 추가 전체 공격 확인
                if focused["add_normal_attack"] and [p for p in battle.users if not p.is_eliminated]:
                    await battle.message.channel.send("이어서 전체 공격을 시작합니다...")
                    await asyncio.sleep(1)
                    await self._start_normal_admin_attack(channel_id)
                else:
                    # 턴 종료
                    battle.focused_attack = None
                    battle.current_round += 1
                    battle.turn_phase = TurnPhase.USER_ATTACK
                    battle.current_turn_index = 0
                    await asyncio.sleep(1)
                    await self._start_next_turn(channel_id)
            
            return
        
        # 유저 공격 처리
        elif phase == "user_attack":
            attacker_id = battle.pending_dice["attacker"]
            attacker = next(p for p in battle.users if p.user.id == attacker_id)
            
            attack_value = results.get(attacker_id, 0)
            defend_value = results.get(battle.admin.user.id, 0)
            
            if attack_value > defend_value:
                battle.admin.hits_received += 1
                attacker.hits_dealt += 1
                result_msg = f"🎯 **명중!** {attacker.real_name}의 공격({attack_value})이 {battle.monster_name}({defend_value})에게 명중!"
                
                await self._update_admin_health_nickname(battle)
                
            else:
                result_msg = f"🛡️ **회피!** {battle.monster_name}({defend_value})이 {attacker.real_name}의 공격({attack_value})을 회피!"
            
            await battle.message.channel.send(result_msg)
            
            battle.current_turn_index += 1
            
            # pending_dice 초기화
            battle.pending_dice = None
            
            if battle.admin.hits_received >= battle.admin.max_health:
                await self._end_battle(channel_id)
                return
            
            await asyncio.sleep(1)
            await self._start_next_turn(channel_id)
            return  # 추가
        
        # Admin 전체 공격 처리
        elif phase == "admin_attack":
            print(f"[DEBUG] Processing admin attack")
            admin_attack = results.get(battle.admin.user.id, 0)
            print(f"[DEBUG] Admin attack value: {admin_attack}")
            battle.last_admin_attack = admin_attack
            
            hit_messages = []
            eliminated_users = []
            
            for player in battle.users:
                if player.is_eliminated:
                    continue
                
                defend_value = results.get(player.user.id, 0)
                
                if admin_attack > defend_value:
                    player.hits_received += 1
                    battle.admin.hits_dealt += 1
                    hit_messages.append(f"🎯 {player.real_name}({defend_value}) 피격!")
                    
                    await self._update_user_health_nickname(player)
                    
                    if player.hits_received >= player.max_health:
                        player.is_eliminated = True
                        eliminated_users.append(player.real_name)
                else:
                    hit_messages.append(f"🛡️ {player.real_name}({defend_value}) 회피!")
            
            result_msg = f"⚔️ **{battle.monster_name} 공격({admin_attack})**\n" + "\n".join(hit_messages)
            
            if eliminated_users:
                result_msg += f"\n\n💀 **탈락:** {', '.join(eliminated_users)}"
            
            await battle.message.channel.send(result_msg)
            
            battle.current_round += 1
            battle.turn_phase = TurnPhase.USER_ATTACK
            battle.current_turn_index = 0
            battle.admin_actions_remaining = 1  # 다음 턴을 위해 리셋
            
            # pending_dice 초기화
            battle.pending_dice = None
            
            await asyncio.sleep(1)
            await self._start_next_turn(channel_id)
            return  # 추가
        
        # 팀 공격 처리 (팀전에서 사용)
        elif phase == "team_attack":
            attacker_id = battle.pending_dice["attacker"]
            target_id = battle.pending_dice["target"]
            
            attacker = next(p for p in battle.users if p.user.id == attacker_id)
            target = next(p for p in battle.users if p.user.id == target_id)
            
            attack_value = results.get(attacker_id, 0)
            defend_value = results.get(target_id, 0)
            
            if attack_value > defend_value:
                target.hits_received += 1
                attacker.hits_dealt += 1
                result_msg = f"🎯 **명중!** {attacker.real_name}의 공격({attack_value})이 {target.real_name}({defend_value})에게 명중!"
                
                await self._update_user_health_nickname(target)
                
                if target.hits_received >= target.max_health:
                    target.is_eliminated = True
                    result_msg += f"\n💀 **{target.real_name} 탈락!**"
            else:
                result_msg = f"🛡️ **회피!** {target.real_name}({defend_value})이 {attacker.real_name}의 공격({attack_value})을 회피!"
            
            await battle.message.channel.send(result_msg)
            
            battle.current_turn_index += 1
            
            # pending_dice 초기화
            battle.pending_dice = None
            
            await asyncio.sleep(1)
            await self._start_next_turn(channel_id)
            return  # 추가
        
        # 마지막 라인의 battle.pending_dice = None 제거

    async def _start_focused_attack_round(self, channel_id: int):
        """집중공격 라운드 시작 (각각 회피 방식)"""
        battle = self.active_battles.get(channel_id)
        if not battle or not battle.focused_attack:
            return
        
        focused = battle.focused_attack
        target_player = next(p for p in battle.users if p.user.id == focused["target"])
        current_attack = focused["current_attack"]
        
        # 현재 공격 번호 표시
        await battle.message.channel.send(
            f"⚔️ **집중공격 {current_attack}/{focused['total_attacks']}회차**\n"
            f"🗡️ {battle.monster_name}님, 공격 주사위를 굴려주세요!\n"
            f"🛡️ {target_player.real_name}님, 회피 주사위를 굴려주세요!"
        )
        
        battle.pending_dice = {
            "phase": "focused_each",
            "waiting_for": [battle.admin.user.id, target_player.user.id],
            "results": {}
        }
    
    async def _start_normal_admin_attack(self, channel_id: int):
        """일반 Admin 전체 공격 시작"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        active_users = [p for p in battle.users if not p.is_eliminated]
        if not active_users:
            await self._end_battle(channel_id)
            return
        
        health_info = self._create_health_info(battle)
        
        await battle.message.channel.send(
            f"⚔️ **{battle.monster_name}의 전체 공격**\n"
            f"{health_info}\n\n"
            f"🗡️ {battle.monster_name}님, 공격 다이스를 굴려주세요!\n"
            f"🛡️ 모든 유저는 회피 다이스를 굴려주세요!"
        )
        
        waiting_users = [p.user.id for p in active_users]
        battle.pending_dice = {
            "phase": "admin_attack",
            "waiting_for": [battle.admin.user.id] + waiting_users,
            "results": {}
        }
    
    # ===== 전투 정보 표시 메서드 =====
    def _create_battle_status_embed(self, battle: MultiUserBattle) -> discord.Embed:
        """전투 상태 임베드 생성"""
        if battle.is_team_battle:
            return self._create_team_battle_status_embed(battle)
        
        embed = discord.Embed(
            title=f"⚔️ {battle.battle_name}",
            description=f"**라운드 {battle.current_round}**",
            color=discord.Color.red()
        )
        
        # Admin 상태
        admin_health_bar = self._create_health_bar(battle.admin.hits_received, battle.admin.max_health)
        embed.add_field(
            name=f"{battle.admin.real_name} (Admin)",
            value=f"{admin_health_bar}\n"
                  f"체력: {battle.admin.max_health - battle.admin.hits_received}/{battle.admin.max_health}\n"
                  f"가한 피해: {battle.admin.hits_dealt}",
            inline=False
        )
        
        # 유저들 상태
        for player in battle.users:
            if player.is_eliminated:
                status = "💀 탈락"
            else:
                health_bar = self._create_health_bar(player.hits_received, player.max_health)
                status = f"{health_bar}\n체력: {player.max_health - player.hits_received}/{player.max_health}"
            
            embed.add_field(
                name=player.real_name,
                value=f"{status}\n가한 피해: {player.hits_dealt}",
                inline=True
            )
        
        return embed
    
    def _create_team_battle_status_embed(self, battle: MultiUserBattle) -> discord.Embed:
        """팀 전투 상태 임베드 생성"""
        embed = discord.Embed(
            title="⚔️ 팀 전투",
            description=f"**라운드 {battle.current_round}**",
            color=discord.Color.red()
        )
        
        # 팀 A 상태
        team_a_info = []
        for player in battle.team_a_users:
            if player.is_eliminated:
                status = f"💀 {player.real_name}"
            else:
                health = player.max_health - player.hits_received
                status = f"{player.real_name} ({health}/{player.max_health}HP)"
            team_a_info.append(status)
        
        embed.add_field(
            name="팀 A",
            value="\n".join(team_a_info) or "전원 탈락",
            inline=True
        )
        
        # 팀 B 상태
        team_b_info = []
        for player in battle.team_b_users:
            if player.is_eliminated:
                status = f"💀 {player.real_name}"
            else:
                health = player.max_health - player.hits_received
                status = f"{player.real_name} ({health}/{player.max_health}HP)"
            team_b_info.append(status)
        
        embed.add_field(
            name="팀 B",
            value="\n".join(team_b_info) or "전원 탈락",
            inline=True
        )
        
        return embed
    
    def _create_health_bar(self, hits_received: int, max_health: int) -> str:
        """체력바 생성"""
        current_health = max_health - hits_received
        percentage = current_health / max_health
        
        if percentage > 0.6:
            emoji = "💚"
        elif percentage > 0.3:
            emoji = "💛"
        elif percentage > 0:
            emoji = "🧡"
        else:
            emoji = "💔"
        
        filled = int(percentage * 10)
        bar = emoji * filled + "🖤" * (10 - filled)
        
        return bar
    
    def _create_health_info(self, battle: MultiUserBattle) -> str:
        """현재 체력 정보 문자열 생성"""
        if battle.is_team_battle:
            return self._create_team_health_info(battle)
        
        info = []
        
        # Admin 체력
        admin_health = battle.admin.max_health - battle.admin.hits_received
        info.append(f"**{battle.admin.real_name}**: {admin_health}/{battle.admin.max_health}HP")
        
        # 유저들 체력
        for player in battle.users:
            if not player.is_eliminated:
                player_health = player.max_health - player.hits_received
                info.append(f"**{player.real_name}**: {player_health}/{player.max_health}HP")
        
        return " | ".join(info)
    
    def _create_team_health_info(self, battle: MultiUserBattle) -> str:
        """팀 전투 체력 정보 문자열 생성"""
        team_a_alive = sum(1 for p in battle.team_a_users if not p.is_eliminated)
        team_b_alive = sum(1 for p in battle.team_b_users if not p.is_eliminated)
        
        return f"**팀 A**: {team_a_alive}명 생존 | **팀 B**: {team_b_alive}명 생존"
    
    # ===== 전투 종료 처리 =====
    async def _end_battle(self, channel_id: int):
        """전투 종료 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        battle.phase = BattlePhase.FINISHED
        battle.is_active = False
        
        # 승자 결정
        admin_health = battle.admin.max_health - battle.admin.hits_received
        surviving_users = [p for p in battle.users if not p.is_eliminated]
        
        embed = discord.Embed(
            title="⚔️ 전투 종료!",
            color=discord.Color.green()
        )
        
        if admin_health <= 0:
            # 유저 승리
            embed.description = f"🎉 **유저 팀 승리!**\n{battle.monster_name}이(가) 쓰러졌습니다!"
            
            # 생존자 정보
            if surviving_users:
                survivor_info = []
                for player in surviving_users:
                    remaining_health = player.max_health - player.hits_received
                    survivor_info.append(f"{player.real_name}: {remaining_health}/{player.max_health}HP")
                
                embed.add_field(
                    name="생존자",
                    value="\n".join(survivor_info),
                    inline=False
                )
        else:
            # Admin 승리
            embed.description = f"💀 **{battle.monster_name} 승리!**\n모든 도전자가 쓰러졌습니다!"
            embed.add_field(
                name=f"{battle.monster_name} 잔여 체력",
                value=f"{admin_health}/{battle.admin.max_health}HP",
                inline=False
            )
        
        # 전투 통계
        stats = []
        
        # Admin 통계
        stats.append(f"**{battle.monster_name}**: {battle.admin.hits_dealt}명중 / {battle.admin.hits_received}피격")
        
        # 유저 통계
        for player in battle.users:
            stats.append(f"**{player.real_name}**: {player.hits_dealt}명중 / {player.hits_received}피격")
        
        embed.add_field(
            name="전투 통계",
            value="\n".join(stats),
            inline=False
        )
        
        embed.add_field(
            name="전투 시간",
            value=f"총 {battle.current_round}라운드",
            inline=False
        )
        
        await battle.message.channel.send(embed=embed)
        
        # 전투 기록 저장
        self.battle_history.append({
            "channel_id": channel_id,
            "battle_name": battle.battle_name,
            "winner": "users" if admin_health <= 0 else "admin",
            "rounds": battle.current_round,
            "timestamp": datetime.now()
        })
        
        # 전투 정보 제거
        del self.active_battles[channel_id]
    
    async def _end_team_battle(self, channel_id: int):
        """팀 전투 종료 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        battle.phase = BattlePhase.FINISHED
        battle.is_active = False
        
        # 승리 팀 결정
        team_a_alive = [p for p in battle.team_a_users if not p.is_eliminated]
        team_b_alive = [p for p in battle.team_b_users if not p.is_eliminated]
        
        embed = discord.Embed(
            title="⚔️ 팀 전투 종료!",
            color=discord.Color.green()
        )
        
        if team_a_alive and not team_b_alive:
            embed.description = "🎉 **팀 A 승리!**"
            winner = "Team A"
        elif team_b_alive and not team_a_alive:
            embed.description = "🎉 **팀 B 승리!**"
            winner = "Team B"
        else:
            embed.description = "🤝 **무승부!**"
            winner = "Draw"
        
        # 생존자 정보
        if team_a_alive:
            survivor_info = []
            for player in team_a_alive:
                remaining_health = player.max_health - player.hits_received
                survivor_info.append(f"{player.real_name}: {remaining_health}/{player.max_health}HP")
            
            embed.add_field(
                name="팀 A 생존자",
                value="\n".join(survivor_info),
                inline=True
            )
        
        if team_b_alive:
            survivor_info = []
            for player in team_b_alive:
                remaining_health = player.max_health - player.hits_received
                survivor_info.append(f"{player.real_name}: {remaining_health}/{player.max_health}HP")
            
            embed.add_field(
                name="팀 B 생존자",
                value="\n".join(survivor_info),
                inline=True
            )
        
        # 전투 통계
        stats_a = []
        stats_b = []
        
        for player in battle.team_a_users:
            stats_a.append(f"{player.real_name}: {player.hits_dealt}명중/{player.hits_received}피격")
        
        for player in battle.team_b_users:
            stats_b.append(f"{player.real_name}: {player.hits_dealt}명중/{player.hits_received}피격")
        
        embed.add_field(
            name="팀 A 전투 통계",
            value="\n".join(stats_a),
            inline=True
        )
        
        embed.add_field(
            name="팀 B 전투 통계",
            value="\n".join(stats_b),
            inline=True
        )
        
        embed.add_field(
            name="전투 시간",
            value=f"총 {battle.current_round}라운드",
            inline=False
        )
        
        await battle.message.channel.send(embed=embed)
        
        # 전투 기록 저장
        self.battle_history.append({
            "channel_id": channel_id,
            "battle_name": "팀 전투",
            "winner": winner,
            "rounds": battle.current_round,
            "timestamp": datetime.now()
        })
        
        # 전투 정보 제거
        del self.active_battles[channel_id]
    
    # ===== 닉네임 업데이트 메서드 =====
    async def _update_user_health_nickname(self, player: BattlePlayer):
        """유저 체력 닉네임 업데이트"""
        if not player.user or not hasattr(player.user, 'edit'):
            return
        
        try:
            damage_taken = player.hits_received * 10
            new_health = max(0, player.real_health - damage_taken)
            
            new_nickname = update_nickname_health(player.user.display_name, new_health)
            
            if new_nickname != player.user.display_name:
                await player.user.edit(nick=new_nickname)
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.error(f"닉네임 업데이트 실패: {e}")
    
    async def _update_admin_health_nickname(self, battle: MultiUserBattle):
        """Admin 체력 닉네임 업데이트"""
        if not battle.admin or not battle.admin.user:
            return
        
        try:
            damage_taken = battle.admin.hits_received * 10
            new_health = max(0, battle.admin.real_health - damage_taken)
            
            new_nickname = update_nickname_health(battle.admin.user.display_name, new_health)
            
            if new_nickname != battle.admin.user.display_name:
                await battle.admin.user.edit(nick=new_nickname)
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.error(f"Admin 닉네임 업데이트 실패: {e}")
    
    # ===== 항복 처리 =====
    async def handle_surrender(self, channel_id: int, player: BattlePlayer):
        """플레이어 항복 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        player.is_eliminated = True
        player.hits_received = player.max_health
        
        await self._update_user_health_nickname(player)
        
        # 모든 플레이어가 탈락했는지 확인
        if battle.is_team_battle:
            await self._end_team_battle(channel_id)
        else:
            active_users = [p for p in battle.users if not p.is_eliminated]
            if not active_users:
                await self._end_battle(channel_id)
    
    async def handle_admin_surrender(self, channel_id: int):
        """Admin 항복 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle or not battle.admin:
            return
        
        battle.admin.hits_received = battle.admin.max_health
        await self._end_battle(channel_id)
    
    # ===== 타격 명령어 처리 (팀전용) =====
    async def handle_team_attack_command(self, message: discord.Message, target: discord.Member):
        """팀 전투 중 타격 명령어 처리"""
        channel_id = message.channel.id
        battle = self.active_battles.get(channel_id)
        
        if not battle or not battle.is_team_battle:
            return
        
        attacker_id = message.author.id
        
        # 공격자 찾기
        attacker_player = None
        for player in battle.users:
            if player.user.id == attacker_id and not player.is_eliminated:
                attacker_player = player
                break
        
        if not attacker_player:
            await message.channel.send("전투에 참여 중이지 않거나 탈락한 상태입니다.")
            return
        
        # 타겟 찾기
        target_player = None
        for player in battle.users:
            if player.user.id == target.id and not player.is_eliminated:
                target_player = player
                break
        
        if not target_player:
            await message.channel.send("대상이 전투에 참여 중이 아닙니다.")
            return
        
        # 같은 팀 공격 방지
        if attacker_player.team == target_player.team:
            await message.channel.send("같은 팀은 공격할 수 없습니다!")
            return
        
        # 탈락한 대상 공격 방지
        if target_player.is_eliminated:
            await message.channel.send("탈락한 대상은 공격할 수 없습니다!")
            return
        
        # 타겟 설정
        attacker_player.current_target = target.id
        await message.channel.send(f"⚔️ {attacker_player.real_name}님이 {target_player.real_name}을(를) 타겟으로 지정했습니다!")
        
        # 현재 턴인 경우 즉시 전투 시작
        if battle.current_turn_index < len(battle.users) and battle.users[battle.current_turn_index].user.id == attacker_id:
            await self._start_team_turn(channel_id)
    
    # ===== 회복 처리 =====
    async def handle_recovery_update(self, user_id: int, old_health: int, new_health: int):
        """회복으로 인한 전투 체력 업데이트"""
        for channel_id, battle in self.active_battles.items():
            player = None
            
            # Admin 회복
            if battle.admin and battle.admin.user.id == user_id:
                # Admin은 실제 체력과 전투 체력 처리가 다름
                if battle.health_sync:
                    # 체력 동기화가 켜져 있을 때
                    from battle_utils import calculate_battle_health
                    
                    # 실제 체력 업데이트
                    battle.admin.real_health = new_health
                    
                    # 전투 체력 재계산
                    old_battle_health = calculate_battle_health(old_health)
                    new_battle_health = calculate_battle_health(new_health)
                    
                    if new_battle_health > old_battle_health:
                        health_increase = new_battle_health - old_battle_health
                        
                        # 피격 횟수 감소 (회복)
                        battle.admin.hits_received = max(0, battle.admin.hits_received - health_increase)
                        
                        await battle.message.channel.send(
                            f"💚 {battle.monster_name}의 회복으로 전투 체력이 {health_increase} 증가했습니다! "
                            f"(전투 체력: {battle.admin.max_health - battle.admin.hits_received}/{battle.admin.max_health})"
                        )
                else:
                    # 체력 동기화가 꺼져 있을 때는 실제 체력만 업데이트
                    battle.admin.real_health = new_health
                
                # 전투 상태 업데이트
                embed = self._create_battle_status_embed(battle)
                await battle.message.edit(embed=embed)
                continue
            
            # 일반 유저 회복
            for p in battle.users:
                if p.user.id == user_id and not p.is_eliminated:
                    player = p
                    break
            
            if player:
                # 실제 체력 업데이트
                player.real_health = new_health
                
                if battle.health_sync:
                    # 체력 동기화가 켜져 있을 때
                    from battle_utils import calculate_battle_health
                    old_battle_health = calculate_battle_health(old_health)
                    new_battle_health = calculate_battle_health(new_health)
                    
                    if new_battle_health > old_battle_health:
                        health_increase = new_battle_health - old_battle_health
                        
                        # 최대 체력 증가 (전투 중 회복)
                        player.max_health += health_increase
                        
                        await battle.message.channel.send(
                            f"💚 {player.real_name}님의 회복으로 전투 체력이 {health_increase} 증가했습니다! "
                            f"(전투 체력: {player.max_health - player.hits_received}/{player.max_health})"
                        )
                        
                        # 전투 상태 업데이트
                        embed = self._create_battle_status_embed(battle)
                        await battle.message.edit(embed=embed)

# ===== UI 컴포넌트 =====

class TeamBattleWithAdminSyncView(discord.ui.View):
    """Admin이 포함된 팀 전투 체력 동기화 선택 뷰"""
    def __init__(self, manager: AdminBattleManager, original_message: discord.Message,
                 team_a_users: List[discord.Member], team_b_users: List[discord.Member],
                 health_values: List[int], team_a_has_admin: bool, team_b_has_admin: bool):
        super().__init__(timeout=30)
        self.manager = manager
        self.original_message = original_message
        self.team_a_users = team_a_users
        self.team_b_users = team_b_users
        self.health_values = health_values
        self.team_a_has_admin = team_a_has_admin
        self.team_b_has_admin = team_b_has_admin
    
    @discord.ui.button(label="체력 동기화하여 시작", style=discord.ButtonStyle.primary, emoji="💚")
    async def sync_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message("Admin만 선택할 수 있습니다!", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="전투를 시작합니다...", embed=None, view=None)
        await self.manager.start_team_battle_with_admin(
            self.original_message,
            self.team_a_users,
            self.team_b_users,
            self.health_values,
            sync_health=True,
            team_a_has_admin=self.team_a_has_admin,
            team_b_has_admin=self.team_b_has_admin
        )
    
    @discord.ui.button(label="설정된 체력으로 시작", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def normal_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message("Admin만 선택할 수 있습니다!", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="전투를 시작합니다...", embed=None, view=None)
        await self.manager.start_team_battle_with_admin(
            self.original_message,
            self.team_a_users,
            self.team_b_users,
            self.health_values,
            sync_health=False,
            team_a_has_admin=self.team_a_has_admin,
            team_b_has_admin=self.team_b_has_admin
        )

class BattleStartWithSyncView(discord.ui.View):
    """1대1 전투 시작 뷰"""
    def __init__(self, manager: AdminBattleManager, channel_id: int, opponent: discord.Member):
        super().__init__(timeout=60)
        self.manager = manager
        self.channel_id = channel_id
        self.opponent = opponent
    
    @discord.ui.button(label="체력 동기화하여 시작", style=discord.ButtonStyle.primary, emoji="💚")
    async def sync_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                "상대방만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self.manager.accept_battle_with_sync(interaction, self.channel_id, sync=True)
    
    @discord.ui.button(label="기본으로 시작", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def normal_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                "상대방만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await self.manager.accept_battle_with_sync(interaction, self.channel_id, sync=False)
    
    @discord.ui.button(label="전투 거절", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                "상대방만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        if self.channel_id in self.manager.active_battles:
            del self.manager.active_battles[self.channel_id]
        
        embed = discord.Embed(
            title="❌ 전투 거절",
            description="전투가 거절되었습니다.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)

class MultiBattleSyncView(discord.ui.View):
    """다중 전투 체력 동기화 선택 뷰"""
    def __init__(self, manager: AdminBattleManager, original_message: discord.Message, 
                 users: List[discord.Member], admin_health: int, monster_name: str = "시스템"):
        super().__init__(timeout=30)
        self.manager = manager
        self.original_message = original_message
        self.users = users
        self.admin_health = admin_health
        self.monster_name = monster_name
    
    @discord.ui.button(label="체력 동기화하여 시작", style=discord.ButtonStyle.primary, emoji="💚")
    async def sync_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message(
                "Admin만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.edit_message(content="전투를 시작합니다...", embed=None, view=None)
        await self.manager.start_multi_battle(
            self.original_message, 
            self.users, 
            self.admin_health, 
            sync_health=True,
            monster_name=self.monster_name
        )
    
    @discord.ui.button(label="기본으로 시작", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def normal_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message(
                "Admin만 선택할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.edit_message(content="전투를 시작합니다...", embed=None, view=None)
        await self.manager.start_multi_battle(
            self.original_message, 
            self.users, 
            self.admin_health, 
            sync_health=False,
            monster_name=self.monster_name
        )
    
    @discord.ui.button(label="취소", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """전투 취소"""
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message(
                "Admin만 취소할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.edit_message(
            content="전투가 취소되었습니다.",
            embed=None,
            view=None
        )

class TeamBattleSyncView(discord.ui.View):
    """팀 전투 체력 동기화 선택 뷰"""
    def __init__(self, manager: AdminBattleManager, original_message: discord.Message,
                 team_a_users: List[discord.Member], team_b_users: List[discord.Member],
                 health_values: List[int]):
        super().__init__(timeout=30)
        self.manager = manager
        self.original_message = original_message
        self.team_a_users = team_a_users
        self.team_b_users = team_b_users
        self.health_values = health_values
    
    @discord.ui.button(label="체력 동기화하여 시작", style=discord.ButtonStyle.primary, emoji="💚")
    async def sync_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message("Admin만 선택할 수 있습니다!", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="전투를 시작합니다...", embed=None, view=None)
        await self.manager.start_team_battle(
            self.original_message,
            self.team_a_users,
            self.team_b_users,
            self.health_values,
            sync_health=True
        )
    
    @discord.ui.button(label="설정된 체력으로 시작", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def normal_start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message("Admin만 선택할 수 있습니다!", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="전투를 시작합니다...", embed=None, view=None)
        await self.manager.start_team_battle(
            self.original_message,
            self.team_a_users,
            self.team_b_users,
            self.health_values,
            sync_health=False
        )

# ===== 전역 인스턴스 =====
admin_battle_manager = AdminBattleManager()

def get_admin_battle_manager():
    """전역 Admin 전투 관리자 반환"""
    return admin_battle_manager
