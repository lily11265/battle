import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re
from dice_system import dice_system  # 기존 주사위 시스템
from battle_utils import extract_health_from_nickname, update_nickname_health, extract_real_name
from mob_ai import MobAI, AIPersonality, create_mob_ai, AutonomousAIController, ActionType, CombatAction, DifficultyManager


logger = logging.getLogger(__name__)

# 권한 있는 유저 ID
AUTHORIZED_USERS = ["1007172975222603798", "1090546247770832910"]
AUTHORIZED_NICKNAME = "system|시스템"

@dataclass
class BattleDialogue:
    """전투 대사 관리"""
    battle_start: str = ""
    health_75: str = ""
    health_50: str = ""
    health_25: str = ""
    health_0: str = ""
    enemy_killed: str = ""
    enemy_avg_50: str = ""
    enemy_all_killed: str = ""

@dataclass
class MobRecoverySettings:
    """몹 회복 설정"""
    enabled: bool = False  # 회복 사용 가능 여부 추가
    health_threshold: int = 0  # 체력이 이 값 이하일 때 회복
    dice_max: int = 0  # 회복 주사위 최댓값
    has_used: bool = False  # 이미 사용했는지

@dataclass
class DiceResult:
    """다이스 결과"""
    player_name: str
    dice_value: int
    user_id: Optional[int] = None

@dataclass
class AutoBattlePlayer:
    """자동 전투 참가자"""
    user: discord.Member
    real_name: str
    max_health: int = 10
    current_health: int = 10
    real_max_health: int = 100
    real_current_health: int = 100
    is_eliminated: bool = False
    has_acted_this_turn: bool = False
    hits_received: int = 0
    hits_dealt: int = 0
    last_nickname_update: Optional[datetime] = None
    nickname_update_failed: bool = False
    
    def take_damage(self, battle_damage: int, real_damage: int):
        """피해 적용"""
        self.current_health -= battle_damage
        self.real_current_health -= real_damage
        self.hits_received += battle_damage
        self.last_damage_time = datetime.now()  # 추가
        if self.current_health <= 0:
            self.current_health = 0
            self.real_current_health = 0
            self.is_eliminated = True

    def heal(self, battle_heal: int, real_heal: int):
        """회복 적용 (체력 동기화 고려)"""
        # 실제 체력 회복
        self.real_current_health = min(self.real_current_health + real_heal, self.real_max_health)
        
        # 전투 체력 회복 (실제 회복량을 10으로 나눠서 전투 체력 계산)
        actual_battle_heal = real_heal // 10
        self.current_health = min(self.current_health + actual_battle_heal, self.max_health)
        
        # hits_received 감소
        if actual_battle_heal > 0:
            self.hits_received = max(0, self.hits_received - actual_battle_heal)

    def __hash__(self):
        """플레이어를 hashable하게 만들기 위한 메서드"""
        return hash(self.user.id)

    def __eq__(self, other):
        """플레이어 동등성 비교"""
        if not isinstance(other, AutoBattlePlayer):
            return False
        return self.user.id == other.user.id
@dataclass
class AutoBattle:
    """자동 전투 정보 (AI 통합)"""
    mob_name: str
    mob_health: int
    mob_real_health: int
    health_sync: bool
    channel: discord.TextChannel
    creator: discord.Member
    players: List[AutoBattlePlayer] = field(default_factory=list)
    dialogue: BattleDialogue = field(default_factory=BattleDialogue)
    recovery_settings: MobRecoverySettings = field(default_factory=MobRecoverySettings)
    is_active: bool = True
    mob_current_health: int = 0
    mob_real_current_health: int = 0
    round_count: int = 0
    battle_log: List[str] = field(default_factory=list)
    turn_order: List[str] = field(default_factory=list)  # 턴 순서
    current_turn_index: int = 0
    pending_action: Optional[Dict] = None  # 대기 중인 행동
    dialogue_set: bool = False  # 대사 설정 완료 여부
    main_message: Optional[discord.Message] = None  # 메인 전투 상태 메시지
    timeout_task: Optional[asyncio.Task] = None  # 타임아웃 태스크
        # AI 회복 관련 필드 추가
    ai_recovery_count: int = 0  # AI가 사용한 회복 횟수
    ai_max_recovery: int = 3    # AI 최대 회복 횟수 (기본값 3)

    # AI 관련 필드
    mob_ai: Optional[MobAI] = None  # AI 인스턴스
    ai_controller: Optional[AutonomousAIController] = None  # AI 컨트롤러
    ai_personality: str = "tactical"  # AI 성격
    ai_difficulty: str = "normal"  # AI 난이도
    
    # 집중공격 정보 추가
    focused_attack: Optional[Dict] = None
    
    # battle_admin 호환성을 위한 필드 추가
    users: List[AutoBattlePlayer] = field(default_factory=list)  # players와 같음

    # AI 회복 관련 필드 추가
    ai_recovery_count: int = 0  # AI가 사용한 회복 횟수
    ai_max_recovery: int = 3    # AI 최대 회복 횟수 (기본값 3)
    
    def __post_init__(self):
        self.mob_current_health = self.mob_health
        self.mob_real_current_health = self.mob_real_health
        self.users = self.players  # AI 호환성
        
        # AI 난이도와 성격에 따른 회복 횟수 설정
        recovery_by_difficulty = {
            'easy': 2,      # 쉬움: 2회
            'normal': 3,    # 보통: 3회
            'hard': 4,      # 어려움: 4회
            'nightmare': 5  # 악몽: 5회
        }
        
        personality_modifier = {
            'defensive': 1,      # 방어적: +1회
            'berserker': -1,     # 광전사: -1회
            'tactical': 0,       # 전술적: 변화 없음
            'aggressive': -1,    # 공격적: -1회
            'opportunist': 0     # 기회주의: 변화 없음
        }
        
        base_recovery = recovery_by_difficulty.get(self.ai_difficulty, 3)
        modifier = personality_modifier.get(self.ai_personality, 0)
        
        # 최소 2회, 최대 5회로 제한
        self.ai_max_recovery = max(2, min(5, base_recovery + modifier))

    def mob_heal(self, battle_heal: int, real_heal: int):
        """몹 회복"""
        self.mob_current_health = min(self.mob_current_health + battle_heal, self.mob_health)
        self.mob_real_current_health = min(self.mob_real_current_health + real_heal, self.mob_real_health)
        
        # AI 체력 업데이트
        if self.mob_ai:
            self.mob_ai.mob_current_health = self.mob_current_health

    def mob_take_damage(self, battle_damage: int, real_damage: int):
        """몹 피해 받기"""
        self.mob_current_health = max(0, self.mob_current_health - battle_damage)
        self.mob_real_current_health = max(0, self.mob_real_current_health - real_damage)
        
        # AI 체력 업데이트
        if self.mob_ai:
            self.mob_ai.take_damage(battle_damage)

# AI 설정 모달들
class MobAISettingModal(discord.ui.Modal):
    """AI 설정 모달"""
    def __init__(self, battle: AutoBattle):
        super().__init__(title="몹 AI 설정")
        self.battle = battle
        
        self.personality = discord.ui.TextInput(
            label="AI 성격",
            placeholder="tactical/aggressive/defensive/berserker/opportunist",
            default="tactical",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.personality)
        
        self.difficulty = discord.ui.TextInput(
            label="AI 난이도",
            placeholder="easy/normal/hard/nightmare",
            default="normal",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.difficulty)
    
    async def on_submit(self, interaction: discord.Interaction):
        # AI 성격 검증
        valid_personalities = ["tactical", "aggressive", "defensive", "berserker", "opportunist"]
        if self.personality.value.lower() not in valid_personalities:
            await interaction.response.send_message(
                f"올바른 AI 성격을 입력해주세요: {', '.join(valid_personalities)}", 
                ephemeral=True
            )
            return
        
        # 난이도 검증
        valid_difficulties = ["easy", "normal", "hard", "nightmare"]
        if self.difficulty.value.lower() not in valid_difficulties:
            await interaction.response.send_message(
                f"올바른 난이도를 입력해주세요: {', '.join(valid_difficulties)}", 
                ephemeral=True
            )
            return
        
        self.battle.ai_personality = self.personality.value.lower()
        self.battle.ai_difficulty = self.difficulty.value.lower()
        
        # AI 인스턴스 생성
        self.battle.mob_ai = create_mob_ai(
            self.battle.mob_name,
            self.battle.mob_health,
            self.battle.ai_personality,
            self.battle.ai_difficulty
        )
        self.battle.ai_controller = AutonomousAIController(self.battle.mob_ai)
        
        # AI 설정 표시
        personality_names = {
            "tactical": "전술적",
            "aggressive": "공격적",
            "defensive": "방어적",
            "berserker": "광전사",
            "opportunist": "기회주의"
        }
        
        difficulty_names = {
            "easy": "쉬움",
            "normal": "보통",
            "hard": "어려움",
            "nightmare": "악몽"
        }
        
        await interaction.response.send_message(
            f"✅ AI 설정 완료!\n"
            f"**성격**: {personality_names.get(self.battle.ai_personality, self.battle.ai_personality)}\n"
            f"**난이도**: {difficulty_names.get(self.battle.ai_difficulty, self.battle.ai_difficulty)}",
            ephemeral=True
        )

class MobDialogueModal(discord.ui.Modal):
    """전투 대사 설정 모달 1"""
    def __init__(self, battle: AutoBattle, view):
        super().__init__(title="몹 전투 대사 설정 (1/2)")
        self.battle = battle
        self.view = view
        
        self.battle_start = discord.ui.TextInput(
            label="전투 시작 대사",
            placeholder="전투가 시작될 때 몹이 할 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.battle_start)
        
        self.health_75 = discord.ui.TextInput(
            label="체력 75% 대사",
            placeholder="몹 체력이 75%가 되었을 때 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.health_75)
        
        self.health_50 = discord.ui.TextInput(
            label="체력 50% 대사",
            placeholder="몹 체력이 50%가 되었을 때 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.health_50)
        
        self.health_25 = discord.ui.TextInput(
            label="체력 25% 대사",
            placeholder="몹 체력이 25%가 되었을 때 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.health_25)
        
        self.health_0 = discord.ui.TextInput(
            label="체력 0% 대사",
            placeholder="몹이 쓰러질 때 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.health_0)
    
    async def on_submit(self, interaction: discord.Interaction):
        # 첫 번째 모달 데이터 저장
        self.battle.dialogue.battle_start = self.battle_start.value
        self.battle.dialogue.health_75 = self.health_75.value
        self.battle.dialogue.health_50 = self.health_50.value
        self.battle.dialogue.health_25 = self.health_25.value
        self.battle.dialogue.health_0 = self.health_0.value
        
        # 응답 후 두 번째 버튼 활성화
        await interaction.response.send_message("첫 번째 대사 설정 완료! 두 번째 대사 설정 버튼을 눌러주세요.", ephemeral=True)
        
        # 뷰에 두 번째 대사 버튼 추가
        self.view.add_second_dialogue_button()
        await self.view.message.edit(view=self.view)

class MobDialogueModal2(discord.ui.Modal):
    """전투 대사 설정 모달 2"""
    def __init__(self, battle: AutoBattle):
        super().__init__(title="몹 전투 대사 설정 (2/2)")
        self.battle = battle
        
        self.enemy_killed = discord.ui.TextInput(
            label="적 처치 대사",
            placeholder="상대 유저가 쓰러졌을 때 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.enemy_killed)
        
        self.enemy_avg_50 = discord.ui.TextInput(
            label="적 평균 체력 50% 대사",
            placeholder="상대팀 평균 체력이 50%일 때 대사",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.enemy_avg_50)
        
        self.enemy_all_killed = discord.ui.TextInput(
            label="적 전멸 대사",
            placeholder="상대팀이 전멸했을 때 대사",
            required=False,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.enemy_all_killed)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.battle.dialogue.enemy_killed = self.enemy_killed.value
        self.battle.dialogue.enemy_avg_50 = self.enemy_avg_50.value
        self.battle.dialogue.enemy_all_killed = self.enemy_all_killed.value
        self.battle.dialogue_set = True
        
        await interaction.response.send_message("전투 대사가 모두 설정되었습니다!", ephemeral=True)

class MobRecoveryModal(discord.ui.Modal):
    """몹 회복 설정 모달"""
    def __init__(self, battle: AutoBattle):
        super().__init__(title="몹 회복 설정")
        self.battle = battle
        
        # 회복 유무 필드 추가
        self.recovery_enabled = discord.ui.TextInput(
            label="회복 유무",
            placeholder="true 또는 false 입력",
            required=True,
            style=discord.TextStyle.short,
            max_length=5
        )
        self.add_item(self.recovery_enabled)
        
        self.health_threshold = discord.ui.TextInput(
            label="회복 발동 체력",
            placeholder="체력이 몇 이하일 때 회복할까요? (예: 5)",
            required=True,
            style=discord.TextStyle.short,
            max_length=3
        )
        self.add_item(self.health_threshold)
        
        self.dice_max = discord.ui.TextInput(
            label="회복 주사위 최댓값",
            placeholder="1d? 주사위를 굴릴까요? (예: 100)",
            required=True,
            style=discord.TextStyle.short,
            max_length=3
        )
        self.add_item(self.dice_max)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # 회복 유무 파싱
            recovery_enabled_str = self.recovery_enabled.value.lower()
            if recovery_enabled_str not in ['true', 'false']:
                await interaction.response.send_message("회복 유무는 true 또는 false로 입력해주세요.", ephemeral=True)
                return
            
            enabled = recovery_enabled_str == 'true'
            threshold = int(self.health_threshold.value)
            dice_max = int(self.dice_max.value)
            
            if threshold <= 0 or threshold > self.battle.mob_health:
                await interaction.response.send_message("올바른 체력 값을 입력해주세요.", ephemeral=True)
                return
            
            if dice_max <= 0:
                await interaction.response.send_message("주사위 최댓값은 1 이상이어야 합니다.", ephemeral=True)
                return
            
            self.battle.recovery_settings.enabled = enabled
            self.battle.recovery_settings.health_threshold = threshold
            self.battle.recovery_settings.dice_max = dice_max
            
            if enabled:
                await interaction.response.send_message(
                    f"몹 회복 설정 완료!\n"
                    f"회복 활성화: ✅\n"
                    f"체력이 {threshold} 이하일 때 1d{dice_max} 회복을 시도합니다.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"몹 회복 설정 완료!\n"
                    f"회복 비활성화: ❌\n"
                    f"몬스터는 회복을 사용할 수 없습니다.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message("숫자를 입력해주세요.", ephemeral=True)


class MobSettingView(discord.ui.View):
    """몹 세팅 뷰 (AI 통합)"""
    def __init__(self, battle: AutoBattle):
        super().__init__(timeout=300)
        self.battle = battle
        self.message = None
        self.dialogue_button_2 = None
    
    @discord.ui.button(label="참가", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def join_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """전투 참가"""
        # 이미 참가한 유저인지 확인
        if any(p.user.id == interaction.user.id for p in self.battle.players):
            await interaction.response.send_message("이미 전투에 참가하셨습니다!", ephemeral=True)
            return
        
        # 닉네임에서 실제 이름 추출
        real_name = extract_real_name(interaction.user.display_name)
        
        # 체력 동기화 처리
        real_health = extract_health_from_nickname(interaction.user.display_name) or 100
        
        if self.battle.health_sync:
            battle_health = max(1, real_health // 10)
            max_battle_health = 10  # 항상 10
        else:
            battle_health = 10
            max_battle_health = 10
        
        player = AutoBattlePlayer(
            user=interaction.user,
            real_name=real_name,
            max_health=max_battle_health,
            current_health=battle_health,
            real_max_health=100,  # 항상 100
            real_current_health=real_health
        )
        
        self.battle.players.append(player)
        self.battle.users = self.battle.players  # AI 호환성
        
        # 참가자 목록 업데이트
        embed = self.create_setup_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    #@discord.ui.button(label="AI 설정", style=discord.ButtonStyle.secondary, emoji="🤖")
    #async def set_ai(self, interaction: discord.Interaction, button: discord.ui.Button):
    #    """AI 설정 (권한 체크)"""
    #    if interaction.user.id != self.battle.creator.id:
    #        await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
    #        return
        
    #    modal = MobAISettingModal(self.battle)
    #    await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="전투 대사 설정 (1/2)", style=discord.ButtonStyle.secondary, emoji="💬")
    async def set_dialogue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """전투 대사 설정 (권한 체크)"""
        if interaction.user.id != self.battle.creator.id:
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        modal = MobDialogueModal(self.battle, self)
        await interaction.response.send_modal(modal)
    
    def add_second_dialogue_button(self):
        """두 번째 대사 설정 버튼 추가"""
        if not self.dialogue_button_2:
            self.dialogue_button_2 = discord.ui.Button(
                label="전투 대사 설정 (2/2)",
                style=discord.ButtonStyle.secondary,
                emoji="💬"
            )
            self.dialogue_button_2.callback = self.set_dialogue_2
            self.add_item(self.dialogue_button_2)
    
    async def set_dialogue_2(self, interaction: discord.Interaction):
        """두 번째 대사 설정"""
        if interaction.user.id != self.battle.creator.id:
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        modal = MobDialogueModal2(self.battle)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="몹 회복 설정", style=discord.ButtonStyle.secondary, emoji="💚")
    async def set_recovery(self, interaction: discord.Interaction, button: discord.ui.Button):
        """몹 회복 설정"""
        if interaction.user.id != self.battle.creator.id:
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        modal = MobRecoveryModal(self.battle)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="전투 시작", style=discord.ButtonStyle.success, emoji="🎯")
    async def start_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """전투 시작"""
        if interaction.user.id != self.battle.creator.id:
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        if not self.battle.players:
            await interaction.response.send_message("참가자가 없습니다!", ephemeral=True)
            return
        
        # AI가 설정되지 않았으면 기본값으로 생성
        if not self.battle.mob_ai:
            self.battle.mob_ai = create_mob_ai(
                self.battle.mob_name,
                self.battle.mob_health,
                "tactical",
                "normal"
            )
            self.battle.ai_controller = AutonomousAIController(self.battle.mob_ai)
        
        # 버튼 비활성화
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(view=self)
        
        # 전투 시작
        await self.run_battle(interaction)
    
    @discord.ui.button(label="전투 취소", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        """전투 취소"""
        if interaction.user.id != self.battle.creator.id:
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        self.battle.is_active = False
        await interaction.response.edit_message(content="전투가 취소되었습니다.", embed=None, view=None)
        
        # 전투 제거
        if hasattr(interaction.client, 'mob_battles'):
            interaction.client.mob_battles.pop(self.battle.channel.id, None)
        self.stop()
    
    def create_setup_embed(self) -> discord.Embed:
        """설정 임베드 생성"""
        embed = discord.Embed(
            title=f"⚔️ 자동 전투 설정: {self.battle.mob_name}",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 몹 정보",
            value=f"**이름**: {self.battle.mob_name}\n"
                f"**체력**: {self.battle.mob_current_health}/{self.battle.mob_health} "
                f"(실제: {self.battle.mob_real_current_health}/{self.battle.mob_real_health})\n"
                f"**체력 동기화**: {'활성화' if self.battle.health_sync else '비활성화'}",
            inline=False
        )
        
        # AI 설정 표시
        if self.battle.mob_ai:
            personality_names = {
                "tactical": "전술적",
                "aggressive": "공격적",
                "defensive": "방어적",
                "berserker": "광전사",
                "opportunist": "기회주의"
            }
            
            difficulty_names = {
                "easy": "쉬움",
                "normal": "보통",
                "hard": "어려움",
                "nightmare": "악몽"
            }
            
            embed.add_field(
                name="🤖 AI 설정",
                value=f"**성격**: {personality_names.get(self.battle.ai_personality, self.battle.ai_personality)}\n"
                    f"**난이도**: {difficulty_names.get(self.battle.ai_difficulty, self.battle.ai_difficulty)}",
                inline=False
            )
        
        # 회복 설정 표시 수정
        if self.battle.recovery_settings.enabled:
            embed.add_field(
                name="💚 회복 설정",
                value=f"**회복 사용**: 활성화 ✅\n"
                    f"체력 {self.battle.recovery_settings.health_threshold} 이하일 때 "
                    f"1d{self.battle.recovery_settings.dice_max} 회복",
                inline=False
            )
        else:
            embed.add_field(
                name="💚 회복 설정",
                value="**회복 사용**: 비활성화 ❌",
                inline=False
            )
        
        if self.battle.players:
            player_list = "\n".join([f"• {p.real_name} (체력: {p.current_health}/{p.max_health})" 
                                    for p in self.battle.players])
            embed.add_field(
                name=f"👥 참가자 ({len(self.battle.players)}명)",
                value=player_list,
                inline=False
            )
        else:
            embed.add_field(
                name="👥 참가자",
                value="*참가자 없음*",
                inline=False
            )
        
        embed.set_footer(text="버튼을 눌러 참가하거나 전투를 시작하세요!")
        return embed

    async def roll_mob_dice_view(self, dice_type: str = "attack") -> int:
        """View에서 몬스터 주사위 굴림 (스킬 시스템 적용)"""
        from skills.skill_effects import skill_effects
        
        # 기본 주사위 값
        base_roll = random.randint(1, 100)
        
        # 스킬 효과 적용
        final_roll, skill_messages = await skill_effects.process_dice_roll(
            self.battle.mob_name,  # 몬스터 이름을 user_id로 사용
            base_roll,
            str(self.battle.channel.id)
        )
        
        # 스킬 메시지 출력
        if skill_messages:
            for msg in skill_messages:
                await self.battle.channel.send(msg)
        
        # 주사위 결과 메시지
        if final_roll != base_roll:
            await self.battle.channel.send(
                f"`{self.battle.mob_name}`님이 주사위를 굴려 **{base_roll}**이(가) 나왔습니다!\n"
                f"⚔️ 스킬 효과로 **{final_roll}**로 변경되었습니다!"
            )
        else:
            await self.battle.channel.send(
                f"`{self.battle.mob_name}`님이 주사위를 굴려 **{final_roll}**이(가) 나왔습니다!"
            )
        
        return final_roll

    def create_battle_status_embed(self) -> discord.Embed:
        """전투 상태 임베드 생성 (집중공격 정보 포함)"""
        embed = discord.Embed(
            title=f"⚔️ {self.battle.mob_name} 전투",
            description=f"**라운드 {self.battle.round_count}**",
            color=discord.Color.red()
        )
        
        # 몹 상태
        mob_health_bar = self.create_health_bar(self.battle.mob_current_health, self.battle.mob_health)
        mob_status = f"{mob_health_bar}\n체력: {self.battle.mob_current_health}/{self.battle.mob_health}"
        
        # 집중공격 상태 추가
        if self.battle.mob_ai:
            if self.battle.mob_ai.is_preparing_focused:
                mob_status += f"\n⚡ 집중공격 준비 중! ({self.battle.mob_ai.prepare_turns_left}턴 후)"
            elif self.battle.mob_ai.focused_attack_cooldown > 0:
                mob_status += f"\n⏳ 집중공격 쿨타임: {self.battle.mob_ai.focused_attack_cooldown}턴"
            
            # 남은 집중공격 횟수
            remaining = self.battle.mob_ai.max_focused_attacks - self.battle.mob_ai.focused_attack_count
            mob_status += f"\n💥 남은 집중공격: {remaining}/{self.battle.mob_ai.max_focused_attacks}회"
        
        embed.add_field(
            name=f"🎯 {self.battle.mob_name}",
            value=mob_status,
            inline=False
        )
        
        # 플레이어 상태
        for player in self.battle.players:
            if player.is_eliminated:
                status = "💀 탈락"
            else:
                health_bar = self.create_health_bar(player.current_health, player.max_health)
                status = f"{health_bar}\n체력: {player.current_health}/{player.max_health}"
            
            embed.add_field(
                name=player.real_name,
                value=status,
                inline=True
            )
        
        # 턴 순서 표시
        if self.battle.turn_order:
            current_turn = self.battle.turn_order[self.battle.current_turn_index % len(self.battle.turn_order)]
            embed.add_field(
                name="📋 턴 순서",
                value=" → ".join([f"**{name}**" if name == current_turn else name for name in self.battle.turn_order]),
                inline=False
            )
        
        return embed

    async def run_battle(self, interaction: discord.Interaction):
        """전투 실행"""
        self.battle.is_active = True
        
        # 봇의 mob_battles에 등록
        if not hasattr(interaction.client, 'mob_battles'):
            interaction.client.mob_battles = {}
        interaction.client.mob_battles[self.battle.channel.id] = self.battle
        
        # 전투 시작 메시지
        start_embed = discord.Embed(
            title=f"⚔️ {self.battle.mob_name} 전투 시작!",
            description=self.battle.dialogue.battle_start or f"{self.battle.mob_name}이(가) 나타났다!",
            color=discord.Color.red()
        )
        self.battle.main_message = await self.battle.channel.send(embed=start_embed)
        
        # 선공 결정
        await self.determine_initiative()

    async def _sync_player_recovery_from_nickname(self, battle: AutoBattle, player_name: str) -> bool:
        """닉네임에서 체력을 읽어 회복이 있었는지 확인하고 전투에 반영"""
        logger.info(f"[DEBUG] Syncing recovery for player: {player_name}")
        
        # 해당 플레이어 찾기
        target_player = None
        for player in battle.players:
            if player.real_name == player_name:
                target_player = player
                break
        
        if not target_player:
            logger.warning(f"[DEBUG] Player {player_name} not found")
            return False
        
        try:
            # ✅ 핵심 수정: Member 객체를 다시 fetch해서 최신 닉네임 가져오기
            fresh_member = await battle.channel.guild.fetch_member(target_player.user.id)
            current_nickname = fresh_member.display_name
            logger.info(f"[DEBUG] Fresh nickname from server: {current_nickname}")
            
            # 기존 저장된 닉네임과 비교
            old_nickname = target_player.user.display_name
            if old_nickname != current_nickname:
                logger.info(f"[DEBUG] Nickname changed: {old_nickname} -> {current_nickname}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Failed to fetch fresh member info: {e}")
            # fallback to cached nickname
            current_nickname = target_player.user.display_name
        
        logger.info(f"[DEBUG] Using nickname: {current_nickname}")
        
        try:
            import re
            
            # ✅ 수정된 정규식 패턴들 - 다양한 닉네임 형태 지원
            patterns = [
                r'/\s*(\d+)\s*/',        # /숫자/ 또는 / 숫자 / 형태 
                r'\|\s*(\d+)',           # | 숫자 형태 (예: 퓨어 메탈 | 100)
                r'/\s*(\d+)(?!\s*/)',    # / 숫자 형태 (슬래시 하나, 예: 유진석 / 100)
                r'(\d+)(?=\s*$)',        # 끝에 오는 숫자 (예: 벨사이르 드라켄리트 80)
            ]
            
            nickname_current_health = None
            
            # 각 패턴을 순서대로 시도
            for pattern in patterns:
                matches = re.findall(pattern, current_nickname)
                if matches:
                    nickname_current_health = int(matches[-1])  # 마지막 매칭된 숫자 사용
                    logger.info(f"[DEBUG] Health extracted using pattern '{pattern}': {nickname_current_health}")
                    break
            
            if nickname_current_health is None:
                logger.warning(f"[DEBUG] Could not extract health from nickname: {current_nickname}")
                return False
            
            stored_current_health = target_player.real_current_health
            
            logger.info(f"[DEBUG] Health comparison - nickname: {nickname_current_health}, stored: {stored_current_health}")
            
            # 회복 여부 확인 (닉네임 체력 > 저장된 체력)
            if nickname_current_health > stored_current_health:
                recovery_amount = nickname_current_health - stored_current_health
                logger.info(f"[DEBUG] Recovery detected! Amount: {recovery_amount}")
                
                # 전투 체력도 비례해서 회복 (실제체력:전투체력 = 100:10 비율)
                battle_recovery = max(1, recovery_amount // 10)  # 최소 1 회복
                
                # 체력 회복 적용
                target_player.heal(battle_recovery, recovery_amount)
                logger.info(f"[DEBUG] Applied recovery - battle: +{battle_recovery}, real: +{recovery_amount}")
                logger.info(f"[DEBUG] New health values - battle: {target_player.current_health}/{target_player.max_health}, real: {target_player.real_current_health}/{target_player.real_max_health}")
                
                # Member 객체도 업데이트
                target_player.user = fresh_member
                logger.info(f"[DEBUG] Updated player member object")
                
                # 전투 상태 업데이트 메시지
                await battle.channel.send(
                    f"💚 **{target_player.real_name}** 님이 회복했습니다! (+{recovery_amount} 체력)\n"
                    f"현재 체력: {target_player.real_current_health}/{target_player.real_max_health}"
                )
                
                # 메인 메시지 업데이트
                if battle.main_message:
                    try:
                        embed = self.create_battle_status_embed()
                        await battle.main_message.edit(embed=embed)
                    except Exception as e:
                        logger.error(f"[DEBUG] Failed to update main message: {e}")
                
                # 플레이어 턴이면 턴 완료 처리
                if (battle.pending_action and 
                    battle.pending_action.get("type") == "player_turn" and
                    battle.pending_action.get("player") == target_player):
                    
                    logger.info(f"[DEBUG] Completing player turn after recovery")
                    target_player.has_acted_this_turn = True
                    battle.current_turn_index += 1
                    battle.pending_action = None
                    await self.process_turn()
                
                return True
            else:
                logger.info(f"[DEBUG] No recovery detected (health unchanged)")
                return False
                
        except Exception as e:
            logger.error(f"[DEBUG] Error in recovery sync: {e}")
            return False

    async def determine_initiative(self):
        """선공 결정"""
        # 메인 메시지 업데이트
        await self.battle.main_message.edit(embed=self.create_battle_status_embed())
        
        # 텍스트로 안내
        waiting_for = [p.real_name for p in self.battle.players] + [self.battle.mob_name]
        self.battle.pending_action = {
            "type": "initiative",
            "waiting_for": waiting_for,
            "results": {}
        }
        
        await self.battle.channel.send(
            f"🎲 **선공 결정**\n"
            f"모든 참가자는 `/주사위` 명령어로 1d100을 굴려주세요!\n"
            f"대기 중: {', '.join(waiting_for)}"
        )
        
        # 몹 주사위 자동 굴림 (3초 후)
        await asyncio.sleep(3)
        mob_dice = random.randint(1, 100)
        await self.battle.channel.send(f"`{self.battle.mob_name}`님이 주사위를 굴려 **{mob_dice}**이(가) 나왔습니다!")
        
        # 몹 결과 저장
        self.battle.pending_action["results"][self.battle.mob_name] = mob_dice
        self.battle.pending_action["waiting_for"].remove(self.battle.mob_name)
        
        # 1분 타임아웃 설정
        self.battle.timeout_task = asyncio.create_task(self.check_timeout(60, "initiative"))
    
    async def check_timeout(self, timeout_seconds: int, phase: str):
        """타임아웃 체크"""
        await asyncio.sleep(timeout_seconds)
        
        if self.battle.pending_action and self.battle.pending_action.get("type") == phase:
            waiting_names = self.battle.pending_action.get("waiting_for", [])
            if waiting_names:
                await self.battle.channel.send(
                    f"⏰ **1분 타임아웃!**\n"
                    f"아직 주사위를 굴리지 않은 참가자: {', '.join(waiting_names)}\n"
                    f"주사위를 굴려주세요!"
                )
    
    async def start_combat_round(self):
        """전투 라운드 시작"""
        self.battle.round_count += 1
        
        # === 스킬 시스템 라운드 처리 추가 ===
        from skills.skill_manager import skill_manager
        channel_id = str(self.battle.channel.id)
        
        # 라운드 종료 시 스킬 처리
        if self.battle.round_count > 1:  # 첫 라운드가 아닌 경우
            expired_messages = await skill_manager.process_round_end(channel_id, self.battle.round_count - 1)
            
            # 만료된 스킬 메시지 출력
            for msg in expired_messages:
                await self.battle.channel.send(msg)
        
        # 체력 동기화
        await self.sync_health()
        
        # 라운드 시작 메시지
        await self.battle.channel.send(
            f"⚔️ **라운드 {self.battle.round_count} 시작!**\n"
            f"턴 순서: {' → '.join(self.battle.turn_order)}"
        )
        
        # 모든 플레이어의 행동 플래그 초기화
        for player in self.battle.players:
            player.has_acted_this_turn = False
        
        # 첫 턴 시작
        self.battle.current_turn_index = 0
        await self.process_turn()

    async def sync_health(self):
        """체력 동기화 - 전투 외부의 체력 변화만 감지"""
        logger.info(f"=== sync_health 시작 (라운드 {self.battle.round_count}) ===")
        
        for player in self.battle.players:
            if not player.is_eliminated:
                logger.info(f"\n플레이어: {player.real_name}")
                logger.info(f"  - 탈락 여부: {player.is_eliminated}")
                logger.info(f"  - 받은 피해: {player.hits_received}")
                logger.info(f"  - 실제 최대 체력: {player.real_max_health}")
                logger.info(f"  - 현재 실제 체력 (저장값): {player.real_current_health}")
                logger.info(f"  - 닉네임 업데이트 실패 여부: {getattr(player, 'nickname_update_failed', False)}")
                
                # 닉네임에서 체력 확인
                current_nickname_health = extract_health_from_nickname(player.user.display_name)
                logger.info(f"  - 닉네임에서 추출한 체력: {current_nickname_health}")
                logger.info(f"  - 현재 닉네임: {player.user.display_name}")
                
                if current_nickname_health is None:
                    logger.warning(f"  ⚠️ 닉네임에서 체력을 추출할 수 없음")
                    continue
                
                # 저장된 체력과 닉네임 체력이 같으면 정상
                if current_nickname_health == player.real_current_health:
                    logger.info(f"  ✅ 체력 동기화 정상 (둘 다 {current_nickname_health})")
                    continue
                
                health_diff = current_nickname_health - player.real_current_health
                
                # 닉네임이 더 높은 경우
                if health_diff > 0:
                    # 피해를 받은 적이 있는데 닉네임이 더 높다면 = 닉네임 업데이트 실패
                    if player.hits_received > 0:
                        logger.info(f"  ⚠️ 닉네임 업데이트 지연 감지 (저장값: {player.real_current_health}, 닉네임: {current_nickname_health})")
                        
                        # 강제로 닉네임 업데이트 재시도
                        try:
                            new_nickname = update_nickname_health(player.user.display_name, player.real_current_health)
                            await player.user.edit(nick=new_nickname)
                            logger.info(f"  ✅ 닉네임 재업데이트 성공: {new_nickname}")
                        except Exception as e:
                            logger.warning(f"  ❌ 닉네임 재업데이트 실패: {e}")
                    else:
                        # 피해를 받은 적이 없는데 체력이 올라감 = 실제 회복
                        logger.info(f"  💚 외부 회복 감지: +{health_diff}")
                        
                        await self.battle.channel.send(
                            f"💚 {player.real_name}의 체력이 회복되었습니다! "
                            f"(+{health_diff} → {current_nickname_health})"
                        )
                        
                        player.real_current_health = current_nickname_health
                        
                        if self.battle.health_sync:
                            heal_ratio = health_diff / 100
                            battle_heal = max(1, int(player.max_health * heal_ratio))
                            player.current_health = min(player.current_health + battle_heal, player.max_health)
                            player.hits_received = max(0, player.hits_received - battle_heal)
                
                # 닉네임이 더 낮은 경우 (외부 피해)
                elif health_diff < 0:
                    logger.info(f"  💔 외부 피해 감지: {health_diff}")
                    
                    await self.battle.channel.send(
                        f"💔 {player.real_name}의 체력이 감소했습니다! "
                        f"({health_diff} → {current_nickname_health})"
                    )
                    
                    player.real_current_health = current_nickname_health
                    
                    if self.battle.health_sync:
                        damage_ratio = abs(health_diff) / 100
                        battle_damage = max(1, int(player.max_health * damage_ratio))
                        player.current_health = max(0, player.current_health - battle_damage)
                        
                        if player.current_health <= 0:
                            player.is_eliminated = True
                            await self.battle.channel.send(f"💀 {player.real_name}이(가) 쓰러졌습니다!")
        
        logger.info("=== sync_health 종료 ===\n")

    async def process_turn(self):
        """턴 처리"""
        if not self.battle.is_active or self.battle.current_turn_index >= len(self.battle.turn_order):
            # 라운드 종료
            await self.check_battle_end()
            if self.battle.is_active:
                await self.start_combat_round()
            return
        
        current_name = self.battle.turn_order[self.battle.current_turn_index]
        
        # 몹 턴
        if current_name == self.battle.mob_name:
            if self.battle.mob_current_health > 0:
                # AI가 있으면 AI 사용, 없으면 기존 로직
                if self.battle.mob_ai and self.battle.ai_controller:
                    await self.ai_mob_turn()
                else:
                    # 회복 체크
                    if (self.battle.recovery_settings.health_threshold > 0 and 
                        self.battle.mob_current_health <= self.battle.recovery_settings.health_threshold and
                        not self.battle.recovery_settings.has_used):
                        await self.mob_recovery()
                    else:
                        await self.mob_turn()
            else:
                self.battle.current_turn_index += 1
                await self.process_turn()
        else:
            # 플레이어 턴
            player = next((p for p in self.battle.players if p.real_name == current_name), None)
            if player and not player.is_eliminated and not player.has_acted_this_turn:
                await self.player_turn(player)
            else:
                self.battle.current_turn_index += 1
                await self.process_turn()
    
    # 3. ai_mob_turn 메서드도 수정하여 기본 공격을 전체 공격으로 변경
    async def ai_mob_turn(self):
        """AI 몹 턴 (준비 턴 포함)"""
        # AI 로그 시작
        ai_decision_log = []
        
        # AI 턴 업데이트
        if self.battle.mob_ai:
            self.battle.mob_ai.update_turn()
            logger.info(f"[DEBUG] AI Turn Update - is_preparing: {self.battle.mob_ai.is_preparing_focused}, prepare_turns_left: {self.battle.mob_ai.prepare_turns_left}")
        
        # 준비 중인 경우 먼저 처리
        if self.battle.mob_ai and self.battle.mob_ai.is_preparing_focused:
            turns_left = self.battle.mob_ai.prepare_turns_left
            logger.info(f"[DEBUG] AI is preparing focused attack - turns_left: {turns_left}")
            
            if turns_left > 0:
                # 준비 메시지 (수정: 항상 표시)
                await self.battle.channel.send(
                    f"⚡ {self.battle.mob_name}이(가) 강력한 공격을 준비 중입니다!\n"
                    f"💥 {turns_left}턴 후 집중공격 발동!"
                )
                
                # 준비 중에는 공격 주사위가 1로 고정되므로 기본 공격만
                await self.battle.channel.send(
                    f"⚔️ {self.battle.mob_name}의 약한 공격! (준비 중)\n"
                    f"모든 플레이어는 `/주사위`를 굴려 회피하세요!"
                )
                
                # 몹 주사위 (자동으로 1)
                await asyncio.sleep(2)
                attack_roll = 1  # 준비 중이므로 1 고정
                await self.battle.channel.send(
                    f"`{self.battle.mob_name}`님이 주사위를 굴려 **{attack_roll}**이(가) 나왔습니다! (준비 중)"
                )
                
                # 전체 공격 대기 설정
                active_players = [p for p in self.battle.players if not p.is_eliminated]
                self.battle.pending_action = {
                    "type": "combat",
                    "phase": "mob_all_attack",
                    "waiting_for": [p.real_name for p in active_players],
                    "defend_results": {},
                    "attack_roll": attack_roll
                }
                
                # 타임아웃 설정
                if self.battle.timeout_task:
                    self.battle.timeout_task.cancel()
                self.battle.timeout_task = asyncio.create_task(self.check_timeout(60, "combat"))
                
                ai_decision_log.append(f"Focused attack preparation: {turns_left} turns left")
                self.battle.battle_log.append(f"[AI] Round {self.battle.round_count}: " + " | ".join(ai_decision_log))
                return
            else:
                # 준비 완료, 집중공격 실행 (수정: 저장된 액션 사용)
                logger.info(f"[DEBUG] Focused attack preparation complete! Executing focused attack NOW")
                
                await self.battle.channel.send(
                    f"💥 준비 완료! {self.battle.mob_name}의 집중공격 발동!\n"
                    f"남은 집중공격: {self.battle.mob_ai.max_focused_attacks - self.battle.mob_ai.focused_attack_count - 1}회"
                )
                
                # 저장된 집중공격 정보 사용 (수정)
                if hasattr(self.battle.mob_ai, 'prepared_action') and self.battle.mob_ai.prepared_action:
                    action = self.battle.mob_ai.prepared_action
                    self.battle.mob_ai.prepared_action = None  # 사용 후 초기화
                else:
                    # 기본 액션 생성 (백업)
                    active_players = [p for p in self.battle.players if not p.is_eliminated]
                    if active_players:
                        target = random.choice(active_players)
                        max_attacks = DifficultyManager.OPTIMIZATION_RATES[self.battle.mob_ai.difficulty]['focused_attack_max']
                        action = CombatAction(
                            ActionType.FOCUSED_ATTACK,
                            target=target,
                            parameters={
                                'attacks': min(max_attacks, len(active_players) + 1),  # 수정: 더 많은 공격
                                'mode': 'each',
                                'add_normal': False
                            }
                        )
                    else:
                        # 플레이어가 없으면 턴 종료
                        self.battle.current_turn_index += 1
                        await self.process_turn()
                        return
                
                # 집중공격 사용 처리
                self.battle.mob_ai.is_preparing_focused = False
                self.battle.mob_ai.prepare_turns_left = 0
                self.battle.mob_ai.focused_attack_count += 1
                self.battle.mob_ai.focused_attack_cooldown = self.battle.mob_ai.cooldown_turns
                
                await self.execute_focused_attack(action)
                ai_decision_log.append("Focused attack executed after preparation")
                self.battle.battle_log.append(f"[AI] Round {self.battle.round_count}: " + " | ".join(ai_decision_log))
                return
                # 아래로 계속 진행하여 실제 집중공격 실행
        
        # 쿨타임 중인 경우 알림
        if self.battle.mob_ai and self.battle.mob_ai.focused_attack_cooldown > 0:
            await self.battle.channel.send(
                f"⏳ 집중공격 쿨타임: {self.battle.mob_ai.focused_attack_cooldown}턴 남음"
            )
            ai_decision_log.append(f"Focused attack cooldown: {self.battle.mob_ai.focused_attack_cooldown} turns")
        
        # 1. MobRecoverySettings 우선 체크 (회복 사용 가능 여부 체크 추가)
        if (self.battle.recovery_settings.enabled and  # 회복이 활성화되어 있고
            self.battle.recovery_settings.health_threshold > 0 and 
            self.battle.mob_current_health <= self.battle.recovery_settings.health_threshold and
            not self.battle.recovery_settings.has_used):
            
            ai_decision_log.append(f"Recovery threshold reached: {self.battle.mob_current_health}/{self.battle.recovery_settings.health_threshold}")
            await self.mob_recovery()
            return
        
        # 2. AI의 회복 결정 (회복이 활성화되어 있을 때만)
        if self.battle.mob_ai and self.battle.recovery_settings.enabled:
            should_recover = self.battle.mob_ai.should_use_recovery()
            can_use_ai_recovery = self.battle.ai_recovery_count < self.battle.ai_max_recovery
            
            ai_decision_log.append(f"AI recovery decision: {should_recover}, Used: {self.battle.ai_recovery_count}/{self.battle.ai_max_recovery}")
            
            if should_recover and can_use_ai_recovery and self.battle.mob_current_health < self.battle.mob_health * 0.5:
                # AI 회복 시도
                await self.battle.channel.send(
                    f"💚 {self.battle.mob_name}이(가) 회복을 시도합니다! (AI 회복 {self.battle.ai_recovery_count + 1}/{self.battle.ai_max_recovery})"
                )
                
                # 회복 주사위 (AI의 roll_dice 사용)
                dice_value, is_mistake = self.battle.mob_ai.roll_dice('recovery')
                
                if is_mistake:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 실수로 1d10을 굴려 **{dice_value}**이(가) 나왔습니다! (회복 실패)"
                    )
                    ai_decision_log.append(f"Recovery failed: wrong dice (1d10)")
                else:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 주사위를 굴려 **{dice_value}**이(가) 나왔습니다!"
                    )
                    heal_amount = dice_value // 10
                    self.battle.mob_heal(heal_amount, dice_value)
                    self.battle.ai_recovery_count += 1  # 회복 카운터 증가
                    ai_decision_log.append(f"Recovery successful: +{heal_amount} HP")
                
                # 회복을 사용했으므로 턴 종료
                self.battle.current_turn_index += 1
                await self.process_turn()
                return
        
        # AI 행동 결정
        # AI 행동 결정
        action, phase_message, ai_log = await self.battle.ai_controller.process_turn(self.battle)
        
        logger.info(f"[DEBUG] AI Action decided - type: {action.type}, is_preparing: {self.battle.mob_ai.is_preparing_focused if self.battle.mob_ai else 'No AI'}")
        
        # AI 로그 추가
        ai_decision_log.extend([
            f"AI Phase: {ai_log.get('phase')}",
            f"AI Decision: {ai_log.get('decision')}",
            f"AI Mistake: {ai_log.get('mistake', 'None')}",
            f"Target: {ai_log.get('target', 'All')}"
        ])
        
        # 전투 로그에 AI 결정사항 추가
        self.battle.battle_log.append(f"[AI] Round {self.battle.round_count}: " + " | ".join(ai_decision_log))
        
        # 페이즈 변경 메시지
        if phase_message:
            await self.battle.channel.send(f"⚡ {phase_message}")
        
        # 행동 타입에 따른 처리
        if action.type == ActionType.FOCUSED_ATTACK:
            # 중요: 준비 중이 아닐 때만 실제 집중공격 실행
            if self.battle.mob_ai and not self.battle.mob_ai.is_preparing_focused:
                logger.info(f"[DEBUG] NOW Executing focused attack action - target: {action.target}")
                if action.target:
                    await self.execute_focused_attack(action)
                    return
                else:
                    action.type = ActionType.BASIC_ATTACK
            else:
                # 준비 중이면 기본 공격으로 전환
                logger.info(f"[DEBUG] Still preparing, converting to basic attack")
                action.type = ActionType.BASIC_ATTACK
        
        if action.type == ActionType.BASIC_ATTACK:
            # 기본 공격 - 전체 공격
            active_players = [p for p in self.battle.players if not p.is_eliminated]
            if not active_players:
                self.battle.current_turn_index += 1
                await self.process_turn()
                return
            
            await self.battle.channel.send(
                f"⚔️ **{self.battle.mob_name}의 전체 공격!**\n"
                f"{self.battle.mob_name}이(가) 모든 플레이어를 공격합니다!\n"
                f"모든 플레이어는 `/주사위`를 굴려 회피하세요!"
            )
            
            # 몹 주사위 (AI의 roll_dice 사용)
            await asyncio.sleep(2)
            
            # ⭐ 수정된 코드
            from skills.skill_effects import skill_effects
            
            # AI가 굴린 기본 주사위
            base_roll, is_mistake = self.battle.mob_ai.roll_dice('attack') if self.battle.mob_ai else (random.randint(1, 100), False)
            
            # 스킬 효과 적용
            attack_roll, skill_messages = await skill_effects.process_dice_roll(
                self.battle.mob_name,
                base_roll,
                str(self.battle.channel.id)
            )
            
            # 스킬 메시지 출력
            if skill_messages:
                for msg in skill_messages:
                    await self.battle.channel.send(msg)
            
            # 결과 메시지
            if is_mistake:
                await self.battle.channel.send(
                    f"`{self.battle.mob_name}`님이 실수로 1d10을 굴려 **{base_roll}**이(가) 나왔습니다!"
                )
            else:
                if attack_roll != base_roll:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 주사위를 굴려 **{base_roll}**이(가) 나왔습니다!\n"
                        f"⚔️ 스킬 효과로 **{attack_roll}**로 변경되었습니다!"
                    )
                else:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 주사위를 굴려 **{attack_roll}**이(가) 나왔습니다!"
                    )
            
            self.battle.pending_action = {
                "type": "combat",
                "phase": "mob_all_attack",
                "waiting_for": [p.real_name for p in active_players],
                "defend_results": {},
                "attack_roll": attack_roll
            }
            
            # 타임아웃 설정
            if self.battle.timeout_task:
                self.battle.timeout_task.cancel()
            self.battle.timeout_task = asyncio.create_task(self.check_timeout(60, "combat"))
        
        elif action.type == ActionType.WAIT:
            # 턴 넘김
            await self.battle.channel.send(f"💤 {self.battle.mob_name}이(가) 턴을 넘깁니다...")
            self.battle.current_turn_index += 1
            await self.process_turn()

    async def execute_focused_attack(self, action):
        """집중공격 실행"""
        target = action.target
        attacks = action.parameters.get('attacks', 2)
        mode = action.parameters.get('mode', 'each')
        add_normal = action.parameters.get('add_normal', False)
        
        defense_text = "각각 회피해야 합니다" if mode == "each" else "한 번의 주사위로 모든 공격이 결정됩니다"
        
        await self.battle.channel.send(
            f"💥 **집중공격!**\n"
            f"{self.battle.mob_name}이(가) {target.real_name}에게 **{attacks}회** 집중공격을 시작합니다!\n"
            f"**회피 방식**: {defense_text}"
        )
        
        self.battle.focused_attack = {
            "target": target,
            "total_attacks": attacks,
            "current_attack": 1,
            "defense_mode": mode,
            "add_normal_attack": add_normal,
            "results": []
        }
        
        if mode == "once":
            await self.battle.channel.send(
                f"🎯 **한 번의 대결**\n"
                f"🗡️ {self.battle.mob_name}님, 공격 주사위를 굴려주세요!\n"
                f"🛡️ {target.real_name}님, 회피 주사위를 굴려주세요!"
            )
            
            # AI가 있으면 AI의 주사위 사용
            if self.battle.mob_ai:
                base_roll, is_mistake = self.battle.mob_ai.roll_dice('focused_attack')
                
                # ⭐ 수정: 스킬 시스템 적용
                from skills.skill_effects import skill_effects
                attack_roll, skill_messages = await skill_effects.process_dice_roll(
                    self.battle.mob_name,
                    base_roll,
                    str(self.battle.channel.id)
                )
                
                # 스킬 메시지 출력
                if skill_messages:
                    for msg in skill_messages:
                        await self.battle.channel.send(msg)
                
                if is_mistake:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 실수로 1d10을 굴려 **{base_roll}**이(가) 나왔습니다!"
                    )
                else:
                    if attack_roll != base_roll:
                        await self.battle.channel.send(
                            f"`{self.battle.mob_name}`님이 주사위를 굴려 **{base_roll}**이(가) 나왔습니다!\n"
                            f"⚔️ 스킬 효과로 **{attack_roll}**로 변경되었습니다!"
                        )
                    else:
                        await self.battle.channel.send(
                            f"`{self.battle.mob_name}`님이 주사위를 굴려 **{attack_roll}**이(가) 나왔습니다!"
                        )
            else:
                # ⭐ 수정: 스킬 시스템 적용
                attack_roll = await self.roll_mob_dice_view("focused_attack")
            
            self.battle.pending_action = {
                "type": "combat",
                "phase": "focused_single",
                "attack_roll": attack_roll,
                "waiting_for": [target.real_name],
                "target_player": target
            }
        else:
            # 각각 회피
            await self.start_focused_attack_round()


    async def check_battle_end(self):
        """전투 종료 확인"""
        active_players = [p for p in self.battle.players if not p.is_eliminated]
        
        if self.battle.mob_current_health <= 0:
            # 몹 패배
            self.battle.is_active = False
            
            if self.battle.dialogue.health_0:
                await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.health_0}")
            
            embed = discord.Embed(
                title="🎉 승리!",
                description=f"{self.battle.mob_name}을(를) 물리쳤습니다!",
                color=discord.Color.gold()
            )
            
            # AI 정보 추가
            if self.battle.mob_ai:
                embed.add_field(
                    name="🤖 AI 분석",
                    value=f"**성격**: {self.battle.ai_personality}\n"
                        f"**난이도**: {self.battle.ai_difficulty}\n"
                        f"**총 행동**: {self.battle.round_count}회",
                    inline=False
                )
                
                # AI 결정 로그 요약 (마지막 5개)
                ai_logs = [log for log in self.battle.battle_log if log.startswith("[AI]")]
                if ai_logs:
                    recent_logs = ai_logs[-5:]
                    embed.add_field(
                        name="📝 AI 결정 로그 (최근 5개)",
                        value="\n".join(recent_logs),
                        inline=False
                    )
            
            embed.add_field(
                name="📊 전투 통계",
                value=f"**총 라운드**: {self.battle.round_count}\n"
                    f"**생존자**: {len(active_players)}/{len(self.battle.players)}",
                inline=False
            )
            
            await self.battle.channel.send(embed=embed)
            

            
            # 메인 메시지 정리
            await self.battle.main_message.edit(
                embed=discord.Embed(
                    title="전투 종료",
                    description=f"플레이어 팀 승리!",
                    color=discord.Color.green()
                ),
                view=None
            )
            
            # 타임아웃 태스크 취소
            if self.battle.timeout_task:
                self.battle.timeout_task.cancel()
            
            # 수정: bot 객체를 통해 mob_battles 접근
            if hasattr(self.battle.channel, 'guild'):
                # bot 객체는 MobSetting의 __init__에서 전달받은 것 사용
                bot = self.battle.channel._state._client  # Discord.py 내부 구조를 통한 bot 접근
                if hasattr(bot, 'mob_battles'):
                    bot.mob_battles.pop(self.battle.channel.id, None)
            
        elif not active_players:
            # 플레이어 전멸
            self.battle.is_active = False
            
            if self.battle.dialogue.enemy_all_killed:
                await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.enemy_all_killed}")
            
            embed = discord.Embed(
                title="💀 패배...",
                description="모든 플레이어가 쓰러졌습니다.",
                color=discord.Color.dark_red()
            )
            
            embed.add_field(
                name="📊 전투 통계",
                value=f"**총 라운드**: {self.battle.round_count}\n"
                    f"**{self.battle.mob_name} 남은 체력**: {self.battle.mob_current_health}/{self.battle.mob_health}",
                inline=False
            )
            
            await self.battle.channel.send(embed=embed)
            
            # 메인 메시지 정리
            await self.battle.main_message.edit(
                embed=discord.Embed(
                    title="전투 종료",
                    description=f"{self.battle.mob_name} 승리!",
                    color=discord.Color.red()
                ),
                view=None
            )
            
            # 타임아웃 태스크 취소
            if self.battle.timeout_task:
                self.battle.timeout_task.cancel()
            
            # 수정: bot 객체를 통해 mob_battles 접근
            if hasattr(self.battle.channel, 'guild'):
                bot = self.battle.channel._state._client
                if hasattr(bot, 'mob_battles'):
                    bot.mob_battles.pop(self.battle.channel.id, None)


    # start_focused_attack_round 메서드도 수정
    async def start_focused_attack_round(self):
        """집중공격 라운드 시작"""
        focused = self.battle.focused_attack
        target = focused["target"]
        
        await self.battle.channel.send(
            f"🎯 **집중공격 {focused['current_attack']}/{focused['total_attacks']}회차**\n"
            f"🗡️ {self.battle.mob_name}의 공격!\n"
            f"🛡️ {target.real_name}님, `/주사위`를 굴려 회피하세요!"
        )
        
        # AI가 있으면 AI의 주사위 사용
        if self.battle.mob_ai:
            base_roll, is_mistake = self.battle.mob_ai.roll_dice('focused_attack')
            
            # ⭐ 수정: 스킬 시스템 적용
            from skills.skill_effects import skill_effects
            attack_roll, skill_messages = await skill_effects.process_dice_roll(
                self.battle.mob_name,
                base_roll,
                str(self.battle.channel.id)
            )
            
            # 스킬 메시지 출력
            if skill_messages:
                for msg in skill_messages:
                    await self.battle.channel.send(msg)
            
            if is_mistake:
                await self.battle.channel.send(
                    f"`{self.battle.mob_name}`님이 실수로 1d10을 굴려 **{base_roll}**이(가) 나왔습니다!"
                )
            else:
                if attack_roll != base_roll:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 주사위를 굴려 **{base_roll}**이(가) 나왔습니다!\n"
                        f"⚔️ 스킬 효과로 **{attack_roll}**로 변경되었습니다!"
                    )
                else:
                    await self.battle.channel.send(
                        f"`{self.battle.mob_name}`님이 주사위를 굴려 **{attack_roll}**이(가) 나왔습니다!"
                    )
        else:
            # ⭐ 수정: 스킬 시스템 적용
            attack_roll = await self.roll_mob_dice_view("focused_attack")
        
        self.battle.pending_action = {
            "type": "combat",
            "phase": "focused_each",
            "attack_roll": attack_roll,
            "waiting_for": [target.real_name],
            "target_player": target
        }

    async def handle_focused_each_defense(self, player_name: str, defend_roll: int):
        """각각 회피 방식 집중공격의 회피 처리 후 다음 라운드로"""
        focused = self.battle.focused_attack
        if not focused or focused["target"].real_name != player_name:
            return

        attack_roll = self.battle.pending_action.get("attack_roll")
        focused["results"].append({
            "attack": focused["current_attack"],
            "attack_roll": attack_roll,
            "defend_roll": defend_roll,
        })

        focused["current_attack"] += 1

        if focused["current_attack"] <= focused["total_attacks"]:
            await self.start_focused_attack_round()
        else:
            await self.battle.channel.send("🔥 **집중공격이 종료되었습니다!**")
            self.battle.focused_attack = None
            self.battle.pending_action = None
            await self.process_turn()

    async def mob_recovery(self):
        """몹 회복"""
        await self.battle.channel.send(
            f"💚 {self.battle.mob_name}이(가) 회복을 시도합니다! "
            f"1d{self.battle.recovery_settings.dice_max} 주사위를 굴립니다."
        )
        
        # 회복 주사위 굴리기
        await asyncio.sleep(1)
        dice_value = random.randint(1, self.battle.recovery_settings.dice_max)
        await self.battle.channel.send(f"`{self.battle.mob_name}`님이 주사위를 굴려 **{dice_value}**이(가) 나왔습니다!")
        
        # 회복 처리
        heal_amount = dice_value // 10
        self.battle.mob_heal(heal_amount, dice_value)
        self.battle.recovery_settings.has_used = True
        
        await self.battle.channel.send(
            f"💚 **회복 성공!** {self.battle.mob_name}이(가) {heal_amount} 체력을 회복했습니다!\n"
            f"현재 체력: {self.battle.mob_current_health}/{self.battle.mob_health}"
        )
        
        # 메인 메시지 업데이트
        await self.battle.main_message.edit(embed=self.create_battle_status_embed())
        
        # 턴 종료
        self.battle.current_turn_index += 1
        await self.process_turn()
    
    async def mob_turn(self):
        """몹 턴 - 전체 공격"""
        # 생존한 플레이어 찾기
        active_players = [p for p in self.battle.players if not p.is_eliminated]
        if not active_players:
            self.battle.current_turn_index += 1
            await self.process_turn()
            return
        
        await self.battle.channel.send(
            f"⚔️ **{self.battle.mob_name}의 전체 공격!**\n"
            f"{self.battle.mob_name}이(가) 모든 플레이어를 공격합니다!\n"
            f"모든 플레이어는 `/주사위`를 굴려 회피하세요!"
        )
        
        # 몹 주사위 굴리기
        await asyncio.sleep(2)
        
        # ⭐ 기존 코드 (스킬 시스템 미적용)
        # attack_roll = random.randint(1, 100)
        
        # ⭐ 수정된 코드 (스킬 시스템 적용)
        from skills.skill_effects import skill_effects
        
        # 몬스터의 기본 주사위 값
        base_attack_roll = random.randint(1, 100)
        
        # 스킬 효과 적용
        attack_roll, skill_messages = await skill_effects.process_dice_roll(
            self.battle.mob_name,  # 몬스터 이름을 user_id로 사용
            base_attack_roll,
            str(self.battle.channel.id)
        )
        
        # 스킬 메시지 출력
        if skill_messages:
            for msg in skill_messages:
                await self.battle.channel.send(msg)
        
        # 주사위 결과 메시지
        if attack_roll != base_attack_roll:
            await self.battle.channel.send(
                f"`{self.battle.mob_name}`님이 주사위를 굴려 **{base_attack_roll}**이(가) 나왔습니다!\n"
                f"⚔️ 스킬 효과로 **{attack_roll}**로 변경되었습니다!"
            )
        else:
            await self.battle.channel.send(
                f"`{self.battle.mob_name}`님이 주사위를 굴려 **{attack_roll}**이(가) 나왔습니다!"
            )
        
        # pending_action에 저장
        self.battle.pending_action = {
            "type": "combat",
            "phase": "mob_all_attack",
            "waiting_for": [p.real_name for p in active_players],
            "defend_results": {},
            "attack_roll": attack_roll  # 스킬이 적용된 최종값
        }
        
        # 타임아웃 설정
        if self.battle.timeout_task:
            self.battle.timeout_task.cancel()
        self.battle.timeout_task = asyncio.create_task(self.check_timeout(60, "combat"))


    
    async def player_turn(self, player: AutoBattlePlayer):
        """플레이어 턴"""
        logger.info(f"[DEBUG] player_turn called for {player.real_name}")
        
        # 메인 메시지 업데이트
        await self.battle.main_message.edit(embed=self.create_battle_status_embed())
        
        # 체력 정보 계산
        active_players = [p for p in self.battle.players if not p.is_eliminated]
        
        # 플레이어 팀 체력 정보
        team_health_info = "**🩸 플레이어 팀 상태**\n"
        for p in active_players:
            team_health_info += f"• {p.real_name}: {p.current_health}/{p.max_health} HP\n"
        
        # 몹 체력 정보 (몬스터 회복 정보 표시)
        mob_health_info = f"\n**🎯 {self.battle.mob_name} 상태**\n"
        mob_health_info += f"• 체력: {self.battle.mob_current_health}/{self.battle.mob_health} HP\n"
        if self.battle.mob_ai:
            mob_health_info += f"• 몬스터 남은 회복: {self.battle.ai_max_recovery - self.battle.ai_recovery_count}회\n"
        
        # 행동 옵션
        action_info = f"\n\n**⚔️ {player.real_name}의 턴!**\n"
        action_info += "무엇을 하시겠습니까?\n"
        action_info += "• **공격**: `/주사위` 명령어로 공격\n"
        action_info += "• **회복**: `/회복` 명령어로 회복 시도 **[턴 소모]**\n"
        action_info += "• **턴 넘김**: `!턴넘김` 명령어 사용"
        
        await self.battle.channel.send(team_health_info + mob_health_info + action_info)
        
        # 플레이어 행동 대기
        self.battle.pending_action = {
            "type": "player_turn",
            "player": player,
            "waiting_for": [player.real_name]
        }
        
        logger.info(f"[DEBUG] player_turn set pending_action: {self.battle.pending_action}")
        
        # 타임아웃 설정
        if self.battle.timeout_task:
            self.battle.timeout_task.cancel()
        self.battle.timeout_task = asyncio.create_task(self.check_timeout(60, "player_turn"))

    
    async def process_combat_result(self, attacker, attack_roll, defender, defense_roll, is_mob_attacking):
        """전투 결과 처리"""
        # 공격자와 방어자 이름 추출
        attacker_name = attacker if isinstance(attacker, str) else attacker.real_name
        defender_name = defender if isinstance(defender, str) else defender.real_name
        
        # 공격자와 방어자가 객체인지 문자열인지 확인
        attacker_is_mob = isinstance(attacker, str)
        defender_is_mob = isinstance(defender, str)
        
        # 전투 결과 텍스트
        result_text = f"{attacker_name} 🎲{attack_roll} vs {defender_name} 🎲{defense_roll}\n"
        
        # 특수 판정
        if attack_roll <= 10:  # 공격자 대실패
            if attacker_is_mob:  # 몬스터가 공격자일 때
                self.battle.mob_current_health -= 1
                self.battle.mob_real_current_health -= 10
                result_text += "**대실패!** 몹이 자신에게 피해를 입었습니다! (-1 체력)"
                
                # AI 체력 업데이트
                if self.battle.mob_ai:
                    self.battle.mob_ai.take_damage(1)
            else:  # 플레이어가 공격자일 때
                attacker.take_damage(1, 10)
                result_text += "**대실패!** 자신에게 피해! (-1 체력)"
                
        elif defense_roll <= 10:  # 방어 대실패
            if defender_is_mob:  # 몬스터가 방어자일 때
                self.battle.mob_take_damage(2, 20)
                if not attacker_is_mob:  # 공격자가 플레이어면
                    attacker.hits_dealt += 2
                result_text += "**방어 대실패!** 몹이 2배 피해! (-2 체력)"
            else:  # 플레이어가 방어자일 때
                defender.take_damage(2, 20)
                result_text += "**방어 대실패!** 2배 피해! (-2 체력)"
                
        elif attack_roll >= 90 and attack_roll > defense_roll:  # 대성공
            if defender_is_mob:  # 몬스터가 맞을 때
                self.battle.mob_take_damage(2, 20)
                if not attacker_is_mob:  # 공격자가 플레이어면
                    attacker.hits_dealt += 2
                result_text += "**대성공!** 몹이 2배 피해! (-2 체력)"
            else:  # 플레이어가 맞을 때
                defender.take_damage(2, 20)
                result_text += "**대성공!** 2배 피해! (-2 체력)"
                
        elif attack_roll > defense_roll:  # 일반 명중
            if defender_is_mob:  # 몬스터가 맞을 때
                self.battle.mob_take_damage(1, 10)
                if not attacker_is_mob:  # 공격자가 플레이어면
                    attacker.hits_dealt += 1
                result_text += "**명중!** 몹이 피해! (-1 체력)"
            else:  # 플레이어가 맞을 때
                defender.take_damage(1, 10)
                result_text += "**명중!** (-1 체력)"
        else:  # 회피
            result_text += "**회피!** 피해 없음"
        
        # 체력이 0 이하가 되도록 제한
        if self.battle.mob_current_health < 0:
            self.battle.mob_current_health = 0
        if self.battle.mob_real_current_health < 0:
            self.battle.mob_real_current_health = 0
        
        await self.battle.channel.send(f"⚔️ **전투 결과**\n{result_text}")
        
        # 체력 동기화가 활성화된 경우 플레이어 닉네임 업데이트 (플레이어가 피해를 입은 경우만)
        if self.battle.health_sync and not defender_is_mob and not isinstance(defender, str):
            # 피해를 입은 경우에만
            if "명중" in result_text or "피해" in result_text:
                # 피해량 계산 (result_text 기반)
                damage_amount = 1  # 기본 피해
                if "2배 피해" in result_text:
                    damage_amount = 2
                
                # 실제 체력 즉시 업데이트 (닉네임 업데이트 전에)
                real_damage = damage_amount * 10
                old_real_health = defender.real_current_health
                defender.real_current_health = max(0, defender.real_current_health - real_damage)
                logger.info(f"{defender.real_name}의 real_current_health 즉시 업데이트: {old_real_health} → {defender.real_current_health} (-{real_damage})")
                
                # 닉네임 업데이트 시도
                new_nickname = update_nickname_health(defender.user.display_name, defender.real_current_health)
                try:
                    await defender.user.edit(nick=new_nickname)
                    defender.last_nickname_update = datetime.now()
                    logger.info(f"{defender.real_name}의 닉네임 업데이트 성공: {new_nickname}")
                except discord.Forbidden:
                    defender.nickname_update_failed = True
                    logger.warning(f"{defender.real_name}의 닉네임 업데이트 실패 (권한 없음)")
                    await self.battle.channel.send(
                        f"⚠️ {defender.real_name}의 닉네임을 업데이트할 수 없습니다. "
                        f"봇에 닉네임 변경 권한이 있는지 확인해주세요."
                    )
                except Exception as e:
                    defender.nickname_update_failed = True
                    logger.error(f"닉네임 업데이트 오류: {e}")

        # 메인 메시지 업데이트
        await self.battle.main_message.edit(embed=self.create_battle_status_embed())
        
        # 처치 확인 및 대사 (플레이어가 처치된 경우만)
        if not defender_is_mob and defender.is_eliminated and self.battle.dialogue.enemy_killed:
            await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.enemy_killed}")
        
        # 체력 기반 대사 체크
        await self.check_mob_health_dialogue()

    async def process_focused_result(self, attack_roll, defense_roll, mode):
        """집중공격 결과 처리"""
        focused = self.battle.focused_attack
        target = focused["target"]
        
        if mode == "single":
            # 한 번에 판정
            if attack_roll > defense_roll:
                # 모든 공격 성공
                hits = min(focused["total_attacks"], target.max_health - target.current_health)
                target.take_damage(hits, hits * 10)
                target.hits_dealt += hits  # AI 호환성
                
                result_msg = f"💥 **대성공!** {self.battle.mob_name}의 공격({attack_roll})이 "
                result_msg += f"{target.real_name}({defense_roll})에게 {hits}회 모두 명중!"
                
                # 닉네임 업데이트
                if self.battle.health_sync:
                    new_nickname = update_nickname_health(target.user.display_name, target.real_current_health)
                    try:
                        await target.user.edit(nick=new_nickname)
                    except discord.Forbidden:
                        pass
                
                if target.is_eliminated:
                    result_msg += f"\n💀 **{target.real_name} 탈락!**"
            else:
                # 모든 공격 실패
                result_msg = f"🛡️ **완벽한 회피!** {target.real_name}({defense_roll})이 "
                result_msg += f"{self.battle.mob_name}의 모든 공격({attack_roll})을 회피!"
            
            await self.battle.channel.send(result_msg)
            
            # 추가 전체 공격 확인
            if focused["add_normal_attack"] and [p for p in self.battle.players if not p.is_eliminated]:
                await self.battle.channel.send("이어서 전체 공격을 시작합니다...")
                await asyncio.sleep(1)
                # 기본 몹 턴 실행
                self.battle.focused_attack = None
                await self.mob_turn()
            else:
                # 턴 종료
                self.battle.focused_attack = None
                self.battle.current_turn_index += 1
                await self.process_turn()
        
        else:
            # 각각 회피
            current_attack = focused["current_attack"]
            
            if attack_roll > defense_roll:
                focused["results"].append({
                    "attack": current_attack,
                    "hit": True,
                    "attack_value": attack_roll,
                    "defend_value": defense_roll
                })
                target.take_damage(1, 10)
                target.hits_dealt += 1
                
                result_msg = f"🎯 **{current_attack}회차 명중!** {self.battle.mob_name}의 공격({attack_roll})이 "
                result_msg += f"{target.real_name}({defense_roll})에게 명중!"
                
                # 닉네임 업데이트
                if self.battle.health_sync:
                    new_nickname = update_nickname_health(target.user.display_name, target.real_current_health)
                    try:
                        await target.user.edit(nick=new_nickname)
                    except discord.Forbidden:
                        pass
                
                if target.is_eliminated:
                    result_msg += f"\n💀 **{target.real_name} 탈락!**"
            else:
                focused["results"].append({
                    "attack": current_attack,
                    "hit": False,
                    "attack_value": attack_roll,
                    "defend_value": defense_roll
                })
                result_msg = f"🛡️ **{current_attack}회차 회피!** {target.real_name}({defense_roll})이 "
                result_msg += f"{self.battle.mob_name}의 공격({attack_roll})을 회피!"
            
            await self.battle.channel.send(result_msg)
            
            # 다음 공격 확인
            focused["current_attack"] += 1
            
            if focused["current_attack"] <= focused["total_attacks"] and not target.is_eliminated:
                # 다음 공격 진행
                await asyncio.sleep(1.5)
                await self.start_focused_attack_round()
            else:
                # 집중공격 종료
                hits = sum(1 for r in focused["results"] if r["hit"])
                await self.battle.channel.send(
                    f"\n💥 **집중공격 종료!**\n"
                    f"총 {focused['total_attacks']}회 공격 중 {hits}회 명중!"
                )
                
                # 추가 전체 공격 확인
                if focused["add_normal_attack"] and [p for p in self.battle.players if not p.is_eliminated]:
                    await self.battle.channel.send("이어서 전체 공격을 시작합니다...")
                    await asyncio.sleep(1)
                    self.battle.focused_attack = None
                    await self.mob_turn()
                else:
                    # 턴 종료
                    self.battle.focused_attack = None
                    self.battle.current_turn_index += 1
                    await self.process_turn()
    
    async def check_mob_health_dialogue(self):
        """몹 체력 기반 대사 체크"""
        if self.battle.mob_current_health <= 0:
            return
        
        health_percent = (self.battle.mob_current_health / self.battle.mob_health) * 100
        
        # 각 임계값에 대해 한 번만 대사 출력
        if 70 <= health_percent < 80 and self.battle.dialogue.health_75 and "75%" not in self.battle.battle_log:
            await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.health_75}")
            self.battle.battle_log.append("75%")
        elif 45 <= health_percent < 55 and self.battle.dialogue.health_50 and "50%" not in self.battle.battle_log:
            await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.health_50}")
            self.battle.battle_log.append("50%")
        elif 20 <= health_percent < 30 and self.battle.dialogue.health_25 and "25%" not in self.battle.battle_log:
            await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.health_25}")
            self.battle.battle_log.append("25%")
        
        # 플레이어 평균 체력 체크
        active_players = [p for p in self.battle.players if not p.is_eliminated]
        if active_players and self.battle.dialogue.enemy_avg_50 and "avg50%" not in self.battle.battle_log:
            total_current = sum(p.current_health for p in active_players)
            total_max = sum(p.max_health for p in active_players)
            avg_percent = (total_current / total_max) * 100
            
            if 45 <= avg_percent < 55:
                await self.battle.channel.send(f"**{self.battle.mob_name}**: {self.battle.dialogue.enemy_avg_50}")
                self.battle.battle_log.append("avg50%")
    
   
    def create_health_bar(self, current: int, maximum: int) -> str:
        """체력바 생성"""
        if maximum == 0:
            return "💀"
        
        percentage = current / maximum
        filled = int(percentage * 10)
        empty = 10 - filled
        
        if percentage > 0.7:
            color = "🟩"
        elif percentage > 0.3:
            color = "🟨"
        else:
            color = "🟥"
        
        return color * filled + "⬜" * empty

class MobSetting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not hasattr(bot, 'mob_battles'):
            bot.mob_battles = {}
        # 스킬 시스템과의 연동을 위한 전투 상태 관리
        if not hasattr(bot, 'battle_states'):
            bot.battle_states = {}
        self.player_health_tracking = {}

    async def create_mob_battle(
        self, 
        interaction: discord.Interaction,
        mob_name: str,
        mob_health: int,
        health_sync: bool,
        ai_personality: str = "tactical",
        ai_difficulty: str = "normal",
        enable_skills: bool = True
    ) -> bool:
        """몹 전투 생성 + 스킬 시스템 통합"""
        try:
            channel_id = interaction.channel.id
            
            # 이미 진행 중인 전투 체크
            if channel_id in self.bot.mob_battles:
                await interaction.followup.send("❌ 이미 진행 중인 몹 전투가 있습니다.")
                return False

            # 실제 체력 계산
            mob_real_health = mob_health * 10 if health_sync else 100

            # 몹 AI 생성
            from mob_ai import create_mob_ai, AIPersonality
            personality_map = {
                "aggressive": AIPersonality.AGGRESSIVE,
                "defensive": AIPersonality.DEFENSIVE,
                "tactical": AIPersonality.TACTICAL,
                "berserker": AIPersonality.BERSERKER,
                "opportunist": AIPersonality.OPPORTUNIST
            }

            mob_ai = create_mob_ai(
                mob_name=mob_name,          # 첫 번째 필수 인자 추가!
                mob_health=mob_health,      # 두 번째 필수 인자 추가!
                personality=ai_personality, # 문자열로 전달 (자동 변환됨)
                difficulty=ai_difficulty
            )

            # AutoBattle 객체 생성
            battle = AutoBattle(
                channel=interaction.channel,
                mob_name=mob_name,
                mob_health=mob_health,
                mob_real_health=mob_real_health,
                health_sync=health_sync,
                creator=interaction.user,        # 🔧 이 줄 추가!
                ai_personality=ai_personality,
                ai_difficulty=ai_difficulty,
                mob_ai=mob_ai
                )

            # View 생성
            view = MobSettingView(battle)
            battle.main_message = await interaction.followup.send(
                embed=view.create_setup_embed(),
                view=view
            )

            # 봇에 전투 등록
            self.bot.mob_battles[channel_id] = battle

            # === 스킬 시스템 활성화 ===
            if enable_skills:
                await self._activate_skill_system(interaction.channel.id, mob_name)

            logger.info(f"몹 전투 생성 완료 - {mob_name}, 채널: {channel_id}, 스킬: {enable_skills}")
            return True

        except Exception as e:
            logger.error(f"몹 전투 생성 실패: {e}")
            await interaction.followup.send(f"❌ 몹 전투 생성 중 오류가 발생했습니다: {e}")
            return False

    async def roll_mob_dice(self, battle: AutoBattle, dice_type: str = "attack") -> int:
        """몬스터 주사위 굴림 (스킬 시스템 적용)"""
        from skills.skill_effects import skill_effects
        
        # 기본 주사위 값
        base_roll = random.randint(1, 100)
        
        # 스킬 효과 적용
        final_roll, skill_messages = await skill_effects.process_dice_roll(
            battle.mob_name,  # 몬스터 이름을 user_id로 사용
            base_roll,
            str(battle.channel.id)
        )
        
        # 스킬 메시지 출력
        if skill_messages:
            for msg in skill_messages:
                await battle.channel.send(msg)
        
        # 주사위 결과 메시지
        if final_roll != base_roll:
            await battle.channel.send(
                f"`{battle.mob_name}`님이 주사위를 굴려 **{base_roll}**이(가) 나왔습니다!\n"
                f"⚔️ 스킬 효과로 **{final_roll}**로 변경되었습니다!"
            )
        else:
            await battle.channel.send(
                f"`{battle.mob_name}`님이 주사위를 굴려 **{final_roll}**이(가) 나왔습니다!"
            )
        
        return final_roll

    async def _activate_skill_system(self, channel_id: int, mob_name: str):
        """스킬 시스템 활성화"""
        try:
            from skills.skill_manager import skill_manager
            
            channel_id_str = str(channel_id)
            channel_state = skill_manager.get_channel_state(channel_id_str)
            
            # 전투 상태 설정
            channel_state["battle_active"] = True
            channel_state["battle_type"] = "mob_battle"
            channel_state["mob_name"] = mob_name
            channel_state["admin_can_use_skills"] = True
            channel_state["user_can_use_skills"] = True  # 유저도 스킬 사용 가능
            
            # 전투 참가자 초기화 (중요!)
            channel_state["battle_participants"] = {}
            
            # 상태 저장
            await skill_manager._save_skill_states()
            
            logger.info(f"스킬 시스템 활성화 완료 - 채널: {channel_id_str}, 몹: {mob_name}")
            
                
        except Exception as e:
            logger.error(f"스킬 시스템 활성화 오류 - 채널: {channel_id}: {e}")
            
    async def _deactivate_skill_system(self, channel_id: int) -> int:
        """스킬 시스템 비활성화 및 정리"""
        try:
            from skills.skill_manager import skill_manager
            
            channel_id_str = str(channel_id)
            channel_state = skill_manager.get_channel_state(channel_id_str)
            
            # 활성 스킬 개수 확인
            active_skills_count = len(channel_state["active_skills"])
            
            # 전투 상태 해제
            channel_state["battle_active"] = False
            channel_state["battle_type"] = None
            channel_state["mob_name"] = None
            channel_state["admin_can_use_skills"] = False
            
            # 활성 스킬 정리
            channel_state["active_skills"].clear()
            channel_state["special_effects"].clear()
            
            # 상태 저장
            await skill_manager._save_skill_states()
            
            logger.info(f"스킬 시스템 정리 완료 - 채널: {channel_id_str}, 정리된 스킬: {active_skills_count}개")
            return active_skills_count
            
        except Exception as e:
            logger.error(f"스킬 시스템 정리 오류 - 채널: {channel_id}: {e}")
            return 0

    async def handle_mob_surrender(self, channel_id: int, user_id: int) -> bool:
        """몹 전투 항복 처리"""
        if channel_id not in self.bot.mob_battles:
            return False
        
        battle = self.bot.mob_battles[channel_id]
        
        # Admin이 항복하는 경우 (몹이 항복)
        if user_id in [1007172975222603798, 1090546247770832910]:  # Admin ID들
            await battle.channel.send(f"🏳️ **{battle.mob_name}이(가) 항복했습니다!")
            
            # 전투 종료 처리
            await self._end_battle(battle)
            return True
        
        # 플레이어가 항복하는 경우
        for player in battle.players:
            if user_id == player.user.id and not player.is_eliminated:
                player.is_eliminated = True
                
                await battle.channel.send(f"🏳️ {player.real_name}이(가) 항복했습니다!")
                
                # 전투 종료 체크
                await self._check_battle_end(battle)
                return True
        
        return False

    async def _end_battle(self, battle: AutoBattle):
        """전투 종료 처리"""
        try:
            # === 스킬 시스템 정리 추가 ===
            from skills.skill_manager import skill_manager
            channel_id = str(battle.channel.id)
            
            # 모든 스킬 정리
            cleared_count = await skill_manager.clear_channel_skills(channel_id)
            if cleared_count > 0:
                await battle.channel.send(f"💫 모든 스킬 효과가 종료되었습니다. ({cleared_count}개)")
            
            # 전투 종료 처리
            battle.is_active = False
            
            # 체력 동기화가 활성화된 경우 닉네임 복구
            if battle.health_sync:
                for player in battle.players:
                    original_nickname = player.real_name
                    try:
                        await player.user.edit(nick=original_nickname)
                    except:
                        pass
            
            # 전투 로그 저장 (선택적)
            if battle.battle_log:
                log_summary = f"**전투 기록**\n총 {battle.round_count} 라운드 진행\n"
                await battle.channel.send(log_summary)
            
            # 전투 객체 제거
            if battle.channel.id in self.bot.mob_battles:
                del self.bot.mob_battles[battle.channel.id]
            
            # 메인 메시지 업데이트
            if battle.main_message:
                final_embed = discord.Embed(
                    title="⚔️ 전투 종료",
                    description="전투가 종료되었습니다.",
                    color=discord.Color.dark_gray()
                )
                await battle.main_message.edit(embed=final_embed, view=None)
            
        except Exception as e:
            logger.error(f"Battle end processing error: {e}")

    async def check_battle_end(self):
        """전투 종료 체크"""
        try:
            # 모든 플레이어 탈락 체크
            active_players = [p for p in self.battle.players if not p.is_eliminated]
            
            if not active_players:
                # 몹 승리
                await self.battle.channel.send(f"💀 **몹 승리!**\n모든 플레이어가 전투불능이 되었습니다!")
                await self._end_battle(self.battle)
                return
            
            # 몹 체력 0 체크
            if self.battle.mob_current_health <= 0:
                # 플레이어 승리
                winner_names = [p.real_name for p in active_players]
                await self.battle.channel.send(f"🎉 **플레이어 승리!**\n생존자: {', '.join(winner_names)}")
                await self._end_battle(self.battle)
                return
                
        except Exception as e:
            logger.error(f"Battle end check error: {e}")

    # logger.info에서 한글을 제거하거나 try-except로 감싸기
    async def process_mob_dice_message(self, message: discord.Message):
        """몹 전투에서 주사위 메시지 처리"""
        try:
            channel_id = message.channel.id
            if channel_id not in self.bot.mob_battles:
                return
                
            battle = self.bot.mob_battles[channel_id]
            if not battle.is_active:
                return
                
            # 주사위 결과 파싱
            dice_result = self.parse_dice_message(message.content)
            if not dice_result:
                return
                
            # 로깅 시 한글 처리 문제 해결
            try:
                logger.info(f"[DEBUG] Mob dice message parsed - player: {dice_result.player_name}, value: {dice_result.dice_value}")
            except:
                # 로깅 실패 시 영어로만 로깅
                logger.info(f"[DEBUG] Mob dice parsed - value: {dice_result.dice_value}")
            
            # === 스킬 시스템과 연동된 주사위 처리 ===
            final_dice_value = await self._process_skill_enhanced_dice(
                dice_result, channel_id, message
            )
            
            # 전투 로직에 최종 주사위 값 전달
            await self._handle_battle_dice(battle, dice_result.player_name, final_dice_value)
            
        except Exception as e:
            logger.error(f"Mob battle dice processing error: {e}")

    async def _process_skill_enhanced_dice(self, dice_result, channel_id: int, message: discord.Message) -> int:
        """스킬 시스템이 적용된 주사위 처리"""
        try:
            from skills.skill_effects import skill_effects
            
            # 몬스터 주사위 처리
            battle = self.bot.mob_battles.get(channel_id)
            if battle and dice_result.player_name == battle.mob_name:
                logger.info(f"몬스터 주사위 스킬 처리 시작 - 몹 이름: {battle.mob_name}, 주사위: {dice_result.dice_value}")
                
                # 몬스터는 실제 몹 이름으로 스킬 효과 처리
                final_value, skill_messages = await skill_effects.process_dice_roll(
                    battle.mob_name,  # 실제 몹 이름 사용
                    dice_result.dice_value, 
                    str(channel_id)
                )
                
                logger.info(f"몬스터 주사위 스킬 처리 결과 - 원래값: {dice_result.dice_value}, 최종값: {final_value}")
                
                # 스킬 효과 메시지 전송
                if skill_messages:
                    for skill_message in skill_messages:
                        await message.channel.send(skill_message)
                
                # 값이 변경된 경우 알림
                if final_value != dice_result.dice_value:
                    change_msg = f"🎲 **{dice_result.player_name}**의 주사위 결과: {dice_result.dice_value} → **{final_value}**"
                    await message.channel.send(change_msg)
                
                logger.info(f"몬스터 주사위 스킬 효과 적용: {dice_result.player_name} - {dice_result.dice_value} → {final_value}")
                return final_value
            else:
                # 플레이어 주사위 처리 (기존 코드)
                user_id = None
                player_name = dice_result.player_name
                
                if message.guild:
                    for member in message.guild.members:
                        if player_name in member.display_name:
                            user_id = str(member.id)
                            break
                
                if user_id:
                    final_value, skill_messages = await skill_effects.process_dice_roll(
                        user_id, dice_result.dice_value, str(channel_id)
                    )
                    
                    if skill_messages:
                        for skill_message in skill_messages:
                            await message.channel.send(skill_message)
                    
                    if final_value != dice_result.dice_value:
                        change_msg = f"🎲 **{player_name}**님의 주사위 결과: {dice_result.dice_value} → **{final_value}**"
                        await message.channel.send(change_msg)
                    
                    return final_value
                
                return dice_result.dice_value
                
        except Exception as e:
            logger.error(f"스킬 강화 주사위 처리 오류: {e}")
            return dice_result.dice_value

    async def _handle_battle_dice(self, battle, player_name: str, dice_value: int):
        """전투에서 주사위 결과 처리"""
        try:
            # 기존 전투 로직과 연동
            # 여기서는 스킬이 적용된 최종 주사위 값으로 전투 처리
            
            # 예시: 공격/회피 처리
            if battle.pending_action:
                action_type = battle.pending_action.get("type")
                
                if action_type == "player_attack":
                    # 플레이어 공격 처리
                    await self.handle_player_attack(battle, player_name, dice_value)
                elif action_type == "player_defense":
                    # 플레이어 방어 처리
                    await self.handle_player_defense(battle, player_name, dice_value)
                elif action_type == "admin_attack":
                    # Admin(몹) 공격 처리
                    await self.handle_admin_attack(battle, player_name, dice_value)
                    
        except Exception as e:
            logger.error(f"전투 주사위 처리 오류: {e}")

    def check_permission(self, user: discord.Member) -> bool:
        """권한 체크"""
        # ID 체크
        if str(user.id) in AUTHORIZED_USERS:
            return True
        
        # 닉네임 체크
        if user.display_name == AUTHORIZED_NICKNAME:
            return True
        
        return False
    
    def parse_dice_message(self, message_content: str) -> Optional[DiceResult]:
        """다이스 봇 메시지를 파싱하여 결과 추출"""
        from collections import namedtuple
        from typing import Optional
        
        # DiceResult namedtuple 정의
        DiceResult = namedtuple('DiceResult', ['player_name', 'dice_value'])
        
        normalized_content = ' '.join(message_content.split())
        pattern = r"`([^`]+)`님이.*?주사위를\s*굴\s*려.*?\*\*(\d+)\*\*.*?나왔습니다"
        
        match = re.search(pattern, normalized_content)
        if match:
            player_name = match.group(1).strip()
            # 추출된 이름을 real name으로 변환
            real_player_name = extract_real_name(player_name)
            dice_value = int(match.group(2))
            
            return DiceResult(player_name=real_player_name, dice_value=dice_value)
        
        return None
    
    async def process_mob_dice_message(self, message: discord.Message):
        """몹 전투 다이스 메시지 처리"""
        if message.channel.id not in self.bot.mob_battles:
            return
        
        battle = self.bot.mob_battles[message.channel.id]
        if not battle.is_active or not battle.pending_action:
            return
        
        # 다이스 메시지 파싱
        result = self.parse_dice_message(message.content)
        if not result:
            return
        
        logger.info(f"[DEBUG] Mob dice message parsed - player: {result.player_name}, value: {result.dice_value}")
        logger.info(f"[DEBUG] Current pending_action type: {battle.pending_action.get('type')}")
        
        # 타임아웃 태스크 취소
        if battle.timeout_task:
            battle.timeout_task.cancel()
        
        # 몹의 주사위인지 확인
        if result.player_name == battle.mob_name:
            # 몹의 공격 주사위 _sync_player_recovery_from_nickname
            if battle.pending_action["type"] == "combat" and battle.pending_action["phase"] == "mob_all_attack":
                # 몹의 공격 주사위 값 저장
                battle.pending_action["attack_roll"] = result.dice_value
                # 이미 메시지로 표시되었으므로 별도 처리 없음
                return
        
        # 선공 결정 중
        if battle.pending_action["type"] == "initiative":
            if result.player_name in battle.pending_action["waiting_for"]:
                battle.pending_action["results"][result.player_name] = result.dice_value
                battle.pending_action["waiting_for"].remove(result.player_name)
                
                # 모든 주사위가 굴려졌는지 확인
                if not battle.pending_action["waiting_for"]:
                    await self.process_initiative_results(battle)
        
        # 전투 중 주사위
        elif battle.pending_action["type"] == "combat":
            await self.process_combat_dice(battle, result)
        
        # 회복 주사위
        elif battle.pending_action["type"] == "recovery":
            if result.player_name in battle.pending_action["waiting_for"]:
                await self.process_recovery_dice(battle, result)
        
        # 플레이어 턴 중 공격
        elif battle.pending_action["type"] == "player_turn":
            if result.player_name == battle.pending_action["player"].real_name:
                # 플레이어가 공격 주사위를 굴렸음
                await self.handle_player_attack(battle, battle.pending_action["player"], result.dice_value)

    async def process_initiative_results(self, battle: AutoBattle):
        """선공 결정 결과 처리"""
        results = battle.pending_action["results"]
        
        # 결과 정렬
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        
        # 턴 순서 설정
        battle.turn_order = [name for name, _ in sorted_results]
        
        # 결과 표시
        result_text = "🎲 **선공 결정 완료!**\n\n"
        for i, (name, roll) in enumerate(sorted_results):
            result_text += f"{i+1}위: {name} - 🎲 {roll}\n"
        result_text += f"\n⚡ **{battle.turn_order[0]}**이(가) 먼저 시작합니다!"
        
        await battle.channel.send(result_text)
        
        # 전투 시작
        battle.pending_action = None
        await asyncio.sleep(2)
        view = MobSettingView(battle)
        await view.start_combat_round()
    
    async def process_combat_dice(self, battle: AutoBattle, result: DiceResult):
        """전투 주사위 처리"""
        action = battle.pending_action
        
        if action["phase"] == "mob_attack":
            # 단일 대상 공격 (이전 코드 유지)
            if result.player_name == action["target"]:
                defense_roll = result.dice_value
                attack_roll = action["attack_roll"]
                target_player = action["target_player"]
                
                view = MobSettingView(battle)
                await view.process_combat_result(
                    battle.mob_name, attack_roll,
                    target_player, defense_roll,
                    is_mob_attacking=True
                )
                
                battle.current_turn_index += 1
                battle.pending_action = None
                await view.process_turn()
        
        elif action["phase"] == "mob_all_attack":
            # 전체 공격 처리
            if result.player_name in action["waiting_for"]:
                action["defend_results"][result.player_name] = result.dice_value
                action["waiting_for"].remove(result.player_name)
                
                # 모든 플레이어가 주사위를 굴렸는지 확인
                if not action["waiting_for"]:
                    await self.process_all_attack_results(battle)
        
        elif action["phase"] == "focused_single":
            # 집중공격 단일 판정 (이전 코드 유지)
            if result.player_name == action["target_player"].real_name:
                defense_roll = result.dice_value
                attack_roll = action["attack_roll"]
                
                view = MobSettingView(battle)
                await view.process_focused_result(attack_roll, defense_roll, "single")
        
        elif action["phase"] == "focused_each":
            # 집중공격 각각 회피 (이전 코드 유지)
            if result.player_name == action["target_player"].real_name:
                defense_roll = result.dice_value
                attack_roll = action["attack_roll"]
                
                view = MobSettingView(battle)
                await view.process_focused_result(attack_roll, defense_roll, "each")

    async def process_all_attack_results(self, battle: AutoBattle):
        """전체 공격 결과 처리"""
        action = battle.pending_action
        
        # attack_roll이 없는 경우 처리
        if "attack_roll" not in action:
            logger.error("attack_roll이 pending_action에 없습니다")
            await battle.channel.send("⚠️ 몹의 공격 주사위 결과를 찾을 수 없습니다. 전투를 계속합니다.")
            
            # 기본값으로 처리
            attack_roll = 50  # 중간값으로 설정
        else:
            attack_roll = action["attack_roll"]
        
        defend_results = action["defend_results"]
        
        hit_messages = []
        eliminated_players = []
        
        for player in battle.players:
            if player.is_eliminated:
                continue
            
            defense_roll = defend_results.get(player.real_name, 0)
            
            if attack_roll > defense_roll:
                # 명중
                player.take_damage(1, 10)
                hit_messages.append(f"🎯 {player.real_name}({defense_roll}) 피격!")
                
                # 체력 동기화가 활성화된 경우 닉네임 업데이트
                if battle.health_sync:
                    new_nickname = update_nickname_health(player.user.display_name, player.real_current_health)
                    try:
                        await player.user.edit(nick=new_nickname)
                    except discord.Forbidden:
                        pass
                
                if player.is_eliminated:
                    eliminated_players.append(player.real_name)
            else:
                # 회피
                hit_messages.append(f"🛡️ {player.real_name}({defense_roll}) 회피!")
        
        # 결과 메시지
        result_msg = f"⚔️ **{battle.mob_name} 전체 공격({attack_roll})**\n" + "\n".join(hit_messages)
        
        if eliminated_players:
            result_msg += f"\n\n💀 **탈락:** {', '.join(eliminated_players)}"
            
            # 탈락 대사
            if battle.dialogue.enemy_killed:
                await battle.channel.send(f"**{battle.mob_name}**: {battle.dialogue.enemy_killed}")
        
        await battle.channel.send(result_msg)
        
        # 메인 메시지 업데이트
        view = MobSettingView(battle)
        await battle.main_message.edit(embed=view.create_battle_status_embed())
        
        # 체력 기반 대사 체크
        await view.check_mob_health_dialogue()
        
        # 턴 종료
        battle.current_turn_index += 1
        battle.pending_action = None
        await view.process_turn()

# mob_setting.py의 _sync_player_recovery_from_nickname 메서드 수정

    async def _sync_player_recovery_from_nickname(self, battle: AutoBattle, player_name: str) -> bool:
        """닉네임에서 체력을 읽어 회복이 있었는지 확인하고 전투에 반영"""
        logger.info(f"[DEBUG] Syncing recovery for player: {player_name}")
        
        # 해당 플레이어 찾기
        target_player = None
        for player in battle.players:
            if player.real_name == player_name:
                target_player = player
                break
        
        if not target_player:
            logger.warning(f"[DEBUG] Player {player_name} not found")
            return False
        
        try:
            # ✅ 핵심 수정: Member 객체를 다시 fetch해서 최신 닉네임 가져오기
            fresh_member = await battle.channel.guild.fetch_member(target_player.user.id)
            current_nickname = fresh_member.display_name
            logger.info(f"[DEBUG] Fresh nickname from server: {current_nickname}")
            
            # 기존 저장된 닉네임과 비교
            old_nickname = target_player.user.display_name
            if old_nickname != current_nickname:
                logger.info(f"[DEBUG] Nickname changed: {old_nickname} -> {current_nickname}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Failed to fetch fresh member info: {e}")
            # fallback to cached nickname
            current_nickname = target_player.user.display_name
        
        logger.info(f"[DEBUG] Using nickname: {current_nickname}")
        
        try:
            import re
            # 닉네임 형태: "이름/현재체력/최대체력%" 패턴 매칭
            health_pattern = r'/(\d+)/'
            matches = re.findall(health_pattern, current_nickname)
            
            if len(matches) >= 1:
                nickname_current_health = int(matches[0])  # 첫 번째 숫자가 현재 체력
                stored_current_health = target_player.real_current_health
                
                logger.info(f"[DEBUG] Health comparison - nickname: {nickname_current_health}, stored: {stored_current_health}")
                
                # 회복 여부 확인 (닉네임 체력 > 저장된 체력)
                if nickname_current_health > stored_current_health:
                    recovery_amount = nickname_current_health - stored_current_health
                    logger.info(f"[DEBUG] Recovery detected! Amount: {recovery_amount}")
                    
                    # 전투 체력 계산 및 적용
                    battle_recovery = max(1, recovery_amount // 10)  # 최소 1은 회복
                    
                    # 체력 업데이트
                    target_player.real_current_health = min(nickname_current_health, target_player.real_max_health)
                    target_player.current_health = min(target_player.current_health + battle_recovery, target_player.max_health)
                    target_player.hits_received = max(0, target_player.hits_received - battle_recovery)
                    
                    logger.info(f"[DEBUG] Applied recovery - battle: +{battle_recovery}, real: +{recovery_amount}")
                    logger.info(f"[DEBUG] New health values - battle: {target_player.current_health}/{target_player.max_health}, real: {target_player.real_current_health}/{target_player.real_max_health}")
                    
                    # ✅ 추가: Member 객체도 업데이트해서 다음에 올바른 닉네임 사용
                    try:
                        target_player.user = fresh_member
                        logger.info(f"[DEBUG] Updated player member object")
                    except:
                        pass
                    
                    # 회복 메시지 전송
                    await battle.channel.send(
                        f"💚 **{target_player.real_name} 회복 완료!**\n"
                        f"실제 체력: +{recovery_amount} HP\n"
                        f"전투 체력: +{battle_recovery} HP\n"
                        f"현재 상태: {target_player.real_current_health}/{target_player.real_max_health} HP\n"
                        f"⚔️ **전투에 반영되었습니다!**"
                    )
                    
                    # 전투 상태 업데이트
                    view = MobSettingView(battle)
                    await battle.main_message.edit(embed=view.create_battle_status_embed())
                    
                    # 플레이어 턴 중이면 턴 종료
                    if (battle.pending_action and 
                        battle.pending_action.get("type") == "player_turn" and 
                        battle.pending_action.get("player") == target_player):
                        
                        await battle.channel.send(f"⏭️ {target_player.real_name}님의 턴이 회복으로 인해 종료됩니다.")
                        battle.current_turn_index += 1
                        battle.pending_action = None
                        await self.process_turn()
                    
                    return True
            
            logger.info(f"[DEBUG] No recovery detected (health unchanged)")
            return False
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in recovery sync: {e}")
            return False
    
    async def process_recovery_dice(self, battle: AutoBattle, result: DiceResult):
        """회복 주사위 처리 (main.py의 auto_skip_turn_after_recovery 참고)"""
        logger.info(f"[DEBUG] process_recovery_dice called - player_name: {result.player_name}, dice_value: {result.dice_value}")
        logger.info(f"[DEBUG] Current pending_action: {battle.pending_action}")
        logger.info(f"[DEBUG] Battle players: {[p.real_name for p in battle.players]}")
        
        # ✅ 수정: dice_value가 0이거나 작을 때도 회복 동기화 시도
        if result.dice_value <= 0:
            logger.info(f"[DEBUG] Zero dice value - attempting recovery sync")
            view = MobSettingView(battle)
            success = await view._sync_player_recovery_from_nickname(battle, result.player_name)
            if success:
                logger.info(f"[DEBUG] Recovery sync successful for {result.player_name}")
            else:
                logger.info(f"[DEBUG] No recovery detected, trying alternative method")
                # ✅ 추가: 다른 방법으로도 시도
                await asyncio.sleep(1)  # 잠깐 기다린 후 다시 시도
                success = await view._sync_player_recovery_from_nickname(battle, result.player_name)
                if success:
                    logger.info(f"[DEBUG] Recovery sync successful on second attempt")
            return
        
        # 플레이어 턴이 아닌 경우도 회복 체크
        if not battle.pending_action or battle.pending_action.get("type") != "player_turn":
            logger.info(f"[DEBUG] Not a player turn, but checking for recovery sync")
            view = MobSettingView(battle)
            await view._sync_player_recovery_from_nickname(battle, result.player_name)
            return
        
        # 플레이어 회복 처리
        for player in battle.players:
            logger.info(f"[DEBUG] Checking player: {player.real_name} == {result.player_name}?")
            
            if player.real_name == result.player_name:
                logger.info(f"[DEBUG] Found matching player for recovery!")
                
                # pending_action 체크
                if battle.pending_action.get("player") != player:
                    logger.warning(f"[DEBUG] pending_action player mismatch!")
                    return
                
                # 회복량 계산
                real_heal = result.dice_value
                battle_heal = real_heal // 10
                
                if real_heal > 0 and battle_heal == 0:
                    battle_heal = 1
                
                # 최대 체력 체크
                if player.real_current_health >= player.real_max_health:
                    logger.info(f"[DEBUG] Player already at max health")
                    await battle.channel.send(
                        f"💚 {player.real_name}이(가) 회복을 시도했지만 이미 체력이 최대입니다!"
                    )
                else:
                    logger.info(f"[DEBUG] Healing - real: {real_heal}, battle: {battle_heal}")
                    
                    # 회복 적용
                    old_health = player.current_health
                    old_real_health = player.real_current_health
                    player.heal(battle_heal, real_heal)
                    
                    logger.info(f"[DEBUG] Health after healing - battle: {old_health} -> {player.current_health}, real: {old_real_health} -> {player.real_current_health}")
                    
                    # 성공 메시지 표시
                    await battle.channel.send(
                        f"💚 **체력 회복**\n"
                        f"회복물품을(를) 사용했습니다!\n"
                        f"회복량\n"
                        f"+{real_heal} HP\n"
                        f"현재 체력\n"
                        f"{player.real_current_health}/{player.real_max_health} HP\n"
                        f"⚔️ **전투 효과**\n"
                        f"회복으로 인해 턴을 소모했습니다!"
                    )
                    
                    # 체력 동기화가 활성화된 경우 닉네임 즉시 업데이트
                    if battle.health_sync:
                        new_nickname = update_nickname_health(player.user.display_name, player.real_current_health)
                        try:
                            await player.user.edit(nick=new_nickname)
                            logger.info(f"[DEBUG] Nickname updated to: {new_nickname}")
                        except discord.Forbidden:
                            logger.warning(f"[DEBUG] Failed to update nickname - no permission")
                            player.nickname_update_failed = True
                        except Exception as e:
                            logger.error(f"[DEBUG] Failed to update nickname: {e}")
                            player.nickname_update_failed = True
                
                # 메인 메시지 업데이트
                view = MobSettingView(battle)
                await battle.main_message.edit(embed=view.create_battle_status_embed())
                
                # 턴 넘김 메시지
                await battle.channel.send(f"⏭️💚 {player.real_name}님이 회복으로 턴을 소모했습니다.")
                
                # 턴 종료 처리
                await self.end_player_turn(battle)
                return

        logger.warning(f"[DEBUG] Player not found for recovery: {result.player_name}")

        
    async def handle_player_attack(self, battle: AutoBattle, player: AutoBattlePlayer, attack_roll: int):
        """플레이어 공격 처리"""
        await battle.channel.send(f"⚔️ {player.real_name}이(가) {battle.mob_name}을(를) 공격합니다!")
        
        # 몹 방어 주사위 (스킬 시스템 적용)
        await asyncio.sleep(2)
        defense_roll = await self.roll_mob_dice(battle, "defense")
        
        # 전투 결과 계산
        view = MobSettingView(battle)
        await view.process_combat_result(
            player, attack_roll,
            battle.mob_name, defense_roll,  # 몬스터는 문자열로 전달
            is_mob_attacking=False
        )
        
        # 턴 종료
        player.has_acted_this_turn = True
        battle.current_turn_index += 1
        battle.pending_action = None
        await view.process_turn()
    
    async def handle_mob_surrender(self, channel_id: int, user_id: int):
        """몹 전투 항복 처리"""
        if channel_id not in self.bot.mob_battles:
            return False
        
        battle = self.bot.mob_battles[channel_id]
        
        # 창시자가 항복하는 경우
        if user_id == battle.creator.id:
            battle.is_active = False
            
            await battle.channel.send(f"🏳️ **몹 항복!** {battle.mob_name}이(가) 항복했습니다!")
            
            # 메인 메시지 정리
            if battle.main_message:
                await battle.main_message.edit(
                    embed=discord.Embed(
                        title="전투 종료",
                        description="몹이 항복했습니다!",
                        color=discord.Color.blue()
                    ),
                    view=None
                )
            
            self.bot.mob_battles.pop(channel_id, None)
            return True
        
        # 플레이어가 항복하는 경우
        for player in battle.players:
            if user_id == player.user.id and not player.is_eliminated:
                player.is_eliminated = True
                
                await battle.channel.send(f"🏳️ {player.real_name}이(가) 항복했습니다!")
                
                # 전투 종료 체크
                await MobSettingView(battle).check_battle_end()
                return True
        
        return False

    async def process_round_transition(self, battle: AutoBattle):
        """라운드 전환 시 스킬 처리"""
        from skills.skill_manager import skill_manager
        
        channel_id = str(battle.channel.id)
        round_num = battle.round_count
        
        # 스킬 라운드 감소 처리
        expired_messages = await skill_manager.process_round_end(channel_id, round_num)
        
        # 만료 메시지 출력
        for msg in expired_messages:
            await battle.channel.send(msg)
        
        # 현재 활성 스킬 확인
        channel_state = skill_manager.get_channel_state(channel_id)
        active_skills = channel_state.get("active_skills", {})
        
        if active_skills:
            # 남은 스킬 정보 표시 (선택적)
            skill_info = "📋 **활성 스킬 현황**\n"
            for skill_name, skill_data in active_skills.items():
                rounds_left = skill_data.get("rounds_left", 0)
                user_name = skill_data.get("user_name", "Unknown")
                skill_info += f"• {skill_name} ({user_name}): {rounds_left}라운드 남음\n"
            
            await battle.channel.send(skill_info)

# 봇에 통합하는 함수
async def setup(bot):
    """봇에 몹 세팅 기능 추가"""
    try:
        await bot.add_cog(MobSetting(bot))
        logger.info("MobSetting Cog 로드 완료")
    except Exception as e:
        logger.error(f"MobSetting Cog 로드 실패: {e}")