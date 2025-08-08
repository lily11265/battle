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
    """스킬 상태 관리자"""
    
    def __init__(self):
        self.base_dir = Path("skills")
        self.config_dir = self.base_dir / "config"
        self.data_dir = self.base_dir / "data"
        
        # 메모리 캐시
        self._skill_states: Dict[str, Dict] = {}
        self._config: Dict = {}
        self._user_skills: Dict = {}
        
        # 동시성 제어
        self._lock = Lock()
        self._dirty_channels: set = set()  # 저장 필요한 채널
        self._last_save_time: Dict[str, datetime] = {}
        
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
            await self._load_user_skills()
            await self._load_skill_states()
            
            # 백업 DB 초기화
            self._initialize_backup_db()
            
            # 백업에서 복구 시도
            await self._restore_from_backup()
            
            # 자동 저장 시작
            self._start_auto_save()
            
            logger.info("스킬 매니저 초기화 완료")
            
        except Exception as e:
            logger.error(f"스킬 매니저 초기화 실패: {e}")
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
    
    # === 설정 파일 로드 메서드들 ===
    
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
    
    async def _load_user_skills(self):
        """유저별 스킬 권한 로드"""
        user_skills_file = self.config_dir / "user_skills.json"
        
        if not user_skills_file.exists():
            self._user_skills = {}
            await self._save_user_skills()
        else:
            try:
                async with aiofiles.open(user_skills_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self._user_skills = json.loads(content)
            except Exception as e:
                logger.error(f"유저 스킬 파일 로드 실패: {e}")
                self._user_skills = {}
    
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
    
    # === 스킬 상태 관리 메서드들 ===
    
    def add_skill(self, channel_id: str, skill_name: str, user_id: str, 
                  user_name: str, target_id: str, target_name: str, 
                  duration: int) -> bool:
        """스킬 추가"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                # 이미 같은 스킬이 활성화되어 있는지 확인
                if skill_name in channel_state["active_skills"]:
                    logger.warning(f"스킬 이미 활성화: {skill_name}")
                    return False
                
                # 유저가 이미 다른 스킬을 사용 중인지 확인
                for active_skill, skill_data in channel_state["active_skills"].items():
                    if skill_data["user_id"] == str(user_id):
                        logger.warning(f"유저 {user_id}가 이미 {active_skill} 사용 중")
                        return False
                
                # 스킬 추가
                current_round = channel_state.get("current_round", 1)
                channel_state["active_skills"][skill_name] = {
                    "user_id": str(user_id),
                    "user_name": user_name,
                    "target_id": str(target_id) if target_id else None,
                    "target_name": target_name,
                    "rounds_left": duration,
                    "started_round": current_round,
                    "activated_at": datetime.now().isoformat()
                }
                
                self.mark_dirty(channel_id)
                self._log_skill_action(channel_id, skill_name, user_id, "activate", 
                                     f"Duration: {duration} rounds")
                
                logger.info(f"스킬 추가: {skill_name} - 채널: {channel_id}")
                return True
                
        except Exception as e:
            logger.error(f"스킬 추가 실패: {e}")
            return False
    
    def remove_skill(self, channel_id: str, skill_name: str) -> bool:
        """스킬 제거"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                if skill_name not in channel_state["active_skills"]:
                    return False
                
                skill_data = channel_state["active_skills"].pop(skill_name)
                self.mark_dirty(channel_id)
                
                self._log_skill_action(channel_id, skill_name, 
                                     skill_data["user_id"], "remove", "Manual removal")
                
                logger.info(f"스킬 제거: {skill_name} - 채널: {channel_id}")
                return True
                
        except Exception as e:
            logger.error(f"스킬 제거 실패: {e}")
            return False
    
    def get_channel_state(self, channel_id: str) -> Dict:
        """채널 상태 조회 (없으면 생성)"""
        channel_id = str(channel_id)
        
        if channel_id not in self._skill_states:
            self._skill_states[channel_id] = self._create_empty_channel_state()
            self.mark_dirty(channel_id)
        
        return self._skill_states[channel_id]
    
    def _create_empty_channel_state(self) -> Dict:
        """빈 채널 상태 생성"""
        return {
            "battle_active": False,
            "current_round": 1,
            "active_skills": {},
            "disabled_skills": [],
            "special_effects": {},
            "last_updated": datetime.now().isoformat()
        }
    
    def update_round(self, channel_id: str, round_num: int):
        """라운드 업데이트"""
        channel_state = self.get_channel_state(str(channel_id))
        channel_state["current_round"] = round_num
        
        # 라운드 기반 스킬 만료 체크
        expired_skills = []
        for skill_name, skill_data in list(channel_state["active_skills"].items()):
            skill_data["rounds_left"] -= 1
            
            if skill_data["rounds_left"] <= 0:
                expired_skills.append(skill_name)
                del channel_state["active_skills"][skill_name]
                self._log_skill_action(channel_id, skill_name, 
                                      skill_data["user_id"], "expire", 
                                      f"Expired at round {round_num}")
        
        if expired_skills:
            logger.info(f"라운드 {round_num}에서 만료된 스킬: {expired_skills}")
        
        self.mark_dirty(channel_id)
    
    def clear_channel_skills(self, channel_id: str):
        """채널의 모든 스킬 초기화"""
        channel_id = str(channel_id)
        
        if channel_id in self._skill_states:
            self._skill_states[channel_id] = self._create_empty_channel_state()
            self.mark_dirty(channel_id)
            self._log_skill_action(channel_id, "ALL", "SYSTEM", "clear", 
                                  "Battle ended or reset")
            logger.info(f"채널 {channel_id}의 모든 스킬 초기화")
    
    # === 권한 관리 메서드들 ===
    
    def is_admin(self, user_id: str, display_name: str = "") -> bool:
        """ADMIN 권한 확인"""
        # 설정된 ADMIN ID 확인
        admin_ids = self._config.get("authorized_admins", [])
        if str(user_id) in admin_ids:
            return True
        
        # 닉네임으로 확인
        admin_nickname = self._config.get("authorized_nickname", "")
        if admin_nickname and admin_nickname.lower() in display_name.lower():
            return True
        
        # 몬스터 체크
        if user_id in ["monster", "admin"]:
            return True
        
        return False
    
    def get_user_allowed_skills(self, user_id: str) -> List[str]:
        """유저별 허용 스킬 목록"""
        user_data = self._user_skills.get(str(user_id), {})
        return user_data.get("allowed_skills", [])
    
    def can_use_skill(self, user_id: str, skill_name: str, display_name: str = "") -> bool:
        """스킬 사용 권한 확인"""
        # ADMIN은 모든 스킬 사용 가능
        if self.is_admin(user_id, display_name):
            return True
        
        # 스킬별 사용자 제한 확인
        skill_users = self._config.get("skill_users", {}).get(skill_name, [])
        
        # 특정 유저 ID만 허용
        if str(user_id) in skill_users:
            return True
        
        # all_users 허용
        if "all_users" in skill_users or "users_only" in skill_users:
            # 개인 허용 목록 확인
            allowed_skills = self.get_user_allowed_skills(user_id)
            return skill_name in allowed_skills
        
        return False
    
    def get_config(self, key: str, default=None):
        """설정값 조회"""
        return self._config.get(key, default)
    
    # === 저장/로드 메서드들 ===
    
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
            
        except Exception as e:
            logger.error(f"설정 파일 저장 실패: {e}")
    
    async def _save_user_skills(self):
        """유저 스킬 권한 저장"""
        try:
            user_skills_file = self.config_dir / "user_skills.json"
            async with aiofiles.open(user_skills_file, 'w', encoding='utf-8') as f:
                content = json.dumps(self._user_skills, ensure_ascii=False, indent=2)
                await f.write(content)
            
        except Exception as e:
            logger.error(f"유저 스킬 권한 저장 실패: {e}")
    
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
    
    # === 자동 저장 ===
    
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
                    #await self._save_skill_states()
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
        await self._save_user_skills()
        self._dirty_channels.clear()
        logger.info("강제 저장 완료")
    
    # === 로깅 ===
    
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
    
    def end_battle(self, channel_id: str):
        """전투 종료 - 메모리에서만 삭제"""
        try:
            with self._lock:
                channel_id = str(channel_id)
                channel_state = self.get_channel_state(channel_id)
                
                if not channel_state["battle_active"]:
                    logger.warning(f"채널 {channel_id}에 활성 전투가 없습니다.")
                    return
                
                # 전투 종료 처리
                channel_state["battle_active"] = False
                channel_state["current_round"] = 1
                channel_state["active_skills"].clear()
                channel_state["disabled_skills"].clear()
                channel_state["special_effects"].clear()
                
                # 파일에 저장하지 않고 메모리에서만 제거
                if channel_id in self._skill_states:
                    del self._skill_states[channel_id]
                
                self._log_skill_action(channel_id, "ALL", "SYSTEM", "end_battle", 
                                     "Battle ended - skills cleared from memory only")
                
                logger.info(f"채널 {channel_id}의 전투 종료 - 스킬 상태 초기화 (메모리만)")
            
    except Exception as e:
        logger.error(f"전투 종료 처리 실패: {e}")
    
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
    
    # === 종료 처리 ===
    
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
            
            logger.info("스킬 매니저 종료 완료")
            
        except Exception as e:
            logger.error(f"스킬 매니저 종료 오류: {e}")

# 싱글톤 인스턴스
skill_manager = SkillManager()


