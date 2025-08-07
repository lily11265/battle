# skills/heroes/volken.py
import discord
import logging
import random
from typing import Dict, Any, List
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class VolkenHandler(BaseSkillHandler):
    """볼켄 스킬 핸들러
    
    1-3라운드: 모든 주사위 값 1로 고정
    4라운드: 선별 주사위 굴림 (50 미만인 대상들 선별)
    4-5라운드: 선별된 대상들에게 기존 집중공격 시스템 적용
    """
    
    def __init__(self):
        super().__init__("볼켄", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        # 볼켄은 최소 5라운드 필요
        if duration < 5:
            duration = 5
        
        # 확인창 표시
        view = VolkenConfirmView(interaction.user, duration)
        
        embed = discord.Embed(
            title="🌋 볼켄의 화산 폭발",
            description="**매우 위험한 5단계 스킬입니다!**\n\n"
                       "이 스킬은 5라운드에 걸쳐 강력한 화산 공격을 펼칩니다.\n"
                       "모든 참가자에게 영향을 미치는 광역 스킬입니다.",
            color=discord.Color.dark_orange()
        )
        
        embed.add_field(
            name="🌋 단계별 효과",
            value="**1-3라운드**: 화산재로 모든 주사위 1로 고정\n"
                  "**4라운드**: 용암 선별 (주사위 50 미만 대상 선별)\n"
                  "**5라운드**: 선별된 대상들에게 집중 용암 공격",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 주의사항",
            value="• **5라운드 고정**: 취소 불가능\n"
                  "• **광역 영향**: 모든 참가자 영향\n"
                  "• **단계적 진행**: 각 라운드마다 다른 효과",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class VolkenConfirmView(discord.ui.View):
    """볼켄 스킬 확인 뷰"""
    
    def __init__(self, user, duration):
        super().__init__(timeout=30)
        self.user = user
        self.duration = duration
    
    @discord.ui.button(label="화산 폭발 시작", emoji="🌋", style=discord.ButtonStyle.danger)
    async def confirm_volken(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # 볼켄 스킬 시작
        from ..skill_manager import skill_manager
        channel_id = str(interaction.channel.id)
        
        success = skill_manager.add_skill(
            channel_id, "볼켄", str(interaction.user.id),
            interaction.user.display_name, "all", "모든 참가자", 5
        )
        
        if success:
            # 볼켄 상태 초기화
            channel_state = skill_manager.get_channel_state(channel_id)
            if "special_effects" not in channel_state:
                channel_state["special_effects"] = {}
            
            channel_state["special_effects"]["volken_eruption"] = {
                "caster_id": str(interaction.user.id),
                "caster_name": interaction.user.display_name,
                "current_phase": 1,
                "selected_targets": [],
                "rounds_left": 5
            }
            skill_manager.mark_dirty(channel_id)
            
            embed = discord.Embed(
                title="🌋 볼켄의 화산 폭발 시작!",
                description=f"**{interaction.user.display_name}**이 볼켄의 힘을 해방합니다!\n\n"
                           f"☁️ **1단계 시작**: 화산재가 하늘을 덮습니다\n"
                           f"🎲 **효과**: 모든 주사위가 1로 고정됩니다\n"
                           f"⏳ **남은 단계**: 4단계",
                color=discord.Color.dark_red()
            )
            
            await interaction.followup.send(embed=embed)
            
            # 공개 알림
            await interaction.followup.send(
                "🌋 **경고!** 볼켄의 화산 폭발이 시작되었습니다! "
                "앞으로 5라운드간 화산의 영향을 받게 됩니다!"
            )
        else:
            await interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
    
    @discord.ui.button(label="취소", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel_volken(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.send_message("볼켄 스킬 사용을 취소했습니다.", ephemeral=True)
        self.stop()

class VolkenHandler(BaseSkillHandler):
    # ... (위의 코드 계속)
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 볼켄 효과 적용"""
        from ..skill_manager import skill_manager
        
        channel_id = context.get("channel_id")
        if not channel_id:
            return dice_value
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        volken_effect = channel_state.get("special_effects", {}).get("volken_eruption")
        
        if not volken_effect:
            return dice_value
        
        current_phase = volken_effect["current_phase"]
        
        # 1-3단계: 모든 주사위 1로 고정
        if 1 <= current_phase <= 3:
            if dice_value != 1:
                logger.info(f"볼켄 1-3단계 효과 - 주사위 {dice_value} → 1")
                return 1
        
        # 4단계: 선별을 위한 정상 주사위, 하지만 50 미만시 선별 목록에 추가
        elif current_phase == 4:
            if dice_value < 50:
                volken_effect["selected_targets"].append({
                    "user_id": str(user_id),
                    "dice_value": dice_value
                })
                skill_manager.mark_dirty(str(channel_id))
        
        return dice_value
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 볼켄 단계 진행"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        volken_effect = channel_state.get("special_effects", {}).get("volken_eruption")
        
        if not volken_effect:
            return
        
        current_phase = volken_effect["current_phase"]
        
        try:
            from battle_admin import send_battle_message
            
            if current_phase == 1:
                await send_battle_message(
                    channel_id,
                    "☁️ **볼켄 1단계**: 화산재가 하늘을 뒤덮습니다. (모든 주사위 1로 고정)"
                )
            elif current_phase == 2:
                await send_battle_message(
                    channel_id,
                    "🌋 **볼켄 2단계**: 용암이 끓어오르기 시작합니다. (계속해서 주사위 1 고정)"
                )
            elif current_phase == 3:
                await send_battle_message(
                    channel_id,
                    "🔥 **볼켄 3단계**: 마그마 챔버가 불안정해집니다. (마지막 주사위 1 고정 라운드)"
                )
            elif current_phase == 4:
                await send_battle_message(
                    channel_id,
                    "⚡ **볼켄 4단계**: 용암 선별이 시작됩니다! 주사위를 굴려주세요! (50 미만시 다음 단계 집중공격 대상)"
                )
                volken_effect["selected_targets"] = []  # 선별 목록 초기화
            elif current_phase == 5:
                await self._execute_volken_final_attack(channel_id, volken_effect)
            
            volken_effect["current_phase"] += 1
            volken_effect["rounds_left"] -= 1
            
            if volken_effect["rounds_left"] <= 0:
                # 볼켄 종료
                del channel_state["special_effects"]["volken_eruption"]
                skill_manager.remove_skill(channel_id, "볼켄")
            
            skill_manager.mark_dirty(channel_id)
            
        except Exception as e:
            logger.error(f"볼켄 단계 진행 실패: {e}")
    
    async def _execute_volken_final_attack(self, channel_id: str, volken_data: dict):
        """볼켄 5단계 최종 공격"""
        try:
            from battle_admin import send_battle_message, damage_user
            
            selected_targets = volken_data.get("selected_targets", [])
            
            if not selected_targets:
                await send_battle_message(
                    channel_id,
                    "🌋 **볼켄 5단계**: 용암이 모든 대상을 놓쳤습니다! (선별된 대상 없음)"
                )
                return
            
            await send_battle_message(
                channel_id,
                f"🌋 **볼켄 5단계 - 집중 용암 공격!**\n"
                f"🎯 선별된 대상 {len(selected_targets)}명에게 용암 집중공격!"
            )
            
            # 선별된 각 대상에게 집중공격 (기존 집중공격 시스템 활용)
            for target in selected_targets:
                user_id = target["user_id"]
                original_dice = target["dice_value"]
                
                # 집중공격 피해 계산 (원래 주사위 값 기반)
                attack_count = max(1, (50 - original_dice) // 10)  # 낮을수록 더 많은 공격
                total_damage = attack_count * 15  # 공격당 15 피해
                
                try:
                    from battle_admin import get_user_info
                    user_info = await get_user_info(channel_id, user_id)
                    user_name = user_info["display_name"] if user_info else "대상"
                    
                    await send_battle_message(
                        channel_id,
                        f"🔥 **{user_name}**에게 용암 집중공격 × {attack_count}회! "
                        f"(원래 주사위: {original_dice}) → -{total_damage} HP"
                    )
                    
                    await damage_user(channel_id, user_id, total_damage)
                    
                except Exception as e:
                    logger.error(f"볼켄 개별 공격 실패 {user_id}: {e}")
            
        except Exception as e:
            logger.error(f"볼켄 최종 공격 실패: {e}")
