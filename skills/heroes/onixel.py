# skills/heroes/onixel.py
import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class OnixelHandler(BaseSkillHandler):
    """오닉셀 스킬 핸들러
    
    효과: 주사위 값이 최대 150, 최소 50으로 고정
    대상: 스킬 사용자 본인만
    """
    
    def __init__(self):
        super().__init__("오닉셀", needs_target=False, skill_type="self", priority=5)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        embed = discord.Embed(
            title="🔥 오닉셀의 힘!",
            description=f"**{interaction.user.display_name}**에게 오닉셀의 안정된 힘이 깃들었습니다!\n\n"
                       f"📊 **효과**: 주사위 값이 50~150으로 안정화됩니다\n"
                       f"⏱️ **지속시간**: {duration}라운드",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="💡 스킬 설명",
            value="• 최소 주사위 값: **50**\n• 최대 주사위 값: **150**\n• 안정적인 전투력 확보",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    
    async def on_skill_start(self, channel_id: str, user_id: str):
        """스킬 시작 시 호출"""
        logger.info(f"오닉셀 스킬 시작 - 채널: {channel_id}, 유저: {user_id}")
        
        # 오닉셀은 특별한 시작 처리가 필요 없음
        # 주사위 굴림 시 자동으로 적용됨
        from ..skill_manager import skill_manager
        channel_state = skill_manager.get_channel_state(channel_id)
        
        # 스킬 사용자 정보 저장 (선택적)
        if "skill_users" not in channel_state:
            channel_state["skill_users"] = {}
        
        channel_state["skill_users"]["오닉셀"] = {
            "user_id": user_id,
            "active": True
        }
        skill_manager.mark_dirty(channel_id)
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 값 보정"""
        # 오닉셀 스킬 대상자만 보정
        from ..skill_manager import skill_manager
        
        channel_id = context.get("channel_id")
        if not channel_id:
            return dice_value
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        onixel_skill = channel_state.get("active_skills", {}).get("오닉셀")
        
        # 스킬이 활성화되어 있고, 주사위를 굴린 사람이 스킬 사용자인지 확인
        if onixel_skill and onixel_skill["user_id"] == str(user_id):
            # 50~150 범위로 보정
            corrected_value = max(50, min(150, dice_value))
            
            if corrected_value != dice_value:
                logger.info(f"오닉셀 스킬 발동 - 유저: {user_id}, 원래값: {dice_value}, 보정값: {corrected_value}")
                return corrected_value
        
        return dice_value
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시"""
        logger.info(f"오닉셀 스킬 종료 - 채널: {channel_id}, 유저: {user_id}")
        
        # 스킬 사용자 정보 제거
        from ..skill_manager import skill_manager
        channel_state = skill_manager.get_channel_state(str(channel_id))
        
        if "skill_users" in channel_state and "오닉셀" in channel_state["skill_users"]:
            del channel_state["skill_users"]["오닉셀"]
            skill_manager.mark_dirty(channel_id)

# Phase 1에서는 간단한 팩토리 함수로 대체 가능
def create_onixel_handler():
    """오닉셀 핸들러 생성"""
    return OnixelHandler()
