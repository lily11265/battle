# skills/skill_manager.py
"""
스킬 상태 관리 시스템
JSON 저장/로드, 라운드 관리, 백업 DB 포함 완전한 구현
"""
import json
import logging
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import aiofiles
from threading import Lock

logger = logging.getLogger(__name__)


class SkillManager:
    """통합된 스킬 상태 관리자 - 권한 관리와 백업 시스템 통합"""
    
    def __init__(self):
        self.base_dir = Path("skills")
        self.config_dir = self.base_dir / "config"
        self.data_dir = self.base_dir / "data"
        
        # 메모리 캐시
        self._skill_states: Dict[str, Dict] = {}
        self._config: Dict = {}
        self._user_data: Dict = {}
        self._initialized = False
        
        # 동시성 제어
        self._lock = Lock()
        self._dirty_channels: set = set()  # 저장 필요한 채널
        self._last_save_time: Dict[str, datetime] = {"config": None, "skill_states": None, "user_data": None}
        
        # 자동 저장 태스크
        self._auto_save_task: Optional[asyncio.Task] = None
        self._save_interval = 30  # 30초마다 자동 저장
        
        # 백업 DB
        self._db_path = self.data_dir / "skill_backup.db"
        self._db_conn: Optional[sqlite3.Connection] = None

    async def initialize(self):
        """시스템 초기화"""
        try:
            # 디렉토리 생성
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
            # 설정 파일 로드
            await self._load_config()
            await self._load_user_data()
            await self._load_skill_states()
            
            # 백업 DB 초기화
            self._initialize_backup_db()
            
            # 백업에서 복구 시도
            await self._restore_from_backup()
            
            # 자동 저장 시작
            self._start_auto_save()
            
            self._initialized = True
            logger.info("통합 스킬 매니저 초기화 완료")
            
        except Exception as e:
            logger.error(f"스킬 매니저 초기화 실패: {e}")
            self._initialized = False
            raise

    def _initialize_backup_db(self):
        """백업 데이터베이스 초기화"""
        try:
            self._db_conn = sqlite3.connect(str(self._db_path))
            cursor = self._db_conn.cursor()
            
            # 스킬 상태 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_states (
                    channel_id TEXT PRIMARY KEY,
                    battle_data TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 스킬 로그 테이블 (디버깅용)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    skill_name TEXT,
                    user_id TEXT,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self._db_conn.commit()
            logger.info("백업 DB 초기화 완료")
            
        except Exception as e:
            logger.error(f"백업 DB 초기화 실패: {e}")

    # === 권한 관리 메서드들 (첫 번째 문서의 개선된 버전) ===
    
    def is_admin(self, user_id: str, display_name: str = "") -> bool:
        """Admin 권한 확인 (몹 전투 전용 로직 포함)"""
        try:
            # === 고정 Admin ID 체크 ===
            ADMIN_IDS = [
                "1007172975222603798",  # Admin ID 1
                "1090546247770832910",  # Admin ID 2
            ]
            
            if str(user_id) in ADMIN_IDS:
                return True
            
            # === 닉네임 기반 Admin 체크 ===
            ADMIN_NICKNAMES = [
                "system | 시스템",
                "system",
                "시스템"
            ]
            
            if display_name.strip() in ADMIN_NICKNAMES:
                return True
            
            # === 몬스터/특별 사용자 체크 ===
            SPECIAL_USERS = [
                "monster",
                "admin", 
                "system_bot"
            ]
            
            if str(user_id).lower() in SPECIAL_USERS:
                return True
            
            # === 설정 파일 기반 Admin 체크 ===
            config_admins = self._config.get("authorized_admins", [])
            if str(user_id) in config_admins:
                return True
            
            # 닉네임으로 확인
            admin_nickname = self._config.get("authorized_nickname", "")
            if admin_nickname and admin_nickname.lower() in display_name.lower():
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Admin 권한 확인 오류: {e}")
            return False
    
    def can_use_skill(self, user_id: str, skill_name: str, display_name: str = "") -> bool:
        """스킬 사용 권한 확인 (몹 전투 강화)"""
        try:
            # === Admin은 모든 스킬 사용 가능 ===
            if self.is_admin(user_id, display_name):
                return True
            
            # === 스킬별 사용자 제한 확인 ===
            skill_users = self._config.get("skill_users", {}).get(skill_name, [])
            
            # 특정 유저 ID 허용
            if str(user_id) in skill_users:
                return True
            
            # 모든 사용자 허용 설정
            if "all_users" in skill_users or "users_only" in skill_users:
                # 개인 허용 목록 확인
                allowed_skills = self.get_user_allowed_skills(user_id)
                return skill_name in allowed_skills
            
            # === 몹 전투 중 특별 권한 ===
            # 몹 전투 상황에서 Admin의 스킬 사용을 보다 유연하게 허용
            if display_name in ["system | 시스템", "system", "시스템"]:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"스킬 권한 확인 오류 ({skill_name}): {e}")
            return False

    def get_user_allowed_skills(self, user_id: str) -> List[str]:
        """사용자별 허용 스킬 목록"""
        user_data = self._user_data.get(str(user_id), {})
        return user_data.get("allowed_skills", [])

    # === 스킬 상태 관리 메서드들 (통합 및 개선된 버전) ===
    
    def get_channel_state(self, channel_id: str) -> Dict:
        """채널 상태 조회 (몹 전투 상태 포함)"""
        try:
            channel_id = str(channel_id)
            
            if channel_id not in self._skill_states:
                # 새 채널 상태 초기화 (몹 전투 지원)
                self._skill_states[channel_id] = {
                    "active_skills": {},
                    "special_effects": {},
                    "battle_active": False,
                    "battle_type": None,
                    "mob_name": None,
                    "admin_can_use_skills": False,
                    "current_round": 1,
                    "last_round_processed": 0,
                    "disabled_skills": [],
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
                self.mark_dirty(channel_id)
            
            return self._skill_states[channel_id]
            
        except Exception as e:
            logger.error(f"채널 상태 조회 오류: {e}")
            # 기본 상태 반환
            return {
                "active_skills": {},
                "special_effects": {},
                "battle_active": False,
                "battle_type": None,
                "mob_name": None,
                "admin_can_use_skills": False,
                "current_round": 1,
                "last_round_processed": 0,
                "disabled_skills": [],
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }

    async def activate_skill(
        self, 
        user_id: str, 
        user_name: str, 
        skill_name: str, 
        channel_id: str,
        duration_rounds: int,
        target: Optional[str] = None
    ) -> bool:
        """스킬 활성화 (몹 전투 완전 지원)"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                # === 중복 스킬 체크 ===
                if skill_name in channel_state["active_skills"]:
                    logger.warning(f"스킬 중복 활성화 시도: {skill_name} in {channel_id}")
                    return False
                
                # === 사용자별 활성 스킬 체크 ===
                for existing_skill, skill_data in channel_state["active_skills"].items():
                    if skill_data["user_id"] == str(user_id):
                        logger.warning(f"사용자 {user_name}가 이미 {existing_skill} 스킬 사용 중")
                        return False
                
                # === 스킬 데이터 생성 ===
                current_round = channel_state.get("current_round", 1)
                skill_data = {
                    "user_id": str(user_id),
                    "user_name": user_name,
                    "skill_name": skill_name,
                    "rounds_left": duration_rounds,
                    "total_rounds": duration_rounds,
                    "target": target,
                    "started_round": current_round,
                    "activated_at": datetime.now().isoformat(),
                    "channel_id": channel_id
                }
                
                # === 몹 전투 관련 메타데이터 추가 ===
                if channel_state.get("battle_type") == "mob_battle":
                    skill_data["battle_context"] = {
                        "battle_type": "mob_battle",
                        "mob_name": channel_state.get("mob_name"),
                        "is_admin_skill": self.is_admin(user_id, user_name)
                    }
                
                # === 스킬 활성화 ===
                channel_state["active_skills"][skill_name] = skill_data
                channel_state["last_updated"] = datetime.now().isoformat()
                
                self.mark_dirty(channel_id)
                self._log_skill_action(channel_id, skill_name, user_id, "activate", 
                                     f"Duration: {duration_rounds} rounds")
                
                # 자동 저장
                await self._save_skill_states()
                
                logger.info(f"스킬 활성화 성공: {skill_name} by {user_name} in {channel_id} for {duration_rounds} rounds")
                return True
                
        except Exception as e:
            logger.error(f"스킬 활성화 오류: {e}")
            return False

    async def deactivate_skill(self, channel_id: str, skill_name: str) -> bool:
        """스킬 비활성화"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                if skill_name not in channel_state["active_skills"]:
                    logger.warning(f"비활성화할 스킬이 없음: {skill_name} in {channel_id}")
                    return False
                
                # 스킬 데이터 가져오기
                skill_data = channel_state["active_skills"][skill_name]
                
                # 스킬 핸들러의 종료 이벤트 호출
                try:
                    from .skill import get_skill_handler
                    handler = get_skill_handler(skill_name)
                    if handler:
                        await handler.on_skill_end(channel_id, skill_data["user_id"])
                except Exception as e:
                    logger.error(f"스킬 종료 이벤트 오류 ({skill_name}): {e}")
                
                # 스킬 제거
                del channel_state["active_skills"][skill_name]
                
                # 관련 특수 효과도 제거
                if skill_name in channel_state["special_effects"]:
                    del channel_state["special_effects"][skill_name]
                
                channel_state["last_updated"] = datetime.now().isoformat()
                
                self.mark_dirty(channel_id)
                self._log_skill_action(channel_id, skill_name, 
                                     skill_data["user_id"], "deactivate", "Manual deactivation")
                
                # 자동 저장
                await self._save_skill_states()
                
                logger.info(f"스킬 비활성화 성공: {skill_name} in {channel_id}")
                return True
                
        except Exception as e:
            logger.error(f"스킬 비활성화 오류: {e}")
            return False

    async def process_round_end(self, channel_id: str, round_num: int) -> List[str]:
        """라운드 종료 시 스킬 처리"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                # 이미 처리된 라운드인지 확인
                if channel_state["last_round_processed"] >= round_num:
                    return []
                
                expired_skills = []
                messages = []
                
                # 각 활성 스킬의 라운드 감소
                for skill_name, skill_data in list(channel_state["active_skills"].items()):
                    skill_data["rounds_left"] -= 1
                    
                    if skill_data["rounds_left"] <= 0:
                        # 스킬 만료
                        expired_skills.append(skill_name)
                        
                        # 종료 메시지
                        user_name = skill_data["user_name"]
                        messages.append(f"💫 **{user_name}**님의 **{skill_name}** 스킬이 종료되었습니다.")
                        
                        # 스킬 핸들러의 종료 이벤트 호출
                        try:
                            from .skill import get_skill_handler
                            handler = get_skill_handler(skill_name)
                            if handler:
                                await handler.on_skill_end(channel_id, skill_data["user_id"])
                        except Exception as e:
                            logger.error(f"스킬 종료 이벤트 오류 ({skill_name}): {e}")
                        
                        self._log_skill_action(channel_id, skill_name, 
                                             skill_data["user_id"], "expire", 
                                             f"Expired at round {round_num}")
                    else:
                        # 지속 중인 스킬 알림
                        rounds_left = skill_data["rounds_left"]
                        user_name = skill_data["user_name"]
                        messages.append(f"✨ **{user_name}**님의 **{skill_name}** 스킬 - {rounds_left}라운드 남음")
                
                # 만료된 스킬들 제거
                for skill_name in expired_skills:
                    del channel_state["active_skills"][skill_name]
                    # 관련 특수 효과도 제거
                    if skill_name in channel_state["special_effects"]:
                        del channel_state["special_effects"][skill_name]
                
                # 라운드 처리 완료 표시
                channel_state["last_round_processed"] = round_num
                channel_state["current_round"] = round_num + 1
                channel_state["last_updated"] = datetime.now().isoformat()
                
                self.mark_dirty(channel_id)
                
                # 자동 저장
                await self._save_skill_states()
                
                logger.info(f"라운드 {round_num} 스킬 처리 완료 - 채널: {channel_id}, 만료 스킬: {len(expired_skills)}개")
                
                return messages
                
        except Exception as e:
            logger.error(f"라운드 종료 스킬 처리 오류: {e}")
            return []

    async def clear_channel_skills(self, channel_id: str) -> int:
        """채널의 모든 스킬 정리"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                # 활성 스킬 개수
                active_count = len(channel_state["active_skills"])
                
                # 각 스킬의 종료 이벤트 호출
                for skill_name, skill_data in channel_state["active_skills"].items():
                    try:
                        from .skill import get_skill_handler
                        handler = get_skill_handler(skill_name)
                        if handler:
                            await handler.on_skill_end(channel_id, skill_data["user_id"])
                    except Exception as e:
                        logger.error(f"스킬 종료 이벤트 오류 ({skill_name}): {e}")
                
                # 모든 스킬 및 효과 정리
                channel_state["active_skills"].clear()
                channel_state["special_effects"].clear()
                channel_state["disabled_skills"].clear()
                channel_state["last_round_processed"] = 0
                channel_state["current_round"] = 1
                
                # 전투 상태 초기화
                channel_state["battle_active"] = False
                channel_state["battle_type"] = None
                channel_state["mob_name"] = None
                channel_state["admin_can_use_skills"] = False
                channel_state["last_updated"] = datetime.now().isoformat()
                
                self.mark_dirty(channel_id)
                self._log_skill_action(channel_id, "ALL", "SYSTEM", "clear", 
                                     "Battle ended or reset")
                
                # 자동 저장
                await self._save_skill_states()
                
                logger.info(f"채널 {channel_id} 스킬 전체 정리 완료 - {active_count}개 스킬 제거")
                return active_count
                
        except Exception as e:
            logger.error(f"채널 스킬 정리 오류: {e}")
            return 0

    # === 기존 호환성 메서드들 ===
    
    def add_skill(self, channel_id: str, skill_name: str, user_id: str, 
                  user_name: str, target_id: str, target_name: str, 
                  duration: int) -> bool:
        """스킬 추가 (기존 호환성)"""
        return asyncio.create_task(self.activate_skill(
            user_id, user_name, skill_name, channel_id, duration, target_name
        ))

    def remove_skill(self, channel_id: str, skill_name: str) -> bool:
        """스킬 제거 (기존 호환성)"""
        return asyncio.create_task(self.deactivate_skill(channel_id, skill_name))

    def update_round(self, channel_id: str, round_num: int):
        """라운드 업데이트 (기존 호환성)"""
        return asyncio.create_task(self.process_round_end(channel_id, round_num))

    def end_battle(self, channel_id: str):
        """전투 종료 - 메모리에서만 삭제"""
        return asyncio.create_task(self.clear_channel_skills(channel_id))

    # === 설정 관리 ===
    
    def get_config(self, key: str, default=None):
        """설정값 조회"""
        return self._config.get(key, default)

    # === 파일 로드/저장 메서드들 ===
    
    async def _load_config(self):
        """전역 설정 로드"""
        config_file = self.config_dir / "skill_config.json"
        
        if not config_file.exists():
            # 기본 설정 생성
            self._config = self._create_default_config()
            await self._save_config()
        else:
            try:
                async with aiofiles.open(config_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self._config = json.loads(content)
            except Exception as e:
                logger.error(f"설정 파일 로드 실패: {e}")
                self._config = self._create_default_config()

    async def _load_user_data(self):
        """유저별 스킬 권한 로드"""
        user_data_file = self.config_dir / "user_data.json"
        
        if not user_data_file.exists():
            self._user_data = {}
            await self._save_user_data()
        else:
            try:
                async with aiofiles.open(user_data_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self._user_data = json.loads(content)
            except Exception as e:
                logger.error(f"유저 데이터 파일 로드 실패: {e}")
                self._user_data = {}

    async def _load_skill_states(self):
        """스킬 상태 로드 - 봇 재시작시 초기화"""
        states_file = self.data_dir / "skill_states.json"
        
        # 봇이 재시작될 때마다 스킬 상태를 초기화
        self._skill_states = {}
        logger.info("봇 재시작으로 인해 모든 스킬 상태가 초기화되었습니다.")
        
        # 파일이 존재하면 삭제 (선택사항)
        if states_file.exists():
            try:
                states_file.unlink()
                logger.info("이전 스킬 상태 파일이 삭제되었습니다.")
            except Exception as e:
                logger.error(f"스킬 상태 파일 삭제 실패: {e}")
        
        # 빈 상태로 새 파일 생성
        await self._save_skill_states()

    async def _save_skill_states(self):
        """스킬 상태 저장"""
        try:
            states_file = self.data_dir / "skill_states.json"
            
            # 불필요한 빈 채널 정리
            clean_states = {}
            for channel_id, state in self._skill_states.items():
                if (state["active_skills"] or state["special_effects"] or 
                    state["battle_active"]):
                    clean_states[channel_id] = state
            
            async with aiofiles.open(states_file, 'w', encoding='utf-8') as f:
                content = json.dumps(clean_states, ensure_ascii=False, indent=2)
                await f.write(content)
            
            # 백업 DB에도 저장
            self._backup_to_db_sync(clean_states)
            
            self._last_save_time["skill_states"] = datetime.now()
            
        except Exception as e:
            logger.error(f"스킬 상태 저장 실패: {e}")

    async def _save_config(self):
        """설정 파일 저장"""
        try:
            config_file = self.config_dir / "skill_config.json"
            async with aiofiles.open(config_file, 'w', encoding='utf-8') as f:
                content = json.dumps(self._config, ensure_ascii=False, indent=2)
                await f.write(content)
            
            self._last_save_time["config"] = datetime.now()
            
        except Exception as e:
            logger.error(f"설정 파일 저장 실패: {e}")

    async def _save_user_data(self):
        """유저 데이터 저장"""
        try:
            user_data_file = self.config_dir / "user_data.json"
            async with aiofiles.open(user_data_file, 'w', encoding='utf-8') as f:
                content = json.dumps(self._user_data, ensure_ascii=False, indent=2)
                await f.write(content)
            
            self._last_save_time["user_data"] = datetime.now()
            
        except Exception as e:
            logger.error(f"유저 데이터 저장 실패: {e}")

    def _backup_to_db_sync(self, states: Dict):
        """백업 DB에 동기적으로 저장"""
        if not self._db_conn:
            return
        
        try:
            cursor = self._db_conn.cursor()
            
            for channel_id, state in states.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO skill_states (channel_id, battle_data, last_updated)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (channel_id, json.dumps(state)))
            
            self._db_conn.commit()
            
        except Exception as e:
            logger.error(f"백업 DB 저장 실패: {e}")

    async def _restore_from_backup(self):
        """백업에서 복구"""
        if not self._db_conn:
            return
        
        try:
            cursor = self._db_conn.cursor()
            cursor.execute("""
                SELECT channel_id, battle_data 
                FROM skill_states 
                WHERE last_updated > datetime('now', '-1 day')
            """)
            
            rows = cursor.fetchall()
            restored_count = 0
            
            for channel_id, battle_data in rows:
                if channel_id not in self._skill_states:
                    self._skill_states[channel_id] = json.loads(battle_data)
                    restored_count += 1
            
            if restored_count > 0:
                logger.info(f"백업에서 {restored_count}개 채널 상태 복구")
                
        except Exception as e:
            logger.error(f"백업 복구 실패: {e}")

    # === 자동 저장 시스템 ===
    
    def _start_auto_save(self):
        """자동 저장 태스크 시작"""
        if self._auto_save_task:
            self._auto_save_task.cancel()
        
        self._auto_save_task = asyncio.create_task(self._auto_save_loop())

    async def _auto_save_loop(self):
        """자동 저장 루프"""
        while True:
            try:
                await asyncio.sleep(self._save_interval)
                
                if self._dirty_channels:
                    await self._save_skill_states()
                    self._dirty_channels.clear()
                    logger.debug(f"자동 저장 완료 - {datetime.now()}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"자동 저장 오류: {e}")

    def mark_dirty(self, channel_id: str):
        """채널을 저장 필요 상태로 표시"""
        self._dirty_channels.add(str(channel_id))

    async def force_save(self):
        """강제 저장"""
        await self._save_skill_states()
        await self._save_config()
        await self._save_user_data()
        self._dirty_channels.clear()
        logger.info("강제 저장 완료")

    async def reload_from_backup(self):
        """백업에서 데이터 복원"""
        try:
            await self._restore_from_backup()
            await self.initialize()
            logger.info("백업에서 데이터 복원 완료")
        except Exception as e:
            logger.error(f"백업 복원 실패: {e}")

    # === 로깅 시스템 ===
    
    def _log_skill_action(self, channel_id: str, skill_name: str, 
                         user_id: str, action: str, details: str = ""):
        """스킬 액션 로깅"""
        if not self._db_conn:
            return
        
        try:
            cursor = self._db_conn.cursor()
            cursor.execute("""
                INSERT INTO skill_logs (channel_id, skill_name, user_id, action, details)
                VALUES (?, ?, ?, ?, ?)
            """, (channel_id, skill_name, user_id, action, details))
            self._db_conn.commit()
        except Exception as e:
            logger.error(f"스킬 로그 저장 실패: {e}")

    # === 기본 설정 생성 ===
    
    def _create_default_config(self) -> Dict:
        """기본 설정 생성"""
        return {
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
            },
            "phase1_skills": [
                "오닉셀", "피닉스", "오리븐", "카론"
            ]
        }

    # === 시스템 종료 ===
    
    async def shutdown(self):
        """시스템 종료"""
        try:
            # 자동 저장 중지
            if self._auto_save_task:
                self._auto_save_task.cancel()
                await asyncio.gather(self._auto_save_task, return_exceptions=True)
            
            # 최종 저장
            await self.force_save()
            
            # DB 연결 종료
            if self._db_conn:
                self._db_conn.close()
            
            logger.info("통합 스킬 매니저 종료 완료")
            
        except Exception as e:
            logger.error(f"스킬 매니저 종료 오류: {e}")


# 싱글톤 인스턴스
skill_manager = SkillManager()

