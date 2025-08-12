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
        super().__init__("볼켄", needs_target=False, skill_type="special", priority=4)
    
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
    
    async def on_skill_start(self, channel_id: str, user_id: str):
        """스킬 시작 시 화산 폭발 준비"""
        logger.info(f"볼켄 화산 폭발 시작 - 채널: {channel_id}, 유저: {user_id}")
        
        from ..skill_manager import skill_manager
        channel_state = skill_manager.get_channel_state(channel_id)
        
        if "special_effects" not in channel_state:
            channel_state["special_effects"] = {}
        
        # 볼켄 상태 초기화
        channel_state["special_effects"]["volken_eruption"] = {
            "caster_id": user_id,
            "current_phase": 1,
            "selected_targets": [],
            "rounds_remaining": 5
        }
        skill_manager.mark_dirty(channel_id)
    
    async def on_dice_roll(self, user_id: str, dice_value: int, context: Dict[str, Any]) -> int:
        """주사위 굴림 시 볼켄 효과 적용"""
        channel_id = context.get("channel_id")
        if not channel_id:
            return dice_value
        
        from ..skill_manager import skill_manager
        channel_state = skill_manager.get_channel_state(str(channel_id))
        volken_data = channel_state.get("special_effects", {}).get("volken_eruption")
        
        if not volken_data:
            return dice_value
        
        phase = volken_data["current_phase"]
        
        # 1-3라운드: 모든 주사위 1로 고정
        if 1 <= phase <= 3:
            logger.info(f"볼켄 화산재 효과: {user_id}의 주사위가 1로 고정됨")
            return 1
        
        # 4라운드: 선별 단계 (50 미만 선별)
        elif phase == 4:
            if dice_value < 50 and user_id not in volken_data["selected_targets"]:
                volken_data["selected_targets"].append(user_id)
                logger.info(f"볼켄 선별: {user_id}가 용암 대상으로 선별됨 (주사위: {dice_value})")
            return dice_value
        
        # 5라운드: 선별된 대상은 불리한 값
        elif phase == 5:
            if user_id in volken_data["selected_targets"]:
                # 선별된 대상은 주사위 값 절반
                modified_value = max(1, dice_value // 2)
                logger.info(f"볼켄 용암 공격: {user_id}의 주사위 {dice_value} → {modified_value}")
                return modified_value
        
        return dice_value
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 볼켄 단계 진행"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        volken_data = channel_state.get("special_effects", {}).get("volken_eruption")
        
        if not volken_data:
            return
        
        # 단계 진행
        volken_data["current_phase"] = min(5, volken_data["current_phase"] + 1)
        volken_data["rounds_remaining"] -= 1
        
        phase = volken_data["current_phase"]
        
        # 단계별 메시지
        phase_messages = {
            1: "🌋 화산이 진동하기 시작합니다... 화산재가 하늘을 뒤덮습니다!",
            2: "🌋 화산재가 짙어집니다. 모든 것이 어둠에 잠깁니다...",
            3: "🌋 용암이 끓어오릅니다. 곧 폭발할 것 같습니다!",
            4: "🌋 **선별 시작!** 약한 자들이 표적이 됩니다!",
            5: "🌋 **화산 폭발!** 선별된 대상들에게 용암이 쏟아집니다!"
        }
        
        if phase in phase_messages:
            logger.info(f"볼켄 {phase}단계: {phase_messages[phase]}")
        
        # 5라운드 후 종료
        if volken_data["rounds_remaining"] <= 0:
            del channel_state["special_effects"]["volken_eruption"]
            logger.info("볼켄 화산 폭발 종료")
        
        skill_manager.mark_dirty(channel_id)
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시 정리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        if "volken_eruption" in special_effects:
            del special_effects["volken_eruption"]
            skill_manager.mark_dirty(channel_id)
            logger.info(f"볼켄 화산 폭발 효과 제거 - 채널: {channel_id}")

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
        
        from ..skill_manager import skill_manager
        channel_id = str(interaction.channel.id)
        
        # 볼켄은 항상 5라운드
        duration = 5
        
        success = skill_manager.add_skill(
            channel_id, "볼켄", str(interaction.user.id),
            interaction.user.display_name, "all", "전체", duration
        )
        
        if success:
            # 화산 폭발 시작
            from . import get_skill_handler
            handler = get_skill_handler("볼켄")
            if handler:
                await handler.on_skill_start(channel_id, str(interaction.user.id))
            
            embed = discord.Embed(
                title="🌋 화산이 깨어났다!",
                description=f"**{interaction.user.display_name}**이 볼켄의 힘으로 화산을 깨웠습니다!\n\n"
                           f"앞으로 **5라운드** 동안 대재앙이 펼쳐집니다!",
                color=discord.Color.dark_red()
            )
            
            embed.add_field(
                name="⚠️ 1단계 시작",
                value="화산재가 하늘을 뒤덮기 시작합니다...\n"
                      "모든 주사위가 1로 고정됩니다!",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
            # 공개 경고
            await interaction.followup.send(
                "🌋 **경고!** 볼켄의 화산이 폭발을 준비합니다! 5라운드 동안 대재앙이 계속됩니다!"
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
