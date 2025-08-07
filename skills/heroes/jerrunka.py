# skills/heroes/jerrunka.py
import discord
import logging
import random
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class JerrunkaHandler(BaseSkillHandler):
    """제룬카 스킬 핸들러
    
    몬스터/ADMIN 사용 시:
    - 체력이 가장 낮은 유저 또는 특별 유저 ID 목록의 유저 타겟팅
    - 타겟팅된 유저는 모든 공격에서 -20 데미지 (기존 -10 대신)
    
    유저 사용 시:
    - 주사위 굴림: 50 이상 시 본인 공격만 -20 적용
    - 90 이상 시 모든 유저 공격에 -20 적용
    """
    
    def __init__(self):
        super().__init__("제룬카", needs_target=False)  # 유저 사용시는 자동, 몬스터는 타겟팅
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        is_monster = await self._is_monster_or_admin(interaction.user)
        
        if is_monster:
            await self._activate_monster_jerrunka(interaction, duration)
        else:
            await self._activate_user_jerrunka(interaction, duration)
    
    async def _activate_monster_jerrunka(self, interaction, duration):
        """몬스터/ADMIN 제룬카 활성화"""
        # 타겟 자동 선택 (가장 약한 유저 또는 특별 유저)
        channel_id = str(interaction.channel.id)
        target_user_id = await self._select_monster_target(channel_id)
        
        if not target_user_id:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 타겟을 찾을 수 없습니다.", ephemeral=True)
            return
        
        try:
            from battle_admin import get_user_info
            user_info = await get_user_info(channel_id, target_user_id)
            target_name = user_info["display_name"] if user_info else "대상"
            
            embed = discord.Embed(
                title="🎯 제룬카의 저주!",
                description=f"**{interaction.user.display_name}**이 {target_name}에게 저주를 걸었습니다!\n\n"
                           f"💀 **저주 효과**: 모든 공격에서 추가 피해를 받습니다\n"
                           f"⚡ **피해 증가**: -20 (기존 -10에서 강화)\n"
                           f"⏱️ **지속시간**: {duration}라운드",
                color=discord.Color.dark_red()
            )
            
            embed.add_field(
                name="🎯 저주 대상",
                value=f"**{target_name}**\n"
                      f"이 유저는 모든 공격에서 -20의 추가 피해를 받습니다.",
                inline=False
            )
            
            # 스킬 상태 저장
            from ..skill_manager import skill_manager
            success = skill_manager.add_skill(
                channel_id, "제룬카", str(interaction.user.id),
                interaction.user.display_name, target_user_id, target_name, duration
            )
            
            # 특별 효과 저장
            channel_state = skill_manager.get_channel_state(channel_id)
            if "special_effects" not in channel_state:
                channel_state["special_effects"] = {}
            
            channel_state["special_effects"]["jerrunka_curse"] = {
                "target_id": target_user_id,
                "target_name": target_name,
                "damage_bonus": 20,
                "rounds_left": duration
            }
            skill_manager.mark_dirty(channel_id)
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            logger.error(f"몬스터 제룬카 활성화 실패: {e}")
    
    async def _activate_user_jerrunka(self, interaction, duration):
        """유저 제룬카 활성화 (주사위 기반)"""
        embed = discord.Embed(
            title="🎲 제룬카의 역저주!",
            description=f"**{interaction.user.display_name}**이 제룬카의 힘을 빌립니다!\n\n"
                       f"🎲 **주사위로 효과 결정**:\n"
                       f"• 50 이상: 본인 공격 +20 적용\n"
                       f"• 90 이상: 모든 유저 공격 +20 적용\n"
                       f"⏱️ **지속시간**: {duration}라운드",
            color=discord.Color.gold()
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
        
        # 주사위 굴리기 요구
        await interaction.followup.send(f"🎲 **{interaction.user.display_name}**님, 제룬카 효과 결정을 위해 주사위를 굴려주세요!")
        
        # 대기 상태 설정
        from ..skill_manager import skill_manager
        channel_id = str(interaction.channel.id)
        channel_state = skill_manager.get_channel_state(channel_id)
        
        if "special_effects" not in channel_state:
            channel_state["special_effects"] = {}
        
        channel_state["special_effects"]["jerrunka_pending"] = {
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "duration": duration
        }
        skill_manager.mark_dirty(channel_id)
    
    async def process_user_dice(self, channel_id: str, user_id: str, dice_value: int) -> bool:
        """유저 주사위 처리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        jerrunka_pending = channel_state.get("special_effects", {}).get("jerrunka_pending")
        
        if not jerrunka_pending or jerrunka_pending["user_id"] != str(user_id):
            return False
        
        try:
            from battle_admin import send_battle_message
            
            if dice_value >= 90:
                # 전체 효과
                effect_type = "전체 강화"
                description = "모든 유저의 공격이 +20 강화됩니다!"
                
                channel_state["special_effects"]["jerrunka_global"] = {
                    "caster_id": str(user_id),
                    "caster_name": jerrunka_pending["user_name"],
                    "damage_bonus": 20,
                    "rounds_left": jerrunka_pending["duration"]
                }
                
            elif dice_value >= 50:
                # 개인 효과
                effect_type = "개인 강화"
                description = f"{jerrunka_pending['user_name']}의 공격이 +20 강화됩니다!"
                
                channel_state["special_effects"]["jerrunka_personal"] = {
                    "user_id": str(user_id),
                    "user_name": jerrunka_pending["user_name"],
                    "damage_bonus": 20,
                    "rounds_left": jerrunka_pending["duration"]
                }
            else:
                # 실패
                effect_type = "실패"
                description = "제룬카의 힘을 제대로 끌어내지 못했습니다..."
            
            # 스킬 상태 저장 (성공시에만)
            if dice_value >= 50:
                skill_manager.add_skill(
                    channel_id, "제룬카", str(user_id),
                    jerrunka_pending["user_name"], str(user_id), 
                    jerrunka_pending["user_name"], jerrunka_pending["duration"]
                )
            
            # 대기 상태 제거
            del channel_state["special_effects"]["jerrunka_pending"]
            skill_manager.mark_dirty(channel_id)
            
            await send_battle_message(
                channel_id,
                f"🎲 **제룬카 결과** (주사위: {dice_value})\n"
                f"✨ **{effect_type}**: {description}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"제룬카 유저 주사위 처리 실패: {e}")
            return False
    
    async def _select_monster_target(self, channel_id: str) -> str:
        """몬스터 타겟 선택"""
        try:
            from battle_admin import get_battle_participants
            from ..skill_manager import skill_manager
            
            participants = await get_battle_participants(channel_id)
            users = [u for u in participants.get("users", []) if not u.get("is_dead")]
            
            if not users:
                return None
            
            # 특별 유저 우선 확인
            priority_users = skill_manager.get_config("priority_users", [])
            priority_targets = [u for u in users if u["user_id"] in priority_users]
            
            if priority_targets:
                return priority_targets[0]["user_id"]
            
            # 체력이 가장 낮은 유저
            users.sort(key=lambda x: x.get("health", 0))
            return users[0]["user_id"]
            
        except Exception as e:
            logger.error(f"제룬카 몬스터 타겟 선택 실패: {e}")
            return None
    
    async def _is_monster_or_admin(self, user) -> bool:
        """몬스터나 ADMIN인지 확인"""
        from ..skill_manager import skill_manager
        return skill_manager.is_admin(str(user.id), user.display_name)
