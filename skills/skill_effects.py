# skills/skill_effects.py
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from .skill_manager import skill_manager

logger = logging.getLogger(__name__)

class SkillEffects:
    """공통 스킬 효과 처리 클래스 (성능 최적화)"""
    
    def __init__(self):
        self._effect_cache: Dict[str, Any] = {}  # 효과 캐시
    
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
        
        # 스킬 우선순위에 따라 처리 (성능 최적화: 한 번만 순회)
        skill_priority = {
            "오닉셀": 1,      # 값 보정
            "스트라보스": 1,   # 값 보정 (Phase 2)
            "콜 폴드": 2,     # 확률 변경 (Phase 2)
            "오리븐": 3,      # 감소 효과
            "카론": 4,        # 데미지 공유 (실제로는 데미지 적용 시점에서 처리)
        }
        
        # 우선순위 순서로 스킬 효과 적용
        sorted_skills = sorted(
            [(name, data) for name, data in active_skills.items() if data["rounds_left"] > 0],
            key=lambda x: skill_priority.get(x[0], 999)
        )
        
        for skill_name, skill_data in sorted_skills:
            try:
                # 스킬별 주사위 효과 적용
                if skill_name == "오닉셀":
                    final_value, msg = await self._apply_onixel_effect(user_id, final_value, skill_data, context)
                elif skill_name == "오리븐":
                    final_value, msg = await self._apply_oriven_effect(user_id, final_value, skill_data, context)
                # Phase 2에서 추가 스킬들 구현
                
                if msg:
                    messages.append(msg)
                    
            except Exception as e:
                logger.error(f"스킬 효과 적용 오류 {skill_name}: {e}")
        
        return final_value, messages
    
    async def _apply_onixel_effect(self, user_id: str, dice_value: int, skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """오닉셀 효과 적용"""
        if skill_data["user_id"] != str(user_id):
            return dice_value, None
        
        if 50 <= dice_value <= 150:
            return dice_value, None
        
        corrected_value = max(50, min(150, dice_value))
        message = f"🔥 **오닉셀의 힘** 발동! 주사위 값이 {dice_value} → {corrected_value}로 보정되었습니다."
        
        logger.info(f"오닉셀 효과 적용 - 유저: {user_id}, {dice_value} → {corrected_value}")
        return corrected_value, message
    
    async def _apply_oriven_effect(self, user_id: str, dice_value: int, skill_data: Dict, context: Dict) -> Tuple[int, Optional[str]]:
        """오리븐 효과 적용"""
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
        """데미지 공유 처리 (카론 스킬)"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        karon_skill = channel_state.get("active_skills", {}).get("카론")
        
        if not karon_skill or karon_skill["rounds_left"] <= 0:
            return {damaged_user_id: damage_amount}
        
        # Phase 2에서 실제 전투 참가자 목록과 연동하여 구현
        logger.info(f"카론 스킬 데미지 공유 처리 - 원본 데미지: {damage_amount}")
        
        return {damaged_user_id: damage_amount}  # Phase 1에서는 단순 반환
    
    async def check_special_conditions(self, channel_id: str, user_id: str, action_type: str) -> Dict[str, Any]:
        """특별 조건 체크 (비렐라, 닉사라 등의 배제 효과)"""
        channel_state = skill_manager.get_channel_state(str(channel_id))
        special_effects = channel_state.get("special_effects", {})
        
        result = {
            "blocked": False,
            "reason": "",
            "alternative_action": None
        }
        
        # Phase 2에서 구현 예정
        # - 비렐라 배제 체크
        # - 닉사라 배제 체크
        # - 기타 행동 제한 효과들
        
        return result
    
    async def update_skill_rounds(self, channel_id: str, round_increment: int = 1) -> List[str]:
        """스킬 라운드 업데이트 및 만료 처리"""
        expired_skills = []
        
        try:
            # 모든 스킬의 남은 라운드 감소
            for _ in range(round_increment):
                skill_manager.decrease_skill_rounds(channel_id)
            
            # 만료된 스킬 확인 및 제거
            expired_skills = skill_manager.update_round(channel_id, 0)  # 라운드 번호는 별도 관리
            
            # 만료된 스킬들의 종료 처리
            for skill_name in expired_skills:
                await self._handle_skill_expiry(channel_id, skill_name)
                
        except Exception as e:
            logger.error(f"스킬 라운드 업데이트 오류: {e}")
        
        return expired_skills
    
    async def _handle_skill_expiry(self, channel_id: str, skill_name: str):
        """스킬 만료 처리"""
        try:
            from .heroes import get_skill_handler
            
            handler = get_skill_handler(skill_name)
            if handler:
                await handler.on_skill_end(channel_id, "system")
                
        except Exception as e:
            logger.error(f"스킬 만료 처리 오류 {skill_name}: {e}")
    
    def clear_cache(self):
        """캐시 정리"""
        self._effect_cache.clear()

# 전역 인스턴스 (싱글톤)
skill_effects = SkillEffects()

# 편의 함수들
async def process_dice_with_skills(user_id: str, dice_value: int, channel_id: str) -> Tuple[int, List[str]]:
    """주사위 값에 스킬 효과 적용"""
    return await skill_effects.process_dice_roll(user_id, dice_value, channel_id)

async def process_damage_with_sharing(channel_id: str, user_id: str, damage: int) -> Dict[str, int]:
    """데미지에 공유 효과 적용"""
    return await skill_effects.process_damage_sharing(channel_id, user_id, damage)

async def update_all_skill_rounds(channel_id: str) -> List[str]:
    """모든 스킬 라운드 업데이트"""
    return await skill_effects.update_skill_rounds(channel_id)