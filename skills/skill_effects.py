# skills/skill_effects.py - Phase 2 업데이트
import logging
import asyncio
import random
from typing import Dict, Any, List, Optional, Tuple
from .skill_manager import skill_manager

logger = logging.getLogger(__name__)

class SkillEffects:
    """공통 스킬 효과 처리 클래스 (Phase 2 - 전체 스킬 지원)"""
    
    def __init__(self):
        self._effect_cache: Dict[str, Any] = {}
        self._damage_share_cache: Dict[str, List] = {}
    
    async def process_dice_roll(self, user_id: str, dice_value: int, channel_id: str) -> Tuple[int, List[str]]:
        """주사위 굴림 처리 및 모든 활성 스킬 효과 적용"""
        messages = []
        final_value = dice_value
        
        channel_state = skill_manager.get_channel_state(str(channel_id))
        active_skills = channel_state.get("active_skills", {})
        
        if not active_skills:
            return final_value, messages
        
        context = {
            "channel_id": channel_id,
            "user_id": user_id,
            "original_value": dice_value
        }
        
        # 스킬 우선순위에 따라 처리
        skill_priority = {
            # 1순위: 값 완전 변경
            "콜 폴드": 1,     # 0 또는 100으로 완전 변경
            # 2순위: 값 보정 (범위 제한)
            "오닉셀": 2,      # 50-150
            "스트라보스": 2,   # 75-150
            # 3순위: 값 감소
            "오리븐": 3,      # -10 감소
            # 4순위: 기타 효과들
            "카론": 4,        # 데미지 공유
            "황야": 4,        # 이중 행동
        }
        
        # 우선순위 순서로 스킬 효과 적용
        sorted_skills = sorted(
            [(name, data) for name, data in active_skills.items() if data["rounds_left"] > 0],
            key=lambda x: skill_priority.get(x[0], 999)
        )
        
        for skill_name, skill_data in sorted_skills:
            try:
                new_value, msg = await self._apply_skill_effect(
                    skill_name, user_id, final_value, skill_data, context
                )
                
                if new_value != final_value:
                    final_value = new_value
                    if msg:
                        messages.append(msg)
                        
            except Exception as e:
                logger.error(f"스킬 효과 적용 오류 {skill_name}: {e}")
        
        return final_value, messages
    
    async def _apply_skill_effect(self, skill_name: str, user_id: str, dice_value: int, 
                                skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """개별 스킬 효과 적용"""
        
        if skill_name == "오닉셀":
            return await self._apply_onixel_effect(user_id, dice_value, skill_data, context)
        elif skill_name == "스트라보스":
            return await self._apply_stravos_effect(user_id, dice_value, skill_data, context)
        elif skill_name == "콜 폴드":
            return await self._apply_coal_fold_effect(user_id, dice_value, skill_data, context)
        elif skill_name == "오리븐":
            return await self._apply_oriven_effect(user_id, dice_value, skill_data, context)
        
        return dice_value, None
    
    async def _apply_onixel_effect(self, user_id: str, dice_value: int, skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """오닉셀 효과: 50-150 범위로 보정"""
        if skill_data["user_id"] != str(user_id):
            return dice_value, None
        
        if 50 <= dice_value <= 150:
            return dice_value, None
        
        corrected_value = max(50, min(150, dice_value))
        message = f"🔥 **오닉셀의 안정화** 발동! 주사위 값이 {dice_value} → {corrected_value}로 보정되었습니다."
        
        logger.info(f"오닉셀 효과 적용 - 유저: {user_id}, {dice_value} → {corrected_value}")
        return corrected_value, message
    
    async def _apply_stravos_effect(self, user_id: str, dice_value: int, skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """스트라보스 효과: 75-150 범위로 보정"""
        if skill_data["user_id"] != str(user_id):
            return dice_value, None
        
        if 75 <= dice_value <= 150:
            return dice_value, None
        
        corrected_value = max(75, min(150, dice_value))
        message = f"⚔️ **스트라보스의 검술** 발동! 주사위 값이 {dice_value} → {corrected_value}로 보정되었습니다."
        
        logger.info(f"스트라보스 효과 적용 - 유저: {user_id}, {dice_value} → {corrected_value}")
        return corrected_value, message
    
    async def _apply_coal_fold_effect(self, user_id: str, dice_value: int, skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """콜 폴드 효과: 0 또는 100으로 변경 (40%:60%)"""
        if skill_data["user_id"] != str(user_id):
            return dice_value, None
        
        # 40% 확률로 0, 60% 확률로 100
        random_chance = random.randint(1, 100)
        
        if random_chance <= 40:
            corrected_value = 0
            result_type = "극한 실패"
        else:
            corrected_value = 100
            result_type = "극한 성공"
        
        message = f"🎲 **콜 폴드의 운명** 발동! {result_type}: {dice_value} → {corrected_value}"
        
        logger.info(f"콜 폴드 효과 적용 - 유저: {user_id}, {dice_value} → {corrected_value} ({result_type})")
        return corrected_value, message
    
    async def _apply_oriven_effect(self, user_id: str, dice_value: int, skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """오리븐 효과: -10 감소"""
        skill_user_id = skill_data["user_id"]
        is_skill_user_monster = skill_user_id in ["monster", "admin"]
        is_current_user_monster = user_id in ["monster", "admin"]
        
        should_apply = False
        
        if is_skill_user_monster and not is_current_user_monster:
            # 몬스터가 사용, 유저에게 적용
            should_apply = True
        elif not is_skill_user_monster and is_current_user_monster:
            # 유저가 사용, 몬스터에게 적용
            should_apply = True
        
        if not should_apply:
            return dice_value, None
        
        corrected_value = max(1, dice_value - 10)
        if corrected_value == dice_value:
            return dice_value, None
        
        effect_type = "저주" if is_skill_user_monster else "축복"
        message = f"⚫ **오리븐의 {effect_type}** 발동! 주사위 값이 {dice_value} → {corrected_value}로 감소했습니다."
        
        logger.info(f"오리븐 효과 적용 - 대상: {user_id}, {dice_value} → {corrected_value}")
        return corrected_value, message
    
    async def process_damage_sharing(self, channel_id: str, damaged_user_id: str, damage_amount: int) -> Dict[str, int]:
        """데미지 공유 처리 (카론, 스카넬 스킬)"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        active_skills = channel_state.get("active_skills", {})
        
        result = {damaged_user_id: damage_amount}
        
        # 카론 데미지 공유
        karon_skill = active_skills.get("카론")
        if karon_skill and karon_skill["rounds_left"] > 0:
            result = await self._apply_karon_sharing(channel_id, damaged_user_id, damage_amount, karon_skill)
        
        # 스카넬 데미지 공유
        scarnel_skill = active_skills.get("스카넬")
        if scarnel_skill and scarnel_skill["rounds_left"] > 0 and scarnel_skill["user_id"] == str(damaged_user_id):
            result = await self._apply_scarnel_sharing(channel_id, damaged_user_id, damage_amount, scarnel_skill)
        
        return result
    
    async def _apply_karon_sharing(self, channel_id: str, damaged_user_id: str, damage_amount: int, karon_skill: Dict) -> Dict[str, int]:
        """카론 데미지 공유 적용"""
        try:
            from battle_admin import get_battle_participants
            
            participants = await get_battle_participants(channel_id)
            skill_user_id = karon_skill["user_id"]
            is_skill_user_monster = skill_user_id in ["monster", "admin"]
            
            shared_damage = {}
            
            if is_skill_user_monster:
                # 몬스터가 사용: 모든 유저가 데미지 공유
                for user in participants.get("users", []):
                    if not user.get("is_dead"):
                        shared_damage[user["user_id"]] = damage_amount
            else:
                # 유저가 사용: 모든 참가자가 데미지 공유
                for user in participants.get("users", []):
                    if not user.get("is_dead"):
                        shared_damage[user["user_id"]] = damage_amount
                
                # 적도 포함
                if participants.get("monster"):
                    shared_damage["monster"] = damage_amount
                if participants.get("admin"):
                    shared_damage["admin"] = damage_amount
            
            logger.info(f"카론 데미지 공유 - 원본: {damage_amount}, 대상: {len(shared_damage)}명")
            return shared_damage
            
        except Exception as e:
            logger.error(f"카론 데미지 공유 실패: {e}")
            return {damaged_user_id: damage_amount}
    
    async def _apply_scarnel_sharing(self, channel_id: str, damaged_user_id: str, damage_amount: int, scarnel_skill: Dict) -> Dict[str, int]:
        """스카넬 데미지 공유 적용 (50:50 분할)"""
        target_id = scarnel_skill["target_id"]
        
        if target_id == damaged_user_id:
            # 자기 자신과 공유하는 경우는 공유하지 않음
            return {damaged_user_id: damage_amount}
        
        # 데미지를 절반씩 나눔
        shared_damage = damage_amount // 2
        remaining_damage = damage_amount - shared_damage
        
        result = {
            damaged_user_id: remaining_damage,
            target_id: shared_damage
        }
        
        logger.info(f"스카넬 데미지 공유 - 원본: {damage_amount}, 분배: {result}")
        return result
    
    async def check_action_blocked(self, channel_id: str, user_id: str, action_type: str) -> Dict[str, Any]:
        """행동 차단 여부 체크 (비렐라, 닉사라 등)"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        result = {
            "blocked": False,
            "reason": "",
            "alternative_action": None
        }
        
        # 비렐라 속박 체크
        virella_effect = special_effects.get("virella_bound")
        if virella_effect and virella_effect["target_id"] == str(user_id):
            result["blocked"] = True
            result["reason"] = "비렐라의 덩굴에 얽매여 행동할 수 없습니다."
        
        # 닉사라 시공 배제 체크
        nixara_effect = special_effects.get("nixara_excluded")
        if nixara_effect and nixara_effect["target_id"] == str(user_id):
            result["blocked"] = True
            result["reason"] = "닉사라의 시공 배제로 인해 행동할 수 없습니다."
        
        return result
    
    async def process_special_damage_effects(self, channel_id: str, user_id: str, base_damage: int) -> int:
        """특별 데미지 효과 처리 (제룬카 저주 등)"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        final_damage = base_damage
        
        # 제룬카 저주 효과
        jerrunka_curse = special_effects.get("jerrunka_curse")
        if jerrunka_curse and jerrunka_curse["target_id"] == str(user_id):
            bonus_damage = jerrunka_curse.get("damage_bonus", 20)
            final_damage += bonus_damage
            logger.info(f"제룬카 저주 추가 피해 - {user_id}: +{bonus_damage}")
        
        # 제룬카 개인/전체 강화 효과
        jerrunka_personal = special_effects.get("jerrunka_personal")
        if jerrunka_personal and jerrunka_personal["user_id"] == str(user_id):
            bonus_damage = jerrunka_personal.get("damage_bonus", 20)
            final_damage += bonus_damage
            logger.info(f"제룬카 개인 강화 - {user_id}: +{bonus_damage}")
        
        jerrunka_global = special_effects.get("jerrunka_global")
        if jerrunka_global and user_id not in ["monster", "admin"]:
            bonus_damage = jerrunka_global.get("damage_bonus", 20)
            final_damage += bonus_damage
            logger.info(f"제룬카 전체 강화 - {user_id}: +{bonus_damage}")
        
        return final_damage
    
    async def check_recovery_limits(self, channel_id: str, user_id: str) -> Dict[str, Any]:
        """회복 제한 체크 (황야 스킬 등)"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        result = {
            "allowed": True,
            "remaining_uses": 1,
            "reason": ""
        }
        
        # 황야 이중 행동 체크
        hwangya_effect = special_effects.get("hwangya_double_action")
        if hwangya_effect and hwangya_effect["user_id"] == str(user_id):
            actions_used = hwangya_effect.get("actions_used_this_turn", 0)
            max_actions = hwangya_effect.get("max_actions_per_turn", 2)
            
            if actions_used >= max_actions:
                result["allowed"] = False
                result["reason"] = "이번 턴에 더 이상 행동할 수 없습니다."
            else:
                result["remaining_uses"] = max_actions - actions_used
        
        return result
    
    async def update_skill_rounds(self, channel_id: str, round_increment: int = 1) -> List[str]:
        """스킬 라운드 업데이트 및 만료 처리"""
        expired_skills = []
        
        try:
            # 모든 스킬의 남은 라운드 감소
            for _ in range(round_increment):
                skill_manager.decrease_skill_rounds(channel_id)
            
            # 만료된 스킬 확인 및 제거
            channel_state = skill_manager.get_channel_state(str(channel_id))
            active_skills = channel_state.get("active_skills", {})
            
            skills_to_remove = []
            for skill_name, skill_data in active_skills.items():
                if skill_data["rounds_left"] <= 0:
                    skills_to_remove.append(skill_name)
                    expired_skills.append(skill_name)
            
            # 만료된 스킬들 제거 및 종료 처리
            for skill_name in skills_to_remove:
                await self._handle_skill_expiry(channel_id, skill_name)
                skill_manager.remove_skill(channel_id, skill_name)
            
            # 특별 효과들도 라운드 감소
            await self._update_special_effects_rounds(channel_id)
                
        except Exception as e:
            logger.error(f"스킬 라운드 업데이트 오류: {e}")
        
        return expired_skills
    
    async def _update_special_effects_rounds(self, channel_id: str):
        """특별 효과들의 라운드 업데이트"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        effects_to_remove = []
        
        for effect_name, effect_data in special_effects.items():
            if isinstance(effect_data, dict) and "rounds_left" in effect_data:
                effect_data["rounds_left"] -= 1
                
                if effect_data["rounds_left"] <= 0:
                    effects_to_remove.append(effect_name)
        
        # 만료된 특별 효과들 제거
        for effect_name in effects_to_remove:
            del special_effects[effect_name]
        
        if effects_to_remove:
            skill_manager.mark_dirty(channel_id)
    
    async def _handle_skill_expiry(self, channel_id: str, skill_name: str):
        """스킬 만료 처리"""
        try:
            from .heroes import get_skill_handler
            
            handler = get_skill_handler(skill_name)
            if handler:
                await handler.on_skill_end(channel_id, "system")
            
            # 특별 종료 처리들
            if skill_name == "스카넬":
                await self._trigger_scarnel_meteor(channel_id)
                
        except Exception as e:
            logger.error(f"스킬 만료 처리 오류 {skill_name}: {e}")
    
    async def _trigger_scarnel_meteor(self, channel_id: str):
        """스카넬 운석 공격 트리거"""
        try:
            from battle_admin import send_battle_message
            
            await send_battle_message(
                channel_id,
                "☄️ **스카넬의 운석 공격!**\n"
                "모든 참가자는 주사위를 굴려주세요! (50 미만 시 -20 피해)"
            )
            
            # 운석 공격 상태 설정
            channel_state = skill_manager.get_channel_state(str(channel_id))
            if "special_effects" not in channel_state:
                channel_state["special_effects"] = {}
                
            channel_state["special_effects"]["scarnel_meteor"] = {
                "active": True,
                "damage_on_fail": 20
            }
            skill_manager.mark_dirty(channel_id)
            
        except Exception as e:
            logger.error(f"스카넬 운석 공격 트리거 실패: {e}")
    
    def clear_cache(self):
        """캐시 정리"""
        self._effect_cache.clear()
        self._damage_share_cache.clear()

# 전역 인스턴스 (싱글톤)
skill_effects = SkillEffects()

# 편의 함수들 (Phase 2)
async def process_dice_with_skills(user_id: str, dice_value: int, channel_id: str) -> Tuple[int, List[str]]:
    """주사위 값에 스킬 효과 적용"""
    return await skill_effects.process_dice_roll(user_id, dice_value, channel_id)

async def process_damage_with_sharing(channel_id: str, user_id: str, damage: int) -> Dict[str, int]:
    """데미지에 공유 효과 적용"""
    return await skill_effects.process_damage_sharing(channel_id, user_id, damage)

async def check_action_allowed(channel_id: str, user_id: str, action_type: str = "attack") -> Dict[str, Any]:
    """행동 허용 여부 체크"""
    return await skill_effects.check_action_blocked(channel_id, user_id, action_type)

async def process_damage_with_effects(channel_id: str, user_id: str, base_damage: int) -> int:
    """데미지에 특별 효과 적용"""
    return await skill_effects.process_special_damage_effects(channel_id, user_id, base_damage)

async def check_recovery_allowed(channel_id: str, user_id: str) -> Dict[str, Any]:
    """회복 허용 여부 체크"""
    return await skill_effects.check_recovery_limits(channel_id, user_id)

async def update_all_skill_rounds(channel_id: str) -> List[str]:
    """모든 스킬 라운드 업데이트"""
    return await skill_effects.update_skill_rounds(channel_id)

async def force_end_skill(channel_id: str, skill_name: str):
    """스킬 강제 종료"""
    await skill_effects._handle_skill_expiry(channel_id, skill_name)
    skill_manager.remove_skill(channel_id, skill_name)
