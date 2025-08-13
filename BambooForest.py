# BambooForest.py - 최적화 및 수정된 버전
import asyncio
import datetime
import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Union
import discord
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials
from collections import OrderedDict
import aiohttp
from dataclasses import dataclass, field
from enum import Enum
import weakref

logger = logging.getLogger(__name__)

# 설정
SCOPES_DRIVE = ['https://www.googleapis.com/auth/drive.file']
BAMBOO_FOLDER_ID = '1OUDj9HcY_zZNeraxNOFl1PwVGBNmzfMN'
SPECIAL_USER_IDS = {"1007172975222603798", "1090546247770832910"}  # Set으로 변경 (더 빠른 조회)

# Rate limit 설정
RATE_LIMIT_DELAY = 1.0
MAX_RETRIES = 3

class MessageType(Enum):
    """메시지 타입 열거형"""
    TEXT = "text"
    IMAGE = "image"

@dataclass
class MessagePart:
    """메시지 구성 요소"""
    type: MessageType
    content: Union[str, discord.Attachment]
    order: int
    url: Optional[str] = None

@dataclass
class AnonymousMessage:
    """익명 메시지 그룹"""
    message_ids: List[int] = field(default_factory=list)
    parts: List[MessagePart] = field(default_factory=list)
    author_id: str = ""
    thread_id: int = 0
    created_at: str = ""
    edited: bool = False
    edit_history: List[Dict] = field(default_factory=list)

class RateLimiter:
    """개선된 Rate limiting 클래스"""
    def __init__(self):
        self.last_request_time = {}
        self.retry_after = {}
        self._lock = asyncio.Lock()
        
    async def wait_if_needed(self, key: str, min_delay: float = RATE_LIMIT_DELAY):
        """필요시 rate limit 대기"""
        async with self._lock:
            current_time = datetime.datetime.now()
            
            if key in self.last_request_time:
                elapsed = (current_time - self.last_request_time[key]).total_seconds()
                if elapsed < min_delay:
                    await asyncio.sleep(min_delay - elapsed)
            
            self.last_request_time[key] = datetime.datetime.now()
            
            # 오래된 항목 정리 (메모리 절약)
            if len(self.last_request_time) > 100:
                cutoff_time = current_time - datetime.timedelta(minutes=5)
                self.last_request_time = {
                    k: v for k, v in self.last_request_time.items()
                    if v > cutoff_time
                }

class MessageCache:
    """메모리 효율적인 메시지 캐싱"""
    def __init__(self, max_size: int = 50):  # 크기 축소
        self.cache = OrderedDict()
        self.max_size = max_size
        self._access_count = {}
        
    def get(self, key: str) -> Optional[List]:
        """캐시에서 메시지 가져오기"""
        if key in self.cache:
            self.cache.move_to_end(key)
            self._access_count[key] = self._access_count.get(key, 0) + 1
            return self.cache[key]
        return None
        
    def set(self, key: str, value: List):
        """캐시에 메시지 저장"""
        # 크기 제한 확인
        if key not in self.cache and len(self.cache) >= self.max_size:
            # LFU 방식으로 제거
            if self._access_count:
                least_used = min(self.cache.keys(), key=lambda k: self._access_count.get(k, 0))
                self.cache.pop(least_used)
                self._access_count.pop(least_used, None)
            else:
                self.cache.popitem(last=False)
        
        self.cache[key] = value
        self.cache.move_to_end(key)
        self._access_count[key] = 1

class BambooForestSystem:
    """최적화된 익명 게시판 시스템"""
    
    def __init__(self, bot):
        self.bot = weakref.ref(bot)  # 약한 참조로 순환 참조 방지
        self.drive_service = self._setup_drive_service()
        self.bamboo_forest_sessions = {}
        self.anonymous_messages = {}
        self.message_to_group = {}
        self.dm_edit_sessions = {}
        self.mapping_file = "bamboo_forest_mapping.json"
        
        # 최적화 구성요소
        self.rate_limiter = RateLimiter()
        self.message_cache = MessageCache(max_size=30)  # 크기 축소
        self.processing_messages = set()
        self.http_session = None
        
        # 세션 정리 설정
        self.session_timeout = 1800  # 30분으로 단축
        self.cleanup_interval = 900  # 15분마다
        self.cleanup_task = None
        
        # 채널 캐시
        self._cached_bamboo_channel = None
        self._channel_cache_time = None
        
        self._load_mappings()
        self._start_cleanup_task()
        
    def _setup_drive_service(self):
        """구글 드라이브 서비스 설정"""
        try:
            if os.path.exists("service_account.json"):
                credentials = Credentials.from_service_account_file(
                    "service_account.json", scopes=SCOPES_DRIVE)
                service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
                logger.info("구글 드라이브 서비스 초기화 성공")
                return service
        except Exception as e:
            logger.error(f"구글 드라이브 서비스 초기화 실패: {e}")
        return None
    
    async def _get_http_session(self):
        """HTTP 세션 재사용"""
        if self.http_session is None or self.http_session.closed:
            timeout = aiohttp.ClientTimeout(total=20, connect=5)  # 타임아웃 조정
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self.http_session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={'User-Agent': 'DiscordBot/1.0'}
            )
        return self.http_session
        
    async def close(self):
        """리소스 정리"""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
    
    def _start_cleanup_task(self):
        """백그라운드 정리 작업 시작"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """주기적 세션 정리"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_sessions()
                
                # 메모리 사용량 체크 및 정리
                import gc
                gc.collect(1)  # 젊은 세대만 수집 (빠름)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"백그라운드 정리 실패: {e}")
    
    async def _cleanup_expired_sessions(self):
        """만료된 세션 정리"""
        current_time = datetime.datetime.now()
        
        # 익명 게시판 세션 정리
        expired_sessions = [
            key for key, session in self.bamboo_forest_sessions.items()
            if (current_time - session.get('last_activity', current_time)).seconds > self.session_timeout
        ]
        
        for key in expired_sessions:
            del self.bamboo_forest_sessions[key]
        
        # DM 편집 세션 정리
        expired_dm_sessions = [
            user_id for user_id, session in self.dm_edit_sessions.items()
            if (current_time - session.get('start_time', current_time)).seconds > self.session_timeout
        ]
        
        for user_id in expired_dm_sessions:
            del self.dm_edit_sessions[user_id]
        
        # Rate limiter 정리
        if hasattr(self.rate_limiter, 'last_request_time'):
            cutoff = current_time - datetime.timedelta(minutes=10)
            self.rate_limiter.last_request_time = {
                k: v for k, v in self.rate_limiter.last_request_time.items()
                if v > cutoff
            }
    
    def _load_mappings(self):
        """저장된 매핑 정보 로드 (최적화)"""
        if not os.path.exists(self.mapping_file):
            return
            
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                
            # 병렬로 데이터 복원
            for group_id, group_data in loaded_data.items():
                if isinstance(group_data, dict) and 'message_ids' in group_data:
                    anonymous_msg = AnonymousMessage(
                        message_ids=group_data['message_ids'],
                        author_id=group_data.get('author_id', ''),
                        thread_id=group_data.get('thread_id', 0),
                        created_at=group_data.get('created_at', ''),
                        edited=group_data.get('edited', False),
                        edit_history=group_data.get('edit_history', [])
                    )
                    
                    # parts 복원
                    for part_data in group_data.get('parts', []):
                        anonymous_msg.parts.append(MessagePart(
                            type=MessageType(part_data['type']),
                            content=part_data['content'],
                            order=part_data['order'],
                            url=part_data.get('url')
                        ))
                    
                    self.anonymous_messages[int(group_id)] = anonymous_msg
                    
                    # 개별 메시지 매핑
                    for msg_id in anonymous_msg.message_ids:
                        self.message_to_group[msg_id] = int(group_id)
            
            logger.info(f"매핑 정보 로드 완료: {len(self.anonymous_messages)}개 그룹")
            
        except Exception as e:
            logger.error(f"매핑 정보 로드 실패: {e}")
            self.anonymous_messages = {}
            self.message_to_group = {}
    
    def _save_mappings(self):
        """매핑 정보 저장 (최적화)"""
        # 백그라운드로 저장
        asyncio.create_task(self._save_mappings_async())
    
    async def _save_mappings_async(self):
        """비동기 매핑 저장"""
        try:
            save_data = {}
            
            for group_id, anonymous_msg in self.anonymous_messages.items():
                parts_data = [{
                    'type': part.type.value,
                    'content': part.content if part.type == MessageType.TEXT else "",
                    'order': part.order,
                    'url': part.url
                } for part in anonymous_msg.parts]
                
                save_data[str(group_id)] = {
                    'message_ids': anonymous_msg.message_ids,
                    'author_id': anonymous_msg.author_id,
                    'thread_id': anonymous_msg.thread_id,
                    'created_at': anonymous_msg.created_at,
                    'edited': anonymous_msg.edited,
                    'edit_history': anonymous_msg.edit_history,
                    'parts': parts_data
                }
            
            # 비동기 파일 쓰기
            temp_file = f"{self.mapping_file}.tmp"
            await asyncio.get_event_loop().run_in_executor(
                None, self._write_json_file, temp_file, save_data
            )
            
            os.replace(temp_file, self.mapping_file)
            
        except Exception as e:
            logger.error(f"매핑 정보 저장 실패: {e}")
    
    def _write_json_file(self, filepath: str, data: dict):
        """JSON 파일 쓰기 (동기)"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def upload_to_drive_async(self, file_data: bytes, filename: str) -> Optional[str]:
        """최적화된 드라이브 업로드"""
        if not self.drive_service:
            return await self._save_local_fallback(filename, file_data)
        
        # 작은 이미지는 로컬 저장
        if len(file_data) < 100 * 1024:  # 100KB 미만
            return await self._save_local_fallback(filename, file_data)
        
        temp_path = f'temp_{filename}'
        
        try:
            # 비동기 파일 쓰기
            await asyncio.get_event_loop().run_in_executor(
                None, self._write_temp_file, temp_path, file_data
            )
            
            # 드라이브 업로드
            url = await asyncio.get_event_loop().run_in_executor(
                None, self._upload_to_drive_sync, temp_path, filename
            )
            
            return url
            
        except Exception as e:
            logger.error(f"드라이브 업로드 실패: {e}")
            return await self._save_local_fallback(filename, file_data)
        finally:
            # 즉시 정리
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def _write_temp_file(self, path: str, data: bytes):
        """임시 파일 쓰기"""
        with open(path, 'wb') as f:
            f.write(data)
    
    def _upload_to_drive_sync(self, temp_path: str, filename: str) -> Optional[str]:
        """드라이브 업로드 (동기)"""
        file_metadata = {
            'name': filename,
            'parents': [BAMBOO_FOLDER_ID]
        }
        
        media = MediaFileUpload(temp_path, resumable=True)
        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        # 공유 링크 생성
        self.drive_service.permissions().create(
            fileId=file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return f"https://drive.google.com/uc?export=view&id={file.get('id')}"
    
    async def _save_local_fallback(self, filename: str, file_data: bytes) -> str:
        """로컬 저장 폴백"""
        local_dir = "bamboo_images"
        os.makedirs(local_dir, exist_ok=True)
        
        local_path = os.path.join(local_dir, filename)
        await asyncio.get_event_loop().run_in_executor(
            None, self._write_temp_file, local_path, file_data
        )
        return local_path

    async def start_bamboo_session(self, message: discord.Message):
        """익명 게시판 세션 시작 (수정됨)"""
        # 특별 사용자는 어떤 채널에서든 사용 가능
        if str(message.author.id) in SPECIAL_USER_IDS:
            # 특별 사용자는 어디서든 사용 가능
            pass
        else:
            # 일반 사용자는 일지 스레드에서만
            if not message.channel.type == discord.ChannelType.private_thread:
                return False
                
            if message.channel.parent.name != "일지":
                return False
        
        session_key = (message.channel.id, message.author.id)
        current_time = datetime.datetime.now()
        
        self.bamboo_forest_sessions[session_key] = {
            "messages": [],
            "status": "editing",
            "initial_message_id": message.id,
            "attachments": [],
            "last_activity": current_time
        }
        
        await message.channel.send(
            "이 뒤의 메시지를 익명-게시판 채널로 보냅니다. "
            "자유로히 적으신 뒤 '!보내기'를 채팅에 보내시길 바랍니다."
        )
        return True

    async def send_to_bamboo_forest(self, message: discord.Message):
        """익명 게시판으로 메시지 전송 (수정됨)"""
        session_key = (message.channel.id, message.author.id)
        
        # 특별 사용자 체크
        if str(message.author.id) in SPECIAL_USER_IDS:
            # 세션이 없어도 진행 가능하도록 처리
            if session_key not in self.bamboo_forest_sessions:
                # 임시 세션 생성
                self.bamboo_forest_sessions[session_key] = {
                    "messages": [],
                    "status": "editing",
                    "initial_message_id": message.id - 1,  # 이전 메시지 ID 추정
                    "attachments": [],
                    "last_activity": datetime.datetime.now()
                }
        else:
            # 일반 사용자는 세션 필수
            if session_key not in self.bamboo_forest_sessions:
                await message.channel.send("먼저 !대나무숲 명령어를 사용해주세요.")
                return False
        
        session = self.bamboo_forest_sessions[session_key]
        if session["status"] != "editing":
            return False
        
        # 활동 시간 업데이트
        session["last_activity"] = datetime.datetime.now()
        
        # Rate limit 대기
        await self.rate_limiter.wait_if_needed(f"bamboo_send_{message.author.id}")
        
        # 메시지 수집
        message_parts = await self._collect_messages_with_order(
            message, session["initial_message_id"]
        )
        
        if not message_parts:
            await message.channel.send("전송할 메시지가 없습니다.")
            return False
        
        # 익명 게시판 채널 찾기
        bamboo_forest_channel = await self._find_bamboo_forest_channel()
        if not bamboo_forest_channel:
            await message.channel.send("익명-게시판 채널을 찾을 수 없습니다.")
            return False
        
        # 메시지 전송
        sent_message_ids = await self._send_messages_in_order(
            bamboo_forest_channel, message_parts
        )
        
        # 익명 메시지 그룹 생성
        group_id = int(datetime.datetime.now().timestamp() * 1000)
        anonymous_msg = AnonymousMessage(
            message_ids=sent_message_ids,
            parts=message_parts,
            author_id=str(message.author.id),
            thread_id=message.channel.id,
            created_at=datetime.datetime.now().isoformat()
        )
        
        self.anonymous_messages[group_id] = anonymous_msg
        
        # 개별 메시지 매핑
        for msg_id in sent_message_ids:
            self.message_to_group[msg_id] = group_id
        
        self._save_mappings()
        
        # 세션 정리
        del self.bamboo_forest_sessions[session_key]
        await message.channel.send("메시지가 익명-게시판에 전송되었습니다.")
        return True

    async def _collect_messages_with_order(self, end_message: discord.Message, 
                                         start_message_id: int) -> List[MessagePart]:
        """최적화된 메시지 수집"""
        message_parts = []
        order = 0
        
        try:
            # 메시지 수집 (제한 설정)
            messages = []
            async for msg in end_message.channel.history(
                limit=30,  # 제한 축소
                after=discord.Object(id=start_message_id),
                before=end_message,
                oldest_first=True
            ):
                if msg.author.id == end_message.author.id and not msg.content.startswith("!"):
                    messages.append(msg)
                    if len(messages) >= 20:  # 최대 20개 메시지
                        break
            
            # 메시지 처리
            for msg in messages:
                if msg.content:
                    message_parts.append(MessagePart(
                        type=MessageType.TEXT,
                        content=msg.content[:2000],  # Discord 제한
                        order=order
                    ))
                    order += 1
                
                # 첨부 파일 처리 (최대 5개)
                for i, attachment in enumerate(msg.attachments[:5]):
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        message_parts.append(MessagePart(
                            type=MessageType.IMAGE,
                            content=attachment,
                            order=order
                        ))
                        order += 1
                        
        except discord.HTTPException as e:
            logger.error(f"메시지 수집 실패: {e}")
        
        return message_parts

    async def _find_bamboo_forest_channel(self) -> Optional[discord.TextChannel]:
        """캐시된 채널 찾기"""
        # 캐시 확인 (5분간 유효)
        if (self._cached_bamboo_channel and self._channel_cache_time and 
            (datetime.datetime.now() - self._channel_cache_time).seconds < 300):
            return self._cached_bamboo_channel
        
        bot_instance = self.bot()
        if not bot_instance:
            return None
            
        for guild in bot_instance.guilds:
            for channel in guild.text_channels:
                if channel.name == "익명-게시판":
                    self._cached_bamboo_channel = channel
                    self._channel_cache_time = datetime.datetime.now()
                    return channel
        return None

    async def _send_messages_in_order(self, channel: discord.TextChannel, 
                                    message_parts: List[MessagePart]) -> List[int]:
        """최적화된 메시지 전송"""
        sent_message_ids = []
        
        # 이미지 업로드 병렬 처리 (최대 3개씩)
        image_parts = [p for p in message_parts if p.type == MessageType.IMAGE]
        for i in range(0, len(image_parts), 3):
            batch = image_parts[i:i+3]
            await asyncio.gather(*[self._prepare_image(part) for part in batch])
        
        # 순서대로 메시지 전송
        for part in message_parts:
            try:
                await self.rate_limiter.wait_if_needed(f"send_{channel.id}")
                
                if part.type == MessageType.TEXT:
                    msg = await channel.send(part.content[:2000])
                    sent_message_ids.append(msg.id)
                    
                elif part.type == MessageType.IMAGE and part.url:
                    embed = discord.Embed(color=0x000000)
                    embed.set_image(url=part.url)
                    msg = await channel.send(embed=embed)
                    sent_message_ids.append(msg.id)
                            
            except discord.HTTPException as e:
                logger.error(f"메시지 전송 실패: {e}")
                if e.status == 429:
                    await asyncio.sleep(e.retry_after)
        
        return sent_message_ids

    async def _prepare_image(self, part: MessagePart):
        """최적화된 이미지 준비"""
        if part.type != MessageType.IMAGE:
            return
            
        attachment = part.content
        try:
            session = await self._get_http_session()
            
            # 크기 제한 확인
            if attachment.size > 8 * 1024 * 1024:  # 8MB 제한
                logger.warning(f"이미지 크기 초과: {attachment.filename}")
                return
            
            async with session.get(attachment.url) as response:
                if response.status == 200:
                    file_data = await response.read()
                    filename = f"anon_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{attachment.filename}"
                    
                    url = await self.upload_to_drive_async(file_data, filename)
                    if url:
                        part.url = url
                        
        except asyncio.TimeoutError:
            logger.error("이미지 다운로드 타임아웃")
        except Exception as e:
            logger.error(f"이미지 준비 실패: {e}")

    async def handle_edit_reaction(self, payload, user: discord.User):
        """편집 리액션 처리 (최적화)"""
        group_id = self.message_to_group.get(payload.message_id)
        if not group_id or group_id not in self.anonymous_messages:
            return False
        
        if group_id in self.processing_messages:
            return False
        
        self.processing_messages.add(group_id)
        
        try:
            anonymous_msg = self.anonymous_messages[group_id]
            
            # 내용 구성 (간소화)
            current_content_parts = []
            for idx, part in enumerate(anonymous_msg.parts[:10], 1):  # 최대 10개
                if part.type == MessageType.TEXT:
                    preview = part.content[:30] + "..." if len(part.content) > 30 else part.content
                    current_content_parts.append(f"**{idx}** [텍스트]: {preview}")
                else:
                    current_content_parts.append(f"**{idx}** [이미지]")
            
            embed = discord.Embed(
                title="익명 메시지 수정",
                description="수정할 번호와 내용을 입력하세요.\n형식: `번호-내용`",
                color=discord.Color.gold()
            )
            
            embed.add_field(
                name="현재 메시지", 
                value="\n".join(current_content_parts[:5]) or "없음",  # 최대 5개 표시
                inline=False
            )
            
            try:
                dm_channel = await user.create_dm()
                initial_msg = await dm_channel.send(embed=embed)
                
                self.dm_edit_sessions[str(user.id)] = {
                    "group_id": group_id,
                    "start_time": datetime.datetime.utcnow(),
                    "channel_id": payload.channel_id,
                    "initial_message_id": initial_msg.id
                }
                return True
                
            except discord.Forbidden:
                logger.error(f"DM 전송 실패: {user.id}")
                return False
                
        finally:
            self.processing_messages.discard(group_id)

    async def handle_restore_reaction(self, payload):
        """복원 리액션 처리 (최적화)"""
        group_id = self.message_to_group.get(payload.message_id)
        if not group_id or group_id not in self.anonymous_messages:
            return False
        
        anonymous_msg = self.anonymous_messages[group_id]
        
        if not anonymous_msg.edited or not anonymous_msg.edit_history:
            return False
        
        bot_instance = self.bot()
        if not bot_instance:
            return False
            
        channel = bot_instance.get_channel(payload.channel_id)
        if not channel:
            return False
        
        try:
            # 원본 내용 찾기
            if anonymous_msg.edit_history and 'parts' in anonymous_msg.edit_history[0]:
                original_parts = anonymous_msg.edit_history[0]['parts']
            else:
                return False
            
            # 배치로 메시지 가져오기
            messages = []
            for msg_id in anonymous_msg.message_ids[:len(original_parts)]:
                try:
                    msg = await channel.fetch_message(msg_id)
                    messages.append(msg)
                except:
                    messages.append(None)
            
            # 복원 작업
            for idx, (part, msg) in enumerate(zip(original_parts, messages)):
                if not msg:
                    continue
                    
                try:
                    if part.type == MessageType.TEXT:
                        await msg.edit(content=part.content[:2000])
                        if idx < len(anonymous_msg.parts):
                            anonymous_msg.parts[idx].content = part.content
                            
                    elif part.type == MessageType.IMAGE:
                        embed = discord.Embed(color=0x000000)
                        embed.set_image(url=part.url)
                        await msg.edit(embed=embed)
                        if idx < len(anonymous_msg.parts):
                            anonymous_msg.parts[idx].url = part.url
                    
                    await asyncio.sleep(0.3)  # Rate limit
                    
                except discord.HTTPException:
                    pass
            
            # 상태 업데이트
            anonymous_msg.edited = False
            anonymous_msg.edit_history.append({
                "restored_at": datetime.datetime.now().isoformat(),
                "action": "restore"
            })
            
            self._save_mappings()
            return True
            
        except Exception as e:
            logger.error(f"메시지 복원 실패: {e}")
            return False

    async def handle_author_check_reaction(self, payload, user: discord.User):
        """작성자 확인 리액션 처리 (최적화)"""
        group_id = self.message_to_group.get(payload.message_id)
        if not group_id or group_id not in self.anonymous_messages:
            return False
        
        anonymous_msg = self.anonymous_messages[group_id]
        author_id = anonymous_msg.author_id
        
        if not author_id:
            return False
        
        bot_instance = self.bot()
        if not bot_instance:
            return False
        
        try:
            # 작성자 찾기 (캐시 활용)
            author_found = False
            author_info = None
            
            for guild in bot_instance.guilds:
                member = guild.get_member(int(author_id))
                if member:
                    author_info = f"**{member.display_name}** ({member.name}#{member.discriminator})"
                    author_found = True
                    break
            
            if not author_found:
                author_info = f"ID: {author_id} (서버에서 찾을 수 없음)"
            
            try:
                await user.send(f"익명 메시지 작성자: {author_info}")
            except discord.Forbidden:
                return False
            
            return True
                    
        except Exception as e:
            logger.error(f"작성자 확인 실패: {e}")
        
        return False

    async def handle_dm_edit_completion(self, message: discord.Message):
        """DM 수정 완료 처리 (최적화)"""
        user_id = str(message.author.id)
        
        if user_id not in self.dm_edit_sessions:
            return False
        
        session = self.dm_edit_sessions[user_id]
        group_id = session["group_id"]
        
        if group_id not in self.anonymous_messages:
            await message.channel.send("메시지를 찾을 수 없습니다.")
            del self.dm_edit_sessions[user_id]
            return False
        
        try:
            # 수정 내용 수집
            edits = {}
            start_time = session["start_time"]
            initial_msg_id = session.get("initial_message_id")
            
            # 메시지 수집 (제한)
            messages = []
            async for msg in message.channel.history(after=start_time, limit=20):
                if msg.id != initial_msg_id and msg.author == message.author and msg.content != "!수정 끝":
                    messages.append(msg)
            
            # 수정 파싱
            for msg in messages:
                if '-' in msg.content:
                    parts = msg.content.split('-', 1)
                    if len(parts) == 2 and parts[0].strip().isdigit():
                        num = int(parts[0].strip())
                        content = parts[1].strip()[:2000]  # 길이 제한
                        
                        # 이미지 처리
                        if msg.attachments and msg.attachments[0].content_type.startswith('image/'):
                            attachment = msg.attachments[0]
                            session = await self._get_http_session()
                            
                            try:
                                async with session.get(attachment.url) as response:
                                    if response.status == 200:
                                        file_data = await response.read()
                                        filename = f"edit_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{attachment.filename}"
                                        url = await self.upload_to_drive_async(file_data, filename)
                                        if url:
                                            edits[num] = {'type': 'image', 'url': url}
                            except:
                                pass
                        else:
                            edits[num] = {'type': 'text', 'content': content}
            
            if not edits:
                await message.channel.send("수정할 내용이 없습니다.")
                del self.dm_edit_sessions[user_id]
                return False
            
            # 채널 찾기
            bamboo_channel = await self._find_bamboo_forest_channel()
            if not bamboo_channel:
                await message.channel.send("익명-게시판 채널을 찾을 수 없습니다.")
                del self.dm_edit_sessions[user_id]
                return False
            
            # 메시지 수정
            anonymous_msg = self.anonymous_messages[group_id]
            
            # 수정 기록
            anonymous_msg.edit_history.append({
                "edited_at": datetime.datetime.now().isoformat(),
                "edits": edits,
                "editor_id": user_id
            })
            
            # 수정 적용
            for num, edit_info in edits.items():
                if 1 <= num <= len(anonymous_msg.parts) and num - 1 < len(anonymous_msg.message_ids):
                    idx = num - 1
                    part = anonymous_msg.parts[idx]
                    msg_id = anonymous_msg.message_ids[idx]
                    
                    try:
                        msg_to_edit = await bamboo_channel.fetch_message(msg_id)
                        
                        if edit_info['type'] == 'text' and part.type == MessageType.TEXT:
                            await msg_to_edit.edit(content=edit_info['content'])
                            part.content = edit_info['content']
                            
                        elif edit_info['type'] == 'image' and part.type == MessageType.IMAGE:
                            embed = discord.Embed(color=0x000000)
                            embed.set_image(url=edit_info['url'])
                            await msg_to_edit.edit(embed=embed)
                            part.url = edit_info['url']
                        
                        await asyncio.sleep(0.3)
                        
                    except discord.HTTPException:
                        pass
            
            anonymous_msg.edited = True
            self._save_mappings()
            
            await message.channel.send(f"수정 완료: {', '.join(map(str, edits.keys()))}번")
            del self.dm_edit_sessions[user_id]
            return True
            
        except Exception as e:
            logger.error(f"DM 수정 처리 실패: {e}")
            await message.channel.send("수정 중 오류가 발생했습니다.")
            
        if user_id in self.dm_edit_sessions:
            del self.dm_edit_sessions[user_id]
        return False
    
    def shutdown(self):
        """시스템 종료"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
        
        if self.http_session and not self.http_session.closed:
            asyncio.create_task(self.http_session.close())

# 전역 변수
bamboo_forest_system = None

def get_bamboo_system():
    """익명 게시판 시스템 인스턴스 반환"""
    return bamboo_forest_system

def init_bamboo_system(bot):
    """익명 게시판 시스템 초기화"""
    global bamboo_forest_system
    bamboo_forest_system = BambooForestSystem(bot)
    return bamboo_forest_system

async def handle_message(message: discord.Message):
    """메시지 이벤트 처리"""
    if message.author.bot:
        return False
    
    system = get_bamboo_system()
    if not system:
        return False
        
    # DM 수정 처리
    if isinstance(message.channel, discord.DMChannel):
        if message.content == "!수정 끝":
            return await system.handle_dm_edit_completion(message)
        return False
    
    # 익명 게시판 명령어 처리
    if message.content == "!대나무숲" or message.content.startswith("!대나무숲 "):
        return await system.start_bamboo_session(message)
    elif message.content == "!보내기":
        return await system.send_to_bamboo_forest(message)
    
    return False

async def handle_reaction(payload):
    """리액션 이벤트 처리"""
    if payload.user_id == payload.member.bot if payload.member else False:
        return False
    
    # 특별 권한 확인
    if str(payload.user_id) not in SPECIAL_USER_IDS:
        return False
    
    system = get_bamboo_system()
    if not system:
        return False
    
    try:
        await system.rate_limiter.wait_if_needed(f"reaction_{payload.user_id}")
        
        bot = system.bot()
        if not bot:
            return False
            
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            return False
        
        try:
            message = await channel.fetch_message(payload.message_id)
            user = await bot.fetch_user(payload.user_id)
        except discord.HTTPException:
            return False
        
        emoji = str(payload.emoji)
        
        # 익명-게시판 채널에서 특정 이모지만 제거
        if channel.name == "익명-게시판" and emoji in ["✏️", "🔄", "❓"]:
            try:
                await message.remove_reaction(emoji, user)
            except discord.HTTPException:
                pass
        
        if emoji == "✏️":
            return await system.handle_edit_reaction(payload, user)
        elif emoji == "🔄":
            return await system.handle_restore_reaction(payload)
        elif emoji == "❓":
            return await system.handle_author_check_reaction(payload, user)
            
    except Exception as e:
        logger.error(f"리액션 처리 중 오류: {e}")
    
    return False