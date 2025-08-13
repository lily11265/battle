# skills/skill_effects.py
"""
스킬 효과 처리 시스템
BaseSkill 기반의 통합 스킬 효과 처리
"""

import logging
import random
import asyncio
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

from .skill_manager import skill_manager
from skills.heroes import (
    get_skill_by_name, 
    get_skill_by_id,
    BaseSkill,
    SkillType,
    CasterType
)

logger = logging.getLogger(__name__)

class SkillEffects:
    """스킬 효과 처리 클래스"""
    
    def __init__(self):
        self._effect_cache: Dict[str, Any] = {}
        self._processing_lock = asyncio.Lock()
        self._initialized = False
        # 채널별 스킬 인스턴스 관리
        self._skill_instances: Dict[str, Dict[str, BaseSkill]] = {}
    
    async def initialize(self):
        """스킬 효과 시스템 초기화"""
        try:
            self._effect_cache.clear()
            self._skill_instances.clear()
            self._initialized = True
            logger.info("스킬 효과 시스템 초기화 완료")
        except Exception as e:
            logger.error(f"스킬 효과 시스템 초기화 실패: {e}")
            self._initialized = False
            raise
    
    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        return self._initialized
    
    async def clear_cache(self):
        """캐시 정리"""
        try:
            async with self._processing_lock:
                self._effect_cache.clear()
                logger.info("스킬 효과 캐시 정리 완료")
        except Exception as e:
            logger.error(f"캐시 정리 실패: {e}")
    
    def get_skill_instance(self, channel_id: str, skill_name: str) -> Optional[BaseSkill]:
        """채널별 스킬 인스턴스 가져오기"""
        if channel_id not in self._skill_instances:
            self._skill_instances[channel_id] = {}
        
        if skill_name not in self._skill_instances[channel_id]:
            # 스킬 클래스 가져오기
            skill_class = get_skill_by_name(skill_name)
            if skill_class:
                self._skill_instances[channel_id][skill_name] = skill_class()
        
        return self._skill_instances[channel_id].get(skill_name)
    
    async def process_dice_roll(self, user_id: str, dice_value: int, 
                               channel_id: str) -> Tuple[int, List[str]]:
        """주사위 굴림 시 모든 스킬 효과 적용"""
        try:
            if not self._initialized:
                logger.warning("스킬 효과 시스템이 초기화되지 않았습니다.")
                return dice_value, []
            
            async with self._processing_lock:
                user_id = str(user_id)
                channel_id = str(channel_id)
                
                channel_state = skill_manager.get_channel_state(channel_id)
                active_skills = channel_state.get("active_skills", {})
                mob_name = channel_state.get("mob_name", "")
                
                # 몬스터 체크
                is_monster = (
                    user_id.lower() in ["monster", "admin", "system"] or
                    user_id == mob_name
                )
                
                final_value = dice_value
                messages = []
                
                # 1. 행동 차단 체크
                block_check = await self.check_action_blocked(channel_id, user_id, "dice_roll")
                if block_check["blocked"]:
                    return 0, [block_check["reason"]]
                
                # 2. 모든 활성 스킬에 대해 효과 적용
                for skill_name, skill_data in active_skills.items():
                    skill_instance = self.get_skill_instance(channel_id, skill_name)
                    if not skill_instance:
                        continue
                    
                    # 스킬이 활성화되어 있는지 확인
                    if not skill_instance.active:
                        # 스킬 데이터에서 상태 복원
                        await self._restore_skill_state(skill_instance, skill_data)
                    
                    # apply_effect 메서드로 주사위 수정
                    modified_value = skill_instance.apply_effect(
                        target=final_value,
                        effect_type="dice_modifier",
                        user_id=user_id,
                        dice_owner=user_id,
                        dice_value=final_value,
                        is_monster=is_monster,
                        character_name=channel_state.get("character_name", "")
                    )
                    
                    if modified_value != final_value:
                        skill_status = skill_instance.get_status()
                        if skill_status:
                            effect_desc = skill_status.get("effect", "")
                            messages.append(f"✨ {skill_name}: {effect_desc}")
                        final_value = modified_value
                
                # 3. 특수 주사위 굴림 (운명의 주사위 등)
                for skill_name, skill_data in active_skills.items():
                    skill_instance = self.get_skill_instance(channel_id, skill_name)
                    if skill_instance and hasattr(skill_instance, 'roll_with_preset'):
                        # 자보라 같은 특수 주사위
                        result = skill_instance.apply_effect(
                            target=None,
                            effect_type="roll_dice",
                            dice_owner=user_id
                        )
                        if result and result.get("preset_applied"):
                            messages.append(result["message"])
                
                if messages:
                    if is_monster:
                        logger.info(f"몬스터({user_id}) 주사위 스킬 효과 적용: {dice_value} → {final_value}")
                    else:
                        logger.info(f"유저 {user_id} 주사위 스킬 효과 적용: {dice_value} → {final_value}")
                
                return final_value, messages
                
        except Exception as e:
            logger.error(f"주사위 효과 처리 실패: {e}")
            return dice_value, []
    
    async def _restore_skill_state(self, skill_instance: BaseSkill, skill_data: Dict):
        """스킬 상태 복원"""
        skill_instance.active = True
        skill_instance.caster_type = skill_data.get("caster_type", "user")
        skill_instance.caster_id = skill_data.get("user_id")
        skill_instance.remaining_rounds = skill_data.get("rounds_left", 0)
    
    async def check_action_blocked(self, channel_id: str, user_id: str, 
                                  action_type: str) -> Dict[str, Any]:
        """행동 차단 체크"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            
            # 각 스킬 인스턴스에서 차단 체크
            for skill_name in active_skills:
                skill_instance = self.get_skill_instance(channel_id, skill_name)
                if not skill_instance:
                    continue
                
                # 비렐라, 닉사라 등 차단 스킬 체크
                if skill_name == "비렐라":
                    result = skill_instance.apply_effect(
                        target=None,
                        effect_type="check_block",
                        user_id=user_id
                    )
                    if result and result.get("blocked"):
                        return result
                
                elif skill_name == "닉사라":
                    result = skill_instance.apply_effect(
                        target=None,
                        effect_type="check_excluded",
                        user_id=user_id
                    )
                    if result and result.get("blocked"):
                        return result
            
            return {"blocked": False}
            
        except Exception as e:
            logger.error(f"행동 차단 체크 실패: {e}")
            return {"blocked": False}
    
    async def process_damage_sharing(self, channel_id: str, victim_id: str,
                                    damage: int) -> Dict[str, int]:
        """데미지 공유 처리 (카론, 스카넬)"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            shared_damage = {}
            
            for skill_name in ["카론", "스카넬"]:
                if skill_name not in active_skills:
                    continue
                
                skill_instance = self.get_skill_instance(channel_id, skill_name)
                if not skill_instance:
                    continue
                
                result = skill_instance.apply_effect(
                    target=damage,
                    effect_type="damage_share",
                    victim_id=victim_id
                )
                
                if result and isinstance(result, dict):
                    shared_damage.update(result)
            
            return shared_damage
            
        except Exception as e:
            logger.error(f"데미지 공유 처리 실패: {e}")
            return {}
    
    async def update_skill_rounds(self, channel_id: str) -> List[str]:
        """스킬 라운드 업데이트 및 만료 처리"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            expired_skills = []
            messages = []
            
            for skill_name in list(channel_state.get("active_skills", {}).keys()):
                skill_instance = self.get_skill_instance(channel_id, skill_name)
                if not skill_instance:
                    continue
                
                # process_round 메서드 호출
                round_message = skill_instance.process_round()
                if round_message:
                    messages.append(round_message)
                
                # 스킬이 비활성화되었는지 확인
                if not skill_instance.active:
                    expired_skills.append(skill_name)
                    del channel_state["active_skills"][skill_name]
                else:
                    # 상태 업데이트
                    channel_state["active_skills"][skill_name]["rounds_left"] = skill_instance.remaining_rounds
            
            if expired_skills:
                skill_manager.mark_dirty(channel_id)
            
            return expired_skills
            
        except Exception as e:
            logger.error(f"스킬 라운드 업데이트 실패: {e}")
            return []
    
    async def process_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 특수 효과 처리"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            
            # 모든 활성 스킬의 라운드별 효과 처리
            for skill_name in active_skills:
                skill_instance = self.get_skill_instance(channel_id, skill_name)
                if not skill_instance:
                    continue
                
                # 라운드별 데미지 (반트로스 등)
                if hasattr(skill_instance, 'process_round_damage'):
                    damage_result = skill_instance.process_round_damage()
                    if damage_result:
                        # 실제 데미지 적용은 battle_admin에서 처리
                        logger.info(f"{skill_name}: {damage_result['message']}")
                
                # 추가 공격 체크 (리메스 등)
                if hasattr(skill_instance, 'should_extra_attack'):
                    if skill_instance.should_extra_attack():
                        extra_attack = skill_instance.get_extra_attack()
                        if extra_attack:
                            logger.info(f"{skill_name}: {extra_attack['message']}")
            
            skill_manager.mark_dirty(channel_id)
            
        except Exception as e:
            logger.error(f"라운드 시작 처리 실패: {e}")
    
    async def process_skill_activation(self, channel_id: str, skill_name: str,
                                      user_id: str, target_id: Optional[str],
                                      duration: int) -> Dict[str, Any]:
        """스킬 활성화 처리"""
        try:
            skill_instance = self.get_skill_instance(channel_id, skill_name)
            if not skill_instance:
                return {
                    "success": False,
                    "message": f"알 수 없는 스킬: {skill_name}"
                }
            
            # 활성화 가능 여부 체크
            can_activate = skill_instance.can_activate(
                caster_type="user" if user_id not in ["monster", "admin", "system"] else "monster"
            )
            
            if not can_activate["can_activate"]:
                return {
                    "success": False,
                    "message": can_activate["reason"]
                }
            
            # 스킬 활성화
            channel_state = skill_manager.get_channel_state(channel_id)
            battle_users = list(channel_state.get("battle_participants", {}).keys())
            
            result = await asyncio.create_task(
                skill_instance.activate(
                    caster_type="user" if user_id not in ["monster", "admin", "system"] else "monster",
                    duration=duration,
                    caster_id=user_id,
                    target_user=target_id,
                    battle_users=battle_users,
                    current_skill=channel_state.get("active_skills", {}).get(skill_name),
                    copy_skill=None,  # 이그나용
                    preset_value=None  # 자보라용
                )
            )
            
            if result["success"]:
                # 채널 상태에 스킬 추가
                if "active_skills" not in channel_state:
                    channel_state["active_skills"] = {}
                
                channel_state["active_skills"][skill_name] = {
                    "user_id": user_id,
                    "caster_type": skill_instance.caster_type,
                    "target_id": target_id,
                    "rounds_left": skill_instance.remaining_rounds,
                    "activated_at": datetime.now().isoformat()
                }
                
                skill_manager.mark_dirty(channel_id)
            
            return result
            
        except Exception as e:
            logger.error(f"스킬 활성화 처리 실패: {e}")
            return {
                "success": False,
                "message": f"스킬 활성화 실패: {str(e)}"
            }
    
    async def get_all_active_skills(self, channel_id: str) -> List[Dict[str, Any]]:
        """모든 활성 스킬 상태 가져오기"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            skill_statuses = []
            
            for skill_name in active_skills:
                skill_instance = self.get_skill_instance(channel_id, skill_name)
                if skill_instance:
                    status = skill_instance.get_status()
                    if status:
                        skill_statuses.append(status)
            
            return skill_statuses
            
        except Exception as e:
            logger.error(f"활성 스킬 상태 조회 실패: {e}")
            return []
    
    async def handle_user_death(self, channel_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """유저 사망 시 처리 (자동 부활 등)"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            
            # 아젤론 자동 부활 체크
            if "아젤론" in active_skills:
                skill_instance = self.get_skill_instance(channel_id, "아젤론")
                if skill_instance:
                    revive_result = skill_instance.apply_effect(
                        target=None,
                        effect_type="check_revive",
                        user_id=user_id
                    )
                    if revive_result and revive_result.get("revive"):
                        return revive_result
            
            # 피닉스 부활 체크
            if "피닉스" in active_skills:
                skill_instance = self.get_skill_instance(channel_id, "피닉스")
                if skill_instance:
                    revive_result = skill_instance.apply_effect(
                        target=None,
                        effect_type="check_revive",
                        user_id=user_id
                    )
                    if revive_result and revive_result.get("revive"):
                        return revive_result
            
            # 드레이언 더미 사망 체크
            if "드레이언" in active_skills:
                skill_instance = self.get_skill_instance(channel_id, "드레이언")
                if skill_instance:
                    dummy_result = skill_instance.apply_effect(
                        target=None,
                        effect_type="damage_dummy",
                        dummy_id=user_id,
                        damage=9999  # 사망
                    )
                    if dummy_result and dummy_result.get("caster_damage"):
                        return dummy_result
            
            return None
            
        except Exception as e:
            logger.error(f"유저 사망 처리 실패: {e}")
            return None
    
    async def cleanup_channel(self, channel_id: str):
        """채널 정리 (전투 종료 시)"""
        try:
            # 모든 스킬 인스턴스 리셋
            if channel_id in self._skill_instances:
                for skill_instance in self._skill_instances[channel_id].values():
                    skill_instance.reset()
                del self._skill_instances[channel_id]
            
            # 채널 상태 정리
            channel_state = skill_manager.get_channel_state(channel_id)
            channel_state["active_skills"] = {}
            channel_state["special_effects"] = {}
            skill_manager.mark_dirty(channel_id)
            
            logger.info(f"채널 {channel_id} 스킬 정리 완료")
            
        except Exception as e:
            logger.error(f"채널 정리 실패: {e}")

# 싱글톤 인스턴스
skill_effects = SkillEffects()