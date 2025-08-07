# skills/heroes/grim.py
import discord
import logging
import random
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class GrimHandler(BaseSkillHandler):
    """그림 스킬 핸들러
    
    단계:
    1. 1턴 준비 (스킬 사용 다음 라운드에 발동)
    2. 체력이 가장 낮은 유저 확정 사망 (주사위 1000)
    
    방어: 피닉스 스킬로만 방어 가능
    """
    
    def __init__(self):
        super().__init__("그림", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        # 확인창 표시
        view = GrimConfirmView(interaction.user, duration)
        
        embed = discord.Embed(
            title="💀 그림의 죽음 선고",
            description="**경고: 매우 위험한 스킬입니다!**\n\n"
                       "이 스킬을 사용하면 다음 라운드에 가장 약한 대상이 확정적으로 사망합니다.\n"
                       "**피닉스 스킬**로만 방어할 수 있습니다.",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="⚠️ 스킬 효과",
            value="• **1라운드 준비**: 사용 즉시 준비 상태 돌입\n"
                  "• **2라운드 발동**: 체력이 가장 낮은 대상 즉사\n"
                  "• **방어 불가**: 피닉스 스킬로만 방어 가능\n"
                  "• **되돌릴 수 없음**: 사용 후 취소 불가능",
            inline=False
        )
        
        embed.add_field(
            name="🎯 타겟 우선순위",
            value="1. 체력이 가장 낮은 유저\n"
                  "2. 동률 시: 특별 유저 중 스킬 미사용자\n" 
                  "3. 그래도 동률 시: 랜덤 선택",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class GrimConfirmView(discord.ui.View):
    """그림 스킬 확인 뷰"""
    
    def __init__(self, user, duration):
        super().__init__(timeout=30)
        self.user = user
        self.duration = duration
    
    @discord.ui.button(label="사용하기", emoji="💀", style=discord.ButtonStyle.danger)
    async def confirm_grim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # 그림 스킬 준비 상태 설정
        from ..skill_manager import skill_manager
        channel_id = str(interaction.channel.id)
        
        success = skill_manager.add_skill(
            channel_id, "그림", str(interaction.user.id),
            interaction.user.display_name, "all_users", "모든 유저", self.duration
        )
        
        if success:
            # 준비 상태 설정
            channel_state = skill_manager.get_channel_state(channel_id)
            if "special_effects" not in channel_state:
                channel_state["special_effects"] = {}
            
            channel_state["special_effects"]["grim_preparing"] = {
                "caster_id": str(interaction.user.id),
                "caster_name": interaction.user.display_name,
                "rounds_until_activation": 1
            }
            skill_manager.mark_dirty(channel_id)
            
            embed = discord.Embed(
                title="쉬이이이이잇...하,하,하...",
                description=f"**{interaction.user.display_name}**이 거대한 낫을 높게 듭니다.\n\n"
                           f"⏰ **다음 라운드에 발동됩니다!**\n"
                           f"🛡️ **방어 방법**: 없음?",
                color=discord.Color.dark_purple()
            )
            
            await interaction.followup.send(embed=embed)
            
            # 공개 경고 메시지
            await interaction.followup.send(
                "💀 **위험!** 영웅 그림이 다가옵니다. "
            )
        else:
            await interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
    
    @discord.ui.button(label="취소", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel_grim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.send_message("그림 스킬 사용을 취소했습니다.", ephemeral=True)
        self.stop()

class GrimHandler(BaseSkillHandler):
    # ... (위의 코드 계속)
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 그림 발동 체크"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        grim_preparing = channel_state.get("special_effects", {}).get("grim_preparing")
        
        if not grim_preparing:
            return
        
        grim_preparing["rounds_until_activation"] -= 1
        
        if grim_preparing["rounds_until_activation"] <= 0:
            # 그림 발동!
            await self._execute_grim_attack(channel_id, grim_preparing)
            
            # 준비 상태 해제
            del channel_state["special_effects"]["grim_preparing"]
            skill_manager.mark_dirty(channel_id)
    
    async def _execute_grim_attack(self, channel_id: str, grim_data: dict):
        """그림 공격 실행"""
        try:
            from battle_admin import get_battle_participants, send_battle_message, kill_user
            
            # 피닉스 방어 체크
            if await self._check_phoenix_defense(channel_id):
                await send_battle_message(
                    channel_id,
                    "영웅 피닉스가 당신을 죽음으로부터 빼내어 줬습니다."
                )
                return
            
            # 타겟 선택
            target_user_id = await self._select_grim_target(channel_id)
            
            if not target_user_id:
                await send_battle_message(channel_id, "💀 그림의 공격이 실패했습니다. (대상 없음)")
                return
            
            # 확정 사망
            from battle_admin import get_user_info
            user_info = await get_user_info(channel_id, target_user_id)
            target_name = user_info["display_name"] if user_info else "알 수 없는 대상"
            
            await send_battle_message(
                channel_id,
                f"💀 **그림의 거대한 낫이 {target_name}님을 가로질릅니다**\n"
                f"⚰️ **{target_name}**이(가) 영웅 그림의 힘에 의해 즉사했습니다.\n"
                f"(주사위 값: 1000)"
            )
            
            # 실제 사망 처리
            await kill_user(channel_id, target_user_id, 1000)
            
        except Exception as e:
            logger.error(f"그림 공격 실행 실패: {e}")
    
    async def _check_phoenix_defense(self, channel_id: str) -> bool:
        """피닉스 방어 체크"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        phoenix_skill = channel_state.get("active_skills", {}).get("피닉스")
        
        return phoenix_skill is not None
    
    async def _select_grim_target(self, channel_id: str) -> str:
        """그림 타겟 선택 (우선순위 적용)"""
        try:
            from battle_admin import get_battle_participants
            from ..skill_manager import skill_manager
            
            participants = await get_battle_participants(channel_id)
            users = [u for u in participants.get("users", []) if not u.get("is_dead")]
            
            if not users:
                return None
            
            # 1. 체력이 가장 낮은 유저들 찾기
            min_health = min(user.get("health", 0) for user in users)
            lowest_health_users = [u for u in users if u.get("health", 0) == min_health]
            
            if len(lowest_health_users) == 1:
                return lowest_health_users[0]["user_id"]
            
            # 2. 특별 유저 우선순위
            priority_users = skill_manager.get_config("priority_users", [])
            channel_state = skill_manager.get_channel_state(str(channel_id))
            active_skill_users = {skill["user_id"] for skill in channel_state.get("active_skills", {}).values()}
            
            # 특별 유저 중 스킬 미사용자 우선
            priority_unused = [
                u for u in lowest_health_users 
                if u["user_id"] in priority_users and u["user_id"] not in active_skill_users
            ]
            
            if priority_unused:
                return priority_unused[0]["user_id"]
            
            # 3. 랜덤 선택
            return random.choice(lowest_health_users)["user_id"]
            
        except Exception as e:
            logger.error(f"그림 타겟 선택 실패: {e}")
            return None