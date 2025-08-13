# shop.py
import json
import logging
from typing import Dict, List, Optional
import discord
from discord import app_commands
from utility import (
    get_user_inventory, get_batch_user_data, update_user_inventory,
    batch_update_user_inventory, get_user_permissions, is_user_dead,
    cache_manager, calculate_corruption_change, validate_corruption_input
)

logger = logging.getLogger(__name__)

class InventoryManager:
    """인벤토리 관리 최적화 클래스 - 새로운 데이터 구조 지원"""
    
    def __init__(self):
        # AmmoManager 제거됨 - 더 이상 필요하지 않음
        pass

    async def get_cached_inventory(self, user_id: str) -> Optional[Dict]:
        """캐시된 사용자 인벤토리 조회"""
        cache_key = f"inventory:{user_id}"
        cached = await cache_manager.get(cache_key)
        if cached:
            return json.loads(cached) if isinstance(cached, str) else cached
            
        inventory = await get_user_inventory(user_id)
        if inventory:
            await cache_manager.set(cache_key, json.dumps(inventory), ex=300)
        return inventory

    async def batch_revoke_items(self, target_id: str, items: List[str], 
                               item_type: Optional[str] = None) -> bool:
        """배치 아이템 회수 처리 (새로운 구조)"""
        target_inventory = await self.get_cached_inventory(target_id)
        if not target_inventory:
            return False

        updated = False
        
        for item in items:
            # 신체현황 회수
            if item_type == "신체현황" and item in target_inventory.get("physical_status", []):
                target_inventory["physical_status"].remove(item)
                updated = True
            # 복장 회수
            elif item_type == "복장" and item in target_inventory.get("outfits", []):
                target_inventory["outfits"].remove(item)
                updated = True
            # 일반 아이템 회수
            elif item in target_inventory.get("items", []):
                target_inventory["items"].remove(item)
                updated = True
            # 타락도 회수 (특별 처리)
            elif item_type == "타락도":
                is_valid, corruption_change = validate_corruption_input(item)
                if is_valid:
                    current_corruption = target_inventory.get("corruption", 0)
                    # 타락도는 감소 방향으로 회수 (음수로 처리)
                    new_corruption = calculate_corruption_change(current_corruption, -abs(corruption_change))
                    target_inventory["corruption"] = new_corruption
                    updated = True
        
        if updated:
            await cache_manager.delete(f"inventory:{target_id}")
            success = await update_user_inventory(
                target_id,
                target_inventory["coins"],
                target_inventory["items"],
                target_inventory.get("outfits", []),
                target_inventory.get("physical_status", []),
                target_inventory.get("corruption", 0)
            )
            return success
            
        return False

    async def process_give_command(self, interaction: discord.Interaction, 
                                 아이템: str, 유형: str, 
                                 대상: Optional[discord.Member] = None) -> bool:
        """지급 명령어 처리 (새로운 구조)"""
        try:
            # 권한 확인
            can_give, _ = await get_user_permissions(str(interaction.user.id))
            if not can_give:
                await interaction.followup.send("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
                return False

            # 전체 유저 데이터 가져오기
            all_users = await get_batch_user_data()
            if not all_users:
                await interaction.followup.send("유저 데이터를 찾을 수 없습니다.", ephemeral=True)
                return False

            # 대상 필터링
            filtered_users = self._filter_target_users(all_users, 대상)
            if not filtered_users:
                if 대상:
                    if str(대상.id) not in all_users:
                        await interaction.followup.send(f"{대상.display_name}님의 정보를 찾을 수 없습니다.", ephemeral=True)
                    else:
                        await interaction.followup.send("사망한 자에게는 아이템을 지급할 수 없습니다.", ephemeral=True)
                else:
                    await interaction.followup.send("지급 가능한 유저가 없습니다.", ephemeral=True)
                return False

            # 업데이트 데이터 생성
            updates = self._create_give_updates(filtered_users, 아이템, 유형)
            if not updates:
                await interaction.followup.send("잘못된 지급 정보입니다.", ephemeral=True)
                return False

            # 데이터 업데이트
            success = await batch_update_user_inventory(updates)
            if not success:
                await interaction.followup.send("지급 처리 중 오류가 발생했습니다.", ephemeral=True)
                return False

            # 결과 메시지
            target_name = (
                f"{filtered_users[str(대상.id)]['name']}님에게"
                if 대상 and str(대상.id) in filtered_users
                else "모든 러너들에게"
            )
            
            await interaction.followup.send(f"{target_name} {유형} '{아이템}'을 지급했습니다.")
            return True
            
        except Exception as e:
            logger.error(f"지급 명령어 처리 실패: {e}")
            await interaction.followup.send("지급 처리 중 오류가 발생했습니다.", ephemeral=True)
            return False

    def _filter_target_users(self, all_users: Dict, 대상: Optional[discord.Member]) -> Dict:
        """대상 유저 필터링"""
        filtered_users = {}
        
        if 대상:
            user_data = all_users.get(str(대상.id))
            if user_data and not is_user_dead(user_data):
                filtered_users[str(대상.id)] = user_data
        else:
            for user_id, user_data in all_users.items():
                if not is_user_dead(user_data):
                    filtered_users[user_id] = user_data
        
        return filtered_users

    def _create_give_updates(self, filtered_users: Dict, 아이템: str, 유형: str) -> Dict:
        """지급 업데이트 데이터 생성 (새로운 구조)"""
        updates = {}
        
        if 유형 == "코인":
            if not 아이템.isdigit():
                return {}
            amount = int(아이템)
            for user_id, user_data in filtered_users.items():
                updates[user_id] = {"coins": user_data["coins"] + amount}
                
        elif 유형 == "아이템":
            for user_id, user_data in filtered_users.items():
                updates[user_id] = {"items": user_data["items"] + [아이템]}
                
        elif 유형 == "복장":
            for user_id, user_data in filtered_users.items():
                updates[user_id] = {"outfits": user_data.get("outfits", []) + [아이템]}
                
        elif 유형 == "신체현황":
            for user_id, user_data in filtered_users.items():
                updates[user_id] = {"physical_status": user_data.get("physical_status", []) + [아이템]}
                
        elif 유형 == "타락도":
            is_valid, corruption_change = validate_corruption_input(아이템)
            if not is_valid:
                return {}
            
            for user_id, user_data in filtered_users.items():
                current_corruption = user_data.get("corruption", 0)
                new_corruption = calculate_corruption_change(current_corruption, corruption_change)
                updates[user_id] = {"corruption": new_corruption}
        
        return updates

    # shop.py의 process_trade_command 메서드 수정
    async def process_trade_command(self, interaction: discord.Interaction,
                                유형: str, 이름: str, 대상: discord.Member) -> bool:
        """거래 명령어 처리 (새로운 구조)"""
        try:
            user_id = str(interaction.user.id)
            target_id = str(대상.id)
            
            # 관리자 ID 가져오기
            from utility import get_admin_id
            admin_id = await get_admin_id()

            # 거래 불가 유형 체크
            if 유형 in ["신체현황", "타락도"]:
                await interaction.followup.send(f"{유형}은 거래할 수 없습니다.", ephemeral=True)
                return False

            # 인벤토리 확인
            giver_inventory = await get_user_inventory(user_id)
            receiver_inventory = None
            
            if target_id != admin_id:
                receiver_inventory = await get_user_inventory(target_id)
                if receiver_inventory and is_user_dead(receiver_inventory):
                    await interaction.followup.send("사망한 자에게는 아이템을 줄 수 없습니다.", ephemeral=True)
                    return False

            if not giver_inventory:
                await interaction.followup.send("유저 정보를 찾을 수 없습니다.", ephemeral=True)
                return False

            # 거래 유효성 검사
            if not self._validate_trade(giver_inventory, 유형, 이름):
                await interaction.followup.send(f"'{이름}'을(를) 보유하고 있지 않거나 유효하지 않은 거래입니다.", ephemeral=True)
                return False

            # 카페 채널에서 Admin에게 돈 1 거래 시 카페 시스템에 알림
            CAFE_CHANNEL_ID = 1388391607983800382
            if (interaction.channel_id == CAFE_CHANNEL_ID and 
                target_id == admin_id and 
                유형 == "돈" and 
                이름 == "1"):
                from cafe import handle_trade_to_admin
                await handle_trade_to_admin(user_id, target_id, 1)
                logger.info(f"카페 채널에서 Admin 거래 감지: {interaction.user.display_name}")

            # 거래 처리
            success = await self._execute_trade(
                user_id, target_id, admin_id, 유형, 이름,
                giver_inventory, receiver_inventory
            )
            
            if not success:
                await interaction.followup.send("거래 처리 중 오류가 발생했습니다.", ephemeral=True)
                return False

            # 결과 메시지
            if target_id == admin_id:
                await interaction.followup.send(f"총괄님에게 {유형} '{이름}'을 거래하였습니다.")
            else:
                await interaction.followup.send(
                    f"{interaction.user.display_name}님이 {대상.display_name}님에게 "
                    f"{유형} '{이름}'을 거래하였습니다."
                )
            return True
            
        except Exception as e:
            logger.error(f"거래 명령어 처리 실패: {e}")
            await interaction.followup.send("거래 처리 중 오류가 발생했습니다.", ephemeral=True)
            return False

    def _validate_trade(self, giver_inventory: Dict, 유형: str, 이름: str) -> bool:
        """거래 유효성 검사 (새로운 구조)"""
        if 유형 == "돈":
            if not 이름.isdigit():
                return False
            amount = int(이름)
            return amount > 0 and giver_inventory["coins"] >= amount
            
        elif 유형 == "아이템":
            return 이름 in giver_inventory.get("items", [])
            
        elif 유형 == "복장":
            return 이름 in giver_inventory.get("outfits", [])
            
        return False

    async def _execute_trade(self, user_id: str, target_id: str, admin_id: str,
                           유형: str, 이름: str, giver_inventory: Dict,
                           receiver_inventory: Optional[Dict]) -> bool:
        """거래 실행 (새로운 구조)"""
        try:
            # Admin에게 거래하는 경우
            if target_id == admin_id:
                return await self._trade_to_admin(user_id, 유형, 이름, giver_inventory)
            
            # 일반 유저 간 거래
            return await self._trade_between_users(
                user_id, target_id, 유형, 이름, giver_inventory, receiver_inventory
            )
            
        except Exception as e:
            logger.error(f"거래 실행 실패: {e}")
            return False

    async def _trade_to_admin(self, user_id: str, 유형: str, 이름: str, 
                            giver_inventory: Dict) -> bool:
        """관리자에게 거래 (새로운 구조)"""
        if 유형 == "돈":
            amount = int(이름)
            giver_inventory["coins"] -= amount
        elif 유형 == "아이템":
            giver_inventory["items"].remove(이름)
        elif 유형 == "복장":
            giver_inventory["outfits"].remove(이름)
        
        return await update_user_inventory(
            user_id,
            giver_inventory["coins"],
            giver_inventory["items"],
            giver_inventory.get("outfits", []),
            giver_inventory.get("physical_status", []),
            giver_inventory.get("corruption", 0)
        )

    async def _trade_between_users(self, user_id: str, target_id: str, 유형: str, 
                                 이름: str, giver_inventory: Dict, 
                                 receiver_inventory: Dict) -> bool:
        """사용자 간 거래 (새로운 구조)"""
        if 유형 == "돈":
            amount = int(이름)
            giver_inventory["coins"] -= amount
            receiver_inventory["coins"] += amount
        elif 유형 == "아이템":
            giver_inventory["items"].remove(이름)
            receiver_inventory["items"].append(이름)
        elif 유형 == "복장":
            giver_inventory["outfits"].remove(이름)
            receiver_inventory["outfits"].append(이름)

        # 두 사용자 인벤토리 업데이트
        success1 = await update_user_inventory(
            user_id,
            giver_inventory["coins"],
            giver_inventory["items"],
            giver_inventory.get("outfits", []),
            giver_inventory.get("physical_status", []),
            giver_inventory.get("corruption", 0)
        )
        
        success2 = await update_user_inventory(
            target_id,
            receiver_inventory["coins"],
            receiver_inventory["items"],
            receiver_inventory.get("outfits", []),
            receiver_inventory.get("physical_status", []),
            receiver_inventory.get("corruption", 0)
        )
        
        return success1 and success2

# 전역 인벤토리 매니저
inventory_manager = InventoryManager()

def get_inventory_manager():
    """인벤토리 매니저 반환"""
    return inventory_manager

async def create_item_autocomplete_choices(user_id: str, 유형: str, current: str) -> List[app_commands.Choice]:
    """아이템 자동완성 선택지 생성 (새로운 구조)"""
    try:
        if 유형 == "돈":
            user_data = await get_user_inventory(user_id)
            if user_data:
                current_balance = user_data.get("coins", 0)
                return [
                    app_commands.Choice(
                        name=f"현재잔액: {current_balance}, 정수로 입력하세요", 
                        value="0"
                    )
                ]
        
        all_users = await get_batch_user_data()
        if user_id not in all_users:
            return []

        user_data = all_users[user_id]
        
        if 유형 == "아이템":
            items = user_data.get("items", [])
        elif 유형 == "복장":
            items = user_data.get("outfits", [])
        else:
            return []

        # 현재 입력에 따라 필터링
        filtered_items = [
            item for item in items 
            if current.lower() in item.lower()
        ]
        
        return [
            app_commands.Choice(name=item, value=item)
            for item in filtered_items[:25]
        ]
        
    except Exception as e:
        logger.error(f"자동완성 생성 실패: {e}")
        return []

async def create_revoke_autocomplete_choices(target_id: str, current: str) -> List[app_commands.Choice]:
    """회수 자동완성 선택지 생성 (새로운 구조)"""
    try:
        target_inventory = await inventory_manager.get_cached_inventory(target_id)
        if not target_inventory:
            return []
            
        all_items = target_inventory.get("items", [])
        outfits = target_inventory.get("outfits", [])
        physical_status = target_inventory.get("physical_status", [])
        
        # 타락도 옵션 (현재 값 표시)
        corruption_options = []
        current_corruption = target_inventory.get("corruption", 0)
        if current_corruption > 0:
            corruption_options = [f"타락도:{current_corruption}"]
        
        all_options = all_items + outfits + physical_status + corruption_options
        
        # 현재 입력에 따라 필터링
        filtered_items = [
            item for item in all_options 
            if current.lower() in item.lower()
        ]
        
        return [
            app_commands.Choice(name=item, value=item)
            for item in filtered_items[:25]
        ]
        
    except Exception as e:
        logger.error(f"회수 자동완성 생성 실패: {e}")
        return []