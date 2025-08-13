import random
import discord
from typing import Optional, Tuple
import asyncio

class DiceSystem:
    """독립적인 주사위 시스템"""
    
    @staticmethod
    def roll_dice(min_value: int = 1, max_value: int = 100) -> int:
        """주사위 굴리기"""
        return random.randint(min_value, max_value)
    
    @staticmethod
    def format_dice_message(player_name: str, dice_value: int, dice_type: str = "1d100") -> str:
        """주사위 결과 메시지 포맷"""
        return f"`{player_name}`님이 주사위를 굴려 **{dice_value}**이(가) 나왔습니다!"
    
    @staticmethod
    async def roll_and_send_dice(channel: discord.TextChannel, player_name: str, 
                                min_value: int = 1, max_value: int = 100,
                                dice_type: str = None, use_embed: bool = False) -> int:
        """주사위를 굴리고 결과를 채널에 전송 (임베드 옵션 수정)"""
        # 주사위 종류 결정
        if dice_type is None:
            if min_value == 1 and max_value == 100:
                dice_type = "1d100"
            else:
                dice_type = f"1d{max_value}" if min_value == 1 else f"{min_value}~{max_value}"
        
        # 주사위 굴리기
        dice_value = DiceSystem.roll_dice(min_value, max_value)
        
        # 메시지 전송 (기본적으로 텍스트로만)
        message = DiceSystem.format_dice_message(player_name, dice_value, dice_type)
        await channel.send(message)
        
        return dice_value
    
    @staticmethod
    async def roll_multiple_dice(channel: discord.TextChannel, player_name: str,
                               count: int, min_value: int = 1, max_value: int = 100) -> list:
        """여러 개의 주사위를 굴리고 결과를 전송 (간단한 텍스트로)"""
        results = []
        total = 0
        
        result_text = f"🎲 **{player_name}**님이 주사위 {count}개를 굴렸습니다!\n"
        
        for i in range(count):
            value = DiceSystem.roll_dice(min_value, max_value)
            results.append(value)
            total += value
            result_text += f"주사위 {i+1}: **{value}**\n"
        
        result_text += f"\n📊 합계: **{total}**"
        
        await channel.send(result_text)
        return results
    
    @staticmethod
    async def competitive_roll(channel: discord.TextChannel, player1_name: str, player2_name: str,
                             min_value: int = 1, max_value: int = 100) -> Tuple[int, int]:
        """경쟁 주사위 굴리기 (두 플레이어가 동시에)"""
        # 두 플레이어의 주사위 결과
        player1_roll = DiceSystem.roll_dice(min_value, max_value)
        player2_roll = DiceSystem.roll_dice(min_value, max_value)
        
        # 승자 결정
        if player1_roll > player2_roll:
            winner = player1_name
        elif player2_roll > player1_roll:
            winner = player2_name
        else:
            winner = "무승부"
        
        # 결과 텍스트
        result = f"⚔️ **주사위 대결!**\n"
        result += f"{player1_name}: 🎲 **{player1_roll}**\n"
        result += f"{player2_name}: 🎲 **{player2_roll}**\n\n"
        
        if winner != "무승부":
            result += f"🏆 승자: **{winner}**"
        else:
            result += "📊 결과: **무승부!**"
        
        await channel.send(result)
        return player1_roll, player2_roll
    
    @staticmethod
    async def roll_with_animation(channel: discord.TextChannel, player_name: str,
                                 min_value: int = 1, max_value: int = 100) -> int:
        """애니메이션 효과가 있는 주사위 굴리기 (간소화)"""
        # 초기 메시지
        message = await channel.send(f"🎲 **{player_name}**님이 주사위를 굴리고 있습니다...")
        
        # 간단한 애니메이션 (2번만 업데이트)
        for i in range(2):
            await asyncio.sleep(0.5)
            temp_value = DiceSystem.roll_dice(min_value, max_value)
            await message.edit(content=f"🎲 **{player_name}**님이 주사위를 굴리고 있습니다... {temp_value}")
        
        # 최종 결과
        await asyncio.sleep(0.5)
        final_value = DiceSystem.roll_dice(min_value, max_value)
        
        # 특수 결과 텍스트 추가
        special = ""
        if final_value <= 10:
            special = " ⚠️ **대실패!**"
        elif final_value >= 90:
            special = " ✨ **대성공!**"
        
        await message.edit(content=f"`{player_name}`님이 주사위를 굴려 **{final_value}**이(가) 나왔습니다!{special}")
        
        return final_value


# 전역 인스턴스
dice_system = DiceSystem()