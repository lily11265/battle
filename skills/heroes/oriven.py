# skills/heroes/oriven.py
import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class OrivenHandler(BaseSkillHandler):
    """오리븐 스킬 핸들러 (전역 효과)
    
    효과:
    - 몬스터 사용 시: 해당 라운드 모든 유저 주사위 -10
    - 유저 사용 시: 해당 라운드 적(몬스터/ADMIN) 주사위 -10
    """
    
    def __init__(self):
        super().__init__("오리븐", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        is_monster_or_admin = self._is_monster_or_admin(interaction.user)
        
        if is_monster_or_admin:
            title = "⚫ 오리븐의 저주!"
            description = f"**{interaction.user.display_name}**이(가) 오리븐의 어둠의 힘을 사용했습니다!\n\n" \
                         f"💀 **효과**: 모든 유저의 주사위가 -10 감소합니다\n" \
                         f"⏱️ **지속시간**: {duration}라운드"
            color = discord.Color.dark_red()
            effect_desc = "• 모든 유저 주사위 **-10**\n• 어둠의 힘으로 적들을 약화시킵니다"
        else:
            title = "🌟 오리븐의 축복!"
            description = f"**{interaction.user.display_name}**이(가) 오리븐의 빛의 힘을 사용했습니다!\n\n" \
                         f"✨ **효과**: 모든 적의 주사위가 -10 감소합니다\n" \
                         f"⏱️ **지속시간**: {duration}라운드"
            color = discord.Color.gold()
            effect_desc = "• 모든 적(몬스터/ADMIN) 주사위 **-10**\n• 빛의 힘으로 적들을 약화시킵니다"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        embed.add_field(
            name="💡 스킬 효과",
            value=effect_desc,
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 주의사항",
            value="이 효과는 매 라운드마다 주사위 굴림 시 적용됩니다.",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 -10 효과 적용"""
        from ..skill_manager import skill_manager
        
        channel_id = context.get("channel_id")
        if not channel_id:
            return dice_value
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        oriven_skill = channel_state["active_skills"].get("오리븐")
        
        if not oriven_skill:
            return dice_value
        
        # 스킬 사용자가 몬스터/ADMIN인지 확인
        skill_user_id = oriven_skill["user_id"]
        is_skill_user_monster = skill_user_id in ["monster", "admin"]
        is_current_user_monster = user_id in ["monster", "admin"]
        
        should_apply_debuff = False
        
        if is_skill_user_monster:
            # 몬스터가 사용한 경우: 모든 유저에게 -10
            if not is_current_user_monster:
                should_apply_debuff = True
        else:
            # 유저가 사용한 경우: 모든 적(몬스터/ADMIN)에게 -10
            if is_current_user_monster:
                should_apply_debuff = True
        
        if should_apply_debuff:
            corrected_value = max(1, dice_value - 10)  # 최소 1은 보장
            
            if corrected_value != dice_value:
                logger.info(f"오리븐 스킬 발동 - 대상: {user_id}, 원래값: {dice_value}, 보정값: {corrected_value}")
                return corrected_value
        
        return dice_value
    
    def _is_monster_or_admin(self, user) -> bool:
        """몬스터나 ADMIN인지 확인"""
        from ..skill_manager import skill_manager
        
        # ADMIN 권한 체크
        if skill_manager.is_admin(str(user.id), user.display_name):
            return True
        
        # 몬스터 역할 체크 (Phase 2에서 더 정교한 구현 예정)
        # 현재는 단순히 ADMIN으로 간주
        return False
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 효과 안내"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        oriven_skill = channel_state["active_skills"].get("오리븐")
        
        if oriven_skill and oriven_skill["rounds_left"] > 0:
            # 효과 지속 중임을 알림 (선택적)
            logger.info(f"오리븐 스킬 효과 지속 중 - 라운드 {round_num}")
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시"""
        logger.info(f"오리븐 스킬 종료 - 채널: {channel_id}, 유저: {user_id}")

def create_oriven_handler():
    """오리븐 핸들러 생성"""
    return OrivenHandler()