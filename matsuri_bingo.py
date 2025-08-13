# matsuri_bingo.py - 캐릭터 이름과 빙고 카운트까지 사전 생성하는 버전
import discord
from discord import app_commands
import asyncio
import random
import logging
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from debug_config import debug_log, performance_tracker, debug_config
import time
from PIL import Image, ImageDraw, ImageFont
import io
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import tempfile
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

# Google Drive API 설정
SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = 'service_account.json'

# 토큰 저장 디렉토리
TOKEN_CACHE_DIR = "bingo_tokens"
TOKEN_VERSION = "v2.0"  # 버전 업데이트 (이름과 빙고 카운트 추가)

# 플레이어 이름 목록 (한글 이름 인식용)
PLAYER_NAMES = [
    "아카시 하지메", "펀처", "유진석", "휘슬", "배달기사", "페이",
    "로메즈 아가레스", "레이나 하트베인", "비비", "오카미 나오하",
    "카라트에크", "토트", "처용", "멀 플리시", "코발트윈드", "옥타",
    "베레니케", "안드라 블랙", "봉고 3호", "몰", "베니", "백야",
    "루치페르", "벨사이르 드라켄리트", "불스", "퓨어 메탈", "노 단투",
    "라록", "아카이브", "베터", "메르쿠리", "마크-112", "스푸트니크 2세",
    "이터니티", "커피머신"
]

# 전역 이미지 생성기 인스턴스
global_image_generator = None

def get_player_name_from_nickname(nickname: str) -> str:
    """닉네임에서 플레이어 이름 추출"""
    for name in PLAYER_NAMES:
        if name in nickname:
            debug_log("BINGO", f"Found player name '{name}' in nickname '{nickname}'")
            return name
    return nickname

class BingoType(Enum):
    """빙고 타입"""
    CUSTOM = "사용자 정의"

@dataclass
class BingoCard:
    """빙고 카드"""
    player_id: int
    player_name: str
    display_name: str
    grid: List[List[str]]
    marked: List[List[bool]]
    bingo_count: int = 0
    completed_lines: Set[str] = field(default_factory=set)
    turn_order: int = 0
    image_url: Optional[str] = None
    dm_message_id: Optional[int] = None

class GoogleDriveUploader:
    """구글 드라이브 업로더"""
    def __init__(self):
        self.service = None
        self.folder_id = None
        self._initialize_service()
    
    def _initialize_service(self):
        """구글 드라이브 서비스 초기화"""
        try:
            creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            self.service = build('drive', 'v3', credentials=creds)
            
            self.folder_id = self._get_or_create_folder("MatsuriBot_Bingo_Images")
            debug_log("BINGO", f"Google Drive folder initialized: {self.folder_id}")
        except Exception as e:
            logger.error(f"Google Drive 초기화 실패: {e}")
    
    def _get_or_create_folder(self, folder_name: str) -> str:
        """폴더 ID 가져오기 또는 생성"""
        try:
            response = self.service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            files = response.get('files', [])
            if files:
                return files[0]['id']
            
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            self.service.permissions().create(
                fileId=folder['id'],
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
            
            return folder['id']
        except Exception as e:
            logger.error(f"폴더 생성/검색 실패: {e}")
            return None
    
    def upload_image(self, image_data: bytes, filename: str) -> Optional[str]:
        """이미지 업로드 및 공유 링크 반환"""
        try:
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id] if self.folder_id else []
            }
            
            media = MediaIoBaseUpload(
                io.BytesIO(image_data),
                mimetype='image/png',
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webContentLink'
            ).execute()
            
            self.service.permissions().create(
                fileId=file['id'],
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
            
            direct_link = f"https://drive.google.com/uc?export=view&id={file['id']}"
            debug_log("BINGO", f"Image uploaded: {direct_link}")
            return direct_link
            
        except Exception as e:
            logger.error(f"이미지 업로드 실패: {e}")
            return None

class BingoImageGenerator:
    """빙고 이미지 생성기 - 모든 요소 사전 생성"""
    def __init__(self):
        self.cell_size = 120
        self.margin = 30
        self.board_size = 5
        self.font_size = 36
        self.free_font_size = 28
        self.title_font_size = 40  # 제목 폰트 크기
        
        self.board_width = self.cell_size * self.board_size + self.margin * 2
        self.board_height = self.board_width + 40
        
        self.background_image_path = "bingo_background.png"
        
        # 토큰 디렉토리 경로
        self.token_dir = os.path.join(TOKEN_CACHE_DIR, TOKEN_VERSION)
        self.circle_token_dir = os.path.join(self.token_dir, "circles")
        self.number_token_dir = os.path.join(self.token_dir, "numbers")
        self.name_token_dir = os.path.join(self.token_dir, "names")
        self.bingo_count_dir = os.path.join(self.token_dir, "bingo_counts")
        self.base_board_dir = os.path.join(self.token_dir, "base_boards")
        
        self.font = None
        self.free_font = None
        self.title_font = None
        self._setup_fonts()
        
        self.is_initialized = False
    
    def _setup_fonts(self):
        """폰트 설정"""
        try:
            font_paths = [
            "/home/wonsukhuh56/Katuri.ttf"
            ]
            
            font_loaded = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    self.font = ImageFont.truetype(font_path, self.font_size)
                    self.free_font = ImageFont.truetype(font_path, self.free_font_size)
                    self.title_font = ImageFont.truetype(font_path, self.title_font_size)
                    font_loaded = True
                    debug_log("BINGO", f"Font loaded from: {font_path}")
                    break
            
            if not font_loaded:
                self.font = ImageFont.truetype("arial.ttf", self.font_size)
                self.free_font = ImageFont.truetype("arial.ttf", self.free_font_size)
                self.title_font = ImageFont.truetype("arial.ttf", self.title_font_size)
        except:
            self.font = ImageFont.load_default()
            self.free_font = ImageFont.load_default()
            self.title_font = ImageFont.load_default()
            logger.warning("한글 폰트를 찾을 수 없어 기본 폰트를 사용합니다.")
    
    def _ensure_directories(self):
        """토큰 디렉토리 생성"""
        os.makedirs(self.circle_token_dir, exist_ok=True)
        os.makedirs(self.number_token_dir, exist_ok=True)
        os.makedirs(self.name_token_dir, exist_ok=True)
        os.makedirs(self.bingo_count_dir, exist_ok=True)
        os.makedirs(self.base_board_dir, exist_ok=True)
        debug_log("BINGO", f"Token directories created: {self.token_dir}")
    
    def _get_token_filename(self, token_type: str, key: str) -> str:
        """토큰 파일명 생성"""
        # 파일명에 사용할 수 없는 문자 처리
        safe_key = key.replace(":", "_").replace(" ", "_").replace("/", "_")
        return f"{token_type}_{safe_key}.png"
    
    def _token_exists(self, token_type: str, key: str) -> bool:
        """토큰 파일 존재 여부 확인"""
        if token_type == "circle":
            filepath = os.path.join(self.circle_token_dir, self._get_token_filename("circle", key))
        elif token_type == "number":
            filepath = os.path.join(self.number_token_dir, self._get_token_filename("number", key))
        elif token_type == "name":
            filepath = os.path.join(self.name_token_dir, self._get_token_filename("name", key))
        elif token_type == "bingo_count":
            filepath = os.path.join(self.bingo_count_dir, self._get_token_filename("bingo_count", key))
        else:
            return False
        return os.path.exists(filepath)
    
    async def initialize_tokens(self):
        """토큰 이미지 초기화 (로컬 파일로 저장)"""
        if self.is_initialized:
            return
        
        debug_log("BINGO", "Initializing image tokens...")
        start_time = time.time()
        
        # 디렉토리 생성
        self._ensure_directories()
        
        # 토큰이 이미 존재하는지 확인
        tokens_exist = self._check_existing_tokens()
        
        if tokens_exist:
            debug_log("BINGO", "Using existing token files")
        else:
            debug_log("BINGO", "Generating new token files...")
            await asyncio.get_event_loop().run_in_executor(
                None, self._generate_and_save_all_tokens
            )
        
        # 기본 빙고판 생성
        await asyncio.get_event_loop().run_in_executor(
            None, self._generate_base_boards
        )
        
        self.is_initialized = True
        elapsed = time.time() - start_time
        debug_log("BINGO", f"Token initialization completed in {elapsed:.2f} seconds")
    
    def _check_existing_tokens(self) -> bool:
        """기존 토큰 파일들이 모두 존재하는지 확인"""
        # 필요한 토큰 목록
        required_circles = ["normal", "marked", "bingo"]
        required_numbers = []
        
        # 1~100 숫자
        for num in range(1, 101):
            for color in ["black", "white"]:
                required_numbers.append(f"{num}_{color}")
        
        # FREE 텍스트
        for color in ["black", "white"]:
            required_numbers.append(f"FREE_{color}")
        
        # 캐릭터 이름
        for name in PLAYER_NAMES:
            if not self._token_exists("name", name):
                return False
        
        # 빙고 카운트
        for count in range(13):  # 0~12 빙고
            if not self._token_exists("bingo_count", str(count)):
                return False
        
        # 모든 파일 확인
        for circle_type in required_circles:
            if not self._token_exists("circle", circle_type):
                return False
        
        for number_key in required_numbers:
            if not self._token_exists("number", number_key):
                return False
        
        return True
    
    def _generate_and_save_all_tokens(self):
        """모든 토큰 생성 및 저장"""
        # 원 토큰 생성
        if debug_config.debug_enabled:
            debug_log("BINGO", "Generating circle tokens...")
        
        circle_states = [
            ("normal", "white", "black", 2),
            ("marked", "#90EE90", "black", 3),
            ("bingo", "#4169E1", "#FF0000", 4)
        ]
        
        for state_name, fill_color, outline_color, outline_width in circle_states:
            img = Image.new('RGBA', (self.cell_size, self.cell_size), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)
            
            circle_bbox = [5, 5, self.cell_size - 5, self.cell_size - 5]
            draw.ellipse(circle_bbox, fill=fill_color, outline=outline_color, width=outline_width)
            
            filepath = os.path.join(self.circle_token_dir, self._get_token_filename("circle", state_name))
            img.save(filepath, "PNG")
        
        # 숫자 토큰 생성
        if debug_config.debug_enabled:
            debug_log("BINGO", "Generating number tokens...")
        
        token_count = 0
        
        # 1~100 숫자
        for num in range(1, 101):
            for text_color in ["black", "white"]:
                key = f"{num}_{text_color}"
                img = self._create_text_token(str(num), text_color, self.font)
                
                filepath = os.path.join(self.number_token_dir, self._get_token_filename("number", key))
                img.save(filepath, "PNG")
                token_count += 1
                
                if debug_config.debug_enabled and token_count % 50 == 0:
                    debug_log("BINGO", f"Generated {token_count} number tokens...")
        
        # FREE 토큰
        for text_color in ["black", "white"]:
            key = f"FREE_{text_color}"
            img = self._create_text_token("FREE", text_color, self.free_font)
            
            filepath = os.path.join(self.number_token_dir, self._get_token_filename("number", key))
            img.save(filepath, "PNG")
        
        # 캐릭터 이름 토큰 생성
        if debug_config.debug_enabled:
            debug_log("BINGO", "Generating player name tokens...")
        
        for name in PLAYER_NAMES:
            # 이름 이미지 생성 (검은색)
            img = self._create_text_token(name, "black", self.title_font)
            filepath = os.path.join(self.name_token_dir, self._get_token_filename("name", name))
            img.save(filepath, "PNG")
            
            if debug_config.debug_enabled:
                debug_log("BINGO", f"Generated name token: {name}")
        
        # 빙고 카운트 토큰 생성 (0 BINGO ~ 12 BINGO)
        if debug_config.debug_enabled:
            debug_log("BINGO", "Generating bingo count tokens...")
        
        for count in range(13):  # 0~12
            text = f"{count} BINGO"
            # 빙고 카운트별 색상 설정
            if count == 0:
                color = "#666666"  # 회색
            elif count <= 3:
                color = "#4169E1"  # 파란색
            elif count <= 6:
                color = "#228B22"  # 녹색
            elif count <= 9:
                color = "#FF8C00"  # 주황색
            else:
                color = "#FF0000"  # 빨간색
            
            img = self._create_text_token(text, color, self.title_font)
            filepath = os.path.join(self.bingo_count_dir, self._get_token_filename("bingo_count", str(count)))
            img.save(filepath, "PNG")
        
        debug_log("BINGO", f"Generated and saved all tokens to {self.token_dir}")
    
    def _generate_base_boards(self):
        """기본 빙고판 배경 생성"""
        if debug_config.debug_enabled:
            debug_log("BINGO", "Generating base board background...")
        
        # 배경 이미지 로드 또는 생성
        try:
            if os.path.exists(self.background_image_path):
                base_img = Image.open(self.background_image_path).convert('RGBA')
                base_img = base_img.resize((self.board_width, self.board_height), Image.Resampling.LANCZOS)
            else:
                base_img = Image.new('RGBA', (self.board_width, self.board_height), 'white')
        except:
            base_img = Image.new('RGBA', (self.board_width, self.board_height), 'white')
        
        # 그리드 라인 그리기 (선택적)
        draw = ImageDraw.Draw(base_img)
        
        # 빙고판 그리드 라인
        for i in range(self.board_size + 1):
            # 세로선
            x = self.margin + i * self.cell_size
            y_start = self.margin + 40
            y_end = self.margin + 40 + self.board_size * self.cell_size
            draw.line([(x, y_start), (x, y_end)], fill="#CCCCCC", width=1)
            
            # 가로선
            y = self.margin + 40 + i * self.cell_size
            x_start = self.margin
            x_end = self.margin + self.board_size * self.cell_size
            draw.line([(x_start, y), (x_end, y)], fill="#CCCCCC", width=1)
        
        # 기본 배경 저장
        filepath = os.path.join(self.base_board_dir, "base_board.png")
        base_img.save(filepath, "PNG")
        
        if debug_config.debug_enabled:
            debug_log("BINGO", "Base board background generated")
    
    def _create_text_token(self, text: str, color: str, font) -> Image:
        """텍스트만 있는 투명 이미지 생성"""
        dummy_img = Image.new('RGBA', (1, 1), (255, 255, 255, 0))
        dummy_draw = ImageDraw.Draw(dummy_img)
        
        bbox = dummy_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 여백 추가
        padding = 10
        img = Image.new('RGBA', (text_width + padding * 2, text_height + padding * 2), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        
        draw.text((padding, padding), text, fill=color, font=font, anchor='lt')
        
        return img
    
    def _load_token(self, token_type: str, key: str) -> Optional[Image.Image]:
        """토큰 파일 로드"""
        try:
            if token_type == "circle":
                filepath = os.path.join(self.circle_token_dir, self._get_token_filename("circle", key))
            elif token_type == "number":
                filepath = os.path.join(self.number_token_dir, self._get_token_filename("number", key))
            elif token_type == "name":
                filepath = os.path.join(self.name_token_dir, self._get_token_filename("name", key))
            elif token_type == "bingo_count":
                filepath = os.path.join(self.bingo_count_dir, self._get_token_filename("bingo_count", key))
            elif token_type == "base_board":
                filepath = os.path.join(self.base_board_dir, key)
            else:
                return None
            
            if os.path.exists(filepath):
                return Image.open(filepath).convert('RGBA')
            else:
                logger.error(f"Token file not found: {filepath}")
                return None
        except Exception as e:
            logger.error(f"Failed to load token {key}: {e}")
            return None
    
    @performance_tracker
    def generate_bingo_image(self, bingo_card: 'BingoCard') -> bytes:
        """빙고판 이미지 생성 (파일 토큰 사용)"""
        if not self.is_initialized:
            raise RuntimeError("Image generator not initialized. Call initialize_tokens() first.")
        
        if debug_config.debug_enabled:
            debug_log("BINGO", f"Generating bingo image for {bingo_card.display_name}")
            start_time = time.time()
        
        # 기본 배경 로드
        base_board = self._load_token("base_board", "base_board.png")
        if base_board:
            img = base_board.copy()
        else:
            img = Image.new('RGBA', (self.board_width, self.board_height), 'white')
        
        # 제목 부분 (이름 + 빙고 카운트)
        # 이름 토큰 로드
        name_token = self._load_token("name", bingo_card.display_name)
        if name_token:
            # 이름 위치 (왼쪽 정렬)
            name_x = self.margin
            name_y = 5
            img.paste(name_token, (name_x, name_y), name_token)
            
            if debug_config.debug_enabled:
                debug_log("BINGO", f"Pasted name token at ({name_x}, {name_y})")
        
        # 빙고 카운트 토큰 로드
        bingo_count_token = self._load_token("bingo_count", str(bingo_card.bingo_count))
        if bingo_count_token:
            # 빙고 카운트 위치 (오른쪽 정렬)
            count_x = self.board_width - bingo_count_token.width - self.margin
            count_y = 5
            img.paste(bingo_count_token, (count_x, count_y), bingo_count_token)
            
            if debug_config.debug_enabled:
                debug_log("BINGO", f"Pasted bingo count token at ({count_x}, {count_y})")
        
        # 빙고판 그리기 (파일 토큰 조합)
        cells_processed = 0
        for row in range(self.board_size):
            for col in range(self.board_size):
                x = self.margin + col * self.cell_size
                y = self.margin + row * self.cell_size + 40
                
                cell_value = bingo_card.grid[row][col]
                is_marked = bingo_card.marked[row][col]
                is_bingo = self._is_part_of_bingo(bingo_card, row, col)
                
                # 상태 결정
                if is_bingo:
                    state = "bingo"
                    text_color = "white"
                elif is_marked:
                    state = "marked"
                    text_color = "black"
                else:
                    state = "normal"
                    text_color = "black"
                
                # 원 토큰 로드 및 붙이기
                circle_token = self._load_token("circle", state)
                if circle_token:
                    img.paste(circle_token, (x, y), circle_token)
                
                # 숫자/텍스트 토큰 로드
                if cell_value == "FREE":
                    text_key = f"FREE_{text_color}"
                else:
                    text_key = f"{cell_value}_{text_color}"
                
                text_token = self._load_token("number", text_key)
                if text_token:
                    text_x = x + (self.cell_size - text_token.width) // 2
                    text_y = y + (self.cell_size - text_token.height) // 2
                    img.paste(text_token, (text_x, text_y), text_token)
                
                cells_processed += 1
                
                if debug_config.debug_enabled and cells_processed % 5 == 0:
                    debug_log("BINGO", f"Processed {cells_processed}/25 cells")
        
        # RGB로 변환하여 저장
        img = img.convert('RGB')
        
        # 이미지를 바이트로 변환
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG', optimize=True, quality=85)
        img_byte_arr.seek(0)
        
        if debug_config.debug_enabled:
            elapsed = time.time() - start_time
            debug_log("BINGO", f"Image generation completed in {elapsed:.3f} seconds")
        
        return img_byte_arr.getvalue()
    
    def _is_part_of_bingo(self, bingo_card: 'BingoCard', row: int, col: int) -> bool:
        """해당 셀이 빙고 라인의 일부인지 확인"""
        if f"row_{row}" in bingo_card.completed_lines:
            return True
        if f"col_{col}" in bingo_card.completed_lines:
            return True
        if row == col and "diag_1" in bingo_card.completed_lines:
            return True
        if row + col == 4 and "diag_2" in bingo_card.completed_lines:
            return True
        return False
    
    def cleanup_old_tokens(self):
        """오래된 토큰 버전 정리"""
        try:
            if os.path.exists(TOKEN_CACHE_DIR):
                for version_dir in os.listdir(TOKEN_CACHE_DIR):
                    if version_dir != TOKEN_VERSION:
                        old_path = os.path.join(TOKEN_CACHE_DIR, version_dir)
                        import shutil
                        shutil.rmtree(old_path)
                        debug_log("BINGO", f"Removed old token version: {version_dir}")
        except Exception as e:
            logger.error(f"Failed to cleanup old tokens: {e}")

# 봇 시작 시 초기화할 함수
async def initialize_bingo_system():
    """빙고 시스템 초기화"""
    global global_image_generator
    global_image_generator = BingoImageGenerator()
    
    # 오래된 토큰 정리
    global_image_generator.cleanup_old_tokens()
    
    # 토큰 초기화
    await global_image_generator.initialize_tokens()
    
    debug_log("BINGO", "Bingo system initialized with all pre-generated tokens")

class MatsuriRingoGame:
    def __init__(self):
        self.active_games = {}
        self.grid_size = 5
        self.max_players = 20
        self.min_players = 2
        self.drive_uploader = GoogleDriveUploader()
        
        self.available_items = [
            "회복포션", "스태미나드링크", "부적", "폭죽", "축제가면",
            "라무네", "타코야키", "솜사탕", "카키고리", "금붕어",
            "요요", "축제부채", "등롱", "오미쿠지", "연꽃"
        ]
        
        self.daily_free_games = {}
    
    async def check_game_eligibility(self, user_id: str, user_name: str) -> Tuple[bool, str]:
        """게임 참가 자격 확인"""
        today = datetime.now().date()
        
        # 오늘 플레이한 게임 수 확인
        if user_id not in self.daily_free_games:
            self.daily_free_games[user_id] = {}
        
        if today not in self.daily_free_games[user_id]:
            self.daily_free_games[user_id][today] = 0
        
        # 오래된 날짜 데이터 정리
        for date_key in list(self.daily_free_games[user_id].keys()):
            if date_key < today - timedelta(days=7):  # 7일 이상 지난 데이터 삭제
                del self.daily_free_games[user_id][date_key]
        
        games_today = self.daily_free_games[user_id][today]
        
        if games_today < 5:
            # 무료 게임
            return True, "free"
        else:
            # 코인 확인
            from utility import get_user_inventory
            user_data = await get_user_inventory(user_id)
            
            if not user_data:
                return False, "유저 정보를 찾을 수 없습니다."
            
            if user_data.get("coins", 0) < 1:
                return False, f"오늘의 무료 게임을 모두 사용했습니다. (5/5)\n게임을 계속하려면 1코인이 필요합니다."
            
            return True, "paid"
    
    async def consume_game_play(self, user_id: str, play_type: str):
        """게임 플레이 소비"""
        today = datetime.now().date()
        
        # 플레이 카운트 증가
        self.daily_free_games[user_id][today] += 1
        
        # 유료 게임인 경우 코인 차감
        if play_type == "paid":
            from utility import update_player_balance
            await update_player_balance(user_id, -1)
            debug_log("BINGO", f"User {user_id} paid 1 coin for game")
    
    @performance_tracker
    async def create_game(self, interaction: discord.Interaction):
        """빙고 게임 생성"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        debug_log("BINGO", f"Creating bingo game in channel {channel_id}")
        
        # 게임 데이터 초기화
        game_data = {
            "host": interaction.user,
            "players": {},  # player_id: BingoCard
            "called_numbers": set(),  # 호출된 숫자들
            "phase": "waiting",  # waiting, playing, ended
            "current_turn": 0,  # 현재 턴
            "turn_order": [],  # 플레이어 턴 순서
            "winners": [],  # 승자 순서
            "start_time": None,
            "message": None,
            "player_payments": {}  # {player_id: "free" or "paid"} 각 플레이어의 결제 상태
        }
        
        self.active_games[channel_id] = game_data
        
        # 참가 대기 화면
        embed = discord.Embed(
            title="🎊 마츠리 빙고 - 사용자 정의",
            description=f"{interaction.user.display_name}님이 빙고 게임을 만들었습니다!\n"
                       f"참가하려면 아래 버튼을 누르세요.\n\n"
                       f"최소 인원: {self.min_players}명\n"
                       f"최대 인원: {self.max_players}명",
            color=discord.Color.purple()
        )
        
        view = BingoLobbyView(self, channel_id)
        await interaction.response.send_message(embed=embed, view=view)
        game_data["message"] = await interaction.original_response()
    
    async def add_player_with_modal(self, interaction: discord.Interaction, channel_id: int):
        """모달을 통해 플레이어 추가"""
        # 게임 참가 자격 확인
        user_id = str(interaction.user.id)
        eligible, status = await self.check_game_eligibility(user_id, interaction.user.display_name)
        
        if not eligible:
            await interaction.response.send_message(status, ephemeral=True)
            return
        
        game_data = self.active_games.get(channel_id)
        if not game_data or game_data["phase"] != "waiting":
            await interaction.response.send_message(
                "게임에 참가할 수 없습니다.",
                ephemeral=True
            )
            return
        
        if interaction.user.id in game_data["players"]:
            await interaction.response.send_message(
                "이미 참가하셨습니다!",
                ephemeral=True
            )
            return
        
        if len(game_data["players"]) >= self.max_players:
            await interaction.response.send_message(
                "인원이 가득 찼습니다!",
                ephemeral=True
            )
            return
        
        # 결제 상태 저장 (실제 차감은 카드 생성 성공 후)
        game_data["player_payments"][user_id] = status
        
        # 빙고 카드 입력 모달 표시
        modal = BingoCardInputModal(self, channel_id, interaction.user)
        await interaction.response.send_modal(modal)
    
    async def process_bingo_card_with_validated_items(self, channel_id: int, player: discord.Member, items: List[str]):
        """검증된 아이템으로 빙고 카드 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return False, "게임을 찾을 수 없습니다."
        
        # 빙고 카드 생성
        grid = []
        for i in range(5):
            row = []
            for j in range(5):
                item = items[i * 5 + j]
                row.append(item)
            grid.append(row)
        
        # 마크 배열 생성 (FREE는 이미 마크됨)
        marked = [[False] * 5 for _ in range(5)]
        for i in range(5):
            for j in range(5):
                if grid[i][j] == "FREE":
                    marked[i][j] = True
        
        # 닉네임에서 실제 플레이어 이름 추출
        display_name = get_player_name_from_nickname(player.display_name)
        
        # 빙고 카드 객체 생성
        bingo_card = BingoCard(
            player_id=player.id,
            player_name=player.display_name,
            display_name=display_name,
            grid=grid,
            marked=marked
        )
        
        game_data["players"][player.id] = bingo_card
        
        # 이제 실제로 게임 플레이 소비
        user_id = str(player.id)
        if user_id in game_data["player_payments"]:
            await self.consume_game_play(user_id, game_data["player_payments"][user_id])
        
        # 빙고판 이미지 생성 및 업로드
        await self._update_and_send_bingo_image(player, bingo_card)
        
        debug_log("BINGO", f"Player {display_name} joined with custom card")
        
        return True, "빙고 카드가 생성되었습니다!"
    
    async def process_bingo_card(self, channel_id: int, player: discord.Member, rows: List[str]):
        """빙고 카드 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return False, "게임을 찾을 수 없습니다."
        
        # 모든 아이템 수집
        all_items = []
        for row_text in rows:
            items = [item.strip() for item in row_text.split(',')]
            all_items.extend(items)
        
        # 검증
        if len(all_items) != 25:
            return False, f"25개의 항목을 입력해야 합니다. (현재 {len(all_items)}개)"
        
        # 중복 검사
        seen = set()
        duplicates = []
        for item in all_items:
            if item.upper() != "FREE" and item in seen:
                duplicates.append(item)
            seen.add(item)
        
        if duplicates:
            return False, f"중복된 항목이 있습니다: {', '.join(duplicates)}"
        
        # 검증된 데이터로 빙고 카드 생성
        return await self.process_bingo_card_with_validated_items(channel_id, player, all_items)
    
    async def _update_and_send_bingo_image(self, player: discord.Member, bingo_card: BingoCard):
        """빙고판 이미지 업데이트 및 전송 - 최적화됨"""
        try:
            if debug_config.debug_enabled:
                debug_log("BINGO", f"Updating bingo image for {bingo_card.display_name}")
                update_start = time.time()
            
            # 전역 이미지 생성기 사용
            if not global_image_generator or not global_image_generator.is_initialized:
                await self._send_text_bingo_card(player, bingo_card)
                return
            
            # 이미지 생성
            image_data = global_image_generator.generate_bingo_image(bingo_card)
            
            if debug_config.debug_enabled:
                debug_log("BINGO", f"Image generated, size: {len(image_data)} bytes")
            
            # 구글 드라이브에 업로드
            filename = f"bingo_{player.id}_{int(time.time())}.png"
            image_url = self.drive_uploader.upload_image(image_data, filename)
            
            if image_url:
                bingo_card.image_url = image_url
                
                embed = discord.Embed(
                    title=f"🎊 {bingo_card.display_name}님의 빙고 카드",
                    color=discord.Color.blue()
                )
                embed.set_image(url=image_url)
                embed.add_field(
                    name="빙고 수",
                    value=f"{bingo_card.bingo_count}개",
                    inline=True
                )
                
                # DM 전송/수정
                if bingo_card.dm_message_id:
                    try:
                        channel = player.dm_channel or await player.create_dm()
                        message = await channel.fetch_message(bingo_card.dm_message_id)
                        await message.edit(embed=embed)
                        debug_log("BINGO", f"Updated existing DM for {bingo_card.display_name}")
                    except Exception as e:
                        debug_log("BINGO", f"Failed to edit DM, sending new: {e}")
                        message = await player.send(embed=embed)
                        bingo_card.dm_message_id = message.id
                else:
                    message = await player.send(embed=embed)
                    bingo_card.dm_message_id = message.id
                    debug_log("BINGO", f"Sent new DM to {bingo_card.display_name}")
                
                if debug_config.debug_enabled:
                    elapsed = time.time() - update_start
                    debug_log("BINGO", f"Total image update time: {elapsed:.3f} seconds")
            else:
                await self._send_text_bingo_card(player, bingo_card)
                
        except Exception as e:
            logger.error(f"빙고 이미지 전송 실패: {e}")
            await self._send_text_bingo_card(player, bingo_card)
    
    async def _send_text_bingo_card(self, player: discord.Member, bingo_card: BingoCard):
        """텍스트 빙고 카드 전송 (폴백)"""
        embed = discord.Embed(
            title=f"🎊 {bingo_card.display_name}님의 빙고 카드",
            color=discord.Color.blue()
        )
        
        # 카드 그리드 표시
        grid_str = ""
        for i in range(self.grid_size):
            row_str = ""
            for j in range(self.grid_size):
                item = bingo_card.grid[i][j]
                if item.upper() == "FREE":
                    item = "🆓"
                
                if bingo_card.marked[i][j]:
                    row_str += f"**[{item}]** "
                else:
                    row_str += f"[{item}] "
            grid_str += row_str + "\n"
        
        embed.description = grid_str
        embed.add_field(
            name="빙고 수",
            value=f"{bingo_card.bingo_count}개",
            inline=True
        )
        
        # DM 메시지 ID가 있으면 수정, 없으면 새로 전송
        try:
            if bingo_card.dm_message_id:
                channel = player.dm_channel or await player.create_dm()
                message = await channel.fetch_message(bingo_card.dm_message_id)
                await message.edit(embed=embed)
            else:
                message = await player.send(embed=embed)
                bingo_card.dm_message_id = message.id
        except Exception as e:
            logger.error(f"텍스트 빙고 카드 전송 실패: {e}")
    
    @performance_tracker
    async def start_game(self, channel_id: int):
        """게임 시작"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        if len(game_data["players"]) < self.min_players:
            return
        
        game_data["phase"] = "playing"
        game_data["start_time"] = time.time()
        
        # 턴 순서 정하기
        player_ids = list(game_data["players"].keys())
        random.shuffle(player_ids)
        game_data["turn_order"] = player_ids
        
        # 플레이어별 턴 순서 저장
        for idx, player_id in enumerate(player_ids):
            game_data["players"][player_id].turn_order = idx + 1
        
        debug_log("BINGO", f"Game started with {len(game_data['players'])} players")
        
        # 게임 시작 알림
        embed = discord.Embed(
            title="🎊 빙고 게임 시작!",
            description=f"참가자: {len(game_data['players'])}명\n"
                       f"각자 DM으로 빙고 카드를 확인하세요!",
            color=discord.Color.green()
        )
        
        # 턴 순서 표시 (한글 이름 사용)
        turn_info = "\n".join([
            f"{idx + 1}. {game_data['players'][pid].display_name}"
            for idx, pid in enumerate(player_ids)
        ])
        embed.add_field(
            name="턴 순서",
            value=turn_info,
            inline=False
        )
        
        # 첫 번째 플레이어 차례 알림
        first_player_card = game_data["players"][player_ids[0]]
        embed.add_field(
            name="현재 차례",
            value=f"🎯 {first_player_card.display_name}님의 차례입니다!",
            inline=False
        )
        
        view = BingoGameView(self, channel_id)
        await game_data["message"].edit(embed=embed, view=view)
    
    async def call_number_with_modal(self, interaction: discord.Interaction, channel_id: int):
        """모달을 통해 숫자 호출"""
        game_data = self.active_games.get(channel_id)
        if not game_data or game_data["phase"] != "playing":
            await interaction.response.send_message(
                "게임이 진행 중이 아닙니다.",
                ephemeral=True
            )
            return
        
        # 현재 차례 확인
        current_player_id = game_data["turn_order"][game_data["current_turn"]]
        if interaction.user.id != current_player_id:
            await interaction.response.send_message(
                "당신의 차례가 아닙니다!",
                ephemeral=True
            )
            return
        
        modal = NumberCallModal(self, channel_id)
        await interaction.response.send_modal(modal)
    
    async def process_called_number(self, channel_id: int, called_number: str):
        """호출된 숫자 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return False, "게임을 찾을 수 없습니다."
        
        # 이미 호출된 숫자인지 확인
        if called_number in game_data["called_numbers"]:
            return False, "이미 호출된 숫자입니다!"
        
        # 호출된 숫자 추가
        game_data["called_numbers"].add(called_number)
        
        debug_log("BINGO", f"Number called: {called_number}")
        
        # 모든 플레이어 카드 업데이트
        new_bingos = []
        
        for player_id, bingo_card in game_data["players"].items():
            updated = False
            
            # 카드에서 숫자 찾기
            for i in range(self.grid_size):
                for j in range(self.grid_size):
                    if bingo_card.grid[i][j] == called_number:
                        bingo_card.marked[i][j] = True
                        updated = True
                        break
            
            if updated:
                # 빙고 체크
                old_bingo_count = bingo_card.bingo_count
                self._check_bingo(bingo_card)
                
                if bingo_card.bingo_count > old_bingo_count:
                    new_bingos.append((player_id, bingo_card))
                
                # 이미지 업데이트 및 DM 수정
                player = game_data["message"].guild.get_member(player_id)
                if player:
                    await self._update_and_send_bingo_image(player, bingo_card)
        
        # 다음 턴으로 이동
        game_data["current_turn"] = (game_data["current_turn"] + 1) % len(game_data["turn_order"])
        
        # 결과를 튜플로 반환
        return True, (called_number, new_bingos)
    
    def _check_bingo(self, bingo_card: BingoCard):
        """빙고 확인"""
        completed_lines = set()
        
        # 가로 확인
        for i in range(self.grid_size):
            if all(bingo_card.marked[i]):
                line_id = f"row_{i}"
                if line_id not in bingo_card.completed_lines:
                    completed_lines.add(line_id)
        
        # 세로 확인
        for j in range(self.grid_size):
            if all(bingo_card.marked[i][j] for i in range(self.grid_size)):
                line_id = f"col_{j}"
                if line_id not in bingo_card.completed_lines:
                    completed_lines.add(line_id)
        
        # 대각선 확인
        if all(bingo_card.marked[i][i] for i in range(self.grid_size)):
            line_id = "diag_1"
            if line_id not in bingo_card.completed_lines:
                completed_lines.add(line_id)
        
        if all(bingo_card.marked[i][self.grid_size-1-i] for i in range(self.grid_size)):
            line_id = "diag_2"
            if line_id not in bingo_card.completed_lines:
                completed_lines.add(line_id)
        
        bingo_card.completed_lines.update(completed_lines)
        bingo_card.bingo_count = len(bingo_card.completed_lines)
    
    async def update_game_display(self, channel_id: int, called_number: str, new_bingos: List):
        """게임 화면 업데이트"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        # 현재 차례 플레이어
        current_player_id = game_data["turn_order"][game_data["current_turn"]]
        current_player_card = game_data["players"][current_player_id]
        
        # 새 embed 생성
        embed = discord.Embed(
            title="🎊 빙고 게임 진행 중",
            description=f"**호출된 숫자**: {called_number}",
            color=discord.Color.gold()
        )
        
        # 호출된 숫자들
        called_list = list(game_data["called_numbers"])
        if len(called_list) > 10:
            recent_calls = called_list[-10:]
            embed.add_field(
                name="최근 호출",
                value=" → ".join(recent_calls),
                inline=False
            )
        else:
            embed.add_field(
                name="호출된 숫자들",
                value=" → ".join(called_list) if called_list else "없음",
                inline=False
            )
        
        # 새로운 빙고 알림
        for player_id, bingo_card in new_bingos:
            embed.add_field(
                name="🎉 빙고!",
                value=f"**{bingo_card.display_name}**님이 {bingo_card.bingo_count}빙고를 달성했습니다!",
                inline=False
            )
            
            # 5빙고 달성 시 게임 종료
            if bingo_card.bingo_count >= 5:
                await self._end_game(channel_id)
                return
        
        # 현재 순위
        sorted_players = sorted(
            game_data["players"].items(),
            key=lambda x: x[1].bingo_count,
            reverse=True
        )
        
        ranking_text = "\n".join([
            f"{idx + 1}. {card.display_name} - {card.bingo_count}빙고"
            for idx, (pid, card) in enumerate(sorted_players[:5])
        ])
        
        embed.add_field(
            name="현재 순위",
            value=ranking_text if ranking_text else "없음",
            inline=True
        )
        
        # 현재 차례
        embed.add_field(
            name="🎯 현재 차례",
            value=f"**{current_player_card.display_name}**님의 차례입니다!",
            inline=True
        )
        
        # View 재생성
        view = BingoGameView(self, channel_id)
        
        # 메시지 편집
        try:
            await game_data["message"].edit(embed=embed, view=view)
        except discord.HTTPException as e:
            logger.error(f"게임 화면 업데이트 실패: {e}")
        
        debug_log("BINGO", f"Game display updated. Current turn: {current_player_card.display_name}")
    
    async def _end_game(self, channel_id: int):
        """게임 종료"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        game_data["phase"] = "ended"
        debug_log("BINGO", f"Game ended")
        
        # 최종 순위 계산
        sorted_players = sorted(
            game_data["players"].items(),
            key=lambda x: x[1].bingo_count,
            reverse=True
        )
        
        # 결과 임베드
        embed = discord.Embed(
            title="🎊 빙고 게임 종료!",
            color=discord.Color.gold()
        )
        
        # 순위별 그룹화 (동점자 처리)
        rank_groups = {}
        current_rank = 1
        last_bingo_count = -1
        
        for idx, (pid, card) in enumerate(sorted_players):
            if card.bingo_count != last_bingo_count:
                current_rank = idx + 1
                last_bingo_count = card.bingo_count
            
            if current_rank not in rank_groups:
                rank_groups[current_rank] = []
            rank_groups[current_rank].append((pid, card))
        
        # 전체 순위 표시
        ranking_text = []
        for rank, players in sorted(rank_groups.items()):
            for pid, card in players:
                ranking_text.append(f"{rank}. {card.display_name} - {card.bingo_count}빙고")
        
        embed.add_field(
            name="최종 순위",
            value="\n".join(ranking_text),
            inline=False
        )
        
        # 게임 통계
        total_called = len(game_data["called_numbers"])
        game_duration = int(time.time() - game_data["start_time"])
        minutes = game_duration // 60
        seconds = game_duration % 60
        
        embed.add_field(
            name="게임 통계",
            value=f"호출된 숫자: {total_called}개\n"
                  f"게임 시간: {minutes}분 {seconds}초\n"
                  f"참가자: {len(game_data['players'])}명",
            inline=False
        )
        
        # 보상 지급
        from utility import update_player_balance, update_user_inventory, get_user_inventory
        reward_text = []
        total_players = len(sorted_players)
        
        # 1위 보상 (모든 1위 동점자에게 지급)
        if 1 in rank_groups:
            for player_id, card in rank_groups[1]:
                player_id_str = str(player_id)
                
                # 코인 지급
                await update_player_balance(player_id_str, 2)
                
                # 아이템 지급
                random_item = random.choice(self.available_items)
                
                # 현재 인벤토리 가져오기
                current_inventory = await get_user_inventory(player_id_str)
                if current_inventory:
                    current_items = current_inventory.get("items", [])
                    new_items = current_items + [random_item]
                    
                    # 인벤토리 업데이트
                    await update_user_inventory(
                        player_id_str,
                        coins=current_inventory.get("coins"),
                        items=new_items,
                        outfits=current_inventory.get("outfits"),
                        physical_status=current_inventory.get("physical_status"),
                        corruption=current_inventory.get("corruption")
                    )
                
                reward_text.append(f"🥇 **1위** {card.display_name}: 2💰 + {random_item}")
        
        # 2위 보상 (3명 이상이고 1위가 혼자일 때만)
        if total_players >= 3 and 2 in rank_groups:
            if len(rank_groups.get(1, [])) == 1:
                for player_id, card in rank_groups[2]:
                    player_id_str = str(player_id)
                    
                    # 코인만 지급
                    await update_player_balance(player_id_str, 1)
                    reward_text.append(f"🥈 **2위** {card.display_name}: 1💰")
        
        # 3위 보상 (3명 이상이고 1,2위가 각각 혼자일 때만)
        if total_players >= 3 and 3 in rank_groups:
            if len(rank_groups.get(1, [])) == 1 and len(rank_groups.get(2, [])) == 1:
                for player_id, card in rank_groups[3]:
                    player_id_str = str(player_id)
                    
                    # 아이템만 지급
                    random_item = random.choice(self.available_items)
                    
                    # 현재 인벤토리 가져오기
                    current_inventory = await get_user_inventory(player_id_str)
                    if current_inventory:
                        current_items = current_inventory.get("items", [])
                        new_items = current_items + [random_item]
                        
                        # 인벤토리 업데이트
                        await update_user_inventory(
                            player_id_str,
                            coins=current_inventory.get("coins"),
                            items=new_items,
                            outfits=current_inventory.get("outfits"),
                            physical_status=current_inventory.get("physical_status"),
                            corruption=current_inventory.get("corruption")
                        )
                    
                    reward_text.append(f"🥉 **3위** {card.display_name}: {random_item}")
        
        # 보상 표시
        if reward_text:
            embed.add_field(
                name="🎁 특별 보상",
                value="\n".join(reward_text),
                inline=False
            )
        
        # 참가자 수와 동점자 안내
        if total_players == 2 and len(rank_groups.get(1, [])) == 2:
            embed.add_field(
                name="💡 안내",
                value="2명 모두 동점으로 1위 보상이 지급되었습니다.",
                inline=False
            )
        elif total_players == 2:
            embed.add_field(
                name="💡 안내",
                value="2명 참가로 1위에게만 보상이 지급되었습니다.",
                inline=False
            )
        
        try:
            await game_data["message"].edit(embed=embed, view=None)
        except discord.HTTPException as e:
            logger.error(f"게임 종료 메시지 편집 실패: {e}")
        
        # 게임 데이터 정리
        del self.active_games[channel_id]

# UI 컴포넌트들
class BingoLobbyView(discord.ui.View):
    def __init__(self, game: MatsuriRingoGame, channel_id: int):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
    
    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, emoji="🎊")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.game.add_player_with_modal(interaction, self.channel_id)
    
    @discord.ui.button(label="시작하기", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_data = self.game.active_games.get(self.channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "게임을 찾을 수 없습니다.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game_data["host"].id:
            await interaction.response.send_message(
                "호스트만 게임을 시작할 수 있습니다!",
                ephemeral=True
            )
            return
        
        if len(game_data["players"]) < self.game.min_players:
            await interaction.response.send_message(
                f"최소 {self.game.min_players}명이 필요합니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self.game.start_game(self.channel_id)
        self.stop()

class BingoCardInputModal(discord.ui.Modal):
    def __init__(self, game: MatsuriRingoGame, channel_id: int, player: discord.Member):
        super().__init__(title="빙고 카드 만들기 (1~100 숫자만)")
        self.game = game
        self.channel_id = channel_id
        self.player = player
        
        # 5개의 입력 필드 (각 줄마다)
        self.row1 = discord.ui.TextInput(
            label="1번째 줄 (1~100 숫자 5개, 콤마로 구분)",
            placeholder="예: 1, 2, 3, 4, 5",
            required=True,
            max_length=50
        )
        self.add_item(self.row1)
        
        self.row2 = discord.ui.TextInput(
            label="2번째 줄 (1~100 숫자 5개, 콤마로 구분)",
            placeholder="예: 6, 7, 8, 9, 10",
            required=True,
            max_length=50
        )
        self.add_item(self.row2)
        
        self.row3 = discord.ui.TextInput(
            label="3번째 줄 (1~100 숫자 5개, 콤마로 구분)",
            placeholder="예: 11, 12, FREE, 14, 15 (FREE 사용 가능)",
            required=True,
            max_length=50
        )
        self.add_item(self.row3)
        
        self.row4 = discord.ui.TextInput(
            label="4번째 줄 (1~100 숫자 5개, 콤마로 구분)",
            placeholder="예: 16, 17, 18, 19, 20",
            required=True,
            max_length=50
        )
        self.add_item(self.row4)
        
        self.row5 = discord.ui.TextInput(
            label="5번째 줄 (1~100 숫자 5개, 콤마로 구분)",
            placeholder="예: 21, 22, 23, 24, 25",
            required=True,
            max_length=50
        )
        self.add_item(self.row5)
    
    def validate_input(self, rows: List[str]) -> Tuple[bool, str, List[str]]:
        """입력 검증"""
        all_items = []
        
        for row_idx, row_text in enumerate(rows):
            items = [item.strip() for item in row_text.split(',')]
            
            if len(items) != 5:
                return False, f"{row_idx + 1}번째 줄에 정확히 5개의 숫자를 입력해야 합니다.", []
            
            for item in items:
                # FREE는 허용
                if item.upper() == "FREE":
                    all_items.append("FREE")
                    continue
                
                # 숫자인지 확인
                try:
                    num = int(item)
                    # 1~100 범위 확인
                    if num < 1 or num > 100:
                        return False, f"'{item}'은(는) 1~100 범위를 벗어났습니다.", []
                    all_items.append(str(num))
                except ValueError:
                    return False, f"'{item}'은(는) 올바른 숫자가 아닙니다.", []
        
        # 중복 검사
        seen = set()
        duplicates = []
        for item in all_items:
            if item != "FREE" and item in seen:
                duplicates.append(item)
            seen.add(item)
        
        if duplicates:
            return False, f"중복된 숫자가 있습니다: {', '.join(duplicates)}", []
        
        return True, "성공", all_items
    
    async def on_submit(self, interaction: discord.Interaction):
        # 먼저 defer로 응답 시간 연장
        await interaction.response.defer(ephemeral=True)
        
        rows = [
            self.row1.value,
            self.row2.value,
            self.row3.value,
            self.row4.value,
            self.row5.value
        ]
        
        # 입력 검증
        is_valid, error_message, validated_items = self.validate_input(rows)
        
        if not is_valid:
            await interaction.followup.send(
                f"❌ {error_message}\n다시 시도해주세요.",
                ephemeral=True
            )
            return
        
        # 검증된 데이터로 빙고 카드 생성
        success, message = await self.game.process_bingo_card_with_validated_items(
            self.channel_id,
            self.player,
            validated_items
        )
        
        if success:
            await interaction.followup.send(
                f"✅ {message}\nDM으로 빙고 카드를 확인하세요!",
                ephemeral=True
            )
            
            # 참가 인원 업데이트
            game_data = self.game.active_games.get(self.channel_id)
            if game_data:
                await interaction.followup.send(
                    f"{self.player.display_name}님이 참가했습니다! "
                    f"({len(game_data['players'])}/{self.game.max_players})",
                    ephemeral=False
                )
        else:
            await interaction.followup.send(
                f"❌ {message}\n다시 시도해주세요.",
                ephemeral=True
            )

class BingoGameView(discord.ui.View):
    def __init__(self, game: MatsuriRingoGame, channel_id: int):
        super().__init__(timeout=None)
        self.game = game
        self.channel_id = channel_id
    
    @discord.ui.button(label="다음 호출", style=discord.ButtonStyle.primary, emoji="📢")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.game.call_number_with_modal(interaction, self.channel_id)
    
    @discord.ui.button(label="게임 종료", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_data = self.game.active_games.get(self.channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "게임이 이미 종료되었습니다.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game_data["host"].id:
            await interaction.response.send_message(
                "호스트만 게임을 종료할 수 있습니다!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        await self.game._end_game(self.channel_id)
        self.stop()

class NumberCallModal(discord.ui.Modal):
    def __init__(self, game: MatsuriRingoGame, channel_id: int):
        super().__init__(title="숫자 호출")
        self.game = game
        self.channel_id = channel_id
        
        self.number_input = discord.ui.TextInput(
            label="호출할 숫자/단어",
            placeholder="예: 7, 42, apple 등",
            required=True,
            max_length=50
        )
        self.add_item(self.number_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # 먼저 defer로 응답 시간 연장
        await interaction.response.defer(ephemeral=True)
        
        called_number = self.number_input.value.strip()
        
        # process_called_number 호출 (interaction 없이)
        success, result = await self.game.process_called_number(
            self.channel_id,
            called_number
        )
        
        if success:
            # 결과 언패킹
            called_num, new_bingos = result
            
            # followup으로 메시지 보내기 (delete_after 제거)
            message = await interaction.followup.send(
                f"✅ '{called_num}' 호출됨!",
                ephemeral=True
            )
            
            # 2초 후에 수동으로 메시지 삭제 (ephemeral 메시지는 삭제할 필요 없음)
            # ephemeral 메시지는 다른 사람이 볼 수 없으므로 삭제하지 않아도 됨
            
            # 게임 화면 업데이트
            await self.game.update_game_display(self.channel_id, called_num, new_bingos)
        else:
            # 오류 메시지
            await interaction.followup.send(
                f"❌ {result}",
                ephemeral=True
            )

# 전역 게임 인스턴스
matsuri_bingo_game = MatsuriRingoGame()

def get_matsuri_bingo_game():
    return matsuri_bingo_game