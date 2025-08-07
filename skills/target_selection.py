# skills/target_selection.py
import discord
from discord import app_commands
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from .skill_manager import skill_manager

logger = logging.getLogger(__name__)

class TargetSelectionModal(discord.ui.Modal):
    """대상 검색 모달 (25개 초과시 사용)"""
    
    def __init__(self, available_targets: List[Dict], callback_func):
        super().__init__(title="대상 검색", timeout=60)
        self.available_targets = available_targets
        self.callback_func = callback_func
        
        self.search_input = discord.ui.TextInput(
            label="대상 이름을 입력하세요",
            placeholder="유저 이름이나 몬스터 이름을 입력...",
            required=True,
            max_length=50
        )
        self.add_item(self.search_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        search_term = self.search_input.value.lower()
        
        # 검색 결과 필터링
        matches = []
        for target in self.available_targets:
            name_lower = target["name"].lower()
            if search_term in name_lower:
                matches.append(target)
        
        if not matches:
            await interaction.response.send_message("❌ 검색 결과가 없습니다.", ephemeral=True)
            return
        
        if len(matches) == 1:
            # 단일 결과 즉시 선택
            await interaction.response.defer()
            await self.callback_func(interaction, matches[0])
        else:
            # 여러 결과 중 선택
            view = TargetSelectionView(matches, self.callback_func)
            embed = discord.Embed(
                title="🔍 검색 결과",
                description=f"'{search_term}' 검색 결과 ({len(matches)}개)",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class TargetSelectionView(discord.ui.View):
    """대상 선택 드롭다운 뷰"""
    
    def __init__(self, targets: List[Dict], callback_func, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.callback_func = callback_func
        
        # 25개씩 나누어서 처리
        if len(targets) <= 25:
            self.add_item(TargetSelectDropdown(targets, callback_func))
        else:
            # 25개 초과시 검색 버튼 추가
            self.add_item(SearchTargetButton(targets, callback_func))
    
    async def on_timeout(self):
        """타임아웃 처리"""
        for item in self.children:
            item.disabled = True

class TargetSelectDropdown(discord.ui.Select):
    """대상 선택 드롭다운"""
    
    def __init__(self, targets: List[Dict], callback_func):
        self.callback_func = callback_func
        
        options = []
        for target in targets[:25]:  # Discord 제한
            emoji = self._get_target_emoji(target["type"])
            description = f"{target['type']} | HP: {target.get('health', '?')}"
            
            options.append(discord.SelectOption(
                label=target["name"],
                value=target["id"],
                description=description,
                emoji=emoji
            ))
        
        super().__init__(
            placeholder="대상을 선택하세요...",
            options=options,
            min_values=1,
            max_values=1
        )
        
        self._targets_by_id = {target["id"]: target for target in targets}
    
    def _get_target_emoji(self, target_type: str) -> str:
        """대상 타입별 이모지"""
        emoji_map = {
            "user": "👤",
            "monster": "👹",
            "admin": "⚔️",
            "dead_user": "💀"
        }
        return emoji_map.get(target_type, "❓")
    
    async def callback(self, interaction: discord.Interaction):
        selected_target = self._targets_by_id[self.values[0]]
        await interaction.response.defer()
        await self.callback_func(interaction, selected_target)

class SearchTargetButton(discord.ui.Button):
    """대상 검색 버튼 (25개 초과시)"""
    
    def __init__(self, targets: List[Dict], callback_func):
        super().__init__(
            label="대상 검색",
            emoji="🔍",
            style=discord.ButtonStyle.primary
        )
        self.targets = targets
        self.callback_func = callback_func
    
    async def callback(self, interaction: discord.Interaction):
        modal = TargetSelectionModal(self.targets, self.callback_func)
        await interaction.response.send_modal(modal)

class TargetSelector:
    """대상 선택 관리 클래스"""
    
    def __init__(self):
        self.known_names = {
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
    
    async def get_available_targets(self, channel_id: str, skill_name: str, user_id: str) -> List[Dict]:
        """사용 가능한 대상 목록 조회"""
        targets = []
        
        try:
            # Discord 채널에서 현재 참여자 정보 가져오기 (battle_admin 연동)
            from battle_admin import get_battle_participants  # battle_admin.py에서 import
            participants = await get_battle_participants(channel_id)
            
            # 유저 목록 추가
            for participant in participants.get("users", []):
                if participant["user_id"] != user_id or self._can_target_self(skill_name):
                    display_name = self._get_display_name(participant["real_name"], participant["user_name"])
                    targets.append({
                        "id": participant["user_id"],
                        "name": display_name,
                        "type": "dead_user" if participant.get("is_dead") else "user",
                        "health": participant.get("health", 0),
                        "real_name": participant["real_name"]
                    })
            
            # 몬스터/ADMIN 추가
            if participants.get("monster"):
                monster = participants["monster"]
                targets.append({
                    "id": "monster",
                    "name": monster["name"],
                    "type": "monster",
                    "health": monster.get("health", 0)
                })
            
            if participants.get("admin"):
                admin = participants["admin"]
                targets.append({
                    "id": "admin", 
                    "name": admin["name"],
                    "type": "admin",
                    "health": admin.get("health", 0)
                })
        
        except Exception as e:
            logger.error(f"참여자 목록 조회 실패: {e}")
            # 기본 대상들 (fallback)
            targets = [
                {"id": user_id, "name": "자기 자신", "type": "user", "health": 100}
            ]
        
        return targets
    
    def _can_target_self(self, skill_name: str) -> bool:
        """자기 자신을 대상으로 할 수 있는 스킬인지 확인"""
        self_target_skills = ["피닉스", "오닉셀", "스트라보스"]
        return skill_name in self_target_skills
    
    def _get_display_name(self, real_name: str, user_name: str) -> str:
        """표시용 이름 생성"""
        if real_name in self.known_names:
            return f"{real_name} ({user_name})"
        return user_name
    
    async def show_target_selection(self, interaction: discord.Interaction, skill_name: str, 
                                  duration: int, callback_func) -> None:
        """대상 선택 UI 표시"""
        channel_id = str(interaction.channel.id)
        user_id = str(interaction.user.id)
        
        # 사용 가능한 대상 목록 조회
        targets = await self.get_available_targets(channel_id, skill_name, user_id)
        
        if not targets:
            await interaction.followup.send("❌ 사용 가능한 대상이 없습니다.", ephemeral=True)
            return
        
        # 단일 대상인 경우 즉시 선택
        if len(targets) == 1:
            await callback_func(interaction, targets[0])
            return
        
        # 대상 선택 UI 표시
        embed = discord.Embed(
            title=f"🎯 {skill_name} 대상 선택",
            description=f"**{skill_name}** 스킬을 사용할 대상을 선택하세요.\n⏱️ 지속시간: {duration}라운드",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="사용 가능한 대상",
            value=f"총 {len(targets)}명의 대상이 있습니다.",
            inline=False
        )
        
        view = TargetSelectionView(targets, callback_func)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# 전역 인스턴스
target_selector = TargetSelector()