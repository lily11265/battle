# blackjack.py
import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Union

# 카드 관련 상수 정의
SUITS = ['♥️', '♦️', '♠️', '♣️']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
CARD_VALUES = {'A': 11, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10}

# 전역 설정
DEBUG_MODE = False

# 블랙잭 게임 클래스
class BlackjackGame:
    def __init__(self, ctx, players: List[discord.Member], bet_amounts: Dict[int, int], bot_instance):
        self.ctx = ctx
        self.players = players
        self.bet_amounts = bet_amounts
        self.bot = bot_instance
        self.deck = []
        self.dealer_hand = []
        self.player_hands = {player.id: [] for player in players}
        self.player_scores = {player.id: 0 for player in players}
        self.player_finished = {player.id: False for player in players}
        self.player_doubled = {player.id: False for player in players}
        self.player_split = {player.id: False for player in players}
        self.player_split_hands = {player.id: [] for player in players}
        self.player_split_scores = {player.id: 0 for player in players}
        self.player_split_finished = {player.id: False for player in players}
        self.player_split_doubled = {player.id: False for player in players}
        self.player_results = {player.id: "" for player in players}
        self.player_split_results = {player.id: "" for player in players}
        self.message = None
        self.is_game_over = False
        self.test_mode = False  # 테스트 모드 플래그
        self.test_commands = {}  # 테스트 명령어 저장

    def create_deck(self):
        """새로운 덱 생성 (테스트 모드 포함)"""
        if self.test_mode:
            # 테스트용 조작된 덱 생성 가능
            if hasattr(self, 'test_deck'):
                self.deck = self.test_deck.copy()
                return
        
        # 일반 덱 생성
        self.deck = [(rank, suit) for suit in SUITS for rank in RANKS]
        random.shuffle(self.deck)
    
    def draw_card(self):
        """덱에서 카드 한 장 뽑기"""
        if not self.deck:
            self.create_deck()
        return self.deck.pop()
    
    def calculate_hand_value(self, hand):
        """핸드의 값 계산"""
        value = sum(CARD_VALUES[card[0]] for card in hand)
        
        # 에이스 처리 (필요한 경우 11 -> 1로 변경)
        aces = sum(1 for card in hand if card[0] == 'A')
        while value > 21 and aces:
            value -= 10
            aces -= 1
            
        return value
    
    def is_blackjack(self, hand):
        """블랙잭 여부 확인 (첫 두 카드로 21점)"""
        return len(hand) == 2 and self.calculate_hand_value(hand) == 21
    
    def format_hand(self, hand, hide_second=False):
        """핸드 표시 형식 지정"""
        if hide_second and len(hand) > 1:
            return f"{hand[0][0]}{hand[0][1]} ??"
        return ' '.join(f"{card[0]}{card[1]}" for card in hand)
    
    def format_result(self, player_id):
        """게임 결과 형식 지정"""
        original_bet = self.bet_amounts[player_id]
        player_hand = self.player_hands[player_id]
        player_score = self.calculate_hand_value(player_hand)
        dealer_score = self.calculate_hand_value(self.dealer_hand)
        
        # 플레이어가 버스트한 경우
        if player_score > 21:
            winnings = -original_bet
            if self.player_doubled[player_id]:
                winnings *= 2
            return f"버스트! ({player_score}점) {winnings:,}💰"
        
        # 플레이어가 블랙잭인 경우
        if self.is_blackjack(player_hand) and not self.is_blackjack(self.dealer_hand):
            winnings = int(original_bet * 1.5)
            return f"블랙잭! +{winnings:,}💰"
        
        # 딜러가 버스트한 경우
        if dealer_score > 21:
            winnings = original_bet
            if self.player_doubled[player_id]:
                winnings *= 2
            return f"딜러 버스트! 승리! +{winnings:,}💰"
        
        # 딜러가 블랙잭인 경우
        if self.is_blackjack(self.dealer_hand) and not self.is_blackjack(player_hand):
            winnings = -original_bet
            return f"딜러 블랙잭! 패배! {winnings:,}💰"
        
        # 둘 다 블랙잭인 경우 - 플레이어 승리로 변경
        if self.is_blackjack(player_hand) and self.is_blackjack(self.dealer_hand):
            winnings = original_bet  # 1.5배가 아닌 1배로 승리
            return f"양측 블랙잭! 플레이어 승리! +{winnings:,}💰"
        
        # 일반적인 경우 점수 비교
        if player_score > dealer_score:
            winnings = original_bet
            if self.player_doubled[player_id]:
                winnings *= 2
            return f"승리! ({player_score} vs {dealer_score}) +{winnings:,}💰"
        elif player_score < dealer_score:
            winnings = -original_bet
            if self.player_doubled[player_id]:
                winnings *= 2
            return f"패배! ({player_score} vs {dealer_score}) {winnings:,}💰"
        else:
            # 21점 동점인 경우 플레이어 승리
            if player_score == 21:
                winnings = original_bet
                if self.player_doubled[player_id]:
                    winnings *= 2
                return f"21점 동점! 플레이어 승리! +{winnings:,}💰"
            else:
                # 그 외 동점은 푸시
                return f"푸시! ({player_score} vs {dealer_score}) +0💰"
    
    def get_winnings(self, player_id):
        """플레이어의 승리 금액 계산"""
        original_bet = self.bet_amounts[player_id]
        player_hand = self.player_hands[player_id]
        player_score = self.calculate_hand_value(player_hand)
        dealer_score = self.calculate_hand_value(self.dealer_hand)
        
        # 플레이어가 버스트한 경우
        if player_score > 21:
            return -original_bet * (2 if self.player_doubled[player_id] else 1)
        
        # 플레이어가 블랙잭인 경우
        if self.is_blackjack(player_hand) and not self.is_blackjack(self.dealer_hand):
            return int(original_bet * 1.5)
        
        # 딜러가 버스트한 경우
        if dealer_score > 21:
            return original_bet * (2 if self.player_doubled[player_id] else 1)
        
        # 딜러가 블랙잭인 경우
        if self.is_blackjack(self.dealer_hand) and not self.is_blackjack(player_hand):
            return -original_bet
        
        # 둘 다 블랙잭인 경우 - 플레이어 승리로 변경
        if self.is_blackjack(player_hand) and self.is_blackjack(self.dealer_hand):
            return original_bet  # 1.5배가 아닌 1배로 승리
        
        # 일반적인 경우 점수 비교
        if player_score > dealer_score:
            return original_bet * (2 if self.player_doubled[player_id] else 1)
        elif player_score < dealer_score:
            return -original_bet * (2 if self.player_doubled[player_id] else 1)
        else:
            # 21점 동점인 경우 플레이어 승리
            if player_score == 21:
                return original_bet * (2 if self.player_doubled[player_id] else 1)
            else:
                # 그 외 동점은 푸시
                return 0

    
    def get_split_winnings(self, player_id):
        """스플릿 핸드의 승리 금액 계산"""
        if not self.player_split[player_id]:
            return 0
            
        original_bet = self.bet_amounts[player_id]
        player_hand = self.player_split_hands[player_id]
        player_score = self.calculate_hand_value(player_hand)
        dealer_score = self.calculate_hand_value(self.dealer_hand)
        
        if player_score > 21:
            return -original_bet * (2 if self.player_split_doubled[player_id] else 1)
        elif self.is_blackjack(player_hand) and not self.is_blackjack(self.dealer_hand):
            return int(original_bet * 1.5)
        elif dealer_score > 21:
            return original_bet * (2 if self.player_split_doubled[player_id] else 1)
        elif self.is_blackjack(self.dealer_hand) and not self.is_blackjack(player_hand):
            return -original_bet
        elif self.is_blackjack(player_hand) and self.is_blackjack(self.dealer_hand):
            return original_bet  # 둘 다 블랙잭인 경우 플레이어 승리
        elif player_score > dealer_score:
            return original_bet * (2 if self.player_split_doubled[player_id] else 1)
        elif player_score < dealer_score:
            return -original_bet * (2 if self.player_split_doubled[player_id] else 1)
        else:
            # 21점 동점인 경우 플레이어 승리
            if player_score == 21:
                return original_bet * (2 if self.player_split_doubled[player_id] else 1)
            else:
                return 0
    
    async def deal_initial_cards(self):
        """초기 카드 배분 (테스트 모드 포함)"""
        self.create_deck()
        
        if self.test_mode:
            # 21점 동점 상황 테스트
            if self.test_commands.get('both21'):
                # 플레이어에게 10, A 주기
                for player_id in self.player_hands:
                    self.player_hands[player_id].append(('10', '♥️'))
                    self.player_hands[player_id].append(('A', '♠️'))
                
                # 딜러에게도 10, A 주기
                self.dealer_hand.append(('K', '♦️'))
                self.dealer_hand.append(('A', '♣️'))
                return
            
            # 플레이어 블랙잭 테스트
            elif self.test_commands.get('player_blackjack'):
                for player_id in self.player_hands:
                    self.player_hands[player_id].append(('A', '♥️'))
                    self.player_hands[player_id].append(('K', '♠️'))
                
                self.dealer_hand.append(('9', '♦️'))
                self.dealer_hand.append(('7', '♣️'))
                return
            
            # 딜러 버스트 테스트
            elif self.test_commands.get('dealer_bust'):
                for player_id in self.player_hands:
                    self.player_hands[player_id].append(('9', '♥️'))
                    self.player_hands[player_id].append(('9', '♠️'))
                
                self.dealer_hand.append(('6', '♦️'))
                self.dealer_hand.append(('6', '♣️'))
                # 딜러는 나중에 추가 카드를 받아 버스트하게 됨
                return
        
        # 일반 카드 배분
        for player_id in self.player_hands:
            self.player_hands[player_id].append(self.draw_card())
            self.player_hands[player_id].append(self.draw_card())
        
        self.dealer_hand.append(self.draw_card())
        self.dealer_hand.append(self.draw_card())
    
    async def create_game_embed(self, current_player=None, hide_dealer=True):
        """게임 상태를 보여주는 임베드 생성 (테스트 모드 표시)"""
        if self.test_mode:
            embed = discord.Embed(
                title="블랙잭 게임 [테스트 모드]", 
                color=discord.Color.orange()
            )
        else:
            embed = discord.Embed(title="블랙잭 게임", color=discord.Color.green())
        
        # 딜러 정보
        dealer_text = f"딜러: {self.format_hand(self.dealer_hand, hide_dealer)}"
        if not hide_dealer:
            dealer_text += f" ({self.calculate_hand_value(self.dealer_hand)}점)"
        embed.add_field(name=dealer_text, value="\u200b", inline=False)
        
        # 각 플레이어 정보
        for player in self.players:
            player_id = player.id
            hand = self.player_hands[player_id]
            hand_value = self.calculate_hand_value(hand)
            
            # 플레이어 상태 텍스트
            status = ""
            if self.is_game_over:
                status = self.player_results[player_id]
            elif self.player_finished[player_id]:
                status = f"대기 중... ({hand_value}점)"
            elif current_player and current_player.id == player_id:
                status = f"**턴 진행 중...** ({hand_value}점)"
            else:
                status = f"대기 중... ({hand_value}점)"
            
            player_text = f"{player.display_name}: {self.format_hand(hand)} - {status}\n"
            player_text += f"베팅: {self.bet_amounts[player_id]:,}💰"
            
            # 더블다운 표시
            if self.player_doubled[player_id]:
                player_text += " (더블다운)"
            
            # 스플릿 정보 표시
            if self.player_split[player_id]:
                split_hand = self.player_split_hands[player_id]
                split_value = self.calculate_hand_value(split_hand)
                
                player_text += f"\n스플릿: {self.format_hand(split_hand)} ({split_value}점)"
                
                if self.is_game_over:
                    player_text += f" - {self.player_split_results[player_id]}"
                
                if self.player_split_doubled[player_id]:
                    player_text += " (더블다운)"
            
            embed.add_field(name=f"{player.display_name}의 핸드", value=player_text, inline=False)
        
        # 디버그 모드인 경우 추가 정보 표시
        if DEBUG_MODE:
            debug_info = f"남은 카드 수: {len(self.deck)}"
            embed.add_field(name="디버그 정보", value=debug_info, inline=False)
        
        if self.test_mode:
            test_info = "**테스트 명령어:**\n"
            test_info += "`/테스트_블랙잭 both21` - 양측 21점\n"
            test_info += "`/테스트_블랙잭 player_blackjack` - 플레이어 블랙잭\n"
            test_info += "`/테스트_블랙잭 dealer_bust` - 딜러 버스트"
            embed.add_field(name="테스트 정보", value=test_info, inline=False)
        
        return embed
    
    async def start_game(self):
        """게임 시작"""
        
        await self.deal_initial_cards()
        
        # 초기 상태 메시지
        embed = await self.create_game_embed()
        self.message = await self.ctx.followup.send(embed=embed)
        
        # 퀘스트 이벤트 발생 - 미니게임 시작
        for player in self.players:
            self.bot.dispatch('minigame_started', str(player.id), player.display_name, '블랙잭')
        
        # 각 플레이어 턴 진행
        for player in self.players:
            if not self.is_game_over:
                await self.player_turn(player)
        
        # 모든 플레이어 턴 종료 후 딜러 턴
        if not self.is_game_over:
            await self.dealer_turn()
        
        # 결과 계산 및 표시
        await self.end_game()
    
    async def player_turn(self, player):
        """플레이어 턴 진행"""
        player_id = player.id
        player_hand = self.player_hands[player_id]
        
        # 블랙잭이면 바로 턴 종료
        if self.is_blackjack(player_hand):
            self.player_results[player_id] = "블랙잭!"
            self.player_finished[player_id] = True
            return
        
        # 플레이어 턴 진행 메시지 업데이트
        embed = await self.create_game_embed(player)
        await self.message.edit(embed=embed)
        
        # 버튼 추가
        view = BlackjackView(self, player)
        await self.message.edit(view=view)
        
        # 플레이어 응답 대기
        timeout = 60  # 60초 제한시간
        start_time = asyncio.get_event_loop().time()
        
        while not self.player_finished[player_id] and asyncio.get_event_loop().time() - start_time < timeout:
            # 메시지 업데이트 (매 3초마다)
            embed = await self.create_game_embed(player)
            await self.message.edit(embed=embed)
            
            await asyncio.sleep(3)
        
        # 타임아웃 처리
        if not self.player_finished[player_id]:
            self.player_finished[player_id] = True
            self.player_results[player_id] = "시간 초과 - 자동 스탠드"
        
        # 스플릿 핸드 턴 진행
        if self.player_split[player_id] and not self.player_split_finished[player_id]:
            embed = await self.create_game_embed(player)
            await self.message.edit(embed=embed)
            
            # 스플릿 핸드용 버튼
            split_view = BlackjackSplitView(self, player)
            await self.message.edit(view=split_view)
            
            # 플레이어 응답 대기
            start_time = asyncio.get_event_loop().time()
            
            while not self.player_split_finished[player_id] and asyncio.get_event_loop().time() - start_time < timeout:
                # 메시지 업데이트 (매 3초마다)
                embed = await self.create_game_embed(player)
                await self.message.edit(embed=embed)
                
                await asyncio.sleep(3)
            
            # 타임아웃 처리
            if not self.player_split_finished[player_id]:
                self.player_split_finished[player_id] = True
                self.player_split_results[player_id] = "시간 초과 - 자동 스탠드"
        
        # 버튼 제거
        await self.message.edit(view=None)
    
    async def dealer_turn(self):
        """딜러 턴 진행"""
        # 딜러 카드 공개
        embed = await self.create_game_embed(hide_dealer=False)
        await self.message.edit(embed=embed)
        await asyncio.sleep(1)
        
        # 딜러는 17 이상이 될 때까지 카드를 뽑는다
        while self.calculate_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.draw_card())
            
            # 화면 업데이트
            embed = await self.create_game_embed(hide_dealer=False)
            await self.message.edit(embed=embed)
            await asyncio.sleep(1)
    
    async def end_game(self):
        """게임 종료 및 결과 계산"""
        self.is_game_over = True
        
        # 각 플레이어의 결과 계산
        for player in self.players:
            player_id = player.id
            self.player_results[player_id] = self.format_result(player_id)
            
            if self.player_split[player_id]:
                player_hand = self.player_split_hands[player_id]
                player_score = self.calculate_hand_value(player_hand)
                dealer_score = self.calculate_hand_value(self.dealer_hand)
                
                # 스플릿 핸드 결과 계산
                if player_score > 21:
                    split_winnings = -self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        split_winnings *= 2
                    self.player_split_results[player_id] = f"버스트! ({player_score}점) {split_winnings:,}💰"
                elif dealer_score > 21:
                    split_winnings = self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        split_winnings *= 2
                    self.player_split_results[player_id] = f"딜러 버스트! 승리! +{split_winnings:,}💰"
                elif player_score > dealer_score:
                    split_winnings = self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        split_winnings *= 2
                    self.player_split_results[player_id] = f"승리! ({player_score} vs {dealer_score}) +{split_winnings:,}💰"
                elif player_score < dealer_score:
                    split_winnings = -self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        split_winnings *= 2
                    self.player_split_results[player_id] = f"패배! ({player_score} vs {dealer_score}) {split_winnings:,}💰"
                else:
                    # 21점 동점인 경우 플레이어 승리
                    if player_score == 21:
                        split_winnings = self.bet_amounts[player_id]
                        if self.player_split_doubled[player_id]:
                            split_winnings *= 2
                        self.player_split_results[player_id] = f"21점 동점! 플레이어 승리! +{split_winnings:,}💰"
                    else:
                        self.player_split_results[player_id] = f"푸시! ({player_score} vs {dealer_score}) +0💰"
        
        # 최종 결과 표시
        embed = await self.create_game_embed(hide_dealer=False)
        await self.message.edit(embed=embed)
        
        # 잔액 업데이트
        await self.update_player_balances()
    
    async def update_player_balances(self):
        """플레이어 잔액 업데이트 - 승자가 모든 베팅금을 가져가는 방식"""
        from utility import update_player_balance
        
        # 전체 팟(pot) 계산
        total_pot = sum(self.bet_amounts.values())
        
        # 승자 판별
        winners = []
        dealer_score = self.calculate_hand_value(self.dealer_hand)
        dealer_bust = dealer_score > 21
        
        for player in self.players:
            player_id = player.id
            player_score = self.calculate_hand_value(self.player_hands[player_id])
            player_bust = player_score > 21
            
            # 메인 핸드 승리 조건
            is_winner = False
            
            if not player_bust:
                if dealer_bust:
                    is_winner = True
                elif self.is_blackjack(self.player_hands[player_id]) and not self.is_blackjack(self.dealer_hand):
                    is_winner = True
                elif not self.is_blackjack(self.dealer_hand) and player_score > dealer_score:
                    is_winner = True
            
            # 스플릿 핸드가 있는 경우 체크
            if self.player_split[player_id]:
                split_score = self.calculate_hand_value(self.player_split_hands[player_id])
                split_bust = split_score > 21
                
                if not split_bust:
                    if dealer_bust:
                        is_winner = True
                    elif self.is_blackjack(self.player_split_hands[player_id]) and not self.is_blackjack(self.dealer_hand):
                        is_winner = True
                    elif not self.is_blackjack(self.dealer_hand) and split_score > dealer_score:
                        is_winner = True
            
            if is_winner:
                winners.append(player)
        
        # 잔액 업데이트
        result_messages = []
        
        if not winners:
            # 모든 플레이어가 졌을 경우 - 하우스(딜러)가 모든 돈을 가져감
            for player in self.players:
                player_id = player.id
                user_id = str(player_id)
                loss = -self.bet_amounts[player_id]
                
                # 더블다운한 경우 베팅액 두 배
                if self.player_doubled[player_id]:
                    loss *= 2
                if self.player_split[player_id] and self.player_split_doubled[player_id]:
                    loss *= 2
                    
                await update_player_balance(user_id, loss)
                result_messages.append(f"{player.display_name}: {loss:,}💰")
            
            result_messages.append(f"\n🏠 하우스가 모든 베팅금 {total_pot:,}💰를 가져갔습니다!")
            
        else:
            # 승자가 있는 경우
            # 먼저 모든 플레이어의 베팅금을 차감
            for player in self.players:
                player_id = player.id
                user_id = str(player_id)
                bet = self.bet_amounts[player_id]
                
                # 더블다운 고려
                if self.player_doubled[player_id]:
                    bet *= 2
                if self.player_split[player_id]:
                    bet += self.bet_amounts[player_id]  # 스플릿은 추가 베팅
                    if self.player_split_doubled[player_id]:
                        bet += self.bet_amounts[player_id]  # 스플릿 더블다운
                
                await update_player_balance(user_id, -bet)
            
            # 실제 총 팟 재계산 (더블다운 포함)
            actual_pot = 0
            for player in self.players:
                player_id = player.id
                bet = self.bet_amounts[player_id]
                
                if self.player_doubled[player_id]:
                    bet *= 2
                if self.player_split[player_id]:
                    bet += self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        bet += self.bet_amounts[player_id]
                        
                actual_pot += bet
            
            # 승자들에게 팟 분배
            winnings_per_winner = actual_pot // len(winners)
            remainder = actual_pot % len(winners)
            
            for i, winner in enumerate(winners):
                user_id = str(winner.id)
                winnings = winnings_per_winner
                
                # 나머지가 있으면 첫 번째 승자부터 1씩 추가
                if i < remainder:
                    winnings += 1
                    
                await update_player_balance(user_id, winnings)
                result_messages.append(f"{winner.display_name}: +{winnings:,}💰 (승리!)")
            
            # 패자 메시지
            for player in self.players:
                if player not in winners:
                    player_id = player.id
                    loss = self.bet_amounts[player_id]
                    
                    if self.player_doubled[player_id]:
                        loss *= 2
                    if self.player_split[player_id]:
                        loss += self.bet_amounts[player_id]
                        if self.player_split_doubled[player_id]:
                            loss += self.bet_amounts[player_id]
                            
                    result_messages.append(f"{player.display_name}: -{loss:,}💰 (패배)")
            
            if len(winners) == 1:
                result_messages.append(f"\n🎉 {winners[0].display_name}님이 총 {actual_pot:,}💰를 획득했습니다!")
            else:
                winner_names = ", ".join([w.display_name for w in winners])
                result_messages.append(f"\n🎉 {winner_names}님이 총 {actual_pot:,}💰를 나눠 가졌습니다!")
        
        # 결과 메시지 전송
        result_embed = discord.Embed(
            title="💰 블랙잭 게임 결과",
            description="\n".join(result_messages),
            color=discord.Color.gold()
        )
        
        await self.message.reply(embed=result_embed)
        
        # 퀘스트 이벤트 발생
        for player in self.players:
            player_id = player.id
            user_id = str(player_id)
            
            # 실제 손익 계산
            if player in winners:
                net_gain = winnings_per_winner - self.bet_amounts[player_id]
                if self.player_doubled[player_id]:
                    net_gain -= self.bet_amounts[player_id]
                if self.player_split[player_id]:
                    net_gain -= self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        net_gain -= self.bet_amounts[player_id]
            else:
                net_gain = -self.bet_amounts[player_id]
                if self.player_doubled[player_id]:
                    net_gain *= 2
                if self.player_split[player_id]:
                    net_gain -= self.bet_amounts[player_id]
                    if self.player_split_doubled[player_id]:
                        net_gain -= self.bet_amounts[player_id]
            
            self.bot.dispatch('minigame_complete', user_id, player.display_name, '블랙잭', net_gain)
    
    async def hit(self, player_id, is_split=False):
        """히트 - 카드 한 장 더 받기"""
        if is_split:
            hand = self.player_split_hands[player_id]
            hand.append(self.draw_card())
            hand_value = self.calculate_hand_value(hand)
            
            if hand_value > 21:
                self.player_split_finished[player_id] = True
        else:
            hand = self.player_hands[player_id]
            hand.append(self.draw_card())
            hand_value = self.calculate_hand_value(hand)
            
            if hand_value > 21:
                self.player_finished[player_id] = True
    
    async def stand(self, player_id, is_split=False):
        """스탠드 - 더 이상 카드 받지 않음"""
        if is_split:
            self.player_split_finished[player_id] = True
        else:
            self.player_finished[player_id] = True
    
    async def double_down(self, player_id, is_split=False):
        """더블다운 - 베팅 두 배로 늘리고 카드 한 장만 더 받음"""
        if is_split:
            hand = self.player_split_hands[player_id]
            hand.append(self.draw_card())
            self.player_split_doubled[player_id] = True
            self.player_split_finished[player_id] = True
        else:
            hand = self.player_hands[player_id]
            hand.append(self.draw_card())
            self.player_doubled[player_id] = True
            self.player_finished[player_id] = True
    
    async def split(self, player_id):
        """스플릿 - 같은 랭크의 카드 두 장을 두 개의 핸드로 분리"""
        hand = self.player_hands[player_id]
        
        # 스플릿 조건 확인
        if len(hand) == 2 and hand[0][0] == hand[1][0]:
            # 첫 번째 핸드에는 첫 카드만 남기고, 두 번째 핸드에는 두 번째 카드 넣기
            split_card = hand.pop()
            self.player_split_hands[player_id].append(split_card)
            
            # 각 핸드에 새 카드 추가
            hand.append(self.draw_card())
            self.player_split_hands[player_id].append(self.draw_card())
            
            # 스플릿 상태 업데이트
            self.player_split[player_id] = True
            
            return True
        return False

# 블랙잭 게임 버튼 뷰
class BlackjackView(discord.ui.View):
    def __init__(self, game, current_player):
        super().__init__(timeout=60)
        self.game = game
        self.current_player = current_player
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="👆")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            await self.game.hit(self.current_player.id)
            
            # 핸드 업데이트
            embed = await self.game.create_game_embed(self.current_player)
            await interaction.response.edit_message(embed=embed)
            
            # 버스트 체크
            if self.game.calculate_hand_value(self.game.player_hands[self.current_player.id]) > 21:
                # 버튼 비활성화
                for child in self.children:
                    child.disabled = True
                await interaction.edit_original_response(view=self)
                self.stop()
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)
    
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            await self.game.stand(self.current_player.id)
            
            # 버튼 비활성화
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            self.stop()
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)
    
    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger, emoji="💰")
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            await self.game.double_down(self.current_player.id)
            
            # 핸드 업데이트
            embed = await self.game.create_game_embed(self.current_player)
            await interaction.response.edit_message(embed=embed)
            
            # 버튼 비활성화
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(view=self)
            self.stop()
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)
    
    @discord.ui.button(label="Split", style=discord.ButtonStyle.success, emoji="🔀")
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            player_id = self.current_player.id
            hand = self.game.player_hands[player_id]
            
            # 스플릿 가능한지 확인
            if len(hand) == 2 and hand[0][0] == hand[1][0]:
                success = await self.game.split(player_id)
                if success:
                    # 핸드 업데이트
                    embed = await self.game.create_game_embed(self.current_player)
                    await interaction.response.edit_message(embed=embed)
                    
                    # 버튼 재구성 (스플릿 버튼 제거)
                    for child in self.children:
                        if child.label == "Split":
                            child.disabled = True
                    await interaction.edit_original_response(view=self)
                else:
                    await interaction.response.send_message("스플릿할 수 없습니다!", ephemeral=True)
            else:
                await interaction.response.send_message("스플릿할 수 있는 카드가 아닙니다!", ephemeral=True)
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)

# 스플릿 핸드용 버튼 뷰
class BlackjackSplitView(discord.ui.View):
    def __init__(self, game, current_player):
        super().__init__(timeout=60)
        self.game = game
        self.current_player = current_player
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="👆")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            await self.game.hit(self.current_player.id, is_split=True)
            
            # 핸드 업데이트
            embed = await self.game.create_game_embed(self.current_player)
            await interaction.response.edit_message(embed=embed)
            
            # 버스트 체크
            if self.game.calculate_hand_value(self.game.player_split_hands[self.current_player.id]) > 21:
                # 버튼 비활성화
                for child in self.children:
                    child.disabled = True
                await interaction.edit_original_response(view=self)
                self.stop()
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)
    
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            await self.game.stand(self.current_player.id, is_split=True)
            
            # 버튼 비활성화
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            self.stop()
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)
    
    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger, emoji="💰")
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.current_player.id:
            await self.game.double_down(self.current_player.id, is_split=True)
            
            # 핸드 업데이트
            embed = await self.game.create_game_embed(self.current_player)
            await interaction.response.edit_message(embed=embed)
            
            # 버튼 비활성화
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(view=self)
            self.stop()
        else:
            await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)

# 블랙잭 참가 뷰
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

# 메인 함수
def setup(bot_instance):
    """봇 설정"""
    global DEBUG_MODE
    if hasattr(bot_instance, 'blackjack_debug_mode'):
        DEBUG_MODE = bot_instance.blackjack_debug_mode
    
