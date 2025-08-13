# dalgona.py - 보상 로직이 제거된 버전
import discord
from discord import app_commands
import asyncio
import random
import logging
import time
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from debug_config import debug_log, debug_config
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Google Sheets 설정
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
ITEM_SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1p4x6mpUqiCPK7gB6Tk_Ju1PWkRn-DoqoPTeEfgoOl4E/edit?usp=sharing"

class ItemManager:
    """아이템 관리자"""
    def __init__(self):
        self.items_cache = []
        self.last_cache_time = 0
        self.cache_duration = 3600  # 1시간
        
    async def get_items_from_sheet(self) -> List[Tuple[str, str]]:
        """스프레드시트에서 아이템 목록 가져오기"""
        try:
            # 캐시 확인
            current_time = asyncio.get_event_loop().time()
            if self.items_cache and (current_time - self.last_cache_time) < self.cache_duration:
                return self.items_cache
            
            # Google Sheets 연결
            creds = Credentials.from_service_account_file(
                "service_account.json", scopes=SCOPES
            )
            gc = gspread.authorize(creds)
            
            # 스프레드시트 열기
            sheet = gc.open_by_url(ITEM_SPREADSHEET_URL).worksheet("시트1")
            
            # A열(아이템 이름)과 B열(아이템 설명) 가져오기
            items_data = sheet.get("A2:B", value_render_option='UNFORMATTED_VALUE')
            
            items = []
            for row in items_data:
                if len(row) >= 2 and row[0] and row[1]:
                    item_name = str(row[0]).strip()
                    item_desc = str(row[1]).strip()
                    items.append((item_name, item_desc))
            
            # 캐시 업데이트
            self.items_cache = items
            self.last_cache_time = current_time
            
            debug_log("DALGONA", f"Loaded {len(items)} items from spreadsheet")
            return items
            
        except Exception as e:
            logger.error(f"스프레드시트에서 아이템 로드 실패: {e}")
            # 폴백: 기본 아이템 목록
            return [
                ("달고나", "완벽한 모양의 달고나"),
                ("설탕 봉지", "달고나를 만들 수 있는 설탕"),
                ("국자", "달고나 제작용 국자")
            ]

# 전역 아이템 관리자
item_manager = ItemManager()

class DalgonaShape(Enum):
    """달고나 모양"""
    CIRCLE = ("원", "⭕")
    TRIANGLE = ("삼각형", "🔺")
    STAR = ("별", "⭐")
    UMBRELLA = ("우산", "☂️")

class DalgonaGame:
    def __init__(self):
        self.active_games = {}
        self.shape_patterns = {
            DalgonaShape.CIRCLE: [
                [0, 1, 1, 1, 0],
                [1, 1, 1, 1, 1],
                [1, 1, 1, 1, 1],
                [1, 1, 1, 1, 1],
                [0, 1, 1, 1, 0]
            ],
            DalgonaShape.TRIANGLE: [
                [0, 0, 1, 0, 0],
                [0, 1, 1, 1, 0],
                [0, 1, 1, 1, 0],
                [1, 1, 1, 1, 1],
                [1, 1, 1, 1, 1]
            ],
            DalgonaShape.STAR: [
                [0, 0, 1, 0, 0],
                [0, 1, 1, 1, 0],
                [1, 1, 1, 1, 1],
                [0, 1, 1, 1, 0],
                [1, 0, 0, 0, 1]
            ],
            DalgonaShape.UMBRELLA: [
                [0, 1, 1, 1, 0],
                [1, 1, 1, 1, 1],
                [1, 1, 1, 1, 1],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0]
            ]
        }
        self.max_fails = 5  # 최대 실패 횟수
        self.leaderboard = []  # 리더보드
    
    def calculate_dice_modifier(self, display_name: str) -> int:
        """닉네임 기반 주사위 보정값 계산"""
        modifier = 0
        
        # 만취 체크 (취함보다 먼저 체크)
        if "만취" in display_name:
            modifier -= 40
            debug_log("DALGONA", f"만취 발견: -40")
        # 취함 체크
        elif "취함" in display_name:
            modifier -= 20
            debug_log("DALGONA", f"취함 발견: -20")
        
        debug_log("DALGONA", f"최종 주사위 보정: {modifier}")
        return modifier
    
    async def _handle_timeout(self, channel_id: int):
        """타임아웃 처리 (별도 태스크)"""
        try:
            await asyncio.sleep(90)
            
            # 게임이 아직 활성화되어 있고 완료되지 않았는지 확인
            if channel_id in self.active_games:
                game_data = self.active_games[channel_id]
                if not game_data["completed"] and not game_data["failed"]:
                    game_data["failed"] = True
                    debug_log("DALGONA", f"Game timeout for channel {channel_id}")
                    await self.end_game(channel_id, reason="시간 초과")
                    
        except asyncio.CancelledError:
            debug_log("DALGONA", f"Timeout task cancelled for channel {channel_id}")
            # 태스크가 취소되면 정상적으로 종료
            pass
        except Exception as e:
            logger.error(f"타임아웃 처리 중 오류: {e}")
    
    def create_preview_embed(self, shape: DalgonaShape, pattern: List[List[int]]) -> discord.Embed:
        """모양 미리보기 임베드 생성"""
        # 미리보기 그리드 생성
        grid_str = ""
        for i in range(5):
            for j in range(5):
                if pattern[i][j] == 1:
                    grid_str += "🟦"  # 정답 위치
                else:
                    grid_str += "⬛"  # 빈 공간
            grid_str += "\n"
        
        embed = discord.Embed(
            title=f"🍪 {shape.value[1]} {shape.value[0]} 모양을 외우세요!",
            description=grid_str,
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="⏰ 준비하세요!",
            value="2초 후에 게임이 시작됩니다!\n이 모양을 잘 기억하세요!",
            inline=False
        )
        
        return embed
    
    async def start_game(self, interaction: discord.Interaction):
        """달고나 게임 시작"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        # 랜덤 모양 선택
        shape = random.choice(list(DalgonaShape))
        pattern = self.shape_patterns[shape]
        grid_size = 5
        
        # 정답 칸 수 계산
        correct_cells = sum(sum(row) for row in pattern)
        max_clicks = correct_cells + 4  # 정답 칸 수 + 4 (실패 횟수에 맞춰 조정)
        
        # 달고나 상태 (0: 초기상태, 1: 정답-파랑, 2: 오답-빨강)
        dalgona_state = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
        
        # 주사위 보정값 계산
        dice_modifier = self.calculate_dice_modifier(interaction.user.display_name)
        
        game_data = {
            "player": interaction.user,
            "shape": shape,
            "pattern": pattern,
            "state": dalgona_state,
            "clicks": 0,
            "max_clicks": max_clicks,
            "correct_cells": correct_cells,
            "correct_count": 0,
            "fail_count": 0,
            "start_time": time.time(),
            "completed": False,
            "failed": False,
            "ended": False,
            "dice_modifier": dice_modifier,
            "guaranteed_success": False,  # 대성공 시 다음 타일 확정 성공
            "dice_history": [],  # 주사위 굴림 기록
            "last_dice_result": None  # 마지막 주사위 결과
        }
        
        self.active_games[channel_id] = game_data
        
        debug_log("DALGONA", f"Started game with shape: {shape.value[0]}, correct cells: {correct_cells}, max clicks: {max_clicks}, dice modifier: {dice_modifier}")
        
        # 모양 미리보기 임베드
        preview_embed = self.create_preview_embed(shape, pattern)
        await interaction.response.send_message(embed=preview_embed)
        game_data["message"] = await interaction.original_response()
        
        # 2초 후 게임 시작
        await asyncio.sleep(2)
        
        # 게임 시작 임베드로 변경
        embed = discord.Embed(
            title="🍪 달고나 도전!",
            description="모양을 기억해서 클릭하세요!",
            color=discord.Color.blue()
        )
        
        # 게임 정보
        embed.add_field(
            name="게임 정보",
            value=f"모양: {shape.value[1]} {shape.value[0]}\n"
                  f"남은 클릭: {max_clicks - game_data['clicks']}회\n"
                  f"목표: {correct_cells}개 타일",
            inline=False
        )
        
        # 뷰 생성
        view = DalgonaView(self, channel_id)
        await game_data["message"].edit(embed=embed, view=view)
        
        # 타임아웃 태스크 시작 (90초)
        asyncio.create_task(self._handle_timeout(channel_id))
    
    def create_grid_embed(self, channel_id: int) -> discord.Embed:
        """현재 게임 상태 임베드 생성"""
        game_data = self.active_games[channel_id]
        
        # 그리드 생성
        grid_str = ""
        for i in range(5):
            for j in range(5):
                state = game_data["state"][i][j]
                if state == 0:
                    grid_str += "🟫"  # 초기 상태
                elif state == 1:
                    grid_str += "🟦"  # 정답
                elif state == 2:
                    grid_str += "🟥"  # 오답
            grid_str += "\n"
        
        embed = discord.Embed(
            title="🍪 달고나 도전 중!",
            description=grid_str,
            color=discord.Color.blue()
        )
        
        # 게임 상태
        embed.add_field(
            name="진행 상황",
            value=f"정답: {game_data['correct_count']}/{game_data['correct_cells']}개\n"
                  f"실패: {game_data['fail_count']}/{self.max_fails}회\n"
                  f"남은 클릭: {game_data['max_clicks'] - game_data['clicks']}회",
            inline=True
        )
        
        # 마지막 주사위 결과
        if game_data["last_dice_result"]:
            embed.add_field(
                name="🎲 마지막 주사위",
                value=game_data["last_dice_result"],
                inline=True
            )
        
        return embed
    
    def check_click(self, channel_id: int, row: int, col: int) -> Tuple[bool, str]:
        """클릭 체크"""
        game_data = self.active_games[channel_id]
        
        # 이미 클릭한 칸인지 확인
        if game_data["state"][row][col] != 0:
            return False, "이미 클릭한 칸입니다!"
        
        game_data["clicks"] += 1
        is_correct = game_data["pattern"][row][col] == 1
        
        # 확정 성공 체크
        if game_data["guaranteed_success"]:
            is_correct = True
            game_data["guaranteed_success"] = False
            game_data["state"][row][col] = 1
            game_data["correct_count"] += 1
            
            if debug_config.debug_enabled:
                debug_log("DALGONA", "Guaranteed success used!")
            
            # 완료 체크
            if game_data["correct_count"] >= game_data["correct_cells"]:
                game_data["completed"] = True
                return True, "🎉 대성공 효과로 완성! 축하합니다!"
            
            return True, "✨ 대성공 효과로 성공!"
        
        # 주사위 굴리기
        base_dice = 100
        modifier = game_data["dice_modifier"]
        max_dice = base_dice + modifier
        dice_roll = random.randint(1, max_dice)
        
        debug_log("DALGONA", f"Dice roll: {dice_roll}/{max_dice}, is_correct: {is_correct}")
        
        # 주사위 결과 저장
        game_data["dice_history"].append((dice_roll, max_dice, is_correct))
        
        # 결과 판정
        result_msg = f"🎲 주사위: {dice_roll}/{max_dice}\n"
        
        if is_correct:
            # 정답 칸을 클릭한 경우
            if dice_roll >= 95:
                # 대성공
                game_data["state"][row][col] = 1
                game_data["correct_count"] += 1
                game_data["guaranteed_success"] = True
                result_msg += "🌟 **대성공!** 다음 타일은 자동으로 성공합니다!"
            elif dice_roll >= 50:
                # 성공
                game_data["state"][row][col] = 1
                game_data["correct_count"] += 1
                result_msg += "✅ 성공!"
            else:
                # 실패
                game_data["state"][row][col] = 2
                game_data["fail_count"] += 1
                result_msg += "💔 실패! 정답이었지만 부서졌습니다..."
        else:
            # 오답 칸을 클릭한 경우
            if dice_roll >= 80:
                # 운 좋게 성공
                game_data["state"][row][col] = 1
                result_msg += "🍀 행운! 빈 곳이었지만 깨지지 않았습니다!"
            else:
                # 실패
                game_data["state"][row][col] = 2
                game_data["fail_count"] += 1
                result_msg += "❌ 실패! 빈 곳을 클릭했습니다!"
        
        game_data["last_dice_result"] = f"{dice_roll}/{max_dice}"
        
        # 게임 종료 체크
        if game_data["correct_count"] >= game_data["correct_cells"]:
            game_data["completed"] = True
            result_msg += "\n🎉 완성! 축하합니다!"
        elif game_data["fail_count"] >= self.max_fails:
            game_data["failed"] = True
            result_msg += "\n💔 게임 오버! 실패 횟수를 초과했습니다."
        elif game_data["clicks"] >= game_data["max_clicks"]:
            game_data["failed"] = True
            result_msg += "\n💔 게임 오버! 클릭 횟수를 초과했습니다."
        
        return True, result_msg
    
    def create_final_grid_embed(self, game_data: dict) -> discord.Embed:
        """최종 결과 그리드 (정답 공개)"""
        # 그리드 생성
        grid_str = ""
        for i in range(5):
            for j in range(5):
                state = game_data["state"][i][j]
                pattern = game_data["pattern"][i][j]
                
                if state == 1:
                    grid_str += "🟦"  # 맞춘 정답
                elif state == 2 and pattern == 1:
                    grid_str += "🟨"  # 못 맞춘 정답
                elif state == 2:
                    grid_str += "🟥"  # 틀린 곳
                elif pattern == 1:
                    grid_str += "⬜"  # 시도하지 않은 정답
                else:
                    grid_str += "⬛"  # 빈 공간
            grid_str += "\n"
        
        embed = discord.Embed(
            title=f"🍪 정답: {game_data['shape'].value[1]} {game_data['shape'].value[0]}",
            description=grid_str,
            color=discord.Color.green() if game_data["completed"] else discord.Color.red()
        )
        
        embed.add_field(
            name="범례",
            value="🟦 맞춘 곳\n🟨 못 맞춘 정답\n⬜ 시도하지 않은 정답\n🟥 틀린 곳",
            inline=False
        )
        
        return embed
    
    async def end_game(self, channel_id: int, reason: str = ""):
        """게임 종료 - 보상 로직 제거"""
        game_data = self.active_games.get(channel_id)
        if not game_data or game_data.get("ended"):
            return
        
        game_data["ended"] = True
        player = game_data["player"]
        elapsed_time = int(time.time() - game_data["start_time"])
        
        # 점수 계산
        base_score = game_data["correct_count"] * 100
        time_bonus = max(0, 90 - elapsed_time) * 2  # 빨리 끝낼수록 보너스
        accuracy_bonus = int((game_data["correct_count"] / game_data["clicks"]) * 100) if game_data["clicks"] > 0 else 0
        total_score = base_score + time_bonus + accuracy_bonus
        
        # 성공/실패 판정
        if game_data["completed"]:
            title = "🎉 달고나 완성!"
            color = discord.Color.green()
        else:
            title = "💔 달고나 실패..."
            color = discord.Color.red()
        
        embed = discord.Embed(
            title=title,
            description=f"{reason}" if reason else "",
            color=color
        )
        
        # 통계
        embed.add_field(
            name="게임 통계",
            value=f"정답: {game_data['correct_count']}/{game_data['correct_cells']}개\n"
                  f"실패: {game_data['fail_count']}회\n"
                  f"총 클릭: {game_data['clicks']}회\n"
                  f"총 점수: {total_score}점",
            inline=False
        )
        
        # 최종 모양 공개
        final_embed = self.create_final_grid_embed(game_data)
        
        # 메시지 업데이트
        try:
            await game_data["message"].edit(embeds=[embed, final_embed], view=None)
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")
        
        # 게임 데이터 정리
        del self.active_games[channel_id]


class DalgonaView(discord.ui.View):
    def __init__(self, game: DalgonaGame, channel_id: int):
        super().__init__(timeout=90)
        self.game = game
        self.channel_id = channel_id
        
        # 5x5 버튼 그리드 생성
        for i in range(5):
            for j in range(5):
                button = DalgonaButton(i, j)
                self.add_item(button)

class DalgonaButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="\u200b",  # 보이지 않는 문자
            row=row
        )
        self.row = row
        self.col = col
    
    async def callback(self, interaction: discord.Interaction):
        view: DalgonaView = self.view
        game_data = view.game.active_games.get(view.channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "게임이 종료되었습니다.",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game_data["player"].id:
            await interaction.response.send_message(
                "다른 사람의 게임입니다!",
                ephemeral=True
            )
            return
        
        # 클릭 처리
        success, message = view.game.check_click(view.channel_id, self.row, self.col)
        
        if game_data["completed"] or game_data["failed"]:
            # 게임 종료
            embed = view.game.create_grid_embed(view.channel_id)
            embed.set_footer(text=message)
            await interaction.response.edit_message(embed=embed, view=None)
            await view.game.end_game(view.channel_id, reason=message if game_data["failed"] else "")
            view.stop()
        else:
            # 계속 진행
            embed = view.game.create_grid_embed(view.channel_id)
            embed.set_footer(text=message)
            await interaction.response.edit_message(embed=embed)

# 전역 게임 인스턴스
dalgona_game = DalgonaGame()

def get_dalgona_game():
    return dalgona_game