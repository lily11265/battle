# skills/heroes/nixara.py
import discord
import logging
import random
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class NixaraHandler(BaseSkillHandler):
    """닉사라 스킬 핸들러
    
    효과: 대상을 전투에서 배제
    배제 기간: |공격자 주사위 - 방어자 주사위| ÷ 10 (내림) 라운드
    즉시 적용: 스킬 발동 즉시 해당 라운드부터 적용
    """
    
    def __init__(self):
        super().__init__("닉사라", needs_target=True)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        from ..target_selection import target_selector
        
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        async def on_target_selected(target_interaction, selected_target):
            # 주사위 대결 시작
            await self._start_dice_duel(target_interaction, selected_target, duration)
        
        await target_selector.show_target_selection(interaction, "닉사라", duration, on_target_selected)
    
    async def _start_dice_duel(self, interaction, selected_target, duration):
        """주사위 대결 시작"""
        target_name = selected_target["name"]
        
        embed = discord.Embed(
            title="영웅 닉사라의 순간이동",
            description=f"**{interaction.user.display_name}**이 {target_name}을 멀리 보내려 합니다.\n\n"
                       f"🎲 **주사위 대결이 시작됩니다!**\n"
                       f"차이값에 따라 배제 기간이 결정됩니다.",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="⚡ 대결 방식",
            value=f"• **공격자**: {interaction.user.display_name}\n"
                  f"• **방어자**: {target_name}\n"
                  f"• **배제 기간**: |공격주사위 - 방어주사위| ÷ 10 라운드\n"
                  f"• **즉시 적용**: 이번 라운드부터 배제",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        
        # 주사위 굴리기 요구
        await interaction.followup.send(
            f"🎲 **주사위 대결**\n"
            f"🗡️ **{interaction.user.display_name}**님, 공격 주사위를 굴려주세요!\n"
            f"🛡️ **{target_name}**님, 방어 주사위를 굴려주세요!"
        )
        
        # 대결 상태 저장
        from ..skill_manager import skill_manager
        channel_id = str(interaction.channel.id)
        channel_state = skill_manager.get_channel_state(channel_id)
        
        if "special_effects" not in channel_state:
            channel_state["special_effects"] = {}
        
        channel_state["special_effects"]["nixara_duel"] = {
            "attacker_id": str(interaction.user.id),
            "attacker_name": interaction.user.display_name,
            "defender_id": selected_target["id"],
            "defender_name": target_name,
            "dice_results": {},
            "duration": duration
        }
        skill_manager.mark_dirty(channel_id)
    
    async def process_dice_result(self, channel_id: str, user_id: str, dice_value: int) -> bool:
        """주사위 결과 처리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        nixara_duel = channel_state.get("special_effects", {}).get("nixara_duel")
        
        if not nixara_duel:
            return False
        
        # 주사위 결과 저장
        if str(user_id) == nixara_duel["attacker_id"]:
            nixara_duel["dice_results"]["attacker"] = dice_value
        elif str(user_id) == nixara_duel["defender_id"]:
            nixara_duel["dice_results"]["defender"] = dice_value
        else:
            return False  # 관련 없는 유저
        
        # 둘 다 굴렸는지 확인
        if len(nixara_duel["dice_results"]) == 2:
            await self._resolve_nixara_duel(channel_id, nixara_duel)
            del channel_state["special_effects"]["nixara_duel"]
        
        skill_manager.mark_dirty(channel_id)
        return True
    
    async def _resolve_nixara_duel(self, channel_id: str, duel_data: dict):
        """닉사라 대결 결과 처리"""
        try:
            attacker_dice = duel_data["dice_results"]["attacker"]
            defender_dice = duel_data["dice_results"]["defender"]
            dice_diff = abs(attacker_dice - defender_dice)
            exclusion_rounds = max(1, dice_diff // 10)  # 최소 1라운드
            
            from battle_admin import send_battle_message
            
            await send_battle_message(
                channel_id,
                f"⚡ **대결 결과**\n"
                f"🗡️ {duel_data['attacker_name']}: {attacker_dice}\n"
                f"🛡️ {duel_data['defender_name']}: {defender_dice}\n"
                f"📊 차이값: {dice_diff} → 배제 {exclusion_rounds}라운드"
            )
            
            if exclusion_rounds > 0:
                # 배제 효과 적용
                from ..skill_manager import skill_manager
                channel_state = skill_manager.get_channel_state(str(channel_id))
                
                if "special_effects" not in channel_state:
                    channel_state["special_effects"] = {}
                
                channel_state["special_effects"]["nixara_excluded"] = {
                    "target_id": duel_data["defender_id"],
                    "target_name": duel_data["defender_name"],
                    "rounds_left": exclusion_rounds,
                    "original_rounds": exclusion_rounds
                }
                
                # 스킬 상태 저장
                success = skill_manager.add_skill(
                    channel_id, "닉사라", duel_data["attacker_id"],
                    duel_data["attacker_name"], duel_data["defender_id"], 
                    duel_data["defender_name"], exclusion_rounds
                )
                
                skill_manager.mark_dirty(channel_id)
                
                await send_battle_message(
                    channel_id,
                    f"🌀 **{duel_data['defender_name']}**이 다른 공간으로 떨어집니다! "
                    f"({exclusion_rounds}라운드간 행동 불가)"
                )
            else:
                await send_battle_message(
                    channel_id,
                    f"✨ **{duel_data['defender_name']}**이 닉사라의 공격을 완전히 막아냈습니다!"
                )
                
        except Exception as e:
            logger.error(f"닉사라 대결 처리 실패: {e}")