# card_utils.py
import discord
from PIL import Image, ImageDraw, ImageFilter
import io
import os
import aiohttp
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# 구글 드라이브 카드 이미지 파일 ID 매핑
CARD_FILE_IDS = {
    '♣2': '1mtobL-efo7KOmbvSBHGFpkfp5fquMsG1', '♦2': '1_xu9m2-wmpwPZIdAxyn-l6L0_kPRFhoO', 
    '♥2': '1I9CTRfD1FLlPJgnnFpElY5Eb0hr-aYhn', '♠2': '1CT_Zufs5lIN-xImZT6lJsVll7ZTSppEj',
    '♣3': '1KuDGtS8vjlJgN6Mic0BEtBkVdqX9Fojk', '♦3': '1Lc-hWcMAWJddbFUy5-fcO49ACnrmAwFO',
    '♥3': '1Z1gY1XOEEdRZIozdF1pjyL70LTbDH0AH', '♠3': '1Zvn5IdQR756I0an1ZEmJnOlGnQXX3YHp',
    '♣4': '1qJfh0TdgqbbLifFDOPCnQJBMETdpAl6-', '♦4': '1WkElJvZ8Xl_dyAdcl3m1DZFPx4EsGjJV',
    '♥4': '17gnJnNqImZ2eS6T_w3poVmBlqxYXA-OT', '♠4': '1mbSZATbsOlnm3kBgIqYWM5avSrYkkWC_',
    '♣5': '1sKjCj7TOsVyp5LMg2gkGdg2ytZ9_Y2WJ', '♦5': '1jl7N5Pb0XibZwibYeK80kxnh_dGD954L',
    '♥5': '1xquvFSq8n9bPmMZi9vvxP5Dt5e0xfyyp', '♠5': '1X14vBPgT25GUiJUsZB-V_zYv7hWOCAPp',
    '♣6': '1rtqo5UoKsOM_kNIGzAXi1SXxPDxGzOBE', '♦6': '1zCck80rx4sP-ZQKE3329MCEmHmHOTIs-',
    '♥6': '15_k8ZDfwgHzXERmE0bY5uWC584YGCCw5', '♠6': '1VAIw8LoyycFp3jnix3I1OtFF5pI-HTZa',
    '♣7': '1HQGC-hqXv3Rqb9hfC7AzqiiN70tnyFdD', '♦7': '1biShOfgCucYYIn_nDPqAMqRS0UNDnX4T',
    '♥7': '1XC77YQoHA8wixGl72ux4nArSBP25uYzb', '♠7': '1HOY2I3P89rCfzPC0Xpq1zmrL9CTw4UH6',
    '♣8': '1Y9y5XuZPqJa_qRekG1et3hW-GD5q1ghs', '♦8': '1kdDL17s4xpV7EyNc7M4eu0RjBrplkgs7',
    '♥8': '1GlkTrr3mySPVqRI_qTMpRaBa0SL75wQ9', '♠8': '1oNqnF1yggawhapp0DtLO5k9OreQufB3_',
    '♣9': '18zla4UUPBxVhtzHarK4H-RL0hZ5fe-hV', '♦9': '1CiKrg6VcCrOFWb2dzHjeBLpmblYue8NP',
    '♥9': '1rslq6p7SxTTeX8Qa8UzwK07c8ithclzb', '♠9': '17LYxv_mKsui9yfMO15DHTj-yAUE_Ybpu',
    '♣10': '1aYtmIdyrLMc0Sxo4ijpJiPsWktznjOOV', '♦10': '19u7AHm9e7lBoEgXtOX4JhZNs9V64KaZz',
    '♥10': '1DrAHr24yF6N42MwcTvc8HjsmZthIAvlw', '♠10': '1n9T6zvKxVeLRd-0urC4DjEIcV9GS8INz',
    '♣A': '1LxHYB-E6OSkKXvKLxwN3ZfQWprRuO9fl', '♦A': '1zdoPtRzEK-i7p3_LSzGeozW_xxCwb0gN',
    '♥A': '1MarGa3VGfcgzR3KvUyJKvnlK66GT2-Bc', '♠A': '1MKl-dH47bE2726gl2ZeZpHbrsWDR8L2x',
    '♣J': '1V9cX0xwb-oX_znzt1DWrJ__LlpuVVJSK', '♦J': '1yADAdK4CmufJrfQmxXr_90jTCmoL_0GM',
    '♥J': '1W1iQaxqyc3cLcWy9L_H3igDtHgmUNw-e', '♠J': '1ZjxG2GJLH4aowyxW2bfjR-Od-uB6J4bo',
    '♣Q': '1DrJZcYkTOJWRF_L6tUXC10oxib7VCgH_', '♦Q': '1RH5DtRFOnIUblyGmnKPRO3JtsqwcIfYL',
    '♥Q': '1AKmuCHq7YZItAT9q8gm3t1u3eYmjHzC0', '♠Q': '1MXddEQLvg3sSjWhwmAxhDZVpXEX0qvFh',
    '♣K': '1mkPKogNSFJ63HnJXAzuz_M2riuT_LkNT', '♦K': '1XTL7Fqcrm2SyGG8MYr_t8Zp3KzWeIpTk',
    '♥K': '1UWB2bUyxllNtJC9gP3uPvow6qnjsBWcy', '♠K': '1De2n1iaStNdN3ZEedzRmzjyJaRDIHTaH',
    '🃏조커': '1SmR5pn0C5tY_xP34sr9ytpuw0jLnwQ0M'
}

class CardImageManager:
    """카드 이미지 관리 클래스"""
    def __init__(self):
        self.card_images = {}
        
    async def download_card_image(self, card_name: str) -> Image.Image:
        """카드 이미지 다운로드 및 캐싱"""
        if card_name in self.card_images:
            return self.card_images[card_name]
        
        # 카드 이름을 파일명으로 변환
        if '조커' in card_name:
            filename = 'red_joker.png'
        else:
            suit_map = {'♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs'}
            rank_map = {'A': 'ace', 'J': 'jack', 'Q': 'queen', 'K': 'king'}
            
            suit_char = card_name[0]
            rank = card_name[1:]
            
            suit = suit_map.get(suit_char, '')
            if rank in rank_map:
                rank = rank_map[rank]
            
            filename = f"{rank}_of_{suit}.png"
        
        # 로컬에 이미지가 있는지 확인
        local_path = f"cards/{filename}"
        if os.path.exists(local_path):
            img = Image.open(local_path)
        else:
            # 구글 드라이브에서 다운로드
            try:
                file_id = CARD_FILE_IDS.get(card_name, '')
                if file_id:
                    url = f"https://drive.google.com/uc?export=download&id={file_id}"
                else:
                    # 파일 ID가 없으면 기본 카드 이미지 생성
                    img = self.create_default_card_image(card_name)
                    self.card_images[card_name] = img
                    return img
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            img_data = await resp.read()
                            img = Image.open(io.BytesIO(img_data))
                            
                            # 로컬에 저장
                            os.makedirs("cards", exist_ok=True)
                            img.save(local_path)
                        else:
                            img = self.create_default_card_image(card_name)
            except Exception as e:
                logger.error(f"카드 이미지 다운로드 실패: {e}")
                img = self.create_default_card_image(card_name)
        
        # 이미지 크기 조정
        img = img.resize((100, 140), Image.Resampling.LANCZOS)
        self.card_images[card_name] = img
        return img
    
    def create_default_card_image(self, card_name: str) -> Image.Image:
        """기본 카드 이미지 생성"""
        width, height = 100, 140
        
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        
        # 카드 테두리
        draw.rectangle([(2, 2), (width-3, height-3)], outline='black', width=2)
        
        # 카드 내용
        if '조커' in card_name:
            draw.text((width//2, height//2), '🃏', fill='red', anchor='mm')
            draw.text((width//2, height//2 + 20), 'JOKER', fill='red', anchor='mm')
        else:
            suit_char = card_name[0]
            rank = card_name[1:]
            
            color = 'red' if suit_char in ['♥', '♦'] else 'black'
            
            draw.text((10, 10), rank, fill=color)
            draw.text((10, 25), suit_char, fill=color)
            draw.text((width//2, height//2), suit_char, fill=color, anchor='mm')
            draw.text((width-10, height-10), rank, fill=color, anchor='rb')
            draw.text((width-10, height-25), suit_char, fill=color, anchor='rb')
        
        return img
    
    async def create_hand_image(self, cards: List[Dict], game_type: str = "joker") -> io.BytesIO:
        """여러 카드를 하나의 이미지로 합성"""
        card_width = 100
        card_height = 140
        gap = 20
        shadow_offset = 5
        
        # 전체 이미지 크기 계산
        total_width = len(cards) * card_width + (len(cards) - 1) * gap + shadow_offset * 2
        total_height = card_height + shadow_offset * 2
        
        # 배경 이미지 생성
        background = Image.new('RGBA', (total_width, total_height), (255, 255, 255, 0))
        
        for i, card in enumerate(cards):
            # 카드 이름 결정
            if game_type == "joker":
                card_name = card.get('name', '')
            else:  # blackjack
                rank, suit = card
                card_name = f"{suit}{rank}"
            
            # 카드 이미지 다운로드
            card_img = await self.download_card_image(card_name)
            
            # 그림자 효과 생성
            shadow = Image.new('RGBA', (card_width + 10, card_height + 10), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rectangle([(5, 5), (card_width + 5, card_height + 5)], fill=(0, 0, 0, 100))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
            
            # 카드 위치 계산
            x_pos = i * (card_width + gap) + shadow_offset
            y_pos = shadow_offset
            
            # 그림자 붙이기
            background.paste(shadow, (x_pos - 5, y_pos - 5), shadow)
            
            # 카드 붙이기
            if card_img.mode != 'RGBA':
                card_img = card_img.convert('RGBA')
            background.paste(card_img, (x_pos, y_pos), card_img)
        
        # BytesIO 객체로 변환
        output = io.BytesIO()
        background.save(output, format='PNG')
        output.seek(0)
        
        return output

# 전역 카드 이미지 매니저
card_image_manager = CardImageManager()

def get_card_image_manager():
    """카드 이미지 매니저 인스턴스 반환"""
    return card_image_manager