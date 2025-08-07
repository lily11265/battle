# === 1. main.py에 추가할 코드 ===

# 기존 import에 추가
from skills.skill_manager import skill_manager
from skills.skill_effects import skill_effects
import battle_admin  # battle_admin.py에 스킬 연동 함수들 추가됨

@bot.event
async def on_ready():
    """봇 준비 완료 이벤트 (스킬 시스템 Phase 2 통합)"""
    logger.info(f"봇이 준비되었습니다! {bot.user}로 로그인됨")
    bot_manager.reconnect_attempts = 0
    
    try:
        # 기존 시스템 초기화
        synced = await tree.sync()
        logger.info(f"{len(synced)}개의 명령어가 동기화되었습니다")
        
        await bot_manager.initialize()
        
        # === 스킬 시스템 Phase 2 초기화 ===
        from skills.skill import SkillCog, SkillInfoCog
        await bot.add_cog(SkillCog(bot))
        await bot.add_cog(SkillInfoCog(bot))
        logger.info("✅ 스킬 시스템 Phase 2가 초기화되었습니다")
        
        # 기존 몹 세팅 시스템
        global mob_setting_handler
        bot.mob_setting_views = {}
        mob_setting_handler = MobSetting(bot)
        logger.info("몹 세팅 시스템이 초기화되었습니다")
        
        # 스킬 시스템 성능 체크
        await _perform_skill_system_health_check()
        
    except Exception as e:
        logger.error(f"봇 시작 중 오류 발생: {e}")
        traceback.print_exc()

async def _perform_skill_system_health_check():
    """스킬 시스템 상태 체크"""
    try:
        # 기본 기능 테스트
        test_channel = "health_check"
        test_user = "health_check_user"
        
        # 스킬 추가/제거 테스트
        success = skill_manager.add_skill(
            test_channel, "오닉셀", test_user, "테스트", test_user, "테스트", 1
        )
        if success:
            skill_manager.remove_skill(test_channel, "오닉셀")
        
        # 주사위 처리 테스트
        final_value, messages = await skill_effects.process_dice_roll(
            test_user, 75, test_channel
        )
        
        logger.info("✅ 스킬 시스템 상태 체크 완료")
        
    except Exception as e:
        logger.error(f"스킬 시스템 상태 체크 실패: {e}")

# === 2. 기존 주사위 처리 시스템에 스킬 효과 통합 ===

async def handle_message(message):
    """메시지 처리 (스킬 효과 통합)"""
    if message.author == bot.user:
        return
    
    # 기존 메시지 처리 로직...
    
    # 주사위 메시지 처리에 스킬 효과 추가
    if is_dice_message(message.content):
        try:
            dice_value = extract_dice_value_from_message(message.content)
            if dice_value is not None:
                user_id = str(message.author.id)
                channel_id = str(message.channel.id)
                
                # 행동 차단 체크 (비렐라, 닉사라 등)
                action_check = await skill_effects.check_action_blocked(
                    channel_id, user_id, "dice_roll"
                )
                
                if action_check["blocked"]:
                    await message.channel.send(f"🚫 {action_check['reason']}")
                    return
                
                # 스킬 효과 적용
                final_value, skill_messages = await skill_effects.process_dice_roll(
                    user_id, dice_value, channel_id
                )
                
                # 스킬 효과 메시지 전송
                for msg in skill_messages:
                    await message.channel.send(msg)
                
                # 특별 스킬 처리 (닉사라, 제룬카, 단목, 볼켄 등)
                await handle_special_skill_dice_effects(channel_id, user_id, final_value)
                
                # 기존 전투 시스템에 최종 주사위 값 전달
                await process_battle_dice(message, final_value)
                
        except Exception as e:
            logger.error(f"주사위 스킬 효과 처리 실패: {e}")

async def handle_special_skill_dice_effects(channel_id: str, user_id: str, dice_value: int):
    """특별 스킬들의 주사위 효과 처리"""
    try:
        from skills.heroes.nixara import NixaraHandler
        from skills.heroes.jerrunka import JerrunkaHandler  
        from skills.heroes.danmok import DanmokHandler
        from skills.skill_manager import skill_manager
        
        channel_state = skill_manager.get_channel_state(channel_id)
        special_effects = channel_state.get("special_effects", {})
        
        # 닉사라 주사위 대결
        if "nixara_duel" in special_effects:
            nixara_handler = NixaraHandler()
            await nixara_handler.process_dice_result(channel_id, user_id, dice_value)
        
        # 제룬카 효과 결정
        if "jerrunka_pending" in special_effects:
            jerrunka_handler = JerrunkaHandler()
            await jerrunka_handler.process_user_dice(channel_id, user_id, dice_value)
        
        # 단목 관통 공격
        if "danmok_penetration" in special_effects:
            danmok_handler = DanmokHandler()
            await danmok_handler.process_penetration_dice(channel_id, user_id, dice_value)
        
        # 볼켄 4단계 선별
        volken_effect = special_effects.get("volken_eruption")
        if volken_effect and volken_effect["current_phase"] == 4:
            if dice_value < 50:
                volken_effect["selected_targets"].append({
                    "user_id": user_id,
                    "dice_value": dice_value
                })
                skill_manager.mark_dirty(channel_id)
                
                user_info = await battle_admin.get_user_info(channel_id, user_id)
                user_name = user_info["display_name"] if user_info else "대상"
                
                await battle_admin.send_battle_message(
                    channel_id,
                    f"🌋 **볼켄 선별**: {user_name}이(가) 집중공격 대상으로 선별되었습니다!"
                )
        
        # 스카넬 운석 공격
        if "scarnel_meteor" in special_effects and dice_value < 50:
            await battle_admin.damage_user(channel_id, user_id, 20)
            user_info = await battle_admin.get_user_info(channel_id, user_id)
            user_name = user_info["display_name"] if user_info else "대상"
            
            await battle_admin.send_battle_message(
                channel_id,
                f"☄️ **운석 직격**: {user_name}이(가) -20 피해를 받았습니다!"
            )
        
    except Exception as e:
        logger.error(f"특별 스킬 주사위 처리 실패: {e}")

def is_dice_message(content: str) -> bool:
    """주사위 메시지 여부 확인"""
    dice_keywords = ["결과:", "주사위:", "결과는", "이(가) 나왔습니다", "점"]
    return any(keyword in content for keyword in dice_keywords)

def extract_dice_value_from_message(content: str) -> Optional[int]:
    """메시지에서 주사위 값 추출"""
    import re
    
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

# === 3. 회복 명령어에 황야 스킬 연동 ===

@tree.command(name="회복", description="회복 아이템을 사용하여 체력을 회복합니다.")
@app_commands.describe(횟수="회복 횟수 (1-10)")
@app_commands.guild_only()
async def recovery_command(interaction: discord.Interaction, 횟수: app_commands.Range[int, 1, 10]):
    """회복 명령어 (황야 스킬 연동)"""
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    
    try:
        # 행동 차단 체크
        action_check = await skill_effects.check_action_blocked(channel_id, user_id, "recovery")
        if action_check["blocked"]:
            await interaction.response.send_message(f"🚫 {action_check['reason']}", ephemeral=True)
            return
        
        # 황야 스킬 체크 (이중 행동)
        recovery_check = await skill_effects.check_recovery_allowed(channel_id, user_id)
        if not recovery_check["allowed"]:
            await interaction.response.send_message(f"❌ {recovery_check['reason']}", ephemeral=True)
            return
        
        # 기존 회복 로직 실행
        await execute_recovery(interaction, 횟수)
        
        # 황야 행동 카운터 업데이트
        from skills.heroes.hwangya import HwangyaHandler
        hwangya_handler = HwangyaHandler()
        await hwangya_handler.use_recovery_action(channel_id, user_id)
        
    except Exception as e:
        logger.error(f"회복 명령어 처리 실패: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ 회복 처리 중 오류가 발생했습니다.", ephemeral=True)

# === 4. 전투 턴 진행에 스킬 라운드 연동 ===

async def advance_battle_round(channel_id: str):
    """전투 라운드 진행 (스킬 연동)"""
    try:
        # 기존 전투 로직...
        
        # 스킬 라운드 시작 이벤트 처리
        await trigger_skill_round_start_events(channel_id)
        
        # 스킬 라운드 업데이트
        expired_skills = await skill_effects.update_skill_rounds(channel_id)
        
        if expired_skills:
            expired_list = ", ".join(expired_skills)
            await battle_admin.send_battle_message(
                channel_id,
                f"⏰ 다음 스킬들이 만료되었습니다: {expired_list}"
            )
        
        # 전투 화면 업데이트 (스킬 정보 포함)
        await battle_admin.update_battle_display(channel_id)
        
    except Exception as e:
        logger.error(f"전투 라운드 진행 실패: {e}")

async def trigger_skill_round_start_events(channel_id: str):
    """스킬 라운드 시작 이벤트들 처리"""
    from skills.skill_manager import skill_manager
    from skills.heroes import get_skill_handler
    
    try:
        channel_state = skill_manager.get_channel_state(channel_id)
        current_round = channel_state.get("current_round", 1) + 1
        
        # 모든 활성 스킬의 라운드 시작 이벤트 호출
        for skill_name in channel_state.get("active_skills", {}):
            handler = get_skill_handler(skill_name)
            if handler:
                await handler.on_round_start(channel_id, current_round)
        
        # 라운드 번호 업데이트
        skill_manager.update_round(channel_id, current_round)
        
    except Exception as e:
        logger.error(f"스킬 라운드 시작 이벤트 실패: {e}")

# === 5. 전투 종료 시 스킬 정리 ===

async def end_battle_cleanup(channel_id: str):
    """전투 종료 정리 (스킬 포함)"""
    try:
        # 기존 전투 종료 로직...
        
        # 모든 스킬 종료 처리
        from skills.skill_manager import skill_manager
        channel_state = skill_manager.get_channel_state(channel_id)
        
        for skill_name in list(channel_state.get("active_skills", {}).keys()):
            await skill_effects.force_end_skill(channel_id, skill_name)
        
        # 스킬 상태 완전 정리
        skill_manager.clear_channel_data(channel_id)
        logger.info(f"채널 {channel_id} 스킬 데이터 정리 완료")
        
    except Exception as e:
        logger.error(f"스킬 데이터 정리 오류: {e}")

# === 6. 데미지/회복 처리에 스킬 효과 통합 ===

async def apply_damage_to_user(channel_id: str, user_id: str, base_damage: int):
    """사용자에게 데미지 적용 (스킬 효과 포함)"""
    try:
        # 특별 데미지 효과 적용 (제룬카 저주 등)
        final_damage = await skill_effects.process_special_damage_effects(
            channel_id, user_id, base_damage
        )
        
        # 데미지 공유 처리 (카론, 스카넬)
        shared_damage = await skill_effects.process_damage_sharing(
            channel_id, user_id, final_damage
        )
        
        # 실제 데미지 적용
        for target_id, damage_amount in shared_damage.items():
            await battle_admin.damage_user(channel_id, target_id, damage_amount)
        
        # 데미지 공유 메시지
        if len(shared_damage) > 1:
            targets = ", ".join([
                (await battle_admin.get_user_info(channel_id, uid))["display_name"] 
                for uid in shared_damage.keys()
            ])
            await battle_admin.send_battle_message(
                channel_id,
                f"🔗 **데미지 공유**: {targets}가(이) 피해를 공유했습니다!"
            )
        
        return final_damage
        
    except Exception as e:
        logger.error(f"데미지 적용 실패: {e}")
        return base_damage

# === 7. 봇 종료 시 스킬 시스템 정리 ===

@bot.event
async def on_disconnect():
    """연결 끊김 시 스킬 시스템 정리"""
    logger.warning("봇 연결이 끊어졌습니다. 스킬 데이터 저장 중...")
    try:
        await skill_manager.force_save()
        await skill_effects.clear_cache()
    except Exception as e:
        logger.error(f"스킬 데이터 저장 오류: {e}")

# === 8. 설정 파일 생성 스크립트 ===

def create_skill_config_files():
    """스킬 시스템 설정 파일 생성"""
    import json
    from pathlib import Path
    
    skills_dir = Path("skills")
    config_dir = skills_dir / "config"
    data_dir = skills_dir / "data"
    heroes_dir = skills_dir / "heroes"
    
    # 디렉토리 생성
    for dir_path in [skills_dir, config_dir, data_dir, heroes_dir]:
        dir_path.mkdir(exist_ok=True)
    
    # skill_config.json
    config_data = {
        "lucencia": {
            "health_cost": 3,
            "revival_health": 5
        },
        "priority_users": [
            "1237738945635160104",
            "1059908946741166120"
        ],
        "skill_users": {
            "오닉셀": ["all_users", "admin", "monster"],
            "피닉스": ["users_only"],
            "오리븐": ["all_users", "admin", "monster"],
            "카론": ["all_users", "admin", "monster"],
            "스카넬": ["all_users", "admin", "monster"],
            "루센시아": ["all_users", "admin", "monster"],
            "비렐라": ["admin", "monster"],
            "그림": ["admin", "monster"],
            "닉사라": ["admin", "monster"],
            "제룬카": ["all_users", "admin", "monster"],
            "넥시스": ["1059908946741166120"],
            "볼켄": ["admin", "monster"],
            "단목": ["all_users", "admin", "monster"],
            "콜 폴드": ["admin", "monster"],
            "황야": ["admin", "monster"],
            "스트라보스": ["all_users", "admin", "monster"]
        },
        "authorized_admins": [
            "1007172975222603798",
            "1090546247770832910"
        ],
        "authorized_nickname": "system | 시스템",
        "system_settings": {
            "auto_save_interval": 30,
            "max_skill_duration": 10,
            "enable_skill_logs": True,
            "performance_mode": True
        }
    }
    
    with open(config_dir / "skill_config.json", 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    
    # user_skills.json (예시)
    user_skills_data = {
        "example_user_1": {
            "allowed_skills": ["오닉셀", "피닉스", "오리븐"],
            "display_name": "일반유저1",
            "skill_level": "basic"
        },
        "1237738945635160104": {
            "allowed_skills": ["피닉스", "루센시아", "오리븐", "카론"],
            "display_name": "특별유저1",
            "skill_level": "advanced"
        },
        "1059908946741166120": {
            "allowed_skills": ["넥시스", "피닉스", "오닉셀", "스트라보스"],
            "display_name": "특별유저2",
            "skill_level": "master"
        }
    }
    
    with open(config_dir / "user_skills.json", 'w', encoding='utf-8') as f:
        json.dump(user_skills_data, f, ensure_ascii=False, indent=2)
    
    # 빈 skill_states.json
    with open(data_dir / "skill_states.json", 'w', encoding='utf-8') as f:
        json.dump({}, f)
    
    # __init__.py 파일 생성
    with open(heroes_dir / "__init__.py", 'w', encoding='utf-8') as f:
        f.write('# 스킬 핸들러 모듈\n')
    
    print("✅ 스킬 시스템 설정 파일들이 생성되었습니다!")
