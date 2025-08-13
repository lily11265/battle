# utility.py - 최적화된 버전 (메타데이터 에러 수정)
import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional, Union, Set
import gspread
from google.oauth2.service_account import Credentials
from asyncio import Lock
import aiofiles
from collections import OrderedDict
import hashlib
import gc  # 가비지 컬렉션 추가
from datetime import datetime

logger = logging.getLogger(__name__)

# Google Sheets 설정 - 새로운 스프레드시트 URL
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_URL_INVENTORY = "https://docs.google.com/spreadsheets/d/1XIO0XZUicfGaSh5R-GdmGWWVUBBMzDYG1MhXmdbFpEQ/edit?usp=sharing"
SPREADSHEET_URL_METADATA = "https://docs.google.com/spreadsheets/d/1hYJHRjVTwcmKoxSHINhKApVHmCSmqEVOP7SQpjj3Pwg/edit?usp=sharing"

# API 호출 제한 설정
API_RATE_LIMIT = 60  # 분당 60회로 감소 (안정성 향상)
API_RATE_WINDOW = 60  # 60초
BATCH_SIZE = 10  # 배치 처리 크기

class APIRateLimiter:
    """Google Sheets API Rate Limiter"""
    def __init__(self, max_calls: int = API_RATE_LIMIT, window: int = API_RATE_WINDOW):
        self.max_calls = max_calls
        self.window = window
        self.calls = []
        self._lock = Lock()
    
    async def wait_if_needed(self):
        """API 호출 전 rate limit 확인 및 대기"""
        async with self._lock:
            now = time.time()
            # 오래된 호출 기록 제거
            self.calls = [call_time for call_time in self.calls if now - call_time < self.window]
            
            if len(self.calls) >= self.max_calls:
                # 가장 오래된 호출로부터 window 시간이 지날 때까지 대기
                sleep_time = self.window - (now - self.calls[0]) + 0.1
                logger.warning(f"API rate limit 도달. {sleep_time:.1f}초 대기")
                await asyncio.sleep(sleep_time)
                # 대기 후 다시 정리
                now = time.time()
                self.calls = [call_time for call_time in self.calls if now - call_time < self.window]
            
            self.calls.append(now)

# 전역 rate limiter
api_limiter = APIRateLimiter()

class SheetConnectionPool:
    """Google Sheets 연결 풀 (개선된 버전)"""
    def __init__(self):
        self._credentials = None
        self._gc = None
        self._inventory_sheet = None
        self._metadata_sheet = None
        self._lock = Lock()
        self._last_refresh = 0
        self._refresh_interval = 1800  # 30분마다 연결 갱신 (메모리 누수 방지)
        self._connection_retries = 0
        self._max_retries = 3
    
    async def get_sheets(self):
        """시트 연결을 반환 (필요시 재연결)"""
        async with self._lock:
            current_time = time.time()
            
            # 연결 갱신이 필요한지 확인
            if current_time - self._last_refresh > self._refresh_interval:
                logger.info("시트 연결 갱신 중...")
                self._inventory_sheet = None
                self._metadata_sheet = None
                self._gc = None
                gc.collect()  # 가비지 컬렉션 강제 실행
            
            if self._credentials is None:
                self._credentials = Credentials.from_service_account_file(
                    "service_account.json", scopes=SCOPES
                )
            
            for attempt in range(self._max_retries):
                try:
                    if self._gc is None:
                        self._gc = gspread.authorize(self._credentials)
                        self._last_refresh = current_time
                    
                    if self._inventory_sheet is None:
                        self._inventory_sheet = self._gc.open_by_url(SPREADSHEET_URL_INVENTORY).worksheet("러너 시트")
                    
                    if self._metadata_sheet is None:
                        self._metadata_sheet = self._gc.open_by_url(SPREADSHEET_URL_METADATA).worksheet("메타데이터시트")
                    
                    self._connection_retries = 0
                    return self._inventory_sheet, self._metadata_sheet
                    
                except Exception as e:
                    self._connection_retries += 1
                    logger.error(f"시트 연결 실패 (시도 {attempt + 1}/{self._max_retries}): {e}")
                    
                    if attempt < self._max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # 지수 백오프
                    else:
                        # 모든 재시도 실패 시 연결 초기화
                        self._gc = None
                        self._inventory_sheet = None
                        self._metadata_sheet = None
                        raise

# 전역 연결 풀
sheet_pool = SheetConnectionPool()

class InMemoryCache:
    """최적화된 인메모리 캐시 시스템 - 메모리 효율성 개선"""
    
    def __init__(self, max_size: int = 1000, cleanup_threshold: float = 0.8):
        self._cache = OrderedDict()
        self._ttl = {}
        self._access_count = {}
        self._access_time = {}
        self._max_size = max_size  # 크기 감소
        self._cleanup_threshold = cleanup_threshold
        self._lock = Lock()
        self._background_cleanup_task = None
        self._cleanup_interval = 600  # 10분마다 정리
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
        self._memory_check_interval = 1800  # 30분마다 메모리 체크

    async def get(self, key: str) -> Optional[Union[Dict, str]]:
        """캐시에서 값 가져오기"""
        current_time = time.time()
        async with self._lock:
            if key in self._cache:
                if self._ttl[key] > current_time:
                    # 캐시 히트
                    self._stats['hits'] += 1
                    self._access_count[key] = self._access_count.get(key, 0) + 1
                    self._access_time[key] = current_time
                    # LRU: 최근 사용한 것을 끝으로 이동
                    self._cache.move_to_end(key)
                    return self._cache[key]
                else:
                    # 만료된 키 즉시 정리
                    self._remove_key(key)
            
            self._stats['misses'] += 1
            return None

    async def set(self, key: str, value: Union[Dict, str], ex: int = 3600):
        """캐시에 값 설정 (메모리 효율성 개선)"""
        try:
            # 큰 객체는 캐시하지 않음
            if isinstance(value, str) and len(value) > 100000:  # 100KB 이상
                logger.debug(f"큰 객체 캐시 스킵: {key}")
                return
                
            current_time = time.time()
            async with self._lock:
                # 캐시 크기 체크 및 정리
                if len(self._cache) >= self._max_size * self._cleanup_threshold:
                    await self._cleanup_expired()
                    
                    # 여전히 크기가 큰 경우 LRU 정리
                    if len(self._cache) >= self._max_size:
                        self._cleanup_lru()
                
                # 기존 키가 있으면 끝으로 이동
                if key in self._cache:
                    self._cache.move_to_end(key)
                
                self._cache[key] = value
                self._ttl[key] = current_time + ex
                self._access_count[key] = 1
                self._access_time[key] = current_time
                
        except Exception as e:
            logger.error(f"캐시 설정 실패: {key} - {e}")

    async def delete(self, key: str) -> bool:
        """캐시에서 키 삭제"""
        try:
            async with self._lock:
                if key in self._cache:
                    self._remove_key(key)
                    return True
                return False
        except Exception as e:
            logger.error(f"캐시 삭제 실패: {key} - {e}")
            return False

    async def delete_pattern(self, pattern: str):
        """패턴에 맞는 모든 키 삭제"""
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                self._remove_key(key)

    def _remove_key(self, key: str):
        """키와 관련된 모든 데이터 삭제"""
        self._cache.pop(key, None)
        self._ttl.pop(key, None)
        self._access_count.pop(key, None)
        self._access_time.pop(key, None)

    def _cleanup_lru(self):
        """개선된 LRU 방식으로 캐시 정리"""
        current_time = time.time()
        
        # 접근 시간과 빈도를 조합한 점수 계산
        scores = {}
        for key in list(self._cache.keys()):
            access_time = self._access_time.get(key, 0)
            access_count = self._access_count.get(key, 0)
            ttl_remaining = self._ttl.get(key, current_time) - current_time
            
            # TTL이 얼마 남지 않은 항목은 우선 제거
            if ttl_remaining < 300:  # 5분 미만
                scores[key] = float('inf')
            else:
                time_score = current_time - access_time
                frequency_score = 1 / (access_count + 1)
                scores[key] = time_score * frequency_score
        
        # 점수가 높은 순으로 정렬하여 제거
        sorted_keys = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        remove_count = max(1, len(self._cache) // 5)  # 최소 1개, 최대 20% 제거
        
        for key, _ in sorted_keys[:remove_count]:
            self._remove_key(key)
            self._stats['evictions'] += 1

    async def start_background_cleanup(self):
        """백그라운드 정리 작업 시작"""
        if self._background_cleanup_task is None or self._background_cleanup_task.done():
            self._background_cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self):
        """백그라운드 정리 작업 (메모리 효율성 개선)"""
        last_memory_check = time.time()
        
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
                
                # 메모리 체크 및 강제 정리
                current_time = time.time()
                if current_time - last_memory_check > self._memory_check_interval:
                    gc.collect()  # 가비지 컬렉션
                    last_memory_check = current_time
                    
                    # 캐시 크기가 너무 크면 추가 정리
                    if len(self._cache) > self._max_size * 0.9:
                        self._cleanup_lru()
                
                # 통계 로깅 (디버그 레벨)
                total_requests = self._stats['hits'] + self._stats['misses']
                if total_requests > 0:
                    hit_rate = (self._stats['hits'] / total_requests) * 100
                    logger.debug(
                        f"캐시 통계 - 히트율: {hit_rate:.1f}%, "
                        f"총 항목: {len(self._cache)}, "
                        f"제거된 항목: {self._stats['evictions']}"
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"백그라운드 캐시 정리 실패: {e}")

    async def _cleanup_expired(self):
        """만료된 캐시 정리"""
        current_time = time.time()
        expired_keys = [k for k, v in self._ttl.items() if v <= current_time]
        for k in expired_keys:
            self._remove_key(k)
            self._stats['evictions'] += 1
        
        if expired_keys:
            logger.debug(f"만료된 캐시 {len(expired_keys)}개 정리됨")

    def get_stats(self) -> Dict:
        """캐시 통계 반환"""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_items': len(self._cache),
            'hit_rate': hit_rate,
            'total_hits': self._stats['hits'],
            'total_misses': self._stats['misses'],
            'total_evictions': self._stats['evictions']
        }

# 전역 캐시 인스턴스
cache_manager = InMemoryCache()

# 데이터 변경 추적을 위한 해시 계산
def calculate_data_hash(data: Union[Dict, List]) -> str:
    """데이터의 해시 계산"""
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

async def get_cached_metadata() -> Dict:
    """메타데이터 캐싱 함수 (에러 수정 버전)"""
    cached_data = await cache_manager.get("user_metadata")
    if cached_data:
        return json.loads(cached_data) if isinstance(cached_data, str) else cached_data

    try:
        # API rate limit 확인
        await api_limiter.wait_if_needed()
        
        inventory_sheet, metadata_sheet = await sheet_pool.get_sheets()
        
        # 개별 시트에서 데이터 가져오기 (batch_get 대신)
        # 이렇게 하면 한글 시트 이름 문제를 회피할 수 있습니다
        metadata_range = metadata_sheet.get("A3:D37", value_render_option='UNFORMATTED_VALUE')
        inventory_names = inventory_sheet.get("B14:B48", value_render_option='UNFORMATTED_VALUE')
        
        user_mapping = {}
        
        # 데이터 처리 최적화
        inventory_name_dict = {}
        for i, row in enumerate(inventory_names):
            if row and row[0]:
                inventory_name_dict[i] = str(row[0]).strip()
        
        for idx, row in enumerate(metadata_range):
            if len(row) < 4:
                continue
                
            # 빈 값 체크
            if not row[1] or str(row[1]).strip() == "":
                continue
                
            name = str(row[0]).strip() if row[0] else ""
            user_id = str(row[1]).strip()
            user_type = str(row[3]).strip() if row[3] else ""
            
            # 인벤토리 이름 매칭 (최적화)
            inventory_name = inventory_name_dict.get(idx)
            
            if inventory_name:
                # 이름 불일치 처리
                if name != inventory_name:
                    # 일치하는 이름 찾기
                    matching_idx = next(
                        (i for i, inv_name in inventory_name_dict.items() if inv_name == name),
                        None
                    )
                    
                    if matching_idx is not None and matching_idx < len(metadata_range):
                        if len(metadata_range[matching_idx]) >= 4:
                            user_id = str(metadata_range[matching_idx][1]).strip()
                            inventory_name = inventory_name_dict.get(matching_idx, inventory_name)
                            user_type = str(metadata_range[matching_idx][3]).strip() if metadata_range[matching_idx][3] else ""
                    else:
                        continue
                
                user_mapping[user_id] = {
                    "user_id": user_id,
                    "name": name,
                    "inventory_name": inventory_name,
                    "type": user_type
                }
        
        # 캐시에 저장 (12시간으로 단축)
        await cache_manager.set("user_metadata", json.dumps(user_mapping), ex=43200)
        logger.info(f"총 {len(user_mapping)}명의 사용자 데이터가 캐싱되었습니다.")
        
        return user_mapping
        
    except Exception as e:
        logger.error(f"메타데이터 캐싱 실패: {e}")
        # 실패 시 빈 dict 대신 이전 캐시 데이터 시도
        old_cache = await cache_manager.get("user_metadata_backup")
        if old_cache:
            logger.warning("백업 캐시 데이터 사용")
            return json.loads(old_cache) if isinstance(old_cache, str) else old_cache
        return {}

async def get_admin_id() -> str:
    """Admin ID 캐싱 함수"""
    admin_id = await cache_manager.get("admin_id")
    if admin_id:
        return admin_id

    try:
        await api_limiter.wait_if_needed()
        _, metadata_sheet = await sheet_pool.get_sheets()
        admin_id = metadata_sheet.acell("B2").value
        if admin_id:
            await cache_manager.set("admin_id", admin_id, ex=43200)  # 12시간
        return admin_id or ""
    except Exception as e:
        logger.error(f"Admin ID 가져오기 실패: {e}")
        return ""

async def get_batch_user_data(user_ids: Optional[List[str]] = None) -> Dict:
    """배치 사용자 데이터 조회 (메모리 효율성 개선)"""
    # 전체 데이터 캐시 확인
    if not user_ids:
        cached_all = await cache_manager.get("all_user_data")
        if cached_all:
            return json.loads(cached_all) if isinstance(cached_all, str) else cached_all
    
    user_metadata = await get_cached_metadata()
    if not user_metadata:
        return {}
    
    try:
        await api_limiter.wait_if_needed()
        inventory_sheet, _ = await sheet_pool.get_sheets()
        
        # 배치 가져오기로 API 호출 최소화
        inventory_data = inventory_sheet.get("B14:H48", value_render_option='UNFORMATTED_VALUE')
        
        batch_user_data = {}
        
        for row_idx, row in enumerate(inventory_data):
            if not row or not row[0]:
                continue
            
            # 행 길이 보정
            while len(row) < 7:
                row.append("")

            target_name = str(row[0]).strip()
            
            # 메타데이터에서 일치하는 사용자 찾기 (최적화)
            user_info = None
            for meta in user_metadata.values():
                if meta["inventory_name"].strip() == target_name:
                    user_info = meta
                    break
            
            if not user_info:
                continue

            user_id = user_info["user_id"]
            
            # 특정 사용자만 필터링
            if user_ids and user_id not in user_ids:
                continue

            # 데이터 파싱
            corruption_value = 0
            if row[6] and str(row[6]).strip():
                try:
                    corruption_value = int(str(row[6]).strip())
                except ValueError:
                    corruption_value = 0

            user_data = {
                "user_id": user_id,
                "name": user_info["name"],
                "inventory_name": target_name,
                "health": str(row[1]).strip() if row[1] else "",
                "coins": int(row[2]) if row[2] and str(row[2]).isdigit() else 0,
                "physical_status": [s.strip() for s in str(row[3]).split(",") if s.strip()] if row[3] else [],
                "items": [i.strip() for i in str(row[4]).split(",") if i.strip()] if row[4] else [],
                "outfits": [o.strip() for o in str(row[5]).split(",") if o.strip()] if row[5] else [],
                "corruption": corruption_value,
            }
            
            batch_user_data[user_id] = user_data
            
            # 개별 사용자 캐시 (3분으로 단축)
            await cache_manager.set(f"user_data:{user_id}", json.dumps(user_data), ex=180)

        # 전체 데이터 캐시 (30초로 단축)
        if not user_ids:
            await cache_manager.set("all_user_data", json.dumps(batch_user_data), ex=30)

        return batch_user_data
        
    except Exception as e:
        logger.error(f"배치 사용자 데이터 조회 실패: {e}")
        return {}

async def get_user_inventory(user_id: str) -> Optional[Dict]:
    """특정 사용자 인벤토리 조회 (캐시 우선)"""
    # 개별 캐시 확인
    cached = await cache_manager.get(f"user_data:{user_id}")
    if cached:
        return json.loads(cached) if isinstance(cached, str) else cached
    
    # 배치 조회
    user_data = await get_batch_user_data(user_ids=[user_id])
    return user_data.get(user_id)

async def update_player_balance(user_id: str, amount: int) -> bool:
    """플레이어 잔액 업데이트 (양수: 증가, 음수: 감소)"""
    try:
        # 현재 사용자 데이터 가져오기
        user_data = await get_user_inventory(user_id)
        if not user_data:
            logger.error(f"사용자 데이터를 찾을 수 없음: {user_id}")
            return False
        
        # 새로운 잔액 계산
        current_coins = user_data.get("coins", 0)
        new_coins = max(0, current_coins + amount)  # 음수 방지
        
        # 잔액 업데이트
        success = await update_user_inventory(
            user_id,
            coins=new_coins,
            items=user_data.get("items"),
            outfits=user_data.get("outfits"),
            physical_status=user_data.get("physical_status"),
            corruption=user_data.get("corruption"),
            health=user_data.get("health")
        )
        
        if success:
            logger.info(f"사용자 {user_id} 잔액 업데이트: {current_coins} -> {new_coins} (변화: {amount:+d})")
        
        return success
        
    except Exception as e:
        logger.error(f"잔액 업데이트 실패: {e}")
        return False

# utility.py의 update_user_inventory 함수 수정
async def update_user_inventory(user_id: str, coins: Optional[int] = None, 
                              items: Optional[List[str]] = None,
                              outfits: Optional[List[str]] = None,
                              physical_status: Optional[List[str]] = None,
                              corruption: Optional[int] = None,
                              health: Optional[str] = None):  # health 파라미터 추가
    """사용자 인벤토리 업데이트 (health 지원 추가)"""
    try:
        user_metadata = await get_cached_metadata()
        if user_id not in user_metadata:
            return False

        target_name = user_metadata[user_id]["inventory_name"]
        
        await api_limiter.wait_if_needed()
        inventory_sheet, _ = await sheet_pool.get_sheets()
        
        # 현재 데이터 가져오기
        inventory_data = inventory_sheet.get("B14:H48", value_render_option='UNFORMATTED_VALUE')
        updated_data = []
        updated = False

        for row in inventory_data:
            if not row or len(row) < 7:
                row = row + [""] * (7 - len(row)) if row else [""] * 7

            if str(row[0]).strip() == target_name:
                # 변경사항만 업데이트
                if health is not None:  # health 업데이트 추가
                    row[1] = str(health)
                    updated = True
                if coins is not None:
                    row[2] = str(coins)
                    updated = True
                if physical_status is not None:
                    row[3] = ",".join(physical_status)
                    updated = True
                if items is not None:
                    row[4] = ",".join(items)
                    updated = True
                if outfits is not None:
                    row[5] = ",".join(outfits)
                    updated = True
                if corruption is not None:
                    row[6] = str(max(0, corruption))
                    updated = True

            updated_data.append(row)

        # 변경사항이 있을 때만 업데이트
        if updated:
            inventory_sheet.update(values=updated_data, range_name="B14:H48")
            
            # 관련 캐시 무효화
            await cache_manager.delete(f"user_data:{user_id}")
            await cache_manager.delete("all_user_data")
            await cache_manager.delete(f"user_inventory_display:{user_id}")
            
        return True
        
    except Exception as e:
        logger.error(f"인벤토리 업데이트 실패: {e}")
        return False

async def batch_update_user_inventory(updates: Dict):
    """배치 인벤토리 업데이트 (최적화)"""
    if not updates:
        return True
        
    try:
        await api_limiter.wait_if_needed()
        inventory_sheet, _ = await sheet_pool.get_sheets()
        
        # 현재 데이터 가져오기
        inventory_data = inventory_sheet.get("B14:H48", value_render_option='UNFORMATTED_VALUE')
        metadata = await get_cached_metadata()
        
        # 업데이트할 행 인덱스 미리 계산
        update_indices = {}
        for user_id in updates.keys():
            user_meta = metadata.get(user_id)
            if user_meta:
                for idx, row in enumerate(inventory_data):
                    if row and str(row[0]).strip() == user_meta["inventory_name"].strip():
                        update_indices[user_id] = idx
                        break
        
        # 데이터 업데이트
        updated_data = []
        updated_users = set()
        
        for idx, row in enumerate(inventory_data):
            if not row or len(row) < 7:
                row = row + [""] * (7 - len(row)) if row else [""] * 7

            # 현재 행에 해당하는 사용자 찾기
            for user_id, row_idx in update_indices.items():
                if idx == row_idx:
                    update = updates[user_id]
                    
                    if "coins" in update:
                        row[2] = str(update["coins"])
                    if "physical_status" in update:
                        row[3] = ",".join(update["physical_status"])
                    if "items" in update:
                        row[4] = ",".join(update["items"])
                    if "outfits" in update:
                        row[5] = ",".join(update["outfits"])
                    if "corruption" in update:
                        row[6] = str(max(0, update["corruption"]))
                    
                    updated_users.add(user_id)
                    break
                    
            updated_data.append(row)

        # 배치 업데이트
        inventory_sheet.update(values=updated_data, range_name="B14:H48")
        
        # 관련 캐시 무효화 (병렬 처리)
        cache_tasks = []
        for user_id in updated_users:
            cache_tasks.append(cache_manager.delete(f"user_data:{user_id}"))
            cache_tasks.append(cache_manager.delete(f"user_inventory_display:{user_id}"))
        cache_tasks.append(cache_manager.delete("all_user_data"))
        
        if cache_tasks:
            await asyncio.gather(*cache_tasks, return_exceptions=True)
        
        logger.info(f"{len(updated_users)}명의 인벤토리가 배치 업데이트되었습니다")
        return True
        
    except Exception as e:
        logger.error(f"배치 인벤토리 업데이트 실패: {e}")
        return False

async def get_user_permissions(user_id: str) -> tuple[bool, bool]:
    """사용자 권한 확인 (캐시 사용)"""
    # 권한 캐시 확인
    cached_perms = await cache_manager.get(f"user_perms:{user_id}")
    if cached_perms:
        perms = json.loads(cached_perms) if isinstance(cached_perms, str) else cached_perms
        return perms['can_give'], perms['can_revoke']
    
    try:
        admin_id = await get_admin_id()
        if user_id == admin_id:
            perms = {'can_give': True, 'can_revoke': True}
            await cache_manager.set(f"user_perms:{user_id}", json.dumps(perms), ex=1800)  # 30분
            return True, True

        metadata = await get_cached_metadata()
        if user_id not in metadata:
            return False, False

        await api_limiter.wait_if_needed()
        _, metadata_sheet = await sheet_pool.get_sheets()
        
        # 권한 정보만 가져오기
        metadata_range = metadata_sheet.get("A3:D37", value_render_option='UNFORMATTED_VALUE')
        
        for row in metadata_range:
            if len(row) >= 4 and str(row[1]).strip() == user_id:
                can_give = str(row[2]).strip().upper() == 'Y' if row[2] else False
                can_revoke = str(row[3]).strip().upper() == 'Y' if row[3] else False
                
                # 캐시에 저장 (30분)
                perms = {'can_give': can_give, 'can_revoke': can_revoke}
                await cache_manager.set(f"user_perms:{user_id}", json.dumps(perms), ex=1800)
                
                return can_give, can_revoke
                
        return False, False
        
    except Exception as e:
        logger.error(f"권한 확인 실패: {e}")
        return False, False

def is_user_dead(user_inventory: Dict) -> bool:
    """사용자 사망 상태 확인 (최적화)"""
    if not user_inventory or "items" not in user_inventory:
        return False
    
    # 리스트 컴프리헨션 대신 빠른 체크
    return "-사망-" in user_inventory["items"]

# 전역 변수 추가
_daily_increment_lock = asyncio.Lock()
_last_daily_increment = None

async def increment_daily_values():
    """일일 코인 증가 (최적화된 배치 처리)"""
    global _last_daily_increment
    
    async with _daily_increment_lock:
        # 중복 실행 방지 - 같은 날에 이미 실행되었는지 확인
        current_date = datetime.now().date()
        if _last_daily_increment == current_date:
            logger.warning(f"일일 코인 증가가 오늘({current_date}) 이미 실행되었습니다. 스킵합니다.")
            return
        
        try:
            await api_limiter.wait_if_needed()
            inventory_sheet, _ = await sheet_pool.get_sheets()
            
            # 현재 데이터 가져오기
            data = inventory_sheet.get("B14:H48", value_render_option='UNFORMATTED_VALUE')
            updated_data = []
            update_count = 0
            
            for row in data:
                if len(row) < 5:
                    updated_data.append(row if row else [""] * 7)
                    continue
                
                # 행 길이 보정
                while len(row) < 7:
                    row.append("")
                    
                items = str(row[4]).split(",") if row[4] else []
                
                # 사망자가 아닌 경우만 코인 증가
                if "-사망-" not in items and row[2] and str(row[2]).isdigit():
                    row[2] = str(int(row[2]) + 1)
                    update_count += 1
                    
                updated_data.append(row)

            # 배치 업데이트
            inventory_sheet.update(values=updated_data, range_name="B14:H48")
            
            # 전체 캐시 무효화
            await cache_manager.delete("all_user_data")
            await cache_manager.delete_pattern("user_data:")
            await cache_manager.delete_pattern("user_inventory_display:")
            
            # 성공적으로 완료되면 날짜 기록
            _last_daily_increment = current_date
            
            logger.info(f"일일 코인 증가 완료 - {update_count}명 업데이트 (날짜: {current_date})")
            
        except Exception as e:
            logger.error(f"일일 코인 증가 실패: {e}")

async def cache_daily_metadata():
    """일일 메타데이터 캐싱 (최적화)"""
    try:
        # 백업 저장
        current_metadata = await cache_manager.get("user_metadata")
        if current_metadata:
            await cache_manager.set("user_metadata_backup", current_metadata, ex=86400)
        
        # 기존 캐시 삭제
        delete_tasks = [
            cache_manager.delete("user_metadata"),
            cache_manager.delete("admin_id"),
            cache_manager.delete("all_user_data")
        ]
        await asyncio.gather(*delete_tasks, return_exceptions=True)
        
        # 사용자별 캐시 패턴 삭제
        await cache_manager.delete_pattern("user_")
        
        # 새로운 데이터 캐싱
        await get_cached_metadata()
        await get_admin_id()
        
        # 백그라운드 정리 시작
        await cache_manager.start_background_cleanup()
        
        # 가비지 컬렉션
        gc.collect()
        
        # 캐시 통계 로깅
        stats = cache_manager.get_stats()
        logger.info(
            f"일일 메타데이터 캐싱 완료 - "
            f"캐시 항목: {stats['total_items']}, "
            f"히트율: {stats['hit_rate']:.1f}%"
        )
        
    except Exception as e:
        logger.error(f"일일 메타데이터 캐싱 실패: {e}")

# 타락도 관련 유틸리티 함수
def calculate_corruption_change(current_value: int, change: int) -> int:
    """타락도 변경 계산 (최소값 0 보장)"""
    return max(0, current_value + change)

def validate_corruption_input(input_str: str) -> tuple[bool, int]:
    """타락도 입력 유효성 검사"""
    try:
        value = int(input_str)
        return True, value
    except ValueError:
        return False, 0

# 비동기 파일 작업을 위한 헬퍼 함수
async def save_json_async(filepath: str, data: Dict):
    """JSON 파일 비동기 저장"""
    temp_file = f"{filepath}.tmp"
    try:
        async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
        # 원자적 파일 교체
        os.replace(temp_file, filepath)
    except Exception as e:
        logger.error(f"JSON 파일 저장 실패: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

async def load_json_async(filepath: str) -> Optional[Dict]:
    """JSON 파일 비동기 로드"""
    try:
        async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error(f"JSON 파일 로드 실패: {e}")
        return None