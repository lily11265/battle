# skills/heroes/stravos.py
import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class StravosHandler(BaseSkillHandler):
    """스트라보스 스킬 핸들러
    
    효과: 주사위 값이 최대 150, 최소 75로 고정
    대상: 스킬 사용자 본인만
    구현: 주사위 굴림 후 값 보정
    """
    
    def __init__(self):
        super().__init__("스트라보스", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        embed = discord.Embed(
            title="⚔️ 스트라보스의 검술!",
            description=f"**{interaction.user.display_name}**에게 스트라보스의 완성된 검술이 깃들었습니다!\n\n"
                       f"📊 **효과**: 주사위 값이 75~150으로 강화됩니다\n"
                       f"⚔️ **검술 보정**: 최소한의 실력이 보장됩니다\n"
                       f"⏱️ **지속시간**: {duration}라운드",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="⚔️ 스킬 효과",
            value="• **최소 주사위 값**: 75 \n"
                  "• **최대 주사위 값**: 100 \n"
                  "• **검술의 완성**: 실패할 확률이 크게 줄어듭니다",
            inline=False
        )
        
        embed.add_field(
            name="🆚 다른 스킬과 비교",
            value="• **오닉셀**: 50~150 (더 넓은 범위)\n"
                  "• **스트라보스**: 75~150 (더 높은 최저값)\n"
                  "• 안정성에서 오닉셀보다 우수합니다",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
        
        # 스킬 상태 저장
        from ..skill_manager import skill_manager
        channel_id = str(interaction.channel.id)
        
        success = skill_manager.add_skill(
            channel_id, "스트라보스", str(interaction.user.id),
            interaction.user.display_name, str(interaction.user.id),
            interaction.user.display_name, duration
        )
        
        if not success:
            await interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 값 보정"""
        from ..skill_manager import skill_manager
        
        channel_id = context.get("channel_id")
        if not channel_id:
            return dice_value
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        stravos_skill = channel_state["active_skills"].get("스트라보스")
        
        # 스킬이 활성화되어 있고, 주사위를 굴린 사람이 스킬 사용자인지 확인
        if stravos_skill and stravos_skill["user_id"] == str(user_id):
            # 75~150 범위로 보정
            corrected_value = max(75, min(100, dice_value))
            
            if corrected_value != dice_value:
                logger.info(f"스트라보스 스킬 발동 - 유저: {user_id}, 원래값: {dice_value}, 보정값: {corrected_value}")
                return corrected_value
        
        return dice_value
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시"""
        logger.info(f"스트라보스 스킬 종료 - 채널: {channel_id}, 유저: {user_id}")

def create_stravos_handler():
    """스트라보스 핸들러 생성"""
    return StravosHandler()
