# snowman.py
import discord
import asyncio
import random
import json
import os
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GamePhase(Enum):
    ROLLING = "굴리기"
    STACKING = "쌓기"
    FINISHED = "완료"

class Direction(Enum):
    UP = (-1, 0)
    DOWN = (1, 0)
    LEFT = (0, -1)
    RIGHT = (0, 1)

@dataclass
class SnowBall:
    size: int
    position: Tuple[int, int]  # 쌓기 단계에서의 위치 (x좌표)
    
@dataclass
class LeaderboardEntry:
    user_id: int
    username: str
    score: int
    height: int
    timestamp: datetime

class SnowmanControlView(discord.ui.View):
    """눈사람 게임 조작 버튼"""
    def __init__(self, game, channel_id):
        super().__init__(timeout=300)  # 5분 타임아웃
        self.game = game
        self.channel_id = channel_id
    
    @discord.ui.button(emoji="⬆️", style=discord.ButtonStyle.secondary, row=0)
    async def up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_user(interaction):
            await self.game._handle_button(self.channel_id, "⬆️")
            await interaction.response.defer()
    
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_user(interaction):
            await self.game._handle_button(self.channel_id, "⬅️")
            await interaction.response.defer()
    
    @discord.ui.button(emoji="🔴", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_user(interaction):
            await self.game._handle_button(self.channel_id, "🔴")
            await interaction.response.defer()
    
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_user(interaction):
            await self.game._handle_button(self.channel_id, "➡️")
            await interaction.response.defer()
    
    @discord.ui.button(emoji="⬇️", style=discord.ButtonStyle.secondary, row=2)
    async def down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_user(interaction):
            await self.game._handle_button(self.channel_id, "⬇️")
            await interaction.response.defer()
    
    async def _check_user(self, interaction: discord.Interaction) -> bool:
        """사용자 권한 확인"""
        game_data = self.game.active_games.get(self.channel_id)
        if not game_data:
            await interaction.response.send_message("게임이 종료되었습니다.", ephemeral=True)
            return False
        
        if interaction.user.id != game_data["user"].id:
            await interaction.response.send_message("게임 참가자만 조작할 수 있습니다.", ephemeral=True)
            return False
        
        return True
    
    async def on_timeout(self):
        """타임아웃 시 게임 종료"""
        if self.channel_id in self.game.active_games:
            await self.game._end_game(self.channel_id)

class SnowmanGame:
    def __init__(self):
        self.active_games = {}
        self.leaderboard_file = "snowman_leaderboard.json"
        
        # 게임 설정
        self.FIELD_SIZE = 10
        self.OBSTACLE_COUNT = 6
        self.MAX_FAILURES = 3
        
        # 쌓기 단계 설정
        self.STACK_WIDTH = 15  # 쌓기 바의 너비
        self.MOVE_SPEED = 0.5  # 검정 타일 이동 속도
        self.STABILITY_THRESHOLD = 5  # 안정성 임계값 (5로 증가)
    
    async def start_game(self, interaction: discord.Interaction):
        """게임 시작"""
        user_id = interaction.user.id
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 눈사람 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        # 게임 데이터 초기화
        game_data = {
            "user": interaction.user,
            "phase": GamePhase.ROLLING,
            "field": self._create_field(),
            "position": (5, 5),  # 시작 위치 (중앙)
            "direction": Direction.RIGHT,
            "trail": [(5, 5)],  # 지나온 길
            "snowball_size": 1,
            "failures": 0,
            "snowballs": [],  # 완성된 눈공들
            "current_height": 0,
            "stacking_position": 7,  # 쌓기 단계에서 움직이는 위치
            "stacking_direction": 1,  # 1: 오른쪽, -1: 왼쪽
            "base_positions": [],  # 각 층의 눈공 위치들
            "stability": 0,  # 눈사람 안정성
            "moving": True,
            "view": None  # View 객체 저장
        }
        
        self.active_games[channel_id] = game_data
        
        # 조작 버튼 뷰 생성
        view = SnowmanControlView(self, channel_id)
        game_data["view"] = view
        
        # 첫 화면 표시
        embed = self._create_embed(game_data)
        await interaction.response.send_message(embed=embed, view=view)
        
        # 메시지 가져오기
        message = await interaction.original_response()
        game_data["message"] = message
        
        # 이동 태스크 시작
        game_data["move_task"] = asyncio.create_task(self._auto_move(channel_id))
        
        logger.info(f"Snowman game started in channel {channel_id} by user {user_id}")
    
    async def start_game_direct(self, channel, user):
        """채널에 직접 게임 시작 (defer된 인터랙션용)"""
        channel_id = channel.id
        
        if channel_id in self.active_games:
            await channel.send("이미 진행 중인 눈사람 게임이 있습니다!")
            return
        
        # 게임 데이터 초기화
        game_data = {
            "user": user,
            "phase": GamePhase.ROLLING,
            "field": self._create_field(),
            "position": (5, 5),
            "direction": Direction.RIGHT,
            "trail": [(5, 5)],
            "snowball_size": 1,
            "failures": 0,
            "snowballs": [],
            "current_height": 0,
            "stacking_position": 7,
            "stacking_direction": 1,
            "base_positions": [],
            "stability": 0,
            "moving": True,
            "view": None
        }
        
        self.active_games[channel_id] = game_data
        
        # 조작 버튼 뷰 생성
        view = SnowmanControlView(self, channel_id)
        game_data["view"] = view
        
        # 첫 화면 표시
        embed = self._create_embed(game_data)
        message = await channel.send(embed=embed, view=view)
        game_data["message"] = message
        
        # 이동 태스크 시작
        game_data["move_task"] = asyncio.create_task(self._auto_move(channel_id))
        
        logger.info(f"Snowman game started directly in channel {channel_id} by user {user.id}")
    
    def _create_field(self) -> List[List[str]]:
        """게임 필드 생성"""
        # 모든 칸을 눈(⚪)으로 채움
        field = [["⚪" for _ in range(self.FIELD_SIZE)] for _ in range(self.FIELD_SIZE)]
        
        # 장애물 배치
        obstacles_placed = 0
        while obstacles_placed < self.OBSTACLE_COUNT:
            x, y = random.randint(0, self.FIELD_SIZE-1), random.randint(0, self.FIELD_SIZE-1)
            
            # 시작 위치(5,5) 주변은 피함
            if abs(x - 5) <= 1 and abs(y - 5) <= 1:
                continue
            
            if field[x][y] == "⚪":
                field[x][y] = "🌲"  # 나무 장애물
                obstacles_placed += 1
        
        return field
    
    def _create_embed(self, game_data) -> discord.Embed:
        """게임 화면 임베드 생성"""
        if game_data["phase"] == GamePhase.ROLLING:
            return self._create_rolling_embed(game_data)
        elif game_data["phase"] == GamePhase.STACKING:
            return self._create_stacking_embed(game_data)
        else:
            return self._create_result_embed(game_data)
    
    def _create_rolling_embed(self, game_data) -> discord.Embed:
        """굴리기 단계 임베드"""
        embed = discord.Embed(
            title="❄️ 눈사람 만들기 - 눈 굴리기",
            description="버튼으로 눈을 굴려 크게 만들어보세요!",
            color=discord.Color.blue()
        )
        
        # 필드 표시
        field_str = ""
        pos_x, pos_y = game_data["position"]
        
        for i in range(self.FIELD_SIZE):
            row = ""
            for j in range(self.FIELD_SIZE):
                if (i, j) == (pos_x, pos_y):
                    row += "🔵"  # 플레이어 위치
                elif (i, j) in game_data["trail"]:
                    row += "❄️"  # 지나온 길
                else:
                    row += game_data["field"][i][j]
            field_str += row + "\n"
        
        embed.add_field(
            name="게임 필드",
            value=f"```\n{field_str}```",
            inline=False
        )
        
        # 게임 정보
        info = f"눈공 크기: **{game_data['snowball_size']}**\n"
        info += f"현재 높이: **{game_data['current_height']}층**\n"
        info += f"안정성: {'🟢' if game_data['stability'] < 5 else '🟡' if game_data['stability'] < 12 else '🔴'}\n"
        if game_data["snowballs"]:
            last_ball = game_data["snowballs"][-1]
            info += f"마지막 눈공: 크기 {last_ball.size}"
        
        embed.add_field(
            name="상태",
            value=info,
            inline=True
        )
        
        # 조작 안내
        controls = "아래 버튼을 클릭하여 조작하세요!\n"
        controls += "⬆️⬇️⬅️➡️: 방향 변경\n"
        controls += "🔴: 그만 굴리기 / 눈공 배치\n\n"
        
        if game_data["current_height"] == 0:
            controls += "💡 첫 눈공은 어디든 배치 가능!"
        else:
            controls += "⚠️ 아래층 근처에만 배치 가능\n"
            controls += "📐 큰 눈공일수록 넓은 허용범위"
        
        embed.add_field(
            name="조작법",
            value=controls,
            inline=True
        )
        
        # 실패 횟수
        embed.add_field(
            name="실패 횟수",
            value=f"{game_data['failures']}/{self.MAX_FAILURES}",
            inline=True
        )
        
        return embed
    
    def _create_stacking_embed(self, game_data) -> discord.Embed:
        """쌓기 단계 임베드"""
        embed = discord.Embed(
            title="🏗️ 눈사람 만들기 - 쌓아올리기",
            description=f"크기 {game_data['snowball_size']}의 눈공을 쌓아올리세요!",
            color=discord.Color.green()
        )
        
        # 쌓기 바 표시
        bar = ["⬜"] * self.STACK_WIDTH
        bar[game_data["stacking_position"]] = "⬛"
        
        # 바로 직전 층(마지막 층)의 위치만 표시
        if game_data["current_height"] > 0 and game_data["base_positions"]:
            last_layer_positions = game_data["base_positions"][-1]  # 마지막 층만
            for pos in last_layer_positions:
                if 0 <= pos < self.STACK_WIDTH:
                    if bar[pos] == "⬜":
                        bar[pos] = "🔘"  # 바로 아래층
                    else:
                        bar[pos] = "🔴"  # 현재 위치와 겹침
        
        # 허용 범위 표시 (바로 전 층 기준)
        if game_data["current_height"] > 0 and game_data["snowballs"]:
            last_snowball = game_data["snowballs"][-1]  # 바로 전 층 눈공
            last_positions = game_data["base_positions"][-1]
            allowed_range = max(1, last_snowball.size // 3)
            
            # 허용 범위 표시 (초록색)
            for base_pos in last_positions:
                for offset in range(-allowed_range, allowed_range + 1):
                    pos = base_pos + offset
                    if 0 <= pos < self.STACK_WIDTH and bar[pos] == "⬜":
                        bar[pos] = "🟢"  # 배치 가능 영역
        
        bar_str = "".join(bar)
        
        # 범례 추가 (더 명확하게)
        legend = ""
        if game_data["current_height"] > 0:
            legend = "\n🟢: 배치 가능 | 🔘: 바로 아래층 | ⬛: 현재 위치"
        else:
            legend = "\n⬛: 현재 위치 (첫 눈공은 어디든 가능!)"
        
        embed.add_field(
            name="타이밍 바",
            value=f"`{bar_str}`\n🔴 버튼을 눌러 눈공을 놓으세요!{legend}",
            inline=False
        )
        
        # 눈사람 상태 (바로 전 층 정보 강조)
        info = f"현재 높이: **{game_data['current_height']}층**\n"
        info += f"놓을 눈공 크기: **{game_data['snowball_size']}**\n"
        info += f"안정성: {'🟢' if game_data['stability'] < 5 else '🟡' if game_data['stability'] < 12 else '🔴'}"
        
        # 배치 조건 안내 (바로 전 층 기준)
        if game_data["current_height"] > 0 and game_data["snowballs"]:
            last_snowball = game_data["snowballs"][-1]
            allowed_range = max(1, last_snowball.size // 3)
            info += f"\n📏 허용 범위: ±{allowed_range}"
            info += f"\n🔘 기준층({game_data['current_height']}층): 크기 {last_snowball.size}"
        
        embed.add_field(
            name="상태",
            value=info,
            inline=False
        )
        
        # 안정성 팁 (더 구체적으로)
        if game_data["current_height"] > 0:
            last_snowball = game_data["snowballs"][-1]
            current_size = game_data["snowball_size"]
            
            if current_size > last_snowball.size:
                tip = f"⚠️ **주의**: 현재 눈공({current_size})이 아래층({last_snowball.size})보다 큽니다!\n불안정해질 수 있어요."
                tip_color = "위험"
            elif current_size < last_snowball.size:
                tip = f"✅ **좋음**: 현재 눈공({current_size})이 아래층({last_snowball.size})보다 작습니다!\n안정적이에요."
                tip_color = "안전"
            else:
                tip = f"➖ **보통**: 현재 눈공과 아래층이 같은 크기입니다."
                tip_color = "보통"
            
            embed.add_field(
                name=f"💡 안정성 예측",
                value=tip,
                inline=False
            )
        
        return embed
    
    def _create_result_embed(self, game_data) -> discord.Embed:
        """결과 화면 임베드"""
        embed = discord.Embed(
            title="🎉 눈사람 완성!",
            description=f"{game_data['user'].display_name}님의 눈사람",
            color=discord.Color.gold()
        )
        
        # 최종 점수 계산
        total_score = sum(ball.size for ball in game_data["snowballs"]) * game_data["current_height"]
        
        embed.add_field(
            name="최종 결과",
            value=f"높이: **{game_data['current_height']}층**\n"
                  f"총 점수: **{total_score}점**\n"
                  f"최종 안정성: {'🟢' if game_data['stability'] < 5 else '🟡' if game_data['stability'] < 12 else '🔴'}",
            inline=False
        )
        
        # 사용된 눈공들 (상세 정보)
        if game_data["snowballs"]:
            balls_info = []
            total_size = 0
            for i, ball in enumerate(game_data["snowballs"]):
                total_size += ball.size
                # 안정성 표시 (2층부터)
                stability_icon = ""
                if i > 0:  # 첫 번째 층이 아닌 경우
                    prev_ball = game_data["snowballs"][i-1]
                    if ball.size > prev_ball.size:
                        stability_icon = " ⚠️"  # 불안정
                    elif ball.size < prev_ball.size:
                        stability_icon = " ✅"  # 안정
                    else:
                        stability_icon = " ➖"  # 보통
                
                balls_info.append(f"{i+1}층: 크기 {ball.size}{stability_icon}")
            
            balls_text = "\n".join(balls_info)
            embed.add_field(
                name="눈공 구성",
                value=balls_text,
                inline=True
            )
            
            # 통계 정보
            avg_size = total_size / len(game_data["snowballs"])
            max_size = max(ball.size for ball in game_data["snowballs"])
            min_size = min(ball.size for ball in game_data["snowballs"])
            
            stats_text = f"총 눈덩이: {total_size}\n"
            stats_text += f"평균 크기: {avg_size:.1f}\n"
            stats_text += f"최대/최소: {max_size}/{min_size}"
            
            embed.add_field(
                name="통계",
                value=stats_text,
                inline=True
            )
        
        # 성취도 평가
        if game_data["current_height"] >= 5:
            achievement = "🏆 눈사람 마스터!"
        elif game_data["current_height"] >= 3:
            achievement = "🥉 숙련된 눈사람 건축가"
        elif game_data["current_height"] >= 2:
            achievement = "🥈 눈사람 건축 입문자"
        else:
            achievement = "🥉 첫 걸음"
        
        embed.add_field(
            name="성취도",
            value=achievement,
            inline=False
        )
        
        return embed
    
    async def _handle_button(self, channel_id: int, button: str):
        """버튼 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        logger.info(f"Button pressed: {button} in channel {channel_id}, phase: {game_data['phase']}")
        
        if game_data["phase"] == GamePhase.ROLLING:
            await self._handle_rolling_button(channel_id, button)
        elif game_data["phase"] == GamePhase.STACKING:
            await self._handle_stacking_button(channel_id, button)
    
    async def _handle_rolling_button(self, channel_id: int, button: str):
        """굴리기 단계 버튼 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        if button == "🔴":
            # 그만 굴리기 - 쌓기 단계로 전환
            logger.info(f"Snowman: User switching to stacking phase in channel {channel_id}")
            await self._switch_to_stacking(channel_id)
        else:
            # 방향 변경
            direction_map = {
                "⬆️": Direction.UP,
                "⬇️": Direction.DOWN,
                "⬅️": Direction.LEFT,
                "➡️": Direction.RIGHT
            }
            
            if button in direction_map:
                old_direction = game_data["direction"]
                game_data["direction"] = direction_map[button]
                logger.info(f"Snowman: Direction changed from {old_direction} to {game_data['direction']} in channel {channel_id}")
    
    async def _handle_stacking_button(self, channel_id: int, button: str):
        """쌓기 단계 버튼 처리"""
        if button == "🔴":
            logger.info(f"Snowman: User placing snowball in channel {channel_id}")
            await self._place_snowball(channel_id)
    
    async def _auto_move(self, channel_id: int):
        """자동 이동 처리"""
        try:
            while channel_id in self.active_games:
                game_data = self.active_games.get(channel_id)
                if not game_data:
                    break
                
                try:
                    if game_data["phase"] == GamePhase.ROLLING and game_data.get("moving", False):
                        await self._move_player(channel_id)
                    elif game_data["phase"] == GamePhase.STACKING:
                        await self._move_stacking_cursor(channel_id)
                    
                    await asyncio.sleep(0.8 if game_data["phase"] == GamePhase.ROLLING else 0.3)
                    
                except Exception as e:
                    logger.error(f"Auto move error: {e}")
                    break
        except asyncio.CancelledError:
            logger.info(f"Auto move task cancelled for channel {channel_id}")
        except Exception as e:
            logger.error(f"Auto move task error: {e}")
    
    async def _move_player(self, channel_id: int):
        """플레이어 이동"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        dx, dy = game_data["direction"].value
        current_x, current_y = game_data["position"]
        new_x, new_y = current_x + dx, current_y + dy
        
        # 경계 체크
        if not (0 <= new_x < self.FIELD_SIZE and 0 <= new_y < self.FIELD_SIZE):
            await self._handle_collision(channel_id)
            return
        
        # 장애물 체크
        if game_data["field"][new_x][new_y] == "🌲":
            await self._handle_collision(channel_id)
            return
        
        # 이미 지나온 길 체크
        if (new_x, new_y) in game_data["trail"]:
            await self._handle_collision(channel_id)
            return
        
        # 이동 성공
        game_data["position"] = (new_x, new_y)
        game_data["trail"].append((new_x, new_y))
        
        # 눈공 크기 증가 (눈을 굴림)
        if game_data["field"][new_x][new_y] == "⚪":
            game_data["snowball_size"] += 1
        
        # 화면 업데이트
        await self._update_display(channel_id)
    
    async def _move_stacking_cursor(self, channel_id: int):
        """쌓기 단계 커서 이동"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        game_data["stacking_position"] += game_data["stacking_direction"]
        
        # 경계에서 방향 전환
        if game_data["stacking_position"] <= 0:
            game_data["stacking_position"] = 0
            game_data["stacking_direction"] = 1
        elif game_data["stacking_position"] >= self.STACK_WIDTH - 1:
            game_data["stacking_position"] = self.STACK_WIDTH - 1
            game_data["stacking_direction"] = -1
        
        # 화면 업데이트
        await self._update_display(channel_id)
    
    async def _handle_collision(self, channel_id: int):
        """충돌 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
            
        game_data["failures"] += 1
        
        if game_data["failures"] >= self.MAX_FAILURES:
            # 게임 오버
            await self._end_game(channel_id)
        else:
            # 다시 시작
            game_data["field"] = self._create_field()
            game_data["position"] = (5, 5)
            game_data["direction"] = Direction.RIGHT
            game_data["trail"] = [(5, 5)]
            game_data["snowball_size"] = 1
            
            await self._update_display(channel_id)
    
    async def _switch_to_stacking(self, channel_id: int):
        """쌓기 단계로 전환"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        game_data["phase"] = GamePhase.STACKING
        game_data["moving"] = False  # 자동 이동 정지
        
        await self._update_display(channel_id)
    
    async def _place_snowball(self, channel_id: int):
        """눈공 배치"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
            
        current_pos = game_data["stacking_position"]
        current_size = game_data["snowball_size"]
        
        # 첫 번째 눈공은 아무곳에나 배치 가능
        if game_data["current_height"] == 0:
            success = True
        else:
            # 두 번째 눈공부터는 이전 눈공과의 위치 관계 확인
            success = await self._check_snowball_placement(game_data, current_pos, current_size)
        
        if not success:
            # 눈공이 떨어짐 - 다시 굴리기로 돌아가기
            await self._drop_snowball(channel_id)
            return
        
        # 눈공 배치 성공 - 눈공 객체 생성
        snowball = SnowBall(
            size=current_size,
            position=(current_pos,)
        )
        game_data["snowballs"].append(snowball)
        game_data["current_height"] += 1
        
        # 눈공 크기에 따른 차지 위치 계산
        ball_positions = self._calculate_ball_positions(current_pos, current_size)
        game_data["base_positions"].append(ball_positions)
        
        # 층별 크기 안정성 체크
        stability_penalty = self._check_size_stability(game_data)
        game_data["stability"] += stability_penalty
        
        # 안정성이 너무 떨어지면 무너짐
        if game_data["stability"] >= self.STABILITY_THRESHOLD * 4:  # 더 관대하게 조정 (20)
            await self._collapse_snowman(channel_id)
            return
        
        # 다음 눈공 준비
        game_data["field"] = self._create_field()
        game_data["position"] = (5, 5)
        game_data["direction"] = Direction.RIGHT
        game_data["trail"] = [(5, 5)]
        game_data["snowball_size"] = 1
        game_data["phase"] = GamePhase.ROLLING
        game_data["moving"] = True
        
        await self._update_display(channel_id)
    
    async def _check_snowball_placement(self, game_data, current_pos: int, current_size: int) -> bool:
        """눈공 배치 가능 여부 확인"""
        if not game_data["base_positions"]:
            return True  # 첫 번째 눈공
        
        # 바로 아래층 눈공들의 위치 가져오기
        last_positions = game_data["base_positions"][-1]
        if not last_positions:
            return True
        
        # 현재 눈공이 차지할 범위 계산
        current_range = self._calculate_ball_positions(current_pos, current_size)
        
        # 아래층 눈공의 크기로 허용 범위 계산
        last_snowball = game_data["snowballs"][-1] if game_data["snowballs"] else None
        if not last_snowball:
            return True
        
        # 허용 범위: 아래층 눈공 크기에 비례 (크기가 클수록 넓은 범위)
        allowed_range = max(1, last_snowball.size // 3)  # 최소 1, 최대 눈공크기/3
        
        # 현재 눈공의 모든 위치가 허용 범위 내에 있는지 확인
        for pos in current_range:
            # 가장 가까운 아래층 눈공과의 거리
            min_distance = min(abs(pos - base_pos) for base_pos in last_positions)
            
            if min_distance > allowed_range:
                return False  # 너무 멀리 떨어져 있음
        
        return True
    
    def _calculate_ball_positions(self, center_pos: int, size: int) -> List[int]:
        """눈공 크기에 따른 차지 위치들 계산"""
        positions = []
        
        # 눈공 크기에 따라 차지하는 범위 결정
        width = max(1, min(3, size // 5))  # 크기 5당 너비 1, 최대 3
        
        for i in range(width):
            pos = center_pos + i - width // 2
            if 0 <= pos < self.STACK_WIDTH:
                positions.append(pos)
        
        return positions
    
    def _check_size_stability(self, game_data) -> int:
        """층별 크기에 따른 안정성 체크"""
        if len(game_data["snowballs"]) < 2:
            return 0  # 첫 번째 눈공은 체크 안함
        
        current_snowball = game_data["snowballs"][-1]  # 방금 놓은 눈공
        penalty = 0
        
        # 아래층들과 크기 비교
        for i in range(len(game_data["snowballs"]) - 1):
            below_snowball = game_data["snowballs"][i]
            
            # 현재 눈공이 아래층보다 큰 경우 불안정
            if current_snowball.size > below_snowball.size:
                # 크기 차이가 클수록 더 큰 페널티
                size_diff = current_snowball.size - below_snowball.size
                layer_diff = len(game_data["snowballs"]) - 1 - i  # 층수 차이
                penalty += size_diff * layer_diff // 5  # 차이와 거리에 비례
        
        return penalty
    
    async def _drop_snowball(self, channel_id: int):
        """눈공 떨어뜨리기 - 다시 굴리기로 돌아가기"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        # 떨어뜨린 메시지 표시를 위해 임시로 상태 업데이트
        embed = discord.Embed(
            title="💥 눈공이 떨어졌습니다!",
            description=f"크기 {game_data['snowball_size']}의 눈공이 잘못된 위치에 떨어졌습니다.\n"
                       f"다시 눈을 굴려보세요!",
            color=discord.Color.red()
        )
        
        view = game_data.get("view")
        if game_data.get("message"):
            try:
                await game_data["message"].edit(embed=embed, view=view)
            except:
                pass
        
        # 2초 후 다시 굴리기로 전환
        await asyncio.sleep(2)
        
        # 굴리기 단계로 리셋
        game_data["field"] = self._create_field()
        game_data["position"] = (5, 5)
        game_data["direction"] = Direction.RIGHT
        game_data["trail"] = [(5, 5)]
        game_data["snowball_size"] = 1
        game_data["phase"] = GamePhase.ROLLING
        game_data["moving"] = True
        
        await self._update_display(channel_id)
    
    async def _collapse_snowman(self, channel_id: int):
        """눈사람 무너짐 - 최고 높이 기록하고 게임 종료"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        # 무너지는 메시지 표시
        embed = discord.Embed(
            title="💥 눈사람이 무너졌습니다!",
            description=f"안정성이 너무 떨어져 눈사람이 무너졌습니다.\n"
                       f"최고 높이: **{game_data['current_height']}층**",
            color=discord.Color.orange()
        )
        
        view = game_data.get("view")
        if game_data.get("message"):
            try:
                await game_data["message"].edit(embed=embed, view=view)
            except:
                pass
        
        # 3초 후 게임 종료
        await asyncio.sleep(3)
        await self._end_game(channel_id)
    
    async def _update_display(self, channel_id: int):
        """화면 업데이트"""
        game_data = self.active_games.get(channel_id)
        if not game_data or not game_data.get("message"):
            return
        
        try:
            embed = self._create_embed(game_data)
            view = game_data.get("view")
            await game_data["message"].edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Display update error: {e}")
    
    async def _end_game(self, channel_id: int):
        """게임 종료"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        # 모든 태스크 정리
        tasks_to_cancel = []
        if "move_task" in game_data and game_data["move_task"]:
            tasks_to_cancel.append(game_data["move_task"])
        
        # 태스크 취소
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Task cleanup error: {e}")
        
        # View 비활성화
        if game_data.get("view"):
            game_data["view"].stop()
        
        game_data["phase"] = GamePhase.FINISHED
        
        # 최종 점수 계산
        total_score = sum(ball.size for ball in game_data["snowballs"]) * game_data["current_height"]
        
        # 리더보드 업데이트
        guild_id = game_data["message"].guild.id if game_data.get("message") and game_data["message"].guild else 0
        await self._update_leaderboard(guild_id, game_data["user"], total_score, game_data["current_height"])
        
        # 최종 결과 표시
        result_embed = self._create_result_embed(game_data)
        
        # 리더보드 추가
        leaderboard_text = await self._get_leaderboard_text(guild_id, game_data["user"].id)
        if leaderboard_text:
            result_embed.add_field(
                name="🏆 서버 리더보드",
                value=leaderboard_text,
                inline=False
            )
        
        # 메시지 업데이트 (View 제거)
        if game_data.get("message"):
            try:
                await game_data["message"].edit(embed=result_embed, view=None)
            except Exception as e:
                logger.error(f"Failed to edit final message: {e}")
        
        # 게임 데이터 정리 (가장 중요!)
        try:
            del self.active_games[channel_id]
            logger.info(f"Snowman game cleaned up for channel {channel_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup game data: {e}")
    
    async def _update_leaderboard(self, guild_id: int, user: discord.Member, score: int, height: int):
        """리더보드 업데이트"""
        leaderboard = self._load_leaderboard()
        
        guild_key = str(guild_id)
        if guild_key not in leaderboard:
            leaderboard[guild_key] = {}
        
        user_key = str(user.id)
        current_entry = leaderboard[guild_key].get(user_key)
        
        # 최고 점수만 저장
        if not current_entry or score > current_entry["score"]:
            leaderboard[guild_key][user_key] = {
                "username": user.display_name,
                "score": score,
                "height": height,
                "timestamp": datetime.now().isoformat()
            }
            
            self._save_leaderboard(leaderboard)
    
    async def _get_leaderboard_text(self, guild_id: int, user_id: int) -> str:
        """리더보드 텍스트 생성"""
        leaderboard = self._load_leaderboard()
        guild_key = str(guild_id)
        
        if guild_key not in leaderboard:
            return "아직 기록이 없습니다."
        
        # 점수순으로 정렬
        entries = []
        for uid, data in leaderboard[guild_key].items():
            entries.append((int(uid), data["username"], data["score"], data["height"]))
        
        entries.sort(key=lambda x: x[2], reverse=True)  # 점수순 정렬
        
        if not entries:
            return "아직 기록이 없습니다."
        
        # 상위 5명
        result = []
        for i, (uid, username, score, height) in enumerate(entries[:5]):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
            result.append(f"{medal} {username}: {score}점 ({height}층)")
        
        # 현재 유저 순위
        user_rank = None
        for i, (uid, username, score, height) in enumerate(entries):
            if uid == user_id:
                user_rank = i + 1
                break
        
        if user_rank and user_rank > 5:
            result.append(f"...")
            result.append(f"{user_rank}위: 당신의 기록")
        
        return "\n".join(result)
    
    def _load_leaderboard(self) -> Dict:
        """리더보드 로드"""
        if os.path.exists(self.leaderboard_file):
            try:
                with open(self.leaderboard_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load leaderboard: {e}")
        return {}
    
    def _save_leaderboard(self, leaderboard: Dict):
        """리더보드 저장"""
        try:
            with open(self.leaderboard_file, 'w', encoding='utf-8') as f:
                json.dump(leaderboard, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save leaderboard: {e}")

# 전역 게임 인스턴스
snowman_game = SnowmanGame()

def get_snowman_game():
    return snowman_game

def set_snowman_bot(bot):
    """봇 인스턴스 설정 (호환성을 위한 빈 함수)"""
    pass  # 버튼 방식에서는 봇 인스턴스가 필요없음