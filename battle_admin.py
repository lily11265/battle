# battle_admin.py - Admin 전용 전투 시스템 (스킬 시스템 통합)
"""
Admin 전용 전투 시스템
- 1대1, 1대다, 팀 대 팀 전투 지원
- 커스텀 몬스터 이름 지원
- 체력 동기화 옵션
- 턴제 전투 시스템
- 스킬 시스템 완전 통합
"""

import discord
from discord import app_commands
import asyncio
import random
import logging
import re
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
from battle_utils import extract_health_from_nickname, calculate_battle_health, update_nickname_health

# === 스킬 시스템 import (추가됨) ===
try:
    from skills.skill_manager import skill_manager
    from skills.skill_effects import skill_effects
    SKILL_SYSTEM_AVAILABLE = True
except ImportError:
    skill_manager = None
    skill_effects = None
    SKILL_SYSTEM_AVAILABLE = False
    logging.warning("스킬 시스템을 찾을 수 없습니다. 스킬 기능이 비활성화됩니다.")

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
    created_at: datetime = field(default_factory=datetime.now)  # 전투 생성 시간
    last_dice_time: Optional[datetime] = None  # 마지막 주사위 시간

# ===== 스킬 시스템 연동 함수들 (새로 추가) =====

async def get_battle_participants(channel_id: str) -> Dict[str, Any]:
    """전투 참여자 목록 조회 (스킬 시스템용)"""
    if not SKILL_SYSTEM_AVAILABLE:
        return {"users": [], "monster": None, "admin": None}
    
    try:
        battle = admin_battle_manager.get_battle(int(channel_id))
        if not battle:
            return {"users": [], "monster": None, "admin": None}
        
        participants = {
            "users": [],
            "monster": None,
            "admin": None
        }
        
        # 유저 목록 수집
        for player in battle.users:
            participants["users"].append({
                "user_id": str(player.user.id),
                "user_name": player.user.display_name,
                "real_name": player.real_name,
                "health": player.max_health - player.hits_received,
                "max_health": player.max_health,
                "is_dead": player.max_health - player.hits_received <= 0,
                "display_name": player.real_name
            })
        
        # 몬스터 정보
        if hasattr(battle, 'monster_name') and battle.monster_name:
            participants["monster"] = {
                "name": battle.monster_name,
                "health": battle.admin.max_health - battle.admin.hits_received if battle.admin else 0,
                "max_health": battle.admin.max_health if battle.admin else 100
            }
        
        # ADMIN 정보
        if battle.admin:
            participants["admin"] = {
                "name": battle.admin.user.display_name,
                "health": battle.admin.max_health - battle.admin.hits_received,
                "max_health": battle.admin.max_health
            }
        
        return participants
        
    except Exception as e:
        logger.error(f"전투 참여자 조회 실패 {channel_id}: {e}")
        return {"users": [], "monster": None, "admin": None}

async def get_user_info(channel_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """특정 유저 정보 조회"""
    if not SKILL_SYSTEM_AVAILABLE:
        return None

# ===== 사용 방법 =====
"""
전투 시스템 사용 방법:

1. 시스템 초기화 (main.py에서 봇 시작 시):
   await initialize_battle_system()

2. 시스템 종료 (main.py에서 봇 종료 시):
   await shutdown_battle_system()

3. 응급 상황 시:
   await emergency_cleanup()

4. 상태 확인:
   status = get_system_status()
   is_healthy = await health_check()

5. 특정 전투 강제 종료:
   await force_cleanup_battle(channel_id, "사유")

6. 전투 디버그 정보:
   debug_info = get_battle_debug_info(channel_id)
"""
        
    try:
        participants = await get_battle_participants(channel_id)
        
        # 유저 목록에서 검색
        for user in participants["users"]:
            if user["user_id"] == str(user_id):
                return user
        
        # 몬스터 체크
        if user_id == "monster" and participants["monster"]:
            return {
                "user_id": "monster",
                "display_name": participants["monster"]["name"],
                "health": participants["monster"]["health"],
                "is_dead": participants["monster"]["health"] <= 0
            }
        
        # ADMIN 체크
        if user_id == "admin" and participants["admin"]:
            return {
                "user_id": "admin", 
                "display_name": participants["admin"]["name"],
                "health": participants["admin"]["health"],
                "is_dead": participants["admin"]["health"] <= 0
            }
        
        return None
        
    except Exception as e:
        logger.error(f"유저 정보 조회 실패 {user_id}: {e}")
        return None

async def send_battle_message(channel_id: str, message: str) -> bool:
    """전투 채널에 메시지 전송"""
    try:
        from main import bot  # main.py에서 bot 인스턴스 import
        
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(message)
            return True
        return False
        
    except Exception as e:
        logger.error(f"전투 메시지 전송 실패 {channel_id}: {e}")
        return False

async def damage_user(channel_id: str, user_id: str, damage_amount: int) -> bool:
    """유저에게 데미지 적용"""
    try:
        battle = admin_battle_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        if user_id == "monster" or user_id == "admin":
            # 몬스터/ADMIN 데미지
            if battle.admin:
                battle.admin.hits_received += damage_amount
                logger.info(f"몬스터/ADMIN 데미지 적용: {damage_amount}")
                return True
        else:
            # 일반 유저 데미지
            for player in battle.users:
                if str(player.user.id) == str(user_id):
                    player.hits_received += damage_amount
                    logger.info(f"유저 {user_id} 데미지 적용: {damage_amount}")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"데미지 적용 실패 {user_id}: {e}")
        return False

async def heal_user(channel_id: str, user_id: str, heal_amount: int) -> bool:
    """유저 회복 처리"""
    try:
        battle = admin_battle_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        if user_id == "monster" or user_id == "admin":
            # 몬스터/ADMIN 회복
            if battle.admin:
                battle.admin.hits_received = max(0, battle.admin.hits_received - heal_amount)
                logger.info(f"몬스터/ADMIN 회복 적용: {heal_amount}")
                return True
        else:
            # 일반 유저 회복
            for player in battle.users:
                if str(player.user.id) == str(user_id):
                    player.hits_received = max(0, player.hits_received - heal_amount)
                    logger.info(f"유저 {user_id} 회복 적용: {heal_amount}")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"회복 적용 실패 {user_id}: {e}")
        return False

async def revive_user(channel_id: str, user_id: str, revive_health: int) -> bool:
    """유저 부활 처리"""
    try:
        battle = admin_battle_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        for player in battle.users:
            if str(player.user.id) == str(user_id):
                # 유저가 죽었는지 확인
                if player.max_health - player.hits_received <= 0:
                    # 부활: hits_received를 조정해서 지정된 체력으로 설정
                    player.hits_received = player.max_health - revive_health
                    player.is_eliminated = False
                    logger.info(f"유저 {user_id} 부활: {revive_health} 체력")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"부활 처리 실패 {user_id}: {e}")
        return False

async def update_battle_display(channel_id: str):
    """전투 상태 화면 업데이트"""
    try:
        battle = admin_battle_manager.get_battle(int(channel_id))
        if battle and hasattr(battle, 'message') and battle.message:
            # 스킬 정보가 포함된 전투 상태 임베드 생성
            embed = await create_battle_status_embed_with_skills(battle)
            await battle.message.edit(embed=embed)
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"전투 화면 업데이트 실패 {channel_id}: {e}")
        return False

async def create_battle_status_embed_with_skills(battle) -> discord.Embed:
    """스킬 정보가 포함된 전투 상태 임베드 생성"""
    try:
        # 기존 전투 상태 임베드 생성
        embed = admin_battle_manager._create_battle_status_embed(battle)
        
        # 스킬 정보 추가
        if SKILL_SYSTEM_AVAILABLE and skill_manager:
            channel_id = str(battle.channel_id)
            channel_state = skill_manager.get_channel_state(channel_id)
            
            active_skills = channel_state.get("active_skills", {})
            special_effects = channel_state.get("special_effects", {})
            
            if active_skills or special_effects:
                skill_info = "🔮 **현재 활성 스킬**:\n"
                
                # 활성 스킬들
                for skill_name, skill_data in active_skills.items():
                    emoji = get_skill_emoji(skill_name)
                    rounds_left = skill_data.get('rounds_left', 0)
                    user_name = skill_data.get('user_name', '알 수 없음')
                    
                    skill_info += f"{emoji} **{skill_name}** ({rounds_left}라운드 남음) - 사용자: {user_name}\n"
                
                # 특수 효과들
                if special_effects:
                    if special_effects.get('virella_bound'):
                        bound_users = special_effects['virella_bound']
                        skill_info += f"🌿 **비렐라** - 배제됨: {', '.join(bound_users)}\n"
                    
                    if special_effects.get('nixara_excluded'):
                        excluded_users = special_effects['nixara_excluded']
                        skill_info += f"🌀 **닉사라** - 배제됨: {', '.join(excluded_users)}\n"
                
                # 스킬 정보 필드 추가
                embed.add_field(
                    name="🔮 활성 스킬",
                    value=skill_info,
                    inline=False
                )
        
        return embed
        
    except Exception as e:
        logger.error(f"스킬 포함 임베드 생성 실패: {e}")
        # 오류 시 기본 임베드 반환
        return admin_battle_manager._create_battle_status_embed(battle)

def get_skill_emoji(skill_name: str) -> str:
    """스킬별 이모지 반환"""
    emoji_map = {
        "오닉셀": "🔥",
        "피닉스": "🔥",
        "오리븐": "⚡",
        "카론": "🤝",
        "스카넬": "☄️",
        "루센시아": "💚",
        "비렐라": "🌿",
        "그림": "💀",
        "닉사라": "🌀",
        "제룬카": "🎯",
        "넥시스": "⭐",
        "볼켄": "🌋",
        "단목": "🏹",
        "콜 폴드": "🎲",
        "황야": "⚔️",
        "스트라보스": "⚡"
    }
    return emoji_map.get(skill_name, "🔮")

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

    def get_battle(self, channel_id: int) -> Optional[MultiUserBattle]:
        """채널의 전투 정보 조회"""
        return self.active_battles.get(channel_id)

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
        """주사위 결과를 직접 처리 (스킬 효과 포함)"""
        print(f"[DEBUG] handle_dice_roll called - User: {user_id}, Channel: {channel_id}, Value: {dice_value}")
        
        battle = self.active_battles.get(channel_id)
        if not battle or not battle.pending_dice:
            print(f"[DEBUG] No battle or pending dice for channel {channel_id}")
            return
        
        # 주사위 시간 업데이트
        battle.last_dice_time = datetime.now()
        
        print(f"[DEBUG] Current phase: {battle.pending_dice.get('phase')}")
        print(f"[DEBUG] Waiting for: {battle.pending_dice.get('waiting_for')}")
        
        # 대기 중인 플레이어인지 확인
        if user_id not in battle.pending_dice["waiting_for"]:
            print(f"[DEBUG] User {user_id} not in waiting list")
            return
        
        # 유저 이름 찾기
        user_name = "Unknown"
        if battle.admin and user_id == battle.admin.user.id:
            user_name = battle.monster_name
        else:
            for player in battle.users:
                if player.user.id == user_id:
                    user_name = player.real_name
                    break
        
        # 스킬 효과 적용
        final_value = dice_value
        skill_messages = []
        
        if SKILL_SYSTEM_AVAILABLE:
            try:
                final_value, skill_messages = await self._process_dice_with_skill_effects(
                    channel_id, user_name, dice_value
                )
                
                # 스킬 메시지 전송
                if skill_messages:
                    channel = None
                    try:
                        from main import bot
                        channel = bot.get_channel(channel_id)
                        if channel:
                            for skill_message in skill_messages:
                                await channel.send(skill_message)
                    except:
                        pass
                
                # 값이 변경된 경우 알림
                if final_value != dice_value and channel:
                    value_change_msg = f"🎲 **{user_name}**님의 주사위 결과: {dice_value} → **{final_value}**"
                    await channel.send(value_change_msg)
                        
            except Exception as e:
                logger.error(f"스킬 주사위 처리 실패: {e}")
                final_value = dice_value
        
        # 결과 저장
        battle.pending_dice["results"][user_id] = final_value
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

    # ===== 스킬 시스템 연동을 위한 확장 메서드들 (새로 추가) =====
    
    async def _process_dice_with_skill_effects(self, channel_id: int, user_name: str, dice_value: int) -> Tuple[int, List[str]]:
        """주사위 처리에 스킬 효과 적용"""
        if not SKILL_SYSTEM_AVAILABLE or not skill_effects:
            return dice_value, []
            
        try:
            # 스킬 시스템의 주사위 처리 함수 호출
            final_value, skill_messages = await skill_effects.process_dice_roll(
                user_name, dice_value, str(channel_id)
            )
            
            return final_value, skill_messages
            
        except Exception as e:
            logger.error(f"스킬 주사위 처리 실패: {e}")
            return dice_value, []
    
    async def _apply_skill_damage_effects(self, channel_id: int, target_id: str, base_damage: int) -> int:
        """데미지에 스킬 효과 적용"""
        if not SKILL_SYSTEM_AVAILABLE or not skill_effects:
            return base_damage
            
        try:
            # 스킬 시스템의 데미지 처리 함수 호출
            final_damage = await skill_effects.apply_damage_effects(
                target_id, base_damage, str(channel_id)
            )
            
            return final_damage
            
        except Exception as e:
            logger.error(f"스킬 데미지 처리 실패: {e}")
            return base_damage
    
    async def _advance_battle_round_with_skills(self, channel_id: int):
        """라운드 진행 시 스킬 시스템 연동"""
        if not SKILL_SYSTEM_AVAILABLE:
            return
            
        try:
            channel_str = str(channel_id)
            
            # 스킬 라운드 시작 이벤트 처리
            await self._trigger_skill_round_start_events(channel_str)
            
            # 스킬 라운드 업데이트
            if skill_effects:
                expired_skills = await skill_effects.update_skill_rounds(channel_str)
                
                if expired_skills:
                    expired_list = ", ".join(expired_skills)
                    await send_battle_message(
                        channel_str,
                        f"⏰ 다음 스킬들이 만료되었습니다: {expired_list}"
                    )
            
            # 전투 화면 업데이트 (스킬 정보 포함)
            await update_battle_display(channel_str)
            
        except Exception as e:
            logger.error(f"스킬 라운드 진행 실패: {e}")
    
    async def _trigger_skill_round_start_events(self, channel_id: str):
        """스킬 라운드 시작 이벤트들 처리"""
        if not SKILL_SYSTEM_AVAILABLE or not skill_manager:
            return
            
        try:
            from skills.heroes import get_skill_handler
            
            channel_state = skill_manager.get_channel_state(channel_id)
            current_round = channel_state.get("current_round", 1) + 1
            
            # 모든 활성 스킬의 라운드 시작 이벤트 호출
            for skill_name in channel_state.get("active_skills", {}):
                try:
                    handler = get_skill_handler(skill_name)
                    if handler:
                        await handler.on_round_start(channel_id, current_round)
                except Exception as e:
                    logger.error(f"스킬 {skill_name} 라운드 시작 이벤트 실패: {e}")
            
            # 라운드 번호 업데이트
            skill_manager.update_round(channel_id, current_round)
            
        except Exception as e:
            logger.error(f"스킬 라운드 시작 이벤트 실패: {e}")
    
    async def _handle_post_damage_skill_effects(self, channel_id: int, target_player, damage: int):
        """데미지 후 스킬 효과 처리 (카론 공유 등)"""
        if not SKILL_SYSTEM_AVAILABLE:
            return
            
        try:
            from skills.heroes.karon import KaronHandler
            
            # 카론 스킬 데미지 공유 처리
            karon_handler = KaronHandler()
            await karon_handler.share_damage(str(channel_id), str(target_player.user.id), damage)
            
        except Exception as e:
            logger.error(f"데미지 후 스킬 처리 실패: {e}")

    async def _process_init_results(self, channel_id: int):
        """선공 결정 결과 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        # 로깅 추가로 디버깅
        logger.info(f"선공 결정 처리 시작 - 채널: {channel_id}")
        
        # 결과 정렬
        results = []
        for user in battle.users:
            dice_value = battle.pending_dice["results"].get(user.user.id, 0)
            results.append((user, dice_value))
        
        # Admin도 추가
        admin_dice = battle.pending_dice["results"].get(battle.admin.user.id, 0)
        results.append((battle.admin, admin_dice))
        
        # 주사위 값으로 정렬
        results.sort(key=lambda x: x[1], reverse=True)
        
        # 선공 결정
        if results[0][1] > results[1][1]:
            # 명확한 선공
            if isinstance(results[0][0], AdminPlayer):
                battle.is_admin_turn = True
                await battle.message.channel.send(f"⚔️ {battle.monster_name}이(가) 선공을 가져갑니다!")
            else:
                battle.is_admin_turn = False
                await battle.message.channel.send(f"⚔️ 플레이어들이 선공을 가져갑니다!")
        else:
            # 동점 - 플레이어 우선
            battle.is_admin_turn = False
            await battle.message.channel.send("🎲 동점! 플레이어들이 선공을 가져갑니다!")
        
        # 전투 상태 초기화
        battle.pending_dice = None
        battle.turn_phase = TurnPhase.WAITING
        
        # 첫 번째 턴 시작
        await asyncio.sleep(1)
        
        if battle.is_admin_turn:
            # Admin 턴
            await self._process_admin_turn(channel_id)
        else:
            # 플레이어 턴
            await self._start_player_attack_phase(channel_id)

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
        
        # 주사위 시간 기록
        battle.last_dice_time = datetime.now()
    
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
            
            # 주사위 시간 기록
            battle.last_dice_time = datetime.now()
        
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
            
            # 주사위 시간 기록
            battle.last_dice_time = datetime.now()
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
            # 스킬 시스템 라운드 진행
            await self._advance_battle_round_with_skills(channel_id)
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
        """전투 결과 처리 (스킬 효과 포함)"""
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
                
                # 스킬 효과 적용 데미지
                final_damage = await self._apply_damage_with_skill_effects(
                    battle, target_player, hits
                )
                
                result_msg = f"💥 **대성공!** {battle.monster_name}의 공격({attack_value})이 "
                result_msg += f"{target_player.real_name}({defend_value})에게 {final_damage}회 모두 명중!"
                
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
                # 스킬 시스템 라운드 진행
                await self._advance_battle_round_with_skills(channel_id)
                await asyncio.sleep(1)
                await self._start_next_turn(channel_id)
            
            return
        
        # 집중공격 각각 회피 처리
        elif phase == "focused_each":
            focused = battle.focused_attack
            target_player = next(p for p in battle.users if p.user.id == focused["target"])
            
            attack_value = results.get(battle.admin.user.id, 0)
            defend_value = results.get(target_player.user.id, 0)
            
            current_attack = focused["current_attack"]  # 변수를 먼저 선언
            
            # 공격 결과 저장
            if attack_value > defend_value:
                focused["results"].append({
                    "attack": current_attack,  # 변수 사용
                    "hit": True,
                    "attack_value": attack_value,
                    "defend_value": defend_value
                })
                
                # 스킬 효과 적용 데미지
                final_damage = await self._apply_damage_with_skill_effects(
                    battle, target_player, 1
                )
                
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
                    "attack": current_attack,  # 변수 사용
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
                    # 스킬 시스템 라운드 진행
                    await self._advance_battle_round_with_skills(channel_id)
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
                # 스킬 효과 적용 데미지
                final_damage = await self._apply_damage_with_skill_effects(
                    battle, battle.admin, 1, is_admin=True
                )
                
                attacker.hits_dealt += final_damage
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
            return
        
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
                    # 스킬 효과 적용 데미지
                    final_damage = await self._apply_damage_with_skill_effects(
                        battle, player, 1
                    )
                    
                    battle.admin.hits_dealt += final_damage
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
            
            # 스킬 시스템 라운드 진행
            await self._advance_battle_round_with_skills(channel_id)
            
            await asyncio.sleep(1)
            await self._start_next_turn(channel_id)
            return
        
        # 팀 공격 처리 (팀전에서 사용)
        elif phase == "team_attack":
            attacker_id = battle.pending_dice["attacker"]
            target_id = battle.pending_dice["target"]
            
            attacker = next(p for p in battle.users if p.user.id == attacker_id)
            target = next(p for p in battle.users if p.user.id == target_id)
            
            attack_value = results.get(attacker_id, 0)
            defend_value = results.get(target_id, 0)
            
            if attack_value > defend_value:
                # 스킬 효과 적용 데미지
                final_damage = await self._apply_damage_with_skill_effects(
                    battle, target, 1
                )
                
                attacker.hits_dealt += final_damage
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
            return

    async def _apply_damage_with_skill_effects(self, battle: MultiUserBattle, target_player, base_damage: int, is_admin: bool = False) -> int:
        """데미지 적용 시 스킬 효과 포함"""
        try:
            # 스킬 효과 적용
            if is_admin:
                # Admin 대상 데미지
                final_damage = await self._apply_skill_damage_effects(
                    battle.channel_id, "admin", base_damage
                )
                battle.admin.hits_received += final_damage
            else:
                # 일반 유저 대상 데미지
                final_damage = await self._apply_skill_damage_effects(
                    battle.channel_id, str(target_player.user.id), base_damage
                )
                target_player.hits_received += final_damage
                
                # 데미지 후 스킬 효과 처리
                await self._handle_post_damage_skill_effects(battle.channel_id, target_player, final_damage)
            
            return final_damage
            
        except Exception as e:
            logger.error(f"스킬 데미지 적용 실패: {e}")
            # 오류 시 기본 데미지 적용
            if is_admin:
                battle.admin.hits_received += base_damage
            else:
                target_player.hits_received += base_damage
            return base_damage

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
        """전투 상태 임베드 생성 (기존 로직)"""
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
        
        # 스킬 시스템에 전투 종료 알림 (안전하게 처리)
        if SKILL_SYSTEM_AVAILABLE and skill_manager:
            try:
                if hasattr(skill_manager, 'end_battle'):
                    skill_manager.end_battle(str(channel_id))
                else:
                    skill_manager.clear_channel_skills(str(channel_id))
            except Exception as e:
                logger.error(f"스킬 시스템 정리 중 오류: {e}")
        
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
        logger.info(f"전투 종료 - 채널: {channel_id}")
    
    async def _end_team_battle(self, channel_id: int):
        """팀 전투 종료 처리"""
        battle = self.active_battles.get(channel_id)
        if not battle:
            return
        
        battle.phase = BattlePhase.FINISHED
        battle.is_active = False
        
        # 스킬 시스템에 전투 종료 알림
        if SKILL_SYSTEM_AVAILABLE and skill_manager:
            skill_manager.end_battle(str(channel_id))
        
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

    # === 회복 명령어에 황야 스킬 연동 (새로 추가) ===
    
    async def handle_recovery_with_hwangya(self, interaction: discord.Interaction, 횟수: int):
        """회복 명령어 (황야 스킬 연동)"""
        if not SKILL_SYSTEM_AVAILABLE:
            await self._execute_original_recovery(interaction, 횟수)
            return
        
        user_id = str(interaction.user.id)
        channel_id = str(interaction.channel.id)
        
        try:
            # 행동 차단 체크
            action_check = await skill_effects.check_action_blocked(channel_id, user_id, "recovery")
            if action_check["blocked"]:
                await interaction.response.send_message(f"🚫 {action_check['reason']}", ephemeral=True)
                return
            
            # 황야 스킬 체크 (이중 행동)
            recovery_check = await skill_effects.check_recovery_allowed(channel_id, user_id)
            if not recovery_check["allowed"]:
                await interaction.response.send_message(f"❌ {recovery_check['reason']}", ephemeral=True)
                return
            
            # 기존 회복 로직 실행
            await self._execute_original_recovery(interaction, 횟수)
            
            # 황야 행동 카운터 업데이트
            from skills.heroes.hwangya import HwangyaHandler
            hwangya_handler = HwangyaHandler()
            await hwangya_handler.use_recovery_action(channel_id, user_id)
            
        except Exception as e:
            logger.error(f"회복 명령어 처리 실패: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 회복 처리 중 오류가 발생했습니다.", ephemeral=True)
    
    async def _execute_original_recovery(self, interaction: discord.Interaction, 횟수: int):
        """기존 회복 로직 실행"""
        # 기존의 회복 명령어 처리 로직을 여기에 구현
        # 실제 구현에서는 기존 회복 시스템의 코드를 그대로 사용
        pass

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

# ===== 유틸리티 함수들 =====

def is_admin_user(user: discord.Member) -> bool:
    """Admin 권한 체크"""
    AUTHORIZED_USERS = ["1007172975222603798", "1090546247770832910"]
    AUTHORIZED_NICKNAME = "system | 시스템"
    
    return (str(user.id) in AUTHORIZED_USERS or 
            user.display_name == AUTHORIZED_NICKNAME)

async def check_battle_permissions(interaction: discord.Interaction) -> bool:
    """전투 권한 체크"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Admin만 사용할 수 있는 기능입니다.", ephemeral=True)
        return False
    return True

# === 로깅 및 디버깅 ===

def log_battle_event(battle: MultiUserBattle, event: str, details: str = ""):
    """전투 이벤트 로깅"""
    logger.info(f"[전투 {battle.channel_id}] {event}: {details}")

def log_skill_event(channel_id: str, event: str, details: str = ""):
    """스킬 이벤트 로깅"""
    logger.info(f"[스킬 {channel_id}] {event}: {details}")

# ===== 추가 Admin 명령어 처리 메서드들 =====

class AdminBattleCommands:
    """Admin 전투 명령어 처리 클래스"""
    
    def __init__(self, manager: AdminBattleManager):
        self.manager = manager
    
    async def handle_focused_attack_command(self, message: discord.Message):
        """!집중공격 명령어 처리"""
        if message.author.display_name not in ["system | 시스템", "system", "시스템"]:
            return
        
        channel_id = message.channel.id
        battle = self.manager.active_battles.get(channel_id)
        
        if not battle or not battle.admin or battle.phase != BattlePhase.COMBAT:
            await message.channel.send("진행 중인 Admin 전투가 없습니다.")
            return
        
        if battle.turn_phase != TurnPhase.ADMIN_ATTACK:
            await message.channel.send("Admin의 공격 턴이 아닙니다.")
            return
        
        content = message.content.strip()
        parts = content.split()
        
        if len(parts) < 3:
            await message.channel.send("사용법: `!집중공격 @대상 횟수 [단일/각각] [추가공격]`")
            return
        
        # 대상 파싱
        target_mention = parts[1]
        if not target_mention.startswith('<@') or not target_mention.endswith('>'):
            await message.channel.send("올바른 유저 멘션을 사용해주세요.")
            return
        
        target_id = int(target_mention[2:-1].replace('!', ''))
        target_player = None
        
        for player in battle.users:
            if player.user.id == target_id and not player.is_eliminated:
                target_player = player
                break
        
        if not target_player:
            await message.channel.send("대상을 찾을 수 없거나 이미 탈락했습니다.")
            return
        
        # 공격 횟수 파싱
        try:
            attack_count = int(parts[2])
            if attack_count < 1 or attack_count > 10:
                await message.channel.send("공격 횟수는 1~10 사이여야 합니다.")
                return
        except ValueError:
            await message.channel.send("공격 횟수는 숫자여야 합니다.")
            return
        
        # 판정 방식 파싱
        judgment_type = "each"  # 기본값: 각각 회피
        if len(parts) >= 4:
            if parts[3] in ["단일", "single"]:
                judgment_type = "single"
            elif parts[3] in ["각각", "each"]:
                judgment_type = "each"
        
        # 추가 공격 여부
        add_normal_attack = False
        if len(parts) >= 5 and parts[4] in ["추가공격", "추가", "add"]:
            add_normal_attack = True
        
        # 집중공격 시작
        battle.focused_attack = {
            "target": target_id,
            "total_attacks": attack_count,
            "current_attack": 1,
            "judgment_type": judgment_type,
            "add_normal_attack": add_normal_attack,
            "results": []
        }
        
        if judgment_type == "single":
            # 단일 판정 방식
            await message.channel.send(
                f"⚔️ **{battle.monster_name}의 집중공격!**\n"
                f"🎯 대상: {target_player.real_name}\n"
                f"🔢 공격 횟수: {attack_count}회\n"
                f"🎲 판정 방식: 단일 판정\n\n"
                f"🗡️ {battle.monster_name}님, 공격 주사위를 굴려주세요!\n"
                f"🛡️ {target_player.real_name}님, 회피 주사위를 굴려주세요!\n"
                f"(성공 시 모든 공격 명중, 실패 시 모든 공격 실패)"
            )
            
            battle.pending_dice = {
                "phase": "focused_single",
                "waiting_for": [battle.admin.user.id, target_id],
                "results": {}
            }
        else:
            # 각각 회피 방식
            await message.channel.send(
                f"⚔️ **{battle.monster_name}의 집중공격!**\n"
                f"🎯 대상: {target_player.real_name}\n"
                f"🔢 공격 횟수: {attack_count}회\n"
                f"🎲 판정 방식: 각각 회피\n\n"
                f"첫 번째 공격을 시작합니다..."
            )
            
            await asyncio.sleep(1)
            await self._start_focused_attack_round(channel_id)
    
    async def _start_focused_attack_round(self, channel_id: int):
        """집중공격 라운드 시작"""
        battle = self.manager.active_battles.get(channel_id)
        if not battle or not battle.focused_attack:
            return
        
        focused = battle.focused_attack
        target_player = next(p for p in battle.users if p.user.id == focused["target"])
        current_attack = focused["current_attack"]
        
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
    
    async def handle_battle_status_command(self, message: discord.Message):
        """!전투상태 명령어 처리"""
        channel_id = message.channel.id
        battle = self.manager.active_battles.get(channel_id)
        
        if not battle:
            await message.channel.send("진행 중인 전투가 없습니다.")
            return
        
        # 스킬 정보 포함된 상태 표시
        if SKILL_SYSTEM_AVAILABLE:
            embed = await create_battle_status_embed_with_skills(battle)
        else:
            embed = self.manager._create_battle_status_embed(battle)
        
        await message.channel.send(embed=embed)
    
    async def handle_battle_end_command(self, message: discord.Message):
        """!전투종료 명령어 처리"""
        if message.author.display_name not in ["system | 시스템", "system", "시스템"]:
            return
        
        channel_id = message.channel.id
        battle = self.manager.active_battles.get(channel_id)
        
        if not battle:
            await message.channel.send("진행 중인 전투가 없습니다.")
            return
        
        # 강제 전투 종료
        embed = discord.Embed(
            title="⚔️ 전투 강제 종료",
            description="Admin에 의해 전투가 강제로 종료되었습니다.",
            color=discord.Color.orange()
        )
        
        await message.channel.send(embed=embed)
        
        # 스킬 시스템에 전투 종료 알림
        if SKILL_SYSTEM_AVAILABLE and skill_manager:
            skill_manager.end_battle(str(channel_id))
        
        # 전투 정보 제거
        del self.manager.active_battles[channel_id]

# ===== 전투 이벤트 처리 클래스 =====

class BattleEventHandler:
    """전투 이벤트 처리 클래스"""
    
    def __init__(self, manager: AdminBattleManager):
        self.manager = manager
    
    async def on_user_join_battle(self, channel_id: int, user: discord.Member):
        """유저 전투 참가 이벤트"""
        battle = self.manager.active_battles.get(channel_id)
        if not battle or battle.phase != BattlePhase.WAITING:
            return
        
        # 이미 참가 중인지 확인
        for player in battle.users:
            if player.user.id == user.id:
                return
        
        # 새 플레이어 추가
        real_health = extract_health_from_nickname(user.display_name) or 100
        battle_health = calculate_battle_health(real_health) if battle.health_sync else 10
        
        new_player = BattlePlayer(
            user=user,
            real_name=self.manager.extract_real_name(user.display_name),
            max_health=battle_health,
            real_health=real_health
        )
        
        battle.users.append(new_player)
        
        await battle.message.channel.send(
            f"➕ {new_player.real_name}님이 전투에 참가했습니다! "
            f"(체력: {battle_health}HP)"
        )
    
    async def on_user_leave_battle(self, channel_id: int, user: discord.Member):
        """유저 전투 탈퇴 이벤트"""
        battle = self.manager.active_battles.get(channel_id)
        if not battle:
            return
        
        # 플레이어 찾기 및 제거
        for i, player in enumerate(battle.users):
            if player.user.id == user.id:
                battle.users.pop(i)
                await battle.message.channel.send(
                    f"➖ {player.real_name}님이 전투에서 떠났습니다."
                )
                break
        
        # 전투 중이고 플레이어가 없으면 종료
        if battle.phase == BattlePhase.COMBAT and not battle.users:
            await self.manager._end_battle(channel_id)
    
    async def on_battle_round_end(self, channel_id: int):
        """라운드 종료 이벤트"""
        battle = self.manager.active_battles.get(channel_id)
        if not battle:
            return
        
        # 스킬 시스템 라운드 이벤트
        if SKILL_SYSTEM_AVAILABLE:
            await self.manager._advance_battle_round_with_skills(channel_id)
        
        # 전투 상태 업데이트
        if battle.message:
            embed = self.manager._create_battle_status_embed(battle)
            try:
                await battle.message.edit(embed=embed)
            except:
                pass

# ===== 전투 유틸리티 클래스 =====

class BattleUtility:
    """전투 관련 유틸리티 클래스"""
    
    @staticmethod
    def calculate_damage_reduction(current_health: int, max_health: int) -> float:
        """체력에 따른 데미지 감소율 계산"""
        health_ratio = current_health / max_health
        if health_ratio > 0.8:
            return 0.0  # 체력이 높을 때는 감소 없음
        elif health_ratio > 0.5:
            return 0.1  # 중간 체력에서는 10% 감소
        elif health_ratio > 0.2:
            return 0.2  # 낮은 체력에서는 20% 감소
        else:
            return 0.3  # 매우 낮은 체력에서는 30% 감소
    
    @staticmethod
    def calculate_critical_chance(attacker_health: int, defender_health: int) -> float:
        """크리티컬 확률 계산"""
        base_chance = 0.05  # 기본 5% 크리티컬 확률
        
        # 체력 차이에 따른 추가 확률
        health_diff = attacker_health - defender_health
        if health_diff > 20:
            return min(base_chance + 0.1, 0.25)  # 최대 25%
        elif health_diff > 10:
            return base_chance + 0.05
        else:
            return base_chance
    
    @staticmethod
    def format_battle_time(start_time: datetime, end_time: datetime) -> str:
        """전투 시간 포맷팅"""
        duration = end_time - start_time
        minutes = duration.seconds // 60
        seconds = duration.seconds % 60
        
        if minutes > 0:
            return f"{minutes}분 {seconds}초"
        else:
            return f"{seconds}초"
    
    @staticmethod
    def generate_battle_summary(battle: MultiUserBattle) -> Dict[str, Any]:
        """전투 요약 정보 생성"""
        summary = {
            "battle_name": battle.battle_name,
            "total_rounds": battle.current_round,
            "participants": len(battle.users) + (1 if battle.admin else 0),
            "survivors": len([p for p in battle.users if not p.is_eliminated]),
            "total_damage_dealt": 0,
            "most_damage_dealer": None,
            "most_damage_taken": None
        }
        
        # 데미지 통계 계산
        max_damage_dealt = 0
        max_damage_taken = 0
        
        all_players = battle.users + ([battle.admin] if battle.admin else [])
        
        for player in all_players:
            summary["total_damage_dealt"] += player.hits_dealt
            
            if player.hits_dealt > max_damage_dealt:
                max_damage_dealt = player.hits_dealt
                summary["most_damage_dealer"] = player.real_name
            
            if player.hits_received > max_damage_taken:
                max_damage_taken = player.hits_received
                summary["most_damage_taken"] = player.real_name
        
        return summary

# ===== 전투 설정 클래스 =====

class BattleSettings:
    """전투 설정 관리 클래스"""
    
    def __init__(self):
        self.default_health = 10
        self.max_health = 100
        self.min_health = 1
        self.max_participants = 20
        self.battle_timeout = 9000  # 1시간
        self.round_timeout = 1200    # 5분
        self.dice_timeout = 1200      # 1분
        
        # 스킬 시스템 설정
        self.skill_enabled = SKILL_SYSTEM_AVAILABLE
        self.skill_round_limit = 10
        self.skill_max_concurrent = 5
    
    def validate_battle_config(self, config: Dict) -> Tuple[bool, str]:
        """전투 설정 검증"""
        if config.get("participants", 0) > self.max_participants:
            return False, f"참가자는 최대 {self.max_participants}명까지 가능합니다."
        
        if config.get("health", 0) > self.max_health:
            return False, f"체력은 최대 {self.max_health}까지 설정 가능합니다."
        
        if config.get("health", 0) < self.min_health:
            return False, f"체력은 최소 {self.min_health} 이상이어야 합니다."
        
        return True, "설정이 유효합니다."

# ===== 전투 통계 클래스 =====

class BattleStatistics:
    """전투 통계 관리 클래스"""
    
    def __init__(self):
        self.total_battles = 0
        self.total_rounds = 0
        self.user_wins = 0
        self.admin_wins = 0
        self.team_battles = 0
        self.skill_usages = {}
    
    def record_battle_result(self, battle: MultiUserBattle, winner: str):
        """전투 결과 기록"""
        self.total_battles += 1
        self.total_rounds += battle.current_round
        
        if winner == "users":
            self.user_wins += 1
        elif winner == "admin":
            self.admin_wins += 1
        # "timeout", "draw" 등은 별도 카운트하지 않음
        
        if battle.is_team_battle:
            self.team_battles += 1
    
    def record_skill_usage(self, skill_name: str):
        """스킬 사용 기록"""
        if skill_name not in self.skill_usages:
            self.skill_usages[skill_name] = 0
        self.skill_usages[skill_name] += 1
    
    def get_statistics_summary(self) -> Dict[str, Any]:
        """통계 요약 반환"""
        return {
            "total_battles": self.total_battles,
            "average_rounds": self.total_rounds / max(self.total_battles, 1),
            "user_win_rate": self.user_wins / max(self.total_battles, 1) * 100,
            "admin_win_rate": self.admin_wins / max(self.total_battles, 1) * 100,
            "team_battle_ratio": self.team_battles / max(self.total_battles, 1) * 100,
            "most_used_skill": max(self.skill_usages, key=self.skill_usages.get) if self.skill_usages else None
        }

# ===== 전역 인스턴스들 =====
admin_battle_commands = AdminBattleCommands(admin_battle_manager)
battle_event_handler = BattleEventHandler(admin_battle_manager)
battle_settings = BattleSettings()
battle_statistics = BattleStatistics()

# ===== 백그라운드 태스크 관리 =====
cleanup_task = None  # 정리 작업 태스크 참조

# ===== 추가 유틸리티 함수들 =====

async def cleanup_expired_battles():
    """만료된 전투들 정리"""
    current_time = datetime.now()
    expired_battles = []
    
    for channel_id, battle in admin_battle_manager.active_battles.items():
        if hasattr(battle, 'created_at'):
            if (current_time - battle.created_at).seconds > battle_settings.battle_timeout:
                expired_battles.append(channel_id)
    
    for channel_id in expired_battles:
        battle = admin_battle_manager.active_battles[channel_id]
        
        # 만료 알림 전송
        if battle.message:
            embed = discord.Embed(
                title="⏰ 전투 시간 만료",
                description="전투가 시간 초과로 자동 종료되었습니다.",
                color=discord.Color.orange()
            )
            await battle.message.channel.send(embed=embed)
        
        # 스킬 시스템 정리
        if SKILL_SYSTEM_AVAILABLE and skill_manager:
            skill_manager.end_battle(str(channel_id))
        
        # 전투 제거
        del admin_battle_manager.active_battles[channel_id]

def get_battle_info_for_skills(channel_id: str) -> Optional[Dict[str, Any]]:
    """스킬 시스템용 전투 정보 조회"""
    try:
        battle = admin_battle_manager.get_battle(int(channel_id))
        if not battle:
            return None
        
        return {
            "channel_id": channel_id,
            "current_round": battle.current_round,
            "phase": battle.phase.value,
            "is_active": battle.is_active,
            "participants": len(battle.users) + (1 if battle.admin else 0),
            "monster_name": battle.monster_name,
            "is_team_battle": battle.is_team_battle
        }
    except Exception as e:
        logger.error(f"전투 정보 조회 실패 {channel_id}: {e}")
        return None

# ===== 메인 초기화 함수 =====

async def initialize_battle_system():
    """전투 시스템 초기화"""
    global cleanup_task
    
    logger.info("Admin 전투 시스템 초기화 중...")
    
    # 스킬 시스템 연동 확인
    if SKILL_SYSTEM_AVAILABLE:
        logger.info("스킬 시스템과 연동됨")
        
        # 스킬 시스템에 콜백 함수 등록
        try:
            from skills.skill_manager import register_battle_callbacks
            register_battle_callbacks({
                "get_battle_participants": get_battle_participants,
                "get_user_info": get_user_info,
                "send_battle_message": send_battle_message,
                "damage_user": damage_user,
                "heal_user": heal_user,
                "revive_user": revive_user,
                "update_battle_display": update_battle_display
            })
            logger.info("스킬 시스템 콜백 함수 등록 완료")
        except Exception as e:
            logger.warning(f"스킬 시스템 콜백 등록 실패: {e}")
    else:
        logger.info("스킬 시스템 없이 실행")
    
    # 주기적 정리 작업 시작
    if cleanup_task is None or cleanup_task.done():
        cleanup_task = asyncio.create_task(periodic_cleanup())
        logger.info("주기적 정리 작업 시작됨")
    
    logger.info("Admin 전투 시스템 초기화 완료")

async def shutdown_battle_system():
    """전투 시스템 종료"""
    global cleanup_task
    
    logger.info("Admin 전투 시스템 종료 중...")
    
    # 정리 작업 태스크 중단
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("주기적 정리 작업 중단됨")
    
    # 모든 활성 전투 종료
    active_channels = list(admin_battle_manager.active_battles.keys())
    for channel_id in active_channels:
        try:
            # 스킬 시스템에 전투 종료 알림
            if SKILL_SYSTEM_AVAILABLE and skill_manager:
                skill_manager.end_battle(str(channel_id))
            
            # 전투 제거
            del admin_battle_manager.active_battles[channel_id]
            
        except Exception as e:
            logger.error(f"전투 {channel_id} 종료 실패: {e}")
    
    logger.info("Admin 전투 시스템 종료 완료")

async def periodic_cleanup():
    """주기적 정리 작업"""
    logger.info("주기적 정리 작업 시작")
    
    while True:
        try:
            current_time = datetime.now()
            cleanup_count = 0
            
            # 만료된 전투들 정리
            expired_battles = []
            
            for channel_id, battle in list(admin_battle_manager.active_battles.items()):
                # 전투 생성 시간이 없는 경우 현재 시간으로 설정
                if not hasattr(battle, 'created_at'):
                    battle.created_at = current_time
                    continue
                
                # 만료 시간 계산
                battle_duration = (current_time - battle.created_at).total_seconds()
                
                # 전투 시간 초과 체크
                if battle_duration > battle_settings.battle_timeout:
                    expired_battles.append(channel_id)
                    continue
                
                # 대기 상태에서 너무 오래된 전투 체크
                if battle.phase == BattlePhase.WAITING and battle_duration > 600:  # 5분
                    expired_battles.append(channel_id)
                    continue
                
                # pending_dice가 너무 오래된 경우 체크
                if (battle.pending_dice and 
                    hasattr(battle, 'last_dice_time') and 
                    (current_time - battle.last_dice_time).total_seconds() > battle_settings.dice_timeout):
                    
                    # 주사위 대기 시간 초과 처리
                    try:
                        if battle.message:
                            await battle.message.channel.send(
                                "⏰ 주사위 대기 시간이 초과되어 해당 플레이어들의 턴을 넘깁니다."
                            )
                        
                        # 대기 중인 플레이어들을 0으로 처리
                        for user_id in battle.pending_dice.get("waiting_for", []):
                            battle.pending_dice["results"][user_id] = 0
                        
                        battle.pending_dice["waiting_for"] = []
                        
                        # 결과 처리
                        if battle.pending_dice["phase"] == "init":
                            await admin_battle_manager._process_init_results(channel_id)
                        else:
                            await admin_battle_manager._process_combat_results(channel_id)
                            
                    except Exception as e:
                        logger.error(f"주사위 시간 초과 처리 실패 {channel_id}: {e}")
                        expired_battles.append(channel_id)
            
            # 만료된 전투들 정리
            for channel_id in expired_battles:
                try:
                    battle = admin_battle_manager.active_battles[channel_id]
                    
                    # 만료 알림 전송
                    if battle.message:
                        embed = discord.Embed(
                            title="⏰ 전투 시간 만료",
                            description="전투가 시간 초과로 자동 종료되었습니다.",
                            color=discord.Color.orange()
                        )
                        
                        # 전투 통계 추가
                        if battle.current_round > 0:
                            embed.add_field(
                                name="전투 정보",
                                value=f"진행된 라운드: {battle.current_round}\n"
                                      f"참여자: {len(battle.users) + (1 if battle.admin else 0)}명",
                                inline=False
                            )
                        
                        await battle.message.channel.send(embed=embed)
                    
                    # 스킬 시스템에 전투 종료 알림
                    if SKILL_SYSTEM_AVAILABLE and skill_manager:
                        skill_manager.end_battle(str(channel_id))
                    
                    # 전투 통계 기록
                    battle_statistics.record_battle_result(battle, "timeout")
                    
                    # 전투 제거
                    del admin_battle_manager.active_battles[channel_id]
                    cleanup_count += 1
                    
                    logger.info(f"만료된 전투 정리 완료: {channel_id}")
                    
                except Exception as e:
                    logger.error(f"전투 {channel_id} 정리 실패: {e}")
            
            # 스킬 시스템 정리 작업
            if SKILL_SYSTEM_AVAILABLE and skill_manager:
                try:
                    # 만료된 스킬들 정리 (스킬 매니저에서 제공하는 경우)
                    if hasattr(skill_manager, 'cleanup_expired_skills'):
                        expired_skills_count = await skill_manager.cleanup_expired_skills()
                        if expired_skills_count > 0:
                            logger.info(f"만료된 스킬 {expired_skills_count}개 정리 완료")
                            
                except Exception as e:
                    logger.error(f"스킬 시스템 정리 실패: {e}")
            
            # 전투 기록 정리 (오래된 기록 제거)
            max_history_size = 100
            if len(admin_battle_manager.battle_history) > max_history_size:
                removed_count = len(admin_battle_manager.battle_history) - max_history_size
                # deque이므로 자동으로 오래된 것부터 제거됨
                logger.info(f"오래된 전투 기록 {removed_count}개 정리 완료")
            
            # 정리 작업 결과 로깅
            if cleanup_count > 0:
                logger.info(f"정리 작업 완료: 전투 {cleanup_count}개 정리됨")
            
            # 5분마다 실행
            await asyncio.sleep(300)
            
        except asyncio.CancelledError:
            logger.info("주기적 정리 작업이 취소되었습니다")
            break
        except Exception as e:
            logger.error(f"정리 작업 실패: {e}")
            # 오류 시 1분 후 재시도
            await asyncio.sleep(60)
    
    logger.info("주기적 정리 작업 종료")

async def emergency_cleanup():
    """응급 정리 작업 (시스템 종료 시 등)"""
    logger.info("응급 정리 작업 시작")
    
    try:
        # 모든 활성 전투에 종료 메시지 전송
        for channel_id, battle in list(admin_battle_manager.active_battles.items()):
            try:
                if battle.message:
                    embed = discord.Embed(
                        title="🔄 시스템 재시작",
                        description="시스템 점검으로 인해 전투가 일시 중단됩니다.\n곧 복구될 예정입니다.",
                        color=discord.Color.blue()
                    )
                    await battle.message.channel.send(embed=embed)
                
                # 스킬 시스템 정리
                if SKILL_SYSTEM_AVAILABLE and skill_manager:
                    skill_manager.end_battle(str(channel_id))
                
            except Exception as e:
                logger.error(f"전투 {channel_id} 응급 정리 실패: {e}")
        
        # 모든 전투 데이터 백업 (필요한 경우)
        if admin_battle_manager.active_battles:
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "active_battles": len(admin_battle_manager.active_battles),
                "battle_statistics": battle_statistics.get_statistics_summary()
            }
            logger.info(f"전투 데이터 백업: {backup_data}")
        
        # 전투 목록 클리어
        admin_battle_manager.active_battles.clear()
        
        logger.info("응급 정리 작업 완료")
        
    except Exception as e:
        logger.error(f"응급 정리 작업 실패: {e}")

# ===== 상태 모니터링 함수들 =====

def get_system_status() -> Dict[str, Any]:
    """시스템 상태 조회"""
    return {
        "active_battles": len(admin_battle_manager.active_battles),
        "total_battles_recorded": battle_statistics.total_battles,
        "cleanup_task_running": cleanup_task is not None and not cleanup_task.done(),
        "skill_system_available": SKILL_SYSTEM_AVAILABLE,
        "system_uptime": datetime.now().isoformat(),
        "battle_timeout": battle_settings.battle_timeout,
        "max_participants": battle_settings.max_participants
    }

async def health_check() -> bool:
    """시스템 헬스 체크"""
    try:
        # 기본 시스템 체크
        if not admin_battle_manager:
            return False
        
        # 정리 작업 태스크 체크
        if cleanup_task is None or cleanup_task.done():
            logger.warning("정리 작업 태스크가 중단됨, 재시작 시도")
            global cleanup_task
            cleanup_task = asyncio.create_task(periodic_cleanup())
        
        # 스킬 시스템 체크
        if SKILL_SYSTEM_AVAILABLE:
            if not skill_manager:
                logger.warning("스킬 시스템 연결 문제 감지")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return False

# ===== 디버그 및 관리 함수들 =====

async def force_cleanup_battle(channel_id: int, reason: str = "Manual cleanup") -> bool:
    """특정 전투 강제 정리"""
    try:
        if channel_id not in admin_battle_manager.active_battles:
            return False
        
        battle = admin_battle_manager.active_battles[channel_id]
        
        # 정리 메시지 전송
        if battle.message:
            embed = discord.Embed(
                title="🛠️ 전투 강제 종료",
                description=f"관리자에 의해 전투가 종료되었습니다.\n사유: {reason}",
                color=discord.Color.red()
            )
            await battle.message.channel.send(embed=embed)
        
        # 스킬 시스템 정리
        if SKILL_SYSTEM_AVAILABLE and skill_manager:
            skill_manager.end_battle(str(channel_id))
        
        # 전투 제거
        del admin_battle_manager.active_battles[channel_id]
        
        logger.info(f"전투 {channel_id} 강제 정리 완료: {reason}")
        return True
        
    except Exception as e:
        logger.error(f"전투 {channel_id} 강제 정리 실패: {e}")
        return False

def get_battle_debug_info(channel_id: int) -> Optional[Dict[str, Any]]:
    """전투 디버그 정보 조회"""
    try:
        battle = admin_battle_manager.active_battles.get(channel_id)
        if not battle:
            return None
        
        return {
            "channel_id": channel_id,
            "battle_name": battle.battle_name,
            "phase": battle.phase.value,
            "current_round": battle.current_round,
            "participants": len(battle.users) + (1 if battle.admin else 0),
            "eliminated_count": len([p for p in battle.users if p.is_eliminated]),
            "pending_dice": bool(battle.pending_dice),
            "waiting_for": battle.pending_dice.get("waiting_for", []) if battle.pending_dice else [],
            "is_team_battle": battle.is_team_battle,
            "health_sync": battle.health_sync,
            "created_at": getattr(battle, 'created_at', None),
            "monster_name": battle.monster_name
        }
        
    except Exception as e:
        logger.error(f"전투 디버그 정보 조회 실패 {channel_id}: {e}")
        return None
