# dart.py - 사격 게임 (호러 모드 포함) 완전 재작성 버전
import discord
from discord import app_commands
import asyncio
import random
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from debug_config import debug_log, performance_tracker, debug_config
import re
from battle_utils import extract_health_from_nickname, update_nickname_health, extract_real_name as extract_real_name_battle
import time

logger = logging.getLogger(__name__)

@dataclass
class Player:
    """플레이어 정보"""
    user: discord.Member
    real_name: str
    score: int = 0
    hits: int = 0
    critical_hits: int = 0
    misses: int = 0
    broken_bullets: int = 0
    dice_modifier: int = 0
    shots_taken: int = 0
    bullets_left: int = 10
    real_health: int = 100
    sanity: int = 100
    is_marked: bool = False
    death_message: Optional[str] = None
    is_in_thread: bool = False
    thread_channel: Optional[discord.Thread] = None
    last_shot_result: Optional[str] = None

@dataclass
class Target:
    """목표물 정보"""
    name: str
    emoji: str
    points: int
    x: int
    y: int
    speed: float = 0.5
    direction_x: int = 1
    direction_y: int = 1
    is_horror: bool = False
    horror_type: Optional[str] = None
    attack_damage: int = 0
    sanity_damage: int = 0
    is_zarrla_piece: bool = False
    corruption_radius: int = 0
    is_invincible: bool = False
    target_player_id: Optional[int] = None
    spawn_time: float = field(default_factory=time.time)
    linked_corruptions: List[int] = field(default_factory=list)
    parent_zarrla: Optional[int] = None
    
    def __post_init__(self):
        self.x = int(self.x)
        self.y = int(self.y)

class ShootingGame:
    def __init__(self, sheet_manager=None):
        self.active_games: Dict[int, dict] = {}
        self.join_messages: Dict[int, discord.Message] = {}
        self.grid_size = 9
        self.max_bullets = 10
        self.base_dice = 10
        self.sheet_manager = sheet_manager
        
        # 일반 목표물 타입
        self.target_types = [
            ("풍선", "🎈", 10, 0.3),
            ("과녁", "🎯", 20, 0.2),
            ("별", "⭐", 30, 0.4),
            ("하트", "❤️", 40, 0.5),
            ("다이아", "💎", 50, 0.6)
        ]
        
        # 호러 목표물 타입 (속도 대폭 감소)
        self.horror_target_types = [
            ("자르조각", "🩸", 50, 0.03, {"is_zarrla_piece": True, "corruption_radius": 2}),
            ("그림자", "👤", 30, 0.1, {"attack_damage": 10, "sanity_damage": 5}),
            ("눈", "👁️", 20, 0.08, {"sanity_damage": 10}),
            ("유령", "👻", 40, 0.1, {"is_invincible": True, "sanity_damage": 10}),
            ("잠식체", "🟪", 25, 0.08, {"attack_damage": 0}),
        ]
        
        self.monster_attack_delay = 20.0
        
        self.random_events = [
            "darkness",
            "zarrla_whisper",
            "shadow_rush",
            "sanity_drain",
            "cursed_bullets",
            "eye_spawn",
            "ghost_spawn"
        ]
    
    def _create_horror_target(self, horror_type: str) -> Target:
        """호러 목표물 생성"""
        for h_type in self.horror_target_types:
            if h_type[0] == horror_type:
                target = Target(
                    name=h_type[0],
                    emoji=h_type[1],
                    points=h_type[2],
                    x=random.randint(1, self.grid_size - 2),
                    y=random.randint(1, self.grid_size - 2),
                    speed=h_type[3],
                    direction_x=random.choice([-1, 1]),
                    direction_y=random.choice([-1, 1]),
                    is_horror=True,
                    horror_type=horror_type,
                    spawn_time=time.time()
                )
                
                for attr, value in h_type[4].items():
                    setattr(target, attr, value)
                
                return target
        
        return Target(
            name=horror_type,
            emoji="❓",
            points=10,
            x=random.randint(1, self.grid_size - 2),
            y=random.randint(1, self.grid_size - 2),
            speed=0.3,
            is_horror=True,
            horror_type=horror_type
        )
    
    async def start_game(self, interaction: discord.Interaction, is_multiplayer: bool = False):
        """게임 생성 (minigames_commands.py 호환성)"""
        await self.create_game(interaction, is_multiplayer)
    
    async def create_game(self, interaction: discord.Interaction, is_multiplayer: bool = False):
        """게임 생성"""
        channel_id = interaction.channel_id
        
        if channel_id in self.active_games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다!",
                ephemeral=True
            )
            return
        
        game_data = {
            "creator_id": interaction.user.id,
            "players": {},
            "targets": [],
            "phase": "waiting",
            "is_multiplayer": is_multiplayer,
            "turn_count": 0,
            "total_horror_spawned": 0,
            "corrupted_cells": set(),
            "darkness_level": 0,
            "random_event_active": None,
            "event_timer": 0
        }
        
        self.active_games[channel_id] = game_data
        
        embed = discord.Embed(
            title=f"🎯 {'멀티플레이어' if is_multiplayer else '싱글플레이어'} 사격 게임 - 호러 모드",
            description="참가 버튼을 눌러 게임에 참여하세요!",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="게임 방식",
            value="좌표를 입력하여 목표물을 맞추세요!\n호러 모드: 괴물들을 조심하세요!",
            inline=False
        )
        
        view = InitialGameView(self)
        
        await interaction.response.send_message(embed=embed, view=view)
        game_data["message"] = await interaction.original_response()
        
        debug_log("SHOOTING", f"Game created in channel {channel_id}")
    
    async def join_game(self, interaction: discord.Interaction):
        """게임 참가"""
        channel_id = interaction.channel_id
        game_data = self.active_games.get(channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "참가할 게임이 없습니다!",
                ephemeral=True
            )
            return
        
        if game_data["phase"] != "waiting":
            await interaction.response.send_message(
                "이미 시작된 게임입니다!",
                ephemeral=True
            )
            return
        
        user_id = interaction.user.id
        
        if user_id in game_data["players"]:
            await interaction.response.send_message(
                "이미 참가했습니다!",
                ephemeral=True
            )
            return
        
        if not game_data["is_multiplayer"] and len(game_data["players"]) >= 1:
            await interaction.response.send_message(
                "싱글플레이어 게임은 1명만 참가할 수 있습니다!",
                ephemeral=True
            )
            return
        
        real_name = self.extract_real_name(interaction.user.display_name)
        real_health = extract_health_from_nickname(interaction.user.display_name)
        
        player = Player(
            user=interaction.user,
            real_name=real_name,
            real_health=real_health
        )
        
        game_data["players"][user_id] = player
        
        await interaction.response.send_message(
            f"{real_name}님이 게임에 참가했습니다!",
            ephemeral=True
        )
        
        embed = discord.Embed(
            title=f"🎯 {'멀티플레이어' if game_data['is_multiplayer'] else '싱글플레이어'} 사격 게임 - 호러 모드",
            description="참가자 목록:",
            color=discord.Color.dark_red()
        )
        
        for p in game_data["players"].values():
            embed.add_field(
                name=p.real_name,
                value=f"체력: {p.real_health}/100",
                inline=True
            )
        
        await game_data["message"].edit(embed=embed)
    
    async def start_game_button(self, interaction: discord.Interaction):
        """게임 시작 버튼 핸들러"""
        channel_id = interaction.channel_id
        game_data = self.active_games.get(channel_id)
        
        if not game_data:
            await interaction.response.send_message(
                "시작할 게임이 없습니다!",
                ephemeral=True
            )
            return
        
        if interaction.user.id != game_data["creator_id"]:
            await interaction.response.send_message(
                "게임 생성자만 시작할 수 있습니다!",
                ephemeral=True
            )
            return
        
        if not game_data["players"]:
            await interaction.response.send_message(
                "참가자가 없습니다!",
                ephemeral=True
            )
            return
        
        if game_data["phase"] != "waiting":
            await interaction.response.send_message(
                "이미 시작된 게임입니다!",
                ephemeral=True
            )
            return
        
        game_data["phase"] = "playing"
        
        self._generate_targets(game_data)
        
        game_data["update_task"] = asyncio.create_task(self._update_loop(channel_id))
        
        asyncio.create_task(self._spawn_new_target(channel_id))
        asyncio.create_task(self._random_event_loop(channel_id))
        
        await interaction.response.send_message(
            "게임이 시작되었습니다! 좌표를 입력하여 사격하세요!",
            ephemeral=True
        )
        
        debug_log("SHOOTING", f"Game started in channel {channel_id}")
    
    async def start_game_direct(self, channel: discord.TextChannel, user: discord.Member, is_multiplayer: bool = False):
        """Interaction 없이 직접 게임 시작"""
        channel_id = channel.id
        
        if channel_id in self.active_games:
            await channel.send("이미 진행 중인 게임이 있습니다!", delete_after=5)
            return
        
        game_data = {
            "creator_id": user.id,
            "players": {},
            "targets": [],
            "phase": "waiting",
            "is_multiplayer": is_multiplayer,
            "turn_count": 0,
            "total_horror_spawned": 0,
            "corrupted_cells": set(),
            "darkness_level": 0,
            "random_event_active": None,
            "event_timer": 0
        }
        
        self.active_games[channel_id] = game_data
        
        if is_multiplayer:
            embed = discord.Embed(
                title="🎯 멀티플레이어 사격 게임 - 호러 모드",
                description="참가 버튼을 눌러 게임에 참여하세요!",
                color=discord.Color.dark_red()
            )
            
            view = InitialGameView(self)
            message = await channel.send(embed=embed, view=view)
            game_data["message"] = message
        else:
            real_name = self.extract_real_name(user.display_name)
            real_health = extract_health_from_nickname(user.display_name)
            
            player = Player(
                user=user,
                real_name=real_name,
                real_health=real_health
            )
            
            game_data["players"][user.id] = player
            game_data["phase"] = "playing"
            
            self._generate_targets(game_data)
            
            embed = self._create_game_embed(channel_id)
            view = ShootingGameView(self)
            message = await channel.send(embed=embed, view=view)
            game_data["message"] = message
            
            game_data["update_task"] = asyncio.create_task(self._update_loop(channel_id))
            
            asyncio.create_task(self._spawn_new_target(channel_id))
            asyncio.create_task(self._random_event_loop(channel_id))
            
            debug_log("SHOOTING", f"Game started directly in channel {channel_id}")
    
    async def _process_shot(self, interaction: discord.Interaction, x: int, y: int):
        """사격 처리 (기존 UI 방식)"""
        channel_id = interaction.channel_id
        game_data = self.active_games.get(channel_id)
        
        if not game_data:
            return
        
        player = game_data["players"].get(interaction.user.id)
        if not player:
            await interaction.response.send_message(
                "게임에 참가하지 않았습니다!",
                ephemeral=True
            )
            return
        
        # 주사위 굴리기 - 수정된 보정값 적용
        dice_modifier = self.calculate_dice_modifier(interaction.user.guild.get_member(interaction.user.id).display_name)
        dice_value = random.randint(1, 100) + dice_modifier
        
        # 음수 방지
        dice_value = max(1, dice_value)
        
        player.shots_taken += 1
        player.bullets_left -= 1
        
        # 이벤트 효과 적용
        if game_data.get("random_event_active") == "cursed_bullets":
            dice_value = max(1, dice_value - 20)  # 저주받은 탄알
        
        # 명중 판정 - 50 이상이면 성공
        success = dice_value >= 50
        
        # 목표물 찾기
        hit_target = None
        for target in game_data["targets"]:
            if target.x == x - 1 and target.y == y - 1:  # 좌표 변환
                # 잠식체는 무조건 명중
                if target.horror_type == "잠식체":
                    hit_target = target
                    break
                    
                # 유령 처리
                if target.is_invincible and target.horror_type == "유령":
                    if dice_value < 90:  # 90 이상이어야 유령 통과
                        result_msg = f"❌ 빗나감!\n주사위: {dice_value} (보정: {dice_modifier:+d})\n👻 유령을 통과했습니다! (90 이상 필요)"
                        player.last_shot_result = result_msg
                        await interaction.response.defer()
                        # 게임 화면 업데이트
                        embed = self._create_game_embed(channel_id)
                        view = ShootingGameView(self)
                        await game_data["message"].edit(embed=embed, view=view)
                        return
                
                # 일반 명중 판정
                if success:
                    hit_target = target
                    break
        
        if hit_target:
            # 명중
            player.hits += 1
            player.score += hit_target.points
            
            # 치명타 판정
            is_critical = dice_value >= 90
            if is_critical:
                player.critical_hits += 1
                player.score += hit_target.points  # 추가 점수
            
            result_msg = f"🎯 명중! {hit_target.emoji} {hit_target.name} (+{hit_target.points}점)\n"
            result_msg += f"주사위: {dice_value} (보정: {dice_modifier:+d})"
            if is_critical:
                result_msg += " 💥 치명타!"
            
            # 자르 조각 제거 시 연결된 잠식체도 제거
            if hit_target.is_zarrla_piece:
                # 연결된 잠식체 제거
                removed_count = 0
                removed_targets = []
                
                if hasattr(hit_target, 'linked_corruptions') and hit_target.linked_corruptions:
                    for corruption_id in hit_target.linked_corruptions[:]:  # 복사본으로 순회
                        for i, t in enumerate(game_data["targets"]):
                            if id(t) == corruption_id:
                                removed_targets.append(i)
                                removed_count += 1
                                break
                
                # 인덱스를 역순으로 정렬하여 제거 (뒤에서부터 제거)
                for idx in sorted(removed_targets, reverse=True):
                    game_data["targets"].pop(idx)
                
                if removed_count > 0:
                    result_msg += f"\n🟪 연결된 잠식체 {removed_count}개도 함께 제거되었습니다!"
            
            player.last_shot_result = result_msg
            
            # 목표물 제거
            game_data["targets"].remove(hit_target)
            
            # 모든 목표물 제거 시 보너스
            if not game_data["targets"]:
                bonus = 50
                player.score += bonus
                result_msg += f"\n🎉 모든 목표물 제거! 보너스 +{bonus}점!"
                player.last_shot_result = result_msg
        else:
            # 빗나감
            player.misses += 1
            
            # 고장 판정
            if dice_value <= 10:  # 10 이하일 때 고장
                player.broken_bullets += 1
                player.bullets_left = max(0, player.bullets_left - 1)  # 추가 탄알 소모
                result_msg = f"💥 탄알 고장! 추가 탄알 1개 소모\n주사위: {dice_value} (보정: {dice_modifier:+d})"
            else:
                result_msg = f"❌ 빗나감!\n주사위: {dice_value} (보정: {dice_modifier:+d})"
            
            player.last_shot_result = result_msg
        
        # interaction 응답 처리
        await interaction.response.defer()
        
        # 게임 화면 업데이트
        embed = self._create_game_embed(channel_id)
        view = ShootingGameView(self)
        await game_data["message"].edit(embed=embed, view=view)
        
        # 게임 종료 체크
        if player.bullets_left <= 0:
            # 모든 플레이어가 탄알을 다 쓴 경우 게임 종료
            all_out = all(p.bullets_left <= 0 for p in game_data["players"].values())
            if all_out:
                await self._end_game(channel_id)
    
    def calculate_dice_modifier(self, display_name: str) -> int:
        """닉네임에서 주사위 보정값 계산 (기존 방식)"""
        modifier = 0
        
        # 닉네임에 특정 단어가 포함되어 있는지 확인
        if "각성" in display_name:
            modifier += 50
        if "만취" in display_name:
            modifier -= 40
        elif "취함" in display_name:  # 만취가 없을 때만 취함 체크
            modifier -= 20
        
        return modifier
    
    async def _update_loop(self, channel_id: int):
        """게임 업데이트 루프"""
        update_count = 0
        
        while channel_id in self.active_games:
            try:
                game_data = self.active_games.get(channel_id)
                if not game_data or game_data.get("phase") == "ended":
                    debug_log("SHOOTING", f"Game ended for channel {channel_id}")
                    break
                
                current_time = time.time()
                
                for target in game_data["targets"][:]:
                    if target in game_data["targets"]:
                        target.x += target.direction_x * target.speed
                        target.y += target.direction_y * target.speed
                        
                        if target.x <= 0 or target.x >= self.grid_size - 1:
                            target.direction_x *= -1
                            target.x = max(0, min(self.grid_size - 1, target.x))
                        
                        if target.y <= 0 or target.y >= self.grid_size - 1:
                            target.direction_y *= -1
                            target.y = max(0, min(self.grid_size - 1, target.y))
                        
                        target.x = int(round(target.x))
                        target.y = int(round(target.y))
                        
                        if target.is_horror:
                            await self._horror_target_effect(channel_id, target)
                        
                        if (target.attack_damage > 0 or target.sanity_damage > 0) and \
                           current_time - target.spawn_time >= self.monster_attack_delay:
                            players = list(game_data["players"].values())
                            if players:
                                if target.horror_type == "유령":
                                    victim = random.choice(players)
                                    await self._ghost_drag_to_thread(channel_id, target, victim)
                                else:
                                    victim = random.choice(players)
                                    await self._monster_attack(channel_id, target, victim)
                                
                                target.spawn_time = current_time
                
                if game_data.get("event_timer") and game_data["event_timer"] > 0:
                    game_data["event_timer"] -= 1
                    if game_data["event_timer"] <= 0:
                        game_data["random_event_active"] = None
                        if game_data.get("darkness_level"):
                            game_data["darkness_level"] = 0
                
                if "corrupted_cells" in game_data and random.random() < 0.1:
                    self._expand_corruption(game_data)
                
                embed = self._create_game_embed(channel_id)
                view = ShootingGameView(self)
                
                try:
                    await game_data["message"].edit(embed=embed, view=view)
                except discord.errors.NotFound:
                    debug_log("SHOOTING", "Game message not found, ending game")
                    await self._end_game(channel_id, forced=True)
                    break
                
                update_count += 1
                if debug_config.debug_enabled and update_count % 20 == 0:
                    debug_log("SHOOTING", f"Update count: {update_count}, Targets: {len(game_data['targets'])}")
                
            except asyncio.CancelledError:
                debug_log("SHOOTING", f"Update task cancelled for channel {channel_id}")
                break
            except Exception as e:
                logger.error(f"Error in update loop: {e}")
                debug_log("SHOOTING", f"Update error: {str(e)}")
                pass
            
            await asyncio.sleep(2.0)  # 느린 업데이트
    
    async def _ghost_drag_to_thread(self, channel_id: int, ghost: Target, victim: Player):
        """유령이 플레이어를 스레드로 끌고 감"""
        game_data = self.active_games.get(channel_id)
        if not game_data or victim.is_in_thread:
            return
        
        channel = game_data["message"].channel
        
        thread_name = f"👻 {victim.real_name}의 악몽"
        try:
            thread = await channel.create_thread(
                name=thread_name,
                auto_archive_duration=60,
                reason=f"{victim.real_name}이(가) 유령에게 끌려감"
            )
            
            victim.is_in_thread = True
            victim.thread_channel = thread
            
            if victim.sanity is not None:
                victim.sanity -= ghost.sanity_damage * 2
                victim.sanity = max(0, victim.sanity)
            
            await channel.send(
                f"👻 **{ghost.name}**이(가) **{victim.real_name}**을(를) 어둠 속으로 끌고 갔습니다!\n"
                f"😱 정신력 -{ghost.sanity_damage * 2}",
                delete_after=10
            )
            
            await thread.send(
                f"👻 **{victim.real_name}**님이 유령에게 붙잡혔습니다!\n"
                f"이곳은 악몽의 공간입니다... 탈출하려면 동료들의 도움이 필요합니다.\n"
                f"(스레드에서는 게임 참여가 불가능합니다)"
            )
            
            game_data["targets"].remove(ghost)
            
        except Exception as e:
            logger.error(f"Failed to create thread: {e}")
            await self._monster_attack(channel_id, ghost, victim)
    
    async def _spawn_new_target(self, channel_id: int):
        """새 목표물 스폰"""
        while channel_id in self.active_games:
            await asyncio.sleep(random.uniform(3, 6))
            
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data.get("phase") == "ended":
                break
            
            if "total_horror_spawned" not in game_data:
                game_data["total_horror_spawned"] = 0
            
            max_targets = 10 if game_data["is_multiplayer"] else 8
            current_target_count = len(game_data["targets"])
            
            if current_target_count >= max_targets:
                continue
            
            zarrla_chance = 0.25
            
            if game_data.get("corrupted_cells") and random.random() < 0.5:
                self._spawn_monster_in_corruption(game_data)
            elif random.random() < zarrla_chance:
                target = self._create_horror_target("자르조각")
                game_data["total_horror_spawned"] += 1
                game_data["targets"].append(target)
                debug_log("SHOOTING", f"자르 조각 스폰: ({target.x}, {target.y})")
            else:
                if random.random() < 0.15:
                    target = self._create_horror_target("잠식체")
                    game_data["total_horror_spawned"] += 1
                else:
                    target_type = random.choice(self.target_types)
                    target = Target(
                        name=target_type[0],
                        emoji=target_type[1],
                        points=target_type[2],
                        x=random.randint(1, self.grid_size - 2),
                        y=random.randint(1, self.grid_size - 2),
                        speed=target_type[3],
                        direction_x=random.choice([-1, 1]),
                        direction_y=random.choice([-1, 1]),
                        spawn_time=time.time()
                    )
                
                game_data["targets"].append(target)
            
            debug_log("SHOOTING", f"Spawned new target: {target.name} at ({target.x}, {target.y})")
    
    def _expand_corruption(self, game_data: dict):
        """잠식 구역 확장"""
        new_corrupted = set()
        
        for x, y in game_data["corrupted_cells"]:
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                    if (nx, ny) not in game_data["corrupted_cells"] and random.random() < 0.15:
                        new_corrupted.add((nx, ny))
        
        game_data["corrupted_cells"].update(new_corrupted)
    
    def _spawn_monster_in_corruption(self, game_data: dict):
        """잠식 구역에 특수 몬스터 스폰"""
        if game_data["corrupted_cells"] and len(game_data["targets"]) < 12:
            x, y = random.choice(list(game_data["corrupted_cells"]))
            
            special_monsters = ["그림자", "눈", "유령"]
            monster_type = random.choice(special_monsters)
            monster = self._create_horror_target(monster_type)
            monster.x = x
            monster.y = y
            monster.spawn_time = time.time()
            game_data["targets"].append(monster)
            
            debug_log("SHOOTING", f"잠식지에 {monster_type} 스폰: ({x}, {y})")
    
    async def _monster_attack(self, channel_id: int, monster: Target, victim: Player):
        """괴물 공격 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        if monster.attack_damage > 0 and victim.real_health is not None:
            victim.real_health -= monster.attack_damage
            victim.real_health = max(0, victim.real_health)
            
            try:
                await update_nickname_health(victim.user, victim.real_health)
            except:
                pass
        
        if monster.sanity_damage > 0 and victim.sanity is not None:
            victim.sanity -= monster.sanity_damage
            victim.sanity = max(0, victim.sanity)
        
        channel = game_data["message"].channel
        damage_text = []
        if monster.attack_damage > 0:
            damage_text.append(f"💔 체력 -{monster.attack_damage}")
        if monster.sanity_damage > 0:
            damage_text.append(f"😱 정신력 -{monster.sanity_damage}")
        
        await channel.send(
            f"⚠️ {monster.emoji} **{monster.name}**이(가) **{victim.real_name}**을(를) 공격했습니다!\n"
            f"{' | '.join(damage_text)}\n"
            f"(20초 동안 처리하지 못한 몬스터)",
            delete_after=5
        )
        
        if victim.real_health is not None and victim.real_health <= 0:
            victim.death_message = f"{monster.name}에게 공격당해 사망"
            await self._player_death(channel_id, victim)
    
    async def _player_death(self, channel_id: int, player: Player):
        """플레이어 사망 처리"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        channel = game_data["message"].channel
        death_embed = discord.Embed(
            title="☠️ 사망",
            description=f"**{player.real_name}**님이 {player.death_message or '사망'}했습니다.",
            color=discord.Color.dark_red()
        )
        
        await channel.send(embed=death_embed, delete_after=10)
        
        if player.user.id in game_data["players"]:
            del game_data["players"][player.user.id]
        
        if not game_data["players"]:
            await self._end_game(channel_id, forced=True)
    
    async def _random_event_loop(self, channel_id: int):
        """랜덤 이벤트 루프"""
        while channel_id in self.active_games:
            await asyncio.sleep(random.uniform(45, 90))
            
            game_data = self.active_games.get(channel_id)
            if not game_data or game_data.get("phase") == "ended":
                break
            
            if random.random() < 0.2:
                await self._trigger_random_event(channel_id)
    
    async def _trigger_random_event(self, channel_id: int):
        """랜덤 이벤트 발생"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        event = random.choice(self.random_events)
        game_data["random_event_active"] = event
        game_data["event_timer"] = 3
        
        channel = game_data["message"].channel
        
        if event == "darkness":
            game_data["darkness_level"] = 3
            await channel.send("🌑 **암흑이 내려왔습니다!** 시야가 제한됩니다.", delete_after=5)
            
        elif event == "zarrla_whisper":
            for player in game_data["players"].values():
                if player.sanity is not None:
                    player.sanity -= 10
                    player.sanity = max(0, player.sanity)
            await channel.send("🩸 **자르가 속삭입니다...** 모든 플레이어의 정신력이 감소합니다.", delete_after=5)
            
        elif event == "shadow_rush":
            if game_data.get("corrupted_cells"):
                for _ in range(3):
                    self._spawn_monster_in_corruption(game_data)
                await channel.send("👤 **그림자들이 습격합니다!** 잠식지에 그림자가 출현합니다.", delete_after=5)
            
        elif event == "sanity_drain":
            await channel.send("😱 **정신이 무너집니다!** 정신력이 지속적으로 감소합니다.", delete_after=5)
            
        elif event == "cursed_bullets":
            await channel.send("💀 **탄알이 저주받았습니다!** 명중률이 감소합니다.", delete_after=5)
            
        elif event == "eye_spawn":
            if len(game_data["targets"]) < 10:
                eye = self._create_horror_target("눈")
                game_data["targets"].append(eye)
                await channel.send("👁️ **무언가가 지켜보고 있습니다...** 눈이 출현했습니다.", delete_after=5)
            
        elif event == "ghost_spawn":
            if len(game_data["targets"]) < 10:
                ghost = self._create_horror_target("유령")
                game_data["targets"].append(ghost)
                await channel.send("👻 **차가운 기운이 느껴집니다...** 유령이 출현했습니다.", delete_after=5)
    
    def _generate_targets(self, game_data: dict):
        """초기 목표물 생성"""
        num_targets = 3 if game_data["is_multiplayer"] else 2
        
        if "total_horror_spawned" not in game_data:
            game_data["total_horror_spawned"] = 0
        
        zarrla = self._create_horror_target("자르조각")
        game_data["targets"].append(zarrla)
        game_data["total_horror_spawned"] += 1
        debug_log("SHOOTING", f"Initial zarrla piece at ({zarrla.x}, {zarrla.y})")
        
        for i in range(num_targets - 1):
            target_type = random.choice(self.target_types)
            target = Target(
                name=target_type[0],
                emoji=target_type[1],
                points=target_type[2],
                x=random.randint(1, self.grid_size - 2),
                y=random.randint(1, self.grid_size - 2),
                speed=target_type[3],
                direction_x=random.choice([-1, 1]),
                direction_y=random.choice([-1, 1]),
                spawn_time=time.time()
            )
            game_data["targets"].append(target)
        
        debug_log("SHOOTING", f"Generated {len(game_data['targets'])} initial targets")
    
    async def _end_game(self, channel_id: int, forced: bool = False):
        """게임 종료"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        game_data["phase"] = "ended"
        
        # 업데이트 태스크 정리
        if "update_task" in game_data:
            game_data["update_task"].cancel()
            try:
                await game_data["update_task"]
            except asyncio.CancelledError:
                pass
        
        # 결과 계산
        embed = discord.Embed(
            title="🏁 게임 종료!",
            description="최종 결과",
            color=discord.Color.gold()
        )
        
        # 플레이어 결과
        sorted_players = sorted(game_data["players"].values(), key=lambda p: p.score, reverse=True)
        
        for i, player in enumerate(sorted_players):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "👤"
            
            # 통계
            accuracy = (player.hits / player.shots_taken * 100) if player.shots_taken > 0 else 0
            
            result_text = (
                f"점수: {player.score}점\n"
                f"명중률: {accuracy:.1f}%\n"
                f"명중/실패: {player.hits}/{player.misses}\n"
                f"치명타: {player.critical_hits}회"
            )
            
            if player.broken_bullets > 0:
                result_text += f"\n고장: {player.broken_bullets}회"
            
            if player.sanity < 100:
                result_text += f"\n최종 정신력: {player.sanity}/100"
            
            if player.death_message:
                result_text += f"\n💀 {player.death_message}"
            
            embed.add_field(
                name=f"{medal} {player.real_name}",
                value=result_text,
                inline=False
            )
        
        # 보상 계산 (1등만) - 제거됨
        if sorted_players and not forced:
            winner = sorted_players[0]
            embed.add_field(
                name="🎁 승리",
                value=f"{winner.real_name}님이 승리했습니다!",
                inline=False
            )
        
        # 메시지 전송
        channel = game_data["message"].channel
        await channel.send(embed=embed)
        
        # 게임 데이터 정리
        del self.active_games[channel_id]
        if channel_id in self.join_messages:
            del self.join_messages[channel_id]
        
        debug_log("SHOOTING", f"Game ended in channel {channel_id}")
    
    def _create_game_embed(self, channel_id: int) -> discord.Embed:
        """게임 화면 생성 (기존 UI 유지)"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return discord.Embed(title="게임 오류", color=discord.Color.red())
        
        # 그리드 생성
        grid = [["⬜" for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        
        # 잠식 구역 표시
        if "corrupted_cells" in game_data:
            for cx, cy in game_data["corrupted_cells"]:
                if 0 <= cx < self.grid_size and 0 <= cy < self.grid_size:
                    grid[self.grid_size - 1 - cy][cx] = "🟪"
        
        # 목표물 배치
        target_count = 0
        for target in game_data["targets"]:
            # 좌표 유효성 검사
            x, y = target.x, target.y
            if 0 <= x < self.grid_size and 0 <= y < self.grid_size:
                grid[self.grid_size - 1 - y][x] = target.emoji  # Y축 반전
                target_count += 1
            else:
                debug_log("SHOOTING", f"Target out of bounds: {target.name} at ({x}, {y})")
        
        # 암흑 효과 적용
        if game_data.get("darkness_level", 0) > 0:
            # 일부 셀을 가림
            for _ in range(game_data["darkness_level"] * 5):
                rx, ry = random.randint(0, self.grid_size - 1), random.randint(0, self.grid_size - 1)
                if grid[ry][rx] == "⬜" or grid[ry][rx] == "🟪":
                    grid[ry][rx] = "⬛"
        
        # 그리드 문자열 생성 (Y축 숫자 추가)
        grid_str = ""
        for y in range(self.grid_size):
            y_num = self.grid_size - y
            grid_str += f"{y_num}️⃣ " + "".join(grid[y]) + "\n"
        
        # X축 숫자 추가
        grid_str += "🔢 "
        for x in range(1, self.grid_size + 1):
            grid_str += f"{x}️⃣"
        
        embed = discord.Embed(
            title="🎯 사격 게임",
            description=grid_str,
            color=discord.Color.dark_red() if game_data.get("random_event_active") else discord.Color.blue()
        )
        # 플레이어 정보
        if game_data["is_multiplayer"]:
            player_info = []
            for player in game_data["players"].values():
                status = f"**{player.real_name}**: {player.score}점 | 탄알: {player.bullets_left}"
                if player.sanity < 100:
                    status += f" | 😱 {player.sanity}"
                if player.is_in_thread:
                    status += " | 👻 스레드에 갇힘"
                player_info.append(status)
            
            embed.add_field(
                name="플레이어",
                value="\n".join(player_info),
                inline=False
            )
        else:
            player = list(game_data["players"].values())[0]
            embed.add_field(
                name="점수",
                value=f"{player.score}점",
                inline=True
            )
            embed.add_field(
                name="탄알",
                value=f"{player.bullets_left}/{self.max_bullets}",
                inline=True
            )
            if player.sanity < 100:
                embed.add_field(
                    name="정신력",
                    value=f"😱 {player.sanity}/100",
                    inline=True
                )
        
        # 목표물 목록
        target_list = {}
        for target in game_data["targets"]:
            key = f"{target.emoji} {target.name}"
            if key in target_list:
                target_list[key] += 1
            else:
                target_list[key] = 1
        
        if target_list:
            target_text = "\n".join([f"{k} x{v}" if v > 1 else k for k, v in target_list.items()])
            embed.add_field(
                name="목표물",
                value=target_text,
                inline=True
            )
        
        # 이벤트 표시
        if game_data.get("random_event_active"):
            event_names = {
                "darkness": "🌑 암흑",
                "zarrla_whisper": "🩸 자르의 속삭임",
                "shadow_rush": "👤 그림자 습격",
                "sanity_drain": "😱 정신 붕괴",
                "cursed_bullets": "💀 저주받은 탄알",
                "eye_spawn": "👁️ 눈의 출현",
                "ghost_spawn": "👻 유령 출현"
            }
            event_name = event_names.get(game_data["random_event_active"], "???")
            timer = game_data.get("event_timer", 0)
            embed.add_field(
                name="이벤트",
                value=f"{event_name} ({timer}턴)",
                inline=True
            )
        
        # 마지막 사격 결과 표시
        last_results = []
        for player in game_data["players"].values():
            if player.last_shot_result:
                last_results.append(f"**{player.real_name}**: {player.last_shot_result}")
        
        if last_results:
            embed.add_field(
                name="📋 최근 사격 결과",
                value="\n".join(last_results[-3:]),  # 최근 3개만 표시
                inline=False
            )
        
        embed.set_footer(text="좌표를 입력하여 사격하세요! (예: 5 3)")
        
        return embed
    
    async def _horror_target_effect(self, channel_id: int, target: Target):
        """호러 목표물 특수 효과"""
        game_data = self.active_games.get(channel_id)
        if not game_data:
            return
        
        if target.is_zarrla_piece:
            if "corrupted_cells" not in game_data:
                game_data["corrupted_cells"] = set()
            
            for dx in range(-target.corruption_radius, target.corruption_radius + 1):
                for dy in range(-target.corruption_radius, target.corruption_radius + 1):
                    cx, cy = target.x + dx, target.y + dy
                    if 0 <= cx < self.grid_size and 0 <= cy < self.grid_size:
                        game_data["corrupted_cells"].add((cx, cy))
            
            if random.random() < 0.4 and len(game_data["targets"]) < 12:
                corruption = self._create_horror_target("잠식체")
                corruption.x = max(0, min(self.grid_size - 1, target.x + random.randint(-2, 2)))
                corruption.y = max(0, min(self.grid_size - 1, target.y + random.randint(-2, 2)))
                corruption.spawn_time = time.time()
                
                corruption.parent_zarrla = id(target)
                
                game_data["targets"].append(corruption)
                
                if not hasattr(target, 'linked_corruptions'):
                    target.linked_corruptions = []
                target.linked_corruptions.append(id(corruption))
                
                debug_log("SHOOTING", f"잠식체 생성: ({corruption.x}, {corruption.y}) - 자르 조각 ID: {id(target)}")
        
        elif target.horror_type == "그림자" and target.attack_damage > 0:
            players = list(game_data["players"].values())
            if players:
                closest_player = min(players, 
                    key=lambda p: abs(p.user.id % self.grid_size - target.x) + 
                                  abs((p.user.id // 1000) % self.grid_size - target.y))
                
                player_x = closest_player.user.id % self.grid_size
                player_y = (closest_player.user.id // 1000) % self.grid_size
                
                if player_x > target.x:
                    target.direction_x = 1
                elif player_x < target.x:
                    target.direction_x = -1
                
                if player_y > target.y:
                    target.direction_y = 1
                elif player_y < target.y:
                    target.direction_y = -1
    
    def extract_real_name(self, display_name: str) -> str:
        """닉네임에서 실제 이름 추출"""
        name = re.sub(r'\s*\[\d+/\d+\]\s*$', '', display_name)
        name = re.sub(r'\s*\(\d+/\d+\)\s*$', '', name)
        name = re.sub(r'\s*\d+/\d+\s*$', '', name)
        
        name = re.sub(r'^PC\d+\s*', '', name, flags=re.IGNORECASE)
        
        name = re.sub(r'[_-]+', ' ', name)
        name = ' '.join(name.split())
        
        return name.strip() or display_name

# View 클래스들 (기존 UI 유지)
class InitialGameView(discord.ui.View):
    """게임 시작 전 View (참가/시작/종료 버튼)"""
    def __init__(self, game: ShootingGame):
        super().__init__(timeout=None)
        self.game = game
    
    @discord.ui.button(label="참가", style=discord.ButtonStyle.primary, emoji="🎮")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """게임 참가 버튼"""
        await self.game.join_game(interaction)
    
    @discord.ui.button(label="시작", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """게임 시작 버튼"""
        await self.game.start_game_button(interaction)
    
    @discord.ui.button(label="종료", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """게임 종료 버튼"""
        channel_id = interaction.channel_id
        game_data = self.game.active_games.get(channel_id)
        
        if not game_data:
            await interaction.response.send_message("진행 중인 게임이 없습니다.", ephemeral=True)
            return
        
        if interaction.user.id != game_data["creator_id"]:
            await interaction.response.send_message("게임 생성자만 종료할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.send_message("게임을 종료합니다...", ephemeral=True)
        await self.game._end_game(channel_id, forced=True)

class ShootingGameView(discord.ui.View):
    """게임 진행 중 View (사격 버튼)"""
    def __init__(self, game: ShootingGame):
        super().__init__(timeout=180)
        self.game = game
    
    @discord.ui.button(label="사격", style=discord.ButtonStyle.primary, emoji="🎯")
    async def shoot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ShootModal(self.game)
        await interaction.response.send_modal(modal)

class ShootModal(discord.ui.Modal, title="사격 좌표 입력"):
    def __init__(self, game: ShootingGame):
        super().__init__()
        self.game = game
    
    x_coord = discord.ui.TextInput(
        label="X 좌표 (1-9)",
        placeholder="1-9 사이의 숫자",
        required=True,
        max_length=1
    )
    
    y_coord = discord.ui.TextInput(
        label="Y 좌표 (1-9)",
        placeholder="1-9 사이의 숫자",
        required=True,
        max_length=1
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            x = int(self.x_coord.value)
            y = int(self.y_coord.value)
            
            if not (1 <= x <= 9 and 1 <= y <= 9):
                await interaction.response.send_message(
                    "좌표는 1-9 사이여야 합니다!",
                    ephemeral=True
                )
                return
            
            await self.game._process_shot(interaction, x, y)
            
        except ValueError:
            await interaction.response.send_message(
                "올바른 숫자를 입력해주세요!",
                ephemeral=True
            )

class JoinGameView(discord.ui.View):
    def __init__(self, game: ShootingGame):
        super().__init__(timeout=30)
        self.game = game
    
    @discord.ui.button(label="참가", style=discord.ButtonStyle.primary, emoji="✅")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.game.join_game(interaction)

# 싱글톤 인스턴스
_shooting_game_instance = None

def get_dart_game():
    """싱글톤 게임 인스턴스 반환"""
    global _shooting_game_instance
    if _shooting_game_instance is None:
        _shooting_game_instance = ShootingGame()
    return _shooting_game_instance