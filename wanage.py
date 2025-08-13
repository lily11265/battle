# wanage.py - 기괴한 요소가 추가된 링 던지기 버전
import discord
from discord import app_commands
import asyncio
import random
import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from debug_config import debug_log, debug_config
import gspread
from google.oauth2.service_account import Credentials
from battle_utils import update_nickname_health  # 체력 업데이트 함수 import

logger = logging.getLogger(__name__)

@dataclass
class Target:
    """목표물 정보"""
    name: str
    emoji: str
    radius: float  # 실제 크기
    boundary_radius: float  # 바운더리 크기
    points: int
    x: int
    y: int
    hit: bool = False  # 맞춘 여부
    is_alive: bool = False  # 살아있는 타겟 여부

@dataclass
class ThrownRing:
    """던진 링 정보"""
    x: int
    y: int
    hit: bool
    target_name: Optional[str] = None
    actual_landing: Optional[Tuple[int, int]] = None  # 실제 착지 위치 (바운더리 히트 시)

@dataclass
class ApproachingMonster:
    """접근하는 괴수"""
    name: str
    emoji: str = "👤"
    current_position: int = 10  # 시작 위치 (10에서 시작해서 0으로)
    speed: int = 1  # 매 턴마다 이동 거리
    grid_x: int = 5  # 그리드 X 좌표
    grid_y: int = 0  # 그리드 Y 좌표 (위에서 시작)

class WanageGame:
    def __init__(self):
        self.active_games = {}
        self.grid_size = 10
        self.throwing_position = (5, 9)  # 던지는 위치 (중앙 하단)
        
        # 일반 목표물 종류 (이름, 이모지, 실제크기, 점수)
        # 점수가 낮을수록 바운더리가 큼
        self.normal_target_types = [
            ("대나무", "🎋", 0.8, 50),    # 바운더리 2.0
            ("등롱", "🏮", 0.7, 100),     # 바운더리 1.5
            ("부채", "🎏", 0.6, 150),     # 바운더리 1.2
            ("방울", "🔔", 0.5, 200),     # 바운더리 1.0
            ("동전", "🪙", 0.4, 300)      # 바운더리 0.8
        ]
        
        # 살아있는 타겟 (가끔 나타남)
        self.alive_target_types = [
            ("깜빡이는 눈", "👁️", 0.6, 0),  # 점수 없음
            ("비명 인형", "🪆", 0.7, 0),
            ("썩은 풍선", "🎈", 0.6, 0)
        ]
        
        # 러너 이름 목록 (괴수용)
        self.runner_names = [
            "아카시하지메", "펀처", "유진석", "휘슬", "배달기사", "페이",
            "로메즈아가레스", "레이나하트베인", "비비", "오카미나오하",
            "카라트에크", "토트", "처용", "멀플리시", "코발트윈드", "옥타",
            "베레니케", "안드라블랙", "봉고3호", "몰", "베니", "백야",
            "루치페르", "벨사이르드라켄리트", "불스", "퓨어메탈",
            "노단투", "라록", "아카이브", "베터", "메르쿠리",
            "마크-112", "스푸트니크2세", "이터니티", "커피머신"
        ]
        
        # 아이템 캐시
        self.item_cache = None
        self.cache_time = None
        self.cache_duration = 3600  # 1시간
    
    def calculate_boundary_radius(self, points: int) -> float:
        """바운더리 반경 계산"""
        if points == 0:  # 살아있는 타겟
            return 1.5
        elif points <= 50:
            return 2.0
        elif points <= 100:
            return 1.5
        elif points <= 150:
            return 1.2
        elif points <= 200:
            return 1.0
        else:
            return 0.8
    
    def calculate_landing_position(self, direction: float, power: float, 
                                 wind_strength: float, wind_direction: float,
                                 is_reversed: bool = False) -> Tuple[int, int, List[Tuple[int, int]]]:
        """착지 위치 계산 (좌우반전 포함) - 수정된 버전: 이동 경로도 반환"""
        # 좌우반전 효과
        if is_reversed:
            direction = 360 - direction
            if debug_config.debug_enabled:
                debug_log("WANAGE", f"Direction reversed: {360 - direction} -> {direction}")
        
        # 방향을 라디안으로 변환
        direction_rad = math.radians(direction)
        wind_rad = math.radians(wind_direction)
        
        # 이동 경로를 저장할 리스트
        path = []
        
        # 시작 위치
        current_x = float(self.throwing_position[0])
        current_y = float(self.throwing_position[1])
        
        # 방향 벡터 계산
        dx = math.sin(direction_rad)
        dy = -math.cos(direction_rad)
        
        # 바람 방향 벡터
        wind_dx = math.sin(wind_rad)
        wind_dy = math.cos(wind_rad)
        
        # 힘에 따른 이동 거리 (10씩 늘어날 때마다 한 칸)
        total_steps = int(power / 10)
        wind_steps = 0
        
        for step in range(total_steps):
            # 기본 이동 (한 칸씩)
            current_x += dx
            current_y += dy
            
            # 3칸 이동할 때마다 바람 효과 적용
            if (step + 1) % 3 == 0:
                wind_move = math.ceil(wind_strength)  # 바람 세기만큼 이동 (올림)
                for _ in range(wind_move):
                    current_x += wind_dx
                    current_y -= wind_dy  # y축은 반대
            
            # 현재 위치를 경로에 추가
            grid_x = int(round(current_x))
            grid_y = int(round(current_y))
            
            # 경계 체크
            grid_x = max(0, min(self.grid_size - 1, grid_x))
            grid_y = max(0, min(self.grid_size - 1, grid_y))
            
            path.append((grid_x, grid_y))
        
        # 최종 위치
        final_x = int(round(current_x))
        final_y = int(round(current_y))
        
        # 경계 처리
        final_x = max(0, min(self.grid_size - 1, final_x))
        final_y = max(0, min(self.grid_size - 1, final_y))
        
        return final_x, final_y, path
    
    async def _move_monster_task(self, channel_id: int):
        """괴수 자동 이동 태스크"""
        while channel_id in self.active_games:
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data.get("game_over") or game_data.get("battle_triggered"):
                break
            
            monster = game_data.get("approaching_monster")
            if not monster:
                break
            
            # 던지는 위치로 이동
            target_x, target_y = self.throwing_position
            
            # 현재 위치에서 목표 위치까지의 방향 계산
            dx = target_x - monster.grid_x
            dy = target_y - monster.grid_y
            
            # 한 번에 한 칸씩 이동
            if abs(dx) > abs(dy):
                # X축 우선 이동
                if dx > 0:
                    monster.grid_x += 1
                elif dx < 0:
                    monster.grid_x -= 1
            elif dy != 0:
                # Y축 이동
                if dy > 0:
                    monster.grid_y += 1
                elif dy < 0:
                    monster.grid_y -= 1
            
            # 거리 업데이트
            monster.current_position = abs(dx) + abs(dy)
            
            # 던지는 위치에 도달했는지 확인
            if monster.grid_x == target_x and monster.grid_y == target_y:
                # 전투 시작
                game_data["battle_triggered"] = True
                # 메시지 업데이트
                if "message" in game_data:
                    embed = self._create_game_embed(channel_id)
                    try:
                        await game_data["message"].edit(embed=embed)
                        await game_data["message"].channel.send(
                            f"👤 **{monster.name}이(가) 도착했다. 전투가 시작된다.**"
                        )
                        await self._trigger_monster_battle(game_data["message"].channel, game_data)
                        del self.active_games[channel_id]
                    except discord.errors.NotFound:
                        pass
                break
            
            # 게임 화면 업데이트
            if "message" in game_data:
                embed = self._create_game_embed(channel_id)
                try:
                    await game_data["message"].edit(embed=embed)
                except discord.errors.NotFound:
                    break
            
            # 5초 대기 (느리게 이동)
            await asyncio.sleep(5)
    
    def get_wind_direction_emoji(self, direction: float) -> str:
        """바람 방향 이모지"""
        if 337.5 <= direction or direction < 22.5:
            return "⬆️"
        elif 22.5 <= direction < 67.5:
            return "↗️"
        elif 67.5 <= direction < 112.5:
            return "➡️"
        elif 112.5 <= direction < 157.5:
            return "↘️"
        elif 157.5 <= direction < 202.5:
            return "⬇️"
        elif 202.5 <= direction < 247.5:
            return "↙️"
        elif 247.5 <= direction < 292.5:
            return "⬅️"
        elif 292.5 <= direction < 337.5:
            return "↖️"
        return "?"
    
    def _create_game_embed(self, channel_id: int) -> discord.Embed:
        """게임 화면 생성"""
        game_data = self.active_games[channel_id]
        
        # 안개 효과 확인
        is_foggy = game_data.get("fog_turns", 0) > 0
        
        # 그리드 생성
        grid = [["　"] * self.grid_size for _ in range(self.grid_size)]
        
        # 안개가 있으면 부분적으로만 보이게
        if is_foggy:
            visible_range = 2
            for y in range(self.grid_size):
                for x in range(self.grid_size):
                    dist = abs(x - self.throwing_position[0]) + abs(y - self.throwing_position[1])
                    if dist > visible_range:
                        grid[y][x] = "🌫️"
        
        # 눈 배치 (깜빡이는 눈을 맞춘 후)
        if game_data.get("eye_count", 0) > 0:
            # 랜덤한 위치에 눈 배치
            eye_positions = []
            for _ in range(min(game_data["eye_count"], 15)):  # 최대 15개
                x = random.randint(0, self.grid_size - 1)
                y = random.randint(0, self.grid_size - 1)
                if grid[y][x] == "　" and (x, y) != self.throwing_position:
                    eye_positions.append((x, y))
            
            for x, y in eye_positions:
                if grid[y][x] == "　":
                    grid[y][x] = "👁️"
        
        # 목표물 배치
        for target in game_data["targets"]:
            if not target.hit and (not is_foggy or grid[target.y][target.x] != "🌫️"):
                grid[target.y][target.x] = target.emoji
        
        # 던진 링 표시 (최근 3개만)
        for ring in game_data["thrown_rings"][-3:]:
            if 0 <= ring.y < self.grid_size and 0 <= ring.x < self.grid_size:
                if grid[ring.y][ring.x] == "　" or grid[ring.y][ring.x] == "🌫️":
                    grid[ring.y][ring.x] = "⭕" if ring.hit else "❌"
        
        # 괴수 표시 (그리드에 직접 표시)
        if game_data.get("approaching_monster"):
            monster = game_data["approaching_monster"]
            if 0 <= monster.grid_y < self.grid_size and 0 <= monster.grid_x < self.grid_size:
                # 안개가 있어도 괴수는 보이게
                if grid[monster.grid_y][monster.grid_x] in ["　", "🌫️"]:
                    grid[monster.grid_y][monster.grid_x] = monster.emoji
        
        # 던지는 위치를 더 눈에 띄게 표시
        grid[self.throwing_position[1]][self.throwing_position[0]] = "🏹"  # 활 이모지로 변경
        
        # 그리드 문자열 생성
        grid_str = "\n".join("".join(row) for row in grid)
        
        # 임베드 생성
        embed = discord.Embed(
            title="⭕ 와나게 (링 던지기)",
            description=f"```\n{grid_str}\n```",
            color=discord.Color.blue()
        )
        
        # 게임 정보
        embed.add_field(
            name="게임 정보",
            value=f"🎯 남은 링: {game_data['rings']}/10\n"
                  f"💰 점수: {game_data['score']}점\n"
                  f"💨 바람: {game_data['wind_strength']:.1f}m/s {self.get_wind_direction_emoji(game_data['wind_direction'])}",
            inline=True
        )
        
        # 남은 목표물
        active_targets = [t for t in game_data["targets"] if not t.hit and not t.is_alive]
        if active_targets:
            target_list = []
            for t in sorted(active_targets, key=lambda x: x.points, reverse=True):
                target_list.append(f"{t.emoji} {t.name}: {t.points}점")
            
            embed.add_field(
                name="목표물",
                value="\n".join(target_list[:3]),  # 상위 3개만
                inline=True
            )
        
        # 이상현상 표시
        effects = []
        if game_data.get("is_reversed", False):
            effects.append("🔄 좌우반전")
        if is_foggy:
            effects.append(f"🌫️ 안개 ({game_data['fog_turns']}턴)")
        
        if effects:
            embed.add_field(
                name="이상현상",
                value="\n".join(effects),
                inline=False
            )
        
        # 접근하는 괴수 (거리 바 제거 - 이제 그리드에 표시됨)
        if game_data.get("approaching_monster"):
            monster = game_data["approaching_monster"]
            embed.add_field(
                name=f"⚠️ {monster.name} 접근중!",
                value=f"거리: {monster.current_position}칸",
                inline=False
            )
        
        # 방향 가이드
        embed.add_field(
            name="방향 가이드 (🏹 = 던지는 위치)",
            value="0° = ↙️ 왼쪽 아래\n"
                  "45° = ↖️ 왼쪽 위\n"
                  "90° = ⬆️ 바로 위\n"
                  "135° = ↗️ 오른쪽 위\n"
                  "180° = ↘️ 오른쪽 아래",
            inline=False
        )
        
        # 마지막 던진 결과를 임베드 하단에 표시
        if game_data.get("last_throw_result"):
            embed.add_field(
                name="📊 마지막 던진 결과",
                value=game_data["last_throw_result"],
                inline=False
            )
        
        embed.set_footer(text="링을 던지려면 아래 버튼을 클릭하세요!")
        
        return embed

    def _create_grid_display(self, game_data: dict, is_foggy: bool = False) -> str:
        """그리드 디스플레이 생성"""
        grid = [["  " for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        
        # 던지는 위치 표시
        px, py = self.throwing_position
        grid[py][px] = "🙂"
        
        # 괴수 표시
        monster = game_data.get("approaching_monster")
        if monster and not game_data.get("battle_triggered"):
            if 0 <= monster.grid_x < self.grid_size and 0 <= monster.grid_y < self.grid_size:
                grid[monster.grid_y][monster.grid_x] = monster.emoji
        
        # 목표물 표시 (안개가 아닐 때만)
        if not is_foggy:
            for target in game_data["targets"]:
                if not target.hit and 0 <= target.x < self.grid_size and 0 <= target.y < self.grid_size:
                    # 살아있는 타겟은 깜빡임 효과
                    if target.is_alive and random.random() < 0.3:
                        grid[target.y][target.x] = "  "
                    else:
                        grid[target.y][target.x] = target.emoji
        
        # 던진 링 표시
        for ring in game_data.get("thrown_rings", []):
            if 0 <= ring.x < self.grid_size and 0 <= ring.y < self.grid_size:
                if grid[ring.y][ring.x] == "  ":
                    grid[ring.y][ring.x] = "⭕" if ring.hit else "❌"
        
        # 그리드를 문자열로 변환
        grid_str = "    " + " ".join(f"{i:2d}" for i in range(self.grid_size)) + "\n"
        grid_str += "   " + "───" * self.grid_size + "\n"
        
        for i, row in enumerate(grid):
            grid_str += f"{i:2d}│" + "".join(row) + "\n"
        
        return grid_str
    
    async def start_game(self, interaction: discord.Interaction):
        """게임 시작"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        debug_log("WANAGE", f"Starting game in channel {channel_id}")
        
        # 목표물 생성
        targets = self._generate_targets()
        
        # 바람 설정 (약하게 조정)
        wind_strength = random.uniform(0.5, 1.5)
        wind_direction = random.uniform(0, 360)
        
        # 게임 데이터 초기화
        game_data = {
            "player": interaction.user,
            "targets": targets,
            "rings": 10,
            "score": 0,
            "wind_strength": wind_strength,
            "wind_direction": wind_direction,
            "thrown_rings": [],
            "game_over": False,
            "collected_items": [],  # 획득한 아이템들
            # 기괴한 요소들
            "eye_count": 0,  # 눈 개수
            "is_reversed": False,  # 좌우반전
            "fog_turns": 0,  # 안개 지속 턴
            "approaching_monster": None,  # 접근하는 괴수
            "battle_triggered": False,  # 전투 트리거 여부
            "last_throw_result": None,  # 마지막 던진 결과 저장
            "monster_task": None,  # 괴수 이동 태스크
        }
        
        self.active_games[channel_id] = game_data
        
        # 게임 시작 화면
        embed = self._create_game_embed(channel_id)
        view = WanageView(self, channel_id)
        
        await interaction.response.send_message(embed=embed, view=view)
        game_data["message"] = await interaction.original_response()
    
    def _generate_targets(self) -> List[Target]:
        """목표물 생성"""
        targets = []
        positions = [(2, 3), (5, 2), (7, 4), (3, 5), (6, 6), (4, 7), (8, 5)]
        
        # 살아있는 타겟 확률 증가 (20% -> 35%)
        alive_count = 1 if random.random() < 0.99 else 0
        alive_positions = random.sample(positions, alive_count) if alive_count > 0 else []
        normal_positions = [p for p in positions if p not in alive_positions]
        
        # 살아있는 타겟 추가
        for pos in alive_positions:
            target_type = random.choice(self.alive_target_types)
            target = Target(
                name=target_type[0],
                emoji=target_type[1],
                radius=target_type[2],
                boundary_radius=self.calculate_boundary_radius(target_type[3]),
                points=target_type[3],
                x=pos[0],
                y=pos[1],
                is_alive=True
            )
            targets.append(target)
        
        # 일반 타겟 추가
        for pos in normal_positions:
            target_type = random.choice(self.normal_target_types)
            target = Target(
                name=target_type[0],
                emoji=target_type[1],
                radius=target_type[2],
                boundary_radius=self.calculate_boundary_radius(target_type[3]),
                points=target_type[3],
                x=pos[0],
                y=pos[1]
            )
            targets.append(target)
        
        return targets
    
    async def throw_ring(self, interaction: discord.Interaction, direction: float, power: float):
        """링 던지기"""
        channel_id = interaction.channel_id
        game_data = self.active_games.get(channel_id)
        
        if not game_data or game_data["game_over"]:
            await interaction.response.send_message(
                "진행 중인 게임이 없습니다!",
                ephemeral=True
            )
            return
        
        # 안개 턴 감소
        if game_data.get("fog_turns", 0) > 0:
            game_data["fog_turns"] -= 1
        
        if debug_config.debug_enabled:
            debug_log("WANAGE", "="*50)
            debug_log("WANAGE", f"Throwing ring - Direction: {direction}, Power: {power}")
            debug_log("WANAGE", f"Wind: {game_data['wind_strength']:.1f}m/s, Direction: {game_data['wind_direction']:.0f}°")
            if game_data.get("is_reversed", False):
                debug_log("WANAGE", "Direction is REVERSED!")
        
        # 착지 위치 계산 (좌우반전 효과 적용) - 수정된 버전 사용
        final_x, final_y, path = self.calculate_landing_position(
            direction, power,
            game_data['wind_strength'], 
            game_data['wind_direction'],
            game_data.get("is_reversed", False)
        )
        
        # 활성화된 목표물만 체크 (맞춘 것 제외)
        active_targets = [t for t in game_data["targets"] if not t.hit]
        
        # 목표물 명중 체크 (바운더리 포함)
        hit_target = None
        actual_landing = None
        
        # 점수가 낮은 순으로 정렬하여 체크
        sorted_targets = sorted(active_targets, key=lambda t: t.points)
        
        for target in sorted_targets:
            # 정수 좌표로 거리 계산
            distance = math.sqrt((target.x - final_x)**2 + (target.y - final_y)**2)
            
            # 바운더리 내에 있는지 체크
            if distance <= target.boundary_radius:
                hit_target = target
                if distance > target.radius:
                    # 바운더리 히트 - 링을 목표물 위치로 이동
                    actual_landing = (final_x, final_y)
                    final_x, final_y = target.x, target.y
                break  # 점수가 낮은 순으로 체크하므로 첫 번째 히트가 최우선
        
        # 괴수 명중 체크 (추가된 부분)
        monster = game_data.get("approaching_monster")
        monster_hit = False
        if monster and not game_data.get("battle_triggered"):
            # 괴수와의 거리 계산
            monster_distance = math.sqrt((monster.grid_x - final_x)**2 + (monster.grid_y - final_y)**2)
            # 괴수 주변 1칸을 바운더리로 설정
            if monster_distance <= 1.5:  # 바운더리 반경 1.5
                monster_hit = True
                game_data["score"] += 300  # +300점
                # 괴수 제거
                game_data["approaching_monster"] = None
                if "monster_task" in game_data and game_data["monster_task"]:
                    game_data["monster_task"].cancel()
                    try:
                        await game_data["monster_task"]
                    except asyncio.CancelledError:
                        pass
        
        # 던진 링 정보 저장
        thrown_ring = ThrownRing(
            x=final_x,
            y=final_y,
            hit=hit_target is not None or monster_hit,
            target_name=hit_target.name if hit_target else None,
            actual_landing=actual_landing
        )
        game_data["thrown_rings"].append(thrown_ring)
        
        # 링 개수 감소
        game_data["rings"] -= 1
        
        # 결과 메시지
        result_msg = ""
        horror_msg = None  # 공포 묘사
        
        if monster_hit:
            result_msg = f"💀 **괴수 처치!** {monster.name}을(를) 맞췄습니다! +300점"
            horror_msg = f"{monster.name}은(는) 비명을 지르며 사라졌다..."
        elif hit_target:
            hit_target.hit = True  # 목표물을 맞춤으로 표시
            
            # 살아있는 타겟 효과
            if hit_target.is_alive:
                if hit_target.name == "깜빡이는 눈":
                    # 더 많은 눈 생성
                    game_data["eye_count"] += random.randint(3, 7)
                    horror_msg = f"눈을 맞추자 주변에 {game_data['eye_count']}개의 눈이 더 떠올랐다."
                    
                elif hit_target.name == "비명 인형":
                    horror_msg = "인형에서 날카로운 비명소리가 들렸다. 그리고 갑자기 조용해졌다."
                    # 좌우반전 효과
                    game_data["is_reversed"] = not game_data.get("is_reversed", False)
                    
                elif hit_target.name == "썩은 풍선":
                    horror_msg = "풍선이 터지며 검은 연기가 퍼져나갔다."
                    # 안개 효과
                    game_data["fog_turns"] = 3
                
                result_msg = f"💀 {hit_target.emoji} {hit_target.name}에 명중!"
            else:
                # 일반 타겟
                game_data["score"] += hit_target.points
                
                if actual_landing:
                    result_msg = f"✨ 명중! {hit_target.emoji} {hit_target.name} +{hit_target.points}점\n"
                    result_msg += f"바운더리에 떨어져 목표물로 끌어당겨졌습니다!"
                else:
                    result_msg = f"🎯 완벽한 명중! {hit_target.emoji} {hit_target.name} +{hit_target.points}점\n"
                    result_msg += f"목표물 정중앙에 명중했습니다!"
                
                # 랜덤하게 괴수 출현 확률 증가 (10% -> 20%)
                if not game_data.get("approaching_monster") and random.random() < 0.50:
                    monster_name = random.choice(self.runner_names) + "?"
                    
                    # 괴수를 그리드 가장자리 랜덤 위치에 생성
                    edge = random.choice(['top', 'bottom', 'left', 'right'])
                    if edge == 'top':
                        grid_x = random.randint(0, self.grid_size - 1)
                        grid_y = 0
                    elif edge == 'bottom':
                        grid_x = random.randint(0, self.grid_size - 1)
                        grid_y = self.grid_size - 1
                    elif edge == 'left':
                        grid_x = 0
                        grid_y = random.randint(0, self.grid_size - 1)
                    else:  # right
                        grid_x = self.grid_size - 1
                        grid_y = random.randint(0, self.grid_size - 1)
                    
                    monster = ApproachingMonster(
                        name=monster_name,
                        grid_x=grid_x,
                        grid_y=grid_y
                    )
                    game_data["approaching_monster"] = monster
                    
                    # 괴수 자동 이동 태스크 시작
                    if "monster_task" not in game_data or game_data.get("monster_task", None) is None:
                        game_data["monster_task"] = asyncio.create_task(
                            self._move_monster_task(channel_id)
                        )
                    
                    horror_msg = f"멀리서 {monster_name}의 형체가 다가오고 있다."
            
            if debug_config.debug_enabled:
                debug_log("WANAGE", f"Hit {hit_target.name} at ({hit_target.x}, {hit_target.y})")
        else:
            # 가장 가까운 목표물 정보
            if active_targets:
                closest = min(active_targets, 
                            key=lambda t: math.sqrt((t.x - final_x)**2 + (t.y - final_y)**2))
                closest_dist = math.sqrt((closest.x - final_x)**2 + (closest.y - final_y)**2)
                result_msg = f"💨 빗나갔습니다! 링이 ({final_x}, {final_y})에 떨어졌습니다.\n"
                result_msg += f"가장 가까운 {closest.name}까지 {closest_dist:.1f} 거리"
            else:
                result_msg = f"💨 빗나갔습니다! 링이 ({final_x}, {final_y})에 떨어졌습니다."
        
        # 괴수 이동 (throw_ring에서는 제거)
        # 괴수 이동은 이제 자동 태스크에서 처리됨
        
        # 공포 묘사가 있으면 결과 메시지에 추가
        if horror_msg:
            result_msg += f"\n\n👁️ *{horror_msg}*"
        
        # 결과를 게임 데이터에 저장
        game_data["last_throw_result"] = result_msg
        
        if debug_config.debug_enabled:
            debug_log("WANAGE", "="*50)
        
        # 게임 화면 업데이트
        embed = self._create_game_embed(channel_id)
        await interaction.response.edit_message(embed=embed)
        
        # 전투 시작 처리
        if game_data.get("battle_triggered"):
            # 괴수 태스크 정리
            if "monster_task" in game_data and game_data["monster_task"]:
                game_data["monster_task"].cancel()
                try:
                    await game_data["monster_task"]
                except asyncio.CancelledError:
                    pass
            
            await self._trigger_monster_battle(interaction.channel, game_data)
            del self.active_games[channel_id]
            return
        
        # 게임 종료 체크
        if game_data["rings"] == 0 or not [t for t in game_data["targets"] if not t.hit]:
            await self._end_game(channel_id)
    
    async def _trigger_monster_battle(self, channel: discord.TextChannel, game_data: dict):
        """괴수와의 전투 시작"""
        monster = game_data["approaching_monster"]
        player = game_data["player"]
        
        # 전투 시작 메시지
        embed = discord.Embed(
            title="⚔️ 기괴한 전투",
            description=f"{player.mention} vs {monster.name}\n\n"
                       f"전투가 시작됩니다!\n"
                       f"플레이어는 `/주사위`를 사용하세요.",
            color=discord.Color.dark_red()
        )
        
        battle_msg = await channel.send(embed=embed)
        
        # 간단한 전투 시스템
        await self._simple_monster_battle(channel, player, monster, battle_msg)
    
    async def _simple_monster_battle(self, channel: discord.TextChannel, 
                                player: discord.Member, monster: ApproachingMonster,
                                battle_msg: discord.Message):
        """간소화된 괴수 전투 - 플레이어는 /주사위, 괴수는 자동"""
        player_hp = 10
        monster_hp = 10
        round_num = 0
        
        # 디버그 로그
        if debug_config.debug_enabled:
            debug_log("WANAGE_BATTLE", f"=== 전투 시작 ===")
            debug_log("WANAGE_BATTLE", f"플레이어: {player.display_name} (ID: {player.id})")
            debug_log("WANAGE_BATTLE", f"괴수: {monster.name}")
            debug_log("WANAGE_BATTLE", f"초기 체력 - 플레이어: {player_hp}, 괴수: {monster_hp}")
        
        # 플레이어 실제 이름 추출
        player_real_name = self._extract_real_name(player.display_name)
        
        while player_hp > 0 and monster_hp > 0:
            round_num += 1
            
            if debug_config.debug_enabled:
                debug_log("WANAGE_BATTLE", f"=== 라운드 {round_num} 시작 ===")
                debug_log("WANAGE_BATTLE", f"현재 체력 - 플레이어: {player_hp}, 괴수: {monster_hp}")
            
            # 라운드 시작 임베드
            embed = discord.Embed(
                title=f"⚔️ 라운드 {round_num}",
                description=f"{player.display_name}: {player_hp}/10 HP\n"
                        f"{monster.name}: {monster_hp}/10 HP\n\n"
                        f"{player.mention}님, `/주사위`를 굴려주세요!",
                color=discord.Color.orange()
            )
            await battle_msg.edit(embed=embed)
            
            # 플레이어 주사위 대기
            def check(m):
                # 주사위 봇의 메시지인지 확인
                if m.channel.id != channel.id:
                    return False
                    
                # 봇이 보낸 메시지인지 확인
                if not m.author.bot:
                    return False
                
                # 메시지에 실제 플레이어 이름이 포함되어 있는지 확인
                # 일부 이름만 체크 (닉네임의 일부일 수 있음)
                player_names = [
                    player_real_name,
                    player.display_name,
                    player.name
                ]
                
                # 메시지 내용에 플레이어 이름이 포함되어 있는지 확인
                content = m.content.lower()
                for name in player_names:
                    if name.lower() in content and ("주사위" in content or "굴려" in content):
                        if debug_config.debug_enabled:
                            debug_log("WANAGE_BATTLE", f"주사위 메시지 감지 - 이름: {name}, 내용: {content[:50]}...")
                        return True
                
                # 주사위 형식 확인 (이름이 없어도)
                if "주사위" in content and "굴려" in content and "나왔습니다" in content:
                    # 다른 플레이어의 주사위가 아닌지 확인
                    if debug_config.debug_enabled:
                        debug_log("WANAGE_BATTLE", f"주사위 형식 메시지: {content[:50]}...")
                        debug_log("WANAGE_BATTLE", f"확인한 이름들: {player_names}")
                
                return False
            
            try:
                # wait_for 사용 - self.bot이 아닌 channel의 guild의 _state를 통해 접근
                bot = channel.guild._state._get_client()
                dice_msg = await bot.wait_for('message', timeout=30.0, check=check)
                
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"주사위 메시지 수신됨: {dice_msg.content}")
                
                # 주사위 값 추출
                player_roll = self._parse_dice_value(dice_msg.content)
                
                if player_roll is None:
                    player_roll = random.randint(1, 100)
                    await channel.send(f"⚠️ 주사위 값을 읽을 수 없어 자동으로 {player_roll}을 사용합니다.")
                    if debug_config.debug_enabled:
                        debug_log("WANAGE_BATTLE", f"주사위 값 파싱 실패, 자동 값 사용: {player_roll}")
                else:
                    if debug_config.debug_enabled:
                        debug_log("WANAGE_BATTLE", f"플레이어 주사위 값: {player_roll}")
                        
            except asyncio.TimeoutError:
                player_roll = random.randint(1, 100)
                await channel.send(f"⏰ 시간 초과! 자동으로 {player_roll}을 굴렸습니다.")
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"타임아웃 발생, 자동 값 사용: {player_roll}")
            except Exception as e:
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"주사위 대기 중 오류: {e}")
                player_roll = random.randint(1, 100)
                await channel.send(f"⚠️ 오류 발생! 자동으로 {player_roll}을 사용합니다.")
            
            # 봇(괴수) 주사위 - 자동으로 굴림
            await asyncio.sleep(1.5)  # 잠시 대기
            monster_roll = random.randint(1, 100)
            
            # 괴수 주사위 메시지 (실제 주사위 봇 형식 모방)
            monster_dice_msg = f"🎲 `{monster.name}`님이 주사위를 굴려 **{monster_roll}** 나왔습니다."
            await channel.send(monster_dice_msg)
            
            if debug_config.debug_enabled:
                debug_log("WANAGE_BATTLE", f"괴수 주사위 값: {monster_roll}")
                debug_log("WANAGE_BATTLE", f"전투 결과 - 플레이어: {player_roll} vs 괴수: {monster_roll}")
            
            await asyncio.sleep(1.5)
            
            # 결과 계산
            if player_roll > monster_roll:
                monster_hp -= 1
                result = f"✅ **{player.display_name}의 공격 성공!**\n{player_roll} > {monster_roll}"
                result_color = discord.Color.green()
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", "플레이어 공격 성공!")
            elif monster_roll > player_roll:
                player_hp -= 1
                result = f"💀 **{monster.name}의 공격 성공!**\n{monster_roll} > {player_roll}"
                result_color = discord.Color.red()
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", "괴수 공격 성공!")
            else:
                result = f"🤝 **무승부!**\n{player_roll} = {monster_roll}"
                result_color = discord.Color.yellow()
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", "무승부!")
            
            # 결과 임베드
            result_embed = discord.Embed(
                title=f"⚔️ 라운드 {round_num} 결과",
                description=result,
                color=result_color
            )
            result_embed.add_field(
                name="현재 체력",
                value=f"{player.display_name}: {player_hp}/10 HP\n{monster.name}: {monster_hp}/10 HP",
                inline=False
            )
            
            await channel.send(embed=result_embed)
            await asyncio.sleep(2)
        
        # 전투 종료
        if debug_config.debug_enabled:
            debug_log("WANAGE_BATTLE", f"=== 전투 종료 ===")
            debug_log("WANAGE_BATTLE", f"최종 체력 - 플레이어: {player_hp}, 괴수: {monster_hp}")
            debug_log("WANAGE_BATTLE", f"승자: {'괴수' if player_hp <= 0 else '플레이어'}")
        
        if player_hp <= 0:
            # 패배 - 체력 감소 처리 (멘션 제거)
            defeat_msg = f"💀 {player.display_name}은(는) {monster.name}에게 패배했습니다.\n\n체력이 10으로 감소했습니다."
            await channel.send(defeat_msg)
            
            # 체력 업데이트
            try:
                await update_nickname_health(player, 10)
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"플레이어 체력 10으로 업데이트 완료")
            except Exception as e:
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"체력 업데이트 실패: {e}")
            
            if debug_config.debug_enabled:
                debug_log("WANAGE_BATTLE", "플레이어 패배 메시지 출력")
        else:
            # 승리 - 메시지 출력
            victory_msg = f"🎉 {player.display_name}님이 승리했습니다. 동료의 모습을 한 괴수는 공기중으로 사라집니다."
            await channel.send(victory_msg)
            if debug_config.debug_enabled:
                debug_log("WANAGE_BATTLE", "플레이어 승리 메시지 출력")

    def _parse_dice_value(self, message_content: str) -> Optional[int]:
        """주사위 메시지에서 값 추출"""
        import re
        
        if debug_config.debug_enabled:
            debug_log("WANAGE_BATTLE", f"주사위 값 파싱 시도: {message_content[:100]}...")
        
        # 여러 패턴 시도
        patterns = [
            r'\*\*(\d+)\*\*',  # **숫자** 형식
            r'\*{4}(\d+)\*{4}',  # ****숫자**** 형식
            r'굴려\s*(\d+)\s*나왔습니다',
            r'주사위를\s*굴려\s*(\d+)\s*나왔습니다',
            r'결과는\s*(\d+)',
            r'(\d+)\s*나왔습니다'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_content)
            if match:
                dice_value = int(match.group(1))
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"주사위 값 추출 성공: {dice_value} (패턴: {pattern})")
                return dice_value
        
        if debug_config.debug_enabled:
            debug_log("WANAGE_BATTLE", "주사위 값 추출 실패")
        return None

    def _extract_real_name(self, display_name: str) -> str:
        """닉네임에서 실제 이름 추출"""
        if debug_config.debug_enabled:
            debug_log("WANAGE_BATTLE", f"실제 이름 추출 시도: {display_name}")
        
        # 알려진 이름 목록
        known_names = {
            "아카시하지메", "아카시 하지메", "아카시_하지메",
            "펀처", "유진석", "휘슬", "배달기사", "페이",
            "로메즈아가레스", "로메즈 아가레스", "로메즈_아가레스",
            "레이나하트베인", "레이나 하트베인", "레이나_하트베인",
            "비비", "오카미나오하", "오카미 나오하", "오카미_나오하",
            "카라트에크", "토트", "처용", "멀플리시", "멀 플리시", "멀_플리시",
            "코발트윈드", "옥타", "베레니케", "안드라블랙", "안드라 블랙", "안드라_블랙",
            "봉고3호", "봉고 3호", "봉고_3호", "몰", "베니", "백야", "루치페르",
            "벨사이르드라켄리트", "벨사이르 드라켄리트", "벨사이르_드라켄리트",
            "불스", "퓨어메탈", "퓨어 메탈", "퓨어_메탈",
            "노단투", "노 단투", "노_단투", "라록", "아카이브", "베터", "메르쿠리",
            "마크-112", "마크112", "스푸트니크2세", "스푸트니크 2세", "스푸트니크_2세",
            "이터니티", "커피머신"
        }
        
        # 정규화: 공백, 언더스코어 제거
        normalized = display_name.replace(" ", "").replace("_", "")
        
        # 알려진 이름들과 매칭
        for known_name in known_names:
            normalized_known = known_name.replace(" ", "").replace("_", "")
            if normalized_known in normalized:
                if debug_config.debug_enabled:
                    debug_log("WANAGE_BATTLE", f"알려진 이름 발견: {known_name}")
                return known_name
        
        # 못 찾으면 원본 반환
        if debug_config.debug_enabled:
            debug_log("WANAGE_BATTLE", f"알려진 이름 없음, 원본 사용: {display_name}")
        return display_name

    async def _end_game(self, channel_id: int):
        """게임 종료"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        # 괴수 이동 태스크 정리
        if "monster_task" in game_data and game_data["monster_task"]:
            game_data["monster_task"].cancel()
            try:
                await game_data["monster_task"]
            except asyncio.CancelledError:
                pass
        
        # 통계 계산
        active_targets_count = len([t for t in game_data["targets"] if not t.hit and not t.is_alive])
        perfect_bonus = 300 if active_targets_count == 0 else 0
        total_hits = len([r for r in game_data["thrown_rings"] if r.hit])
        accuracy = (total_hits / 10 * 100) if game_data["thrown_rings"] else 0
        accuracy_bonus = int(accuracy * 2)
        
        total_score = game_data["score"] + perfect_bonus + accuracy_bonus
        
        # 아이템 보상 결정 (기괴한 버전에서는 보상 없음)
        reward_item = None
        
        # 결과 임베드
        result_embed = discord.Embed(
            title="🎊 게임 종료!",
            description=f"{game_data['player'].mention}님의 게임이 종료되었습니다.",
            color=discord.Color.gold()
        )
        
        # 점수 정보
        result_embed.add_field(
            name="📊 게임 결과",
            value=f"기본 점수: {game_data['score']}점\n"
                  f"정확도 보너스: +{accuracy_bonus}점 ({accuracy:.1f}%)\n"
                  f"{'퍼펙트 보너스: +300점' if perfect_bonus > 0 else ''}\n"
                  f"**총 점수: {total_score}점**",
            inline=False
        )
        
        # 통계
        result_embed.add_field(
            name="📈 통계",
            value=f"명중률: {total_hits}/10 ({accuracy:.1f}%)\n"
                  f"남은 목표물: {active_targets_count}개",
            inline=True
        )
        
        # 맞춘 목표물
        hit_targets = [t for t in game_data["targets"] if t.hit and not t.is_alive]
        if hit_targets:
            target_list = "\n".join([f"{t.emoji} {t.name} ({t.points}점)" for t in hit_targets[:5]])
            result_embed.add_field(
                name="🎯 맞춘 목표물",
                value=target_list,
                inline=True
            )
        
        # 게임에서 일어난 기괴한 일들
        weird_events = []
        if game_data.get("eye_count", 0) > 0:
            weird_events.append(f"👁️ {game_data['eye_count']}개의 눈이 당신을 지켜봤습니다")
        if any(t.hit for t in game_data["targets"] if t.is_alive):
            weird_events.append("💀 살아있는 타겟을 맞췄습니다")
        if game_data.get("approaching_monster"):
            weird_events.append(f"👤 {game_data['approaching_monster'].name}이(가) 접근했습니다")
        
        if weird_events:
            result_embed.add_field(
                name="👁️ 기괴한 사건",
                value="\n".join(weird_events),
                inline=False
            )
        
        # 보상 정보 (없음)
        coin_reward = 0
        result_embed.add_field(
            name="💰 보상",
            value="없음",
            inline=False
        )
        
        result_embed.set_footer(text="즐거운 시간 보내셨나요?")
        
        # 결과 전송
        await game_data["message"].channel.send(embed=result_embed)
        
        # 봇에 이벤트 알림 (있다면)
        if hasattr(game_data["message"].channel, 'bot'):
            bot = game_data["message"].channel.bot
            if hasattr(bot, 'on_minigame_complete'):
                await bot.on_minigame_complete(
                    str(game_data["player"].id),
                    game_data["player"].display_name,
                    "와나게",
                    coin_reward
                )
        
        # 게임 데이터 삭제
        del self.active_games[channel_id]
        debug_log("WANAGE", f"Game ended. Total score: {total_score}")
    
    async def start_game_direct(self, channel: discord.TextChannel, player: discord.Member):
        """채널에서 직접 게임 시작 (인터랙션 없이)"""
        channel_id = channel.id
        
        if channel_id in self.active_games:
            await channel.send(f"{player.mention} 이미 진행 중인 게임이 있습니다!")
            return
        
        debug_log("WANAGE", f"Starting game in channel {channel_id} for player {player.display_name}")
        
        # 목표물 생성
        targets = self._generate_targets()
        
        # 바람 설정 (약하게 조정)
        wind_strength = random.uniform(0.5, 1.5)
        wind_direction = random.uniform(0, 360)
        
        # 게임 데이터 초기화
        game_data = {
            "player": player,
            "targets": targets,
            "rings": 10,
            "score": 0,
            "wind_strength": wind_strength,
            "wind_direction": wind_direction,
            "thrown_rings": [],
            "game_over": False,
            "collected_items": [],  # 획득한 아이템들
            # 기괴한 요소들
            "eye_count": 0,  # 눈 개수
            "is_reversed": False,  # 좌우반전
            "fog_turns": 0,  # 안개 지속 턴
            "approaching_monster": None,  # 접근하는 괴수
            "battle_triggered": False,  # 전투 트리거 여부
            "last_throw_result": None,  # 마지막 던진 결과 저장
            "monster_task": None,  # 괴수 이동 태스크
        }
        
        self.active_games[channel_id] = game_data
        
        # 게임 시작 화면
        embed = self._create_game_embed(channel_id)
        view = WanageView(self, channel_id)
        
        message = await channel.send(embed=embed, view=view)
        game_data["message"] = message

# UI 요소들
class WanageView(discord.ui.View):
    def __init__(self, game: WanageGame, channel_id: int):
        super().__init__(timeout=600)  # 10분 타임아웃
        self.game = game
        self.channel_id = channel_id
        
    @discord.ui.button(label="🎯 링 던지기", style=discord.ButtonStyle.primary)
    async def throw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_data = self.game.active_games.get(self.channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "게임이 종료되었습니다!",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game_data["player"].id:
            await interaction.response.send_message(
                "이 게임의 플레이어가 아닙니다!",
                ephemeral=True
            )
            return
        
        modal = WanageModal(self.game, self.channel_id)
        await interaction.response.send_modal(modal)

class WanageModal(discord.ui.Modal, title="링 던지기"):
    direction = discord.ui.TextInput(
        label="방향 (0-360도)",
        placeholder="0: 왼쪽아래, 90: 위, 180: 오른쪽아래",
        min_length=1,
        max_length=3
    )
    
    power = discord.ui.TextInput(
        label="파워 (0-100)",
        placeholder="0: 매우 약함, 100: 매우 강함",
        min_length=1,
        max_length=3
    )
    
    def __init__(self, game: WanageGame, channel_id: int):
        super().__init__()
        self.game = game
        self.channel_id = channel_id
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            direction = float(self.direction.value)
            power = float(self.power.value)
            
            if not (0 <= direction <= 360):
                await interaction.response.send_message(
                    "방향은 0-360 사이여야 합니다!",
                    ephemeral=True
                )
                return
            
            if not (0 <= power <= 100):
                await interaction.response.send_message(
                    "파워는 0-100 사이여야 합니다!",
                    ephemeral=True
                )
                return
            
            await self.game.throw_ring(interaction, direction, power)
            
        except ValueError:
            await interaction.response.send_message(
                "올바른 숫자를 입력하세요!",
                ephemeral=True
            )

# 전역 게임 인스턴스
wanage_game = WanageGame()

def get_wanage_game():
    return wanage_game