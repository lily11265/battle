# battle_admin.py 스킬 시스템 연동 함수들

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
import discord

logger = logging.getLogger(__name__)

# === 스킬 시스템과 battle_admin 연동을 위한 함수들 ===

async def get_battle_participants(channel_id: str) -> Dict[str, Any]:
    """전투 참여자 목록 조회 (스킬 시스템용)"""
    try:
        from admin_manager import admin_manager  # 기존 admin_manager import
        
        battle = admin_manager.get_battle(int(channel_id))
        if not battle:
            return {"users": [], "monster": None, "admin": None}
        
        participants = {
            "users": [],
            "monster": None,
            "admin": None
        }
        
        # 유저 목록 수집
        for player in battle.players:
            participants["users"].append({
                "user_id": str(player.user.id),
                "user_name": player.user.display_name,
                "real_name": player.real_name,
                "health": player.max_health - player.hits_received,
                "max_health": player.max_health,
                "is_dead": player.max_health - player.hits_received <= 0,
                "display_name": player.real_name
            })
        
        # 몬스터 정보
        if hasattr(battle, 'monster_name') and battle.monster_name:
            participants["monster"] = {
                "name": battle.monster_name,
                "health": battle.admin.max_health - battle.admin.hits_received if battle.admin else 0,
                "max_health": battle.admin.max_health if battle.admin else 100
            }
        
        # ADMIN 정보
        if battle.admin:
            participants["admin"] = {
                "name": battle.admin.user.display_name,
                "health": battle.admin.max_health - battle.admin.hits_received,
                "max_health": battle.admin.max_health
            }
        
        return participants
        
    except Exception as e:
        logger.error(f"전투 참여자 조회 실패 {channel_id}: {e}")
        return {"users": [], "monster": None, "admin": None}

async def get_user_info(channel_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """특정 유저 정보 조회"""
    try:
        participants = await get_battle_participants(channel_id)
        
        # 유저 목록에서 검색
        for user in participants["users"]:
            if user["user_id"] == str(user_id):
                return user
        
        # 몬스터 체크
        if user_id == "monster" and participants["monster"]:
            return {
                "user_id": "monster",
                "display_name": participants["monster"]["name"],
                "health": participants["monster"]["health"],
                "is_dead": participants["monster"]["health"] <= 0
            }
        
        # ADMIN 체크
        if user_id == "admin" and participants["admin"]:
            return {
                "user_id": "admin", 
                "display_name": participants["admin"]["name"],
                "health": participants["admin"]["health"],
                "is_dead": participants["admin"]["health"] <= 0
            }
        
        return None
        
    except Exception as e:
        logger.error(f"유저 정보 조회 실패 {user_id}: {e}")
        return None

async def send_battle_message(channel_id: str, message: str) -> bool:
    """전투 채널에 메시지 전송"""
    try:
        from main import bot  # main.py에서 bot 인스턴스 import
        
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(message)
            return True
        return False
        
    except Exception as e:
        logger.error(f"전투 메시지 전송 실패 {channel_id}: {e}")
        return False

async def damage_user(channel_id: str, user_id: str, damage_amount: int) -> bool:
    """유저에게 데미지 적용"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        if user_id == "monster" or user_id == "admin":
            # 몬스터/ADMIN 데미지
            if battle.admin:
                battle.admin.hits_received += damage_amount
                logger.info(f"몬스터/ADMIN 데미지 적용: {damage_amount}")
                return True
        else:
            # 일반 유저 데미지
            for player in battle.players:
                if str(player.user.id) == str(user_id):
                    player.hits_received += damage_amount
                    logger.info(f"유저 {user_id} 데미지 적용: {damage_amount}")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"데미지 적용 실패 {user_id}: {e}")
        return False

async def heal_user(channel_id: str, user_id: str, heal_amount: int) -> bool:
    """유저 회복 처리"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        if user_id == "monster" or user_id == "admin":
            # 몬스터/ADMIN 회복
            if battle.admin:
                battle.admin.hits_received = max(0, battle.admin.hits_received - heal_amount)
                logger.info(f"몬스터/ADMIN 회복: {heal_amount}")
                return True
        else:
            # 일반 유저 회복
            for player in battle.players:
                if str(player.user.id) == str(user_id):
                    player.hits_received = max(0, player.hits_received - heal_amount)
                    logger.info(f"유저 {user_id} 회복: {heal_amount}")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"회복 처리 실패 {user_id}: {e}")
        return False

async def kill_user(channel_id: str, user_id: str, damage_amount: int = 1000) -> bool:
    """유저 즉사 처리"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        if user_id == "monster" or user_id == "admin":
            # 몬스터/ADMIN 즉사
            if battle.admin:
                battle.admin.hits_received = battle.admin.max_health
                logger.info(f"몬스터/ADMIN 즉사 처리")
                return True
        else:
            # 일반 유저 즉사
            for player in battle.players:
                if str(player.user.id) == str(user_id):
                    player.hits_received = player.max_health
                    logger.info(f"유저 {user_id} 즉사 처리")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"즉사 처리 실패 {user_id}: {e}")
        return False

async def revive_user(channel_id: str, user_id: str, revive_health: int) -> bool:
    """유저 부활 처리"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if not battle:
            return False
        
        # 일반 유저 부활만 지원
        for player in battle.players:
            if str(player.user.id) == str(user_id):
                # 죽은 상태인지 확인
                if player.max_health - player.hits_received <= 0:
                    player.hits_received = player.max_health - revive_health
                    logger.info(f"유저 {user_id} 부활 처리: {revive_health} HP")
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"부활 처리 실패 {user_id}: {e}")
        return False

async def get_ai_difficulty(channel_id: str) -> str:
    """AI 난이도 조회"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if battle and hasattr(battle, 'ai_difficulty'):
            return battle.ai_difficulty
        
        return "normal"  # 기본값
        
    except Exception as e:
        logger.error(f"AI 난이도 조회 실패 {channel_id}: {e}")
        return "normal"

async def is_battle_active(channel_id: str) -> bool:
    """전투 활성 상태 확인"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        return battle is not None
        
    except Exception as e:
        logger.error(f"전투 상태 확인 실패 {channel_id}: {e}")
        return False

async def get_current_turn_user(channel_id: str) -> Optional[str]:
    """현재 턴 유저 ID 조회"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if battle and hasattr(battle, 'current_turn_user'):
            return str(battle.current_turn_user) if battle.current_turn_user else None
        
        return None
        
    except Exception as e:
        logger.error(f"현재 턴 유저 조회 실패 {channel_id}: {e}")
        return None

async def advance_battle_turn(channel_id: str):
    """전투 턴 진행"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if battle and hasattr(battle, 'advance_turn'):
            battle.advance_turn()
            
            # 스킬 라운드 업데이트
            from skills.skill_effects import update_all_skill_rounds
            expired_skills = await update_all_skill_rounds(channel_id)
            
            if expired_skills:
                expired_list = ", ".join(expired_skills)
                await send_battle_message(
                    channel_id, 
                    f"⏰ 다음 스킬들이 만료되었습니다: {expired_list}"
                )
            
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"전투 턴 진행 실패 {channel_id}: {e}")
        return False

async def update_battle_display(channel_id: str):
    """전투 상태 화면 업데이트"""
    try:
        from admin_manager import admin_manager
        
        battle = admin_manager.get_battle(int(channel_id))
        if battle:
            # 기존 전투 상태 임베드 업데이트
            if hasattr(battle, 'message') and battle.message:
                from admin_manager import create_battle_status_embed_with_skills
                embed = await create_battle_status_embed_with_skills(battle)
                await battle.message.edit(embed=embed)
            
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"전투 화면 업데이트 실패 {channel_id}: {e}")
        return False

# === 기존 admin_manager.py에 추가할 함수 ===

async def create_battle_status_embed_with_skills(battle) -> discord.Embed:
    """스킬 정보가 포함된 전투 상태 임베드 생성"""
    try:
        # 기존 전투 상태 임베드 생성
        from admin_manager import admin_manager
        embed = admin_manager._create_battle_status_embed(battle)
        
        # 스킬 정보 추가
        from skills.skill_manager import skill_manager
        channel_id = str(battle.message.channel.id)
        channel_state = skill_manager.get_channel_state(channel_id)
        
        active_skills = channel_state.get("active_skills", {})
        special_effects = channel_state.get("special_effects", {})
        
        if active_skills or special_effects:
            skill_info = "🔮 **현재 활성 스킬**:\n"
            
            # 활성 스킬들
            for skill_name, skill_data in active_skills.items():
                emoji = get_skill_emoji(skill_name)
                skill_info += f"{emoji} **{skill_name}** ({skill_data['rounds_left']}라운드 남음) - {skill_data['user_name']}\n"
            
            # 특별 효과들
            for effect_name, effect_data in special_effects.items():
                if effect_name == "virella_bound":
                    skill_info += f"🌿 **속박됨**: {effect_data['target_name']} (저항 기회 남음)\n"
                elif effect_name == "nixara_excluded":
                    skill_info += f"⚡ **시공 배제**: {effect_data['target_name']} ({effect_data['rounds_left']}라운드)\n"
                elif effect_name == "grim_preparing":
                    skill_info += f"💀 **그림 준비 중**: {effect_data['rounds_until_activation']}라운드 후 발동\n"
                elif effect_name == "volken_eruption":
                    phase = effect_data['current_phase']
                    skill_info += f"🌋 **볼켄 {phase}단계**: 화산 폭발 진행중\n"
            
            embed.add_field(
                name="🔮 활성 스킬",
                value=skill_info[:1024],  # Discord 제한
                inline=False
            )
        
        return embed
        
    except Exception as e:
        logger.error(f"스킬 포함 전투 임베드 생성 실패: {e}")
        # 실패 시 기본 임베드 반환
        from admin_manager import admin_manager
        return admin_manager._create_battle_status_embed(battle)

def get_skill_emoji(skill_name: str) -> str:
    """스킬별 이모지 반환"""
    emoji_map = {
        "오닉셀": "🔥",
        "피닉스": "🔥", 
        "오리븐": "⚫",
        "카론": "🔗",
        "스카넬": "💥",
        "루센시아": "✨",
        "비렐라": "🌿",
        "그림": "💀",
        "닉사라": "⚡",
        "제룬카": "🎯",
        "넥시스": "⭐",
        "볼켄": "🌋",
        "단목": "🏹",
        "콜 폴드": "🎲",
        "황야": "⚡",
        "스트라보스": "⚔️"
    }
    return emoji_map.get(skill_name, "🔮")

# === 주사위 처리 시 스킬 효과 적용 ===

async def process_dice_with_skill_effects(message):
    """주사위 메시지에 스킬 효과 적용"""
    try:
        # 주사위 값 추출 (기존 로직 사용)
        dice_value = extract_dice_value_from_message(message.content)
        if dice_value is None:
            return
        
        user_id = str(message.author.id)
        channel_id = str(message.channel.id)
        
        # 스킬 효과 적용
        from skills.skill_effects import process_dice_with_skills
        final_value, skill_messages = await process_dice_with_skills(user_id, dice_value, channel_id)
        
        # 스킬 효과 메시지 전송
        for msg in skill_messages:
            await message.channel.send(msg)
        
        # 특별 처리가 필요한 스킬들
        await handle_special_skill_dice_effects(channel_id, user_id, final_value)
        
        return final_value
        
    except Exception as e:
        logger.error(f"주사위 스킬 효과 처리 실패: {e}")
        return dice_value

async def handle_special_skill_dice_effects(channel_id: str, user_id: str, dice_value: int):
    """특별 처리가 필요한 스킬들의 주사위 효과"""
    try:
        from skills.skill_manager import skill_manager
        from skills.heroes.nixara import NixaraHandler
        from skills.heroes.jerrunka import JerrunkaHandler
        from skills.heroes.danmok import DanmokHandler
        
        channel_state = skill_manager.get_channel_state(channel_id)
        special_effects = channel_state.get("special_effects", {})
        
        # 닉사라 주사위 대결 처리
        if "nixara_duel" in special_effects:
            nixara_handler = NixaraHandler()
            await nixara_handler.process_dice_result(channel_id, user_id, dice_value)
        
        # 제룬카 유저 주사위 처리
        if "jerrunka_pending" in special_effects:
            jerrunka_handler = JerrunkaHandler()
            await jerrunka_handler.process_user_dice(channel_id, user_id, dice_value)
        
        # 단목 관통 주사위 처리
        if "danmok_penetration" in special_effects:
            danmok_handler = DanmokHandler()
            await danmok_handler.process_penetration_dice(channel_id, user_id, dice_value)
        
        # 볼켄 선별 처리 (4단계)
        if "volken_eruption" in special_effects:
            volken_effect = special_effects["volken_eruption"]
            if volken_effect["current_phase"] == 4 and dice_value < 50:
                volken_effect["selected_targets"].append({
                    "user_id": user_id,
                    "dice_value": dice_value
                })
                skill_manager.mark_dirty(channel_id)
                
                user_info = await get_user_info(channel_id, user_id)
                user_name = user_info["display_name"] if user_info else "대상"
                
                await send_battle_message(
                    channel_id,
                    f"🌋 **볼켄 선별**: {user_name}이(가) 다음 단계 집중공격 대상으로 선별되었습니다! (주사위: {dice_value})"
                )
        
        # 스카넬 운석 공격 처리
        if "scarnel_meteor" in special_effects and dice_value < 50:
            await damage_user(channel_id, user_id, 20)
            user_info = await get_user_info(channel_id, user_id)
            user_name = user_info["display_name"] if user_info else "대상"
            
            await send_battle_message(
                channel_id,
                f"☄️ **스카넬 운석 공격**: {user_name}이(가) 운석에 맞아 -20 피해를 받았습니다! (주사위: {dice_value})"
            )
        
    except Exception as e:
        logger.error(f"특별 스킬 주사위 효과 처리 실패: {e}")

def extract_dice_value_from_message(content: str) -> Optional[int]:
    """메시지에서 주사위 값 추출 (기존 로직 사용)"""
    import re
    
    # 다양한 주사위 봇 형식 지원
    patterns = [
        r'결과:\s*(\d+)',
        r'주사위:\s*(\d+)', 
        r'결과는\s*(\d+)',
        r'(\d+)이\(가\) 나왔습니다',
        r'(\d+)점'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return int(match.group(1))
    
    return None

# === 회복 명령어에 황야 스킬 연동 ===

async def handle_recovery_with_hwangya(interaction: discord.Interaction):
    """회복 명령어에 황야 스킬 효과 적용"""
    try:
        user_id = str(interaction.user.id)
        channel_id = str(interaction.channel.id)
        
        # 황야 스킬 체크
        from skills.heroes.hwangya import HwangyaHandler
        hwangya_handler = HwangyaHandler()
        
        if not await hwangya_handler.can_use_recovery(channel_id, user_id):
            await interaction.response.send_message(
                "❌ 이번 턴에 더 이상 행동할 수 없습니다. (황야 스킬 제한)", 
                ephemeral=True
            )
            return False
        
        # 회복 실행 후 황야 행동 카운터 업데이트
        # (기존 회복 로직 실행)
        
        await hwangya_handler.use_recovery_action(channel_id, user_id)
        return True
        
    except Exception as e:
        logger.error(f"황야 회복 처리 실패: {e}")
        return True  # 실패 시 일반 회복은 허용
