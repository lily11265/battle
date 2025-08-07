# skills/heroes/scarnel.py
import discord
import logging
import random
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class ScarnelHandler(BaseSkillHandler):
    """스카넬 스킬 핸들러
    
    효과:
    1. 본인이 받는 데미지를 다른 유저와 공유
    2. 퇴장 시(스킬 종료 시) 운석 공격 (광역공격)
    """
    
    def __init__(self):
        super().__init__("스카넬", needs_target=True)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        from ..target_selection import target_selector
        
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        # 대상 선택 필요
        async def on_target_selected(target_interaction, selected_target):
            target_name = selected_target["name"]
            
            embed = discord.Embed(
                title="💥 스카넬의 연장!",
                description=f"**{interaction.user.display_name}**과 **{target_name}**이 안전끈으로 연결되었습니다.\n\n"
                           f"🔗 **데미지 공유**: 받는 피해를 함께 나눕니다\n"
                           f"☄️ **운석 준비**: 스킬 종료 시 운석 공격이 발동됩니다\n"
                           f"⏱️ **지속시간**: {duration}라운드",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="💡 효과 설명",
                value=f"• **데미지 공유**: {interaction.user.display_name}이 받는 데미지를 {target_name}과 공유\n"
                      f"• **운석 공격**: 종료 시 주사위 50 미만인 대상에게 -20 피해\n"
                      f"• **연결 대상**: {target_name}",
                inline=False
            )
            
            # 스킬 상태에 대상 정보 저장
            from ..skill_manager import skill_manager
            channel_id = str(interaction.channel.id)
            
            success = skill_manager.add_skill(
                channel_id, "스카넬", str(interaction.user.id),
                interaction.user.display_name, selected_target["id"], target_name, duration
            )
            
            if success:
                await target_interaction.followup.send(embed=embed)
            else:
                await target_interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
        
        await target_selector.show_target_selection(interaction, "스카넬", duration, on_target_selected)
    
    async def on_damage_taken(self, channel_id: str, user_id: str, damage: int) -> Dict[str, int]:
        """데미지 받을 때 공유 처리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        scarnel_skill = channel_state["active_skills"].get("스카넬")
        
        if not scarnel_skill or scarnel_skill["user_id"] != str(user_id):
            return {user_id: damage}
        
        # 데미지 공유 (50:50)
        shared_damage = damage // 2
        remaining_damage = damage - shared_damage
        
        result = {
            user_id: remaining_damage,
            scarnel_skill["target_id"]: shared_damage
        }
        
        logger.info(f"스카넬 데미지 공유 - 원본: {damage}, 분배: {result}")
        return result
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시 운석 공격"""
        try:
            from battle_admin import get_battle_participants, send_battle_message
            
            # 운석 공격 실행
            participants = await get_battle_participants(channel_id)
            if not participants:
                return
            
            # 모든 참가자에게 주사위 굴리기 요구
            await send_battle_message(
                channel_id,
                "☄️ **스카넬의 운석 공격!**\n"
                "모든 참가자는 주사위를 굴려주세요! (50 미만 시 -20 피해)"
            )
            
            # 운석 공격 상태 설정
            from ..skill_manager import skill_manager
            channel_state = skill_manager.get_channel_state(str(channel_id))
            channel_state["special_effects"]["scarnel_meteor"] = {
                "active": True,
                "targets": list(participants.get("users", [])) + (["monster"] if participants.get("monster") else [])
            }
            skill_manager.mark_dirty(str(channel_id))
            
        except Exception as e:
            logger.error(f"스카넬 운석 공격 실패: {e}")