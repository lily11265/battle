# skills/skill.py
"""
스킬 시스템 Discord 명령어
BaseSkill 기반의 통합 스킬 시스템
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

# 새로운 import 구조
from skills.heroes import (
    SKILL_MAPPING,
    SKILL_ID_MAPPING,
    get_skill_by_name,
    get_skill_by_id,
    get_all_skill_names,
    BaseSkill,
    SkillType
)
from .skill_manager import skill_manager
from .skill_effects import skill_effects
from .skill_adapter import (
    get_skill_handler,  # 호환성을 위해 유지
    get_skill_priority,
    SkillAdapter
)

logger = logging.getLogger(__name__)

@dataclass
class SkillSession:
    """스킬 세션 클래스 (BaseSkill과 연동)"""
    name: str
    user_id: str
    user_name: str
    target_id: Optional[str]
    target_name: Optional[str]
    duration: int
    channel_id: str
    activated_at: float
    skill_instance: Optional[BaseSkill] = None
    
    async def on_start(self):
        """스킬 시작 시 호출되는 이벤트"""
        try:
            # BaseSkill 인스턴스가 있으면 직접 사용
            if self.skill_instance:
                # activate 메서드는 이미 호출되었으므로 추가 초기화만
                logger.info(f"스킬 시작 이벤트 실행 완료: {self.name}")
            else:
                # 호환성을 위한 레거시 핸들러 사용
                handler = get_skill_handler(self.name)
                if handler and hasattr(handler, 'on_skill_start'):
                    await handler.on_skill_start(self.channel_id, self.user_id)
                    logger.info(f"레거시 스킬 시작 이벤트 실행: {self.name}")
                    
        except Exception as e:
            logger.error(f"스킬 시작 이벤트 오류 ({self.name}): {e}")
    
    async def on_end(self):
        """스킬 종료 시 호출되는 이벤트"""
        try:
            if self.skill_instance:
                # BaseSkill의 deactivate 메서드 호출
                self.skill_instance.deactivate()
                logger.info(f"스킬 종료 이벤트 실행 완료: {self.name}")
            else:
                handler = get_skill_handler(self.name)
                if handler and hasattr(handler, 'on_skill_end'):
                    await handler.on_skill_end(self.channel_id, self.user_id)
                    logger.info(f"레거시 스킬 종료 이벤트 실행: {self.name}")
                    
        except Exception as e:
            logger.error(f"스킬 종료 이벤트 오류 ({self.name}): {e}")
    
    def get_info(self) -> Dict[str, Any]:
        """스킬 정보 반환"""
        base_info = {
            "name": self.name,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "duration": self.duration,
            "channel_id": self.channel_id,
            "activated_at": self.activated_at
        }
        
        # BaseSkill 인스턴스가 있으면 추가 정보 포함
        if self.skill_instance:
            status = self.skill_instance.get_status()
            if status:
                base_info.update({
                    "type": self.skill_instance.skill_type.value,
                    "cooldown": self.skill_instance.current_cooldown,
                    "remaining_rounds": self.skill_instance.remaining_rounds,
                    "effect": status.get("effect", "")
                })
        
        return base_info


class SkillCog(commands.Cog):
    """스킬 시스템 명령어 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self._skill_cache: Dict[str, BaseSkill] = {}  # BaseSkill 인스턴스 캐시
        self._interaction_cache: Dict[str, datetime] = {}
        self._target_cache: Dict[str, List] = {}
        self.command_cooldowns = {}
    
    async def cog_load(self):
        """Cog 로딩 시 초기화"""
        await skill_manager.initialize()
        await skill_effects.initialize()  # skill_effects도 초기화
        await self._preload_skills()
        logger.info("SkillCog 로딩 완료")
    
    async def cog_unload(self):
        """Cog 언로드 시 정리"""
        await skill_manager.shutdown()
        self._skill_cache.clear()
        logger.info("SkillCog 언로드 완료")
    
    async def _preload_skills(self):
        """스킬 미리 로딩 (BaseSkill)"""
        for skill_name, skill_class in SKILL_MAPPING.items():
            try:
                # BaseSkill 인스턴스 생성 테스트
                instance = skill_class()
                self._skill_cache[skill_name] = instance
                logger.debug(f"스킬 로딩: {skill_name} - {instance.name}")
            except Exception as e:
                logger.error(f"스킬 로딩 실패 {skill_name}: {e}")
    
    def _get_skill_instance(self, skill_name: str) -> Optional[BaseSkill]:
        """스킬 인스턴스 가져오기"""
        if skill_name in self._skill_cache:
            # 캐시된 인스턴스의 새 복사본 생성
            skill_class = SKILL_MAPPING.get(skill_name)
            if skill_class:
                return skill_class()
        return None
    
    def _get_skill_info(self, skill_name: str) -> Dict[str, Any]:
        """스킬 정보 가져오기 (BaseSkill에서)"""
        skill_instance = self._get_skill_instance(skill_name)
        if skill_instance:
            return {
                "name": skill_instance.name,
                "type": skill_instance.skill_type.value,
                "description": skill_instance.get_description("user"),
                "cooldown": skill_instance.cooldown,
                "max_duration": skill_instance.max_duration,
                "min_duration": skill_instance.min_duration
            }
        return {"name": skill_name, "type": "unknown", "description": "정보 없음"}
    
    # === 자동완성 함수들 ===
    
    async def skill_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """스킬 이름 자동완성"""
        try:
            user_id = str(interaction.user.id)
            channel_id = str(interaction.channel.id)
            display_name = interaction.user.display_name
            
            # 사용 가능한 스킬 목록
            if skill_manager.is_admin(user_id, display_name):
                available_skills = get_all_skill_names()
            else:
                available_skills = skill_manager.get_user_allowed_skills(user_id)
                
                # 특별 제한 스킬 체크
                if "넥시스" in available_skills and user_id != "1059908946741166120":
                    available_skills.remove("넥시스")
            
            # 이미 활성화된 스킬 제외
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = set(channel_state.get("active_skills", {}).keys())
            
            # 사용자가 이미 사용 중인 스킬 확인
            user_active_skill = None
            for skill_name, skill_data in channel_state.get("active_skills", {}).items():
                if skill_data.get("user_id") == user_id:
                    user_active_skill = skill_name
                    break
            
            # 필터링
            filtered_skills = []
            for skill in available_skills:
                if skill not in active_skills:
                    if not current or current.lower() in skill.lower():
                        filtered_skills.append(skill)
            
            # Choice 객체 생성
            choices = []
            for skill in filtered_skills[:25]:
                skill_info = self._get_skill_info(skill)
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
    
    async def target_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """대상 자동완성"""
        try:
            if not interaction.guild:
                return []
            
            choices = []
            
            # 특수 대상들
            special_targets = ["all_users", "all_monsters", "random"]
            for target in special_targets:
                if not current or current.lower() in target.lower():
                    choices.append(app_commands.Choice(name=f"🎯 {target}", value=target))
            
            # 서버 멤버들
            member_count = 0
            for member in interaction.guild.members:
                if member.bot:
                    continue
                
                display_name = member.display_name
                if not current or current.lower() in display_name.lower():
                    choices.append(
                        app_commands.Choice(
                            name=f"👤 {display_name}",
                            value=str(member.id)
                        )
                    )
                    member_count += 1
                    
                    if member_count >= 20:
                        break
            
            return choices[:25]
            
        except Exception as e:
            logger.error(f"대상 자동완성 오류: {e}")
            return []
    
    async def cancel_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """취소할 스킬 자동완성 (Admin 전용)"""
        try:
            user_id = str(interaction.user.id)
            display_name = interaction.user.display_name
            
            if not skill_manager.is_admin(user_id, display_name):
                return []
            
            channel_id = str(interaction.channel.id)
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            
            choices = []
            for skill_name, skill_data in active_skills.items():
                if not current or current.lower() in skill_name.lower():
                    display = f"{skill_name} (사용자: {skill_data.get('user_name', 'Unknown')})"
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
            
            # 취소 옵션 처리
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
            is_admin = skill_manager.is_admin(user_id, display_name)
            channel_state = skill_manager.get_channel_state(channel_id)
            battle_active = channel_state.get("battle_active", False)
            
            # Admin이면서 몹 전투가 진행 중인 경우 자동 활성화
            if is_admin and not battle_active:
                mob_battle_active = await self._check_and_activate_mob_battle(channel_id)
                if mob_battle_active:
                    battle_active = True
                    logger.info(f"Admin 스킬 사용으로 몹 전투 스킬 시스템 자동 활성화")
            
            # 일반 사용자는 전투 상태 필수
            if not is_admin and not battle_active:
                await interaction.response.send_message(
                    "❌ 현재 전투가 진행되지 않습니다.",
                    ephemeral=True
                )
                return
            
            # 권한 확인
            if not skill_manager.can_use_skill(user_id, 영웅, display_name):
                available_skills = skill_manager.get_user_allowed_skills(user_id) if not is_admin else get_all_skill_names()
                
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬을 사용할 권한이 없습니다.\n\n"
                    f"**사용 가능한 스킬**: {', '.join(available_skills[:10])}{'...' if len(available_skills) > 10 else ''}",
                    ephemeral=True
                )
                return
            
            # BaseSkill 인스턴스 가져오기
            skill_instance = self._get_skill_instance(영웅)
            if not skill_instance:
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬을 찾을 수 없습니다.",
                    ephemeral=True
                )
                return
            
            # 중복 스킬 체크
            active_skills = channel_state.get("active_skills", {})
            
            if 영웅 in active_skills:
                existing_data = active_skills[영웅]
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬이 이미 활성화되어 있습니다.\n"
                    f"**사용자**: {existing_data.get('user_name', 'Unknown')}\n"
                    f"**남은 라운드**: {existing_data.get('rounds_left', 0)}",
                    ephemeral=True
                )
                return
            
            # 사용자가 이미 다른 스킬 사용 중인지 확인
            for skill_name, skill_data in active_skills.items():
                if skill_data.get("user_id") == user_id:
                    await interaction.response.send_message(
                        f"❌ 이미 **{skill_name}** 스킬을 사용 중입니다.\n"
                        f"한 번에 하나의 스킬만 사용할 수 있습니다.",
                        ephemeral=True
                    )
                    return
            
            # 응답 지연 처리
            await interaction.response.defer()
            
            try:
                # 몹 전투 중 Admin 스킬 처리
                if is_admin and channel_state.get("battle_type") == "mob_battle":
                    actual_user_id = channel_state.get("mob_name", "monster")
                    actual_user_name = channel_state.get("mob_name", "몬스터")
                    caster_type = "monster"
                else:
                    actual_user_id = user_id
                    actual_user_name = display_name
                    caster_type = "user"
                
                # skill_effects를 통해 스킬 활성화
                result = await skill_effects.process_skill_activation(
                    channel_id=channel_id,
                    skill_name=영웅,
                    user_id=actual_user_id,
                    target_id=대상,
                    duration=라운드
                )
                
                if result.get("success"):
                    # 성공 메시지
                    success_embed = discord.Embed(
                        title=f"⚔️ {영웅} 스킬 발동!",
                        description=result.get("message", f"**{display_name}**님이 **{영웅}**의 힘을 빌렸습니다!"),
                        color=discord.Color.gold()
                    )
                    
                    # 스킬 정보 추가
                    skill_info = skill_instance.get_info()
                    success_embed.add_field(
                        name="📊 스킬 정보",
                        value=f"**타입**: {skill_info.get('type', 'Unknown')}\n"
                              f"**지속 시간**: {라운드} 라운드\n"
                              f"**효과**: {result.get('effect', skill_info.get('description', ''))}",
                        inline=False
                    )
                    
                    if 대상:
                        success_embed.add_field(
                            name="🎯 대상",
                            value=대상,
                            inline=True
                        )
                    
                    # 몹 전투 정보
                    if channel_state.get("battle_type") == "mob_battle":
                        mob_name = channel_state.get("mob_name", "몹")
                        success_embed.add_field(
                            name="⚔️ 전투 정보",
                            value=f"**몹 전투**: {mob_name}\n**Admin 스킬**: ✅",
                            inline=True
                        )
                    
                    success_embed.set_footer(text=f"스킬은 {라운드} 라운드 동안 지속됩니다.")
                    
                    await interaction.followup.send(embed=success_embed)
                    
                    # 스킬 세션 생성 및 시작 이벤트
                    session = SkillSession(
                        name=영웅,
                        user_id=actual_user_id,
                        user_name=actual_user_name,
                        target_id=대상,
                        target_name=대상 or "전체",
                        duration=라운드,
                        channel_id=channel_id,
                        activated_at=datetime.now().timestamp(),
                        skill_instance=skill_instance
                    )
                    await session.on_start()
                    
                    logger.info(f"스킬 활성화 성공 - 사용자: {display_name}, 스킬: {영웅}, 라운드: {라운드}")
                    
                else:
                    # 실패 메시지
                    error_message = result.get("message", "스킬 활성화에 실패했습니다.")
                    await interaction.followup.send(f"❌ {error_message}")
                    
            except Exception as e:
                logger.error(f"스킬 활성화 처리 오류: {e}")
                await interaction.followup.send(
                    f"❌ 스킬 처리 중 오류가 발생했습니다: {str(e)[:100]}"
                )
                
        except Exception as e:
            logger.error(f"스킬 명령어 오류: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "❌ 스킬 사용 중 오류가 발생했습니다.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ 스킬 사용 중 오류가 발생했습니다.",
                        ephemeral=True
                    )
            except:
                pass
    
    # === 보조 메서드들 ===
    
    async def _check_and_activate_mob_battle(self, channel_id: str) -> bool:
        """몹 전투 상태 확인 및 스킬 시스템 자동 활성화"""
        try:
            if hasattr(self.bot, 'mob_battles'):
                channel_id_int = int(channel_id)
                
                if channel_id_int in self.bot.mob_battles:
                    battle = self.bot.mob_battles[channel_id_int]
                    
                    if battle.is_active:
                        channel_state = skill_manager.get_channel_state(channel_id)
                        channel_state["battle_active"] = True
                        channel_state["battle_type"] = "mob_battle"
                        channel_state["mob_name"] = battle.mob_name
                        channel_state["admin_can_use_skills"] = True
                        
                        await skill_manager._save_skill_states()
                        
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"몹 전투 상태 확인 오류: {e}")
            return False
    
    async def _check_cooldown(self, interaction: discord.Interaction) -> bool:
        """중복 실행 방지 쿨다운 체크"""
        user_id = str(interaction.user.id)
        current_time = datetime.now().timestamp()
        
        # 3초 쿨다운
        if user_id in self.command_cooldowns:
            last_used = self.command_cooldowns[user_id]
            if current_time - last_used < 3:
                await interaction.response.send_message(
                    "❌ 스킬 명령어는 3초마다 사용할 수 있습니다.",
                    ephemeral=True
                )
                return False
        
        self.command_cooldowns[user_id] = current_time
        return True
    
    async def _handle_skill_cancel(self, interaction: discord.Interaction, skill_name: str):
        """스킬 취소 처리 (ADMIN 전용)"""
        try:
            channel_id = str(interaction.channel.id)
            channel_state = skill_manager.get_channel_state(channel_id)
            
            if skill_name not in channel_state.get("active_skills", {}):
                await interaction.response.send_message(
                    f"❌ **{skill_name}** 스킬이 활성화되어 있지 않습니다.",
                    ephemeral=True
                )
                return
            
            # 스킬 정보 가져오기
            skill_data = channel_state["active_skills"][skill_name]
            original_user = skill_data.get("user_name", "Unknown")
            
            # skill_effects를 통해 스킬 인스턴스 가져오기
            skill_instance = skill_effects.get_skill_instance(channel_id, skill_name)
            if skill_instance:
                # BaseSkill의 deactivate 메서드 호출
                skill_instance.deactivate()
            
            # 스킬 비활성화
            success = await skill_manager.deactivate_skill(channel_id, skill_name)
            
            if success:
                cancel_embed = discord.Embed(
                    title="🚫 스킬 강제 취소",
                    description=f"**Admin**이 **{skill_name}** 스킬을 취소했습니다.",
                    color=discord.Color.orange()
                )
                
                cancel_embed.add_field(
                    name="📋 취소된 스킬 정보",
                    value=f"**스킬**: {skill_name}\n"
                          f"**원래 사용자**: {original_user}\n"
                          f"**취소자**: {interaction.user.display_name}",
                    inline=False
                )
                
                await interaction.response.send_message(embed=cancel_embed)
                
                logger.info(f"Admin 스킬 취소 - 스킬: {skill_name}, 취소자: {interaction.user.display_name}")
            else:
                await interaction.response.send_message(
                    f"❌ **{skill_name}** 스킬 취소에 실패했습니다.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"스킬 취소 처리 오류: {e}")
            await interaction.response.send_message(
                "❌ 스킬 취소 중 오류가 발생했습니다.",
                ephemeral=True
            )


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
    async def select_target(self, interaction: discord.Interaction, select: discord.ui.Select):
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
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """확인 버튼"""
        self.confirmed = True
        await interaction.response.send_message("✅ 스킬 사용을 확인했습니다.", ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """취소 버튼"""
        self.confirmed = False
        await interaction.response.send_message("❌ 스킬 사용을 취소했습니다.", ephemeral=True)
        self.stop()


async def setup(bot):
    """Cog 설정"""
    await bot.add_cog(SkillCog(bot))