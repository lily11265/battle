# mafia.py
import discord
from discord import app_commands
from discord.errors import InteractionResponded
import asyncio
import random
import logging
from typing import Dict, List, Optional, Set
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# 게임에서 사용할 이름 목록
GAME_NAMES = [
    "아카시 하지메", "펀처", "유진석", "휘슬", "배달기사", "페이",
    "로메즈 아가레스", "레이나 하트베인", "비비", "오카미 나오하",
    "카라트에크", "토트", "처용", "멀 플리시", "코발트윈드", "옥타",
    "베레니케", "안드라 블랙", "봉고 3호", "몰", "베니", "백야",
    "루치페르", "벨사이르 드라켄리트", "불스", "퓨어 메탈", "노 단투",
    "라록", "아카이브", "베터", "메르쿠리", "마크-112", "스푸트니크 2세",
    "이터니티", "커피머신"
]

def get_game_name(member: discord.Member) -> str:
    """서버 닉네임에서 게임 이름 추출"""
    display_name = member.display_name
    
    # 이름 목록에서 닉네임에 포함된 이름 찾기
    for name in GAME_NAMES:
        if name in display_name:
            return name
    
    # 못 찾으면 원래 닉네임 반환
    return display_name

class Role(Enum):
    """마피아 게임 역할"""
    CITIZEN = ("시민", "👤", "마을을 지켜주세요!")
    MAFIA = ("마피아", "🔫", "밤에 시민을 제거하세요!")
    POLICE = ("경찰", "👮", "밤에 마피아를 조사하세요!")
    DOCTOR = ("의사", "👨‍⚕️", "밤에 누군가를 보호하세요!")

class GamePhase(Enum):
    """게임 진행 단계"""
    WAITING = "대기중"
    NIGHT = "밤"
    DAY_DISCUSSION = "낮 - 토론"
    DAY_VOTE = "낮 - 투표"
    GAME_OVER = "게임종료"

@dataclass
class Player:
    """플레이어 정보"""
    user: discord.Member
    role: Role
    alive: bool = True
    protected: bool = False
    votes: int = 0
    
    @property
    def game_name(self) -> str:
        """게임에서 사용할 이름"""
        return get_game_name(self.user)

class MafiaGame:
    def __init__(self):
        self.games = {}  # channel_id: game_data
        self.MIN_PLAYERS = 4
        self.MAX_PLAYERS = 24  # 12에서 24로 변경
        
    def assign_roles(self, players: List[discord.Member]) -> Dict[int, Player]:
        """역할 배정"""
        player_count = len(players)
        player_data = {}
        
        # 역할 개수 결정 (24명일 때를 고려해 조정)
        mafia_count = max(1, player_count // 4)  # 24명일 때 마피아 6명
        police_count = min(2, 1 if player_count >= 5 else 0)  # 최대 2명으로 제한
        doctor_count = min(2, 1 if player_count >= 6 else 0)  # 최대 2명으로 제한
        citizen_count = player_count - mafia_count - police_count - doctor_count
        
        # 역할 리스트 생성
        roles = (
            [Role.MAFIA] * mafia_count +
            [Role.POLICE] * police_count +
            [Role.DOCTOR] * doctor_count +
            [Role.CITIZEN] * citizen_count
        )
        
        # 랜덤 배정
        random.shuffle(roles)
        random.shuffle(players)
        
        for player, role in zip(players, roles):
            player_data[player.id] = Player(user=player, role=role)
        
        return player_data
    
    async def check_night_actions_complete(self, channel_id: int) -> bool:
        """밤 행동이 모두 완료되었는지 확인"""
        if channel_id not in self.games:
            return False
            
        game_data = self.games[channel_id]
        actions = game_data["night_actions"]
        
        # 필요한 행동 수 계산
        required_actions = set()
        
        for player_id, player in game_data["players"].items():
            if not player.alive:
                continue
            
            if player.role == Role.MAFIA:
                required_actions.add(f"mafia_{player_id}")
            elif player.role == Role.POLICE:
                required_actions.add(f"police_{player_id}")
            elif player.role == Role.DOCTOR:
                required_actions.add(f"doctor_{player_id}")
        
        # 실제 행동과 비교
        completed_actions = set(actions.keys())
        
        return required_actions.issubset(completed_actions)
    
    async def start_game(self, interaction: discord.Interaction, players: List[discord.Member]):
        """게임 시작"""
        channel_id = interaction.channel_id
        
        if channel_id in self.games:
            try:
                await interaction.response.send_message(
                    "이미 진행 중인 게임이 있습니다!",
                    ephemeral=True
                )
            except InteractionResponded:
                await interaction.followup.send(
                    "이미 진행 중인 게임이 있습니다!",
                    ephemeral=True
                )
            return
        
        if not (self.MIN_PLAYERS <= len(players) <= self.MAX_PLAYERS):
            try:
                await interaction.response.send_message(
                    f"플레이어 수는 {self.MIN_PLAYERS}~{self.MAX_PLAYERS}명이어야 합니다!",
                    ephemeral=True
                )
            except InteractionResponded:
                await interaction.followup.send(
                    f"플레이어 수는 {self.MIN_PLAYERS}~{self.MAX_PLAYERS}명이어야 합니다!",
                    ephemeral=True
                )
            return
        
        # 게임 데이터 초기화
        player_data = self.assign_roles(players)
        
        game_data = {
            "channel": interaction.channel,
            "players": player_data,
            "phase": GamePhase.WAITING,
            "day": 0,  # 0일차로 시작 (첫 낮은 1일차가 됨)
            "night_actions": {},
            "day_votes": {},
            "game_log": [],
            "host": interaction.user.id  # 호스트 ID 저장
        }
        
        self.games[channel_id] = game_data
        
        # 역할 DM 전송
        for player_id, player in player_data.items():
            try:
                role_embed = discord.Embed(
                    title=f"당신의 역할: {player.role.value[1]} {player.role.value[0]}",
                    description=player.role.value[2],
                    color=discord.Color.red() if player.role == Role.MAFIA else discord.Color.blue()
                )
                
                # 마피아끼리는 서로 알려줌
                if player.role == Role.MAFIA:
                    other_mafias = [
                        p.game_name for p in player_data.values()
                        if p.role == Role.MAFIA and p.user.id != player_id
                    ]
                    if other_mafias:
                        role_embed.add_field(
                            name="동료 마피아",
                            value=", ".join(other_mafias),
                            inline=False
                        )
                
                await player.user.send(embed=role_embed)
            except:
                logger.warning(f"Failed to send DM to {player.game_name}")
        
        # 게임 시작 메시지
        start_embed = discord.Embed(
            title="🌙 마피아 게임 시작!",
            description=f"참가자: {len(players)}명\n"
                       f"각자 DM으로 역할을 확인하세요!\n"
                       f"**호스트**: {get_game_name(interaction.user)}",
            color=discord.Color.dark_purple()
        )
        
        # 역할 분포 표시
        role_counts = {}
        for player in player_data.values():
            role_name = player.role.value[0]
            role_counts[role_name] = role_counts.get(role_name, 0) + 1
        
        role_info = "\n".join([
            f"{role}: {count}명" 
            for role, count in role_counts.items()
        ])
        
        start_embed.add_field(
            name="역할 분포",
            value=role_info,
            inline=False
        )
        
        # 인터랙션 응답 처리
        try:
            await interaction.response.send_message(embed=start_embed)
        except InteractionResponded:
            # 이미 응답된 경우 채널에 직접 전송
            await interaction.channel.send(embed=start_embed)
        
        # 5초 후 첫 낮 토론 시작 (변경됨)
        await asyncio.sleep(5)
        game_data["day"] = 1  # 1일차로 설정
        await self.day_discussion_phase(channel_id)
    
    async def next_phase(self, channel_id: int):
        """다음 페이즈로 전환"""
        if channel_id not in self.games:
            return
        
        game_data = self.games[channel_id]
        current_phase = game_data["phase"]
        
        # 디버그 로그 추가
        logger.info(f"Transitioning from phase: {current_phase.value}")
        
        if current_phase == GamePhase.WAITING:
            await self.day_discussion_phase(channel_id)
        elif current_phase == GamePhase.NIGHT:
            await self.process_night_actions(channel_id)
        elif current_phase == GamePhase.DAY_DISCUSSION:
            await self.day_vote_phase(channel_id)
        elif current_phase == GamePhase.DAY_VOTE:
            await self.process_votes(channel_id)
        else:
            # 게임이 종료된 경우
            logger.warning(f"Cannot transition from phase: {current_phase.value}")
    
    async def night_phase(self, channel_id: int):
        """밤 페이즈"""
        if channel_id not in self.games:
            return
            
        game_data = self.games[channel_id]
        game_data["phase"] = GamePhase.NIGHT
        game_data["night_actions"] = {}
        
        # 보호 상태 초기화
        for player in game_data["players"].values():
            player.protected = False
        
        embed = discord.Embed(
            title=f"🌙 {game_data['day']}일차 밤",
            description="마피아, 경찰, 의사는 DM으로 행동을 선택하세요!\n"
                       f"시간 제한: 60초\n\n"
                       f"⚡ **모든 행동이 완료되면 자동으로 다음 페이즈로 넘어갑니다**\n"
                       f"호스트는 `/게임 마피아 action:페이즈전환`으로 강제 진행 가능합니다.",
            color=discord.Color.dark_purple()
        )
        
        # 새 메시지로 전송
        await game_data["channel"].send(embed=embed)
        
        # 역할별 행동 요청
        tasks = []
        for player_id, player in game_data["players"].items():
            if not player.alive:
                continue
            
            if player.role == Role.MAFIA:
                tasks.append(self.request_mafia_action(channel_id, player))
            elif player.role == Role.POLICE:
                tasks.append(self.request_police_action(channel_id, player))
            elif player.role == Role.DOCTOR:
                tasks.append(self.request_doctor_action(channel_id, player))
        
        # 행동 요청 동시 실행
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def handle_action_complete(self, channel_id: int):
        """행동 완료 시 처리"""
        if await self.check_night_actions_complete(channel_id):
            # 모든 행동이 완료되면 자동으로 다음 페이즈로
            game_data = self.games.get(channel_id)
            if game_data and game_data["phase"] == GamePhase.NIGHT:
                await asyncio.sleep(1)  # 잠시 대기
                await self.process_night_actions(channel_id)
    
    async def request_mafia_action(self, channel_id: int, mafia: Player):
        """마피아 행동 요청"""
        game_data = self.games[channel_id]
        
        # 생존자 목록 (마피아 제외)
        targets = [
            p for p in game_data["players"].values()
            if p.alive and p.role != Role.MAFIA
        ]
        
        if not targets:
            return
        
        embed = discord.Embed(
            title="🔫 마피아 행동",
            description="제거할 대상을 선택하세요:",
            color=discord.Color.red()
        )
        
        view = MafiaActionView(self, channel_id, mafia.user.id, targets)
        
        try:
            await mafia.user.send(embed=embed, view=view)
        except:
            logger.warning(f"Failed to send action request to {mafia.game_name}")
    
    async def request_police_action(self, channel_id: int, police: Player):
        """경찰 행동 요청"""
        game_data = self.games[channel_id]
        
        # 조사 가능 대상
        targets = [
            p for p in game_data["players"].values()
            if p.alive and p.user.id != police.user.id
        ]
        
        if not targets:
            return
        
        embed = discord.Embed(
            title="👮 경찰 조사",
            description="조사할 대상을 선택하세요:",
            color=discord.Color.blue()
        )
        
        view = PoliceActionView(self, channel_id, police.user.id, targets)
        
        try:
            await police.user.send(embed=embed, view=view)
        except:
            logger.warning(f"Failed to send action request to {police.game_name}")
    
    async def request_doctor_action(self, channel_id: int, doctor: Player):
        """의사 행동 요청"""
        game_data = self.games[channel_id]
        
        # 보호 가능 대상 (모든 생존자)
        targets = [
            p for p in game_data["players"].values()
            if p.alive
        ]
        
        if not targets:
            return
        
        embed = discord.Embed(
            title="👨‍⚕️ 의사 치료",
            description="보호할 대상을 선택하세요:",
            color=discord.Color.green()
        )
        
        view = DoctorActionView(self, channel_id, doctor.user.id, targets)
        
        try:
            await doctor.user.send(embed=embed, view=view)
        except:
            logger.warning(f"Failed to send action request to {doctor.game_name}")
    
    async def process_night_actions(self, channel_id: int):
        """밤 행동 처리"""
        if channel_id not in self.games:
            return
            
        game_data = self.games[channel_id]
        actions = game_data["night_actions"]
        
        # 의사 보호 처리
        for action_type, target_id in actions.items():
            if action_type.startswith("doctor_"):
                if target_id in game_data["players"]:
                    game_data["players"][target_id].protected = True
        
        # 마피아 공격 처리
        killed = None
        mafia_votes = {}
        
        for action_type, target_id in actions.items():
            if action_type.startswith("mafia_"):
                mafia_votes[target_id] = mafia_votes.get(target_id, 0) + 1
        
        if mafia_votes:
            # 가장 많은 표를 받은 대상
            target_id = max(mafia_votes, key=mafia_votes.get)
            target = game_data["players"].get(target_id)
            
            if target and target.alive and not target.protected:
                target.alive = False
                killed = target
        
        # 경찰 조사 결과
        for action_type, target_id in actions.items():
            if action_type.startswith("police_"):
                police_id = int(action_type.split("_")[1])
                target = game_data["players"].get(target_id)
                police = game_data["players"].get(police_id)
                
                if target and police and police.alive:
                    result = "마피아입니다!" if target.role == Role.MAFIA else "시민입니다!"
                    try:
                        await police.user.send(
                            f"조사 결과: {target.game_name}은(는) {result}"
                        )
                    except:
                        pass
        
        # 다음 날 증가
        game_data["day"] += 1
        
        # 아침 알림
        morning_embed = discord.Embed(
            title=f"☀️ {game_data['day']}일차 아침",
            color=discord.Color.gold()
        )
        
        if killed:
            morning_embed.add_field(
                name="밤사이 사망자",
                value=f"{killed.game_name} ({killed.role.value[0]})",
                inline=False
            )
            game_data["game_log"].append(
                f"Day {game_data['day']}: {killed.game_name} 사망"
            )
        else:
            morning_embed.add_field(
                name="평화로운 밤",
                value="아무도 죽지 않았습니다!",
                inline=False
            )
        
        # 생존자 수
        alive_players = [p for p in game_data["players"].values() if p.alive]
        mafia_count = len([p for p in alive_players if p.role == Role.MAFIA])
        citizen_count = len(alive_players) - mafia_count
        
        morning_embed.add_field(
            name="생존자",
            value=f"총 {len(alive_players)}명 (마피아 {mafia_count}명)",
            inline=False
        )
        
        # 새 메시지로 전송
        await game_data["channel"].send(embed=morning_embed)
        
        # 게임 종료 체크
        if mafia_count >= citizen_count:
            await self.end_game(channel_id, "마피아")
        elif mafia_count == 0:
            await self.end_game(channel_id, "시민")
        else:
            # 낮 토론으로 전환
            await asyncio.sleep(5)
            await self.day_discussion_phase(channel_id)
    
    async def day_discussion_phase(self, channel_id: int):
        """낮 토론 페이즈"""
        if channel_id not in self.games:
            return
            
        game_data = self.games[channel_id]
        game_data["phase"] = GamePhase.DAY_DISCUSSION
        
        embed = discord.Embed(
            title=f"☀️ {game_data['day']}일차 낮 - 토론 시간",
            description="마피아로 의심되는 사람에 대해 토론하세요!\n"
                       f"시간 제한: 90초\n\n"
                       f"호스트는 `/게임 마피아 action:페이즈전환`으로 투표를 시작할 수 있습니다.",
            color=discord.Color.gold()
        )
        
        # 새 메시지로 전송
        await game_data["channel"].send(embed=embed)
    
    async def day_vote_phase(self, channel_id: int):
        """낮 투표 페이즈"""
        if channel_id not in self.games:
            logger.error(f"No game found for channel {channel_id}")
            return
            
        game_data = self.games[channel_id]
        game_data["phase"] = GamePhase.DAY_VOTE
        game_data["day_votes"] = {}
        game_data["abstain_count"] = 0  # 기권 카운트 초기화
        
        # 투표 초기화
        for player in game_data["players"].values():
            player.votes = 0
        
        # 생존한 플레이어 목록
        alive_players = [p for p in game_data["players"].values() if p.alive]
        alive_count = len(alive_players)
        
        if alive_count == 0:
            logger.error("No alive players found")
            return
        
        # 투표 안내 임베드
        embed = discord.Embed(
            title=f"🗳️ {game_data['day']}일차 낮 - 투표 시간",
            description="마피아로 의심되는 사람을 투표하세요!\n"
                    f"**💡 투표 변경 가능!**\n\n"
                    f"• 같은 버튼을 다시 누르면 투표 취소\n"
                    f"• 다른 버튼을 누르면 투표 변경\n"
                    f"• 기권도 취소 가능\n\n"
                    f"{'⚠️ 생존자가 20명을 초과하여 일부만 표시됩니다.' if alive_count > 20 else ''}\n"
                    f"시간 제한: 60초\n"
                    f"호스트는 `/게임 마피아 action:페이즈전환`으로 투표를 종료할 수 있습니다.",
            color=discord.Color.orange()
        )
        
        # 생존자 목록 표시
        embed.add_field(
            name=f"생존자 ({alive_count}명)",
            value=", ".join([p.game_name for p in alive_players[:10]]) + 
                (f" 외 {alive_count - 10}명" if alive_count > 10 else ""),
            inline=False
        )
        
        # 투표 뷰 생성
        view = VoteView(self, channel_id, alive_players)
        
        # 메시지 전송
        try:
            message = await game_data["channel"].send(embed=embed, view=view)
            game_data["vote_message"] = message
            logger.info(f"Vote phase started for channel {channel_id}")
        except Exception as e:
            logger.error(f"Failed to send vote message: {e}")
            return
        
        # 60초 후 자동으로 투표 종료
        await asyncio.sleep(60)
        
        # 게임이 여전히 존재하고 투표 페이즈인지 확인
        if channel_id in self.games and self.games[channel_id]["phase"] == GamePhase.DAY_VOTE:
            await self.process_votes(channel_id)

    async def process_votes(self, channel_id: int):
        """투표 결과 처리"""
        if channel_id not in self.games:
            logger.error(f"No game found for channel {channel_id}")
            return
            
        game_data = self.games[channel_id]
        
        # 투표 뷰 비활성화
        if "vote_message" in game_data and game_data["vote_message"]:
            try:
                await game_data["vote_message"].edit(view=None)
            except Exception as e:
                logger.warning(f"Failed to disable vote view: {e}")
        
        # 생존한 플레이어 목록
        alive_players = [p for p in game_data["players"].values() if p.alive]
        
        if not alive_players:
            logger.error("No alive players to process votes")
            return
        
        # 최다 득표자 찾기
        max_votes = max((p.votes for p in alive_players), default=0)
        abstain_count = game_data.get("abstain_count", 0)
        
        # 투표 결과 임베드 생성
        result_embed = discord.Embed(
            title="⚖️ 투표 결과",
            color=discord.Color.red()
        )
        
        eliminated = None
        
        if max_votes > 0:
            # 최다 득표자들 찾기
            candidates = [p for p in alive_players if p.votes == max_votes]
            
            # 동점일 경우 랜덤 선택
            eliminated = random.choice(candidates)
            eliminated.alive = False
            
            result_embed.description = f"**{eliminated.game_name}**님이 처형되었습니다!\n"
            result_embed.add_field(
                name="정보",
                value=f"역할: **{eliminated.role.value[1]} {eliminated.role.value[0]}**\n"
                    f"득표수: {eliminated.votes}표\n"
                    f"기권: {abstain_count}표",
                inline=False
            )
            
            # 게임 로그에 기록
            game_data["game_log"].append(
                f"Day {game_data['day']} Vote: {eliminated.game_name} ({eliminated.role.value[0]}) 처형 - {eliminated.votes}표"
            )
            
            logger.info(f"Player {eliminated.game_name} eliminated with {eliminated.votes} votes")
        else:
            result_embed.description = "아무도 처형되지 않았습니다."
            result_embed.add_field(
                name="투표 결과",
                value=f"최다 득표: 0표\n기권: {abstain_count}표",
                inline=False
            )
            
            game_data["game_log"].append(
                f"Day {game_data['day']} Vote: 아무도 처형되지 않음 (기권 {abstain_count}표)"
            )
            
            logger.info("No one was eliminated in the vote")
        
        # 현재 생존자 상태
        alive_players = [p for p in game_data["players"].values() if p.alive]
        mafia_count = len([p for p in alive_players if p.role == Role.MAFIA])
        citizen_count = len(alive_players) - mafia_count
        
        result_embed.add_field(
            name="생존자 현황",
            value=f"총 {len(alive_players)}명 (마피아 ???명)",
            inline=False
        )
        
        # 투표 결과 메시지 전송
        try:
            await game_data["channel"].send(embed=result_embed)
        except Exception as e:
            logger.error(f"Failed to send vote result: {e}")
            return
        
        # 기권 카운트 초기화
        game_data["abstain_count"] = 0
        
        # 게임 종료 체크
        if mafia_count >= citizen_count:
            logger.info(f"Game over - Mafia wins (Mafia: {mafia_count}, Citizens: {citizen_count})")
            await asyncio.sleep(3)
            await self.end_game(channel_id, "마피아")
        elif mafia_count == 0:
            logger.info("Game over - Citizens win (No mafia left)")
            await asyncio.sleep(3)
            await self.end_game(channel_id, "시민")
        else:
            # 게임 계속 - 밤 페이즈로 전환
            logger.info(f"Game continues - transitioning to night phase (Mafia: {mafia_count}, Citizens: {citizen_count})")
            await asyncio.sleep(5)
            await self.night_phase(channel_id)

    async def end_game(self, channel_id: int, winner: str):
        """게임 종료"""
        if channel_id not in self.games:
            return
            
        game_data = self.games[channel_id]
        game_data["phase"] = GamePhase.GAME_OVER
        
        # 승리팀 결정
        if winner == "마피아":
            winners = [p for p in game_data["players"].values() if p.role == Role.MAFIA]
            color = discord.Color.red()
        else:
            winners = [p for p in game_data["players"].values() if p.role != Role.MAFIA]
            color = discord.Color.blue()
        
        # 결과 임베드
        result_embed = discord.Embed(
            title=f"🎉 {winner} 팀 승리!",
            color=color
        )
        
        # 전체 플레이어 정보
        player_info = ""
        for player in game_data["players"].values():
            status = "생존" if player.alive else "사망"
            player_info += f"{player.game_name}: {player.role.value[0]} ({status})\n"
        
        result_embed.add_field(
            name="플레이어 정보",
            value=player_info,
            inline=False
        )
        
        # 게임 로그
        if game_data["game_log"]:
            log_text = "\n".join(game_data["game_log"][-5:])  # 최근 5개
            result_embed.add_field(
                name="게임 진행 기록",
                value=log_text,
                inline=False
            )
        
        # 새 메시지로 전송
        await game_data["channel"].send(embed=result_embed)
        
        # 게임 데이터 정리
        del self.games[channel_id]

# UI 컴포넌트들
class MafiaJoinView(discord.ui.View):
    def __init__(self, game: MafiaGame, host: discord.Member = None):
        super().__init__(timeout=None)  # 시간 제한 없음
        self.game = game
        self.host = host
        self.participants = []
        
        # 호스트 자동 참가
        if host:
            self.participants.append(host)
    
    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, emoji="🔫")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants:
            await interaction.response.send_message(
                "이미 참가하셨습니다!",
                ephemeral=True
            )
            return
        
        if len(self.participants) >= self.game.MAX_PLAYERS:
            await interaction.response.send_message(
                f"최대 인원({self.game.MAX_PLAYERS}명)에 도달했습니다!",
                ephemeral=True
            )
            return
        
        self.participants.append(interaction.user)
        
        # 현재 참가자 수를 임베드에 업데이트
        embed = interaction.message.embeds[0]
        embed.set_field_at(
            0,  # "현재 참가자" 필드의 인덱스
            name="현재 참가자",
            value=f"**{len(self.participants)}명** / {self.game.MAX_PLAYERS}명",
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed)
        
        # 참가 알림
        await interaction.followup.send(
            f"{get_game_name(interaction.user)}님이 참가했습니다!",
            ephemeral=False
        )
    
    @discord.ui.button(label="게임 시작", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 호스트만 시작 가능
        if self.host and interaction.user.id != self.host.id:
            await interaction.response.send_message(
                "게임 호스트만 시작할 수 있습니다!",
                ephemeral=True
            )
            return
        
        if len(self.participants) < self.game.MIN_PLAYERS:
            await interaction.response.send_message(
                f"최소 {self.game.MIN_PLAYERS}명이 필요합니다! (현재 {len(self.participants)}명)",
                ephemeral=True
            )
            return
        
        # 버튼 비활성화
        for item in self.children:
            item.disabled = True
        
        # 메시지 업데이트
        try:
            await interaction.response.edit_message(view=self)
        except InteractionResponded:
            await interaction.message.edit(view=self)
        
        # 게임 시작 (별도의 태스크로 실행)
        asyncio.create_task(self.game.start_game(interaction, self.participants))
        self.stop()

class MafiaActionView(discord.ui.View):
    def __init__(self, game: MafiaGame, channel_id: int, mafia_id: int, targets: List[Player]):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.mafia_id = mafia_id
        
        # 대상 선택 드롭다운
        options = [
            discord.SelectOption(
                label=target.game_name,
                value=str(target.user.id)
            )
            for target in targets[:25]
        ]
        
        select = discord.ui.Select(
            placeholder="제거할 대상을 선택하세요",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.mafia_id:
            return
        
        target_id = int(interaction.data["values"][0])
        
        # 마피아 액션 저장
        game_data = self.game.games[self.channel_id]
        game_data["night_actions"][f"mafia_{self.mafia_id}"] = target_id
        
        await interaction.response.send_message(
            "대상을 선택했습니다.",
            ephemeral=True
        )
        self.stop()
        
        # 모든 행동 완료 확인
        await self.game.handle_action_complete(self.channel_id)

class PoliceActionView(discord.ui.View):
    def __init__(self, game: MafiaGame, channel_id: int, police_id: int, targets: List[Player]):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.police_id = police_id
        
        # 대상 선택 드롭다운
        options = [
            discord.SelectOption(
                label=target.game_name,
                value=str(target.user.id)
            )
            for target in targets[:25]
        ]
        
        select = discord.ui.Select(
            placeholder="조사할 대상을 선택하세요",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.police_id:
            return
        
        target_id = int(interaction.data["values"][0])
        
        # 경찰 액션 저장
        game_data = self.game.games[self.channel_id]
        game_data["night_actions"][f"police_{self.police_id}"] = target_id
        
        await interaction.response.send_message(
            "조사를 시작합니다...",
            ephemeral=True
        )
        self.stop()
        
        # 모든 행동 완료 확인
        await self.game.handle_action_complete(self.channel_id)

class DoctorActionView(discord.ui.View):
    def __init__(self, game: MafiaGame, channel_id: int, doctor_id: int, targets: List[Player]):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.doctor_id = doctor_id
        
        # 대상 선택 드롭다운
        options = [
            discord.SelectOption(
                label=target.game_name,
                value=str(target.user.id)
            )
            for target in targets[:25]
        ]
        
        select = discord.ui.Select(
            placeholder="보호할 대상을 선택하세요",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.doctor_id:
            return
        
        target_id = int(interaction.data["values"][0])
        
        # 의사 액션 저장
        game_data = self.game.games[self.channel_id]
        game_data["night_actions"][f"doctor_{self.doctor_id}"] = target_id
        
        await interaction.response.send_message(
            "치료 준비를 완료했습니다.",
            ephemeral=True
        )
        self.stop()
        
        # 모든 행동 완료 확인
        await self.game.handle_action_complete(self.channel_id)

class VoteView(discord.ui.View):
    def __init__(self, game: MafiaGame, channel_id: int, targets: List[Player]):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.voted_users = {}  # set에서 dict로 변경 {user_id: target_id or "abstain"}
        
        # 투표 대상 버튼들
        for target in targets[:20]:  # 최대 20명
            button = VoteButton(target)
            self.add_item(button)
        
        # 기권 버튼 추가
        abstain_button = discord.ui.Button(
            label="기권 (0표)",
            style=discord.ButtonStyle.secondary,
            emoji="🚫",
            custom_id="abstain"
        )
        abstain_button.callback = self.abstain_callback
        self.add_item(abstain_button)
    
    async def abstain_callback(self, interaction: discord.Interaction):
        """기권 처리"""
        user_id = interaction.user.id
        game_data = self.game.games.get(self.channel_id)
        
        if not game_data:
            return
        
        # 이미 기권한 경우 - 취소
        if user_id in self.voted_users and self.voted_users[user_id] == "abstain":
            del self.voted_users[user_id]
            game_data["abstain_count"] = max(0, game_data.get("abstain_count", 1) - 1)
            
            # 버튼 라벨 업데이트
            for item in self.children:
                if hasattr(item, 'custom_id') and item.custom_id == "abstain":
                    item.label = f"기권 ({game_data.get('abstain_count', 0)}표)"
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("기권을 취소했습니다.", ephemeral=True)
            return
        
        # 다른 투표를 한 경우 - 이전 투표 취소
        if user_id in self.voted_users and self.voted_users[user_id] != "abstain":
            previous_target_id = self.voted_users[user_id]
            if previous_target_id in game_data["players"]:
                game_data["players"][previous_target_id].votes -= 1
                
                # 해당 버튼 라벨 업데이트
                for item in self.children:
                    if isinstance(item, VoteButton) and item.target.user.id == previous_target_id:
                        item.label = f"{item.target.game_name} ({item.target.votes}표)"
        
        # 기권 처리
        self.voted_users[user_id] = "abstain"
        
        if "abstain_count" not in game_data:
            game_data["abstain_count"] = 0
        game_data["abstain_count"] += 1
        
        # 버튼 라벨 업데이트
        for item in self.children:
            if hasattr(item, 'custom_id') and item.custom_id == "abstain":
                item.label = f"기권 ({game_data['abstain_count']}표)"
        
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("투표를 기권했습니다.", ephemeral=True)

class VoteButton(discord.ui.Button):
    def __init__(self, target: Player):
        super().__init__(
            label=f"{target.game_name} ({target.votes}표)",
            style=discord.ButtonStyle.primary
        )
        self.target = target
    
    async def callback(self, interaction: discord.Interaction):
        view: VoteView = self.view
        user_id = interaction.user.id
        game_data = view.game.games.get(view.channel_id)
        
        if not game_data:
            return
        
        # 같은 버튼을 다시 누른 경우 - 투표 취소
        if user_id in view.voted_users and view.voted_users[user_id] == self.target.user.id:
            del view.voted_users[user_id]
            self.target.votes -= 1
            self.label = f"{self.target.game_name} ({self.target.votes}표)"
            
            await interaction.response.edit_message(view=view)
            await interaction.followup.send("투표를 취소했습니다.", ephemeral=True)
            return
        
        # 이전에 다른 투표를 한 경우
        if user_id in view.voted_users:
            previous_vote = view.voted_users[user_id]
            
            # 기권을 취소하는 경우
            if previous_vote == "abstain":
                game_data["abstain_count"] = max(0, game_data.get("abstain_count", 1) - 1)
                # 기권 버튼 라벨 업데이트
                for item in view.children:
                    if hasattr(item, 'custom_id') and item.custom_id == "abstain":
                        item.label = f"기권 ({game_data.get('abstain_count', 0)}표)"
            
            # 다른 플레이어 투표를 취소하는 경우
            elif previous_vote in game_data["players"]:
                game_data["players"][previous_vote].votes -= 1
                # 해당 버튼 라벨 업데이트
                for item in view.children:
                    if isinstance(item, VoteButton) and item.target.user.id == previous_vote:
                        item.label = f"{item.target.game_name} ({item.target.votes}표)"
        
        # 새로운 투표
        view.voted_users[user_id] = self.target.user.id
        self.target.votes += 1
        self.label = f"{self.target.game_name} ({self.target.votes}표)"
        
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(f"{self.target.game_name}에게 투표했습니다.", ephemeral=True)

# 전역 게임 인스턴스
mafia_game = MafiaGame()

def get_mafia_game():
    return mafia_game