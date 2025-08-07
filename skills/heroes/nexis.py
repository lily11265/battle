import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class NexisHandler(BaseSkillHandler):
    """넥시스 스킬 핸들러 (특별 제한)
    
    사용자: 오직 유저 ID "1059908946741166120"만 사용 가능
    효과: 적에게 확정적으로 -30 체력 차감
    """
    
    AUTHORIZED_USER_ID = "1059908946741166120"
    
    def __init__(self):
        super().__init__("넥시스", needs_target=True)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        # 권한 체크
        if str(interaction.user.id) != self.AUTHORIZED_USER_ID:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "🔒 넥시스 스킬은 특별한 권한이 필요합니다.", ephemeral=True
                )
            return
        
        # 확인창 표시
        view = NexisConfirmView(interaction.user, duration)
        
        embed = discord.Embed(
            title="⭐ 넥시스의 절대 공격",
            description="**궁극의 힘을 사용하시겠습니까?**\n\n"
                       "이 스킬은 적에게 확정적으로 -30의 피해를 가합니다.\n"
                       "어떠한 방어나 저항도 무시합니다.",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="⚡ 스킬 효과",
            value="• **확정 피해**: -30 HP (방어 무시)\n"
                  "• **대상**: 적 (몬스터/ADMIN)\n"
                  "• **저항 불가**: 모든 방어 효과 무시\n"
                  "• **특별 권한**: 선택받은 자만 사용 가능",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 주의사항",
            value="이 힘은 매우 강력합니다. 신중히 사용하세요.",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class NexisConfirmView(discord.ui.View):
    """넥시스 스킬 확인 뷰"""
    
    def __init__(self, user, duration):
        super().__init__(timeout=30)
        self.user = user
        self.duration = duration
    
    @discord.ui.button(label="사용하기", emoji="⭐", style=discord.ButtonStyle.primary)
    async def confirm_nexis(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # 적 대상 선택
        from ..target_selection import target_selector
        
        async def on_target_selected(target_interaction, selected_target):
            # 적만 대상으로 가능
            if selected_target["type"] not in ["monster", "admin"]:
                await target_interaction.followup.send("❌ 넥시스는 적(몬스터/ADMIN)만 대상으로 할 수 있습니다.", ephemeral=True)
                return
            
            target_name = selected_target["name"]
            
            # 확정 피해 적용
            try:
                from battle_admin import damage_user, send_battle_message
                
                await send_battle_message(
                    str(interaction.channel.id),
                    f"⭐ **넥시스의 절대 공격!**\n"
                    f"🎯 대상: {target_name}\n"
                    f"💥 확정 피해: -30 HP (방어 무시)"
                )
                
                # 실제 피해 적용
                await damage_user(str(interaction.channel.id), selected_target["id"], 30)
                
                # 스킬 상태 저장
                from ..skill_manager import skill_manager
                success = skill_manager.add_skill(
                    str(interaction.channel.id), "넥시스", str(interaction.user.id),
                    interaction.user.display_name, selected_target["id"], target_name, self.duration
                )
                
                embed = discord.Embed(
                    title="⭐ 넥시스 발동 완료!",
                    description=f"**{target_name}**에게 절대적인 힘이 작용했습니다!\n\n"
                               f"💥 **피해량**: -30 HP\n"
                               f"🛡️ **방어 무시**: 모든 보호 효과 관통\n"
                               f"⏱️ **지속시간**: {self.duration}라운드",
                    color=discord.Color.gold()
                )
                
                await target_interaction.followup.send(embed=embed)
                
            except Exception as e:
                logger.error(f"넥시스 피해 적용 실패: {e}")
                await target_interaction.followup.send("❌ 스킬 실행 중 오류가 발생했습니다.", ephemeral=True)
        
        # 대상 선택 (적만)
        channel_id = str(interaction.channel.id)
        targets = await target_selector.get_available_targets(channel_id, "넥시스", str(interaction.user.id))
        enemy_targets = [t for t in targets if t["type"] in ["monster", "admin"]]
        
        if not enemy_targets:
            await interaction.followup.send("❌ 공격할 수 있는 적이 없습니다.", ephemeral=True)
            return
        
        if len(enemy_targets) == 1:
            await on_target_selected(interaction, enemy_targets[0])
        else:
            from ..target_selection import TargetSelectionView
            embed = discord.Embed(
                title="⭐ 넥시스 - 대상 선택",
                description="공격할 적을 선택하세요.",
                color=discord.Color.gold()
            )
            view = TargetSelectionView(enemy_targets, on_target_selected)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="취소", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel_nexis(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.send_message("넥시스 스킬 사용을 취소했습니다.", ephemeral=True)
        self.stop()