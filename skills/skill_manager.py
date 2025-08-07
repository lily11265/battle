# skills/skill_manager.py
"""
스킬 상태 관리 시스템
- JSON 파일 기반 상태 저장/로드
- 24시간 운영을 위한 메모리 최적화
- 백업/복구 시스템
"""
import json
import sqlite3
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiofiles
import weakref
import gc

logger = logging.getLogger(__name__)

class SkillManager:
    """스킬 상태 관리자 - 24시간 운영 최적화"""
    
    def __init__(self):
        # 24시간 운영을 위한 메모리 최적화
        self._skill_states: Dict[str, Dict] = {}
        self._config: Dict[str, Any] = {}
        self._user_skills: Dict[str, Dict] = {}
        self._dirty_channels: set = set()
        
        # 파일 경로 설정
        self.skills_dir = Path("skills")
        self.config_dir = self.skills_dir / "config"
        self.data_dir = self.skills_dir / "data"
        
        # 백업 DB 경로
        self.backup_db_path = self.data_dir / "skill_backup.db"
        
        # 성능 최적화를 위한 캐시
        self._admin_cache = weakref.WeakValueDictionary()
        self._last_save_time = {}
        self._save_lock = asyncio.Lock()
        
        # 자동 저장 태스크
        self._auto_save_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """초기화 및 데이터 로드"""
        try:
            # 디렉토리 생성
            for dir_path in [self.skills_dir, self.config_dir, self.data_dir]:
                dir_path.mkdir(exist_ok=True)
            
            # 백업 DB 초기화
            await self._init_backup_db()
            
            # 설정 파일들 로드
            await self._load_config()
            await self._load_user_skills()
            await self._load_skill_states()
            
            # 자동 저장 시스템 시작
            self._start_auto_save()
            
            logger.info("SkillManager 초기화 완료")
            
        except Exception as e:
            logger.error(f"SkillManager 초기화 실패: {e}")
            raise
    
    async def _init_backup_db(self):
        """백업 DB 초기화"""
        try:
            conn = sqlite3.connect(str(self.backup_db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS skill_states (
                    channel_id TEXT PRIMARY KEY,
                    battle_data TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config_backup (
                    config_type TEXT PRIMARY KEY,
                    config_data TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info("백업 DB 초기화 완료")
            
        except Exception as e:
            logger.error(f"백업 DB 초기화 실패: {e}")
    
    async def _load_config(self):
        """설정 파일 로드"""
        config_file = self.config_dir / "skill_config.json"
        
        try:
            if config_file.exists():
                async with aiofiles.open(config_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self._config = json.loads(content)
            else:
                # 기본 설정 생성
                self._config = self._create_default_config()
                await self._save_config()
            
            logger.info(f"설정 파일 로드 완료: {len(self._config)} 항목")
            
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {e}")
            self._config = self._create_default_config()
    
    async def _load_user_skills(self):
        """유저별 스킬 권한 파일 로드"""
        user_skills_file = self.config_dir / "user_skills.json"
        
        try:
            if user_skills_file.exists():
                async with aiofiles.open(user_skills_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self._user_skills = json.loads(content)
            else:
                self._user_skills = {}
                await self._save_user_skills()
            
            logger.info(f"유저 스킬 권한 로드 완료: {len(self._user_skills)} 유저")
            
        except Exception as e:
            logger.error(f"유저 스킬 권한 로드 실패: {e}")
            self._user_skills = {}
    
    async def _load_skill_states(self):
        """스킬 상태 파일 로드"""
        states_file = self.data_dir / "skill_states.json"
        
        try:
            if states_file.exists():
                async with aiofiles.open(states_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self._skill_states = json.loads(content)
            else:
                self._skill_states = {}
                await self._save_skill_states()
            
            # 백업 DB에서 복구 시도
            await self._try_restore_from_backup()
            
            logger.info(f"스킬 상태 로드 완료: {len(self._skill_states)} 채널")
            
        except Exception as e:
            logger.error(f"스킬 상태 로드 실패: {e}")
            # 백업 DB에서 복구 시도
            await self._try_restore_from_backup()
    
    async def _try_restore_from_backup(self):
        """백업 DB에서 복구 시도"""
        try:
            conn = sqlite3.connect(str(self.backup_db_path))
            cursor = conn.cursor()
            
            cursor.execute('SELECT channel_id, battle_data FROM skill_states')
            rows = cursor.fetchall()
            
            restored_count = 0
            for channel_id, battle_data in rows:
                if channel_id not in self._skill_states:
                    self._skill_states[channel_id] = json.loads(battle_data)
                    restored_count += 1
            
            conn.close()
            
            if restored_count > 0:
                logger.info(f"백업 DB에서 {restored_count}개 채널 복구")
            
        except Exception as e:
            logger.warning(f"백업 DB 복구 실패: {e}")
    
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
            }
        }
    
    def _start_auto_save(self):
        """자동 저장 시스템 시작"""
        if self._auto_save_task is None or self._auto_save_task.done():
            self._auto_save_task = asyncio.create_task(self._auto_save_loop())
    
    async def _auto_save_loop(self):
        """자동 저장 루프 - 24시간 안정성"""
        save_interval = self.get_config("system_settings", {}).get("auto_save_interval", 30)
        
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(save_interval)
                
                if self._dirty_channels:
                    async with self._save_lock:
                        await self._save_skill_states()
                        await self._backup_to_db()
                        self._dirty_channels.clear()
                
                # 주기적으로 가비지 컬렉션 실행 (메모리 최적화)
                if self.get_config("system_settings", {}).get("performance_mode", True):
                    gc.collect()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"자동 저장 루프 오류: {e}")
    
    # === 스킬 상태 관리 메서드들 ===
    
    def add_skill(self, channel_id: str, skill_name: str, user_id: str, 
                  user_name: str, target_id: str, target_name: str, rounds: int) -> bool:
        """스킬 추가"""
        try:
            channel_state = self.get_channel_state(channel_id)
            
            # 중복 스킬 체크
            if skill_name in channel_state["active_skills"]:
                return False
            
            # 개인 스킬 제한 체크 (한 명당 하나)
            for active_skill, skill_data in channel_state["active_skills"].items():
                if skill_data["user_id"] == user_id:
                    return False
            
            # 스킬 추가
            channel_state["active_skills"][skill_name] = {
                "user_id": user_id,
                "user_name": user_name,
                "target_id": target_id,
                "target_name": target_name,
                "rounds_left": rounds,
                "started_round": channel_state.get("current_round", 1)
            }
            
            self.mark_dirty(channel_id)
            return True
            
        except Exception as e:
            logger.error(f"스킬 추가 실패 {skill_name}: {e}")
            return False
    
    def remove_skill(self, channel_id: str, skill_name: str) -> bool:
        """스킬 제거"""
        try:
            channel_state = self.get_channel_state(channel_id)
            
            if skill_name in channel_state["active_skills"]:
                del channel_state["active_skills"][skill_name]
                self.mark_dirty(channel_id)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"스킬 제거 실패 {skill_name}: {e}")
            return False
    
    def get_channel_state(self, channel_id: str) -> Dict:
        """채널 상태 조회 (메모리 최적화)"""
        if channel_id not in self._skill_states:
            self._skill_states[channel_id] = {
                "battle_active": False,
                "current_round": 1,
                "active_skills": {},
                "disabled_skills": [],
                "special_effects": {}
            }
        
        return self._skill_states[channel_id]
    
    def mark_dirty(self, channel_id: str):
        """변경사항 표시 - 효율적인 저장을 위해"""
        self._dirty_channels.add(channel_id)
    
    def update_round(self, channel_id: str, new_round: int):
        """라운드 업데이트 및 스킬 지속시간 감소"""
        try:
            channel_state = self.get_channel_state(channel_id)
            old_round = channel_state.get("current_round", 1)
            channel_state["current_round"] = new_round
            
            # 스킬 지속시간 감소
            skills_to_remove = []
            for skill_name, skill_data in channel_state["active_skills"].items():
                skill_data["rounds_left"] -= 1
                if skill_data["rounds_left"] <= 0:
                    skills_to_remove.append(skill_name)
            
            # 만료된 스킬 제거
            for skill_name in skills_to_remove:
                self.remove_skill(channel_id, skill_name)
            
            self.mark_dirty(channel_id)
            
            if skills_to_remove:
                logger.info(f"라운드 {new_round}: 만료된 스킬들 - {skills_to_remove}")
            
        except Exception as e:
            logger.error(f"라운드 업데이트 실패: {e}")
    
    def clear_channel_state(self, channel_id: str):
        """채널 상태 초기화 (전투 종료시)"""
        try:
            if channel_id in self._skill_states:
                del self._skill_states[channel_id]
                self._dirty_channels.discard(channel_id)
                logger.info(f"채널 상태 초기화: {channel_id}")
            
        except Exception as e:
            logger.error(f"채널 상태 초기화 실패: {e}")
    
    # === 권한 관리 메서드들 ===
    
    def is_admin(self, user_id: str, display_name: str) -> bool:
        """관리자 권한 체크 (캐싱으로 성능 최적화)"""
        cache_key = f"{user_id}_{display_name}"
        
        if cache_key in self._admin_cache:
            return self._admin_cache[cache_key]
        
        # 실제 권한 체크
        authorized_admins = self.get_config("authorized_admins", [])
        authorized_nickname = self.get_config("authorized_nickname", "system | 시스템")
        
        is_admin = (user_id in authorized_admins or 
                   display_name == authorized_nickname)
        
        # 메모리 효율성을 위한 WeakValueDictionary 사용
        class AdminStatus:
            def __init__(self, status):
                self.status = status
        
        self._admin_cache[cache_key] = AdminStatus(is_admin)
        return is_admin
    
    def get_user_allowed_skills(self, user_id: str) -> List[str]:
        """유저별 허용 스킬 목록"""
        user_data = self._user_skills.get(user_id, {})
        return user_data.get("allowed_skills", [])
    
    def get_config(self, key: str, default=None):
        """설정값 조회"""
        return self._config.get(key, default)
    
    # === 저장/로드 메서드들 ===
    
    async def _save_skill_states(self):
        """스킬 상태 저장 (비동기 I/O 최적화)"""
        try:
            states_file = self.data_dir / "skill_states.json"
            
            # 메모리에서 불필요한 빈 채널 상태 정리
            clean_states = {}
            for channel_id, state in self._skill_states.items():
                if (state["active_skills"] or state["special_effects"] or 
                    state["battle_active"] or len(state["disabled_skills"]) > 0):
                    clean_states[channel_id] = state
            
            async with aiofiles.open(states_file, 'w', encoding='utf-8') as f:
                content = json.dumps(clean_states, ensure_ascii=False, indent=2)
                await f.write(content)
            
            self._last_save_time[states_file.name] = datetime.now()
            
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
    
    async def _backup_to_db(self):
        """백업 DB 저장 (24시간 안정성)"""
        try:
            conn = sqlite3.connect(str(self.backup_db_path))
            cursor = conn.cursor()
            
            # 스킬 상태 백업
            for channel_id, state in self._skill_states.items():
                if state["active_skills"] or state["special_effects"]:
                    cursor.execute('''
                        INSERT OR REPLACE INTO skill_states 
                        (channel_id, battle_data, last_updated)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    ''', (channel_id, json.dumps(state)))
            
            # 설정 백업
            cursor.execute('''
                INSERT OR REPLACE INTO config_backup
                (config_type, config_data, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', ("main_config", json.dumps(self._config)))
            
            cursor.execute('''
                INSERT OR REPLACE INTO config_backup
                (config_type, config_data, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', ("user_skills", json.dumps(self._user_skills)))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"백업 DB 저장 실패: {e}")
    
    async def force_save(self):
        """강제 저장 (봇 종료시 등)"""
        try:
            async with self._save_lock:
                await self._save_skill_states()
                await self._backup_to_db()
                self._dirty_channels.clear()
                logger.info("강제 저장 완료")
            
        except Exception as e:
            logger.error(f"강제 저장 실패: {e}")
    
    async def shutdown(self):
        """시스템 종료 처리"""
        try:
            self._shutdown_event.set()
            
            if self._auto_save_task and not self._auto_save_task.done():
                self._auto_save_task.cancel()
                try:
                    await self._auto_save_task
                except asyncio.CancelledError:
                    pass
            
            await self.force_save()
            logger.info("SkillManager 종료 완료")
            
        except Exception as e:
            logger.error(f"종료 처리 실패: {e}")

# 전역 인스턴스
skill_manager = SkillManager()
