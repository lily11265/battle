# skills/skill.py
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from .skill_manager import skill_manager
from .heroes import get_skill_handler

logger = logging.getLogger(__name__)

class SkillCog(commands.Cog):
    """스킬 시스템 명령어 Cog (24시간 최적화)"""
    
    def __init__(self, bot):
        self.bot = bot
        self._skill_handlers: Dict = {}  # 스킬 핸들러 캐시
        self._interaction_cache: Dict[str, float] = {}  # 중복 실행 방지
    
    async def cog_load(self):
        """Cog 로딩 시 초기화"""
        await skill_manager.initialize()
        await self._load_skill_handlers()
        logger.info("SkillCog 로딩 완료")
    
    async def _load_skill_handlers(self):
        """스킬 핸들러 미리 로딩 (성능 최적화)"""
        skill_names = ["오닉셀", "피닉스", "오리븐", "카론"]
        for skill_name in skill_names:
            try:
                handler = get_skill_handler(skill_name)
                if handler:
                    self._skill_handlers[skill_name] = handler
            except Exception as e:
                logger.error(f"스킬 핸들러 로딩 실패 {skill_name}: {e}")
    
    def _get_available_skills_for_user(self, user_id: str, channel_id: str) -> List[app_commands.Choice]:
        """유저가 사용 가능한 스킬 목록 (최적화된 조회)"""
        # 권한 체크
        user_id_str = str(user_id)
        if skill_manager.is_admin(user_id_str):
            available_skills = list(self._skill_handlers.keys())
        else:
            available_skills = skill_manager.get_user_allowed_skills(user_id_str)
        
        # 이미 사용 중인 스킬 제외
        channel_state = skill_manager.get_channel_state(str(channel_id))
        active_skills = set(channel_state["active_skills"].keys())
        
        # Choice 객체 생성 (메모리 효율적)
        choices = []
        for skill in available_skills:
            if skill not in active_skills and skill in self._skill_handlers:
                choices.append(app_commands.Choice(name=skill, value=skill))
        
        return choices[:25]  # Discord 제한
    
    @app_commands.command(name="스킬", description="영웅의 스킬을 사용합니다")
    @app_commands.describe(
        영웅="사용할 영웅 스킬",
        라운드="지속 라운드 (1-10)",
        취소할_스킬="취소할 스킬 (ADMIN 전용)"
    )
    @app_commands.guild_only()
    async def skill_command(
        self, 
        interaction: discord.Interaction,
        영웅: Optional[str] = None,
        라운드: Optional[app_commands.Range[int, 1, 10]] = None,
        취소할_스킬: Optional[str] = None
    ):
        """메인 스킬 명령어"""
        # 중복 실행 방지 (성능 최적화)
        interaction_key = f"{interaction.user.id}_{interaction.channel.id}"
        current_time = asyncio.get_event_loop().time()
        
        if interaction_key in self._interaction_cache:
            if current_time - self._interaction_cache[interaction_key] < 2.0:
                await interaction.response.send_message("❌ 너무 빨리 명령어를 실행했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
                return
        
        self._interaction_cache[interaction_key] = current_time
        
        try:
            # 취소 옵션 처리 (ADMIN 전용)
            if 취소할_스킬:
                if not skill_manager.is_admin(str(interaction.user.id), interaction.user.display_name):
                    await interaction.response.send_message("🔒 스킬 취소는 관리자만 사용할 수 있습니다.", ephemeral=True)
                    return
                
                await self._handle_skill_cancel(interaction, 취소할_스킬)
                return
            
            # 필수 옵션 체크
            if not 영웅 or not 라운드:
                await interaction.response.send_message("❌ 영웅과 라운드를 모두 입력해주세요.", ephemeral=True)
                return
            
            # 스킬 사용 처리
            await self._handle_skill_use(interaction, 영웅, 라운드)
            
        except Exception as e:
            logger.error(f"스킬 명령어 처리 중 오류: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 명령어 처리 중 오류가 발생했습니다.", ephemeral=True)
        finally:
            # 캐시 정리 (메모리 누수 방지)
            if len(self._interaction_cache) > 100:
                old_keys = [k for k, v in self._interaction_cache.items() if current_time - v > 300]
                for key in old_keys:
                    del self._interaction_cache[key]
    
    async def _handle_skill_cancel(self, interaction: discord.Interaction, skill_name: str):
        """스킬 취소 처리"""
        channel_id = str(interaction.channel.id)
        channel_state = skill_manager.get_channel_state(channel_id)
        
        if skill_name not in channel_state["active_skills"]:
            await interaction.response.send_message(f"❌ '{skill_name}' 스킬이 활성화되어 있지 않습니다.", ephemeral=True)
            return
        
        # 스킬 제거
        skill_manager.remove_skill(channel_id, skill_name)
        
        embed = discord.Embed(
            title="🚫 스킬 취소",
            description=f"**{skill_name}** 스킬이 취소되었습니다.",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)
    
    async def _handle_skill_use(self, interaction: discord.Interaction, skill_name: str, duration: int):
        """스킬 사용 처리"""
        user_id = str(interaction.user.id)
        channel_id = str(interaction.channel.id)
        
        # 권한 체크
        if not self._check_skill_permission(user_id, skill_name, interaction.user.display_name):
            await interaction.response.send_message(f"🔒 '{skill_name}' 스킬 사용 권한이 없습니다.", ephemeral=True)
            return
        
        # 스킬 핸들러 체크
        if skill_name not in self._skill_handlers:
            await interaction.response.send_message(f"❌ '{skill_name}' 스킬을 찾을 수 없습니다.", ephemeral=True)
            return
        
        # 전투 상태 체크 (mob_setting.py와 연동)
        if not await self._check_battle_active(channel_id):
            await interaction.response.send_message("⚠️ 전투 중이 아닙니다.", ephemeral=True)
            return
        
        # 대상 선택이 필요한 스킬 체크
        handler = self._skill_handlers[skill_name]
        needs_target = getattr(handler, 'needs_target', False)
        
        if needs_target:
            await self._handle_target_selection(interaction, skill_name, duration, handler)
        else:
            await self._activate_skill(interaction, skill_name, duration, user_id, user_id, interaction.user.display_name)
    
    def _check_skill_permission(self, user_id: str, skill_name: str, display_name: str) -> bool:
        """스킬 사용 권한 체크 (최적화)"""
        # 관리자는 모든 스킬 사용 가능
        if skill_manager.is_admin(user_id, display_name):
            return True
        
        # 특별 제한 스킬 체크
        if skill_name == "넥시스" and user_id != "1059908946741166120":
            return False
        
        # 일반 사용자 권한 체크
        allowed_skills = skill_manager.get_user_allowed_skills(user_id)
        return skill_name in allowed_skills
    
    async def _check_battle_active(self, channel_id: str) -> bool:
        """전투 활성 상태 체크 (기존 시스템과 연동)"""
        # 기존 mob_setting.py와 연동하여 전투 상태 확인
        # 현재는 단순화된 체크
        channel_state = skill_manager.get_channel_state(channel_id)
        return channel_state.get("battle_active", False)
    
    async def _handle_target_selection(self, interaction: discord.Interaction, 
                                     skill_name: str, duration: int, handler):
        """대상 선택 처리"""
        # 현재 Phase 1에서는 단순화 (Phase 2에서 구현 예정)
        user_id = str(interaction.user.id)
        await self._activate_skill(interaction, skill_name, duration, user_id, user_id, interaction.user.display_name)
    
    async def _activate_skill(self, interaction: discord.Interaction, skill_name: str, 
                            duration: int, user_id: str, target_id: str, target_name: str):
        """스킬 활성화"""
        channel_id = str(interaction.channel.id)
        
        # 스킬 추가 시도
        success = skill_manager.add_skill(
            channel_id, skill_name, user_id, 
            interaction.user.display_name, target_id, target_name, duration
        )
        
        if not success:
            await interaction.response.send_message("❌ 스킬을 사용할 수 없습니다. (중복 사용 또는 제한)", ephemeral=True)
            return
        
        # 스킬 효과 적용
        handler = self._skill_handlers[skill_name]
        try:
            await handler.activate(interaction, target_id, duration)
        except Exception as e:
            logger.error(f"스킬 활성화 실패 {skill_name}: {e}")
            # 실패 시 롤백
            skill_manager.remove_skill(channel_id, skill_name)
            await interaction.followup.send("❌ 스킬 활성화 중 오류가 발생했습니다.", ephemeral=True)
            return
        
        # 성공 메시지
        embed = discord.Embed(
            title="✅ 스킬 발동!",
            description=f"**{skill_name}**의 힘이 {target_name}에게 적용되었습니다! ({duration}라운드)",
            color=discord.Color.green()
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    
    # 자동완성 (동적 생성으로 성능 최적화)
    @skill_command.autocomplete('영웅')
    async def skill_autocomplete(self, interaction: discord.Interaction, current: str):
        """스킬 자동완성"""
        try:
            available_skills = self._get_available_skills_for_user(
                interaction.user.id, 
                interaction.channel.id
            )
            
            # 현재 입력과 일치하는 스킬 필터링
            if current:
                filtered = [choice for choice in available_skills 
                          if current.lower() in choice.name.lower()]
                return filtered[:25]
            
            return available_skills[:25]
            
        except Exception as e:
            logger.error(f"자동완성 오류: {e}")
            return []
    
    @skill_command.autocomplete('취소할_스킬')
    async def cancel_skill_autocomplete(self, interaction: discord.Interaction, current: str):
        """취소할 스킬 자동완성 (ADMIN 전용)"""
        try:
            # 관리자만 접근 가능
            if not skill_manager.is_admin(str(interaction.user.id), interaction.user.display_name):
                return []
            
            channel_state = skill_manager.get_channel_state(str(interaction.channel.id))
            active_skills = list(channel_state["active_skills"].keys())
            
            choices = [app_commands.Choice(name=skill, value=skill) for skill in active_skills]
            
            if current:
                choices = [choice for choice in choices if current.lower() in choice.name.lower()]
            
            return choices[:25]
            
        except Exception as e:
            logger.error(f"취소 자동완성 오류: {e}")
            return []

async def setup(bot):
    """Cog 설정"""
    await bot.add_cog(SkillCog(bot))