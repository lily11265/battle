# admin_commands.py
import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
from typing import Optional, Literal
from hot_reload import setup_hot_reload, hot_reload_system
from debug_config import debug_log, debug_config

class AdminCommands(commands.Cog):
    """관리자 전용 명령어"""
    
    def __init__(self, bot):
        self.bot = bot
        self.hot_reload = setup_hot_reload(bot)
    
    @app_commands.command(name="reload", description="모듈을 핫 리로드합니다 (관리자 전용)")
    @app_commands.describe(
        module="리로드할 모듈 이름",
        reload_all="모든 모듈 리로드"
    )
    @app_commands.choices(module=[
        app_commands.Choice(name="미니게임 전체", value="minigames_commands"),
        app_commands.Choice(name="사격", value="dart"),
        app_commands.Choice(name="금붕어잡기", value="fishing"),
        app_commands.Choice(name="달고나", value="dalgona"),
        app_commands.Choice(name="마피아", value="mafia"),
        app_commands.Choice(name="와나게", value="wanage"),
        app_commands.Choice(name="빙고", value="matsuri_bingo"),
        app_commands.Choice(name="전투", value="battle"),
        app_commands.Choice(name="상점", value="shop"),
        app_commands.Choice(name="유틸리티", value="utility"),
        app_commands.Choice(name="디버그", value="debug_config"),
        app_commands.Choice(name="설정파일", value="config")
    ])
    @app_commands.default_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction, 
                    module: Optional[str] = None,
                    reload_all: bool = False):
        """모듈 핫 리로드"""
        # 권한 체크
        if interaction.user.id not in self.bot.config.get('owner_ids', []):
            await interaction.response.send_message(
                "❌ 봇 소유자만 사용할 수 있는 명령어입니다.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        if reload_all:
            # 모든 모듈 리로드
            success, results = await self.hot_reload.safe_reload_all()
            
            embed = discord.Embed(
                title="🔄 전체 모듈 리로드",
                color=discord.Color.green() if success else discord.Color.red()
            )
            
            # 결과를 보기 좋게 정리
            for result in results:
                module_name = result.split(':')[0]
                status = "성공" if "✅" in result else "실패"
                embed.add_field(
                    name=f"{module_name}",
                    value=status,
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        elif module:
            # 특정 모듈 리로드
            if module == "config":
                success, msg = await self.hot_reload.reload_config()
            else:
                success, msg = await self.hot_reload.reload_module(module)
            
            embed = discord.Embed(
                title=f"🔄 모듈 리로드: {module}",
                description=msg,
                color=discord.Color.green() if success else discord.Color.red()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # 사용법 안내
            embed = discord.Embed(
                title="📚 핫 리로드 사용법",
                description="봇을 재시작하지 않고 코드를 업데이트합니다.",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="특정 모듈 리로드",
                value="`/reload module:사격` - 사격 게임만 리로드",
                inline=False
            )
            
            embed.add_field(
                name="전체 리로드",
                value="`/reload reload_all:True` - 모든 모듈 리로드",
                inline=False
            )
            
            # 최근 리로드 기록
            history = self.hot_reload.get_reload_history(5)
            if history:
                history_text = "\n".join([
                    f"• {h['module']} - {h['timestamp'].strftime('%H:%M:%S')} "
                    f"{'✅' if h['status'] == 'success' else '❌'}"
                    for h in history
                ])
                embed.add_field(
                    name="최근 리로드 기록",
                    value=history_text,
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="exec", description="Python 코드 실행 (위험! 소유자 전용)")
    @app_commands.describe(code="실행할 Python 코드")
    @app_commands.default_permissions(administrator=True)
    async def execute_code(self, interaction: discord.Interaction, code: str):
        """Python 코드 직접 실행 (매우 위험!)"""
        # 봇 소유자만 사용 가능
        if interaction.user.id not in self.bot.config.get('owner_ids', []):
            await interaction.response.send_message(
                "❌ 봇 소유자만 사용할 수 있는 명령어입니다.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # 보안 경고
        warning_embed = discord.Embed(
            title="⚠️ 코드 실행 경고",
            description="이 기능은 매우 위험합니다!\n"
                       "신뢰할 수 있는 코드만 실행하세요.",
            color=discord.Color.orange()
        )
        
        try:
            # 실행 환경 설정
            env = {
                'bot': self.bot,
                'interaction': interaction,
                'discord': discord,
                'commands': commands,
                'debug_log': debug_log,
                'debug_config': debug_config
            }
            
            # 코드 실행
            exec(code, env)
            
            await interaction.followup.send(
                embeds=[warning_embed],
                content="✅ 코드 실행 완료",
                ephemeral=True
            )
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ 실행 오류",
                description=f"```python\n{str(e)}\n```",
                color=discord.Color.red()
            )
            
            await interaction.followup.send(
                embeds=[warning_embed, error_embed],
                ephemeral=True
            )
    
    @app_commands.command(name="status", description="봇 상태 확인")
    @app_commands.default_permissions(administrator=True)
    async def check_status(self, interaction: discord.Interaction):  # bot_status에서 check_status로 이름 변경
        """봇 상태 확인"""
        embed = discord.Embed(
            title="🤖 봇 상태",
            color=discord.Color.blue()
        )
        
        # 기본 정보
        embed.add_field(
            name="버전",
            value=f"Python {sys.version.split()[0]}",
            inline=True
        )
        
        embed.add_field(
            name="discord.py",
            value=discord.__version__,
            inline=True
        )
        
        embed.add_field(
            name="서버 수",
            value=f"{len(self.bot.guilds)}개",
            inline=True
        )
        
        # 로드된 Cog
        cogs = list(self.bot.cogs.keys())
        embed.add_field(
            name="로드된 Cog",
            value=", ".join(cogs) if cogs else "없음",
            inline=False
        )
        
        # 로드된 모듈
        game_modules = [
            'dart', 'fishing', 'dalgona', 
            'mafia', 'wanage', 'matsuri_bingo', 'battle'
        ]
        loaded_modules = [m for m in game_modules if m in sys.modules]
        embed.add_field(
            name="게임 모듈",
            value=", ".join(loaded_modules),
            inline=False
        )
        
        # 디버그 상태
        embed.add_field(
            name="디버그 모드",
            value="✅ 켜짐" if debug_config.debug_enabled else "❌ 꺼짐",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Cog 설정"""
    await bot.add_cog(AdminCommands(bot))