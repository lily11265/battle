# skills/skill.py - Phase 2 업데이트
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from .skill_manager import skill_manager
from .heroes import get_skill_handler, get_all_available_skills

logger = logging.getLogger(__name__)

class SkillCog(commands.Cog):
    """스킬 시스템 명령어 Cog (Phase 2 - 완전 기능)"""
    
    def __init__(self, bot):
        self.bot = bot
        self._skill_handlers: Dict = {}  # 스킬 핸들러 캐시
        self._interaction_cache: Dict[str, float] = {}  # 중복 실행 방지
    
    async def cog_load(self):
        """Cog 로딩 시 초기화"""
        await skill_manager.initialize()
        await self._load_all_skill_handlers()
        logger.info("SkillCog Phase 2 로딩 완료")
    
    async def _load_all_skill_handlers(self):
        """모든 스킬 핸들러 로딩 (Phase 2)"""
        all_skills = [
            # Phase 1 기본 스킬들
            "오닉셀", "피닉스", "오리븐", "카론",
            # Phase 2 추가 스킬들
            "스카넬", "루센시아", "비렐라", "그림", "닉사라", 
            "제룬카", "넥시스", "볼켄", "단목", "콜 폴드", 
            "황야", "스트라보스"
        ]
        
        for skill_name in all_skills:
            try:
                handler = get_skill_handler(skill_name)
                if handler:
                    self._skill_handlers[skill_name] = handler
                    logger.debug(f"스킬 핸들러 로딩 완료: {skill_name}")
            except Exception as e:
                logger.error(f"스킬 핸들러 로딩 실패 {skill_name}: {e}")
    
    def _get_available_skills_for_user(self, user_id: str, channel_id: str) -> List[app_commands.Choice]:
        """유저가 사용 가능한 스킬 목록 (최적화된 조회)"""
        user_id_str = str(user_id)
        display_name = ""
        
        try:
            # Discord에서 유저 정보 가져오기
            guild = self.bot.get_guild(int(channel_id)) if channel_id.isdigit() else None
            if guild:
                member = guild.get_member(int(user_id))
                if member:
                    display_name = member.display_name
        except:
            pass
        
        # 권한 체크
        if skill_manager.is_admin(user_id_str, display_name):
            available_skills = list(self._skill_handlers.keys())
        else:
            available_skills = skill_manager.get_user_allowed_skills(user_id_str)
        
        # 특별 제한 스킬 체크
        if "넥시스" in available_skills and user_id_str != "1059908946741166120":
            available_skills.remove("넥시스")
        
        # 이미 사용 중인 스킬 제외
        channel_state = skill_manager.get_channel_state(str(channel_id))
        active_skills = set(channel_state["active_skills"].keys())
        
        # 개인 스킬 제한 체크 (한 명당 하나의 스킬만)
        user_active_skills = [
            skill_name for skill_name, skill_data in channel_state["active_skills"].items()
            if skill_data["user_id"] == user_id_str
        ]
        
        if user_active_skills:
            # 이미 스킬을 사용 중이면 빈 목록 반환
            return []
        
        # Choice 객체 생성
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
        """메인 스킬 명령어 (Phase 2 완전 기능)"""
        # 중복 실행 방지
        interaction_key = f"{interaction.user.id}_{interaction.channel.id}"
        current_time = asyncio.get_event_loop().time()
        
        if interaction_key in self._interaction_cache:
            if current_time - self._interaction_cache[interaction_key] < 3.0:  # 3초 쿨다운
                await interaction.response.send_message("❌ 너무 빨리 명령어를 실행했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
                return
        
        self._interaction_cache[interaction_key] = current_time
        
        try:
            # 전투 상태 체크
            if not await self._check_battle_active(str(interaction.channel.id)):
                await interaction.response.send_message("⚠️ 전투 중이 아닙니다.", ephemeral=True)
                return
            
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
        
        # 스킬 종료 처리
        await self._end_skill(channel_id, skill_name)
        
        embed = discord.Embed(
            title="🚫 스킬 취소",
            description=f"**{skill_name}** 스킬이 관리자에 의해 취소되었습니다.",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)
        
        # 전투 화면 업데이트
        await self._update_battle_display(channel_id)
    
    async def _handle_skill_use(self, interaction: discord.Interaction, skill_name: str, duration: int):
        """스킬 사용 처리 (Phase 2)"""
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
        
        # 개인 스킬 제한 체크
        channel_state = skill_manager.get_channel_state(channel_id)
        user_active_skills = [
            s for s in channel_state["active_skills"].values() 
            if s["user_id"] == user_id
        ]
        
        if user_active_skills:
            await interaction.response.send_message(f"❌ 이미 활성화된 스킬이 있습니다: {user_active_skills[0].get('skill_name', '알 수 없음')}", ephemeral=True)
            return
        
        # 중복 스킬 체크
        if skill_name in channel_state["active_skills"]:
            await interaction.response.send_message(f"❌ '{skill_name}' 스킬이 이미 사용 중입니다.", ephemeral=True)
            return
        
        # 스킬 활성화
        handler = self._skill_handlers[skill_name]
        try:
            await handler.activate(interaction, user_id, duration)
            
            # 전투 화면 업데이트
            await self._update_battle_display(channel_id)
            
        except Exception as e:
            logger.error(f"스킬 활성화 실패 {skill_name}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 스킬 활성화 중 오류가 발생했습니다.", ephemeral=True)
    
    def _check_skill_permission(self, user_id: str, skill_name: str, display_name: str) -> bool:
        """스킬 사용 권한 체크"""
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
        """전투 활성 상태 체크"""
        try:
            from battle_admin import is_battle_active
            return await is_battle_active(channel_id)
        except Exception as e:
            logger.error(f"전투 상태 확인 실패: {e}")
            return False
    
    async def _end_skill(self, channel_id: str, skill_name: str):
        """스킬 종료 처리"""
        try:
            # 스킬 핸들러의 종료 처리 호출
            handler = self._skill_handlers.get(skill_name)
            if handler:
                await handler.on_skill_end(channel_id, "system")
            
            # 스킬 상태에서 제거
            skill_manager.remove_skill(channel_id, skill_name)
            
            # 특별 효과 정리
            channel_state = skill_manager.get_channel_state(channel_id)
            special_effects = channel_state.get("special_effects", {})
            
            # 스킬 관련 특별 효과들 정리
            effects_to_remove = []
            for effect_name in special_effects:
                if (effect_name.startswith(skill_name.lower()) or 
                    effect_name in [f"{skill_name.lower()}_bound", f"{skill_name.lower()}_excluded", 
                                   f"{skill_name.lower()}_preparing", f"{skill_name.lower()}_curse"]):
                    effects_to_remove.append(effect_name)
            
            for effect_name in effects_to_remove:
                del special_effects[effect_name]
            
            skill_manager.mark_dirty(channel_id)
            
        except Exception as e:
            logger.error(f"스킬 종료 처리 실패 {skill_name}: {e}")
    
    async def _update_battle_display(self, channel_id: str):
        """전투 화면 업데이트"""
        try:
            from battle_admin import update_battle_display
            await update_battle_display(channel_id)
        except Exception as e:
            logger.error(f"전투 화면 업데이트 실패: {e}")
    
    # 자동완성들
    @skill_command.autocomplete('영웅')
    async def skill_autocomplete(self, interaction: discord.Interaction, current: str):
        """스킬 자동완성 (Phase 2)"""
        try:
            available_skills = self._get_available_skills_for_user(
                interaction.user.id, 
                str(interaction.channel.id)
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

# 메시지 리스너 (주사위 처리)
@commands.Cog.listener()
async def on_message(message):
    """메시지 리스너 - 주사위 처리"""
    if message.author.bot:
        return
    
    # 주사위 메시지인지 확인
    if is_dice_message(message.content):
        try:
            from battle_admin import process_dice_with_skill_effects
            await process_dice_with_skill_effects(message)
        except Exception as e:
            logger.error(f"주사위 스킬 효과 처리 실패: {e}")

def is_dice_message(content: str) -> bool:
    """주사위 메시지 여부 확인"""
    dice_keywords = ["결과:", "주사위:", "결과는", "이(가) 나왔습니다", "점"]
    return any(keyword in content for keyword in dice_keywords)

# Phase 2 추가 명령어들
class SkillInfoCog(commands.Cog):
    """스킬 정보 관련 명령어들"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="스킬목록", description="사용 가능한 스킬 목록을 확인합니다")
    @app_commands.guild_only()
    async def skill_list(self, interaction: discord.Interaction):
        """스킬 목록 표시"""
        user_id = str(interaction.user.id)
        display_name = interaction.user.display_name
        
        # 사용자 권한에 따른 스킬 목록
        if skill_manager.is_admin(user_id, display_name):
            available_skills = get_all_available_skills()
            title = "🔮 모든 스킬 목록 (관리자)"
        else:
            available_skills = skill_manager.get_user_allowed_skills(user_id)
            title = "🔮 사용 가능한 스킬 목록"
        
        embed = discord.Embed(
            title=title,
            description=f"총 {len(available_skills)}개의 스킬을 사용할 수 있습니다.",
            color=discord.Color.blue()
        )
        
        # 카테고리별 분류
        skill_categories = {
            "자기 강화": ["오닉셀", "스트라보스", "콜 폴드", "황야"],
            "대상 지정": ["스카넬", "루센시아", "비렐라", "그림", "닉사라", "제룬카", "넥시스", "단목"],
            "전역 효과": ["오리븐", "카론", "볼켄"],
            "유저 전용": ["피닉스"]
        }
        
        for category, skills in skill_categories.items():
            user_skills = [skill for skill in skills if skill in available_skills]
            if user_skills:
                embed.add_field(
                    name=f"⚔️ {category}",
                    value="\n".join([f"• {skill}" for skill in user_skills]),
                    inline=True
                )
        
        if not available_skills:
            embed.add_field(
                name="❌ 사용 불가",
                value="현재 사용할 수 있는 스킬이 없습니다.\n관리자에게 문의하세요.",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="스킬상태", description="현재 활성화된 스킬 상태를 확인합니다")
    @app_commands.guild_only()
    async def skill_status(self, interaction: discord.Interaction):
        """현재 스킬 상태 표시"""
        channel_id = str(interaction.channel.id)
        channel_state = skill_manager.get_channel_state(channel_id)
        
        active_skills = channel_state.get("active_skills", {})
        special_effects = channel_state.get("special_effects", {})
        
        if not active_skills and not special_effects:
            embed = discord.Embed(
                title="🔮 스킬 상태",
                description="현재 활성화된 스킬이 없습니다.",
                color=discord.Color.gray()
            )
        else:
            embed = discord.Embed(
                title="🔮 현재 스킬 상태",
                description=f"활성화된 스킬: {len(active_skills)}개",
                color=discord.Color.green()
            )
            
            # 활성 스킬들
            if active_skills:
                skill_list = []
                for skill_name, skill_data in active_skills.items():
                    emoji = get_skill_emoji(skill_name)
                    skill_list.append(
                        f"{emoji} **{skill_name}** ({skill_data['rounds_left']}라운드)\n"
                        f"   └ 사용자: {skill_data['user_name']}"
                    )
                
                embed.add_field(
                    name="⚔️ 활성 스킬",
                    value="\n".join(skill_list),
                    inline=False
                )
            
            # 특별 효과들
            if special_effects:
                effect_list = []
                for effect_name, effect_data in special_effects.items():
                    if effect_name == "virella_bound":
                        effect_list.append(f"🌿 **속박**: {effect_data['target_name']}")
                    elif effect_name == "nixara_excluded":
                        effect_list.append(f"⚡ **시공 배제**: {effect_data['target_name']}")
                    elif effect_name == "grim_preparing":
                        effect_list.append(f"💀 **그림 준비**: {effect_data['rounds_until_activation']}라운드 후")
                    elif effect_name == "volken_eruption":
                        phase = effect_data['current_phase']
                        effect_list.append(f"🌋 **볼켄 {phase}단계**: 화산 폭발 진행중")
                
                if effect_list:
                    embed.add_field(
                        name="✨ 특별 효과",
                        value="\n".join(effect_list),
                        inline=False
                    )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

def get_skill_emoji(skill_name: str) -> str:
    """스킬별 이모지 반환"""
    emoji_map = {
        "오닉셀": "🔥", "피닉스": "🔥", "오리븐": "⚫", "카론": "🔗",
        "스카넬": "💥", "루센시아": "✨", "비렐라": "🌿", "그림": "💀",
        "닉사라": "⚡", "제룬카": "🎯", "넥시스": "⭐", "볼켄": "🌋",
        "단목": "🏹", "콜 폴드": "🎲", "황야": "⚡", "스트라보스": "⚔️"
    }
    return emoji_map.get(skill_name, "🔮")

async def setup(bot):
    """Cog 설정 (Phase 2)"""
    await bot.add_cog(SkillCog(bot))
    await bot.add_cog(SkillInfoCog(bot))
