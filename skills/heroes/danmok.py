# skills/heroes/danmok.py
import discord
import logging
from typing import Dict, Any, List
from . import BaseSkillHandler

logger = logging.getLogger(__name__)

class DanmokHandler(BaseSkillHandler):
    """단목 스킬 핸들러
    
    발동: 모든 유저가 주사위 굴림
    관통 시스템:
    - 50 미만 유저 + 그 다음 순서 유저가 피격
    - 직접 피격(50 미만): 체력 -20
    - 관통 피격(다음 순서): 체력 -10
    - 연속 50 미만 시: 해당 수만큼 다음 유저들 관통 피격
    
    유저 사용 시: 몬스터/ADMIN에게 방어 무시 -30 데미지
    """
    
    def __init__(self):
        super().__init__("단목", needs_target=False)
    
    async def activate(self, interaction: discord.Interaction, target_id: str, duration: int):
        """스킬 활성화"""
        is_monster = await self._is_monster_or_admin(interaction.user)
        
        if is_monster:
            await self._activate_monster_danmok(interaction, duration)
        else:
            await self._activate_user_danmok(interaction, duration)
    
    async def _activate_monster_danmok(self, interaction, duration):
        """몬스터 단목 활성화 (관통 시스템)"""
        embed = discord.Embed(
            title="🏹 단목의 바람 화살",
            description=f"**{interaction.user.display_name}**이 사슴신의 힘을 빼앗아 옵니다.\n\n"
                       f"🎯 **관통 시스템**: 모든 유저가 주사위를 굴립니다\n"
                       f"💥 **직접 피격**: 50 미만시 -20 피해\n"
                       f"🔄 **관통 피격**: 다음 순서 유저 -10 피해\n"
                       f"⏱️ **지속시간**: {duration}라운드",
            color=discord.Color.dark_green()
        )
        
        embed.add_field(
            name="🏹 관통 규칙",
            value="• 50 미만 굴린 유저: 직접 피격 (-20 HP)\n"
                  "• 그 다음 순서 유저: 관통 피격 (-10 HP)\n"
                  "• 연속 50 미만시: 연속 관통 피격\n"
                  "• 턴 순서에 따라 관통 방향 결정",
            inline=False
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)
        
        # 모든 유저 주사위 굴리기 요구
        await interaction.followup.send(
            "🎲 **모든 유저는 단목 회피를 위해 주사위를 굴려주세요!**\n"
            "50 미만시 직접 피격, 그 다음 유저는 관통 피격을 받습니다."
        )
        
        # 단목 대기 상태 설정
        from ..skill_manager import skill_manager
        from ..skill_effects import skill_effects
        channel_id = str(interaction.channel.id)
        
        success = skill_manager.add_skill(
            channel_id, "단목", str(interaction.user.id),
            interaction.user.display_name, "all_users", "모든 유저", duration
        )
        
        if success:
            # skill_effects를 통해 특수 효과 설정 (테스트와 일관성 유지)
            await skill_effects.process_skill_activation(
                channel_id, "단목", str(interaction.user.id), 
                "all_users", duration
            )
            
            # 추가로 단목 특유의 정보 저장
            channel_state = skill_manager.get_channel_state(channel_id)
            if "danmok_penetration" in channel_state.get("special_effects", {}):
                channel_state["special_effects"]["danmok_penetration"].update({
                    "caster_id": str(interaction.user.id),
                    "caster_name": interaction.user.display_name,
                    "dice_results": {},
                    "turn_order": [],
                    "duration": duration
                })
                skill_manager.mark_dirty(channel_id)
    
    async def _activate_user_danmok(self, interaction, duration):
        """유저 단목 활성화 (직접 공격)"""
        from ..target_selection import target_selector
        
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        # 적 대상만 선택 가능
        channel_id = str(interaction.channel.id)
        targets = await target_selector.get_available_targets(channel_id, "단목", str(interaction.user.id))
        enemy_targets = [t for t in targets if t["type"] in ["monster", "admin"]]
        
        if not enemy_targets:
            await interaction.followup.send("❌ 공격할 수 있는 적이 없습니다.", ephemeral=True)
            return
        
        async def on_target_selected(target_interaction, selected_target):
            target_name = selected_target["name"]
            
            # 방어 무시 -30 데미지 즉시 적용
            try:
                from battle_admin import damage_user, send_battle_message
                
                await send_battle_message(
                    channel_id,
                    f"🏹 **사슴신의 바람 화살이 손에 쥐어집니다.**\n"
                    f"🎯 {target_name}에게 방어 무시 공격!\n"
                    f"💥 확정 피해: -30 HP"
                )
                
                # 실제 피해 적용
                await damage_user(channel_id, selected_target["id"], 30)
                
                # 스킬 상태 저장
                from ..skill_manager import skill_manager
                success = skill_manager.add_skill(
                    channel_id, "단목", str(interaction.user.id),
                    interaction.user.display_name, selected_target["id"], target_name, duration
                )
                
                embed = discord.Embed(
                    title="🏹 단목 화살 명중!",
                    description=f"**{target_name}**에게 단목의 관통 화살이 명중했습니다!\n\n"
                               f"💥 **피해량**: -30 HP (방어 무시)\n"
                               f"🏹 **관통력**: 모든 방어 효과 무시\n"
                               f"⏱️ **지속시간**: {duration}라운드",
                    color=discord.Color.green()
                )
                
                await target_interaction.followup.send(embed=embed)
                
            except Exception as e:
                logger.error(f"단목 직접 공격 실패: {e}")
                await target_interaction.followup.send("❌ 공격 실행 중 오류가 발생했습니다.", ephemeral=True)
        
        if len(enemy_targets) == 1:
            await on_target_selected(interaction, enemy_targets[0])
        else:
            from ..target_selection import TargetSelectionView
            embed = discord.Embed(
                title="🏹 단목 - 대상 선택",
                description="공격할 적을 선택하세요.",
                color=discord.Color.green()
            )
            view = TargetSelectionView(enemy_targets, on_target_selected)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def process_penetration_dice(self, channel_id: str, user_id: str, dice_value: int) -> bool:
        """관통 주사위 처리"""
        from ..skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        danmok_effect = channel_state.get("special_effects", {}).get("danmok_penetration")
        
        if not danmok_effect:
            return False
        
        # 주사위 결과 저장
        danmok_effect["dice_results"][str(user_id)] = dice_value
        
        # 턴 순서에 추가
        if str(user_id) not in danmok_effect["turn_order"]:
            danmok_effect["turn_order"].append(str(user_id))
        
        skill_manager.mark_dirty(channel_id)
        
        # 모든 유저가 굴렸는지 확인
        try:
            from battle_admin import get_battle_participants
            participants = await get_battle_participants(channel_id)
            total_users = len([u for u in participants.get("users", []) if not u.get("is_dead")])
            
            if len(danmok_effect["dice_results"]) >= total_users:
                # 관통 공격 실행
                await self._execute_penetration_attack(channel_id, danmok_effect)
                del channel_state["special_effects"]["danmok_penetration"]
                skill_manager.mark_dirty(channel_id)
            
            return True
            
        except Exception as e:
            logger.error(f"단목 관통 처리 실패: {e}")
            return False
    
    async def _execute_penetration_attack(self, channel_id: str, danmok_data: dict):
        """관통 공격 실행"""
        try:
            from battle_admin import send_battle_message, damage_user, get_user_info
            
            dice_results = danmok_data["dice_results"]
            turn_order = danmok_data["turn_order"]
            
            # 50 미만인 유저들 찾기
            direct_hits = []
            for user_id, dice_value in dice_results.items():
                if dice_value < 50:
                    direct_hits.append({
                        "user_id": user_id,
                        "dice_value": dice_value,
                        "position": turn_order.index(user_id) if user_id in turn_order else 999
                    })
            
            if not direct_hits:
                await send_battle_message(
                    channel_id,
                    "🏹 **단목의 화살이 모든 대상을 빗나갔습니다!** (모든 주사위 50 이상)"
                )
                return
            
            # 턴 순서대로 정렬
            direct_hits.sort(key=lambda x: x["position"])
            
            await send_battle_message(
                channel_id,
                f"🏹 **단목 관통 결과**\n"
                f"🎯 직접 피격 대상: {len(direct_hits)}명"
            )
            
            # 관통 공격 처리
            for i, hit in enumerate(direct_hits):
                user_info = await get_user_info(channel_id, hit["user_id"])
                user_name = user_info["display_name"] if user_info else "대상"
                
                # 직접 피격 처리
                await send_battle_message(
                    channel_id,
                    f"💥 **{user_name}** 직접 피격! (주사위: {hit['dice_value']}) → -20 HP"
                )
                await damage_user(channel_id, hit["user_id"], 20)
                
                # 관통 피격 처리 (다음 유저)
                next_position = hit["position"] + 1
                if next_position < len(turn_order):
                    next_user_id = turn_order[next_position]
                    next_user_info = await get_user_info(channel_id, next_user_id)
                    next_user_name = next_user_info["display_name"] if next_user_info else "대상"
                    
                    await send_battle_message(
                        channel_id,
                        f"🔄 **{next_user_name}** 관통 피격! → -10 HP"
                    )
                    await damage_user(channel_id, next_user_id, 10)
                
        except Exception as e:
            logger.error(f"단목 관통 공격 실행 실패: {e}")
    
    async def _is_monster_or_admin(self, user) -> bool:
        """몬스터나 ADMIN인지 확인"""
        from ..skill_manager import skill_manager
        return skill_manager.is_admin(str(user.id), user.display_name)
