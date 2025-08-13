# joker_game.py (joker.py의 내용을 모듈화)
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from typing import List, Dict, Optional
import logging
from card_utils import get_card_image_manager

logger = logging.getLogger(__name__)

# 특별한 이름 매핑
SPECIAL_NAMES = {
    "아카시 하지메": "아카시 하지메",
    "펀처": "펀처",
    "유진석": "유진석",
    "휘슬": "휘슬",
    "배달기사": "배달기사",
    "페이": "페이",
    "로메즈 아가레스": "로메즈 아가레스",
    "레이나 하트베인": "레이나 하트베인",
    "비비": "비비",
    "오카미 나오하": "오카미 나오하",
    "카라트에크": "카라트에크",
    "토트": "토트",
    "처용": "처용",
    "멀 플리시": "멀 플리시",
    "코발트윈드": "코발트윈드",
    "옥타": "옥타",
    "베레니케": "베레니케",
    "안드라 블랙": "안드라 블랙",
    "봉고 3호": "봉고 3호",
    "몰": "몰",
    "베니": "베니",
    "백야": "백야",
    "루치페르": "루치페르",
    "벨사이르 드라켄리트": "벨사이르 드라켄리트",
    "불스": "불스",
    "퓨어 메탈": "퓨어 메탈",
    "노 단투": "노 단투",
    "라록": "라록",
    "아카이브": "아카이브",
    "베터": "베터",
    "메르쿠리": "메르쿠리",
    "마크-112": "마크-112",
    "스푸트니크 2세": "스푸트니크 2세",
    "이터니티": "이터니티",
    "커피머신": "커피머신"
}

def get_player_name(user: discord.Member) -> str:
    """플레이어의 표시 이름 결정"""
    display_name = user.display_name
    
    # 특별한 이름이 포함되어 있는지 확인
    for special_name in SPECIAL_NAMES.keys():
        if special_name in display_name:
            return special_name
    
    return display_name

class JoinButton(discord.ui.View):
    def __init__(self, game_instance):
        super().__init__(timeout=20)
        self.game = game_instance
        self.participants = []
    
    @discord.ui.button(label='참가하기', style=discord.ButtonStyle.primary, emoji='🎮')
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants:
            await interaction.response.send_message("이미 참가하셨습니다!", ephemeral=True)
            return
        
        if len(self.participants) >= 10:
            await interaction.response.send_message("최대 인원(10명)에 도달했습니다!", ephemeral=True)
            return
        
        self.participants.append(interaction.user)
        player_name = get_player_name(interaction.user)
        await interaction.response.send_message(f"{player_name}님이 참가했습니다! (현재 {len(self.participants)}명)", ephemeral=False)
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

class JokerGame:
    def __init__(self):
        self.games = {}  # 채널별 게임 상태 저장
        self.card_manager = get_card_image_manager()
        
    def determine_cards_per_player(self, player_count: int) -> int:
        """플레이어 수에 따른 카드 개수 결정"""
        cards_mapping = {
            2: 10, 3: 10, 4: 10, 5: 10,
            6: 8, 7: 7, 8: 6, 9: 5, 10: 5
        }
        return cards_mapping.get(player_count, 5)
    
    def create_balanced_deck(self, total_cards_needed: int, extra_cards: int = 20) -> List[str]:
        """균형잡힌 카드 덱 생성 (모든 카드는 정확히 짝수개, 조커는 1개)"""
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        
        # 조커를 제외한 필요한 카드 수
        total_regular_cards = total_cards_needed + extra_cards - 1  # -1은 조커 공간
        
        # 짝수로 만들기
        if total_regular_cards % 2 == 1:
            total_regular_cards += 1
        
        deck = []
        
        # 각 랭크별로 필요한 카드 생성
        cards_created = 0
        rank_idx = 0
        
        while cards_created < total_regular_cards:
            current_rank = ranks[rank_idx % len(ranks)]
            
            # 남은 카드 수 계산
            remaining_cards = total_regular_cards - cards_created
            
            # 2장 또는 4장씩 추가 (항상 짝수)
            if remaining_cards >= 4 and random.random() > 0.5:
                # 같은 숫자 4장 (모든 무늬)
                for suit in suits:
                    deck.append(f"{suit}{current_rank}")
                cards_created += 4
            else:
                # 같은 숫자 2장 (랜덤 무늬 2개)
                selected_suits = random.sample(suits, 2)
                for suit in selected_suits:
                    deck.append(f"{suit}{current_rank}")
                cards_created += 2
            
            rank_idx += 1
        
        # 덱 섞기
        random.shuffle(deck)
        
        # 조커를 플레이어가 받을 카드 범위 내에 삽입
        joker_position = random.randint(0, min(total_cards_needed - 1, len(deck)))
        deck.insert(joker_position, '🃏조커')
        
        logger.info(f"덱 생성 완료: 총 {len(deck)}장 (조커 포함)")
        logger.info(f"조커 위치: {joker_position}번째")
        
        # 각 랭크별 카드 수 확인 (디버깅용)
        rank_count = {}
        for card in deck:
            if '조커' not in card:
                rank = card[1:]
                rank_count[rank] = rank_count.get(rank, 0) + 1
        
        # 모든 카드가 짝수개인지 확인
        for rank, count in rank_count.items():
            if count % 2 != 0:
                logger.error(f"경고: {rank} 카드가 {count}장으로 홀수개입니다!")
        
        # 조커가 확실히 포함되었는지 확인
        if '🃏조커' not in deck:
            logger.error("경고: 조커가 덱에 포함되지 않았습니다!")
            # 강제로 조커 추가
            deck.insert(random.randint(0, min(total_cards_needed - 1, len(deck) - 1)), '🃏조커')
        
        return deck

    
    def check_and_remove_pairs(self, cards: List[Dict]) -> tuple[List[Dict], List[str]]:
        """같은 숫자 카드 쌍 제거 (조커는 절대 제거되지 않음)"""
        rank_groups = {}
        joker_card = None
        
        for card in cards:
            if '조커' in card['name']:
                joker_card = card
                logger.debug(f"조커 발견: {card['name']}")
            else:
                rank = card['name'][1:]
                if rank not in rank_groups:
                    rank_groups[rank] = []
                rank_groups[rank].append(card)
        
        remaining_cards = []
        removed_pairs = []
        
        for rank, rank_cards in rank_groups.items():
            if len(rank_cards) >= 2:
                pairs_to_remove = (len(rank_cards) // 2) * 2
                for i in range(pairs_to_remove):
                    removed_pairs.append(rank_cards[i]['name'])
                
                if len(rank_cards) % 2 == 1:
                    remaining_cards.append(rank_cards[-1])
            else:
                remaining_cards.append(rank_cards[0])
        
        if joker_card:
            remaining_cards.append(joker_card)
            logger.debug(f"조커 유지됨")
        
        return remaining_cards, removed_pairs

    async def start_game(self, interaction: discord.Interaction):
        """조커 뽑기 게임 시작"""
        channel_id = interaction.channel_id
        
        if channel_id in self.games and self.games[channel_id].get('active'):
            await interaction.response.send_message("이미 게임이 진행 중입니다!", ephemeral=True)
            return
        
        # 게임 상태 초기화
        self.games[channel_id] = {
            'active': True,
            'players': [],
            'player_cards': {},
            'turn_order': [],
            'current_turn': 0,
            'winners': []
        }
        
        embed = discord.Embed(
            title="🃏 조커 뽑기 게임",
            description="20초 동안 참가 신청을 받습니다!\n아래 버튼을 눌러 참가하세요!",
            color=discord.Color.blue()
        )
        
        view = JoinButton(self)
        await interaction.response.send_message(embed=embed, view=view)
        
        # 20초 대기
        await asyncio.sleep(20)
        
        # 참가자 확인
        if len(view.participants) < 2:
            embed = discord.Embed(
                title="게임 취소",
                description="참가자가 부족합니다. (최소 2명)",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            self.games[channel_id]['active'] = False
            return
        
        # 게임 진행
        players = view.participants
        self.games[channel_id]['players'] = players
        
        # 턴 순서 랜덤 설정
        turn_order = players.copy()
        random.shuffle(turn_order)
        self.games[channel_id]['turn_order'] = turn_order
        
        # 카드 분배
        cards_per_player = self.determine_cards_per_player(len(players))
        total_cards = cards_per_player * len(players)
        
        # 카드 분배 시작
        embed = discord.Embed(
            title="🎲 카드를 분배하고 있습니다...",
            description=f"참가자: {len(players)}명\n총 카드: {total_cards}장 (각 {cards_per_player}장)",
            color=discord.Color.yellow()
        )
        await interaction.edit_original_response(embed=embed, view=None)
        
        # 개선된 카드 분배 로직
        success = await self.distribute_cards_evenly(players, cards_per_player, total_cards)
        
        if not success:
            embed = discord.Embed(
                title="오류",
                description="카드 분배 중 문제가 발생했습니다.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed)
            self.games[channel_id]['active'] = False
            return
        
        # 초기 카드 제거 정보 수집
        initial_removed_info = {}
        for player in players:
            player_hand = self.games[channel_id]['player_cards'][player.id]
            player_hand, removed = self.check_and_remove_pairs(player_hand)
            self.games[channel_id]['player_cards'][player.id] = player_hand
            
            if removed:
                initial_removed_info[player] = removed
        
        # 게임 시작 알림
        turn_list = "\n".join([f"{i+1}. {get_player_name(p)}" for i, p in enumerate(turn_order)])
        
        embed = discord.Embed(
            title="🎯 게임 시작!",
            description=f"총 {total_cards}장의 카드가 분배되었습니다.\n`/내카드`로 확인하세요!",
            color=discord.Color.green()
        )
        
        # 각 플레이어의 카드 수 표시
        card_count_text = ""
        for player in players:
            card_count = len(self.games[channel_id]['player_cards'][player.id])
            card_count_text += f"**{get_player_name(player)}**: {card_count}장\n"
        
        embed.add_field(
            name="플레이어별 카드 수",
            value=card_count_text,
            inline=False
        )
        
        if initial_removed_info:
            removed_text = ""
            for player, removed_cards in initial_removed_info.items():
                if removed_cards:
                    player_name = get_player_name(player)
                    removed_text += f"**{player_name}**: {len(removed_cards)}장 제거\n"
            
            if removed_text:
                embed.add_field(
                    name="🗑️ 초기 카드 제거",
                    value=removed_text,
                    inline=False
                )
        
        embed.add_field(name="턴 순서", value=turn_list, inline=False)
        embed.add_field(
            name="현재 차례", 
            value=f"**{get_player_name(turn_order[0])}**님의 차례입니다!",
            inline=False
        )
        
        await interaction.edit_original_response(embed=embed)

    async def distribute_cards_evenly(self, players: List[discord.Member], cards_per_player: int, total_cards: int) -> bool:
        """카드를 균등하게 분배 (같은 랭크가 한 플레이어에게 몰리지 않도록)"""
        channel_id = list(self.games.keys())[-1]  # 현재 게임의 channel_id
        
        # 플레이어별 카드 초기화
        for player in players:
            self.games[channel_id]['player_cards'][player.id] = []
        
        # 덱 생성
        deck = self.create_balanced_deck(total_cards, extra_cards=30)
        
        # 조커 위치 확인
        joker_index = None
        for i, card in enumerate(deck):
            if '조커' in card:
                joker_index = i
                break
        
        # 조커를 임시로 제거
        if joker_index is not None:
            joker_card = deck.pop(joker_index)
        
        # 카드를 랭크별로 그룹화
        rank_groups = {}
        for card in deck:
            if '조커' not in card:
                rank = card[1:]
                if rank not in rank_groups:
                    rank_groups[rank] = []
                rank_groups[rank].append(card)
        
        # 각 랭크별로 카드를 플레이어들에게 분산
        temp_hands = {player.id: [] for player in players}
        player_index = 0
        
        for rank, cards in rank_groups.items():
            # 같은 랭크의 카드들을 다른 플레이어들에게 분산
            for card in cards:
                temp_hands[players[player_index].id].append(card)
                player_index = (player_index + 1) % len(players)
        
        # 조커를 랜덤 플레이어에게 추가
        if joker_index is not None:
            joker_player = random.choice(players)
            temp_hands[joker_player.id].append(joker_card)
            logger.info(f"조커를 {get_player_name(joker_player)}님에게 분배")
        
        # 각 플레이어의 카드를 섞고 저장
        MIN_CARDS = 7
        
        for player in players:
            player_cards = temp_hands[player.id]
            random.shuffle(player_cards)  # 플레이어의 카드 순서를 섞음
            
            # 카드 딕셔너리 형태로 변환
            player_hand = []
            for i, card in enumerate(player_cards):
                player_hand.append({
                    'name': card,
                    'position': i
                })
            
            # 최소 카드 수 확인
            if len(player_hand) < MIN_CARDS:
                logger.warning(f"{get_player_name(player)}님의 카드가 {len(player_hand)}장으로 부족합니다.")
                
                # 추가 카드 필요
                additional_needed = MIN_CARDS - len(player_hand)
                
                # 남은 덱에서 추가 카드 생성
                extra_deck = self.create_balanced_deck(additional_needed * 2, extra_cards=0)
                for card in extra_deck[:additional_needed]:
                    if '조커' not in card:  # 조커가 아닌 경우만 추가
                        player_hand.append({
                            'name': card,
                            'position': len(player_hand)
                        })
            
            self.games[channel_id]['player_cards'][player.id] = player_hand
            logger.info(f"{get_player_name(player)}님: {len(player_hand)}장 분배")
        
        # 조커가 분배되었는지 최종 확인
        joker_found = False
        for player_id, cards in self.games[channel_id]['player_cards'].items():
            if any('조커' in card['name'] for card in cards):
                joker_found = True
                break
        
        if not joker_found:
            logger.error("경고: 조커가 분배되지 않았습니다! 강제 추가합니다.")
            random_player = random.choice(players)
            self.games[channel_id]['player_cards'][random_player.id].append({
                'name': '🃏조커',
                'position': len(self.games[channel_id]['player_cards'][random_player.id])
            })
        
        return True

    async def show_cards(self, interaction: discord.Interaction, shuffle: bool = False):
        """플레이어의 카드 보기"""
        channel_id = interaction.channel_id
        user_id = interaction.user.id
        
        # 조커 게임 확인
        joker_game = None
        if channel_id in self.games and self.games[channel_id].get('active'):
            if user_id in self.games[channel_id]['player_cards']:
                joker_game = self.games[channel_id]
        
        # 블랙잭 게임 확인 (blackjack_commands에서 가져오기)
        from blackjack_commands import get_active_blackjack_game
        blackjack_game = get_active_blackjack_game(channel_id, user_id)
        
        if not joker_game and not blackjack_game:
            await interaction.response.send_message("진행 중인 게임이 없습니다.", ephemeral=True)
            return
        
        player_name = get_player_name(interaction.user)
        
        # 조커 게임 카드 표시
        if joker_game:
            # 셔플 요청 시 실제 게임 상태를 업데이트
            if shuffle:
                # 직접 게임 상태의 카드를 셔플
                cards = joker_game['player_cards'][user_id]
                
                # 카드 위치 정보를 임시 저장
                temp_cards = []
                for card in cards:
                    temp_cards.append({
                        'name': card['name'],
                        'position': card['position']
                    })
                
                # 셔플
                random.shuffle(temp_cards)
                
                # 새로운 position 할당
                for i, card in enumerate(temp_cards):
                    card['position'] = i
                
                # 게임 상태에 저장
                joker_game['player_cards'][user_id] = temp_cards
                
                cards = temp_cards
            else:
                # 셔플하지 않는 경우 현재 상태 그대로 사용
                cards = joker_game['player_cards'][user_id]
            
            if len(cards) == 0:
                embed = discord.Embed(
                    title=f"🃏 {player_name}님의 카드 (조커 뽑기)",
                    description="축하합니다! 모든 카드를 버렸습니다! 🎊",
                    color=discord.Color.gold()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.defer(ephemeral=True)
                
                try:
                    hand_image = await self.card_manager.create_hand_image(cards, game_type="joker")
                    file = discord.File(hand_image, filename="joker_hand.png")
                    
                    embed = discord.Embed(
                        title=f"🃏 {player_name}님의 카드 (조커 뽑기)",
                        description=f"총 {len(cards)}장" + (" (셔플됨)" if shuffle else ""),
                        color=discord.Color.blue()
                    )
                    embed.set_image(url="attachment://joker_hand.png")
                    
                    await interaction.followup.send(embed=embed, file=file, ephemeral=True)
                except Exception as e:
                    logger.error(f"카드 이미지 생성 실패: {e}")
                    embed = discord.Embed(
                        title=f"🃏 {player_name}님의 카드 (조커 뽑기)",
                        description=f"총 {len(cards)}장" + (" (셔플됨)" if shuffle else ""),
                        color=discord.Color.blue()
                    )
                    for i, card in enumerate(cards):
                        embed.add_field(
                            name=f"카드 {i+1}",
                            value=card['name'],
                            inline=True
                        )
                    await interaction.followup.send(embed=embed, ephemeral=True)
        
        # 블랙잭 게임 카드 표시
        elif blackjack_game:
            await interaction.response.defer(ephemeral=True)
            
            player_hand = blackjack_game.player_hands[user_id]
            hand_value = blackjack_game.calculate_hand_value(player_hand)
            
            try:
                # 블랙잭 카드를 표시용 형식으로 변환
                cards_for_display = [{'rank': card[0], 'suit': card[1]} for card in player_hand]
                hand_image = await self.card_manager.create_hand_image(player_hand, game_type="blackjack")
                file = discord.File(hand_image, filename="blackjack_hand.png")
                
                embed = discord.Embed(
                    title=f"🎰 {player_name}님의 카드 (블랙잭)",
                    description=f"총 {hand_value}점",
                    color=discord.Color.green()
                )
                embed.set_image(url="attachment://blackjack_hand.png")
                
                # 스플릿 핸드가 있는 경우
                if blackjack_game.player_split[user_id]:
                    split_hand = blackjack_game.player_split_hands[user_id]
                    split_value = blackjack_game.calculate_hand_value(split_hand)
                    embed.add_field(
                        name="스플릿 핸드",
                        value=f"{blackjack_game.format_hand(split_hand)} ({split_value}점)",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            except Exception as e:
                logger.error(f"블랙잭 카드 이미지 생성 실패: {e}")
                embed = discord.Embed(
                    title=f"🎰 {player_name}님의 카드 (블랙잭)",
                    description=f"총 {hand_value}점",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="카드",
                    value=blackjack_game.format_hand(player_hand),
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

# joker.py의 JokerGame 클래스에 다음 메서드들을 추가하세요

    async def show_game_status(self, interaction: discord.Interaction):
        """게임 상태 표시"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.games or not self.games[channel_id].get('active'):
            await interaction.response.send_message("진행 중인 조커 게임이 없습니다.", ephemeral=True)
            return
        
        game = self.games[channel_id]
        turn_order = game['turn_order']
        current_turn = game['current_turn']
        current_player = turn_order[current_turn % len(turn_order)]
        
        embed = discord.Embed(
            title="🃏 조커 뽑기 게임 상태",
            color=discord.Color.blue()
        )
        
        # 턴 순서 표시
        turn_list = []
        for i, player in enumerate(turn_order):
            player_name = get_player_name(player)
            cards_count = len(game['player_cards'].get(player.id, []))
            
            if cards_count == 0:
                status = "✅ 완료"
            elif i == current_turn % len(turn_order):
                status = "▶️ 현재 차례"
            else:
                status = f"카드 {cards_count}장"
            
            turn_list.append(f"{i+1}. {player_name} - {status}")
        
        embed.add_field(
            name="턴 순서",
            value="\n".join(turn_list),
            inline=False
        )
        
        # 승리자 표시
        if game['winners']:
            winner_names = [get_player_name(w) for w in game['winners']]
            embed.add_field(
                name="🏆 승리자",
                value="\n".join([f"{i+1}위: {name}" for i, name in enumerate(winner_names)]),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)

    async def draw_card(self, interaction: discord.Interaction, target_name: str, card_number: int):
        """다른 플레이어의 카드 뽑기 (이전 턴 플레이어만 가능)"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.games or not self.games[channel_id].get('active'):
            await interaction.response.send_message("진행 중인 게임이 없습니다.", ephemeral=True)
            return
        
        game = self.games[channel_id]
        turn_order = game['turn_order']
        current_turn = game['current_turn']
        current_player = turn_order[current_turn % len(turn_order)]
        
        # 현재 차례 확인
        if interaction.user.id != current_player.id:
            await interaction.response.send_message("당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        # 이전 턴 플레이어 찾기
        active_players = [p for p in turn_order if len(game['player_cards'].get(p.id, [])) > 0]
        current_index = active_players.index(current_player)
        prev_index = (current_index - 1) % len(active_players)
        previous_player = active_players[prev_index]
        
        # 대상 플레이어 찾기
        target_player = None
        for player in game['players']:
            if get_player_name(player) == target_name:
                target_player = player
                break
        
        if not target_player:
            await interaction.response.send_message("플레이어를 찾을 수 없습니다.", ephemeral=True)
            return
        
        # 이전 턴 플레이어만 선택 가능
        if target_player.id != previous_player.id:
            await interaction.response.send_message(
                f"이전 턴의 플레이어({get_player_name(previous_player)})의 카드만 뽑을 수 있습니다!", 
                ephemeral=True
            )
            return
        
        target_hand = game['player_cards'].get(target_player.id, [])
        
        if not target_hand:
            await interaction.response.send_message(f"{target_name}님은 카드가 없습니다.", ephemeral=True)
            return
        
        if card_number < 1 or card_number > len(target_hand):
            await interaction.response.send_message(f"유효하지 않은 카드 번호입니다. (1-{len(target_hand)})", ephemeral=True)
            return
        
        # 카드 뽑기
        drawn_card = target_hand.pop(card_number - 1)
        game['player_cards'][interaction.user.id].append(drawn_card)
        
        # 조커를 뽑았는지 확인
        drew_joker = '조커' in drawn_card['name']
        
        # 뽑은 사람의 카드에서 쌍 제거
        player_hand = game['player_cards'][interaction.user.id]
        player_hand, removed_pairs = self.check_and_remove_pairs(player_hand)
        game['player_cards'][interaction.user.id] = player_hand
        
        # 임베드 생성
        embed = discord.Embed(
            title="🎴 카드 뽑기",
            description=f"{get_player_name(interaction.user)}님이 {target_name}님의 {card_number}번째 카드를 뽑았습니다!",
            color=discord.Color.green()
        )
        
        # 뽑은 카드는 표시하지 않음
        
        if removed_pairs:
            embed.add_field(
                name="제거된 카드",
                value=f"{len(removed_pairs)}장이 쌍으로 제거되었습니다.",
                inline=True
            )
        
        # 승리 확인
        if len(player_hand) == 0 and interaction.user not in game['winners']:
            game['winners'].append(interaction.user)
            embed.add_field(
                name="🎊 축하합니다!",
                value=f"{len(game['winners'])}등으로 완주했습니다!",
                inline=False
            )
        
        # 대상이 카드를 모두 잃은 경우
        if len(target_hand) == 0 and target_player not in game['winners']:
            game['winners'].append(target_player)
        
        # 다음 턴으로
        game['current_turn'] += 1
        
        # 다음 플레이어 찾기 (카드가 있는 플레이어만)
        active_players = [p for p in turn_order if len(game['player_cards'].get(p.id, [])) > 0]
        
        if len(active_players) <= 1:
            # 게임 종료
            game['active'] = False
            embed.add_field(
                name="🏁 게임 종료!",
                value="모든 플레이어가 카드를 버렸습니다.",
                inline=False
            )
            
            # 조커 보유자 찾기
            for player_id, cards in game['player_cards'].items():
                if any('조커' in card['name'] for card in cards):
                    for player in game['players']:
                        if player.id == player_id:
                            embed.add_field(
                                name="🃏 조커 보유자",
                                value=get_player_name(player),
                                inline=False
                            )
                            break
        else:
            # 다음 차례 표시
            next_player = turn_order[game['current_turn'] % len(turn_order)]
            while len(game['player_cards'].get(next_player.id, [])) == 0:
                game['current_turn'] += 1
                next_player = turn_order[game['current_turn'] % len(turn_order)]
            
            embed.add_field(
                name="다음 차례",
                value=get_player_name(next_player),
                inline=False
            )
        
        # defer 사용하여 두 개의 메시지 보내기
        await interaction.response.defer()
        
        # 공개 메시지 전송
        await interaction.followup.send(embed=embed)
        
        # 조커를 뽑았다면 ephemeral 메시지로 알림
        if drew_joker:
            joker_embed = discord.Embed(
                title="🃏 조커!",
                description="당신이 조커를 뽑았습니다!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=joker_embed, ephemeral=True)

    async def player_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """플레이어 자동완성 (이전 턴 플레이어만)"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.games or not self.games[channel_id].get('active'):
            return []
        
        game = self.games[channel_id]
        turn_order = game['turn_order']
        current_turn = game['current_turn']
        current_player = turn_order[current_turn % len(turn_order)]
        
        # 현재 플레이어가 맞는지 확인
        if interaction.user.id != current_player.id:
            return []
        
        # 이전 턴 플레이어 찾기
        active_players = [p for p in turn_order if len(game['player_cards'].get(p.id, [])) > 0]
        
        try:
            current_index = active_players.index(current_player)
            prev_index = (current_index - 1) % len(active_players)
            previous_player = active_players[prev_index]
            
            player_name = get_player_name(previous_player)
            cards_count = len(game['player_cards'].get(previous_player.id, []))
            
            if cards_count > 0 and current.lower() in player_name.lower():
                return [
                    app_commands.Choice(
                        name=f"{player_name} ({cards_count}장)",
                        value=player_name
                    )
                ]
        except ValueError:
            # 현재 플레이어가 active_players에 없는 경우
            pass
        
        return []

    async def card_number_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[int]]:
        """카드 번호 자동완성"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.games or not self.games[channel_id].get('active'):
            return []
        
        # 선택된 플레이어 이름 가져오기
        if hasattr(interaction.namespace, '참여유저'):
            target_name = interaction.namespace.참여유저
            
            game = self.games[channel_id]
            
            # 대상 플레이어 찾기
            target_player = None
            for player in game['players']:
                if get_player_name(player) == target_name:
                    target_player = player
                    break
            
            if target_player:
                cards_count = len(game['player_cards'].get(target_player.id, []))
                return [
                    app_commands.Choice(name=str(i), value=i)
                    for i in range(1, cards_count + 1)
                    if str(i).startswith(current)
                ][:25]
        
        return []

    async def shuffle_turn_order(self, interaction: discord.Interaction):
        """턴 순서 섞기"""
        channel_id = interaction.channel_id
        
        if channel_id not in self.games or not self.games[channel_id].get('active'):
            await interaction.response.send_message("진행 중인 게임이 없습니다.", ephemeral=True)
            return
        
        game = self.games[channel_id]
        
        # 현재 플레이어가 게임 참가자인지 확인
        if interaction.user not in game['players']:
            await interaction.response.send_message("게임 참가자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        # 턴 순서 섞기
        random.shuffle(game['turn_order'])
        game['current_turn'] = 0
        
        # 새로운 순서 표시
        embed = discord.Embed(
            title="🔀 턴 순서 변경",
            description="턴 순서가 랜덤으로 변경되었습니다!",
            color=discord.Color.purple()
        )
        
        turn_list = "\n".join([
            f"{i+1}. {get_player_name(p)}"
            for i, p in enumerate(game['turn_order'])
        ])
        
        embed.add_field(
            name="새로운 턴 순서",
            value=turn_list,
            inline=False
        )
        
        embed.add_field(
            name="현재 차례",
            value=get_player_name(game['turn_order'][0]),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

# 전역 게임 인스턴스
joker_game = JokerGame()

def get_joker_game():
    """조커 게임 인스턴스 반환"""
    return joker_game