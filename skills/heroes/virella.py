# skills/heroes/virella.py
import discord
import logging
import random
from typing import Dict, Any
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class VirellaHandler(BaseSkillHandler):
    """비렐라 스킬 핸들러
    
    효과: 대상을 전투에서 배제 (3라운드 또는 저항 성공까지)
    저항 시스템: 매 턴마다 저항 주사위 굴림 (50 이상 시 탈출)
    실패 시: 해당 턴의 공격/방어 주사위가 0으로 처리
    """
    
    def __init__(self):
        super().__init__("비렐라", needs_target=True)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        from ..target_selection import target_selector
        
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        async def on_target_selected(target_interaction, selected_target):
            target_name = selected_target["name"]
            target_user_id = selected_target["id"]
            
            # AI 난이도별 타겟팅 처리
            if target_user_id in ["monster", "admin"]:
                # 몬스터/ADMIN이 사용하는 경우의 타겟팅 로직
                target_user_id = await self._get_ai_target(str(interaction.channel.id))
                if target_user_id:
                    # 새 타겟 정보로 업데이트
                    from battle_admin import get_user_info
                    user_info = await get_user_info(str(interaction.channel.id), target_user_id)
                    if user_info:
                        target_name = user_info["display_name"]
                        selected_target["id"] = target_user_id
            
            embed = discord.Embed(
                title="🌿 비렐라의 속박!",
                description=f"**{target_name}**이 비렐라의 덩굴에 얽매였습니다!\n\n"
                           f"🔒 **배제 효과**: 전투에서 일시적으로 배제됩니다\n"
                           f"🎲 **저항 기회**: 매 턴마다 저항 주사위 (50+ 시 탈출)\n"
                           f"⏱️ **최대 지속**: {min(duration, 3)}라운드",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="💡 효과 설명",
                value="• **배제 중**: 공격/방어 주사위가 0으로 처리\n"
                      "• **저항 주사위**: 매 턴 시작 시 자동 굴림\n"
                      "• **탈출 조건**: 저항 주사위 50 이상\n"
                      "• **최대 3라운드** 후 자동 해제",
                inline=False
            )
            
            # 배제 상태 설정
            from ..skill_manager import skill_manager
            channel_id = str(interaction.channel.id)
            
            # 특별 효과에 배제 상태 추가
            channel_state = skill_manager.get_channel_state(channel_id)
            if "special_effects" not in channel_state:
                channel_state["special_effects"] = {}
            
            channel_state["special_effects"]["virella_bound"] = {
                "target_id": selected_target["id"],
                "target_name": target_name,
                "rounds_left": min(duration, 3),
                "resistance_attempts": 0
            }
            
            # 스킬 상태 저장
            success = skill_manager.add_skill(
                channel_id, "비렐라", str(interaction.user.id),
                interaction.user.display_name, selected_target["id"], target_name, min(duration, 3)
            )
            
            skill_manager.mark_dirty(channel_id)
            
            if success:
                await target_interaction.followup.send(embed=embed)
                
                # 배제 알림
                await target_interaction.followup.send(
                    f"🔒 **{target_name}**이 비렐라의 덩굴에 얽매여 행동할 수 없습니다!\n"
                    f"매 턴마다 저항 주사위를 굴려 탈출을 시도하세요."
                )
            else:
                await target_interaction.followup.send("❌ 스킬 활성화에 실패했습니다.", ephemeral=True)
        
        await target_selector.show_target_selection(interaction, "비렐라", duration, on_target_selected)
    
    async def _get_ai_target(self, channel_id: str) -> str:
        """AI 난이도별 타겟 선택"""
        try:
            from battle_admin import get_battle_participants, get_ai_difficulty
            
            participants = await get_battle_participants(channel_id)
            users = participants.get("users", [])
            
            if not users:
                return None
            
            difficulty = await get_ai_difficulty(channel_id)
            
            if difficulty in ["easy", "normal"]:
                # 랜덤 선택
                return random.choice(users)["user_id"]
            else:
                # 어려움 이상: 가장 위협적인 유저 선택 (체력이 높은 유저)
                users.sort(key=lambda x: x.get("health", 0), reverse=True)
                return users[0]["user_id"]
                
        except Exception as e:
            logger.error(f"AI 타겟 선택 실패: {e}")
            return None
    
    async def on_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 저항 주사위"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        virella_effect = channel_state.get("special_effects", {}).get("virella_bound")
        
        if not virella_effect:
            return
        
        # 저항 주사위 굴림
        resistance_roll = random.randint(1, 100)
        virella_effect["resistance_attempts"] += 1
        
        try:
            from battle_admin import send_battle_message
            
            if resistance_roll >= 50:
                # 저항 성공
                await send_battle_message(
                    channel_id,
                    f"🎲 **저항 성공!** {virella_effect['target_name']}이(가) "
                    f"덩굴에서 탈출했습니다! (주사위: {resistance_roll})"
                )
                
                # 효과 해제
                del channel_state["special_effects"]["virella_bound"]
                skill_manager.remove_skill(channel_id, "비렐라")
                skill_manager.mark_dirty(channel_id)
            else:
                # 저항 실패
                await send_battle_message(
                    channel_id,
                    f"🎲 **저항 실패...** {virella_effect['target_name']}은(는) "
                    f"여전히 속박되어 있습니다. (주사위: {resistance_roll})"
                )
                
                virella_effect["rounds_left"] -= 1
                
                if virella_effect["rounds_left"] <= 0:
                    # 최대 라운드 도달로 자동 해제
                    await send_battle_message(
                        channel_id,
                        f"⏰ **자동 해제** {virella_effect['target_name']}의 속박이 풀렸습니다."
                    )
                    
                    del channel_state["special_effects"]["virella_bound"]
                    skill_manager.remove_skill(channel_id, "비렐라")
                
                skill_manager.mark_dirty(channel_id)
                
        except Exception as e:
            logger.error(f"비렐라 저항 처리 실패: {e}")
    
    async def check_action_blocked(self, channel_id: str, user_id: str, action_type: str) -> bool:
        """행동 차단 여부 확인"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        virella_effect = channel_state.get("special_effects", {}).get("virella_bound")
        
        if virella_effect and virella_effect["target_id"] == str(user_id):
            return True  # 행동 차단
        
        return False  # 정상 행동