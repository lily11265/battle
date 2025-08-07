# skills/heroes/karon.py
import discord
import logging
from typing import Dict, Any, List
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class KaronHandler(BaseSkillHandler):
    """카론 스킬 핸들러 (전역 데미지 공유)
    
    효과:
    - 기본 효과: 모든 유저가 데미지 공유
    - 유저 사용 시: 적(몬스터/ADMIN)도 데미지 공유에 포함
    - 공유 방식: 한 명이 받은 데미지를 모든 대상이 동일하게 받음
    """
    
    def __init__(self):
        super().__init__("카론", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        is_monster_or_admin = self._is_monster_or_admin(interaction.user)
        
        if is_monster_or_admin:
            title = "🔗 카론의 속박!"
            description = f"**{interaction.user.display_name}**이(가) 카론의 운명 공유 능력을 사용했습니다!\n\n" \
                         f"⚖️ **효과**: 모든 유저가 데미지를 공유합니다\n" \
                         f"⏱️ **지속시간**: {duration}라운드"
            color = discord.Color.dark_purple()
            effect_desc = "• **데미지 공유**: 한 유저가 받은 데미지를 모든 유저가 동일하게 받습니다\n" \
                         "• 운명이 하나로 연결됩니다"
        else:
            title = "🤝 카론의 연대!"
            description = f"**{interaction.user.display_name}**이(가) 카론의 운명 공유 능력을 사용했습니다!\n\n" \
                         f"⚖️ **효과**: 모든 참가자(유저+적)가 데미지를 공유합니다\n" \
                         f"⏱️ **지속시간**: {duration}라운드"
            color = discord.Color.purple()
            effect_desc = "• **완전 데미지 공유**: 모든 참가자가 데미지를 공유합니다\n" \
                         "• 적도 함께 피해를 받습니다\n" \
                         "• 진정한 운명 공동체가 형성됩니다"
        
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
            value="• 회복도 공유됩니다\n• 전략적으로 활용하면 강력한 효과를 발휘합니다\n• 모든 데미지/회복이 즉시 공유 적용됩니다",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    
    async def on_damage_taken(self, channel_id: str, damaged_user_id: str, damage_amount: int) -> Dict[str, int]:
        """데미지를 받았을 때 공유 처리 (Phase 2에서 구현 예정)"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        karon_skill = channel_state["active_skills"].get("카론")
        
        if not karon_skill:
            return {damaged_user_id: damage_amount}
        
        # 스킬 사용자 타입 확인
        skill_user_id = karon_skill["user_id"]
        is_skill_user_monster = skill_user_id in ["monster", "admin"]
        
        # Phase 2에서 실제 전투 시스템과 연동하여 구현
        shared_damage = {}
        
        if is_skill_user_monster:
            # 몬스터가 사용: 모든 유저가 데미지 공유
            # 실제 구현에서는 현재 전투에 참여 중인 모든 유저 목록을 가져와야 함
            logger.info(f"카론 스킬(몬스터) - 유저들 간 데미지 공유: {damage_amount}")
            # shared_damage = {user_id: damage_amount for user_id in all_users}
        else:
            # 유저가 사용: 모든 참가자(유저+적)가 데미지 공유
            logger.info(f"카론 스킬(유저) - 모든 참가자 데미지 공유: {damage_amount}")
            # shared_damage = {participant_id: damage_amount for participant_id in all_participants}
        
        return shared_damage or {damaged_user_id: damage_amount}
    
    async def on_healing_received(self, channel_id: str, healed_user_id: str, heal_amount: int) -> Dict[str, int]:
        """회복을 받았을 때 공유 처리 (Phase 2에서 구현 예정)"""
        # 카론 스킬은 회복도 공유함
        return await self.on_damage_taken(channel_id, healed_user_id, heal_amount)
    
    def _is_monster_or_admin(self, user) -> bool:
        """몬스터나 ADMIN인지 확인"""
        from ..skill_manager import skill_manager
        
        # ADMIN 권한 체크
        if skill_manager.is_admin(str(user.id), user.display_name):
            return True
        
        return False
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 효과 안내"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        karon_skill = channel_state["active_skills"].get("카론")
        
        if karon_skill and karon_skill["rounds_left"] > 0:
            logger.info(f"카론 스킬 데미지 공유 효과 지속 중 - 라운드 {round_num}")
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시"""
        logger.info(f"카론 스킬 종료 - 채널: {channel_id}, 유저: {user_id}")
        
        # Phase 2에서 종료 메시지 구현
        # "카론의 운명 공유가 해제되었습니다."

def create_karon_handler():
    """카론 핸들러 생성"""
    return KaronHandler()