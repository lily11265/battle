# skills/skill_effects.py
"""
스킬 효과 처리 시스템
주사위 보정, 데미지 계산, 특수 효과 등 모든 스킬 효과 처리
"""
import logging
import random
import asyncio
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from .skill_manager import skill_manager
from .heroes import get_skill_handler, get_skill_priority

logger = logging.getLogger(__name__)

class SkillEffects:
    """스킬 효과 처리 클래스"""
    
    def __init__(self):
        self._effect_cache: Dict[str, Any] = {}
        self._processing_lock = asyncio.Lock()
        self._initialized = False  # 이 라인 추가

    async def initialize(self):
        """스킬 효과 시스템 초기화"""
        try:
            self._effect_cache.clear()
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

    async def process_dice_roll(self, user_id: str, dice_value: int, 
                            channel_id: str) -> Tuple[int, List[str]]:
        """주사위 굴림 시 모든 스킬 효과 적용"""
        try:
            # 초기화 체크 추가
            if not self._initialized:
                logger.warning("스킬 효과 시스템이 초기화되지 않았습니다.")
                return dice_value, []
            
            async with self._processing_lock:
                user_id = str(user_id)
                channel_id = str(channel_id)
                
                channel_state = skill_manager.get_channel_state(channel_id)
                active_skills = channel_state.get("active_skills", {})
                special_effects = channel_state.get("special_effects", {})
                
                # 몬스터 체크 - 실제 몹 이름도 확인
                mob_name = channel_state.get("mob_name", "")
                is_monster = (
                    user_id.lower() in ["monster", "admin", "system"] or
                    user_id == mob_name  # 실제 몹 이름과 비교
                )
                
                final_value = dice_value
                messages = []
                
                # 1. 행동 차단 체크 (비렐라, 닉사라)
                block_check = await self.check_action_blocked(channel_id, user_id, "dice_roll")
                if block_check["blocked"]:
                    return 0, [block_check["reason"]]
                
                # 2. 스킬 우선순위대로 적용
                sorted_skills = sorted(active_skills.items(), 
                                    key=lambda x: get_skill_priority(x[0]))
                
                for skill_name, skill_data in sorted_skills:
                    # 스킬 사용자 확인
                    skill_user_id = skill_data.get("user_id", "")
                    
                    # 스킬이 몬스터 것인지 확인 (실제 몹 이름 포함)
                    skill_is_from_monster = (
                        skill_user_id.lower() in ["monster", "admin", "system"] or
                        skill_user_id == mob_name
                    )
                    
                    # 스킬 적용 조건 확인
                    should_apply = False
                    
                    if skill_is_from_monster and is_monster:
                        # 몬스터가 사용한 스킬이고 몬스터 주사위
                        if skill_name in ["오닉셀", "피닉스", "콜 폴드", "황야", "스트라보스"]:
                            should_apply = True
                            logger.debug(f"몬스터 자체 버프 스킬 {skill_name} 적용 - user_id: {user_id}")
                    elif skill_is_from_monster and not is_monster:
                        # 몬스터가 사용한 스킬이고 유저 주사위
                        if skill_name in ["오리븐", "카론", "스카넬", "비렐라", "그림", "닉사라", "볼켄"]:
                            should_apply = True
                            logger.debug(f"몬스터→유저 디버프 스킬 {skill_name} 적용")
                    elif not skill_is_from_monster and is_monster:
                        # 유저가 사용한 스킬이고 몬스터 주사위
                        if skill_name in ["오리븐", "카론", "스카넬"]:
                            should_apply = True
                            logger.debug(f"유저→몬스터 디버프 스킬 {skill_name} 적용")
                    elif not skill_is_from_monster and not is_monster:
                        # 유저가 사용한 스킬이고 유저 주사위
                        if skill_user_id == user_id:
                            should_apply = True
                            logger.debug(f"유저 자체 스킬 {skill_name} 적용")
                    
                    if should_apply:
                        new_value, message = await self._apply_skill_effect(
                            skill_name, skill_data, user_id, final_value, channel_state
                        )
                        
                        if new_value != final_value:
                            final_value = new_value
                            if message:
                                # 몬스터용 메시지 커스터마이징
                                if is_monster:
                                    message = message.replace("유저", mob_name)
                                messages.append(message)
                
                # 3. 특수 효과 처리
                final_value, special_messages = await self._apply_special_effects(
                    user_id, final_value, special_effects
                )
                messages.extend(special_messages)
                
                # 로깅
                if is_monster and messages:
                    logger.info(f"몬스터({user_id}) 주사위 스킬 효과 적용: {dice_value} → {final_value}")
                elif messages:
                    logger.info(f"유저 {user_id} 주사위 스킬 효과 적용: {dice_value} → {final_value}")
                
                return final_value, messages
                
        except Exception as e:
            logger.error(f"주사위 효과 처리 실패: {e}")
            return dice_value, []

    async def _apply_skill_effect_with_context(self, skill_name: str, skill_data: Dict,
                                            user_id: str, dice_value: int,
                                            channel_state: Dict, context: Dict) -> Tuple[int, str]:
        """컨텍스트를 포함한 스킬 효과 적용"""
        try:
            from .heroes import get_skill_handler
            
            handler = get_skill_handler(skill_name)
            if not handler:
                return dice_value, ""
            
            # 스킬 핸들러의 on_dice_roll 호출
            new_value = await handler.on_dice_roll(user_id, dice_value, context)
            
            message = ""
            if new_value != dice_value:
                # 몬스터용 메시지 생성
                if context.get("is_monster"):
                    monster_name = channel_state.get("mob_name", "몬스터")
                    if context.get("skill_is_from_monster"):
                        message = f"⚔️ **{monster_name}**의 **{skill_name}** 효과 발동! 주사위: {dice_value} → {new_value}"
                    else:
                        message = f"🛡️ **{skill_name}** 효과로 **{monster_name}**의 주사위 변경! {dice_value} → {new_value}"
                else:
                    message = f"✨ **{skill_name}** 효과 발동! 주사위: {dice_value} → {new_value}"
            
            return new_value, message
            
        except Exception as e:
            logger.error(f"스킬 효과 적용 실패 ({skill_name}): {e}")
            return dice_value, ""
    
    async def _apply_skill_effect(self, skill_name: str, skill_data: Dict,
                                user_id: str, dice_value: int,
                                channel_state: Dict) -> Tuple[int, Optional[str]]:
        """개별 스킬 효과 적용"""
        try:
            caster_id = skill_data.get("user_id")
            target_id = skill_data.get("target_id")
            
            # === 자기 자신에게만 적용되는 스킬들 ===
            
            if skill_name == "오닉셀" and user_id == caster_id:
                new_value = max(50, min(150, dice_value))
                if new_value != dice_value:
                    return new_value, f"🔥 오닉셀의 힘으로 주사위가 {new_value}로 보정됩니다!"
            
            elif skill_name == "스트라보스" and user_id == caster_id:
                new_value = max(75, min(150, dice_value))
                if new_value != dice_value:
                    return new_value, f"⚔️ 스트라보스의 힘으로 주사위가 {new_value}로 보정됩니다!"
            
            elif skill_name == "콜 폴드" and user_id == caster_id:
                # 40% 확률로 0, 60% 확률로 100
                result = 0 if random.random() < 0.4 else 100
                return result, f"🎲 콜 폴드 발동! 주사위가 {result}로 고정됩니다!"
            
            elif skill_name == "그림" and user_id == caster_id:
                # 그림 스킬: 주사위 1로 고정
                return 1, f"🎨 그림의 저주로 주사위가 1로 고정됩니다!"
            
            elif skill_name == "로바" and user_id == caster_id:
                # 로바 스킬: 주사위를 100으로 고정
                return 100, f"👑 로바의 축복으로 주사위가 100으로 상승합니다!"
            
            elif skill_name == "스카넬" and user_id == caster_id:
                # 스카넬 스킬: 주사위 * 2 (최대 200)
                new_value = min(200, dice_value * 2)
                if new_value != dice_value:
                    return new_value, f"⚡ 스카넬의 전류로 주사위가 {new_value}로 증폭됩니다!"
            
            # === 대상 지정 스킬들 ===
            
            elif skill_name == "비렐라" and user_id == target_id:
                # 비렐라 스킬: 대상의 주사위를 0으로 만듦
                return 0, f"❄️ 비렐라의 빙결로 행동이 봉쇄됩니다!"
            
            # === 전역 효과 스킬들 ===
            
            elif skill_name == "오리븐":
                # 🔧 수정: 이 스킬은 새로운 핸들러 시스템(skills/heroes/oriven.py)에서 처리
                # 중복 처리 방지를 위해 여기서는 건너뜀
                # 실제 효과와 메시지는 OrivenHandler.on_dice_roll()에서 처리됨
                pass
            
            elif skill_name == "볼켄":
                # 볼켄 스킬: 1-3라운드 동안 모든 주사위 1로 고정
                volken_data = channel_state.get("special_effects", {}).get("volken_eruption", {})
                current_phase = volken_data.get("current_phase", 0)
                if 1 <= current_phase <= 3:
                    return 1, f"🌋 볼켄의 화산재로 주사위가 1로 고정됩니다! (단계 {current_phase}/6)"
            
            elif skill_name == "젤다":
                # 젤다 스킬: 모든 주사위를 50으로 고정
                return 50, f"🔮 젤다의 마법으로 주사위가 50으로 안정화됩니다!"
            
            elif skill_name == "닉사라":
                # 닉사라 스킬: 대결 시스템에서 처리
                # 여기서는 일반적인 주사위 효과만 처리
                nixara_duel = channel_state.get("special_effects", {}).get("nixara_duel")
                if nixara_duel:
                    # 대결 참가자인 경우 별도 처리 (닉사라 핸들러에서 처리)
                    attacker_id = nixara_duel.get("attacker_id")
                    defender_id = nixara_duel.get("defender_id")
                    if user_id in [attacker_id, defender_id]:
                        # 대결 시스템에서 처리하므로 여기서는 패스
                        pass
            
            elif skill_name == "카론":
                # 카론 스킬: 데미지 공유 (주사위에는 직접적인 영향 없음)
                # 실제 데미지 공유는 전투 시스템에서 처리
                pass
            
            elif skill_name == "넥시스":
                # 넥시스 스킬: 확정 데미지 (주사위에는 영향 없음)
                # 실제 효과는 전투 시스템에서 처리
                pass
            
            # === 특수 효과들 ===
            
            # 다른 스킬들의 특수 효과도 여기서 처리할 수 있음
            # 예: 상태 이상, 버프/디버프 등
            
        except Exception as e:
            logger.error(f"스킬 효과 적용 실패 ({skill_name}): {e}")
            import traceback
            traceback.print_exc()
        
        # 변화가 없는 경우 원본 값과 None 반환
        return dice_value, None
    
    async def _apply_special_effects(self, user_id: str, dice_value: int,
                                    special_effects: Dict) -> Tuple[int, List[str]]:
        """특수 효과 적용"""
        messages = []
        final_value = dice_value
        
        try:
            # 비렐라 저항 굴림
            if "virella_bound" in special_effects:
                bound_users = special_effects["virella_bound"]
                if user_id in bound_users:
                    if dice_value >= 50:
                        bound_users.remove(user_id)
                        messages.append("🌿 비렐라의 속박에서 벗어났습니다!")
                    else:
                        final_value = 0
                        messages.append("🌿 비렐라의 속박으로 행동할 수 없습니다!")
            
            # 닉사라 배제
            if "nixara_excluded" in special_effects:
                excluded_data = special_effects["nixara_excluded"]
                if user_id in excluded_data:
                    final_value = 0
                    messages.append("💫 닉사라의 차원 유배로 행동할 수 없습니다!")
            
            # 제룬카 효과
            if "jerrunka_active" in special_effects:
                jerrunka_data = special_effects["jerrunka_active"]
                if jerrunka_data.get("target_id") == user_id:
                    # 타겟된 유저는 추가 데미지
                    messages.append("🔴 제룬카의 표적이 되어 추가 피해를 받습니다!")
            
            # 단목 관통 처리
            if "danmok_penetration" in special_effects:
                if dice_value < 50:
                    messages.append("⚡ 단목의 관통 공격 발동!")
                    special_effects["danmok_penetration"]["targets"].append(user_id)
            
        except Exception as e:
            logger.error(f"특수 효과 적용 실패: {e}")
        
        return final_value, messages
    
    async def check_action_blocked(self, channel_id: str, user_id: str, 
                                  action_type: str) -> Dict[str, Any]:
        """행동 차단 체크"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            special_effects = channel_state.get("special_effects", {})
            
            # 비렐라 속박
            if "virella_bound" in special_effects:
                if user_id in special_effects["virella_bound"]:
                    return {
                        "blocked": True,
                        "reason": "비렐라의 속박으로 행동할 수 없습니다!",
                        "skill": "virella"
                    }
            
            # 닉사라 배제
            if "nixara_excluded" in special_effects:
                excluded_data = special_effects["nixara_excluded"]
                if user_id in excluded_data:
                    return {
                        "blocked": True,
                        "reason": "닉사라의 차원 유배로 행동할 수 없습니다!",
                        "skill": "nixara"
                    }
            
            # 황야 이중 행동 체크 (회복 명령어용)
            if action_type == "recovery" and "hwangya_double_action" in special_effects:
                hwangya_data = special_effects["hwangya_double_action"]
                if hwangya_data["user_id"] == user_id:
                    if hwangya_data.get("actions_used_this_turn", 0) >= 2:
                        return {
                            "blocked": True,
                            "reason": "이번 턴에 이미 2번 행동했습니다!",
                            "skill": "hwangya"
                        }
            
            return {"blocked": False}
            
        except Exception as e:
            logger.error(f"행동 차단 체크 실패: {e}")
            return {"blocked": False}
    
    async def check_recovery_allowed(self, channel_id: str, user_id: str) -> Dict[str, Any]:
        """회복 가능 여부 체크 (황야 스킬용)"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            special_effects = channel_state.get("special_effects", {})
            
            if "hwangya_double_action" in special_effects:
                hwangya_data = special_effects["hwangya_double_action"]
                if hwangya_data["user_id"] == user_id:
                    actions_used = hwangya_data.get("actions_used_this_turn", 0)
                    if actions_used < 2:
                        return {"allowed": True, "remaining_actions": 2 - actions_used}
                    else:
                        return {
                            "allowed": False,
                            "reason": "이번 턴의 모든 행동을 사용했습니다."
                        }
            
            return {"allowed": True}
            
        except Exception as e:
            logger.error(f"회복 가능 체크 실패: {e}")
            return {"allowed": True}
    
    async def process_damage_sharing(self, channel_id: str, victim_id: str,
                                    damage: int) -> Dict[str, int]:
        """데미지 공유 처리 (카론, 스카넬)"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            active_skills = channel_state.get("active_skills", {})
            shared_damage = {}
            
            # 카론 효과
            if "카론" in active_skills:
                karon_data = active_skills["카론"]
                # 모든 살아있는 대상에게 데미지 공유
                # 실제 구현 시 battle_admin과 연동 필요
                shared_damage["all_alive"] = damage
                logger.info(f"카론 효과: 모든 대상에게 {damage} 데미지 공유")
            
            # 스카넬 효과
            if "스카넬" in active_skills:
                scarnel_data = active_skills["스카넬"]
                if scarnel_data["user_id"] == victim_id:
                    target_id = scarnel_data["target_id"]
                    if target_id:
                        shared_damage[target_id] = damage // 2
                        logger.info(f"스카넬 효과: {target_id}에게 {damage//2} 데미지 공유")
            
            return shared_damage
            
        except Exception as e:
            logger.error(f"데미지 공유 처리 실패: {e}")
            return {}
    
    async def update_skill_rounds(self, channel_id: str) -> List[str]:
        """스킬 라운드 업데이트 및 만료 처리"""
        try:
            channel_state = skill_manager.get_channel_state(channel_id)
            expired_skills = []
            
            for skill_name, skill_data in list(channel_state["active_skills"].items()):
                skill_data["rounds_left"] -= 1
                
                if skill_data["rounds_left"] <= 0:
                    expired_skills.append(skill_name)
                    
                    # 스킬 종료 이벤트 호출
                    handler = get_skill_handler(skill_name)
                    if handler:
                        await handler.on_skill_end(channel_id, skill_data["user_id"])
                    
                    del channel_state["active_skills"][skill_name]
            
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
            special_effects = channel_state.get("special_effects", {})
            active_skills = channel_state.get("active_skills", {})
            
            # 그림 준비 단계 처리
            if "grim_preparing" in special_effects:
                grim_data = special_effects["grim_preparing"]
                grim_data["rounds_until_activation"] -= 1
                
                if grim_data["rounds_until_activation"] <= 0:
                    # 그림 발동!
                    await self._execute_grim_attack(channel_id, grim_data)
                    del special_effects["grim_preparing"]
            
            # 볼켄 단계 진행
            if "volken_eruption" in special_effects:
                volken_data = special_effects["volken_eruption"]
                volken_data["current_phase"] += 1
                
                if volken_data["current_phase"] == 4:
                    # 선별 단계 시작
                    volken_data["selected_targets"] = []
                elif volken_data["current_phase"] > 5:
                    # 볼켄 종료
                    del special_effects["volken_eruption"]
            
            # 비렐라/닉사라 지속 시간 감소
            if "virella_bound" in special_effects:
                # 3라운드 후 자동 해제
                pass
            
            if "nixara_excluded" in special_effects:
                excluded_data = special_effects["nixara_excluded"]
                for user_id in list(excluded_data.keys()):
                    excluded_data[user_id]["rounds_left"] -= 1
                    if excluded_data[user_id]["rounds_left"] <= 0:
                        del excluded_data[user_id]
            
            # 모든 활성 스킬의 라운드 시작 이벤트
            for skill_name in active_skills:
                handler = get_skill_handler(skill_name)
                if handler:
                    await handler.on_round_start(channel_id, round_num)
            
            skill_manager.mark_dirty(channel_id)
            
        except Exception as e:
            logger.error(f"라운드 시작 처리 실패: {e}")
    
    async def _execute_grim_attack(self, channel_id: str, grim_data: Dict):
        """그림 공격 실행"""
        try:
            # 피닉스 방어 체크
            channel_state = skill_manager.get_channel_state(channel_id)
            if "피닉스" in channel_state.get("active_skills", {}):
                logger.info("피닉스가 그림 공격을 방어했습니다!")
                return
            
            # 타겟 선택 로직 (battle_admin과 연동 필요)
            # 1. 체력이 가장 낮은 유저
            # 2. 동률 시 특별 유저 우선
            # 3. 그래도 동률 시 랜덤
            
            target_id = grim_data.get("selected_target")
            if target_id:
                logger.info(f"그림 공격 발동! 타겟: {target_id} (주사위: 1000)")
                # 실제 사망 처리는 battle_admin에서
                
        except Exception as e:
            logger.error(f"그림 공격 실행 실패: {e}")
    
    async def process_skill_activation(self, channel_id: str, skill_name: str,
                                          user_id: str, target_id: Optional[str],
                                          duration: int):
            """스킬 활성화 시 특수 처리"""
            try:
                channel_state = skill_manager.get_channel_state(channel_id)
                
                # special_effects가 없으면 초기화
                if "special_effects" not in channel_state:
                    channel_state["special_effects"] = {}
                
                special_effects = channel_state["special_effects"]
                
                # 그림: 준비 단계 설정
                if skill_name == "그림":
                    special_effects["grim_preparing"] = {
                        "user_id": user_id,
                        "rounds_until_activation": 3,  # 테스트에서 기대하는 값
                        "target_id": target_id,  # 테스트에서 기대하는 필드명
                        "selected_target": None
                    }
                    # disabled_skills 키가 없으면 생성
                    if "disabled_skills" not in channel_state:
                        channel_state["disabled_skills"] = []
                    channel_state["disabled_skills"].append("grim_preparing")
                
                # 비렐라: 속박 대상 설정
                elif skill_name == "비렐라":
                    if "virella_bound" not in special_effects:
                        special_effects["virella_bound"] = []
                    if target_id:
                        special_effects["virella_bound"].append(target_id)
                
                # 닉사라: 배제 대상 설정
                elif skill_name == "닉사라":
                    if "nixara_excluded" not in special_effects:
                        special_effects["nixara_excluded"] = {}
                    if target_id:
                        # 초기 라운드 수는 주사위 대결로 결정
                        special_effects["nixara_excluded"][target_id] = {
                            "rounds_left": 0,  # 주사위 대결 후 결정
                            "caster_id": user_id
                        }
                
                # 볼켄: 화산 폭발 시작
                elif skill_name == "볼켄":
                    special_effects["volken_eruption"] = {
                        "current_phase": 1,
                        "selected_targets": []
                    }
                
                # 황야: 이중 행동 설정
                elif skill_name == "황야":
                    special_effects["hwangya_double_action"] = {
                        "user_id": user_id,
                        "actions_used_this_turn": 0,
                        "is_monster": user_id in ["monster", "admin"]
                    }
                
                # 제룬카: 타겟 설정
                elif skill_name == "제룬카":
                    special_effects["jerrunka_active"] = {
                        "user_id": user_id,
                        "target_id": target_id,
                        "is_monster": user_id in ["monster", "admin"]
                    }
                
                # 단목: 관통 준비
                elif skill_name == "단목":
                    special_effects["danmok_penetration"] = {
                        "targets": [],
                        "processed": False
                    }
                
                skill_manager.mark_dirty(channel_id)
                
            except Exception as e:
                logger.error(f"스킬 활성화 처리 실패: {e}")

# 싱글톤 인스턴스
skill_effects = SkillEffects()



