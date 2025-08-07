# skills/heroes/lucencia.py
import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class LucenciaHandler(BaseSkillHandler):
    """루센시아 스킬 핸들러
    
    효과: 체력을 소모하여 사망한 유저 부활
    소모량: nn번 소모하여 총 mm 체력으로 부활 (전역변수)
    특별 우선순위: 유저 ID "1237738945635160104" 최우선 부활
    """
    
    def __init__(self):
        super().__init__("루센시아", needs_target=True)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        from ..target_selection import target_selector
        from ..skill_manager import skill_manager
        
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        # 죽은 유저만 대상으로 할 수 있도록 필터링
        async def get_dead_targets(channel_id: str, skill_name: str, user_id: str):
            all_targets = await target_selector.get_available_targets(channel_id, skill_name, user_id)
            return [target for target in all_targets if target["type"] == "dead_user"]
        
        dead_targets = await get_dead_targets(str(interaction.channel.id), "루센시아", str(interaction.user.id))
        
        if not dead_targets:
            await interaction.followup.send("❌ 부활시킬 수 있는 대상이 없습니다.", ephemeral=True)
            return
        
        # 우선순위 정렬 (특별 유저 우선)
        priority_user_id = "1237738945635160104"
        dead_targets.sort(key=lambda x: (x["id"] != priority_user_id, x["name"]))
        
        async def on_target_selected(target_interaction, selected_target):
            # 설정 값 조회
            config = skill_manager.get_config("lucencia", {"health_cost": 3, "revival_health": 5})
            health_cost = config["health_cost"]
            revival_health = config["revival_health"]
            
            target_name = selected_target["name"]
            
            embed = discord.Embed(
                title="✨ 루센시아의 부활술!",
                description=f"**{interaction.user.display_name}**이 루센시아의 생명력을 사용합니다!\n\n"
                           f"💚 **부활 대상**: {target_name}\n"
                           f"❤️ **체력 소모**: -{health_cost}HP\n"
                           f"🔄 **부활 체력**: +{revival_health}HP\n"
                           f"⏱️ **지속시간**: {duration}라운드",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="💡 부활 효과",
                value=f"• {target_name}이(가) {revival_health} 체력으로 부활합니다\n"
                      f"• 시전자는 {health_cost} 체력을 소모합니다\n"
                      f"• 부활 즉시 전투에 참여 가능합니다",
                inline=False
            )
            
            if selected_target["id"] == priority_user_id:
                embed.add_field(
                    name="⭐ 특별 효과",
                    value="우선순위 대상에게 시전되어 추가 보호 효과가 적용됩니다!",
                    inline=False
                )
            
            # 부활 처리 실행
            try:
                from battle_admin import revive_user, damage_user
                
                # 시전자 체력 차감
                await damage_user(str(interaction.channel.id), str(interaction.user.id), health_cost)
                
                # 대상 부활
                await revive_user(str(interaction.channel.id), selected_target["id"], revival_health)
                
                # 스킬 상태 저장
                success = skill_manager.add_skill(
                    str(interaction.channel.id), "루센시아", str(interaction.user.id),
                    interaction.user.display_name, selected_target["id"], target_name, duration
                )
                
                if success:
                    await target_interaction.followup.send(embed=embed)
                    
                    # 부활 알림
                    await target_interaction.followup.send(
                        f"🎉 **{target_name}**이(가) 루센시아의 힘으로 부활했습니다!"
                    )
                else:
                    await target_interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
                    
            except Exception as e:
                logger.error(f"루센시아 부활 처리 실패: {e}")
                await target_interaction.followup.send("❌ 부활 처리 중 오류가 발생했습니다.", ephemeral=True)
        
        # 대상 선택 (죽은 유저만)
        embed = discord.Embed(
            title="✨ 루센시아 - 부활 대상 선택",
            description="부활시킬 대상을 선택하세요.",
            color=discord.Color.green()
        )
        
        view = discord.ui.View(timeout=60)
        
        # 25개 이하면 드롭다운
        if len(dead_targets) <= 25:
            from ..target_selection import TargetSelectDropdown
            view.add_item(TargetSelectDropdown(dead_targets, on_target_selected))
        else:
            from ..target_selection import SearchTargetButton  
            view.add_item(SearchTargetButton(dead_targets, on_target_selected))
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)