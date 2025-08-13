# main.py
import asyncio
import logging
import pytz
import traceback
from concurrent.futures import ThreadPoolExecutor
import discord
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import signal
import sys
from typing import Optional
import re
from datetime import datetime, timedelta
from typing import Optional
from battle import get_battle_game
from discord.ext import commands
from mob_setting import setup as setup_mob_setting
from mob_setting import MobSetting
from mob_setting import AutoBattle, MobSettingView
from mob_setting import *
from mob_ai import create_mob_ai, AutonomousAIController, AIPersonality
from pathlib import Path

# === 스킬 시스템 import 추가 ===
from skills.skill_manager import skill_manager
from skills.skill_effects import skill_effects
import battle_admin

# 모듈 import
from utility import (
    cache_manager, get_user_inventory, get_user_permissions, 
    increment_daily_values, cache_daily_metadata
)
from BambooForest import init_bamboo_system, handle_message, handle_reaction
from shop import (
    get_inventory_manager, create_item_autocomplete_choices, 
    create_revoke_autocomplete_choices
)
from joker import JokerGame, get_player_name
from blackjack import BlackjackGame
from dice_poker import DicePokerGame, DicePokerJoinView
# main.py의 import 섹션에 추가
from fishing import get_fishing_game
from dalgona import get_dalgona_game, DalgonaShape
from dart import get_dart_game
from mafia import get_mafia_game, MafiaJoinView
# 로깅 설정
from skills.heroes import (
    SKILL_MAPPING,
    SKILL_ID_MAPPING,
    get_skill_by_name,
    get_all_skill_names,
    BaseSkill,
    SkillType
)
# 로깅 설정 - 한글 처리 개선
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 표준 출력으로 변경
        logging.FileHandler('bot.log', encoding='utf-8')  # 파일 로그는 UTF-8
    ]
)

# 또는 문제가 되는 로거만 별도 처리
mob_logger = logging.getLogger('mob_setting')
mob_logger.handlers = []  # 기존 핸들러 제거
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
mob_logger.addHandler(handler)

# 테스트 모듈 추가
try:
    from mob_test import handle_mob_test_command
except ImportError:
    handle_mob_test_command = None
    logger.warning("mob_test 모듈을 찾을 수 없습니다. 테스트 기능이 제한됩니다.")

# 봇 설정
BOT_TOKEN = ""

# Discord 설정
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.dm_messages = True
intents.guilds = True
intents.guild_messages = True
intents.presences = False
intents.typing = False
mob_setting_handler = None

# 봇 인스턴스 생성
class CustomBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


bot = CustomBot(
    command_prefix="!",
    intents=intents,
    heartbeat_timeout=60,
    guild_ready_timeout=10.0,
    assume_unsync_clock=False,
    max_messages=200,
    member_cache_flags=discord.MemberCacheFlags.all(),
    chunk_guilds_at_startup=True,
    status=discord.Status.online,
    activity=None,
    allowed_mentions=discord.AllowedMentions.none(),
    enable_debug_events=False
)



# 전역 스레드 풀
thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='BotWorker')

# 게임 관리
joker_game = JokerGame()
active_blackjack_games = {}  # channel_id: BlackjackGame
blackjack_join_views = {}  # channel_id: BlackjackJoinView
active_dice_poker_games = {}

# 테스트 블랙잭 시작 함수
async def start_test_blackjack(original_interaction, test_user):
    """테스트 모드로 블랙잭 시작"""
    from blackjack import BlackjackGame
    
    players = [test_user]
    bet_amounts = {test_user.id: 10}  # 기본 베팅 10
    
    # 기존 메시지 수정
    embed = discord.Embed(
        title="🎰 블랙잭 테스트 모드",
        description=f"{test_user.display_name}님의 테스트 게임을 시작합니다!\n\n"
                   "**테스트 기능:**\n"
                   "• 21점 동점 시 플레이어 승리 확인\n"
                   "• 다양한 상황 테스트 가능",
        color=discord.Color.orange()
    )
    
    await original_interaction.edit_original_response(embed=embed, view=None)
    
    # 게임 생성
    game = BlackjackGame(original_interaction, players, bet_amounts, bot)
    game.test_mode = True
    active_blackjack_games[original_interaction.channel_id] = game
    
    try:
        await game.start_game()
    finally:
        if original_interaction.channel_id in active_blackjack_games:
            del active_blackjack_games[original_interaction.channel_id]

# main.py의 process_admin_recovery 함수 수정
async def process_admin_recovery(channel: discord.TextChannel, admin_user_id: int, recovery_amount: int):
    """Admin 회복 주사위 결과 처리"""
    try:
        # Admin 사용자 가져오기
        admin_user = channel.guild.get_member(admin_user_id)
        if not admin_user:
            await channel.send("Admin 사용자를 찾을 수 없습니다.")
            return
        
        # Admin이 전투 중인지 확인
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        
        # 전투 중인 경우 체력 업데이트 알림
        try:
            from battle import get_battle_game
            battle_game = get_battle_game()
            await battle_game.handle_recovery_update(int(user_id), current_health, new_health)

            # Admin 전투도 확인
            from battle_admin import get_admin_battle_manager
            admin_manager = get_admin_battle_manager()
            await admin_manager.handle_recovery_update(int(user_id), current_health, new_health)
        except Exception as e:
            logger.error(f"전투 체력 업데이트 실패: {e}")
            # 전투 업데이트 실패해도 회복은 성공으로 처리
        
        # 결과 메시지
        embed = discord.Embed(
            title="💚 체력 회복",
            description=f"{selected_item['name']}을(를) 사용했습니다!",
            color=discord.Color.green()
        )
        embed.add_field(name="회복량", value=f"+{health_recovered} HP", inline=True)
        embed.add_field(name="현재 체력", value=f"{new_health}/100 HP", inline=True)
        
        # 전투 중인 경우 턴 소모 메시지 추가
        if is_in_battle and is_user_turn:
            embed.add_field(name="⚔️ 전투 효과", value="회복으로 인해 턴을 소모했습니다!", inline=False)
        
        await interaction.followup.send(embed=embed)
        
        # 전투 중이고 본인 턴인 경우 자동 턴 넘김 처리
        if is_in_battle and is_user_turn:
            await auto_skip_turn_after_recovery(interaction.user.id, channel_id, battle_type, interaction.user.display_name)
        
    except Exception as e:
        logger.error(f"회복 명령어 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send("회복 처리 중 오류가 발생했습니다.")

async def check_and_validate_battle_turn(user_id: int, channel_id: int) -> dict:
    """
    사용자가 현재 전투 중인지, 그리고 본인 턴인지 확인
    
    Returns:
        dict: {
            "in_battle": bool,
            "is_user_turn": bool, 
            "battle_type": str  # "normal" or "admin" or "mob" or None
        }
    """
    result = {
        "in_battle": False,
        "is_user_turn": False,
        "battle_type": None
    }
    
    try:
        
        if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
            battle = bot.mob_battles[channel_id]
            if battle.is_active:
                result["in_battle"] = True
                result["battle_type"] = "mob"
                
                # 현재 플레이어 턴인지 확인
                if battle.pending_action and battle.pending_action.get("type") == "player_turn":
                    player = battle.pending_action.get("player")
                    if player and player.user.id == user_id:
                        result["is_user_turn"] = True
                
                return result

        # 일반 전투 확인
        from battle import get_battle_game
        battle_game = get_battle_game()
        
        if channel_id in battle_game.active_battles:
            battle_data = battle_game.active_battles[channel_id]
            result["in_battle"] = True
            result["battle_type"] = "normal"
            
            # 다이스 대기 중인지 확인
            if channel_id in battle_game.pending_dice:
                pending = battle_game.pending_dice[channel_id]
                if user_id in pending["waiting_for"]:
                    result["is_user_turn"] = True
            
            return result
        
        # Admin 전투 확인
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        
        if channel_id in admin_manager.active_battles:
            battle = admin_manager.active_battles[channel_id]
            result["in_battle"] = True
            result["battle_type"] = "admin"
            
            # 다이스 대기 중인지 확인
            if battle.pending_dice:
                if user_id in battle.pending_dice["waiting_for"]:
                    result["is_user_turn"] = True
            
            return result
            
    except Exception as e:
        logger.error(f"전투 턴 확인 실패: {e}")
    
    return result

async def auto_skip_turn_after_recovery(user_id: int, channel_id: int, battle_type: str, player_name: str):
    """
    회복 후 자동 턴 넘김 처리
    """
    try:
        if battle_type == "mob":
            # 몹 전투에서 회복 처리
            if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
                battle = bot.mob_battles[channel_id]
                
                if battle.pending_action and battle.pending_action.get("type") == "player_turn":
                    player = battle.pending_action.get("player")
                    if player and player.user.id == user_id:
                        from mob_setting import MobSetting, DiceResult
                        mob_setting = MobSetting(bot)
                        result = DiceResult(player_name=player.real_name, dice_value=0)
                        await mob_setting.process_recovery_dice(battle, result)
                        return
        
        elif battle_type == "normal":
            # 일반 전투 턴 넘김
            from battle import get_battle_game
            battle_game = get_battle_game()
            
            if channel_id in battle_game.pending_dice:
                pending = battle_game.pending_dice[channel_id]
                if user_id in pending["waiting_for"]:
                    pending["waiting_for"].remove(user_id)
                    
                    # 가상의 다이스 결과 추가 (0으로 처리)
                    from battle_utils import extract_real_name
                    real_name = extract_real_name(player_name)
                    
                    from battle import DiceResult
                    pending["results"][user_id] = DiceResult(
                        player_name=real_name,
                        dice_value=0,
                        user_id=user_id
                    )
                    
                    # 전투 채널에 턴 넘김 메시지
                    battle_data = battle_game.active_battles[channel_id]
                    await battle_data["message"].channel.send(f"⏭️💚 {real_name}님이 회복으로 턴을 소모했습니다.")
                    
                    # 모두 행동했는지 확인
                    if not pending["waiting_for"]:
                        await battle_game._process_dice_results(channel_id)
        
        elif battle_type == "admin":
            # Admin 전투 턴 넘김
            from battle_admin import get_admin_battle_manager
            admin_manager = get_admin_battle_manager()
            
            battle = admin_manager.active_battles[channel_id]
            if battle.pending_dice and user_id in battle.pending_dice["waiting_for"]:
                battle.pending_dice["waiting_for"].remove(user_id)
                battle.pending_dice["results"][user_id] = 0  # 0으로 처리
                
                # 플레이어 이름 찾기
                real_name = None
                
                # Admin ID 확인 (특정 ID로 하드코딩)
                ADMIN_IDS = [1007172975222603798, 1090546247770832910]
                
                if user_id in ADMIN_IDS:
                    # Admin인 경우 몬스터 이름 사용
                    real_name = battle.monster_name
                else:
                    # 일반 유저인 경우
                    from battle_utils import extract_real_name
                    real_name = extract_real_name(player_name)
                
                await battle.message.channel.send(f"⏭️💚 {real_name}님이 회복으로 턴을 소모했습니다.")
                
                # 모두 행동했는지 확인
                if not battle.pending_dice["waiting_for"]:
                    if battle.pending_dice["phase"] == "init":
                        await admin_manager._process_init_results(channel_id)
                    else:
                        await admin_manager._process_combat_results(channel_id)
                        
    except Exception as e:
        logger.error(f"자동 턴 넘김 처리 실패: {e}")

class BotManager:
    """봇 관리 클래스"""
    
    def __init__(self):
        self.scheduler = None
        self.bamboo_system = None
        self.inventory_manager = None
        self.gateway_task = None
        self.health_check_interval = 300
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self._shutdown_event = asyncio.Event()
        self._initialized = False  # 초기화 플래그 추가
        self._scheduler_started = False  # 스케줄러 시작 플래그 추가

    async def initialize(self):
        """봇 초기화"""
        # 이미 초기화되었으면 스킵
        if self._initialized:
            logger.warning("봇이 이미 초기화되어 있습니다. 중복 초기화 스킵.")
            return
            
        try:
            # 대나무숲 시스템 초기화
            self.bamboo_system = init_bamboo_system(bot)

            # 인벤토리 매니저 초기화
            self.inventory_manager = get_inventory_manager()
            
            # 캐시 관리자 시작
            await cache_manager.start_background_cleanup()
            
            # 메타데이터 캐싱
            await cache_daily_metadata()
            
            # 스케줄러 설정
            self._setup_scheduler()
            
            # Gateway 모니터링 시작
            self.gateway_task = asyncio.create_task(self._monitor_gateway())
            
            bot.mob_setting_views = {}
            mob_setting_handler = MobSetting(bot)

            self._initialized = True  # 초기화 완료 표시
            logger.info("봇 초기화 완료")
            
        except Exception as e:
            logger.error(f"봇 초기화 실패: {e}")
            raise

    def _setup_scheduler(self):
        """스케줄러 설정"""
        # 스케줄러가 이미 실행 중이면 스킵
        if self.scheduler and self.scheduler.running:
            logger.warning("스케줄러가 이미 실행 중입니다. 중복 설정 스킵.")
            return
            
        self.scheduler = AsyncIOScheduler(
            timezone=pytz.timezone("Asia/Seoul"),
            job_defaults={
                'misfire_grace_time': 60,
                'coalesce': True,
                'max_instances': 1
            }
        )
        
        # 일일 메타데이터 캐싱 (새벽 5시)
        self.scheduler.add_job(
            self._safe_cache_daily_metadata, 
            'cron', 
            hour=5, 
            minute=0,
            id='daily_cache',
            replace_existing=True
        )
        
        # 일일 코인 증가 (자정)
        self.scheduler.add_job(
            self._safe_increment_daily_values, 
            'cron', 
            hour=0, 
            minute=0,
            id='daily_coins',
            replace_existing=True
        )
        
        # 스케줄러 시작 전 확인
        if not self._scheduler_started:
            self.scheduler.start()
            self._scheduler_started = True
            logger.info("스케줄러 시작됨")
        else:
            logger.warning("스케줄러가 이미 시작되어 있습니다.")

    async def _safe_cache_daily_metadata(self):
        """안전한 메타데이터 캐싱"""
        try:
            await cache_daily_metadata()
        except Exception as e:
            logger.error(f"일일 메타데이터 캐싱 실패: {e}")

    async def _safe_increment_daily_values(self):
        """안전한 일일 코인 증가"""
        try:
            await increment_daily_values()
        except Exception as e:
            logger.error(f"일일 코인 증가 실패: {e}")

    async def _monitor_gateway(self):
        """Gateway 상태 모니터링"""
        consecutive_high_latency = 0
        
        while not self._shutdown_event.is_set():
            try:
                if bot.is_closed():
                    logger.warning("봇 연결이 끊어졌습니다. 재연결 시도 중...")
                    self.reconnect_attempts += 1
                    
                    if self.reconnect_attempts > self.max_reconnect_attempts:
                        logger.error("최대 재연결 시도 횟수 초과")
                        break
                    
                    await asyncio.sleep(30)
                    continue
                
                latency = bot.latency * 1000
                
                if latency < 0:
                    logger.warning("봇이 연결되지 않은 상태입니다")
                elif latency > 2000:
                    consecutive_high_latency += 1
                    logger.warning(f"높은 지연 시간 감지: {latency:.2f}ms (연속 {consecutive_high_latency}회)")
                    
                    if consecutive_high_latency >= 3:
                        logger.error("지속적인 높은 지연 시간 - 재연결 고려 필요")
                else:
                    consecutive_high_latency = 0
                    if latency > 1000:
                        logger.info(f"지연 시간: {latency:.2f}ms")
                
                await asyncio.sleep(self.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gateway 모니터링 실패: {e}")
                await asyncio.sleep(30)

    async def shutdown(self):
        """봇 종료 처리 (스킬 시스템 포함)"""
        logger.info("봇 종료 시작...")
        self._shutdown_event.set()
        
        # === 스킬 시스템 정리 추가 ===
        try:
            await skill_manager.force_save()
            await skill_effects.clear_cache()
            logger.info("스킬 시스템 데이터 저장 완료")
        except Exception as e:
            logger.error(f"스킬 시스템 정리 오류: {e}")
        
        try:
            cache_manager.save_all_caches()
            logger.info("모든 캐시 저장 완료")
        except Exception as e:
            logger.error(f"캐시 저장 오류: {e}")
        
        shutdown_tasks = []
        
        if self.scheduler and self.scheduler.running:
            shutdown_tasks.append(
                asyncio.create_task(self._shutdown_scheduler())
            )
        
        if self.gateway_task and not self.gateway_task.done():
            self.gateway_task.cancel()
            shutdown_tasks.append(self.gateway_task)
        
        if self.bamboo_system:
            shutdown_tasks.append(
                asyncio.create_task(self._shutdown_bamboo_system())
            )
        
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("일부 종료 작업이 타임아웃되었습니다")
        
        thread_pool.shutdown(wait=False, cancel_futures=True)
        
        logger.info("봇 종료 완료")

    async def _shutdown_scheduler(self):
        """스케줄러 안전 종료"""
        try:
            self.scheduler.shutdown(wait=False)
        except Exception as e:
            logger.error(f"스케줄러 종료 실패: {e}")

    async def _shutdown_bamboo_system(self):
        """대나무숲 시스템 안전 종료"""
        try:
            if hasattr(self.bamboo_system, 'close'):
                await self.bamboo_system.close()
            self.bamboo_system.shutdown()
        except Exception as e:
            logger.error(f"대나무숲 시스템 종료 실패: {e}")

# 전역 봇 매니저
bot_manager = BotManager()

# 시그널 핸들러 설정
def signal_handler(sig, frame):
    logger.info(f"시그널 {sig} 받음, 종료 시작...")
    asyncio.create_task(shutdown_bot())

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def shutdown_bot():
    """봇 안전 종료"""
    await bot_manager.shutdown()
    if not bot.is_closed():
        await bot.close()

# === 스킬 시스템 상태 체크 함수 추가 ===
async def _perform_skill_system_health_check():
    """스킬 시스템 상태 체크"""
    try:
        test_channel = "health_check"
        test_user = "health_check_user"
        
        success = skill_manager.add_skill(
            test_channel, "오닉셀", test_user, "테스트", test_user, "테스트", 1
        )
        if success:
            skill_manager.remove_skill(test_channel, "오닉셀")
        
        final_value, messages = await skill_effects.process_dice_roll(
            test_user, 75, test_channel
        )
        
        logger.info("✅ 스킬 시스템 상태 체크 완료")
        
    except Exception as e:
        logger.error(f"스킬 시스템 상태 체크 실패: {e}")

async def _verify_skill_system():
    """스킬 시스템 검증"""
    try:
        from skills.heroes import SKILL_MAPPING, get_all_skill_names
        
        loaded_skills = len(SKILL_MAPPING)
        skill_names = get_all_skill_names()
        
        logger.info(f"📊 스킬 시스템 상태:")
        logger.info(f"  - 로드된 스킬: {loaded_skills}개")
        logger.info(f"  - 사용 가능: {', '.join(skill_names[:5])}...")
        
        # Cog 확인
        if "SkillCog" in bot.cogs:
            logger.info("  - SkillCog: ✅ 활성")
        else:
            logger.warning("  - SkillCog: ❌ 비활성")
            
    except Exception as e:
        logger.error(f"스킬 시스템 검증 실패: {e}")


# 이벤트 핸들러
@bot.event
async def on_ready():
    """봇 시작 시 초기화 (오류 해결 버전)"""
    try:
        logger.info(f'✅ {bot.user.name}이 성공적으로 로그인했습니다!')
        logger.info(f'봇 ID: {bot.user.id}')
        logger.info('=' * 50)
        
        # === 1. 스킬 시스템 초기화 ===
        skill_system_loaded = False
        
        try:
            # 방법 1: extension으로 로드 (권장)
            try:
                await bot.load_extension("skills.skill")
                logger.info("✅ 스킬 시스템 Extension 로드 완료")
                skill_system_loaded = True
            except commands.ExtensionAlreadyLoaded:
                logger.info("✅ 스킬 시스템 Extension 이미 로드됨")
                skill_system_loaded = True
            except Exception as ext_error:
                logger.warning(f"Extension 로드 실패, Cog 직접 로드 시도: {ext_error}")
                
                # 방법 2: Cog 직접 로드 (백업)
                try:
                    # 먼저 필요한 시스템들 초기화
                    from skills.skill_manager import skill_manager
                    from skills.skill_effects import skill_effects
                    
                    # 매니저와 효과 시스템 초기화
                    if not skill_manager.initialize():
                        await skill_manager.initialize()
                        logger.info("✅ 스킬 매니저 초기화 완료")
                    
                    if not skill_effects.initialize():
                        await skill_effects.initialize()
                        logger.info("✅ 스킬 효과 시스템 초기화 완료")
                    
                    # Cog 로드
                    from skills.skill import SkillCog
                    if "SkillCog" not in [cog_name for cog_name in bot.cogs]:
                        cog_instance = SkillCog(bot)
                        await bot.add_cog(cog_instance)
                        logger.info("✅ 스킬 시스템 Cog 직접 로드 완료")
                        skill_system_loaded = True
                    else:
                        logger.info("✅ 스킬 시스템 Cog 이미 로드됨")
                        skill_system_loaded = True
                        
                except ImportError as ie:
                    logger.error(f"❌ 스킬 모듈 import 실패: {ie}")
                    logger.error("필요한 파일 확인:")
                    logger.error("  - skills/skill.py")
                    logger.error("  - skills/skill_manager.py")
                    logger.error("  - skills/skill_effects.py")
                    logger.error("  - heroes/__init__.py")
                    
                except Exception as cog_error:
                    logger.error(f"❌ 스킬 Cog 로드 실패: {cog_error}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            # 스킬 시스템 상태 확인
            if skill_system_loaded:
                await _verify_skill_system()
            else:
                logger.warning("⚠️ 스킬 시스템 없이 봇 실행 중")
                
        except Exception as e:
            logger.error(f"❌ 스킬 시스템 초기화 실패: {e}")
            logger.warning("⚠️ 스킬 시스템 없이 봇 실행 중")
        
        
        # === 2. BambooForest 초기화 (await 제거) ===
        try:
            # init_bamboo_system은 동기 함수이므로 await 사용하지 않음
            init_bamboo_system(bot)
            logger.info("✅ 대나무 숲 시스템 초기화 완료")
        except Exception as e:
            logger.error(f"❌ 대나무 숲 초기화 실패: {e}")
            # 계속 진행
        
        # === 3. 캐시 시스템 초기화 ===
        try:
            await cache_daily_metadata()
            logger.info("✅ 캐시 시스템 초기화 완료")
        except Exception as e:
            logger.error(f"❌ 캐시 초기화 실패: {e}")
            # 계속 진행
        
        # === 4. 기타 시스템 초기화 ===
        try:
            # 스킬 상태 파일 확인
            from pathlib import Path
            skill_states_file = Path("skills/data/skill_states.json")
            if skill_states_file.exists():
                logger.info("스킬 상태 파일이 존재합니다.")
            else:
                logger.info("새로운 스킬 상태 파일이 생성됩니다.")
        except Exception as e:
            logger.warning(f"스킬 상태 파일 확인 실패: {e}")
        
        # === 5. 명령어 동기화 ===
        try:
            synced = await bot.tree.sync()
            logger.info(f"✅ {len(synced)}개의 명령어가 동기화되었습니다")
        except Exception as e:
            logger.error(f"❌ 명령어 동기화 실패: {e}")
        
        # === 6. 몹 세팅 시스템 초기화 ===
        try:
            # global 변수 문제 해결
            global mob_setting_handler
            
            # 몹 전투 딕셔너리 초기화
            if not hasattr(bot, 'mob_battles'):
                bot.mob_battles = {}
            
            # MobSetting 핸들러 생성
            mob_setting_handler = MobSetting(bot)
            
            # 몹 세팅 설정
            await setup_mob_setting(bot)
            
            logger.info("✅ 몹 세팅 시스템이 초기화되었습니다")
        except Exception as e:
            logger.error(f"❌ 몹 세팅 초기화 실패: {e}")
        
        # === 7. 스킬 시스템 상태 체크 ===
        try:
            health_check_result = await perform_skill_system_health_check()
            if health_check_result:
                logger.info("✅ 스킬 시스템 상태: 정상")
            else:
                logger.warning("⚠️ 스킬 시스템에 일부 문제가 있지만 계속 진행합니다")
        except Exception as e:
            logger.warning(f"스킬 시스템 상태 체크 실패: {e}")
        
        # === 8. 완료 메시지 ===
        logger.info("🚀 모든 시스템 초기화 완료!")
        
    except Exception as e:
        logger.error(f"❌ 봇 초기화 중 치명적 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        # 오류가 있어도 봇은 계속 실행

async def perform_skill_system_health_check():
    """스킬 시스템 상태 체크 (완전 수정 버전)"""
    try:
        # 1. 스킬 매니저 초기화 상태 확인
        if not hasattr(skill_manager, '_initialized') or not skill_manager._initialized:
            logger.warning("스킬 매니저가 초기화되지 않았습니다.")
            return False
        
        # 2. 스킬 효과 시스템 초기화 상태 확인
        if not skill_effects.is_initialized():
            logger.warning("스킬 효과 시스템이 초기화되지 않았습니다.")
            return False
        
        # 3. 스킬 모듈 로드 확인
        try:
            # heroes 모듈에서 SKILL_MAPPING 가져오기
            from skills.heroes import SKILL_MAPPING, SKILL_ID_MAPPING, get_all_skill_names
            
            # 로드된 스킬 확인
            loaded_skills = len(SKILL_MAPPING)
            loaded_skill_ids = len(SKILL_ID_MAPPING)
            
            logger.info(f"로드된 스킬: {loaded_skills}개 (이름 기준)")
            logger.info(f"로드된 스킬 ID: {loaded_skill_ids}개")
            
            # 사용 가능한 스킬 목록
            available_skills = get_all_skill_names()
            logger.debug(f"사용 가능: {', '.join(available_skills[:5])}...")  # 처음 5개만 표시
            
            if loaded_skills == 0:
                logger.warning("로드된 스킬이 없습니다.")
                SKILL_SYSTEM_AVAILABLE = False
            else:
                SKILL_SYSTEM_AVAILABLE = True
                
        except ImportError as e:
            logger.warning(f"스킬 모듈 import 실패: {e}")
            
            # 백업: skill_adapter 경유
            try:
                from skills.skill_adapter import get_skill_priority
                from skills.heroes import SKILL_MAPPING
                
                loaded_skills = len(SKILL_MAPPING) if SKILL_MAPPING else 0
                logger.info(f"백업 경로에서 스킬 로드: {loaded_skills}개")
                
                SKILL_SYSTEM_AVAILABLE = loaded_skills > 0
                
            except ImportError:
                logger.warning("스킬 모듈을 찾을 수 없습니다.")
                SKILL_SYSTEM_AVAILABLE = False
        
        # 4. 스킬 Cog 확인
        if "SkillCog" not in bot.cogs:
            logger.warning("SkillCog가 로드되지 않았습니다.")
            return False
        
        # 5. 간단한 기능 테스트
        try:
            test_channel_id = "health_check_test"
            test_result = skill_manager.get_channel_state(test_channel_id)
            
            if not isinstance(test_result, dict):
                logger.warning("스킬 매니저 기본 기능에 문제가 있습니다.")
                return False
        except Exception as e:
            logger.warning(f"스킬 시스템 기본 기능 테스트 실패: {e}")
            return False
        
        logger.info("스킬 시스템 모든 구성요소가 정상 작동합니다.")
        return True
        
    except Exception as e:
        logger.error(f"스킬 시스템 상태 체크 중 오류: {e}")
        return False

@bot.event
async def on_message(message):
    """메시지 이벤트 처리 (스킬 시스템 + 몹 전투 통합)"""
    if message.author.bot:
        # 다이스 봇 메시지 처리
        if message.author.id == 218010938807287808:  # 다이스 봇 ID
            channel_id = message.channel.id
            channel_id_str = str(channel_id)
            
            # 주사위 메시지 파싱
            dice_pattern = r"`([^`]+)`님이.*?주사위를\s*굴\s*려.*?\*\*(\d+)\*\*.*?나왔습니다"
            match = re.search(dice_pattern, message.content)
            
            if match:
                player_name = match.group(1).strip()
                dice_value = int(match.group(2))

                # === 스킬 시스템 주사위 처리 ===
                try:
                    # 실제 유저 ID 찾기
                    user_id = None
                    if message.guild:
                        for member in message.guild.members:
                            if player_name in member.display_name:
                                user_id = str(member.id)
                                break
                    
                    if user_id:
                        # 스킬 효과 적용
                        final_value, skill_messages = await skill_effects.process_dice_roll(
                            user_id, dice_value, channel_id_str
                        )
                        
                        # 스킬 효과 메시지 전송
                        if skill_messages:
                            for skill_message in skill_messages:
                                await message.channel.send(skill_message)
                        
                        # 값이 변경된 경우 알림
                        if final_value != dice_value:
                            value_change_msg = f"🎲 **{player_name}**님의 주사위 결과: {dice_value} → **{final_value}**"
                            await message.channel.send(value_change_msg)
                            
                        # 변경된 값으로 전투 처리
                        dice_value = final_value
                
                except Exception as e:
                    logger.error(f"스킬 주사위 처리 오류: {e}")

                # === 몹 전투 다이스 처리 ===
                if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
                    try:
                        global mob_setting_handler
                        if mob_setting_handler:
                            await mob_setting_handler.process_mob_dice_message(message)
                    except Exception as e:
                        logger.error(f"몹 전투 주사위 처리 오류: {e}")

                # === 기존 전투 시스템들 처리 ===
                # Admin 회복 주사위 처리 확인
                if hasattr(회복_command, 'pending_admin_recovery') and channel_id in 회복_command.pending_admin_recovery:
                    recovery_data = 회복_command.pending_admin_recovery[channel_id]
                    
                    # 30초 이내인지 확인
                    if (datetime.now() - recovery_data["timestamp"]).total_seconds() < 30:
                        # Admin인지 확인
                        if player_name in ["system | 시스템", "system", "시스템"]:
                            await process_admin_recovery(message.channel, recovery_data["user_id"], dice_value)
                            del 회복_command.pending_admin_recovery[channel_id]
                            return
                
                # 일반 전투 처리
                from battle import get_battle_game
                battle_game = get_battle_game()
                await battle_game.process_dice_message(message)
                
                # Admin 전투 처리
                from battle_admin import get_admin_battle_manager
                admin_manager = get_admin_battle_manager()
                await admin_manager.process_dice_message(message)
                
        return
    
    # 턴 넘김 처리
    if message.content == "!턴넘김":
        channel_id = message.channel.id
        
        # 몹 전투 턴넘김 처리
        if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
            try:
                battle = bot.mob_battles[channel_id]
                if battle.is_active and battle.turn_order:
                    # 현재 턴 확인
                    if battle.current_turn_index < len(battle.turn_order):
                        current_turn = battle.turn_order[battle.current_turn_index]
                        user_name = message.author.display_name
                        
                        # Admin 권한 확인
                        is_admin = (
                            user_name in ["system | 시스템", "system", "시스템"] or
                            str(message.author.id) in ["1007172975222603798", "1090546247770832910"]
                        )
                        
                        # 몹 턴인 경우
                        if current_turn == battle.mob_name:
                            if is_admin:
                                await message.channel.send(f"⏭️ Admin이 {battle.mob_name}의 턴을 넘겼습니다.")
                                # 턴 넘김 처리
                                battle.current_turn_index += 1
                                if battle.pending_action:
                                    if battle.timeout_task:
                                        battle.timeout_task.cancel()
                                    battle.pending_action = None
                                # 다음 턴 처리
                                from mob_setting import MobSettingView
                                view = MobSettingView(battle)
                                await view.process_turn()
                                return
                            else:
                                await message.channel.send(f"❌ {battle.mob_name}의 턴은 Admin만 넘길 수 있습니다.")
                                return
                        
                        # 플레이어 턴인 경우
                        else:
                            # 해당 플레이어 찾기
                            current_player = None
                            for player in battle.players:
                                if player.real_name == current_turn:
                                    current_player = player
                                    break
                            
                            if current_player:
                                # 본인이거나 Admin인지 확인
                                can_skip = (
                                    message.author.id == current_player.user.id or
                                    is_admin
                                )
                                
                                if can_skip:
                                    await message.channel.send(f"⏭️ {current_player.real_name}의 턴을 넘겼습니다.")
                                    # 플레이어 턴 완료 처리
                                    current_player.has_acted_this_turn = True
                                    battle.current_turn_index += 1
                                    if battle.pending_action:
                                        if battle.timeout_task:
                                            battle.timeout_task.cancel()
                                        battle.pending_action = None
                                    # 다음 턴 처리
                                    from mob_setting import MobSettingView
                                    view = MobSettingView(battle)
                                    await view.process_turn()
                                    return
                                else:
                                    await message.channel.send(f"❌ {current_turn}의 턴은 본인 또는 Admin만 넘길 수 있습니다.")
                                    return
            except Exception as e:
                logger.error(f"몹 전투 턴넘김 처리 오류: {e}")
        
        # 기존 전투들 처리
        from battle import get_battle_game
        battle_game = get_battle_game()
        await battle_game.handle_turn_skip(message)
        
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        await admin_manager.handle_turn_skip(message)
        
        return
    
    # 기존 명령어들 처리
    if message.content.startswith("!타격"):
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        await admin_manager.handle_target_command(message)
        return
        
    if message.content.startswith("!전투"):
        if message.author.display_name in ["system | 시스템", "system", "시스템"]:
            await handle_multi_battle_command(message)
        else:
            await message.channel.send("!전투 명령어는 Admin만 사용할 수 있습니다.")
 
    
    # 테스트 모드 활성화 체크
    if message.content == "test1234":
        # 블랙잭 참가 대기 중인지 확인
        for channel_id, view in blackjack_join_views.items():
            if channel_id == message.channel.id and not view.is_finished():
                # 권한 확인 (선택사항 - 원하면 주석 처리)
                ALLOWED_USERS = ["1007172975222603798", "YOUR_DISCORD_ID_HERE"]
                if str(message.author.id) in ALLOWED_USERS:
                    # 테스트 모드로 즉시 게임 시작
                    await message.delete()  # 비밀 코드 삭제
                    await start_test_blackjack(view.interaction, message.author)
                    view.stop()  # 참가 대기 중단
                    return
    
    asyncio.create_task(handle_message_safe(message))

# 회복 명령어에서 몹 전투 회복 처리를 위한 함수
async def handle_mob_recovery(player_name: str, dice_value: int):
    """몹 전투에서 플레이어 회복 처리"""
    # 몹 전투 찾기
    for channel_id, battle in bot.mob_battles.items():
        if not battle.is_active:
            continue
            
        # 플레이어 찾기
        for p in battle.players:
            if p.real_name == player_name and battle.pending_action:
                if (battle.pending_action.get("type") == "player_turn" and
                    battle.pending_action.get("player") == p):
                    # MobSetting의 회복 처리 호출
                    from mob_setting import MobSetting, DiceResult
                    mob_setting = MobSetting(bot)
                    result = DiceResult(player_name=player_name, dice_value=dice_value)
                    await mob_setting.process_recovery_dice(battle, result)
                    return

async def handle_multi_battle_command(message: discord.Message):
    """!전투 명령어 처리 - 팀 전투 지원 (Admin 포함)"""
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    
    # 명령어 파싱
    content = message.content[4:].strip()  # "!전투" 제거
    
    # vs로 팀 구분 확인
    if " vs " in content:
        # 팀 전투 처리
        parts = content.split(" vs ")
        if len(parts) != 2:
            await message.channel.send("올바른 형식: !전투 @유저1 @유저2 vs @유저3 @유저4 [몬스터], 체력값들")
            return
        
        # 체력값 파싱을 위해 먼저 콤마 위치 찾기
        full_content = content
        comma_index = full_content.rfind(',')
        
        if comma_index != -1:
            # 체력값 부분 추출
            health_part = full_content[comma_index + 1:].strip()
            # 팀 정의 부분
            team_part = full_content[:comma_index].strip()
            
            # 체력값 파싱
            health_values = []
            if health_part:
                health_parts = health_part.split(',')
                for part in health_parts:
                    try:
                        health = int(part.strip())
                        if health < 1:
                            health = 10
                        health_values.append(health)
                    except ValueError:
                        continue
        else:
            team_part = content
            health_values = []
        
        # 팀 파싱
        team_parts = team_part.split(" vs ")
        team_a_part = team_parts[0].strip()
        team_b_part = team_parts[1].strip()
        
        # 팀 A 멘션 추출
        team_a_mentions = []
        team_a_has_admin = False
        for mention in message.mentions:
            if f"<@{mention.id}>" in team_a_part or f"<@!{mention.id}>" in team_a_part:
                team_a_mentions.append(mention)
        
        # 팀 A에 몬스터/Admin 있는지 확인
        if "몬스터" in team_a_part or "admin" in team_a_part.lower() or "시스템" in team_a_part:
            team_a_has_admin = True
        
        # 팀 B 멘션 추출
        team_b_mentions = []
        team_b_has_admin = False
        for mention in message.mentions:
            if mention not in team_a_mentions:
                if f"<@{mention.id}>" in team_b_part or f"<@!{mention.id}>" in team_b_part:
                    team_b_mentions.append(mention)
        
        # 팀 B에 몬스터/Admin 있는지 확인
        if "몬스터" in team_b_part or "admin" in team_b_part.lower() or "시스템" in team_b_part:
            team_b_has_admin = True
        
        # 최소 인원 확인
        total_users_a = len(team_a_mentions) + (1 if team_a_has_admin else 0)
        total_users_b = len(team_b_mentions) + (1 if team_b_has_admin else 0)
        
        if total_users_a == 0 or total_users_b == 0:
            await message.channel.send("각 팀에 최소 1명씩 있어야 합니다.")
            return
        
        # 체력값이 부족하면 10으로 채우기
        total_users = len(team_a_mentions) + len(team_b_mentions) + (1 if team_a_has_admin else 0) + (1 if team_b_has_admin else 0)
        while len(health_values) < total_users:
            health_values.append(10)
        
        # 팀 전투 시작 (Admin 포함)
        await admin_manager.start_team_battle_with_admin_sync_choice(
            message, team_a_mentions, team_b_mentions, health_values, team_a_has_admin, team_b_has_admin
        )
        
    else:
        # 기존 1대다 전투 처리
        # 멘션과 옵션 파싱
        parts = content.split(',')
        mentions_part = parts[0].strip()
        
        mentions = []
        for mention in message.mentions:
            if mention != message.author:
                mentions.append(mention)
        
        if not mentions:
            await message.channel.send("최소 한 명의 상대를 멘션해주세요.")
            return
        
        # 체력값 파싱 (옵션)
        admin_health = 10
        if len(parts) > 1:
            try:
                admin_health = int(parts[1].strip())
                if admin_health < 1:
                    admin_health = 10
            except ValueError:
                admin_health = 10
        
        # 몬스터 이름 파싱 (옵션)
        monster_name = "시스템"  # 기본값
        if len(parts) > 2:
            monster_name = parts[2].strip()
            if not monster_name:
                monster_name = "시스템"
        
        # 체력 동기화 선택 화면 표시 - 수정된 부분
        from battle_admin import MultiBattleSyncView
        
        view = MultiBattleSyncView(admin_manager, message, mentions, admin_health, monster_name)
        
        embed = discord.Embed(
            title="⚔️ 다중 전투 설정",
            description=f"{monster_name} vs {', '.join([m.display_name for m in mentions])}\n\n"
                        f"체력 동기화 옵션을 선택해주세요.",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="전투 정보",
            value=f"{monster_name}: {admin_health}HP\n"
                f"참가자: {len(mentions)}명",
            inline=False
        )
        
        await message.channel.send(embed=embed, view=view)

async def handle_message_safe(message):
    """안전한 메시지 처리"""
    try:
        await handle_message(message)
    except Exception as e:
        logger.error(f"메시지 처리 중 오류: {e}")

@bot.event
async def on_raw_reaction_add(payload):
    """리액션 추가 이벤트 처리"""
    if payload.user_id == bot.user.id:
        return
    
    asyncio.create_task(handle_reaction_safe(payload))

async def handle_reaction_safe(payload):
    """안전한 리액션 처리"""
    try:
        await handle_reaction(payload)
    except Exception as e:
        logger.error(f"리액션 처리 중 오류: {e}")

# === 스킬 시스템용 이벤트 추가 ===
@bot.event
async def on_disconnect():
    """연결 끊김 시 데이터 저장 (수정된 버전)"""
    logger.warning("봇 연결이 끊어졌습니다. 데이터 저장 중...")
    try:
        # 스킬 시스템 데이터 저장
        if skill_manager._initialized:
            await skill_manager.force_save()
            logger.info("스킬 매니저 데이터 저장 완료")
        
        if skill_effects.is_initialized():
            await skill_effects.clear_cache()
            logger.info("스킬 효과 캐시 정리 완료")
        
        # 몹 전투 데이터 정리
        if hasattr(bot, 'mob_battles') and bot.mob_battles:
            active_battles = len(bot.mob_battles)
            logger.info(f"진행 중인 몹 전투 {active_battles}개를 정리합니다.")
            
            # 각 전투별로 스킬 시스템 정리
            for channel_id, battle in list(bot.mob_battles.items()):
                try:
                    if mob_setting_handler:
                        await mob_setting_handler._deactivate_skill_system(channel_id)
                        logger.info(f"몹 전투 {channel_id} 스킬 시스템 정리 완료")
                except Exception as e:
                    logger.error(f"몹 전투 {channel_id} 정리 오류: {e}")
        
        logger.info("연결 끊김 시 데이터 저장 완료")
        
    except Exception as e:
        logger.error(f"연결 끊김 시 데이터 저장 오류: {e}")

@bot.event
async def on_resumed():
    """연결 재개 이벤트 (수정된 버전)"""
    logger.info("봇 연결이 재개되었습니다.")
    
    # 스킬 시스템 상태 확인 및 복구
    try:
        if skill_manager._initialized:
            # 필요시 백업에서 데이터 복원
            logger.info("스킬 시스템 데이터 확인 중...")
            
            # 간단한 기능 테스트
            test_result = skill_manager.get_channel_state("reconnect_test")
            if test_result:
                logger.info("스킬 시스템 연결 재개 후 정상 작동 확인")
            else:
                logger.warning("스킬 시스템 연결 재개 후 문제 감지")
                
    except Exception as e:
        logger.warning(f"연결 재개 후 스킬 시스템 확인 실패: {e}")

@bot.event
async def on_error(event, *args, **kwargs):
    """오류 이벤트 처리"""
    logger.error(f"봇 오류 발생 - 이벤트: {event}")
    import traceback
    traceback.print_exc()
    
    # 스킬 시스템 관련 오류인 경우 추가 로깅
    if 'skill' in str(event).lower():
        logger.error("스킬 시스템 관련 오류 - 시스템 상태를 확인하세요.")


# === 봇 종료 시 정리 ===
async def cleanup_on_shutdown():
    """봇 종료 시 정리 작업"""
    logger.info("봇 종료 정리 작업 시작...")
    
    try:
        # 스킬 시스템 정리
        await skill_manager.force_save()
        await skill_effects.clear_cache()
        
        # 진행 중인 모든 전투의 스킬 시스템 정리
        if hasattr(bot, 'mob_battles'):
            for channel_id in list(bot.mob_battles.keys()):
                try:
                    global mob_setting_handler
                    if mob_setting_handler:
                        await mob_setting_handler._deactivate_skill_system(channel_id)
                        logger.info(f"전투 {channel_id} 스킬 시스템 정리 완료")
                except Exception as e:
                    logger.error(f"전투 {channel_id} 정리 중 오류: {e}")
        
        logger.info("봇 종료 정리 작업 완료")
        
    except Exception as e:
        logger.error(f"봇 종료 정리 중 오류: {e}")

# === 슬래시 명령어 ===

# === 추가 유틸리티 함수들 ===

async def handle_mob_battle_end(channel_id: int, winner_type: str, winner_name: str):
    """몹 전투 종료 이벤트 처리"""
    try:
        logger.info(f"몹 전투 종료 - 채널: {channel_id}, 승리자: {winner_type}({winner_name})")
        
        # 스킬 시스템 정리
        global mob_setting_handler
        if mob_setting_handler:
            cleaned_skills = await mob_setting_handler._deactivate_skill_system(channel_id)
            
            if cleaned_skills > 0:
                channel = bot.get_channel(channel_id)
                if channel:
                    cleanup_embed = discord.Embed(
                        title="🧹 전투 종료 - 시스템 정리",
                        description=f"전투가 끝나면서 활성화된 스킬 {cleaned_skills}개가 정리되었습니다.",
                        color=discord.Color.green()
                    )
                    await channel.send(embed=cleanup_embed)
        
        # 전투 데이터 정리
        if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
            del bot.mob_battles[channel_id]
        
    except Exception as e:
        logger.error(f"몹 전투 종료 처리 오류: {e}")

# === 디버그 명령어들 ===

@bot.tree.command(name="스킬상태", description="현재 채널의 스킬 시스템 상태를 확인합니다 (Admin 전용)")
async def 스킬상태_command(interaction: discord.Interaction):
    """스킬 시스템 상태 확인"""
    # Admin 체크
    is_admin = (
        str(interaction.user.id) in ["1007172975222603798", "1090546247770832910"] or
        interaction.user.display_name in ["system | 시스템", "system", "시스템"]
    )
    
    if not is_admin:
        await interaction.response.send_message("❌ 이 명령어는 Admin만 사용할 수 있습니다.", ephemeral=True)
        return
    
    try:
        channel_id = str(interaction.channel.id)
        channel_state = skill_manager.get_channel_state(channel_id)
        
        # 전투 상태
        battle_active = channel_state.get("battle_active", False)
        battle_type = channel_state.get("battle_type", "없음")
        mob_name = channel_state.get("mob_name", "없음")
        
        # 활성 스킬들
        active_skills = channel_state["active_skills"]
        
        # 몹 전투 상태
        mob_battle_status = "없음"
        if hasattr(bot, 'mob_battles') and int(channel_id) in bot.mob_battles:
            battle = bot.mob_battles[int(channel_id)]
            mob_battle_status = f"진행중 - {battle.mob_name}" if battle.is_active else f"대기중 - {battle.mob_name}"
        
        status_embed = discord.Embed(
            title="🔍 스킬 시스템 상태",
            color=discord.Color.blue()
        )
        
        status_embed.add_field(
            name="⚔️ 전투 상태",
            value=f"**활성화**: {'✅' if battle_active else '❌'}\n"
                  f"**타입**: {battle_type}\n" 
                  f"**몹 이름**: {mob_name}",
            inline=False
        )
        
        status_embed.add_field(
            name="🎯 몹 전투 상태",
            value=mob_battle_status,
            inline=False
        )
        
        if active_skills:
            skill_list = []
            for skill_name, skill_data in active_skills.items():
                rounds_left = skill_data["rounds_left"]
                user_name = skill_data["user_name"]
                skill_list.append(f"• **{skill_name}** ({user_name}) - {rounds_left}라운드 남음")
            
            status_embed.add_field(
                name=f"✨ 활성 스킬 ({len(active_skills)}개)",
                value="\n".join(skill_list),
                inline=False
            )
        else:
            status_embed.add_field(
                name="✨ 활성 스킬",
                value="활성화된 스킬이 없습니다.",
                inline=False
            )
        
        status_embed.set_footer(text=f"채널 ID: {channel_id}")
        
        await interaction.response.send_message(embed=status_embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"스킬 상태 확인 오류: {e}")
        await interaction.response.send_message(
            f"❌ 스킬 상태 확인 중 오류가 발생했습니다: {str(e)[:100]}",
            ephemeral=True
        )

# main.py의 process_admin_recovery 함수 수정
async def process_admin_recovery(channel: discord.TextChannel, admin_user_id: int, recovery_amount: int):
    """Admin 회복 주사위 결과 처리"""
    try:
        # Admin 사용자 가져오기
        admin_user = channel.guild.get_member(admin_user_id)
        if not admin_user:
            await channel.send("Admin 사용자를 찾을 수 없습니다.")
            return
        
        # Admin이 전투 중인지 확인
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        in_battle = False
        battle = None
        for channel_id, b in admin_manager.active_battles.items():
            if b.admin and b.admin.user.id == admin_user_id:
                in_battle = True
                battle = b
                break

        if in_battle and battle:
            # 전투 중인 경우: 실제 체력과 전투 체력 모두 회복
            
            # 1. 실제 체력 회복 (10 단위)
            current_real_health = battle.admin.real_health
            health_to_recover = 10  # 모든 회복은 10단위
            new_real_health = min(100, current_real_health + health_to_recover)
            actual_health_recovered = new_real_health - current_real_health
            
            # 2. 체력 동기화 여부에 따른 처리
            if battle.health_sync:
                # 체력 동기화가 켜져 있을 때: calculate_battle_health 사용
                from battle_utils import calculate_battle_health
                old_battle_health = calculate_battle_health(current_real_health)
                new_battle_health = calculate_battle_health(new_real_health)
                battle_recovery = new_battle_health - old_battle_health
            else:
                # 체력 동기화가 꺼져 있을 때: 10HP = 1전투체력
                battle_recovery = 1
            
            # 3. 전투 체력 회복 적용
            old_hits_received = battle.admin.hits_received
            battle.admin.hits_received = max(0, battle.admin.hits_received - battle_recovery)
            actual_battle_recovery = old_hits_received - battle.admin.hits_received
            
            # 4. 실제 체력 업데이트
            battle.admin.real_health = new_real_health
            
            # 새 전투 체력 계산 (표시용)
            current_battle_health = battle.admin.max_health - battle.admin.hits_received
            
            if actual_health_recovered <= 0 and actual_battle_recovery <= 0:
                embed = discord.Embed(
                    title="💙 시스템 회복",
                    description=f"주사위 결과: **{recovery_amount}**\n\n이미 체력이 최대입니다!",
                    color=discord.Color.blue()
                )
                await channel.send(embed=embed)
            else:
                # 결과 메시지
                embed = discord.Embed(
                    title="💙 시스템 회복 성공!",
                    description=f"주사위 결과: **{recovery_amount}**",
                    color=discord.Color.blue()
                )
                if actual_health_recovered > 0:
                    embed.add_field(name="실제 체력 회복량", value=f"+{actual_health_recovered} HP", inline=True)
                    embed.add_field(name="현재 실제 체력", value=f"{new_real_health}/100 HP", inline=True)
                if actual_battle_recovery > 0:
                    embed.add_field(name="전투 체력 회복량", value=f"+{actual_battle_recovery} (전투)", inline=True)
                    embed.add_field(name="현재 전투 체력", value=f"{current_battle_health}/{battle.admin.max_health}", inline=True)
                
                await channel.send(embed=embed)
                
                # 전투 상태 업데이트
                battle_embed = admin_manager._create_battle_status_embed(battle)
                await battle.message.edit(embed=battle_embed)
            
            # 전투 턴 처리
            battle_turn_check_result = await check_and_validate_battle_turn(admin_user_id, channel.id)
            if battle_turn_check_result["in_battle"] and battle_turn_check_result["is_user_turn"]:
                embed.add_field(name="⚔️ 전투 효과", value="회복으로 인해 턴을 소모했습니다!", inline=False)
                await auto_skip_turn_after_recovery(admin_user_id, channel.id, "admin", battle.monster_name)
                
        else:
            # 전투 중이 아닌 경우: 일반 회복 (Admin은 항상 100HP)
            embed = discord.Embed(
                title="💙 시스템 회복",
                description=f"주사위 결과: **{recovery_amount}**\n\n전투 중이 아닐 때는 항상 최대 체력입니다!",
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Admin 회복 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        await channel.send("Admin 회복 처리 중 오류가 발생했습니다.")

@bot.tree.command(name="몹세팅", description="자동 전투 몹을 설정합니다 (Admin 전용)")
@app_commands.describe(
    mob_name="몹 이름",
    mob_health="몹 체력 (전투 체력)",
    health_sync="체력 동기화 여부 (True: 실제 체력 = 전투 체력 × 10)",
    ai_personality="AI 성격 (기본: tactical)",
    ai_difficulty="AI 난이도 (기본: normal)",
    enable_skills="스킬 시스템 활성화 여부 (기본: 활성화)"
)
@app_commands.choices(
    ai_personality=[
        app_commands.Choice(name="전술적 (균형잡힌 전투)", value="tactical"),
        app_commands.Choice(name="공격적 (높은 공격 빈도)", value="aggressive"),
        app_commands.Choice(name="방어적 (신중한 행동)", value="defensive"),
        app_commands.Choice(name="광전사 (낮은 HP시 강화)", value="berserker"),
        app_commands.Choice(name="기회주의 (약한 적 우선)", value="opportunist")
    ],
    ai_difficulty=[
        app_commands.Choice(name="쉬움 (느린 반응, 실수 많음)", value="easy"),
        app_commands.Choice(name="보통 (균형잡힌 난이도)", value="normal"),
        app_commands.Choice(name="어려움 (빠른 반응, 최적 선택)", value="hard"),
        app_commands.Choice(name="악몽 (완벽한 AI)", value="nightmare")
    ],
    enable_skills=[
        app_commands.Choice(name="활성화 (Admin이 스킬 사용 가능)", value="yes"),
        app_commands.Choice(name="비활성화 (스킬 없이 전투)", value="no")
    ]
)
@app_commands.guild_only()
async def mob_setting_command(
    interaction: discord.Interaction,
    mob_name: str,
    mob_health: int,
    health_sync: bool,
    ai_personality: str = "tactical",
    ai_difficulty: str = "normal",
    enable_skills: str = "yes"
):
    """몹 세팅 슬래시 명령어 (스킬 시스템 완전 통합)"""
    
    try:
        # === 권한 체크 ===
        AUTHORIZED_USERS = ["1007172975222603798", "1090546247770832910"]
        AUTHORIZED_NICKNAME = "system | 시스템"
        
        is_authorized = (
            str(interaction.user.id) in AUTHORIZED_USERS or
            interaction.user.display_name == AUTHORIZED_NICKNAME
        )
        
        if not is_authorized:
            await interaction.response.send_message(
                "❌ 이 명령어는 Admin만 사용할 수 있습니다.", 
                ephemeral=True
            )
            return
        
        # === 입력 값 검증 ===
        if mob_health <= 0:
            await interaction.response.send_message(
                "❌ 체력은 1 이상이어야 합니다.", 
                ephemeral=True
            )
            return
            
        if len(mob_name) > 50:
            await interaction.response.send_message(
                "❌ 몹 이름은 50자 이하여야 합니다.", 
                ephemeral=True
            )
            return
        
        # === 응답 지연 처리 ===
        await interaction.response.defer()
        
        # === MobSetting 핸들러 초기화 ===
        global mob_setting_handler
        if not mob_setting_handler:
            from mob_setting import MobSetting
            mob_setting_handler = MobSetting(bot)
        
        # === 몹 전투 생성 ===
        success = await mob_setting_handler.create_mob_battle(
            interaction=interaction,
            mob_name=mob_name,
            mob_health=mob_health,
            health_sync=health_sync,
            ai_personality=ai_personality,
            ai_difficulty=ai_difficulty,
            enable_skills=(enable_skills == "yes")
        )
        
        if success:
            # === 전투 설정 완료 메시지 ===
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
            
            setup_embed = discord.Embed(
                title="✅ 몹 전투 설정 완료!",
                color=discord.Color.green()
            )
            
            setup_embed.add_field(
                name="🎯 몹 정보",
                value=f"**이름**: {mob_name}\n"
                      f"**전투 체력**: {mob_health}\n"
                      f"**실제 체력**: {mob_health * 10 if health_sync else 100}\n"
                      f"**체력 동기화**: {'✅ 활성화' if health_sync else '❌ 비활성화'}",
                inline=False
            )
            
            setup_embed.add_field(
                name="🤖 AI 설정",
                value=f"**성격**: {personality_names[ai_personality]}\n"
                      f"**난이도**: {difficulty_names[ai_difficulty]}",
                inline=True
            )
            
            setup_embed.add_field(
                name="⚔️ 스킬 시스템",
                value=f"{'✅ 활성화' if enable_skills == 'yes' else '❌ 비활성화'}",
                inline=True
            )
            
            if enable_skills == "yes":
                setup_embed.add_field(
                    name="💡 스킬 사용법",
                    value="Admin은 전투 중 `/스킬 영웅:(영웅명) 라운드:(지속시간)` 명령어를 사용할 수 있습니다!",
                    inline=False
                )
            
            setup_embed.set_footer(text="참가자들이 참가 버튼을 눌러 전투를 시작하세요!")
            
            await interaction.followup.send(embed=setup_embed)
            
            logger.info(
                f"몹세팅 명령어 성공 - 사용자: {interaction.user.display_name}, "
                f"몹: {mob_name}, 체력: {mob_health}, 스킬: {enable_skills}"
            )
            
        else:
            await interaction.followup.send(
                "❌ 몹 전투 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
            )
            
    except Exception as e:
        logger.error(f"몹세팅 명령어 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ 몹 전투 설정 중 오류가 발생했습니다: {str(e)[:100]}"
                )
            else:
                await interaction.response.send_message(
                    f"❌ 몹 전투 설정 중 오류가 발생했습니다: {str(e)[:100]}",
                    ephemeral=True
                )
        except:
            pass

@bot.tree.command(name="sync", description="명령어 동기화 (Admin 전용)")
async def sync_command(interaction: discord.Interaction):
    if str(interaction.user.id) == "1090546247770832910":
        try:
            synced = await bot.tree.sync()
            await interaction.response.send_message(f"✅ {len(synced)}개의 명령어가 동기화되었습니다!")
            
            # 로드된 명령어 목록 확인
            commands = [cmd.name for cmd in bot.tree.get_commands()]
            await interaction.followup.send(f"로드된 명령어: {', '.join(commands)}")
        except Exception as e:
            await interaction.response.send_message(f"❌ 동기화 실패: {e}")
    else:
        await interaction.response.send_message("권한이 없습니다.", ephemeral=True)



@bot.tree.command(name="debug_skill", description="스킬 시스템 디버그")
async def debug_skill(interaction: discord.Interaction):
    if str(interaction.user.id) == "1090546247770832910":
        # Cog 상태 확인
        cog_info = "SkillCog 로드됨" if "SkillCog" in bot.cogs else "SkillCog 없음"
        
        # Cog 명령어 확인
        cog_commands = []
        if "SkillCog" in bot.cogs:
            skill_cog = bot.get_cog("SkillCog")
            
            # 여러 방법으로 명령어 확인
            try:
                # 방법 1: walk_app_commands
                for cmd in skill_cog.walk_app_commands():
                    cog_commands.append(f"/{cmd.name} (walk)")
            except:
                pass
                
            try:
                # 방법 2: __cog_app_commands__
                if hasattr(skill_cog, '__cog_app_commands__'):
                    for cmd in skill_cog.__cog_app_commands__:
                        cog_commands.append(f"/{cmd.name} (cog_app)")
            except:
                pass
                
            # 방법 3: 직접 속성 확인
            for attr_name in dir(skill_cog):
                attr = getattr(skill_cog, attr_name)
                if hasattr(attr, '_callback'):  # 명령어인지 확인
                    cog_commands.append(f"/{attr_name} (attr)")
        
        # 전체 명령어 확인
        all_commands = [f"/{cmd.name}" for cmd in bot.tree.get_commands()]
        
        await interaction.response.send_message(
            f"**디버그 정보:**\n"
            f"Cog 상태: {cog_info}\n"
            f"Cog 명령어: {', '.join(cog_commands) if cog_commands else '없음'}\n"
            f"전체 명령어 수: {len(all_commands)}\n"
            f"전체 명령어: {', '.join(all_commands[:10])}...\n"  # 처음 10개만
            f"스킬 포함 여부: {'예' if any('스킬' in cmd for cmd in all_commands) else '아니오'}"
        )
# ===== 추가 명령어: AI 테스트 =====
@bot.tree.command(name="몹ai테스트", description="몹 AI 및 전체 시스템을 종합적으로 테스트합니다 (Admin 전용)")
@app_commands.describe(
    scenario="테스트 시나리오 선택",
    detailed="상세 결과 표시 여부",
    specific_suite="특정 테스트 스위트만 실행"
)
@app_commands.choices(
    scenario=[
        app_commands.Choice(name="전체 테스트 (모든 기능)", value="all"),
        app_commands.Choice(name="빠른 테스트 (핵심 기능)", value="quick"),
        app_commands.Choice(name="AI 시스템만", value="ai_only"),
        app_commands.Choice(name="전투 시스템만", value="battle_only"),
        app_commands.Choice(name="회복 시스템만", value="recovery_only"),
        app_commands.Choice(name="체력 동기화만", value="sync_only"),
        app_commands.Choice(name="엣지 케이스", value="edge_only"),
        app_commands.Choice(name="스트레스 테스트", value="stress"),
        app_commands.Choice(name="성능 테스트", value="performance"),
        app_commands.Choice(name="모든 조합 테스트", value="combination")
    ],
    specific_suite=[
        app_commands.Choice(name="AI 시스템", value="AI 시스템"),
        app_commands.Choice(name="전투 시스템", value="전투 시스템"),
        app_commands.Choice(name="회복 시스템", value="회복 시스템"),
        app_commands.Choice(name="대사 시스템", value="대사 시스템"),
        app_commands.Choice(name="체력 동기화", value="체력 동기화"),
        app_commands.Choice(name="엣지 케이스", value="엣지 케이스"),
        app_commands.Choice(name="스트레스 테스트", value="스트레스 테스트"),
        app_commands.Choice(name="성능 테스트", value="성능 테스트"),
        app_commands.Choice(name="조합 테스트", value="조합 테스트")
    ]
)
@app_commands.guild_only()
async def mob_ai_test_command(
    interaction: discord.Interaction,
    scenario: str = "all",
    detailed: bool = False,
    specific_suite: Optional[str] = None
):
    """몹 시스템 종합 테스트 명령어"""
    # 권한 체크
    AUTHORIZED_USERS = ["1007172975222603798", "1090546247770832910"]
    AUTHORIZED_NICKNAME = "system | 시스템"
    
    is_authorized = (
        str(interaction.user.id) in AUTHORIZED_USERS or
        interaction.user.display_name == AUTHORIZED_NICKNAME
    )
    
    if not is_authorized:
        await interaction.response.send_message(
            "❌ 이 명령어는 Admin만 사용할 수 있습니다.", 
            ephemeral=True
        )
        return
    
    # mob_test 모듈 import
    try:
        from mob_test import handle_mob_test_command
    except ImportError:
        await interaction.response.send_message(
            "❌ 테스트 모듈을 찾을 수 없습니다. mob_test.py 파일이 있는지 확인해주세요.",
            ephemeral=True
        )
        return
    
    # 시나리오 매핑
    scenario_mapping = {
        "ai_only": None,  # specific_suite로 처리
        "battle_only": None,
        "recovery_only": None,
        "sync_only": None,
        "edge_only": None
    }
    
    # 특정 시스템만 테스트하는 경우
    if scenario in ["ai_only", "battle_only", "recovery_only", "sync_only", "edge_only"]:
        suite_mapping = {
            "ai_only": "AI 시스템",
            "battle_only": "전투 시스템",
            "recovery_only": "회복 시스템",
            "sync_only": "체력 동기화",
            "edge_only": "엣지 케이스"
        }
        specific_suite = suite_mapping.get(scenario)
        scenario = "specific"  # handle_mob_test_command에서 처리
    
    # 테스트 실행
    await handle_mob_test_command(
        interaction=interaction,
        scenario=scenario,
        detailed=detailed,
        specific_suite=specific_suite
    )

@bot.tree.command(name="아이템", description="러너의 아이템, 복장, 신체현황, 타락도를 확인합니다.")
async def 아이템_command(interaction: discord.Interaction):
    """아이템 확인 명령어"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        user_id = str(interaction.user.id)
        
        cache_key = f"user_inventory_display:{user_id}"
        cached_display = await cache_manager.get(cache_key)
        
        if cached_display:
            await interaction.followup.send(embed=discord.Embed.from_dict(cached_display))
            return
        
        user_inventory = await get_user_inventory(user_id)

        if not user_inventory:
            await interaction.followup.send("러너 정보를 찾을 수 없습니다.")
            return

        coins = user_inventory.get("coins", 0)
        health = user_inventory.get("health", "알 수 없음")
        items = ", ".join(user_inventory.get("items", [])) or "없음"
        outfits = ", ".join(user_inventory.get("outfits", [])) or "없음"
        physical_status = ", ".join(user_inventory.get("physical_status", [])) or "없음"
        corruption = user_inventory.get("corruption", 0)

        embed = discord.Embed(
            title=f"{interaction.user.display_name}님의 인벤토리",
            color=discord.Color.blue()
        )
        embed.add_field(name="💰 코인", value=str(coins), inline=True)
        embed.add_field(name="❤️ 체력", value=health, inline=True)
        embed.add_field(name="😈 타락도", value=str(corruption), inline=True)
        embed.add_field(name="🎒 아이템", value=items[:1024], inline=False)
        embed.add_field(name="👕 복장", value=outfits[:1024], inline=False)
        embed.add_field(name="🏥 신체현황", value=physical_status[:1024], inline=False)

        await cache_manager.set(cache_key, embed.to_dict(), ex=300)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"아이템 명령어 처리 실패: {e}")
        await interaction.followup.send("명령어 처리 중 오류가 발생했습니다.")

@bot.tree.command(name="전투", description="⚔️ 다른 플레이어와 전투를 시작합니다")
@app_commands.describe(상대="전투할 상대방을 선택하세요")
async def 전투_command(interaction: discord.Interaction, 상대: discord.Member):
    """전투 게임"""
    battle_game = get_battle_game()
    
    # Admin 체크
    is_admin = interaction.user.display_name in ["system | 시스템", "system", "시스템"]
    
    if is_admin:
        # Admin은 battle_admin 사용
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        await admin_manager.start_battle(interaction, 상대)
    else:
        # 일반 유저는 기존 battle 사용
        await battle_game.start_battle(interaction, 상대)

@bot.tree.command(name="지급", description="특정 러너 또는 전체에게 아이템, 코인, 복장, 신체현황, 타락도를 지급합니다.")
async def 지급_command(interaction: discord.Interaction, 아이템: str, 유형: str, 대상: discord.Member = None):
    """지급 명령어"""
    await interaction.response.defer(thinking=True)
    
    try:
        success = await bot_manager.inventory_manager.process_give_command(
            interaction, 아이템, 유형, 대상
        )
        
        if not success:
            logger.warning(f"지급 실패 - 사용자: {interaction.user.id}, 아이템: {아이템}, 유형: {유형}")
            
    except Exception as e:
        logger.error(f"지급 명령어 처리 실패: {e}")
        await interaction.followup.send("명령어 처리 중 오류가 발생했습니다.", ephemeral=True)

@지급_command.autocomplete("유형")
async def 지급_유형_autocomplete(interaction: discord.Interaction, current: str):
    """지급 유형 자동완성"""
    options = ["코인", "아이템", "복장", "신체현황", "타락도"]
    return [
        app_commands.Choice(name=opt, value=opt)
        for opt in options if current.lower() in opt.lower()
    ][:25]

@bot.tree.command(name="거래", description="코인, 아이템, 복장을 다른 유저 또는 Admin에게 거래합니다.")
async def 거래_command(interaction: discord.Interaction, 유형: str, 이름: str, 대상: discord.Member):
    """거래 명령어"""
    await interaction.response.defer()
    
    try:
        success = await bot_manager.inventory_manager.process_trade_command(
            interaction, 유형, 이름, 대상
        )
        
        if not success:
            logger.warning(f"거래 실패 - 사용자: {interaction.user.id}, 유형: {유형}, 이름: {이름}")
            
    except Exception as e:
        logger.error(f"거래 명령어 처리 실패: {e}")
        await interaction.followup.send("명령어 처리 중 오류가 발생했습니다.", ephemeral=True)

@거래_command.autocomplete("유형")
async def 거래_유형_autocomplete(interaction: discord.Interaction, current: str):
    """거래 유형 자동완성"""
    options = ["돈", "아이템", "복장"]
    return [
        app_commands.Choice(name=opt, value=opt) 
        for opt in options if current in opt
    ][:25]

@거래_command.autocomplete("이름")
async def 거래_이름_autocomplete(interaction: discord.Interaction, current: str):
    """거래 이름 자동완성"""
    user_id = str(interaction.user.id)
    유형 = interaction.namespace.__dict__.get('유형')
    
    return await create_item_autocomplete_choices(user_id, 유형, current)

@bot.tree.command(name="회수", description="특정 러너의 아이템, 복장, 신체현황, 타락도를 회수합니다.")
async def 회수_command(interaction: discord.Interaction, 대상: discord.Member, 아이템: str):
    """회수 명령어"""
    _, can_revoke = await get_user_permissions(str(interaction.user.id))
    if not can_revoke:
        await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        target_id = str(대상.id)
        target_inventory = await bot_manager.inventory_manager.get_cached_inventory(target_id)
        
        if not target_inventory:
            await interaction.followup.send(f"{대상.display_name}님의 인벤토리를 찾을 수 없습니다.", ephemeral=True)
            return
        
        item_type = None
        if 아이템 in target_inventory.get("items", []):
            item_type = "아이템"
        elif 아이템 in target_inventory.get("outfits", []):
            item_type = "복장"
        elif 아이템 in target_inventory.get("physical_status", []):
            item_type = "신체현황"
        elif 아이템.startswith("타락도:"):
            item_type = "타락도"
            아이템 = 아이템.split(":")[1] if ":" in 아이템 else 아이템
        else:
            item_type = "아이템"
        
        success = await bot_manager.inventory_manager.batch_revoke_items(target_id, [아이템], item_type)
        
        if not success:
            await interaction.followup.send(f"{대상.display_name}님은 '{아이템}'을 보유하고 있지 않습니다.", ephemeral=True)
            return
        
        await interaction.followup.send(f"{대상.display_name}의 {item_type} '{아이템}'을 회수했습니다.")
        
    except Exception as e:
        logger.error(f"회수 명령어 처리 실패: {e}")
        await interaction.followup.send("명령어 처리 중 오류가 발생했습니다.", ephemeral=True)

@회수_command.autocomplete("아이템")
async def 회수_아이템_autocomplete(interaction: discord.Interaction, current: str):
    """회수 아이템 자동완성"""
    namespace = interaction.namespace
    if not hasattr(namespace, '대상') or not namespace.대상:
        return []
        
    target_id = str(namespace.대상.id)
    return await create_revoke_autocomplete_choices(target_id, current)

@bot.tree.command(name="캐시_재갱신", description="캐싱된 데이터를 삭제하고 재갱신합니다.")
async def 캐시_재갱신_command(interaction: discord.Interaction):
    """캐시 재갱신 명령어"""
    can_give, _ = await get_user_permissions(str(interaction.user.id))
    if not can_give:
        await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        await cache_daily_metadata()
        await interaction.followup.send("캐시가 성공적으로 재갱신되었습니다.")
        
    except Exception as e:
        logger.error(f"캐시 재갱신 실패: {e}")
        await interaction.followup.send("캐시 재갱신 중 오류가 발생했습니다.")

# Admin 전용 명령어 체크 함수 추가
def is_admin():
    """Admin 권한 체크 데코레이터"""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Admin ID 리스트 (필요시 추가)
        ADMIN_IDS = [1007172975222603798, 1090546247770832910]  # 실제 Admin Discord ID
        
        # ID로 체크하거나 닉네임으로 체크
        return (interaction.user.id in ADMIN_IDS or 
                interaction.user.display_name in ["system | 시스템", "system", "시스템"])
    
    return app_commands.check(predicate)

# 타격 명령어 수정
@bot.tree.command(name="타격", description="⚔️ Admin 전용 - 특정 대상에게 집중공격을 합니다")
@app_commands.guild_only()  # 서버에서만 사용 가능
@is_admin()  # Admin만 볼 수 있음
@app_commands.describe(
    대상="집중공격할 대상",
    횟수="공격 횟수 (1-10)",
    회피방식="각각 회피 or 한번에 결정",
    추가공격="집중공격 후 전체 공격 여부"
)
@app_commands.choices(
    회피방식=[
        app_commands.Choice(name="각각 회피 (n번 주사위)", value="each"),
        app_commands.Choice(name="한번에 결정 (1번 주사위)", value="once")
    ],
    추가공격=[
        app_commands.Choice(name="추가 전체 공격", value="yes"),
        app_commands.Choice(name="턴 종료", value="no")
    ]
)
async def 타격_command(interaction: discord.Interaction, 
                    대상: discord.Member,
                    횟수: int,
                    회피방식: str = "each",
                    추가공격: str = "no"):
    """Admin 집중공격 명령어"""
    
    # 전투 중인지 확인
    channel_id = interaction.channel_id
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    
    if channel_id not in admin_manager.active_battles:
        await interaction.response.send_message("진행 중인 전투가 없습니다.", ephemeral=True)
        return
    
    battle = admin_manager.active_battles[channel_id]
    
    # Admin 턴인지 확인 (턴 체크 제거하여 언제든 사용 가능하게)
    # if battle.turn_phase != TurnPhase.ADMIN_ATTACK:
    #     await interaction.response.send_message("Admin의 공격 턴이 아닙니다.", ephemeral=True)
    #     return
    
    # 대상이 전투 참여자인지 확인
    target_player = None
    for player in battle.users:
        if player.user.id == 대상.id and not player.is_eliminated:
            target_player = player
            break
    
    if not target_player:
        await interaction.response.send_message("유효한 대상이 아닙니다.", ephemeral=True)
        return
    
    # 횟수 유효성 검사
    remaining_health = target_player.max_health - target_player.hits_received
    if 횟수 < 1 or 횟수 > min(10, remaining_health):
        await interaction.response.send_message(
            f"공격 횟수는 1 ~ {min(10, remaining_health)} 사이여야 합니다.", 
            ephemeral=True
        )
        return
    
    await interaction.response.defer()
    
    # 집중공격 정보 저장
    battle.focused_attack = {
        "target": target_player.user.id,
        "total_attacks": 횟수,
        "current_attack": 1,
        "defense_mode": 회피방식,
        "add_normal_attack": 추가공격 == "yes",
        "results": []
    }
    
    # 집중공격 시작 메시지
    defense_text = "각각 회피해야 합니다" if 회피방식 == "each" else "한 번의 주사위로 모든 공격이 결정됩니다"
    
    embed = discord.Embed(
        title="💥 집중공격 시작!",
        description=f"{battle.monster_name}이(가) {target_player.real_name}에게 **{횟수}회** 집중공격을 시작합니다!\n\n"
                   f"**회피 방식**: {defense_text}",
        color=discord.Color.red()
    )
    
    await interaction.followup.send(embed=embed)
    
    # 회피 방식에 따른 처리
    if 회피방식 == "once":
        # 한 번에 결정
        await interaction.followup.send(
            f"🎯 **한 번의 대결**\n"
            f"🗡️ {battle.monster_name}님, 공격 주사위를 굴려주세요!\n"
            f"🛡️ {target_player.real_name}님, 회피 주사위를 굴려주세요!"
        )
        
        battle.pending_dice = {
            "phase": "focused_single",
            "waiting_for": [battle.admin.user.id, target_player.user.id],
            "results": {}
        }
    else:
        # 각각 회피
        await admin_manager._start_focused_attack_round(channel_id)


@bot.tree.command(name="회복", description="회복 아이템을 사용하여 체력을 회복합니다. (Admin은 주사위로 회복)")
@app_commands.describe(아이템="[일반 유저] 사용할 회복 아이템 선택")
async def 회복_command(interaction: discord.Interaction, 아이템: Optional[str] = None):
    """회복 아이템 사용 (전투 중 사용 시 턴 소모)"""
    await interaction.response.defer()
    
    try:
        user_id = str(interaction.user.id)
        channel_id = interaction.channel_id
        
        # Admin 체크
        is_admin = interaction.user.display_name in ["system | 시스템", "system", "시스템"]
        
        if is_admin:
            # Admin 회복 - 주사위 굴리기 안내
            embed = discord.Embed(
                title="💙 시스템 회복",
                description="회복량을 결정하기 위해 `/주사위`를 굴려주세요!\n\n"
                           "주사위 결과값만큼 체력이 회복됩니다.",
                color=discord.Color.blue()
            )
            
            await interaction.followup.send(embed=embed)
            
            # Admin 회복 대기 상태 저장
            if not hasattr(회복_command, 'pending_admin_recovery'):
                회복_command.pending_admin_recovery = {}
            
            회복_command.pending_admin_recovery[channel_id] = {
                "user_id": interaction.user.id,
                "timestamp": datetime.now()
            }
            
            # 30초 후 자동 취소
            await asyncio.sleep(30)
            if channel_id in 회복_command.pending_admin_recovery:
                del 회복_command.pending_admin_recovery[channel_id]
            
            return
        
        # 일반 유저 회복 아이템 로직
        if not 아이템:
            await interaction.followup.send("사용할 회복 아이템을 선택해주세요.")
            return
        
        # 사용자 인벤토리 가져오기
        from utility import get_user_inventory, update_user_inventory
        user_data = await get_user_inventory(user_id)
        
        if not user_data:
            await interaction.followup.send("사용자 정보를 찾을 수 없습니다.")
            return
        
        # 회복 아이템 확인
        try:
            from battle_utils import extract_recovery_items
            recovery_items = extract_recovery_items(user_data.get("items", []))
        except Exception as e:
            logger.error(f"회복 아이템 추출 실패: {e}")
            await interaction.followup.send("아이템 정보를 처리하는 중 오류가 발생했습니다.")
            return
        
        # 선택한 아이템 찾기
        selected_item = None
        for item in recovery_items:
            if item['full_name'] == 아이템:
                selected_item = item
                break
        
        if not selected_item:
            await interaction.followup.send("해당 회복 아이템을 보유하고 있지 않습니다.")
            return
        
        # 전투 중인지 확인 (턴 체크)
        battle_turn_check_result = await check_and_validate_battle_turn(interaction.user.id, channel_id)
        is_in_battle = battle_turn_check_result["in_battle"]
        is_user_turn = battle_turn_check_result["is_user_turn"]
        battle_type = battle_turn_check_result["battle_type"]
        
        # 전투 중이지만 본인 턴이 아닌 경우
        if is_in_battle and not is_user_turn:
            await interaction.followup.send("⚔️ 전투 중이지만 현재 당신의 턴이 아닙니다!")
            return
        
        # 현재 체력 추출
        try:
            from battle_utils import extract_health_from_nickname, update_nickname_health
            current_health = extract_health_from_nickname(interaction.user.display_name)
            if current_health is None:
                current_health = 100  # 기본값
        except Exception as e:
            logger.error(f"체력 추출 실패: {e}")
            current_health = 100  # 기본값으로 설정
        
        # 새 체력 계산 (최대 100)
        new_health = min(100, current_health + selected_item['value'])
        health_recovered = new_health - current_health
        
        if health_recovered <= 0:
            await interaction.followup.send("이미 체력이 최대입니다!")
            return
        
        # 닉네임 업데이트
        try:
            new_nickname = update_nickname_health(interaction.user.display_name, new_health)
            await interaction.user.edit(nick=new_nickname)
        except discord.Forbidden:
            await interaction.followup.send("닉네임 변경 권한이 없습니다.")
            return
        except Exception as e:
            logger.error(f"닉네임 업데이트 실패: {e}")
            await interaction.followup.send("닉네임 업데이트 중 오류가 발생했습니다.")
            return
        
        # 아이템 제거
        try:
            user_data["items"].remove(selected_item['full_name'])
            await update_user_inventory(
                user_id,
                coins=user_data.get("coins"),
                items=user_data.get("items"),
                outfits=user_data.get("outfits"),
                physical_status=user_data.get("physical_status"),
                corruption=user_data.get("corruption"),
                health=str(new_health)
            )
        except Exception as e:
            logger.error(f"인벤토리 업데이트 실패: {e}")
            # 닉네임은 이미 변경되었으므로 되돌리기 시도
            try:
                old_nickname = update_nickname_health(interaction.user.display_name, current_health)
                await interaction.user.edit(nick=old_nickname)
            except:
                pass  # 되돌리기 실패해도 무시
            await interaction.followup.send("아이템 제거 중 오류가 발생했습니다.")
            return
        
        # 전투 중인 경우 체력 업데이트 알림
        try:
            from battle import get_battle_game
            battle_game = get_battle_game()
            await battle_game.handle_recovery_update(int(user_id), current_health, new_health)

            # Admin 전투도 확인
            from battle_admin import get_admin_battle_manager
            admin_manager = get_admin_battle_manager()
            await admin_manager.handle_recovery_update(int(user_id), current_health, new_health)
        except Exception as e:
            logger.error(f"전투 체력 업데이트 실패: {e}")
            # 전투 업데이트 실패해도 회복은 성공으로 처리
        
        # 결과 메시지
        embed = discord.Embed(
            title="💚 체력 회복",
            description=f"{selected_item['name']}을(를) 사용했습니다!",
            color=discord.Color.green()
        )
        embed.add_field(name="회복량", value=f"+{health_recovered} HP", inline=True)
        embed.add_field(name="현재 체력", value=f"{new_health}/100 HP", inline=True)
        
        # 전투 중인 경우 턴 소모 메시지 추가
        if is_in_battle and is_user_turn:
            embed.add_field(name="⚔️ 전투 효과", value="회복으로 인해 턴을 소모했습니다!", inline=False)
        
        await interaction.followup.send(embed=embed)
        
        # 전투 중이고 본인 턴인 경우 자동 턴 넘김 처리
        if is_in_battle and is_user_turn:
            await auto_skip_turn_after_recovery(interaction.user.id, channel_id, battle_type, interaction.user.display_name)
        
    except Exception as e:
        logger.error(f"회복 명령어 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send("회복 처리 중 오류가 발생했습니다.")
        
@회복_command.autocomplete("아이템")
async def 회복_아이템_autocomplete(interaction: discord.Interaction, current: str):
    """회복 아이템 자동완성"""
    try:
        # Admin 체크
        is_admin = interaction.user.display_name in ["system | 시스템", "system", "시스템"]
        
        if is_admin:
            # Admin은 아이템 선택 불가 안내
            return []  # Admin은 아이템 선택 없음
        
        # 일반 유저는 기존 로직
        user_id = str(interaction.user.id)
        
        from utility import get_user_inventory
        from battle_utils import extract_recovery_items
        
        user_data = await get_user_inventory(user_id)
        if not user_data:
            return []
        
        recovery_items = extract_recovery_items(user_data.get("items", []))
        
        return [
            app_commands.Choice(
                name=f"{item['name']} (+{item['value']} HP)",
                value=item['full_name']
            )
            for item in recovery_items
            if current.lower() in item['name'].lower()
        ][:25]
    except Exception as e:
        logger.error(f"회복 아이템 자동완성 실패: {e}")
        return []

async def handle_mob_surrender(channel_id: int, user_id: int) -> bool:
    """몹 전투 항복 처리 - MobSetting으로 위임"""
    if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
        # MobSetting의 메서드 호출
        from mob_setting import MobSetting
        mob_setting = MobSetting(bot)
        return await mob_setting.handle_mob_surrender(channel_id, user_id)
    return False

@bot.tree.command(name="항복", description="⚔️ 현재 진행 중인 전투에서 항복합니다")
async def 항복_command(interaction: discord.Interaction):
    """전투 항복"""
    channel_id = interaction.channel_id
    user_id = interaction.user.id

    # 몹 전투 확인 추가
    if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
        if await handle_mob_surrender(channel_id, user_id):
            await interaction.response.send_message("항복 처리되었습니다.")
            return

    # 일반 전투 확인
    from battle import get_battle_game
    battle_game = get_battle_game()
    
    if channel_id in battle_game.active_battles:
        battle_data = battle_game.active_battles[channel_id]
        
        # 전투 참가자인지 확인
        if user_id == battle_data["player1"].user.id:
            winner = battle_data["player2"]
            loser = battle_data["player1"]
            await battle_game.handle_surrender(channel_id, winner, loser)
            await interaction.response.send_message(f"🏳️ {loser.real_name}님이 항복했습니다!")
            return
        elif user_id == battle_data["player2"].user.id:
            winner = battle_data["player1"]
            loser = battle_data["player2"]
            await battle_game.handle_surrender(channel_id, winner, loser)
            await interaction.response.send_message(f"🏳️ {loser.real_name}님이 항복했습니다!")
            return
    
    # Admin 전투 확인
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    
    if channel_id in admin_manager.active_battles:
        battle = admin_manager.active_battles[channel_id]
        
        # 참가자인지 확인
        for player in battle.users:
            if user_id == player.user.id:
                await admin_manager.handle_surrender(channel_id, player)
                await interaction.response.send_message(f"🏳️ {player.real_name}님이 항복했습니다!")
                return
        
        # Admin인 경우
        if user_id == battle.admin.user.id:
            await admin_manager.handle_admin_surrender(channel_id)
            await interaction.response.send_message(f"🏳️ {battle.monster_name}이(가) 항복했습니다!")
            return
    
    await interaction.response.send_message("진행 중인 전투가 없습니다.", ephemeral=True)

# === 게임 명령어 ===

class GameSelectView(discord.ui.View):
    """게임 선택 뷰"""
    def __init__(self):
        super().__init__(timeout=30)
        self.game_type = None
    
    @discord.ui.button(label="블랙잭", style=discord.ButtonStyle.primary, emoji="🎰")
    async def blackjack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game_type = "blackjack"
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="조커뽑기", style=discord.ButtonStyle.primary, emoji="🃏")
    async def joker_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game_type = "joker"
        self.stop()
        await interaction.response.defer()

@bot.tree.command(name="게임시작", description="미니게임을 시작합니다.")
@app_commands.describe(게임종류="플레이할 게임을 선택하세요")
@app_commands.choices(게임종류=[
    app_commands.Choice(name="블랙잭", value="blackjack"),
    app_commands.Choice(name="조커뽑기", value="joker"),
    app_commands.Choice(name="주사위포커", value="dice_poker")
])
async def 게임시작_command(interaction: discord.Interaction, 게임종류: str):
    """게임 시작 명령어"""
    
    if 게임종류 == "blackjack":
        from blackjack import BlackjackJoinView
        
        MAX_BET = 100
        
        embed = discord.Embed(
            title="🎰 블랙잭 게임",
            description=f"30초 동안 참가 신청을 받습니다!\n베팅 한도: 1 ~ {MAX_BET:,}💰",
            color=discord.Color.green()
        )
        
        view = BlackjackJoinView(MAX_BET)
        view.interaction = interaction  # interaction 저장
        blackjack_join_views[interaction.channel_id] = view  # 전역 딕셔너리에 저장
        
        await interaction.response.send_message(embed=embed, view=view)
        
        # 30초 대기
        await asyncio.sleep(30)
        
        # 뷰가 여전히 활성 상태인지 확인 (테스트 모드로 전환되지 않았는지)
        if interaction.channel_id in blackjack_join_views:
            del blackjack_join_views[interaction.channel_id]
            
            if len(view.participants) < 1:
                embed = discord.Embed(
                    title="게임 취소",
                    description="참가자가 없습니다.",
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=embed, view=None)
                return
            
            # 일반 게임 진행 (기존 코드)
            players = []
            bet_amounts = {}
            
            for user_id, bet_amount in view.participants.items():
                member = interaction.guild.get_member(user_id)
                if member:
                    players.append(member)
                    bet_amounts[user_id] = bet_amount
            
            start_embed = discord.Embed(
                title="🎯 블랙잭 게임 시작!",
                description=f"참가자: {len(players)}명\n카드를 분배하고 있습니다...",
                color=discord.Color.blue()
            )
            await interaction.edit_original_response(embed=start_embed, view=None)
            
            game = BlackjackGame(interaction, players, bet_amounts, bot)
            active_blackjack_games[interaction.channel_id] = game
            
            try:
                await game.start_game()
            finally:
                if interaction.channel_id in active_blackjack_games:
                    del active_blackjack_games[interaction.channel_id]

    elif 게임종류 == "dice_poker":
        from dice_poker import DicePokerGame, DicePokerJoinView
        
        # 최대 베팅 금액 설정
        MAX_BET = 100000
        
        embed = discord.Embed(
            title="🎲 주사위 포커",
            description=f"30초 동안 참가 신청을 받습니다!\n"
                       f"최소 2명, 최대 10명 참가 가능\n"
                       f"베팅 한도: 1 ~ {MAX_BET:,}💰",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="📖 게임 설명",
            value="• 주사위 5개로 족보를 만드는 게임\n"
                  "• 최대 2번까지 원하는 주사위 리롤 가능\n"
                  "• 첫 주사위 후, 최종 리롤 후 베팅\n"
                  "• Check, Call, Raise, Fold 가능",
            inline=False
        )
        
        view = DicePokerJoinView(MAX_BET)
        await interaction.response.send_message(embed=embed, view=view)
        
        # 30초 대기
        await asyncio.sleep(30)
        
        if len(view.participants) < 2:
            embed = discord.Embed(
                title="게임 취소",
                description="참가자가 부족합니다. (최소 2명)",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return
        
        # 참가자 목록 생성
        players = []
        bet_amounts = {}
        
        for user_id, bet_amount in view.participants.items():
            member = interaction.guild.get_member(user_id)
            if member:
                players.append(member)
                bet_amounts[user_id] = bet_amount
        
        # 수정: 빈 메시지 대신 게임 시작 메시지 표시
        await interaction.edit_original_response(
            content="🎲 주사위 포커 게임을 시작합니다...", 
            embed=None, 
            view=None
        )
        
        # 주사위 포커 게임 시작
        game = DicePokerGame(interaction, players, bet_amounts, bot)
        active_dice_poker_games[interaction.channel_id] = game  # 추가

        try:
            await game.start_game()
        finally:
            # 게임 종료 후 제거
            if interaction.channel_id in active_dice_poker_games:
                del active_dice_poker_games[interaction.channel_id]  # 추가

@bot.tree.command(name="내카드", description="현재 게임에서 내 카드를 확인합니다.")
@app_commands.describe(shuffle='카드 순서를 섞을지 여부 (조커 게임만 적용)')
async def 내카드_command(interaction: discord.Interaction, shuffle: Optional[bool] = False):
    """카드 확인 명령어"""
    await joker_game.show_cards(interaction, shuffle)

# 조커 게임 명령어들
@bot.tree.command(name="카드뽑기", description="다른 플레이어의 카드를 뽑습니다. (조커 게임)")
async def 카드뽑기_command(interaction: discord.Interaction, 참여유저: str, 뽑을_카드_번호: int):
    """조커 게임 카드 뽑기"""
    await joker_game.draw_card(interaction, 참여유저, 뽑을_카드_번호)

@카드뽑기_command.autocomplete('참여유저')
async def player_autocomplete(interaction: discord.Interaction, current: str):
    return await joker_game.player_autocomplete(interaction, current)

@카드뽑기_command.autocomplete('뽑을_카드_번호')
async def card_number_autocomplete(interaction: discord.Interaction, current: str):
    return await joker_game.card_number_autocomplete(interaction, current)

@bot.tree.command(name="게임상태", description="현재 게임 상태를 확인합니다.")
async def 게임상태_command(interaction: discord.Interaction):
    """게임 상태 확인"""
    channel_id = interaction.channel_id
    
    # 조커 게임 확인
    if channel_id in joker_game.games and joker_game.games[channel_id].get('active'):
        await joker_game.show_game_status(interaction)
        return
    
    # 블랙잭 게임 확인
    if channel_id in active_blackjack_games:
        game = active_blackjack_games[channel_id]
        embed = await game.create_game_embed(hide_dealer=True)
        await interaction.response.send_message(embed=embed)
        return
    
    await interaction.response.send_message("진행 중인 게임이 없습니다.")

@bot.tree.command(name="게임종료", description="현재 게임을 강제로 종료합니다.")
async def 게임종료_command(interaction: discord.Interaction):
    """게임 강제 종료"""
    channel_id = interaction.channel_id

    # 몹 전투 종료 추가
    if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
        del bot.mob_battles[channel_id]
        await interaction.response.send_message("몹 전투가 종료되었습니다.")
        return

    # 일반 전투 종료
    from battle import get_battle_game
    battle_game = get_battle_game()
    if channel_id in battle_game.active_battles:
        del battle_game.active_battles[channel_id]
        await interaction.response.send_message("전투가 종료되었습니다.")
        return
    
    # Admin 전투 종료
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    if channel_id in admin_manager.active_battles:
        del admin_manager.active_battles[channel_id]
        await interaction.response.send_message("Admin 전투가 종료되었습니다.")
        return
    
    # 조커 게임 종료
    if channel_id in joker_game.games and joker_game.games[channel_id].get('active'):
        joker_game.games[channel_id]['active'] = False
        await interaction.response.send_message("조커 게임이 종료되었습니다.")
        return
    
    # 블랙잭 게임 종료
    if channel_id in active_blackjack_games:
        del active_blackjack_games[channel_id]
        await interaction.response.send_message("블랙잭 게임이 종료되었습니다.")
        return
    
    # 다이스 포커 게임 종료 (추가)
    if channel_id in active_dice_poker_games:
        game = active_dice_poker_games[channel_id]
        # 타임아웃 태스크 취소
        for task in game.timeout_tasks.values():
            if not task.done():
                task.cancel()
        del active_dice_poker_games[channel_id]
        await interaction.response.send_message("주사위 포커 게임이 종료되었습니다.")
        return
    
    await interaction.response.send_message("진행 중인 게임이 없습니다.")

@bot.tree.command(name="순서변경", description="조커 게임의 턴 순서를 랜덤으로 변경합니다.")
async def 순서변경_command(interaction: discord.Interaction):
    """턴 순서 변경 (조커 게임 전용)"""
    await joker_game.shuffle_turn_order(interaction)

# === 메인 실행 ===

async def main():
    """메인 실행 함수"""
    try:
        logger.info("봇 시작 중...")
        
        async with bot:
            await bot.start(BOT_TOKEN, reconnect=True)
        
    except KeyboardInterrupt:
        logger.info("봇 종료 요청 받음")
    except discord.LoginFailure:
        logger.error("봇 토큰이 유효하지 않습니다")
    except Exception as e:
        logger.error(f"봇 실행 중 오류: {e}")
        traceback.print_exc()
    finally:
        await bot_manager.shutdown()

if __name__ == "__main__":
    # === 스킬 시스템 초기화 스크립트 실행 추가 ===
    try:
        import os
        if not os.path.exists("skills/config/skill_config.json"):
            logger.info("스킬 시스템 초기 설정 파일 생성 중...")
            os.system("python init_skill_system.py")
    except Exception as e:
        logger.error(f"스킬 시스템 초기화 오류: {e}")
    
    # 봇 실행
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("프로그램이 사용자에 의해 종료되었습니다.")
    except Exception as e:
        logger.error(f"프로그램 실행 중 치명적 오류: {e}")
        traceback.print_exc()


