# skills/skill.py
"""
스킬 시스템 Discord 명령어
/스킬 명령어의 완전한 구현
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from .skill_manager import skill_manager
from .skill_effects import skill_effects
from .heroes import (
    get_skill_handler, 
    get_all_available_skills,
    get_skill_info,
    validate_skill_target,
    SKILL_MODULE_MAP
)

logger = logging.getLogger(__name__)

class SkillCog(commands.Cog):
    """스킬 시스템 명령어 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self._skill_handlers: Dict = {}
        self._interaction_cache: Dict[str, datetime] = {}  # 중복 실행 방지
        self._target_cache: Dict[str, List] = {}  # 대상 목록 캐시
    
    async def cog_load(self):
        """Cog 로딩 시 초기화"""
        await skill_manager.initialize()
        await self._preload_skill_handlers()
        logger.info("SkillCog 로딩 완료")
    
    async def cog_unload(self):
        """Cog 언로드 시 정리"""
        await skill_manager.shutdown()
        logger.info("SkillCog 언로드 완료")
    
    async def _preload_skill_handlers(self):
        """스킬 핸들러 미리 로딩"""
        for skill_name in SKILL_MODULE_MAP.keys():
            try:
                handler = get_skill_handler(skill_name)
                if handler:
                    self._skill_handlers[skill_name] = handler
                    logger.debug(f"스킬 핸들러 로딩: {skill_name}")
            except Exception as e:
                logger.error(f"스킬 핸들러 로딩 실패 {skill_name}: {e}")
    
    # === 자동완성 함수들 ===
    
    async def skill_autocomplete(self, interaction: discord.Interaction, 
                                current: str) -> List[app_commands.Choice[str]]:
        """스킬 자동완성"""
        try:
            user_id = str(interaction.user.id)
            channel_id = str(interaction.channel.id)
            display_name = interaction.user.display_name
            
            # 사용 가능한 스킬 목록 가져오기
            if skill_manager.is_admin(user_id, display_name):
                available_skills = list(SKILL_MODULE_MAP.keys())
            else:
                available_skills = skill_manager.get_user_allowed_skills(user_id)
                
                # 특별 제한 스킬 체크
                if "넥시스" in available_skills and user_id != "1059908946741166120":
                    available_skills.remove("넥시스")
            
            # 이미 활성화된 스킬 제외
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = set(channel_state["active_skills"].keys())
            
            # 사용자가 이미 사용 중인 스킬 확인
            user_active_skill = None
            for skill_name, skill_data in channel_state["active_skills"].items():
                if skill_data["user_id"] == user_id:
                    user_active_skill = skill_name
                    break
            
            # 필터링
            filtered_skills = []
            for skill in available_skills:
                if skill not in active_skills:  # 필드에 없는 스킬만
                    if not current or current.lower() in skill.lower():
                        filtered_skills.append(skill)
            
            # Choice 객체 생성 (최대 25개)
            choices = []
            for skill in filtered_skills[:25]:
                skill_info = get_skill_info(skill)
                description = f"[{skill_info.get('type', 'unknown')}]"
                
                if user_active_skill:
                    description += f" ⚠️ 현재 {user_active_skill} 사용 중"
                
                choices.append(
                    app_commands.Choice(
                        name=f"{skill} {description}",
                        value=skill
                    )
                )
            
            return choices
            
        except Exception as e:
            logger.error(f"스킬 자동완성 오류: {e}")
            return []
    
    async def target_autocomplete(self, interaction: discord.Interaction,
                                current: str) -> List[app_commands.Choice[str]]:
        """대상 자동완성"""
        try:
            # 선택된 스킬 확인
            skill_name = None
            for option in interaction.data.get("options", []):
                if option["name"] == "영웅":
                    skill_name = option["value"]
                    break
            
            if not skill_name:
                return []
            
            skill_info = get_skill_info(skill_name)
            if not skill_info.get("needs_target"):
                return [app_commands.Choice(name="대상 선택 불필요", value="self")]
            
            # 대상 목록 가져오기
            targets = await self._get_available_targets(interaction, skill_name)
            
            # 필터링 및 Choice 생성
            choices = []
            for target in targets[:25]:
                if not current or current.lower() in target["name"].lower():
                    choices.append(
                        app_commands.Choice(
                            name=target["display"],
                            value=target["id"]
                        )
                    )
            
            return choices
            
        except Exception as e:
            logger.error(f"대상 자동완성 오류: {e}")
            return []
    
    async def cancel_autocomplete(self, interaction: discord.Interaction,
                                current: str) -> List[app_commands.Choice[str]]:
        """취소할 스킬 자동완성 (ADMIN 전용)"""
        try:
            user_id = str(interaction.user.id)
            display_name = interaction.user.display_name
            
            # ADMIN 체크
            if not skill_manager.is_admin(user_id, display_name):
                return []
            
            channel_id = str(interaction.channel.id)
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state["active_skills"]
            
            choices = []
            for skill_name, skill_data in active_skills.items():
                if not current or current.lower() in skill_name.lower():
                    display = f"{skill_name} (사용자: {skill_data['user_name']})"
                    choices.append(
                        app_commands.Choice(name=display, value=skill_name)
                    )
            
            return choices[:25]
            
        except Exception as e:
            logger.error(f"취소 자동완성 오류: {e}")
            return []
    
    # === 메인 명령어 ===
    
    @app_commands.command(name="스킬", description="영웅의 힘을 빌려 전투합니다")
    @app_commands.describe(
        영웅="사용할 영웅 스킬",
        라운드="스킬 지속 라운드 (1-10)",
        대상="스킬 대상 (필요한 경우)",
        취소="취소할 스킬 (ADMIN 전용)"
    )
    @app_commands.autocomplete(
        영웅=skill_autocomplete,
        대상=target_autocomplete,
        취소=cancel_autocomplete
    )
    @app_commands.guild_only()
    async def skill_command(
        self,
        interaction: discord.Interaction,
        영웅: str,
        라운드: app_commands.Range[int, 1, 10],
        대상: Optional[str] = None,
        취소: Optional[str] = None
    ):
        """스킬 명령어 메인 처리"""
        try:
            # 중복 실행 방지
            if not await self._check_cooldown(interaction):
                return
            
            user_id = str(interaction.user.id)
            channel_id = str(interaction.channel.id)
            display_name = interaction.user.display_name
            
            # 취소 옵션 처리 (ADMIN 전용)
            if 취소:
                if not skill_manager.is_admin(user_id, display_name):
                    await interaction.response.send_message(
                        "❌ 스킬 취소는 ADMIN만 가능합니다.",
                        ephemeral=True
                    )
                    return
                
                await self._handle_skill_cancel(interaction, 취소)
                return
            
            # 전투 상태 확인
            channel_state = skill_manager.get_channel_state(channel_id)
            if not channel_state.get("battle_active", True):  # 기본값 True (테스트용)
                # 실제로는 battle_admin과 연동하여 확인
                pass
            
            # 권한 확인
            if not skill_manager.can_use_skill(user_id, 영웅, display_name):
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬을 사용할 권한이 없습니다.",
                    ephemeral=True
                )
                return
            
            # 스킬 핸들러 가져오기
            handler = get_skill_handler(영웅)
            if not handler:
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬을 찾을 수 없습니다.",
                    ephemeral=True
                )
                return
            
            # 대상 처리
            target_id = 대상
            target_name = "자기 자신"
            
            if handler.needs_target:
                if not 대상 or 대상 == "self":
                    # 대상 선택 필요
                    await self._show_target_selection(interaction, 영웅, 라운드)
                    return
                
                target_info = await self._get_target_info(interaction, 대상)
                if target_info:
                    target_name = target_info["name"]
            
            # 중요 스킬 확인창
            if 영웅 in ["그림", "넥시스", "볼켄"]:
                confirmed = await self._show_confirmation(interaction, 영웅)
                if not confirmed:
                    return
            
            # 스킬 활성화
            success = skill_manager.add_skill(
                channel_id, 영웅, user_id, display_name,
                target_id, target_name, 라운드
            )
            
            if not success:
                await interaction.response.send_message(
                    f"❌ 스킬 활성화 실패. 이미 같은 스킬이 사용 중이거나 다른 스킬을 사용 중입니다.",
                    ephemeral=True
                )
                return
            
            # 스킬 효과 처리
            await skill_effects.process_skill_activation(
                channel_id, 영웅, user_id, target_id, 라운드
            )
            
            # 스킬 활성화 메시지
            await handler.activate(interaction, target_id, 라운드)
            
            # 공개 메시지
            embed = self._create_skill_embed(영웅, display_name, target_name, 라운드)
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)
            
            logger.info(f"스킬 활성화: {영웅} by {display_name} in {channel_id}")
            
        except Exception as e:
            logger.error(f"스킬 명령어 처리 실패: {e}", exc_info=True)
            
            error_msg = "❌ 스킬 처리 중 오류가 발생했습니다."
            if interaction.response.is_done():
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
    
    # === 보조 메서드들 ===
    
    async def _check_cooldown(self, interaction: discord.Interaction) -> bool:
        """중복 실행 방지 (3초)"""
        user_id = str(interaction.user.id)
        now = datetime.now()
        
        if user_id in self._interaction_cache:
            last_time = self._interaction_cache[user_id]
            if (now - last_time).total_seconds() < 3:
                await interaction.response.send_message(
                    "⏱️ 잠시 후 다시 시도해주세요.",
                    ephemeral=True
                )
                return False
        
        self._interaction_cache[user_id] = now
        return True
    
    async def _handle_skill_cancel(self, interaction: discord.Interaction, skill_name: str):
        """스킬 취소 처리"""
        try:
            channel_id = str(interaction.channel.id)
            
            if skill_manager.remove_skill(channel_id, skill_name):
                await interaction.response.send_message(
                    f"✅ **{skill_name}** 스킬이 취소되었습니다.",
                    ephemeral=False
                )
            else:
                await interaction.response.send_message(
                    f"❌ **{skill_name}** 스킬을 찾을 수 없습니다.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"스킬 취소 실패: {e}")
            await interaction.response.send_message(
                "❌ 스킬 취소 중 오류가 발생했습니다.",
                ephemeral=True
            )
    
    async def _get_available_targets(self, interaction: discord.Interaction,
                                    skill_name: str) -> List[Dict]:
        """사용 가능한 대상 목록"""
        targets = []
        
        try:
            # 유저 목록
            guild = interaction.guild
            if guild:
                for member in guild.members:
                    if not member.bot:
                        targets.append({
                            "id": str(member.id),
                            "name": member.display_name,
                            "display": f"👤 {member.display_name}",
                            "type": "user"
                        })
            
            # 몬스터/ADMIN 추가 (실제로는 battle_admin과 연동)
            targets.append({
                "id": "monster",
                "name": "현재 몬스터",
                "display": "👾 현재 몬스터",
                "type": "monster"
            })
            
            # 전체 대상 (카론 등)
            if skill_name in ["카론", "오리븐"]:
                targets.insert(0, {
                    "id": "all_users",
                    "name": "모든 유저",
                    "display": "👥 모든 유저",
                    "type": "all"
                })
            
        except Exception as e:
            logger.error(f"대상 목록 가져오기 실패: {e}")
        
        return targets
    
    async def _get_target_info(self, interaction: discord.Interaction,
                              target_id: str) -> Optional[Dict]:
        """대상 정보 조회"""
        try:
            if target_id == "monster":
                return {"id": "monster", "name": "몬스터", "type": "monster"}
            elif target_id == "all_users":
                return {"id": "all_users", "name": "모든 유저", "type": "all"}
            else:
                guild = interaction.guild
                if guild:
                    member = guild.get_member(int(target_id))
                    if member:
                        return {
                            "id": str(member.id),
                            "name": member.display_name,
                            "type": "user"
                        }
        except Exception as e:
            logger.error(f"대상 정보 조회 실패: {e}")
        
        return None
    
    async def _show_target_selection(self, interaction: discord.Interaction,
                                    skill_name: str, duration: int):
        """대상 선택 UI 표시"""
        # View 생성
        view = TargetSelectionView(self, skill_name, duration)
        
        await interaction.response.send_message(
            f"**{skill_name}** 스킬의 대상을 선택해주세요:",
            view=view,
            ephemeral=True
        )
    
    async def _show_confirmation(self, interaction: discord.Interaction,
                                skill_name: str) -> bool:
        """중요 스킬 확인창"""
        view = ConfirmationView()
        
        await interaction.response.send_message(
            f"⚠️ **{skill_name}** 스킬을 정말 사용하시겠습니까?\n"
            "이 행동은 되돌릴 수 없습니다.",
            view=view,
            ephemeral=True
        )
        
        await view.wait()
        return view.confirmed
    
    def _create_skill_embed(self, skill_name: str, user_name: str,
                          target_name: str, duration: int) -> discord.Embed:
        """스킬 활성화 임베드 생성"""
        skill_info = get_skill_info(skill_name)
        
        embed = discord.Embed(
            title=f"🔮 {skill_name} 스킬 발동!",
            description=f"**{user_name}**님이 **{skill_name}**의 힘을 발동시켰습니다!",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="📊 대상", value=target_name, inline=True)
        embed.add_field(name="⏱️ 지속시간", value=f"{duration}라운드", inline=True)
        embed.add_field(name="🎯 타입", value=skill_info.get("type", "unknown"), inline=True)
        
        embed.set_footer(text="영웅의 힘이 전장을 지배합니다")
        
        return embed

# === UI 컴포넌트들 ===

class TargetSelectionView(discord.ui.View):
    """대상 선택 View"""
    
    def __init__(self, cog: SkillCog, skill_name: str, duration: int):
        super().__init__(timeout=30)
        self.cog = cog
        self.skill_name = skill_name
        self.duration = duration
        self.selected_target = None
    
    @discord.ui.select(
        placeholder="대상을 선택하세요",
        min_values=1,
        max_values=1
    )
    async def select_target(self, interaction: discord.Interaction,
                          select: discord.ui.Select):
        """대상 선택 처리"""
        self.selected_target = select.values[0]
        
        # 스킬 활성화 재시도
        await self.cog.skill_command(
            interaction, self.skill_name, self.duration,
            self.selected_target, None
        )
        
        self.stop()

class ConfirmationView(discord.ui.View):
    """확인 View"""
    
    def __init__(self):
        super().__init__(timeout=15)
        self.confirmed = False
    
    @discord.ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        """확인 버튼"""
        self.confirmed = True
        await interaction.response.send_message("✅ 스킬 사용을 확인했습니다.", ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        """취소 버튼"""
        self.confirmed = False
        await interaction.response.send_message("❌ 스킬 사용을 취소했습니다.", ephemeral=True)
        self.stop()

# Cog 등록 함수
async def setup(bot):
    """Cog 등록"""
    await bot.add_cog(SkillCog(bot))
