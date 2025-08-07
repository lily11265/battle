# skills/skill_effects.py
"""
공통 스킬 효과 처리 시스템
- 주사위 보정 시스템
- 데미지 계산
- 스킬 우선순위 처리
- 24시간 운영을 위한 성능 최적화
"""
import random
import logging
import asyncio
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from .skill_manager import skill_manager

logger = logging.getLogger(__name__)

@dataclass
class SkillEffect:
    """스킬 효과 데이터 클래스"""
    skill_name: str
    priority: int  # 낮을수록 높은 우선순위
    effect_type: str  # 'dice_modify', 'damage_modify', 'special'
    target_type: str  # 'self', 'target', 'all_users', 'all'

class SkillEffects:
    """스킬 효과 처리 시스템"""
    
    def __init__(self):
        # 성능 최적화를 위한 캐시
        self._dice_cache = {}
        self._effect_cache = {}
        self._priority_map = self._init_priority_map()
    
    def _init_priority_map(self) -> Dict[str, int]:
        """스킬 우선순위 맵 - 낮을수록 먼저 적용"""
        return {
            # 최우선 (완전 변경)
            "콜 폴드": 1,
            "그림": 1,
            "볼켄": 1,
            
            # 범위 보정 (중간 우선순위)
            "오닉셀": 2,
            "스트라보스": 2,
            
            # 추가/감소 (낮은 우선순위)
            "오리븐": 3,
            "제룬카": 3,
            "단목": 3,
            
            # 특수 효과 (별도 처리)
            "카론": 10,
            "황야": 10,
            "피닉스": 10,
            "비렐라": 10,
            "닉사라": 10,
            "스카넬": 10,
            "루센시아": 10,
            "넥시스": 10
        }
    
    async def process_dice_roll(self, user_id: str, original_value: int, 
                              channel_id: str) -> Tuple[int, List[str]]:
        """주사위 굴림 처리 - 모든 스킬 효과 적용"""
        try:
            messages = []
            final_value = original_value
            
            # 채널 상태 조회
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            special_effects = channel_state.get("special_effects", {})
            
            if not active_skills and not special_effects:
                return final_value, messages
            
            # 적용할 효과들 수집 및 우선순위 정렬
            effects_to_apply = []
            
            for skill_name, skill_data in active_skills.items():
                target_id = skill_data.get("target_id")
                
                # 효과 대상인지 체크
                if self._should_apply_effect(user_id, target_id, skill_name):
                    priority = self._priority_map.get(skill_name, 5)
                    effects_to_apply.append((priority, skill_name, skill_data))
            
            # 우선순위 정렬 (낮은 숫자가 먼저)
            effects_to_apply.sort(key=lambda x: x[0])
            
            # 효과들 순차 적용
            for priority, skill_name, skill_data in effects_to_apply:
                new_value, effect_message = await self._apply_skill_effect(
                    skill_name, skill_data, user_id, final_value, channel_state
                )
                
                if new_value != final_value:
                    final_value = new_value
                    if effect_message:
                        messages.append(effect_message)
            
            # 특수 효과들 처리
            final_value, special_messages = await self._apply_special_effects(
                user_id, final_value, special_effects
            )
            messages.extend(special_messages)
            
            return final_value, messages
            
        except Exception as e:
            logger.error(f"주사위 처리 실패 {user_id}: {e}")
            return original_value, []
    
    def _should_apply_effect(self, user_id: str, target_id: str, skill_name: str) -> bool:
        """효과 적용 대상 체크"""
        if target_id == user_id:
            return True
        elif target_id == "all_users" and user_id != "monster":
            return True
        elif target_id == "all":
            return True
        elif skill_name in ["오리븐", "카론"] and target_id == "all_users":
            return True
        
        return False
    
    async def _apply_skill_effect(self, skill_name: str, skill_data: Dict, 
                                 user_id: str, dice_value: int, 
                                 channel_state: Dict) -> Tuple[int, Optional[str]]:
        """개별 스킬 효과 적용"""
        try:
            caster_id = skill_data.get("user_id")
            
            if skill_name == "오닉셀":
                return self._apply_onixel_effect(dice_value, caster_id, user_id)
            
            elif skill_name == "스트라보스":
                return self._apply_stravos_effect(dice_value, caster_id, user_id)
            
            elif skill_name == "콜 폴드":
                return await self._apply_coal_fold_effect(dice_value, caster_id, user_id)
            
            elif skill_name == "오리븐":
                return self._apply_oriven_effect(dice_value, caster_id, user_id)
            
            elif skill_name == "제룬카":
                return await self._apply_jerrunka_effect(dice_value, channel_state, user_id)
            
            elif skill_name == "볼켄":
                return await self._apply_volken_effect(dice_value, channel_state, user_id)
            
            else:
                # 기타 스킬들은 별도 처리하지 않음
                return dice_value, None
            
        except Exception as e:
            logger.error(f"스킬 효과 적용 실패 {skill_name}: {e}")
            return dice_value, None
    
    def _apply_onixel_effect(self, dice_value: int, caster_id: str, 
                           user_id: str) -> Tuple[int, str]:
        """오닉셀 효과: 최대 150, 최소 50"""
        if user_id != caster_id:
            return dice_value, None
        
        new_value = max(50, min(150, dice_value))
        if new_value != dice_value:
            return new_value, f"🔥 오닉셀의 힘으로 주사위가 {new_value}로 보정됩니다!"
        
        return dice_value, None
    
    def _apply_stravos_effect(self, dice_value: int, caster_id: str, 
                            user_id: str) -> Tuple[int, str]:
        """스트라보스 효과: 최대 150, 최소 75"""
        if user_id != caster_id:
            return dice_value, None
        
        new_value = max(75, min(150, dice_value))
        if new_value != dice_value:
            return new_value, f"⚔️ 스트라보스의 힘으로 주사위가 {new_value}로 보정됩니다!"
        
        return dice_value, None
    
    async def _apply_coal_fold_effect(self, dice_value: int, caster_id: str, 
                                    user_id: str) -> Tuple[int, str]:
        """콜 폴드 효과: 0 (40%) 또는 100 (60%)"""
        if user_id != caster_id:
            return dice_value, None
        
        # 캐시 키 생성 (성능 최적화)
        cache_key = f"coal_fold_{user_id}_{dice_value}"
        if cache_key in self._dice_cache:
            cached_result = self._dice_cache[cache_key]
            return cached_result[0], cached_result[1]
        
        # 확률적 결과 결정
        rand_value = random.random()
        if rand_value < 0.4:  # 40% 확률로 0
            new_value = 0
            message = "💀 콜 폴드의 절망이 주사위를 0으로 만듭니다!"
        else:  # 60% 확률로 100
            new_value = 100
            message = "✨ 콜 폴드의 희망이 주사위를 100으로 만듭니다!"
        
        # 결과 캐싱 (메모리 효율성을 위해 제한)
        if len(self._dice_cache) < 100:
            self._dice_cache[cache_key] = (new_value, message)
        
        return new_value, message
    
    def _apply_oriven_effect(self, dice_value: int, caster_id: str, 
                           user_id: str) -> Tuple[int, str]:
        """오리븐 효과: 주사위 -10"""
        new_value = max(0, dice_value - 10)
        return new_value, f"🌀 오리븐의 바람으로 주사위가 -10됩니다! ({dice_value} → {new_value})"
    
    async def _apply_jerrunka_effect(self, dice_value: int, channel_state: Dict,
                                   user_id: str) -> Tuple[int, str]:
        """제룬카 효과: 공격력 -20 (복잡한 조건)"""
        special_effects = channel_state.get("special_effects", {})
        jerrunka_curse = special_effects.get("jerrunka_curse", {})
        
        if user_id in jerrunka_curse.get("affected_users", []):
            new_value = max(0, dice_value - 20)
            return new_value, f"😈 제룬카의 저주로 공격력이 -20됩니다! ({dice_value} → {new_value})"
        
        return dice_value, None
    
    async def _apply_volken_effect(self, dice_value: int, channel_state: Dict,
                                 user_id: str) -> Tuple[int, str]:
        """볼켄 효과: 화산 폭발 단계별 처리"""
        special_effects = channel_state.get("special_effects", {})
        volken_eruption = special_effects.get("volken_eruption", {})
        
        if not volken_eruption:
            return dice_value, None
        
        current_phase = volken_eruption.get("current_phase", 1)
        
        if 1 <= current_phase <= 3:
            # 1-3단계: 주사위 1로 고정
            return 1, f"🌋 볼켄의 화산재로 주사위가 1로 고정됩니다!"
        
        elif current_phase == 4:
            # 4단계: 50 미만 시 선별 목록에 추가
            if dice_value < 50:
                selected_targets = volken_eruption.get("selected_targets", [])
                if user_id not in selected_targets:
                    selected_targets.append(user_id)
                    volken_eruption["selected_targets"] = selected_targets
                
                return dice_value, f"🔥 볼켄의 타겟으로 선정되었습니다!"
        
        return dice_value, None
    
    async def _apply_special_effects(self, user_id: str, dice_value: int, 
                                   special_effects: Dict) -> Tuple[int, List[str]]:
        """특수 효과들 처리"""
        messages = []
        final_value = dice_value
        
        # 비렐라 배제 효과
        if "virella_bound" in special_effects:
            bound_users = special_effects["virella_bound"]
            if user_id in bound_users:
                return 0, ["🌿 비렐라의 속박으로 행동할 수 없습니다!"]
        
        # 닉사라 배제 효과
        if "nixara_excluded" in special_effects:
            excluded_users = special_effects["nixara_excluded"]
            if user_id in excluded_users:
                return 0, ["💫 닉사라의 차원 유배로 행동할 수 없습니다!"]
        
        return final_value, messages
    
    async def apply_damage_modification(self, base_damage: int, attacker_id: str,
                                      victim_id: str, channel_id: str) -> int:
        """데미지 수정 효과 적용"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            final_damage = base_damage
            
            # 카론 효과: 데미지 공유
            if "카론" in channel_state.get("active_skills", {}):
                final_damage = await self._apply_karon_damage_share(
                    final_damage, channel_state, victim_id
                )
            
            # 스카넬 효과: 데미지 공유
            if "스카넬" in channel_state.get("active_skills", {}):
                final_damage = await self._apply_scarnel_damage_share(
                    final_damage, channel_state, attacker_id, victim_id
                )
            
            return final_damage
            
        except Exception as e:
            logger.error(f"데미지 수정 실패: {e}")
            return base_damage
    
    async def _apply_karon_damage_share(self, damage: int, channel_state: Dict,
                                      victim_id: str) -> int:
        """카론 데미지 공유 효과"""
        # 구현 필요: 모든 참가자에게 동일한 데미지
        logger.info(f"카론 데미지 공유: {damage} 데미지를 모든 참가자에게")
        return damage
    
    async def _apply_scarnel_damage_share(self, damage: int, channel_state: Dict,
                                        attacker_id: str, victim_id: str) -> int:
        """스카넬 데미지 공유 효과"""
        # 구현 필요: 선택된 대상과 데미지 공유
        scarnel_skill = channel_state.get("active_skills", {}).get("스카넬", {})
        target_id = scarnel_skill.get("target_id")
        
        if target_id and target_id != victim_id:
            logger.info(f"스카넬 데미지 공유: {damage} 데미지를 {target_id}와 공유")
        
        return damage
    
    async def process_round_start(self, channel_id: str, round_num: int):
        """라운드 시작 시 특수 효과 처리"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            special_effects = channel_state.get("special_effects", {})
            
            # 그림 준비 처리
            if "grim_preparing" in special_effects:
                await self._process_grim_preparation(special_effects, round_num)
            
            # 볼켄 화산 폭발 처리
            if "volken_eruption" in special_effects:
                await self._process_volken_phases(special_effects, round_num)
            
            # 비렐라/닉사라 저항 굴림
            await self._process_exclusion_resistance(special_effects)
            
            skill_manager.mark_dirty(channel_id)
            
        except Exception as e:
            logger.error(f"라운드 시작 처리 실패: {e}")
    
    async def _process_grim_preparation(self, special_effects: Dict, round_num: int):
        """그림 준비 단계 처리"""
        grim_data = special_effects["grim_preparing"]
        grim_data["rounds_until_activation"] -= 1
        
        if grim_data["rounds_until_activation"] <= 0:
            # 그림 발동!
            logger.info("그림 스킬 발동 - 타겟 선정 중...")
            # 실제 구현에서는 가장 체력이 낮은 유저를 찾아 처리
            del special_effects["grim_preparing"]
    
    async def _process_volken_phases(self, special_effects: Dict, round_num: int):
        """볼켄 화산 폭발 단계 처리"""
        volken_data = special_effects["volken_eruption"]
        volken_data["rounds_left"] -= 1
        
        if volken_data["current_phase"] == 3 and volken_data["rounds_left"] == 2:
            # 4단계로 전환 (선별 단계)
            volken_data["current_phase"] = 4
            logger.info("볼켄 4단계 진입 - 타겟 선별 시작")
        
        elif volken_data["current_phase"] == 4 and volken_data["rounds_left"] == 1:
            # 5단계로 전환 (집중 공격 단계)
            volken_data["current_phase"] = 5
            logger.info("볼켄 5단계 진입 - 집중 공격 시작")
    
    async def _process_exclusion_resistance(self, special_effects: Dict):
        """배제 효과 저항 굴림 처리"""
        # 비렐라 저항 굴림
        if "virella_bound" in special_effects:
            bound_users = special_effects["virella_bound"]
            escaped_users = []
            
            for user_id in bound_users:
                resistance_roll = random.randint(1, 100)
                if resistance_roll >= 50:  # 50 이상 시 탈출
                    escaped_users.append(user_id)
                    logger.info(f"유저 {user_id} 비렐라 속박에서 탈출 ({resistance_roll})")
            
            for user_id in escaped_users:
                bound_users.remove(user_id)
            
            if not bound_users:
                del special_effects["virella_bound"]
    
    async def clear_cache(self):
        """캐시 정리 - 메모리 최적화"""
        self._dice_cache.clear()
        self._effect_cache.clear()
        logger.info("스킬 효과 캐시 정리 완료")
    
    def get_skill_priority(self, skill_name: str) -> int:
        """스킬 우선순위 조회"""
        return self._priority_map.get(skill_name, 5)
    
    async def validate_skill_state(self, channel_id: str) -> bool:
        """스킬 상태 유효성 검증"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            
            # 만료된 스킬 체크
            current_round = channel_state.get("current_round", 1)
            invalid_skills = []
            
            for skill_name, skill_data in active_skills.items():
                rounds_left = skill_data.get("rounds_left", 0)
                if rounds_left <= 0:
                    invalid_skills.append(skill_name)
            
            # 무효한 스킬 제거
            for skill_name in invalid_skills:
                skill_manager.remove_skill(channel_id, skill_name)
                logger.warning(f"만료된 스킬 제거: {skill_name}")
            
            return len(invalid_skills) == 0
            
        except Exception as e:
            logger.error(f"스킬 상태 검증 실패: {e}")
            return False

# 전역 인스턴스
skill_effects = SkillEffects()
