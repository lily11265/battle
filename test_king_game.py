# test_king_game.py

import asyncio
import discord
from unittest.mock import Mock, AsyncMock
from king_game import KingGame, get_king_game

async def test_king_game():
    """왕게임 테스트"""
    game = get_king_game()
    
    # 가상 채널 및 인터랙션 생성
    mock_channel = Mock(spec=discord.TextChannel)
    mock_channel.id = 12345
    mock_channel.send = AsyncMock()
    
    mock_interaction = Mock(spec=discord.Interaction)
    mock_interaction.channel_id = mock_channel.id
    mock_interaction.channel = mock_channel
    mock_interaction.response = AsyncMock()
    mock_interaction.user = Mock()
    mock_interaction.user.id = 1
    mock_interaction.user.mention = "<@1>"
    mock_interaction.user.display_name = "테스트호스트"
    
    # 가상 플레이어 생성
    test_players = []
    for i in range(6):  # 6명으로 테스트
        mock_player = Mock(spec=discord.Member)
        mock_player.id = 100 + i
        mock_player.display_name = f"테스트플레이어{i+1}"
        mock_player.mention = f"<@{mock_player.id}>"
        mock_player.send = AsyncMock()  # DM 전송 모킹
        test_players.append(mock_player)
    
    # 게임 시작
    print("왕게임 테스트 시작...")
    await game.start_game(mock_interaction, test_players)
    
    # 게임 데이터 확인
    game_data = game.active_games.get(mock_channel.id)
    if game_data:
        print(f"✅ 게임 생성 성공!")
        print(f"참가자: {len(game_data['players'])}명")
        print(f"현재 라운드: {game_data['round']}")
        
        # 왕 확인
        if 'king' in game_data:
            print(f"👑 현재 왕: {game_data['king'].user.display_name}")
        
        # 플레이어 번호 확인
        if 'player_data' in game_data:
            print("\n플레이어 번호:")
            for player in game_data['player_data'].values():
                if player.is_king:
                    print(f"  {player.user.display_name}: 👑 왕")
                else:
                    print(f"  {player.user.display_name}: {player.number}번")
    
    # 명령 실행 테스트
    if game_data and 'king' in game_data:
        print("\n명령 실행 테스트...")
        command = "{0}번과 {1}번이 하이파이브하기"
        await game.execute_command(mock_channel.id, command, 1, 2)
        print("✅ 명령 실행 완료!")
    
    # 게임 종료
    await game.end_game(mock_channel.id)
    print("\n✅ 게임 종료 완료!")

# 실행
if __name__ == "__main__":
    asyncio.run(test_king_game())