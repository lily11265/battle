# main1.py - 전투 시스템 다이스 감지 추가 버전
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
import json
import os
from datetime import datetime
import sys
import traceback

# 환경 설정 및 로깅
from debug_config import debug_config, debug_log

# 로깅 설정
def setup_logging():
    """로깅 설정"""
    # 로그 디렉토리 생성
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 로그 포맷 설정
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 파일 핸들러
    file_handler = logging.FileHandler(
        filename=f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log',
        encoding='utf-8',
        mode='a'
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # 루트 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Discord.py 로거 레벨 조정
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)
    
    return logger

# 설정 파일 로드
def load_config():
    """설정 파일 로드"""
    config_file = 'config.json'
    
    # 기본 설정
    default_config = {
        "token": "",
        "prefix": "!",
        "owner_ids": [1090546247770832910],
        "database": {
            "type": "sqlite",
            "path": "bot_database.db"
        },
        "features": {
            "minigames": True,
            "economy": True,
            "quests": True
        },
        "dice_bot": {
            "enabled": True,
            "bot_name": "봇",
            "timeout": 30
        }
    }
    
    # 설정 파일이 없으면 생성
    if not os.path.exists(config_file):
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"⚠️  {config_file} 파일이 생성되었습니다. 봇 토큰을 설정해주세요!")
        sys.exit(1)
    
    # 설정 로드
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 토큰 확인
    if config['token'] == "YOUR_BOT_TOKEN_HERE":
        print("⚠️  config.json 파일에 봇 토큰을 설정해주세요!")
        sys.exit(1)
    
    return config

# 봇 클래스
class MatsuriBot(commands.Bot):
    def __init__(self, config):
        # 인텐트 설정
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=config['prefix'],
            intents=intents,
            owner_ids=set(config['owner_ids']) if config['owner_ids'] else None,
            help_command=None  # 커스텀 도움말 사용
        )
        
        self.config = config
        self.start_time = datetime.now()
        self.logger = logging.getLogger('MatsuriBot')
        
        # 전투 시스템을 위한 참조 저장
        self.battle_game = None
        self.fishing_game = None  # fishing 게임 참조 추가

    async def setup_hook(self):
        """봇 초기화 시 실행"""
        self.logger.info("봇 초기화 중...")
        
        # Cog 로드
        await self.load_extensions()
        
        # 전투 게임 인스턴스 가져오기
        try:
            from battle import get_battle_game
            self.battle_game = get_battle_game()
            self.logger.info("전투 시스템 로드 완료")
        except Exception as e:
            self.logger.error(f"전투 시스템 로드 실패: {e}")
        
        # fishing 게임 인스턴스 가져오기
        try:
            from fishing import get_fishing_game
            self.fishing_game = get_fishing_game()
            self.logger.info("낚시 게임 시스템 로드 완료")
        except Exception as e:
            self.logger.error(f"낚시 게임 시스템 로드 실패: {e}")
        
        # 슬래시 커맨드 동기화
        self.logger.info("슬래시 커맨드 동기화 중...")
        try:
            synced = await self.tree.sync()
            self.logger.info(f"{len(synced)}개의 슬래시 커맨드가 동기화되었습니다.")
        except Exception as e:
            self.logger.error(f"슬래시 커맨드 동기화 실패: {e}")
    
    async def load_extensions(self):
        """확장 기능(Cog) 로드"""
        # 관리자 명령어 로드
        try:
            await self.load_extension('admin_commands')
            self.logger.info("관리자 명령어 Cog 로드 완료")
        except Exception as e:
            self.logger.error(f"관리자 명령어 Cog 로드 실패: {e}")
        
        # 미니게임 Cog 로드
        if self.config['features']['minigames']:
            try:
                await self.load_extension('minigames_commands')
                self.logger.info("미니게임 Cog 로드 완료")
            except Exception as e:
                self.logger.error(f"미니게임 Cog 로드 실패: {e}")
                traceback.print_exc()
    
    async def on_ready(self):
        """봇이 준비되었을 때"""
        self.logger.info(f"봇 로그인: {self.user} (ID: {self.user.id})")
        self.logger.info(f"접속한 서버 수: {len(self.guilds)}")
        
        # 상태 메시지 설정
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="🎌 일본 축제 미니게임 | /게임 도움말")
        )
        
        # 디버그 모드 상태
        if debug_config.debug_enabled:
            self.logger.warning("⚠️  디버그 모드가 활성화되어 있습니다!")
    
    async def on_guild_join(self, guild):
        """새 서버에 참가했을 때"""
        self.logger.info(f"새 서버 참가: {guild.name} (ID: {guild.id}, 멤버: {guild.member_count})")
        
        # 환영 메시지 (시스템 채널이 있는 경우)
        if guild.system_channel:
            embed = discord.Embed(
                title="🎌 마츠리 봇을 초대해주셔서 감사합니다!",
                description="일본 축제 테마의 다양한 미니게임을 즐겨보세요!\n\n"
                           "**시작하기**: `/게임 도움말`\n"
                           "**게임 목록**:\n"
                           "• 🎯 사격\n"
                           "• 🎣 낚시\n"
                           "• 🍪 달고나\n"
                           "• 🔫 마피아\n"
                           "• ⭕ 와나게 (링 던지기)\n"
                           "• 🎊 빙고\n"
                           "• ⚔️ 전투 (NEW!)",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="⚔️ 전투 게임 특별 안내",
                value="전투 게임은 **봇**의 `/주사위` 명령어와 연동됩니다!\n"
                      "전투 중 다이스 요청 시 `/주사위`를 입력하세요.",
                inline=False
            )
            
            try:
                await guild.system_channel.send(embed=embed)
            except:
                pass
    
    async def on_message(self, message):
        """메시지 이벤트 처리"""
        # 봇 메시지 무시
        if message.author.bot:
            # 다이스 봇 메시지 처리
            if (self.config.get('dice_bot', {}).get('enabled', True) and 
                message.author.display_name == self.config.get('dice_bot', {}).get('bot_name', '봇')):
                await self._handle_dice_message(message)
            return
        
        # fishing 게임 채팅 메시지 처리
        if self.fishing_game:
            try:
                await self.fishing_game.process_chat_message(message)
            except Exception as e:
                debug_log("FISHING_CHAT", f"Error processing chat message: {e}")
        
        # 일반 커맨드 처리
        await self.process_commands(message)
    
    async def _handle_dice_message(self, message):
        """다이스 메시지 처리"""
        try:
            # 전투 게임과 낚시 게임 모두 확인
            if self.battle_game:
                content_normalized = message.content.replace(" ", "")
                if ("주사위를굴려" in content_normalized and 
                    "나왔습니다" in content_normalized):
                    
                    debug_log("DICE_HANDLER", f"Processing dice message from {message.author.display_name}: {message.content}")
                    
                    # 전투 시스템에 전달
                    await self.battle_game.process_dice_message(message)
                    
                    # 낚시 게임에도 전달 (fishing 모듈 확인)
                    try:
                        from fishing import get_fishing_game
                        fishing_game = get_fishing_game()
                        if fishing_game:
                            await fishing_game.process_dice_message(message)
                            debug_log("DICE_HANDLER", "Dice message also sent to fishing game")
                    except Exception as e:
                        debug_log("DICE_HANDLER", f"Failed to send to fishing game: {e}")
                        
        except Exception as e:
            self.logger.error(f"다이스 메시지 처리 실패: {e}")
            debug_log("DICE_HANDLER", f"Error processing dice message: {e}")
    
    async def on_command_error(self, ctx, error):
        """커맨드 에러 처리"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ 필수 인자가 누락되었습니다: {error.param.name}")
        
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ 이 명령어를 사용할 권한이 없습니다.")
        
        else:
            self.logger.error(f"커맨드 에러: {error}")
            await ctx.send(f"❌ 오류가 발생했습니다: {error}")
    
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        """슬래시 커맨드 에러 처리"""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ 이 명령어를 사용할 권한이 없습니다.",
                ephemeral=True
            )
        else:
            self.logger.error(f"슬래시 커맨드 에러: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 오류가 발생했습니다.",
                    ephemeral=True
                )
    
    # 이벤트 리스너 (퀘스트 시스템 등을 위해)
    async def on_minigame_started(self, user_id: str, user_name: str, game_name: str):
        """미니게임 시작 이벤트"""
        debug_log("EVENT", f"{user_name}님이 {game_name} 게임을 시작했습니다.")
    
    async def on_minigame_complete(self, user_id: str, user_name: str, game_name: str, reward: int):
        """미니게임 완료 이벤트"""
        debug_log("EVENT", f"{user_name}님이 {game_name} 게임을 완료했습니다. 보상: {reward}💰")
    
    async def on_battle_started(self, user1_id: str, user1_name: str, user2_id: str, user2_name: str):
        """전투 시작 이벤트"""
        debug_log("EVENT", f"전투 시작: {user1_name} vs {user2_name}")
    
    async def on_battle_ended(self, winner_id: str, winner_name: str, loser_id: str, loser_name: str, rounds: int):
        """전투 종료 이벤트"""
        debug_log("EVENT", f"전투 종료: {winner_name} 승리 vs {loser_name} ({rounds}라운드)")

# utility.py의 더미 구현 (실제로는 별도 파일로 구현해야 함)
async def update_player_balance(user_id: str, amount: int):
    """플레이어 잔액 업데이트 (더미 구현)"""
    debug_log("ECONOMY", f"User {user_id} balance updated by {amount}")
    # 실제로는 데이터베이스에 저장
    pass

# 메인 실행
async def main():
    """메인 함수"""
    # 로깅 설정
    logger = setup_logging()
    logger.info("=== 마츠리 봇 시작 ===")
    
    # 설정 로드
    config = load_config()
    
    # 봇 생성
    bot = MatsuriBot(config)
    
    try:
        # 봇 시작
        await bot.start(config['token'])
    except discord.LoginFailure:
        logger.error("❌ 봇 토큰이 올바르지 않습니다!")
    except Exception as e:
        logger.error(f"❌ 봇 실행 중 오류 발생: {e}")
        traceback.print_exc()
    finally:
        await bot.close()

if __name__ == "__main__":
    # Windows 환경에서 ProactorEventLoop 경고 방지
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 봇 실행
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n봇이 종료되었습니다.")
    except Exception as e:
        print(f"치명적 오류: {e}")
        traceback.print_exc()