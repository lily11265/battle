# skills/heroes/phoenix.py
import discord
import logging
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class PhoenixHandler(BaseSkillHandler):
    """피닉스 스킬 핸들러 (유저 전용)
    
    효과: 
    1. 죽은 유저 소생
    2. 그림 공격 방어 (Phase 2에서 구현)
    
    체력 소모: 없음
    대상: 스킬 사용자 본인 또는 다른 유저
    """
    
    def __init__(self):
        super().__init__("피닉스", needs_target=True)  # Phase 2에서 대상 선택 구현
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        embed = discord.Embed(
            title="🔥 피닉스의 재생력!",
            description=f"**{interaction.user.display_name}**에게 피닉스의 재생 능력이 깃들었습니다!\n\n"
                       f"🛡️ **방어 효과**: 그림의 공격을 방어할 수 있습니다\n"
                       f"💚 **소생 효과**: 죽은 동료를 되살릴 수 있습니다\n"
                       f"⏱️ **지속시간**: {duration}라운드",
            color=discord.Color.from_rgb(255, 100, 0)  # 주황색
        )
        
        embed.add_field(
            name="💡 스킬 설명",
            value="• **그림 방어**: 그림의 확정 사망 공격을 무효화\n"
                  "• **소생 능력**: 죽은 유저를 되살림 (체력 소모 없음)\n"
                  "• **유저 전용**: 몬스터는 사용할 수 없습니다",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 사용법",
            value="피닉스 스킬이 활성화된 상태에서 그림의 공격이 들어오면 자동으로 방어됩니다.",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
    
    async def defend_against_grim(self, channel_id: str, target_user_id: str) -> bool:
        """그림 공격 방어 (Phase 2에서 구현 예정)"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        phoenix_skill = channel_state["active_skills"].get("피닉스")
        
        # 피닉스 스킬이 활성화되어 있는지 확인
        if not phoenix_skill:
            return False
        
        # Phase 2에서 상세 구현 예정
        # 현재는 기본적인 방어 로직만
        logger.info(f"피닉스 스킬로 그림 공격 방어 - 대상: {target_user_id}")
        return True
    
    async def revive_user(self, channel_id: str, target_user_id: str) -> bool:
        """사용자 소생 (Phase 2에서 구현 예정)"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        phoenix_skill = channel_state["active_skills"].get("피닉스")
        
        if not phoenix_skill:
            return False
        
        # Phase 2에서 실제 체력 시스템과 연동하여 구현
        logger.info(f"피닉스 스킬로 유저 소생 - 대상: {target_user_id}")
        return True
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 - 그림 공격 감지 준비"""
        # Phase 2에서 그림 스킬과의 상호작용 구현 예정
        pass
    
    async def on_skill_end(self, channel_id: str, user_id: str):
        """스킬 종료 시"""
        logger.info(f"피닉스 스킬 종료 - 채널: {channel_id}, 유저: {user_id}")
        
        # Phase 2에서 종료 메시지 구현 예정
        # await self._send_skill_end_message(channel_id, user_id)

def create_phoenix_handler():
    """피닉스 핸들러 생성"""
    return PhoenixHandler()