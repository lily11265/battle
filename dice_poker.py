# dice_poker.py
import discord
from discord import app_commands
import asyncio
import random
import logging
from typing import Dict, List, Optional, Tuple, Set
from collections import Counter
from enum import Enum
from dataclasses import dataclass, field
from utility import get_user_inventory

logger = logging.getLogger(__name__)

class HandRank(Enum):
    """족보 등급 (높은 숫자가 더 높은 등급)"""
    HIGH_CARD = 1
    ONE_PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    FIVE_OF_A_KIND = 8

class BettingAction(Enum):
    """베팅 액션"""
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    FOLD = "fold"

class GamePhase(Enum):
    """게임 진행 단계"""
    WAITING = "waiting"
    INITIAL_ROLL = "initial_roll"
    FIRST_BETTING = "first_betting"
    REROLL_1 = "reroll_1"
    REROLL_2 = "reroll_2"
    FINAL_BETTING = "final_betting"
    SHOWDOWN = "showdown"
    FINISHED = "finished"

@dataclass
class PlayerHand:
    """플레이어 핸드 정보"""
    dice: List[int] = field(default_factory=list)
    reroll_count: int = 0
    folded: bool = False
    all_in: bool = False
    current_bet: int = 0
    total_bet: int = 0

class DicePokerGame:
    def __init__(self, interaction: discord.Interaction, players: List[discord.Member], 
                 bet_amounts: Dict[int, int], bot_instance):
        self.interaction = interaction
        self.players = players
        self.initial_bets = bet_amounts
        self.bot = bot_instance
        
        # 게임 상태
        self.phase = GamePhase.WAITING
        self.current_turn = 0
        self.pot = sum(bet_amounts.values())
        self.current_bet = 0
        self.min_raise = 1
        
        # 플레이어 정보
        self.player_hands: Dict[int, PlayerHand] = {
            player.id: PlayerHand(total_bet=bet_amounts[player.id]) 
            for player in players
        }
        self.active_players = [p.id for p in players]
        
        # 메시지 관리
        self.game_message: Optional[discord.Message] = None
        self.current_view: Optional[discord.ui.View] = None
        
        # 타임아웃 관리
        self.timeout_tasks: Dict[int, asyncio.Task] = {}
        
    def roll_dice(self, count: int = 5) -> List[int]:
        """주사위 굴리기"""
        return [random.randint(1, 6) for _ in range(count)]
    
    def evaluate_hand(self, dice: List[int]) -> Tuple[HandRank, int]:
        """손패 평가 - 족보와 합계 반환"""
        if not dice or len(dice) != 5:
            return HandRank.HIGH_CARD, 0
            
        counter = Counter(dice)
        counts = sorted(counter.values(), reverse=True)
        dice_sum = sum(dice)
        
        # Five of a Kind
        if counts[0] == 5:
            return HandRank.FIVE_OF_A_KIND, dice_sum
        
        # Four of a Kind
        if counts[0] == 4:
            return HandRank.FOUR_OF_A_KIND, dice_sum
        
        # Full House
        if counts[0] == 3 and counts[1] == 2:
            return HandRank.FULL_HOUSE, dice_sum
        
        # Straight
        sorted_dice = sorted(dice)
        if sorted_dice == [1, 2, 3, 4, 5] or sorted_dice == [2, 3, 4, 5, 6]:
            return HandRank.STRAIGHT, dice_sum
        
        # Three of a Kind
        if counts[0] == 3:
            return HandRank.THREE_OF_A_KIND, dice_sum
        
        # Two Pair
        if counts[0] == 2 and counts[1] == 2:
            return HandRank.TWO_PAIR, dice_sum
        
        # One Pair
        if counts[0] == 2:
            return HandRank.ONE_PAIR, dice_sum
        
        # High Card
        return HandRank.HIGH_CARD, dice_sum
    
    def format_dice(self, dice: List[int]) -> str:
        """주사위 포맷팅"""
        dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        return " ".join([dice_emojis.get(d, str(d)) for d in dice])
    
    def get_hand_name(self, rank: HandRank) -> str:
        """족보 이름 반환"""
        names = {
            HandRank.HIGH_CARD: "하이 카드",
            HandRank.ONE_PAIR: "원 페어",
            HandRank.TWO_PAIR: "투 페어",
            HandRank.THREE_OF_A_KIND: "쓰리 오브 어 카인드",
            HandRank.STRAIGHT: "스트레이트",
            HandRank.FULL_HOUSE: "풀 하우스",
            HandRank.FOUR_OF_A_KIND: "포 오브 어 카인드",
            HandRank.FIVE_OF_A_KIND: "파이브 오브 어 카인드"
        }
        return names.get(rank, "알 수 없음")
    
    async def create_game_embed(self, show_all_dice: bool = False) -> discord.Embed:
        """게임 상태 임베드 생성 (주사위 숨김 기능 추가)"""
        embed = discord.Embed(
            title="🎲 주사위 포커",
            color=discord.Color.blue()
        )
        
        # 게임 정보
        phase_names = {
            GamePhase.WAITING: "대기 중",
            GamePhase.INITIAL_ROLL: "주사위 굴리기",
            GamePhase.FIRST_BETTING: "첫 번째 베팅",
            GamePhase.REROLL_1: "첫 번째 리롤",
            GamePhase.REROLL_2: "두 번째 리롤",
            GamePhase.FINAL_BETTING: "최종 베팅",
            GamePhase.SHOWDOWN: "결과 공개",
            GamePhase.FINISHED: "게임 종료"
        }
        
        embed.add_field(
            name="게임 정보",
            value=f"단계: {phase_names.get(self.phase, '알 수 없음')}\n"
                  f"팟: {self.pot:,}💰\n"
                  f"현재 베팅: {self.current_bet:,}💰",
            inline=False
        )
        
        # 플레이어 정보
        for player in self.players:
            player_id = player.id
            hand = self.player_hands[player_id]
            
            if hand.folded:
                status = "❌ 폴드"
            elif player_id not in self.active_players:
                status = "⏳ 대기 중"
            elif self.current_turn < len(self.players) and self.players[self.current_turn].id == player_id:
                status = "🎯 **현재 차례**"
            else:
                status = "✅ 진행 중"
            
            # 주사위 표시 (숨김 처리)
            if hand.dice:
                # 쇼다운이거나 show_all_dice가 True일 때만 모든 주사위 공개
                if show_all_dice or self.phase in [GamePhase.SHOWDOWN, GamePhase.FINISHED]:
                    dice_str = self.format_dice(hand.dice)
                    rank, total = self.evaluate_hand(hand.dice)
                    hand_info = f"{dice_str}\n{self.get_hand_name(rank)} (합계: {total})"
                else:
                    # 그 외에는 주사위 숨김
                    hand_info = "🎲 ? ? ? ? ?"
                    if hand.reroll_count > 0:
                        hand_info += f"\n(리롤: {hand.reroll_count}회)"
            else:
                hand_info = "주사위 대기 중..."
            
            # 베팅 정보
            from utility import get_user_inventory
            user_data = await get_user_inventory(str(player_id))
            balance = user_data.get("coins", 0) if user_data else 0
            
            player_info = f"{status}\n"
            player_info += f"💰 잔액: {balance:,} / 베팅: {hand.total_bet:,}\n"
            player_info += f"🎲 {hand_info}"
            
            embed.add_field(
                name=f"{player.display_name}",
                value=player_info,
                inline=True
            )
        
        return embed
    
    
    async def start_game(self):
        """게임 시작"""
        try:
            # 초기 메시지
            embed = await self.create_game_embed()
            self.game_message = await self.interaction.followup.send(embed=embed)
            
            # 초기 주사위 굴리기 단계
            await self.initial_roll_phase()
            
            # 첫 번째 베팅 라운드
            if len(self.active_players) > 1:
                await self.betting_round()
            
            # 리롤 단계 (2번)
            for i in range(2):
                if len(self.active_players) > 1:
                    await self.reroll_phase(i + 1)
            
            # 최종 베팅 라운드
            if len(self.active_players) > 1:
                self.phase = GamePhase.FINAL_BETTING
                await self.betting_round()
            
            # 쇼다운
            await self.showdown()
            
        except Exception as e:
            logger.error(f"게임 진행 중 오류: {e}")
            await self.game_message.edit(
                content="게임 진행 중 오류가 발생했습니다.",
                embed=None,
                view=None
            )
    
    async def initial_roll_phase(self):
        """초기 주사위 굴리기 (수정됨)"""
        self.phase = GamePhase.INITIAL_ROLL
        
        for i, player in enumerate(self.players):
            if player.id not in self.active_players:
                continue
                
            self.current_turn = i
            embed = await self.create_game_embed()  # 주사위 숨김
            
            # 굴리기 버튼
            view = RollDiceView(self, player)
            await self.game_message.edit(embed=embed, view=view)
            
            # 타임아웃 설정 (1분)
            timeout_task = asyncio.create_task(
                self.handle_timeout(player.id, "roll")
            )
            self.timeout_tasks[player.id] = timeout_task
            
            # 대기
            await view.wait()
            
            # 타임아웃 태스크 취소
            if player.id in self.timeout_tasks:
                self.timeout_tasks[player.id].cancel()
                del self.timeout_tasks[player.id]
            
            # 업데이트된 상태 표시 (여전히 주사위는 숨김)
            embed = await self.create_game_embed()
            await self.game_message.edit(embed=embed, view=None)
            
            await asyncio.sleep(1)
    
    async def betting_round(self):
        """베팅 라운드"""
        if self.phase == GamePhase.INITIAL_ROLL:
            self.phase = GamePhase.FIRST_BETTING
        
        # 리롤 후 최종 베팅에서는 current_bet을 0으로 리셋하여 체크 가능하게 함
        if self.phase == GamePhase.FINAL_BETTING:
            self.current_bet = 0
            # 모든 플레이어의 current_bet도 리셋
            for player_id in self.active_players:
                self.player_hands[player_id].current_bet = 0
        
        betting_complete = False
        players_acted = set()
                
        while not betting_complete:
            betting_complete = True
            
            for i, player in enumerate(self.players):
                player_id = player.id
                
                if player_id not in self.active_players:
                    continue
                
                hand = self.player_hands[player_id]
                if hand.folded or hand.all_in:
                    continue
                
                # 현재 베팅에 맞춰야 하는지 확인
                if hand.current_bet < self.current_bet or player_id not in players_acted:
                    betting_complete = False
                    self.current_turn = i
                    
                    # 베팅 옵션 표시
                    embed = await self.create_game_embed()
                    view = BettingView(self, player)
                    await self.game_message.edit(embed=embed, view=view)
                    
                    # 타임아웃 설정
                    timeout_task = asyncio.create_task(
                        self.handle_timeout(player_id, "bet")
                    )
                    self.timeout_tasks[player_id] = timeout_task
                    
                    # 대기
                    await view.wait()
                    
                    # 타임아웃 취소
                    if player_id in self.timeout_tasks:
                        self.timeout_tasks[player_id].cancel()
                        del self.timeout_tasks[player_id]
                    
                    players_acted.add(player_id)
                    
                    # 모두 폴드했는지 확인
                    if len(self.active_players) == 1:
                        return
    
    async def reroll_phase(self, reroll_num: int):
        """리롤 단계"""
        if reroll_num == 1:
            self.phase = GamePhase.REROLL_1
        else:
            self.phase = GamePhase.REROLL_2
        
        for i, player in enumerate(self.players):
            if player.id not in self.active_players:
                continue
            
            hand = self.player_hands[player.id]
            if hand.folded:
                continue
            
            self.current_turn = i
            
            # 리롤 모달 표시
            embed = await self.create_game_embed()
            view = RerollView(self, player)
            await self.game_message.edit(embed=embed, view=view)
            
            # 타임아웃 설정
            timeout_task = asyncio.create_task(
                self.handle_timeout(player.id, "reroll")
            )
            self.timeout_tasks[player.id] = timeout_task
            
            # 대기
            await view.wait()
            
            # 타임아웃 취소
            if player.id in self.timeout_tasks:
                self.timeout_tasks[player.id].cancel()
                del self.timeout_tasks[player.id]
    
    async def handle_timeout(self, player_id: int, action_type: str):
        """타임아웃 처리"""
        await asyncio.sleep(60)  # 1분 대기
        
        hand = self.player_hands[player_id]
        
        if action_type == "roll":
            # 랜덤으로 주사위 굴리기
            hand.dice = self.roll_dice()
            
        elif action_type == "bet":
            # 자동으로 Call
            await self.handle_call(player_id)
            
        elif action_type == "reroll":
            # 리롤하지 않음
            pass
        
        # 현재 뷰 종료
        if self.current_view:
            self.current_view.stop()
    
    async def handle_check(self, player_id: int):
        """체크 처리"""
        hand = self.player_hands[player_id]
        if self.current_bet > hand.current_bet:
            return False  # 체크 불가
        return True
    
    async def handle_call(self, player_id: int):
        """콜 처리"""
        hand = self.player_hands[player_id]
        call_amount = self.current_bet - hand.current_bet
        
        # 잔액 확인
        from utility import get_user_inventory
        user_data = await get_user_inventory(str(player_id))
        balance = user_data.get("coins", 0) if user_data else 0
        
        if balance < call_amount:
            # All-in
            call_amount = balance
            hand.all_in = True
        
        hand.current_bet += call_amount
        hand.total_bet += call_amount
        self.pot += call_amount
        
        return True
    
    async def handle_raise(self, player_id: int, raise_amount: int):
        """레이즈 처리"""
        hand = self.player_hands[player_id]
        
        # 최소 레이즈 금액 확인
        min_raise_total = self.current_bet + self.min_raise
        if hand.current_bet + raise_amount < min_raise_total:
            return False
        
        # 잔액 확인
        from utility import get_user_inventory
        user_data = await get_user_inventory(str(player_id))
        balance = user_data.get("coins", 0) if user_data else 0
        
        if balance < raise_amount:
            return False
        
        hand.current_bet += raise_amount
        hand.total_bet += raise_amount
        self.pot += raise_amount
        self.current_bet = hand.current_bet
        
        return True
    
    async def handle_fold(self, player_id: int):
        """폴드 처리"""
        hand = self.player_hands[player_id]
        hand.folded = True
        self.active_players.remove(player_id)
        return True
    
    async def showdown(self):
        """쇼다운 - 승자 결정 (수정됨)"""
        self.phase = GamePhase.SHOWDOWN
        
        # 쇼다운 시작 알림
        embed = await self.create_game_embed(show_all_dice=False)
        embed.add_field(
            name="🎰 쇼다운!",
            value="모든 플레이어의 주사위를 공개합니다...",
            inline=False
        )
        await self.game_message.edit(embed=embed, view=None)
        await asyncio.sleep(2)  # 긴장감을 위한 딜레이
        
        # 주사위 공개
        embed = await self.create_game_embed(show_all_dice=True)
        await self.game_message.edit(embed=embed, view=None)
        await asyncio.sleep(1)
        
        # 남은 플레이어들의 핸드 평가
        player_results = []
        for player_id in self.active_players:
            hand = self.player_hands[player_id]
            if not hand.folded and hand.dice:
                rank, total = self.evaluate_hand(hand.dice)
                player_results.append((player_id, rank, total))
        
        # 승자 결정 (족보 등급 → 합계 순)
        player_results.sort(key=lambda x: (x[1].value, x[2]), reverse=True)
        
        # 동점자 처리 및 팟 분배
        winners = []
        if player_results:
            best_rank = player_results[0][1]
            best_total = player_results[0][2]
            
            for player_id, rank, total in player_results:
                if rank == best_rank and total == best_total:
                    winners.append(player_id)
                else:
                    break
        
        # 팟 분배
        if winners:
            prize_per_winner = self.pot // len(winners)
            remainder = self.pot % len(winners)
            
            # 잔액 업데이트
            from utility import update_user_inventory
            for i, winner_id in enumerate(winners):
                prize = prize_per_winner
                if i == 0:  # 첫 번째 승자가 나머지 받음
                    prize += remainder
                
                # 순수익 계산 (상금 - 베팅액)
                net_profit = prize - self.player_hands[winner_id].total_bet
                
                winner = next(p for p in self.players if p.id == winner_id)
                user_data = await get_user_inventory(str(winner_id))
                if user_data:
                    new_balance = user_data.get("coins", 0) + net_profit
                    await update_user_inventory(
                        str(winner_id),
                        coins=new_balance
                    )
        
        # 패자들의 베팅액 차감
        for player in self.players:
            if player.id not in winners:
                hand = self.player_hands[player.id]
                if hand.total_bet > 0:
                    user_data = await get_user_inventory(str(player.id))
                    if user_data:
                        new_balance = max(0, user_data.get("coins", 0) - hand.total_bet)
                        await update_user_inventory(
                            str(player.id),
                            coins=new_balance
                        )
        
        # 최종 결과 표시
        self.phase = GamePhase.FINISHED
        embed = await self.create_final_embed(winners)
        await self.game_message.edit(embed=embed, view=None)
    
    async def create_final_embed(self, winners: List[int]) -> discord.Embed:
        """최종 결과 임베드"""
        embed = discord.Embed(
            title="🎲 주사위 포커 - 게임 종료",
            color=discord.Color.gold()
        )
        
        # 승자 정보
        if winners:
            winner_names = []
            for winner_id in winners:
                winner = next(p for p in self.players if p.id == winner_id)
                winner_names.append(winner.display_name)
            
            prize_per_winner = self.pot // len(winners)
            embed.add_field(
                name="🏆 승자",
                value=f"{', '.join(winner_names)}\n상금: {prize_per_winner:,}💰",
                inline=False
            )
        
        # 모든 플레이어 결과
        results = []
        for player in self.players:
            hand = self.player_hands[player.id]
            if hand.dice:
                rank, total = self.evaluate_hand(hand.dice)
                dice_str = self.format_dice(hand.dice)
                
                status = ""
                if hand.folded:
                    status = "❌ 폴드"
                elif player.id in winners:
                    status = "🏆 승리!"
                else:
                    status = "💔 패배"
                
                results.append(
                    f"**{player.display_name}** {status}\n"
                    f"{dice_str}\n"
                    f"{self.get_hand_name(rank)} (합계: {total})\n"
                    f"베팅액: {hand.total_bet:,}💰"
                )
        
        embed.add_field(
            name="📊 최종 결과",
            value="\n\n".join(results),
            inline=False
        )
        
        embed.add_field(
            name="💰 총 팟",
            value=f"{self.pot:,}💰",
            inline=False
        )
        
        return embed

# UI 컴포넌트들
class RollDiceView(discord.ui.View):
    def __init__(self, game: DicePokerGame, player: discord.Member):
        super().__init__(timeout=60)
        self.game = game
        self.player = player
    
    @discord.ui.button(label="주사위 굴리기", style=discord.ButtonStyle.primary, emoji="🎲")
    async def roll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        # 주사위 굴리기
        hand = self.game.player_hands[self.player.id]
        hand.dice = self.game.roll_dice()
        
        # 자신의 주사위만 ephemeral로 표시
        dice_str = self.game.format_dice(hand.dice)
        rank, total = self.game.evaluate_hand(hand.dice)
        
        embed = discord.Embed(
            title="🎲 당신의 주사위",
            description=f"{dice_str}\n{self.game.get_hand_name(rank)} (합계: {total})",
            color=discord.Color.green()
        )
        
        # 팁 추가
        embed.add_field(
            name="💡 팁",
            value="다른 플레이어는 당신의 주사위를 볼 수 없습니다.\n베팅으로 상대를 속이세요!",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # 버튼 비활성화
        self.stop()

class CheckMyDiceView(discord.ui.View):
    def __init__(self, game: DicePokerGame, player: discord.Member):
        super().__init__(timeout=300)  # 5분
        self.game = game
        self.player = player
    
    @discord.ui.button(label="내 주사위 확인", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def check_dice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("다른 플레이어의 주사위는 확인할 수 없습니다!", ephemeral=True)
            return
        
        hand = self.game.player_hands[self.player.id]
        if not hand.dice:
            await interaction.response.send_message("아직 주사위를 굴리지 않았습니다.", ephemeral=True)
            return
        
        dice_str = self.game.format_dice(hand.dice)
        rank, total = self.game.evaluate_hand(hand.dice)
        
        embed = discord.Embed(
            title="🎲 당신의 주사위",
            description=f"{dice_str}\n{self.game.get_hand_name(rank)} (합계: {total})",
            color=discord.Color.blue()
        )
        
        if hand.reroll_count > 0:
            embed.add_field(
                name="리롤 횟수",
                value=f"{hand.reroll_count}/2회 사용",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class BettingView(discord.ui.View):
    def __init__(self, game: DicePokerGame, player: discord.Member):
        super().__init__(timeout=60)
        self.game = game
        self.player = player
        self.add_buttons()
    
    def add_buttons(self):
        """상황에 맞는 버튼 추가"""
        hand = self.game.player_hands[self.player.id]
        
        # 내 주사위 확인 버튼 (항상 추가)
        check_dice_btn = discord.ui.Button(
            label="내 주사위", 
            style=discord.ButtonStyle.secondary, 
            emoji="👁️",
            row=0  # 첫 번째 줄
        )
        check_dice_btn.callback = self.check_my_dice_callback
        self.add_item(check_dice_btn)
        
        # Check 버튼 (현재 베팅이 없거나 이미 맞춘 경우)
        if self.game.current_bet == hand.current_bet:
            check_btn = discord.ui.Button(
                label="Check", 
                style=discord.ButtonStyle.secondary, 
                emoji="✅",
                row=1  # 두 번째 줄
            )
            check_btn.callback = self.check_callback
            self.add_item(check_btn)
        
        # Call 버튼 (콜해야 할 금액이 있는 경우)
        if self.game.current_bet > hand.current_bet:
            call_amount = self.game.current_bet - hand.current_bet
            call_btn = discord.ui.Button(
                label=f"Call ({call_amount:,}💰)", 
                style=discord.ButtonStyle.primary, 
                emoji="📞",
                row=1
            )
            call_btn.callback = self.call_callback
            self.add_item(call_btn)
        
        # Raise 버튼
        raise_btn = discord.ui.Button(
            label="Raise", 
            style=discord.ButtonStyle.success, 
            emoji="⬆️",
            row=1
        )
        raise_btn.callback = self.raise_callback
        self.add_item(raise_btn)
        
        # Fold 버튼
        fold_btn = discord.ui.Button(
            label="Fold", 
            style=discord.ButtonStyle.danger, 
            emoji="🏳️",
            row=1
        )
        fold_btn.callback = self.fold_callback
        self.add_item(fold_btn)
    
    async def check_my_dice_callback(self, interaction: discord.Interaction):
        """내 주사위 확인"""
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("다른 플레이어의 주사위는 확인할 수 없습니다!", ephemeral=True)
            return
        
        hand = self.game.player_hands[self.player.id]
        dice_str = self.game.format_dice(hand.dice)
        rank, total = self.game.evaluate_hand(hand.dice)
        
        embed = discord.Embed(
            title="🎲 당신의 주사위",
            description=f"{dice_str}\n{self.game.get_hand_name(rank)} (합계: {total})",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def check_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        success = await self.game.handle_check(self.player.id)
        if success:
            await interaction.response.send_message("체크!", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message("체크할 수 없습니다!", ephemeral=True)
    
    async def call_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        await self.game.handle_call(self.player.id)
        await interaction.response.send_message("콜!", ephemeral=True)
        self.stop()
    
    async def raise_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        modal = RaiseModal(self.game, self.player)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.success:
            self.stop()
    
    async def fold_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        await self.game.handle_fold(self.player.id)
        await interaction.response.send_message("폴드!", ephemeral=True)
        self.stop()

class RaiseModal(discord.ui.Modal):
    def __init__(self, game: DicePokerGame, player: discord.Member):
        super().__init__(title="레이즈 금액 입력")
        self.game = game
        self.player = player
        self.success = False
        
        # 최소/최대 금액 계산
        hand = game.player_hands[player.id]
        min_amount = game.current_bet - hand.current_bet + game.min_raise
        
        self.amount_input = discord.ui.TextInput(
            label="레이즈 금액",
            placeholder=f"최소 {min_amount:,}💰 이상",
            required=True,
            min_length=1,
            max_length=10
        )
        self.add_item(self.amount_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            success = await self.game.handle_raise(self.player.id, amount)
            
            if success:
                await interaction.response.send_message(f"레이즈! ({amount:,}💰)", ephemeral=True)
                self.success = True
            else:
                await interaction.response.send_message("레이즈할 수 없습니다!", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("올바른 숫자를 입력하세요!", ephemeral=True)

class RerollView(discord.ui.View):
    def __init__(self, game: DicePokerGame, player: discord.Member):
        super().__init__(timeout=60)
        self.game = game
        self.player = player
    
    @discord.ui.button(label="리롤 선택", style=discord.ButtonStyle.primary, emoji="🔄")
    async def reroll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        hand = self.game.player_hands[self.player.id]
        modal = RerollModal(self.game, self.player, hand.dice)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.stop()
    
    @discord.ui.button(label="리롤 안함", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        await interaction.response.send_message("리롤하지 않습니다.", ephemeral=True)
        self.stop()

class RerollModal(discord.ui.Modal):
    def __init__(self, game: DicePokerGame, player: discord.Member, current_dice: List[int]):
        super().__init__(title="리롤할 주사위 선택")
        self.game = game
        self.player = player
        self.current_dice = current_dice
        
        # 현재 주사위 표시
        dice_str = game.format_dice(current_dice)
        
        self.reroll_input = discord.ui.TextInput(
            label=f"현재 주사위: {dice_str}",
            placeholder="리롤할 주사위 번호 (예: 1,3,5)",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.reroll_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # 입력 파싱
            if self.reroll_input.value.strip() == "":
                await interaction.response.send_message("리롤하지 않습니다.", ephemeral=True)
                return
            
            indices = [int(x.strip()) - 1 for x in self.reroll_input.value.split(",")]
            
            # 유효성 검사
            if any(i < 0 or i >= 5 for i in indices):
                await interaction.response.send_message("잘못된 주사위 번호입니다!", ephemeral=True)
                return
            
            # 리롤 실행
            hand = self.game.player_hands[self.player.id]
            new_dice = self.game.roll_dice(len(indices))
            
            for i, idx in enumerate(indices):
                hand.dice[idx] = new_dice[i]
            
            hand.reroll_count += 1
            
            # 결과 표시
            dice_str = self.game.format_dice(hand.dice)
            await interaction.response.send_message(
                f"리롤 완료! 새로운 주사위: {dice_str}",
                ephemeral=True
            )
            
        except (ValueError, IndexError):
            await interaction.response.send_message("올바른 형식으로 입력하세요!", ephemeral=True)

# 게임 참가 뷰
class DicePokerJoinView(discord.ui.View):
    def __init__(self, max_bet: int):
        super().__init__(timeout=30)
        self.participants = {}  # user_id: bet_amount
        self.max_bet = max_bet
    
    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, emoji="🎲")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            await interaction.response.send_message("이미 참가하셨습니다!", ephemeral=True)
            return
        
        if len(self.participants) >= 10:
            await interaction.response.send_message("최대 인원(10명)에 도달했습니다!", ephemeral=True)
            return
        
        # 사용자의 현재 잔액 확인
        from utility import get_user_inventory
        user_data = await get_user_inventory(str(interaction.user.id))
        
        if not user_data:
            await interaction.response.send_message("사용자 정보를 찾을 수 없습니다.", ephemeral=True)
            return
            
        user_coins = user_data.get("coins", 0)
        
        if user_coins <= 0:
            await interaction.response.send_message("보유한 코인이 없어 게임에 참가할 수 없습니다.", ephemeral=True)
            return
        
        # 사용자의 최대 베팅 가능 금액 계산 (보유 코인과 게임 최대 베팅 중 작은 값)
        user_max_bet = min(user_coins, self.max_bet)
        
        modal = DicePokerBetModal(user_max_bet, user_coins, self)
        await interaction.response.send_modal(modal)
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

class DicePokerBetModal(discord.ui.Modal):
    def __init__(self, max_bet: int, user_coins: int, view: DicePokerJoinView):
        super().__init__(title="주사위 포커 베팅")
        self.max_bet = max_bet
        self.user_coins = user_coins
        self.view = view
        
        # 추천 베팅 금액 계산 (보유 코인의 10% 또는 100 중 큰 값, 최대 베팅 제한)
        suggested_bet = min(max(100, user_coins // 10), max_bet)
        
        self.bet_input = discord.ui.TextInput(
            label=f"베팅 금액 (보유: {user_coins:,}💰)",
            placeholder=f"1 ~ {max_bet:,} 사이의 금액을 입력하세요 (추천: {suggested_bet:,})",
            default=str(suggested_bet),
            required=True,
            min_length=1,
            max_length=10
        )
        self.add_item(self.bet_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.bet_input.value)
            
            # 베팅 금액 유효성 검사
            if bet_amount < 1:
                await interaction.response.send_message(
                    "베팅 금액은 최소 1💰 이상이어야 합니다!",
                    ephemeral=True
                )
                return
            
            if bet_amount > self.max_bet:
                await interaction.response.send_message(
                    f"베팅 금액은 최대 {self.max_bet:,}💰를 초과할 수 없습니다!",
                    ephemeral=True
                )
                return
            
            if bet_amount > self.user_coins:
                await interaction.response.send_message(
                    f"보유한 코인({self.user_coins:,}💰)보다 많이 베팅할 수 없습니다!",
                    ephemeral=True
                )
                return
            
            # 다시 한 번 현재 잔액 확인 (다른 곳에서 사용했을 수 있음)
            from utility import get_user_inventory
            current_data = await get_user_inventory(str(interaction.user.id))
            
            if not current_data or current_data.get("coins", 0) < bet_amount:
                await interaction.response.send_message(
                    "잔액이 부족합니다! (다른 곳에서 코인을 사용하셨나요?)",
                    ephemeral=True
                )
                return
            
            remaining_coins = current_data.get('coins', 0) - bet_amount
            
            self.view.participants[interaction.user.id] = bet_amount
            
            await interaction.response.send_message(
                f"{interaction.user.display_name}님이 {bet_amount:,}💰 베팅하여 참가했습니다!\n"
                f"(남은 코인: {remaining_coins:,}💰)",
                ephemeral=False
            )
            
        except ValueError:
            await interaction.response.send_message(
                "올바른 숫자를 입력하세요!",
                ephemeral=True
            )