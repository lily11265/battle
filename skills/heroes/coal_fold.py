# skills/heroes/coal_fold.py
import discord
import logging
import random
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class CoalFoldHandler(BaseSkillHandler):
    """콜 폴드 스킬 핸들러
    
    효과: 주사위 값이 0 또는 100만 나옴
    확률: 0이 40%, 100이 60%
    대상: 몬스터, ADMIN, 스킬 사용자 본인만
    """
    
    def __init__(self):
        super().__init__("콜 폴드", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        embed = discord.Embed(
            title="🎲 콜 폴드의 운명 주사위!",
            description=f"**{interaction.user.display_name}**에게 콜 폴드의 극단적 운명이 깃들었습니다!\n\n"
                       f"🎯 **극단 효과**: 주사위가 0 또는 100만 나옵니다\n"
                       f"📊 **확률**: 0 (40%) / 100 (60%)\n"
                       f"⏱️ **지속시간**: {duration}라운드",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="🎲 확률 분포",
            value="• **0 (실패)**: 40% 확률\n"
                  "• **100 (대성공)**: 60% 확률\n"
                  "• **중간값 없음**: 극단적 결과만 발생",
            inline=False
        )
        
        embed.add_field(
            name="💡 전략적 활용",
            value="• 높은 확률로 100 획득 가능\n"
                  "• 하지만 40% 확률로 0이 될 위험\n"
                  "• 도박적인 선택이 필요한 스킬",
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
            channel_id, "콜 폴드", str(interaction.user.id),
            interaction.user.display_name, str(interaction.user.id), 
            interaction.user.display_name, duration
        )
        
        if not success:
            await interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 0 또는 100으로 변경"""
        from ..skill_manager import skill_manager
        
        channel_id = context.get("channel_id")
        if not channel_id:
            return dice_value
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        coal_fold_skill = channel_state["active_skills"].get("콜 폴드")
        
        # 스킬이 활성화되어 있고, 주사위를 굴린 사람이 스킬 사용자인지 확인
        if coal_fold_skill and coal_fold_skill["user_id"] == str(user_id):
            # 40% 확률로 0, 60% 확률로 100
            random_chance = random.randint(1, 100)
            
            if random_chance <= 40:
                # 0 (실패)
                corrected_value = 0
                result_type = "극한 실패"
            else:
                # 100 (성공)  
                corrected_value = 100
                result_type = "극한 성공"
            
            if corrected_value != dice_value:
                logger.info(f"콜 폴드 스킬 발동 - 유저: {user_id}, 원래값: {dice_value}, "
                          f"보정값: {corrected_value} ({result_type})")
                return corrected_value
        
        return dice_value
