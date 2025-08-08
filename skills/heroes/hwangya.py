import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class HwangyaHandler(BaseSkillHandler):
    """황야 스킬 핸들러
    
    효과: 한 턴에 두 가지 행동 가능
    행동: 공격+공격, 공격+회복, 회복+회복
    대상: 몬스터, ADMIN, 스킬 사용자 본인만
    
    구현:
    - 몬스터: 두 번의 별도 주사위 굴림
    - 유저: 두 번의 `/회복` 명령어 사용 가능
    """
    
    def __init__(self):
        super().__init__("황야", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        is_monster = await self._is_monster_or_admin(interaction.user)
        
        if is_monster:
            title = "황야 주변 시간이 느리게 흘러갑니다"
            description = f"**{interaction.user.display_name}**이 황야의 능력을 카피해옵니다.\n\n" \
                         f"💥 **이중 행동**: 매 턴마다 2번의 공격이 가능합니다\n" \
                         f"🎲 **두 번 굴림**: 공격할 때마다 2개의 주사위를 굴립니다\n" \
                         f"⏱️ **지속시간**: {duration}라운드"
            color = discord.Color.red()
            effect_desc = "• **공격 횟수**: 턴당 2회\n• **주사위**: 각 공격마다 별도 굴림\n• **행동 선택**: 공격+공격만 가능"
        else:
            title = "🌟 황야의 도움"
            description = f"**{interaction.user.display_name}**이 황야에게 도움을 받습니다.\n\n" \
                         f"⚡ **이중 행동**: 매 턴마다 2가지 행동이 가능합니다\n" \
                         f"🔄 **행동 조합**: 공격+공격, 공격+회복, 회복+회복\n" \
                         f"⏱️ **지속시간**: {duration}라운드"
            color = discord.Color.gold()
            effect_desc = "• **회복 횟수**: 턴당 최대 2회 가능\n• **행동 선택**: 자유로운 조합\n• **전략적 활용**: 상황에 따른 최적 선택"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        embed.add_field(
            name="⚡ 이중 행동 효과",
            value=effect_desc,
            inline=False
        )
        
        embed.add_field(
            name="💡 사용 방법",
            value="• **몬스터**: 공격 시 자동으로 2번 주사위 굴림\n"
                  "• **유저**: `/회복` 명령어를 턴당 2번까지 사용 가능\n"
                  "• 각 행동은 별도로 계산됩니다",
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
            channel_id, "황야", str(interaction.user.id),
            interaction.user.display_name, str(interaction.user.id),
            interaction.user.display_name, duration
        )
        
        # 스킬 상태 저장
        from ..skill_manager import skill_manager
        from ..skill_effects import skill_effects
        channel_id = str(interaction.channel.id)
        
        success = skill_manager.add_skill(
            channel_id, "황야", str(interaction.user.id),
            interaction.user.display_name, str(interaction.user.id),
            interaction.user.display_name, duration
        )
        
        # 특별 효과 저장을 skill_effects를 통해 처리 (테스트와 일관성 유지)
        if success:
            await skill_effects.process_skill_activation(
                channel_id, "황야", str(interaction.user.id), 
                str(interaction.user.id), duration
            )
            
            # 추가로 황야 특유의 정보 저장
            channel_state = skill_manager.get_channel_state(channel_id)
            if "hwangya_double_action" in channel_state.get("special_effects", {}):
                channel_state["special_effects"]["hwangya_double_action"].update({
                    "user_name": interaction.user.display_name,
                    "is_monster": is_monster,
                    "max_actions_per_turn": 2,
                    "duration": duration
                })
                skill_manager.mark_dirty(channel_id)
    
    async def can_use_recovery(self, channel_id: str, user_id: str) -> bool:
        """회복 사용 가능 여부 확인 (유저용)"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        hwangya_effect = channel_state.get("special_effects", {}).get("hwangya_double_action")
        
        if not hwangya_effect or hwangya_effect["user_id"] != str(user_id):
            return True  # 일반적인 회복 사용
        
        # 황야 스킬 사용자인 경우 2회까지 가능
        return hwangya_effect["actions_used_this_turn"] < hwangya_effect["max_actions_per_turn"]
    
    async def use_recovery_action(self, channel_id: str, user_id: str):
        """회복 행동 사용 처리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        hwangya_effect = channel_state.get("special_effects", {}).get("hwangya_double_action")
        
        if hwangya_effect and hwangya_effect["user_id"] == str(user_id):
            hwangya_effect["actions_used_this_turn"] += 1
            skill_manager.mark_dirty(channel_id)
            
            remaining_actions = hwangya_effect["max_actions_per_turn"] - hwangya_effect["actions_used_this_turn"]
            
            if remaining_actions > 0:
                try:
                    from battle_admin import send_battle_message
                    await send_battle_message(
                        channel_id,
                        f"⚡ **황야 효과**: {hwangya_effect['user_name']}님은 "
                        f"이번 턴에 {remaining_actions}번의 행동을 더 할 수 있습니다!"
                    )
                except Exception as e:
                    logger.error(f"황야 행동 알림 실패: {e}")
    
    async def get_monster_attack_count(self, channel_id: str, user_id: str) -> int:
        """몬스터 공격 횟수 조회"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        hwangya_effect = channel_state.get("special_effects", {}).get("hwangya_double_action")
        
        if (hwangya_effect and 
            hwangya_effect["user_id"] == str(user_id) and 
            hwangya_effect["is_monster"]):
            return 2  # 몬스터는 2번 공격
        
        return 1  # 일반적인 1번 공격
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 행동 카운터 리셋"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        hwangya_effect = channel_state.get("special_effects", {}).get("hwangya_double_action")
        
        if hwangya_effect:
            hwangya_effect["actions_used_this_turn"] = 0
            skill_manager.mark_dirty(channel_id)
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시 특별 효과 정리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        if "hwangya_double_action" in channel_state.get("special_effects", {}):
            del channel_state["special_effects"]["hwangya_double_action"]
            skill_manager.mark_dirty(channel_id)
        
        logger.info(f"황야 스킬 종료 - 채널: {channel_id}, 유저: {user_id}")
    
    async def _is_monster_or_admin(self, user) -> bool:
        """몬스터나 ADMIN인지 확인"""
        from ..skill_manager import skill_manager
        return skill_manager.is_admin(str(user.id), user.display_name)
