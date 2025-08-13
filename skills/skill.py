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
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
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

@dataclass
class Skill:
    """개별 스킬 클래스"""
    name: str
    user_id: str
    user_name: str
    target_id: str
    target_name: str
    duration: int
    channel_id: str
    activated_at: float = 0
    
    async def on_start(self):
        """스킬 시작 시 호출되는 이벤트"""
        try:
            from skills.heroes import get_skill_handler
            handler = get_skill_handler(self.name)
            
            if handler:
                # on_skill_start 메서드가 있으면 호출
                if hasattr(handler, 'on_skill_start'):
                    await handler.on_skill_start(self.channel_id, self.user_id)
                    logger.info(f"스킬 시작 이벤트 실행 완료: {self.name}")
                else:
                    logger.debug(f"스킬 {self.name}에 on_skill_start 메서드 없음")
            else:
                logger.warning(f"스킬 핸들러를 찾을 수 없음: {self.name}")
                
        except Exception as e:
            logger.error(f"스킬 시작 이벤트 오류 ({self.name}): {e}")
            # 오류가 발생해도 스킬 활성화는 계속됨
    
    async def on_end(self):
        """스킬 종료 시 호출되는 이벤트"""
        try:
            from skills.heroes import get_skill_handler
            handler = get_skill_handler(self.name)
            
            if handler:
                # on_skill_end 메서드가 있으면 호출
                if hasattr(handler, 'on_skill_end'):
                    await handler.on_skill_end(self.channel_id, self.user_id)
                    logger.info(f"스킬 종료 이벤트 실행 완료: {self.name}")
                else:
                    logger.debug(f"스킬 {self.name}에 on_skill_end 메서드 없음")
            else:
                logger.warning(f"스킬 핸들러를 찾을 수 없음: {self.name}")
                
        except Exception as e:
            logger.error(f"스킬 종료 이벤트 오류 ({self.name}): {e}")
    
    def get_info(self) -> Dict[str, Any]:
        """스킬 정보 반환"""
        return {
            "name": self.name,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "duration": self.duration,
            "channel_id": self.channel_id,
            "activated_at": self.activated_at
        }
    
    def __str__(self) -> str:
        """문자열 표현"""
        return f"Skill({self.name} by {self.user_name} -> {self.target_name}, {self.duration} rounds)"
    
    def __repr__(self) -> str:
        """개발자용 표현"""
        return (f"Skill(name='{self.name}', user_id='{self.user_id}', "
                f"target_id='{self.target_id}', duration={self.duration})")

class SkillCog(commands.Cog):
    """스킬 시스템 명령어 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self._skill_handlers: Dict = {}
        self._interaction_cache: Dict[str, datetime] = {}  # 중복 실행 방지
        self._target_cache: Dict[str, List] = {}  # 대상 목록 캐시
        self.command_cooldowns = {} 

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
    
    async def skill_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """스킬 이름 자동완성"""
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
            
            # 서버 멤버들 (최대 20명)
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
                    
                    if member_count >= 20:  # 최대 20명으로 제한
                        break
            
            return choices[:25]  # Discord 제한
            
        except Exception as e:
            logger.error(f"대상 자동완성 오류: {e}")
            return []
        
    async def cancel_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """취소할 스킬 자동완성 (Admin 전용)"""
        try:
            user_id = str(interaction.user.id)
            display_name = interaction.user.display_name
            
            # Admin 권한 체크
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
        """스킬 명령어 메인 처리 (몹 전투 완전 통합)"""
        try:
            # === 중복 실행 방지 ===
            if not await self._check_cooldown(interaction):
                return
            
            user_id = str(interaction.user.id)
            channel_id = str(interaction.channel.id)
            display_name = interaction.user.display_name
            
            # === 취소 옵션 처리 (ADMIN 전용) ===
            if 취소:
                if not skill_manager.is_admin(user_id, display_name):
                    await interaction.response.send_message(
                        "❌ 스킬 취소는 ADMIN만 가능합니다.",
                        ephemeral=True
                    )
                    return
                
                await self._handle_skill_cancel(interaction, 취소)
                return
            
            # === 전투 상태 확인 및 자동 활성화 ===
            is_admin = skill_manager.is_admin(user_id, display_name)
            channel_state = skill_manager.get_channel_state(channel_id)
            battle_active = channel_state.get("battle_active", False)
            
            # Admin이면서 몹 전투가 진행 중인 경우 자동 활성화
            if is_admin and not battle_active:
                mob_battle_active = await self._check_and_activate_mob_battle(channel_id)
                if mob_battle_active:
                    battle_active = True
                    logger.info(f"Admin 스킬 사용으로 몹 전투 스킬 시스템 자동 활성화 - 채널: {channel_id}")
            
            # 일반 사용자는 전투 상태 필수
            if not is_admin and not battle_active:
                await interaction.response.send_message(
                    "❌ 현재 전투가 진행되지 않습니다.",
                    ephemeral=True
                )
                return
            
            # === 권한 확인 ===
            if not skill_manager.can_use_skill(user_id, 영웅, display_name):
                available_skills = skill_manager.get_user_allowed_skills(user_id) if not is_admin else list(SKILL_MODULE_MAP.keys())
                
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬을 사용할 권한이 없습니다.\n\n"
                    f"**사용 가능한 스킬**: {', '.join(available_skills[:10])}{'...' if len(available_skills) > 10 else ''}",
                    ephemeral=True
                )
                return
            
            # === 중복 스킬 체크 ===
            active_skills = channel_state["active_skills"]
            
            # 이미 활성화된 스킬인지 확인
            if 영웅 in active_skills:
                existing_user = active_skills[영웅]["user_name"]
                remaining_rounds = active_skills[영웅]["rounds_left"]
                
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬이 이미 활성화되어 있습니다.\n"
                    f"**사용자**: {existing_user}\n"
                    f"**남은 라운드**: {remaining_rounds}",
                    ephemeral=True
                )
                return
            
            # 사용자가 이미 다른 스킬을 사용 중인지 확인
            user_active_skill = None
            for skill_name, skill_data in active_skills.items():
                if skill_data["user_id"] == user_id:
                    user_active_skill = skill_name
                    break
            
            if user_active_skill:
                await interaction.response.send_message(
                    f"❌ 이미 **{user_active_skill}** 스킬을 사용 중입니다.\n"
                    f"한 번에 하나의 스킬만 사용할 수 있습니다.",
                    ephemeral=True
                )
                return
            
            # === 스킬 핸들러 가져오기 ===
            handler = get_skill_handler(영웅)
            if not handler:
                await interaction.response.send_message(
                    f"❌ **{영웅}** 스킬을 찾을 수 없습니다.\n"
                    f"올바른 영웅 이름을 입력해주세요.",
                    ephemeral=True
                )
                return
            
            # === 응답 지연 처리 ===
            await interaction.response.defer()
            
            try:
                # === 몹 전투 중 Admin 스킬 처리 === ← 여기에 추가!
                # Admin이면서 몹 전투가 진행 중인 경우 몬스터에게 스킬 적용
                if is_admin and channel_state.get("battle_type") == "mob_battle":
                    # 실제 몹 이름을 사용
                    actual_user_id = channel_state.get("mob_name", "monster")  # "monster" 대신 실제 몹 이름
                    actual_user_name = channel_state.get("mob_name", "몬스터")
                    
                    logger.info(f"몹 전투 중 Admin 스킬 - {영웅} 스킬을 {actual_user_name}(ID: {actual_user_id})에게 적용")
                else:
                    actual_user_id = user_id
                    actual_user_name = display_name
                
                # === 스킬 활성화 ===
                success = await skill_manager.activate_skill(
                    user_id=actual_user_id,  # 몹 전투 시 "monster"로 변경됨
                    user_name=actual_user_name,
                    skill_name=영웅,
                    channel_id=channel_id,
                    duration_rounds=라운드,
                    target=대상
                )
                
                if success:
                    # === 스킬 정보 가져오기 ===
                    skill_info = get_skill_info(영웅)
                    
                    # === 성공 메시지 ===
                    success_embed = discord.Embed(
                        title=f"⚔️ {영웅} 스킬 발동!",
                        description=f"**{display_name}**님이 **{영웅}**의 힘을 빌렸습니다!",
                        color=discord.Color.gold()
                    )
                    
                    success_embed.add_field(
                        name="📊 스킬 정보",
                        value=f"**타입**: {skill_info.get('type', 'Unknown')}\n"
                              f"**지속 시간**: {라운드} 라운드\n"
                              f"**설명**: {skill_info.get('description', '정보 없음')}",
                        inline=False
                    )
                    
                    if 대상:
                        success_embed.add_field(
                            name="🎯 대상",
                            value=대상,
                            inline=True
                        )
                    
                    # 전투 타입별 추가 정보
                    battle_type = channel_state.get("battle_type")
                    if battle_type == "mob_battle":
                        mob_name = channel_state.get("mob_name", "몹")
                        success_embed.add_field(
                            name="⚔️ 전투 정보",
                            value=f"**몹 전투**: {mob_name}\n**Admin 스킬**: ✅",
                            inline=True
                        )
                    
                    success_embed.set_footer(text=f"스킬은 {라운드} 라운드 동안 지속됩니다.")
                    
                    await interaction.followup.send(embed=success_embed)
                    
                    # === 스킬 시작 이벤트 호출 ===
                    try:
                        # 몹 전투 중 Admin 스킬인 경우 actual_user_id 전달
                        await handler.on_skill_start(channel_id, actual_user_id, 라운드)  # user_id 대신 actual_user_id
                    except Exception as e:
                        logger.error(f"스킬 시작 이벤트 오류 ({영웅}): {e}")
                    
                    logger.info(f"스킬 활성화 성공 - 사용자: {display_name}, 스킬: {영웅}, 라운드: {라운드}, 채널: {channel_id}")
                    
                else:
                    await interaction.followup.send(
                        f"❌ **{영웅}** 스킬 활성화에 실패했습니다.\n"
                        f"잠시 후 다시 시도해주세요."
                    )
                    
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
            # main.py의 bot 인스턴스에서 mob_battles 확인
            if hasattr(self.bot, 'mob_battles'):
                channel_id_int = int(channel_id)
                
                if channel_id_int in self.bot.mob_battles:
                    battle = self.bot.mob_battles[channel_id_int]
                    
                    # 전투가 활성화되어 있는지 확인
                    if battle.is_active:
                        # 스킬 시스템 자동 활성화
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
            
            if skill_name not in channel_state["active_skills"]:
                await interaction.response.send_message(
                    f"❌ **{skill_name}** 스킬이 활성화되어 있지 않습니다.",
                    ephemeral=True
                )
                return
            
            # 스킬 정보 가져오기
            skill_data = channel_state["active_skills"][skill_name]
            original_user = skill_data["user_name"]
            
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

async def setup(bot):
    await bot.add_cog(SkillCog(bot))



