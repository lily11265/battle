# hot_reload.py
import importlib
import sys
import logging
import traceback
import os
import json
import asyncio
from typing import Dict, List, Optional, Set
from datetime import datetime
import discord
from discord.ext import commands
from debug_config import debug_log, debug_config

logger = logging.getLogger(__name__)

class HotReloadSystem:
    """핫 리로드 시스템"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reload_history = []
        self.file_watchers = {}
        self.module_dependencies = {}
        self._build_dependency_map()
        
    def _build_dependency_map(self):
        """모듈 의존성 맵 구성"""
        # 각 모듈이 의존하는 다른 모듈들을 매핑
        self.module_dependencies = {
            'minigames_commands': [
                'dart', 'fishing', 'dalgona', 'mafia', 
                'wanage', 'matsuri_bingo', 'battle', 'debug_config'
            ],
            'shop': ['utility'],
            'matsuri_bingo': ['utility', 'debug_config'],
            'battle': ['utility', 'debug_config'],
            # 각 게임 모듈들
            'dart': ['utility', 'debug_config'],
            'fishing': ['utility', 'debug_config'],
            'dalgona': ['utility', 'debug_config'],
            'mafia': ['utility', 'debug_config'],
            'wanage': ['utility', 'debug_config']
        }
    
    async def reload_module(self, module_name: str) -> tuple[bool, str]:
        """특정 모듈 리로드"""
        try:
            debug_log("HOT_RELOAD", f"Reloading module: {module_name}")
            
            # 의존성 체크
            dependencies = self.module_dependencies.get(module_name, [])
            
            # 의존하는 모듈들 먼저 리로드
            for dep in dependencies:
                if dep in sys.modules:
                    importlib.reload(sys.modules[dep])
                    debug_log("HOT_RELOAD", f"Reloaded dependency: {dep}")
            
            # 모듈 리로드
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
                
                # Cog인 경우 재로드
                if module_name == 'minigames_commands':
                    await self.reload_cog(module_name)
                
                # 게임 인스턴스 업데이트
                await self._update_game_instances(module_name)
                
                self.reload_history.append({
                    'module': module_name,
                    'timestamp': datetime.now(),
                    'status': 'success'
                })
                
                return True, f"모듈 '{module_name}' 리로드 성공"
            else:
                return False, f"모듈 '{module_name}'을 찾을 수 없습니다"
                
        except Exception as e:
            error_msg = f"모듈 리로드 실패: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            
            self.reload_history.append({
                'module': module_name,
                'timestamp': datetime.now(),
                'status': 'failed',
                'error': str(e)
            })
            
            return False, error_msg
    
    async def reload_cog(self, cog_name: str) -> tuple[bool, str]:
        """Cog 리로드"""
        try:
            debug_log("HOT_RELOAD", f"Reloading cog: {cog_name}")
            
            # 기존 Cog 언로드
            await self.bot.unload_extension(cog_name)
            
            # Cog 재로드
            await self.bot.load_extension(cog_name)
            
            # 슬래시 커맨드 재동기화
            await self.bot.tree.sync()
            
            return True, f"Cog '{cog_name}' 리로드 성공"
            
        except Exception as e:
            error_msg = f"Cog 리로드 실패: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    async def _update_game_instances(self, module_name: str):
        """게임 인스턴스 업데이트"""
        try:
            # 게임 모듈별 인스턴스 업데이트
            if module_name == 'dart':
                from dart import get_dart_game
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'dart_game'):
                            cog.dart_game = get_dart_game()
                            debug_log("HOT_RELOAD", "Updated dart game instance")
                            
            elif module_name == 'fishing':
                from fishing import get_fishing_game
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'fishing_game'):
                            cog.fishing_game = get_fishing_game()
                            debug_log("HOT_RELOAD", "Updated fishing game instance")
                            
            elif module_name == 'dalgona':
                from dalgona import get_dalgona_game
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'dalgona_game'):
                            cog.dalgona_game = get_dalgona_game()
                            debug_log("HOT_RELOAD", "Updated dalgona game instance")
                            
            elif module_name == 'mafia':
                from mafia import get_mafia_game
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'mafia_game'):
                            cog.mafia_game = get_mafia_game()
                            debug_log("HOT_RELOAD", "Updated mafia game instance")
                            
            elif module_name == 'wanage':
                from wanage import get_wanage_game
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'wanage_game'):
                            cog.wanage_game = get_wanage_game()
                            debug_log("HOT_RELOAD", "Updated wanage game instance")
                            
            elif module_name == 'matsuri_bingo':
                from matsuri_bingo import get_matsuri_bingo_game
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'bingo_game'):
                            cog.bingo_game = get_matsuri_bingo_game()
                            debug_log("HOT_RELOAD", "Updated bingo game instance")
                            
            elif module_name == 'battle':
                from battle import get_battle_game
                self.bot.battle_game = get_battle_game()
                if hasattr(self.bot, 'cogs'):
                    for cog in self.bot.cogs.values():
                        if hasattr(cog, 'battle_game'):
                            cog.battle_game = get_battle_game()
                            debug_log("HOT_RELOAD", "Updated battle game instance")
                            
        except Exception as e:
            logger.error(f"게임 인스턴스 업데이트 실패: {e}")
    
    async def reload_config(self) -> tuple[bool, str]:
        """설정 파일 리로드"""
        try:
            config_file = 'config.json'
            with open(config_file, 'r', encoding='utf-8') as f:
                new_config = json.load(f)
            
            # 안전한 설정만 업데이트
            safe_keys = ['prefix', 'features', 'dice_bot']
            for key in safe_keys:
                if key in new_config:
                    self.bot.config[key] = new_config[key]
            
            debug_log("HOT_RELOAD", "Configuration reloaded")
            return True, "설정 파일 리로드 성공"
            
        except Exception as e:
            error_msg = f"설정 파일 리로드 실패: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    async def safe_reload_all(self) -> tuple[bool, List[str]]:
        """모든 모듈 안전하게 리로드"""
        results = []
        
        # 리로드 순서 (의존성 고려)
        reload_order = [
            'debug_config',
            'utility',
            'shop',
            'dart',
            'fishing',
            'dalgona',
            'mafia',
            'wanage',
            'matsuri_bingo',
            'battle',
            'minigames_commands'
        ]
        
        for module in reload_order:
            if module in sys.modules:
                success, msg = await self.reload_module(module)
                results.append(f"{module}: {'✅' if success else '❌'} {msg}")
                
                if not success and module in ['utility', 'debug_config']:
                    # 핵심 모듈 실패 시 중단
                    results.append("⚠️ 핵심 모듈 리로드 실패로 중단")
                    return False, results
        
        # 설정 리로드
        success, msg = await self.reload_config()
        results.append(f"config: {'✅' if success else '❌'} {msg}")
        
        return True, results
    
    def get_reload_history(self, limit: int = 10) -> List[Dict]:
        """리로드 기록 조회"""
        return self.reload_history[-limit:]

# 전역 핫 리로드 시스템
hot_reload_system = None

def setup_hot_reload(bot: commands.Bot):
    """핫 리로드 시스템 설정"""
    global hot_reload_system
    hot_reload_system = HotReloadSystem(bot)
    return hot_reload_system