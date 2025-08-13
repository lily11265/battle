# blackjack_commands.py
import discord
from discord import app_commands
import asyncio
from typing import Dict, List, Optional
import logging
from blackjack import BlackjackGame
from card_utils import get_card_image_manager

logger = logging.getLogger(__name__)

# 진행 중인 블랙잭 게임 추적
active_blackjack_games = {}  # channel_id: BlackjackGame

def get_active_blackjack_game(channel_id: int, user_id: int) -> Optional[BlackjackGame]:
    """특정 채널에서 사용자가 참여 중인 블랙잭 게임 반환"""
    if channel_id in active_blackjack_games:
        game = active_blackjack_games[channel_id]
        if user_id in game.player_hands:
            return game
    return None

async def start_blackjack_game(interaction: discord.Interaction, 
                              players: List[discord.Member], 
                              bet_amounts: Dict[int, int],
                              bot_instance):
    """블랙잭 게임 시작"""
    channel_id = interaction.channel_id
    
    # 기존 게임이 있는지 확인
    if channel_id in active_blackjack_games:
        await interaction.response.send_message("이미 진행 중인 블랙잭 게임이 있습니다!", ephemeral=True)
        return
    
    # 게임 생성 및 시작
    game = BlackjackGame(interaction, players, bet_amounts, bot_instance)
    active_blackjack_games[channel_id] = game
    
    try:
        await game.start_game()
    finally:
        # 게임 종료 후 제거
        if channel_id in active_blackjack_games:
            del active_blackjack_games[channel_id]

# 블랙잭 버튼 뷰 (기존 코드 재사용)
# 블랙잭 참가 뷰
class BlackjackJoinView(discord.ui.View):
    def __init__(self, max_bet: int):
        super().__init__(timeout=30)
        self.participants = {}  # user_id: bet_amount
        self.max_bet = max_bet
    
    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, emoji="🎰")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            await interaction.response.send_message("이미 참가하셨습니다!", ephemeral=True)
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
        
        modal = BlackjackBetModal(user_max_bet, user_coins, self)
        await interaction.response.send_modal(modal)
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

class BlackjackBetModal(discord.ui.Modal, title="블랙잭 베팅"):
    def __init__(self, max_bet: int, user_coins: int, view: BlackjackJoinView):
        super().__init__()
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
            
            self.view.participants[interaction.user.id] = bet_amount
            await interaction.response.send_message(
                f"{interaction.user.display_name}님이 {bet_amount:,}💰 베팅하여 참가했습니다!\n"
                f"(남은 코인: {current_data.get('coins', 0) - bet_amount:,}💰)",
                ephemeral=False
            )
            
        except ValueError:
            await interaction.response.send_message(
                "올바른 숫자를 입력하세요!",
                ephemeral=True
            )