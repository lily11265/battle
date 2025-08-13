# heroes/lucencia.py
"""루센시아 스킬 - 체력 소모 부활"""

from .base import BaseSkill

class LucenciaSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="루센시아",
            skill_id=13,
            description="체력을 -20 소모해서 사망한 유저 부활"
        )
        self.priority_user_id = "1237738945635160104"
    
    def execute(self, caster, target, battle_context, duration=1):
        """스킬 실행"""
        result = {
            "success": True,
            "message": f"{caster.name}이(가) 루센시아 스킬을 발동했습니다!",
            "effects": []
        }
        
        effect = {
            "type": "resurrection_ability",
            "caster": caster,
            "duration": duration,
            "source": "루센시아"
        }
        
        battle_context.add_effect(effect)
        result["effects"].append(f"{caster.name}은(는) 이제 체력을 소모하여 죽은 유저를 부활시킬 수 있습니다! (지속: {duration}라운드)")
        
        # 몬스터가 사용 시 방어 주사위 0 보정
        if caster.is_monster:
            defense_debuff = {
                "type": "defense_dice_override",
                "target": caster,
                "value": 0,
                "duration": duration,
                "source": "루센시아"
            }
            battle_context.add_effect(defense_debuff)
            result["effects"].append(f"{caster.name}의 방어 주사위가 0으로 고정됩니다!")
        
        return result
    
    def on_attack_turn(self, caster, battle_context):
        """공격 턴에 부활 시도"""
        if not self.is_active or caster != self.caster:
            return None
        
        dead_users = battle_context.get_dead_users()
        if not dead_users:
            return None
        
        # 우선순위 유저 확인
        priority_user = None
        for user in dead_users:
            if user.id == self.priority_user_id:
                priority_user = user
                break
        
        target_user = priority_user if priority_user else dead_users[0]
        
        # 체력 소모
        caster.hp -= 20
        
        # 부활
        target_user.revive(50)
        
        return {
            "message": f"{caster.name}이(가) 체력 20을 소모하여 {target_user.name}을(를) 부활시켰습니다!",
            "revived_user": target_user
        }