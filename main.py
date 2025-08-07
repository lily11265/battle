# main.py
import asyncio
import logging
import pytz
import traceback
from concurrent.futures import ThreadPoolExecutor
import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import signal
import sys
from typing import Optional
import re
from datetime import datetime, timedelta
from typing import Optional
from battle import get_battle_game
from mob_setting import setup as setup_mob_setting
from mob_setting import MobSetting
from mob_setting import AutoBattle, MobSettingView
from mob_setting import *
from mob_ai import create_mob_ai, AutonomousAIController, AIPersonality

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
from fishing import get_fishing_game
from dalgona import get_dalgona_game, DalgonaShape
from dart import get_dart_game
from mafia import get_mafia_game, MafiaJoinView

# === 스킬 시스템 import ===
from skills.skill_manager import skill_manager
from skills.skill_effects import skill_effects
import battle_admin

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
bot = discord.Client(
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

tree = app_commands.CommandTree(bot)

# 전역 스레드 풀
thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='BotWorker')

# 게임 관리
joker_game = JokerGame()
active_blackjack_games = {}
blackjack_join_views = {}
active_dice_poker_games = {}

# 테스트 블랙잭 시작 함수
async def start_test_blackjack(original_interaction, test_user):
    """테스트 모드로 블랙잭 시작"""
    from blackjack import BlackjackGame
    
    players = [test_user]
    bet_amounts = {test_user.id: 10}
    
    embed = discord.Embed(
        title="🎰 블랙잭 테스트 모드",
        description=f"{test_user.display_name}님의 테스트 게임을 시작합니다!\n\n"
                   "**테스트 기능:**\n"
                   "• 21점 동점 시 플레이어 승리 확인\n"
                   "• 다양한 상황 테스트 가능",
        color=discord.Color.orange()
    )
    
    await original_interaction.edit_original_response(embed=embed, view=None)
    
    game = BlackjackGame(original_interaction, players, bet_amounts, bot)
    game.test_mode = True
    active_blackjack_games[original_interaction.channel_id] = game
    
    try:
        await game.start_game()
    finally:
        if original_interaction.channel_id in active_blackjack_games:
            del active_blackjack_games[original_interaction.channel_id]

# Admin 회복 주사위 결과 처리
async def process_admin_recovery(channel: discord.TextChannel, admin_user_id: int, recovery_amount: int):
    """Admin 회복 주사위 결과 처리"""
    try:
        admin_user = channel.guild.get_member(admin_user_id)
        if not admin_user:
            await channel.send("Admin 사용자를 찾을 수 없습니다.")
            return
        
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
            current_real_health = battle.admin.real_health
            health_to_recover = 10
            new_real_health = min(100, current_real_health + health_to_recover)
            actual_health_recovered = new_real_health - current_real_health
            
            if battle.health_sync:
                from battle_utils import calculate_battle_health
                old_battle_health = calculate_battle_health(current_real_health)
                new_battle_health = calculate_battle_health(new_real_health)
                battle_recovery = new_battle_health - old_battle_health
            else:
                battle_recovery = 1
            
            old_hits_received = battle.admin.hits_received
            battle.admin.hits_received = max(0, battle.admin.hits_received - battle_recovery)
            actual_battle_recovery = old_hits_received - battle.admin.hits_received
            
            battle.admin.real_health = new_real_health
            
            current_battle_health = battle.admin.max_health - battle.admin.hits_received
            
            if actual_health_recovered <= 0 and actual_battle_recovery <= 0:
                embed = discord.Embed(
                    title="💙 시스템 회복",
                    description=f"주사위 결과: **{recovery_amount}**\n\n이미 체력이 최대입니다!",
                    color=discord.Color.blue()
                )
                await channel.send(embed=embed)
            else:
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
                
                battle_embed = admin_manager._create_battle_status_embed(battle)
                await battle.message.edit(embed=battle_embed)
            
            battle_turn_check_result = await check_and_validate_battle_turn(admin_user_id, channel.id)
            if battle_turn_check_result["in_battle"] and battle_turn_check_result["is_user_turn"]:
                embed.add_field(name="⚔️ 전투 효과", value="회복으로 인해 턴을 소모했습니다!", inline=False)
                await auto_skip_turn_after_recovery(admin_user_id, channel.id, "admin", battle.monster_name)
                
        else:
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
        self._initialized = False
        self._scheduler_started = False

    async def initialize(self):
        """봇 초기화"""
        if self._initialized:
            logger.warning("봇이 이미 초기화되어 있습니다. 중복 초기화 스킵.")
            return
            
        try:
            self.bamboo_system = init_bamboo_system(bot)
            self.inventory_manager = get_inventory_manager()
            
            await cache_manager.start_background_cleanup()
            await cache_daily_metadata()
            
            self._setup_scheduler()
            self.gateway_task = asyncio.create_task(self._monitor_gateway())
            
            bot.mob_setting_views = {}
            mob_setting_handler = MobSetting(bot)

            self._initialized = True
            logger.info("봇 초기화 완료")
            
        except Exception as e:
            logger.error(f"봇 초기화 실패: {e}")
            raise

    def _setup_scheduler(self):
        """스케줄러 설정"""
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
        
        self.scheduler.add_job(
            self._safe_cache_daily_metadata, 
            'cron', 
            hour=5, 
            minute=0,
            id='daily_cache',
            replace_existing=True
        )
        
        self.scheduler.add_job(
            self._safe_increment_daily_values, 
            'cron', 
            hour=0, 
            minute=0,
            id='daily_coins',
            replace_existing=True
        )
        
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
        """봇 안전 종료 (스킬 시스템 포함)"""
        logger.info("봇 종료 시작...")
        self._shutdown_event.set()
        
        # 스킬 시스템 정리
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
            shutdown_tasks.append(asyncio.create_task(self._shutdown_scheduler()))
        
        if self.gateway_task and not self.gateway_task.done():
            self.gateway_task.cancel()
            shutdown_tasks.append(self.gateway_task)
        
        if self.bamboo_system:
            shutdown_tasks.append(asyncio.create_task(self._shutdown_bamboo_system()))
        
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=10.0
                )
                logger.info("시스템 컴포넌트 종료 완료")
            except asyncio.TimeoutError:
                logger.warning("일부 종료 작업이 타임아웃되었습니다")
            except Exception as e:
                logger.error(f"시스템 컴포넌트 종료 중 오류: {e}")
        
        try:
            thread_pool.shutdown(wait=False, cancel_futures=True)
            logger.info("스레드 풀 종료 완료")
        except Exception as e:
            logger.error(f"스레드 풀 종료 오류: {e}")
        
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

# === 이벤트 핸들러 ===

@bot.event
async def on_ready():
    """봇 준비 완료 이벤트 (스킬 시스템 통합)"""
    logger.info(f"봇이 준비되었습니다! {bot.user}로 로그인됨")
    bot_manager.reconnect_attempts = 0
    
    try:
        # 명령어 동기화
        synced = await tree.sync()
        logger.info(f"{len(synced)}개의 명령어가 동기화되었습니다")
        
        # 봇 매니저 초기화
        await bot_manager.initialize()
        
        # === 스킬 시스템 초기화 ===
        await skill_manager.initialize()
        logger.info("✅ 스킬 매니저가 초기화되었습니다")
        
        # 스킬 Cog 로딩
        try:
            from skills.skill import SkillCog
            await bot.add_cog(SkillCog(bot))
            logger.info("✅ 스킬 명령어 Cog가 로드되었습니다")
        except Exception as e:
            logger.error(f"스킬 Cog 로딩 실패: {e}")
        
        # 몹 세팅 시스템 초기화
        global mob_setting_handler
        bot.mob_setting_views = {}
        bot.mob_battles = {}
        mob_setting_handler = MobSetting(bot)
        await setup_mob_setting(bot)
        logger.info("몹 세팅 시스템이 초기화되었습니다")
        
        # 스킬 시스템 상태 체크
        await _perform_skill_system_health_check()
        
    except Exception as e:
        logger.error(f"봇 시작 중 오류 발생: {e}")
        traceback.print_exc()

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

@bot.event
async def on_message(message):
    """메시지 이벤트 처리 (스킬 시스템 통합)"""
    if message.author.bot:
        # 다이스 봇 메시지 처리
        if message.author.id == 218010938807287808:  # 다이스 봇 ID
            channel_id = str(message.channel.id)
            
            # 주사위 메시지 파싱
            dice_pattern = r"`([^`]+)`님이.*?주사위를\s*굴\s*려.*?\*\*(\d+)\*\*"
            match = re.search(dice_pattern, message.content)
            
            if match:
                user_name = match.group(1)
                dice_value = int(match.group(2))
                
                # === 스킬 시스템 주사위 처리 ===
                try:
                    # 실제 유저 ID 찾기 (닉네임으로)
                    user_id = None
                    if message.guild:
                        for member in message.guild.members:
                            if user_name in member.display_name:
                                user_id = str(member.id)
                                break
                    
                    if user_id:
                        # 스킬 효과 적용
                        final_value, skill_messages = await skill_effects.process_dice_roll(
                            user_id, dice_value, channel_id
                        )
                        
                        # 스킬 효과 메시지 전송
                        if skill_messages:
                            for skill_message in skill_messages:
                                await message.channel.send(skill_message)
                        
                        # 값이 변경된 경우 알림
                        if final_value != dice_value:
                            value_change_msg = f"🎲 **{user_name}**님의 주사위 결과: {dice_value} → **{final_value}**"
                            await message.channel.send(value_change_msg)
                            
                            # 변경된 값으로 전투 처리
                            dice_value = final_value
                
                except Exception as e:
                    logger.error(f"스킬 주사위 처리 오류: {e}")
            
                # 몹 세팅 시스템 주사위 처리
                if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
                    from mob_setting import MobSetting
                    mob_setting = MobSetting(bot)
                    await mob_setting.process_mob_dice_message(message)

                # Admin 회복 주사위 처리
                if hasattr(회복_command, 'pending_admin_recovery') and channel_id in 회복_command.pending_admin_recovery:
                    recovery_data = 회복_command.pending_admin_recovery[channel_id]
                    
                    if (datetime.now() - recovery_data["timestamp"]).total_seconds() < 30:
                        if user_name in ["system | 시스템", "system", "시스템"]:
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
        from battle import get_battle_game
        battle_game = get_battle_game()
        await battle_game.handle_turn_skip(message)
        
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        await admin_manager.handle_turn_skip(message)
        
        return
    
    # !타격 명령어 처리
    if message.content.startswith("!타격"):
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        await admin_manager.handle_target_command(message)
        return
        
    # !전투 명령어 처리
    if message.content.startswith("!전투"):
        if message.author.display_name in ["system | 시스템", "system", "시스템"]:
            await handle_multi_battle_command(message)
        else:
            await message.channel.send("!전투 명령어는 Admin만 사용할 수 있습니다.")
        return
    
    # 테스트 모드 활성화
    if message.content == "test1234":
        for channel_id, view in blackjack_join_views.items():
            if channel_id == message.channel.id and not view.is_finished():
                ALLOWED_USERS = ["1007172975222603798", "YOUR_DISCORD_ID_HERE"]
                if str(message.author.id) in ALLOWED_USERS:
                    await message.delete()
                    await start_test_blackjack(view.interaction, message.author)
                    view.stop()
                    return
    
    asyncio.create_task(handle_message_safe(message))

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

@bot.event
async def on_disconnect():
    """연결 끊김 시 스킬 시스템 정리"""
    logger.warning("봇 연결이 끊어졌습니다. 스킬 데이터 저장 중...")
    try:
        await skill_manager.force_save()
        await skill_effects.clear_cache()
    except Exception as e:
        logger.error(f"스킬 데이터 저장 오류: {e}")

@bot.event
async def on_resumed():
    """연결 재개 이벤트"""
    logger.info("봇 연결이 재개되었습니다.")
    bot_manager.reconnect_attempts = 0

@bot.event
async def on_error(event, *args, **kwargs):
    """오류 이벤트 처리"""
    logger.error(f"봇 오류 발생 - 이벤트: {event}")
    traceback.print_exc()

# === 핵심 함수들 ===

async def handle_multi_battle_command(message: discord.Message):
    """!전투 명령어 처리 - 팀 전투 지원"""
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    
    content = message.content[4:].strip()
    
    if " vs " in content:
        # 팀 전투 처리 코드
        pass  # 기존 코드 유지
    else:
        # 1대다 전투 처리
        parts = content.split(',')
        
        if len(parts) < 1 or not parts[0].strip():
            await message.channel.send("사용법: !전투 @유저1 @유저2 , 체력값, 몬스터이름")
            return
        
        mentions = message.mentions
        if not mentions:
            await message.channel.send("전투할 유저를 멘션해주세요.")
            return
        
        admin_health = 10
        if len(parts) > 1:
            try:
                admin_health = int(parts[1].strip())
                if admin_health < 1:
                    admin_health = 10
            except ValueError:
                admin_health = 10
        
        monster_name = "시스템"
        if len(parts) > 2:
            monster_name = parts[2].strip()
            if not monster_name:
                monster_name = "시스템"
        
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

async def check_and_validate_battle_turn(user_id: int, channel_id: int) -> dict:
    """사용자가 현재 전투 중인지, 그리고 본인 턴인지 확인"""
    result = {
        "in_battle": False,
        "is_user_turn": False,
        "battle_type": None
    }
    
    try:
        # 몹 전투 확인
        if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
            battle = bot.mob_battles[channel_id]
            if battle.is_active:
                result["in_battle"] = True
                result["battle_type"] = "mob"
                
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
            
            if battle.pending_dice:
                if user_id in battle.pending_dice["waiting_for"]:
                    result["is_user_turn"] = True
            
            return result
            
    except Exception as e:
        logger.error(f"전투 턴 확인 실패: {e}")
    
    return result

async def auto_skip_turn_after_recovery(user_id: int, channel_id: int, battle_type: str, player_name: str, actual_recovery: int = 0):
    """회복 후 자동 턴 넘김 처리"""
    try:
        if battle_type == "mob":
            if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
                battle = bot.mob_battles[channel_id]
                
                if battle.pending_action and battle.pending_action.get("type") == "player_turn":
                    player = battle.pending_action.get("player")
                    if player and player.user.id == user_id:
                        from mob_setting import MobSetting, DiceResult
                        mob_setting = MobSetting(bot)
                        result = DiceResult(player_name=player.real_name, dice_value=actual_recovery)
                        await mob_setting.process_recovery_dice(battle, result)
                        return
        
        elif battle_type == "normal":
            from battle import get_battle_game
            battle_game = get_battle_game()
            
            if channel_id in battle_game.pending_dice:
                pending = battle_game.pending_dice[channel_id]
                if user_id in pending["waiting_for"]:
                    pending["waiting_for"].remove(user_id)
                    
                    from battle_utils import extract_real_name
                    real_name = extract_real_name(player_name)
                    
                    from battle import DiceResult
                    pending["results"][user_id] = DiceResult(
                        player_name=real_name,
                        dice_value=0,
                        user_id=user_id
                    )
                    
                    battle_data = battle_game.active_battles[channel_id]
                    await battle_data["message"].channel.send(f"⏭️💚 {real_name}님이 회복으로 턴을 소모했습니다.")
                    
                    if not pending["waiting_for"]:
                        await battle_game._process_dice_results(channel_id)
        
        elif battle_type == "admin":
            from battle_admin import get_admin_battle_manager
            admin_manager = get_admin_battle_manager()
            
            battle = admin_manager.active_battles[channel_id]
            if battle.pending_dice and user_id in battle.pending_dice["waiting_for"]:
                battle.pending_dice["waiting_for"].remove(user_id)
                battle.pending_dice["results"][user_id] = 0
                
                ADMIN_IDS = [1007172975222603798, 1090546247770832910]
                
                if user_id in ADMIN_IDS:
                    real_name = battle.monster_name
                else:
                    from battle_utils import extract_real_name
                    real_name = extract_real_name(player_name)
                
                await battle.message.channel.send(f"⏭️💚 {real_name}님이 회복으로 턴을 소모했습니다.")
                
                if not battle.pending_dice["waiting_for"]:
                    if battle.pending_dice["phase"] == "init":
                        await admin_manager._process_init_results(channel_id)
                    else:
                        await admin_manager._process_combat_results(channel_id)
                        
    except Exception as e:
        logger.error(f"자동 턴 넘김 처리 실패: {e}")

async def handle_mob_surrender(channel_id: int, user_id: int) -> bool:
    """몹 전투 항복 처리"""
    if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
        from mob_setting import MobSetting
        mob_setting = MobSetting(bot)
        return await mob_setting.handle_mob_surrender(channel_id, user_id)
    return False

# Admin 권한 체크
def is_admin():
    """Admin 권한 체크 데코레이터"""
    async def predicate(interaction: discord.Interaction) -> bool:
        ADMIN_IDS = [1007172975222603798, 1090546247770832910]
        return (interaction.user.id in ADMIN_IDS or 
                interaction.user.display_name in ["system | 시스템", "system", "시스템"])
    
    return app_commands.check(predicate)

# === 슬래시 명령어들 (필요한 것들만 포함) ===

@tree.command(name="몹세팅", description="자동 전투 몹을 설정합니다 (Admin 전용)")
@app_commands.describe(
    mob_name="몹 이름",
    mob_health="몹 체력 (전투 체력)",
    health_sync="체력 동기화 여부",
    ai_personality="AI 성격",
    ai_difficulty="AI 난이도"
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
        app_commands.Choice(name="쉬움", value="easy"),
        app_commands.Choice(name="보통", value="normal"),
        app_commands.Choice(name="어려움", value="hard"),
        app_commands.Choice(name="악몽", value="nightmare")
    ]
)
@app_commands.guild_only()
async def mob_setting_command(
    interaction: discord.Interaction,
    mob_name: str,
    mob_health: int,
    health_sync: bool,
    ai_personality: str = "tactical",
    ai_difficulty: str = "normal"
):
    """몹 세팅 슬래시 명령어"""
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
    
    if mob_health <= 0:
        await interaction.response.send_message(
            "❌ 체력은 1 이상이어야 합니다.", 
            ephemeral=True
        )
        return
    
    from mob_setting import AutoBattle, MobSettingView, create_mob_ai, AutonomousAIController
    
    battle = AutoBattle(
        mob_name=mob_name,
        mob_health=mob_health,
        mob_real_health=mob_health * 10 if health_sync else mob_health,
        health_sync=health_sync,
        channel=interaction.channel,
        creator=interaction.user,
        ai_personality=ai_personality,
        ai_difficulty=ai_difficulty
    )
    
    battle.mob_ai = create_mob_ai(
        mob_name,
        mob_health,
        ai_personality,
        ai_difficulty
    )
    battle.ai_controller = AutonomousAIController(battle.mob_ai)
    
    view = MobSettingView(battle)
    embed = view.create_setup_embed()
    
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()

@tree.command(name="전투", description="⚔️ 다른 플레이어와 전투를 시작합니다")
@app_commands.describe(상대="전투할 상대방을 선택하세요")
async def 전투_command(interaction: discord.Interaction, 상대: discord.Member):
    """전투 게임"""
    battle_game = get_battle_game()
    
    is_admin = interaction.user.display_name in ["system | 시스템", "system", "시스템"]
    
    if is_admin:
        from battle_admin import get_admin_battle_manager
        admin_manager = get_admin_battle_manager()
        await admin_manager.start_battle(interaction, 상대)
    else:
        await battle_game.start_battle(interaction, 상대)

@tree.command(name="항복", description="⚔️ 현재 진행 중인 전투에서 항복합니다")
async def 항복_command(interaction: discord.Interaction):
    """전투 항복"""
    channel_id = interaction.channel_id
    user_id = interaction.user.id

    if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
        if await handle_mob_surrender(channel_id, user_id):
            await interaction.response.send_message("항복 처리되었습니다.")
            return

    from battle import get_battle_game
    battle_game = get_battle_game()
    
    if channel_id in battle_game.active_battles:
        battle_data = battle_game.active_battles[channel_id]
        
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
    
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    
    if channel_id in admin_manager.active_battles:
        battle = admin_manager.active_battles[channel_id]
        
        for player in battle.users:
            if user_id == player.user.id:
                await admin_manager.handle_surrender(channel_id, player)
                await interaction.response.send_message(f"🏳️ {player.real_name}님이 항복했습니다!")
                return
        
        if user_id == battle.admin.user.id:
            await admin_manager.handle_admin_surrender(channel_id)
            await interaction.response.send_message(f"🏳️ {battle.monster_name}이(가) 항복했습니다!")
            return
    
    await interaction.response.send_message("진행 중인 전투가 없습니다.", ephemeral=True)

@tree.command(name="게임종료", description="현재 게임을 강제로 종료합니다.")
async def 게임종료_command(interaction: discord.Interaction):
    """게임 강제 종료"""
    channel_id = interaction.channel_id

    if hasattr(bot, 'mob_battles') and channel_id in bot.mob_battles:
        del bot.mob_battles[channel_id]
        await interaction.response.send_message("몹 전투가 종료되었습니다.")
        return

    from battle import get_battle_game
    battle_game = get_battle_game()
    if channel_id in battle_game.active_battles:
        del battle_game.active_battles[channel_id]
        await interaction.response.send_message("전투가 종료되었습니다.")
        return
    
    from battle_admin import get_admin_battle_manager
    admin_manager = get_admin_battle_manager()
    if channel_id in admin_manager.active_battles:
        del admin_manager.active_battles[channel_id]
        await interaction.response.send_message("Admin 전투가 종료되었습니다.")
        return
    
    if channel_id in joker_game.games and joker_game.games[channel_id].get('active'):
        joker_game.games[channel_id]['active'] = False
        await interaction.response.send_message("조커 게임이 종료되었습니다.")
        return
    
    if channel_id in active_blackjack_games:
        del active_blackjack_games[channel_id]
        await interaction.response.send_message("블랙잭 게임이 종료되었습니다.")
        return
    
    if channel_id in active_dice_poker_games:
        game = active_dice_poker_games[channel_id]
        for task in game.timeout_tasks.values():
            if not task.done():
                task.cancel()
        del active_dice_poker_games[channel_id]
        await interaction.response.send_message("주사위 포커 게임이 종료되었습니다.")
        return
    
    await interaction.response.send_message("진행 중인 게임이 없습니다.")

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
    # 스킬 시스템 초기화 스크립트 실행 (최초 1회)
    try:
        import os
        if not os.path.exists("skills/config/skill_config.json"):
            logger.info("스킬 시스템 초기 설정 파일 생성 중...")
            os.system("python init_skill_system.py")
    except Exception as e:
        logger.error(f"스킬 시스템 초기화 오류: {e}")
    
    # 봇 실행
    try:
        bot.run(BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트로 봇 종료")
    except Exception as e:
        logger.error(f"봇 실행 중 오류: {e}")
        traceback.print_exc()
    finally:
        asyncio.run(shutdown_bot())

