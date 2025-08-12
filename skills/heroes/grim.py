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
        super().__init__("그림", needs_target=False, skill_type="special", priority=1)
    
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
    
    async def on_skill_start(self, channel_id: str, user_id: str):
        """스킬 시작 시 처리"""
        logger.info(f"그림 스킬 시작 - 채널: {channel_id}, 유저: {user_id}")
        
        # 그림 준비 상태 설정
        from ..skill_manager import skill_manager
        channel_state = skill_manager.get_channel_state(channel_id)
        
        if "special_effects" not in channel_state:
            channel_state["special_effects"] = {}
        
        channel_state["special_effects"]["grim_preparing"] = {
            "caster_id": user_id,
            "caster_name": "그림 사용자",
            "rounds_until_activation": 1,
            "target_id": None,
            "selected_target": None
        }
        skill_manager.mark_dirty(channel_id)
    
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
            logger.info(f"💀 그림 발동! 채널: {channel_id}, 라운드: {round_num}")
            
            # 타겟 선택 로직은 battle_admin과 연동
            # 여기서는 발동 신호만 보냄
            channel_state["special_effects"]["grim_activated"] = {
                "caster_id": grim_preparing["caster_id"],
                "round": round_num
            }
            
            # 준비 상태 제거
            del channel_state["special_effects"]["grim_preparing"]
            skill_manager.mark_dirty(channel_id)
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시 정리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        # 그림 관련 효과 제거
        if "grim_preparing" in special_effects:
            del special_effects["grim_preparing"]
        if "grim_activated" in special_effects:
            del special_effects["grim_activated"]
        
        skill_manager.mark_dirty(channel_id)
        logger.info(f"그림 스킬 종료 및 정리 완료 - 채널: {channel_id}")

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
            # 준비 상태 설정 (on_skill_start에서 처리)
            handler = get_skill_handler("그림")
            if handler:
                await handler.on_skill_start(channel_id, str(interaction.user.id))
            
            embed = discord.Embed(
                title="쉬이이이이잇...하,하,하...",
                description=f"**{interaction.user.display_name}**이 거대한 낫을 높게 듭니다.\n\n"
                           f"⏰ **다음 라운드에 발동됩니다!**\n"
                           f"🛡️ **방어 방법**: 피닉스 스킬만 가능",
                color=discord.Color.dark_purple()
            )
            
            await interaction.followup.send(embed=embed)
            
            # 공개 경고 메시지
            await interaction.followup.send(
                "💀 **위험!** 영웅 그림이 다가옵니다. 다음 라운드에 가장 약한 자가 처형됩니다!"
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

# 필요한 import 추가
from . import get_skill_handler
