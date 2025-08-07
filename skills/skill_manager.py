# skills/skill_manager.py
import json
import asyncio
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Set
from pathlib import Path
import aiofiles

logger = logging.getLogger(__name__)

class SkillManager:
    """효율적인 스킬 상태 관리 클래스 (24시간 작동 최적화)"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        """싱글톤 패턴으로 메모리 효율성 확보"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        # 경로 설정
        self.skills_dir = Path("skills")
        self.config_dir = self.skills_dir / "config"
        self.data_dir = self.skills_dir / "data"
        
        # 디렉토리 생성
        for dir_path in [self.skills_dir, self.config_dir, self.data_dir]:
            dir_path.mkdir(exist_ok=True)
        
        # 파일 경로
        self.states_file = self.data_dir / "skill_states.json"
        self.backup_db = self.data_dir / "skill_backup.db"
        self.config_file = self.config_dir / "skill_config.json"
        self.user_skills_file = self.config_dir / "user_skills.json"
        
        # 메모리 캐시 (디스크 I/O 최소화)
        self._skill_states: Dict[str, Dict] = {}
        self._user_skills: Dict[str, Dict] = {}
        self._config: Dict[str, Any] = {}
        
        # 성능 최적화 변수
        self._dirty_channels: Set[str] = set()  # 변경된 채널만 저장
        self._last_save = datetime.now()
        self._save_task = None
        
        self._initialized = True
    
    async def initialize(self):
        """비동기 초기화"""
        async with self._lock:
            await self._load_all_data()
            await self._init_backup_db()
            self._start_auto_save()
            logger.info("SkillManager 초기화 완료")
    
    async def _load_all_data(self):
        """모든 데이터를 메모리로 로드"""
        # 병렬 로딩으로 성능 향상
        tasks = [
            self._load_json_safe(self.states_file, {}),
            self._load_json_safe(self.user_skills_file, {}),
            self._load_json_safe(self.config_file, self._get_default_config())
        ]
        
        results = await asyncio.gather(*tasks)
        self._skill_states, self._user_skills, self._config = results
        
        logger.info(f"데이터 로딩 완료 - 채널: {len(self._skill_states)}개, 유저: {len(self._user_skills)}개")
    
    async def _load_json_safe(self, file_path: Path, default_value: Any) -> Any:
        """안전한 JSON 로딩"""
        try:
            if file_path.exists():
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content) if content.strip() else default_value
        except Exception as e:
            logger.error(f"JSON 로딩 실패 {file_path}: {e}")
        
        return default_value
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정"""
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
                "카론": ["all_users", "admin", "monster"]
            },
            "authorized_admins": ["1007172975222603798", "1090546247770832910"],
            "authorized_nickname": "system | 시스템"
        }
    
    async def _init_backup_db(self):
        """백업 DB 초기화"""
        try:
            async with aiofiles.open(self.backup_db, 'w+b') as f:
                pass  # 파일 생성만
            
            # 동기적 DB 초기화 (빠른 실행)
            with sqlite3.connect(self.backup_db) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS skill_states (
                        channel_id TEXT PRIMARY KEY,
                        battle_data TEXT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"백업 DB 초기화 실패: {e}")
    
    def _start_auto_save(self):
        """자동 저장 태스크 시작"""
        if self._save_task is None:
            self._save_task = asyncio.create_task(self._auto_save_loop())
    
    async def _auto_save_loop(self):
        """주기적 자동 저장 (30초마다)"""
        while True:
            try:
                await asyncio.sleep(30)
                if self._dirty_channels:  # 변경사항이 있을 때만 저장
                    await self._save_dirty_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"자동 저장 중 오류: {e}")
    
    async def _save_dirty_data(self):
        """변경된 데이터만 저장 (성능 최적화)"""
        if not self._dirty_channels:
            return
        
        try:
            # JSON 저장
            async with aiofiles.open(self.states_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._skill_states, ensure_ascii=False, indent=2))
            
            # 백업 DB 저장 (변경된 채널만)
            dirty_channels = list(self._dirty_channels)
            self._dirty_channels.clear()
            
            await asyncio.get_event_loop().run_in_executor(
                None, self._save_to_backup_db, dirty_channels
            )
            
            logger.debug(f"자동 저장 완료 - {len(dirty_channels)}개 채널")
            
        except Exception as e:
            logger.error(f"데이터 저장 실패: {e}")
    
    def _save_to_backup_db(self, channels: list):
        """백업 DB에 저장 (동기 실행)"""
        try:
            with sqlite3.connect(self.backup_db) as conn:
                for channel_id in channels:
                    if channel_id in self._skill_states:
                        conn.execute(
                            "INSERT OR REPLACE INTO skill_states (channel_id, battle_data) VALUES (?, ?)",
                            (channel_id, json.dumps(self._skill_states[channel_id]))
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"백업 DB 저장 실패: {e}")
    
    # === 공개 메서드 ===
    
    def get_channel_state(self, channel_id: str) -> Dict[str, Any]:
        """채널 상태 조회 (메모리에서 즉시 반환)"""
        return self._skill_states.get(str(channel_id), {
            "battle_active": False,
            "current_round": 0,
            "active_skills": {},
            "disabled_skills": [],
            "special_effects": {}
        })
    
    def mark_dirty(self, channel_id: str):
        """채널을 변경됨으로 표시"""
        self._dirty_channels.add(str(channel_id))
    
    def add_skill(self, channel_id: str, skill_name: str, user_id: str, 
                  user_name: str, target_id: str, target_name: str, 
                  duration: int) -> bool:
        """스킬 추가"""
        channel_id = str(channel_id)
        state = self.get_channel_state(channel_id)
        
        # 중복 체크
        if skill_name in state["active_skills"]:
            return False
        
        # 개인 스킬 제한 체크 (한 명당 하나)
        user_skills = [s for s in state["active_skills"].values() if s["user_id"] == str(user_id)]
        if user_skills:
            return False
        
        # 스킬 추가
        current_round = state.get("current_round", 1)
        state["active_skills"][skill_name] = {
            "user_id": str(user_id),
            "user_name": user_name,
            "target_id": str(target_id),
            "target_name": target_name,
            "rounds_left": duration,
            "started_round": current_round
        }
        
        self._skill_states[channel_id] = state
        self.mark_dirty(channel_id)
        return True
    
    def remove_skill(self, channel_id: str, skill_name: str) -> bool:
        """스킬 제거"""
        channel_id = str(channel_id)
        state = self.get_channel_state(channel_id)
        
        if skill_name in state["active_skills"]:
            del state["active_skills"][skill_name]
            self._skill_states[channel_id] = state
            self.mark_dirty(channel_id)
            return True
        return False
    
    def update_round(self, channel_id: str, round_num: int):
        """라운드 업데이트 및 만료된 스킬 정리"""
        channel_id = str(channel_id)
        state = self.get_channel_state(channel_id)
        state["current_round"] = round_num
        
        # 만료된 스킬 찾기
        expired_skills = []
        for skill_name, skill_data in state["active_skills"].items():
            if skill_data["rounds_left"] <= 0:
                expired_skills.append(skill_name)
        
        # 만료된 스킬 제거
        for skill_name in expired_skills:
            del state["active_skills"][skill_name]
        
        self._skill_states[channel_id] = state
        self.mark_dirty(channel_id)
        
        return expired_skills
    
    def decrease_skill_rounds(self, channel_id: str):
        """모든 스킬의 남은 라운드 감소"""
        channel_id = str(channel_id)
        state = self.get_channel_state(channel_id)
        
        for skill_data in state["active_skills"].values():
            skill_data["rounds_left"] = max(0, skill_data["rounds_left"] - 1)
        
        self._skill_states[channel_id] = state
        self.mark_dirty(channel_id)
    
    def get_user_allowed_skills(self, user_id: str) -> list:
        """유저가 사용 가능한 스킬 목록"""
        user_data = self._user_skills.get(str(user_id), {})
        return user_data.get("allowed_skills", [])
    
    def is_admin(self, user_id: str, display_name: str = "") -> bool:
        """관리자 권한 체크"""
        return (str(user_id) in self._config["authorized_admins"] or 
                display_name == self._config["authorized_nickname"])
    
    def get_config(self, key: str, default=None):
        """설정 값 조회"""
        return self._config.get(key, default)
    
    def clear_channel_data(self, channel_id: str):
        """채널 데이터 초기화 (전투 종료 시)"""
        channel_id = str(channel_id)
        if channel_id in self._skill_states:
            del self._skill_states[channel_id]
            self.mark_dirty(channel_id)
    
    async def force_save(self):
        """강제 저장"""
        self._dirty_channels.update(self._skill_states.keys())
        await self._save_dirty_data()
    
    async def shutdown(self):
        """종료 시 정리"""
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        
        await self.force_save()
        logger.info("SkillManager 종료 완료")

# 전역 인스턴스
skill_manager = SkillManager()