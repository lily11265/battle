# Discord 스킬 시스템 테스트 보고서

## 테스트 개요
- **테스트 실행 시간**: 2025년 08월 08일 00:25:37
- **총 소요 시간**: 0.00초
- **총 테스트 수**: 21
- **통과**: 14
- **실패**: 6
- **건너뜀**: 1
- **성공률**: 70.0% (건너뛴 테스트 제외)

## 테스트 결과 요약

| 테스트 클래스 | 테스트 이름 | 상태 | 실행 시간 |
|-------------|-----------|------|----------|
| TestSkillSystem | test_coal_fold_skill | ✅ PASSED | 0.025초 |
| TestSkillSystem | test_error_handling | ✅ PASSED | 0.013초 |
| TestSkillSystem | test_grim_skill_preparation | ✅ PASSED | 0.007초 |
| TestSkillSystem | test_karon_damage_sharing | ❌ FAILED | 0.266초 |
| TestSkillSystem | test_memory_management | ⏭️ SKIPPED | 0.003초 |
| TestSkillSystem | test_multiple_skills_interaction | ✅ PASSED | 0.018초 |
| TestSkillSystem | test_onixel_skill | ✅ PASSED | 0.012초 |
| TestSkillSystem | test_oriven_skill | ✅ PASSED | 0.014초 |
| TestSkillSystem | test_performance_with_many_skills | ✅ PASSED | 0.201초 |
| TestSkillSystem | test_results | ❌ FAILED | 0.003초 |
| TestSkillSystem | test_skill_addition_and_removal | ✅ PASSED | 0.016초 |
| TestSkillSystem | test_skill_manager_initialization | ✅ PASSED | 0.017초 |
| TestSkillSystem | test_skill_permission_system | ❌ FAILED | 0.007초 |
| TestSkillSystem | test_skill_round_management | ❌ FAILED | 0.011초 |
| TestSkillSystem | test_skill_state_persistence | ✅ PASSED | 0.032초 |
| TestSkillSystem | test_volken_eruption_phases | ✅ PASSED | 0.009초 |
| TestBattleAdminIntegration | test_battle_participant_integration | ✅ PASSED | 0.001초 |
| TestBattleAdminIntegration | test_damage_and_heal_integration | ✅ PASSED | 0.002초 |
| TestBattleAdminIntegration | test_results | ❌ FAILED | 0.000초 |
| TestReportGeneration | test_report_generation_success | ✅ PASSED | 0.102초 |
| TestReportGeneration | test_results | ❌ FAILED | 0.000초 |

## 성능 측정 결과

### test_performance_with_many_skills
- **skill_creation_time**: 0.19140839576721191
- **dice_processing_time**: 0.0008401870727539062
- **skills_created**: 50
- **dice_rolls_processed**: 100


## 실패한 테스트 상세 정보

### TestSkillSystem.test_karon_damage_sharing
**오류**: '111' not found in {'all_alive': 30}

```python
Traceback (most recent call last):
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 1320, in run_all_tests
    await getattr(test_instance, test_method)()
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 372, in test_karon_damage_sharing
    self.assertIn(expected_user, shared_damage)
  File "/usr/lib/python3.11/unittest/case.py", line 1140, in assertIn
    self.fail(self._formatMessage(msg, standardMsg))
  File "/usr/lib/python3.11/unittest/case.py", line 703, in fail
    raise self.failureException(msg)
AssertionError: '111' not found in {'all_alive': 30}
```

### TestSkillSystem.test_results
**오류**: 'dict' object is not callable

```python
Traceback (most recent call last):
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 1320, in run_all_tests
    await getattr(test_instance, test_method)()
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: 'dict' object is not callable
```

### TestSkillSystem.test_skill_permission_system
**오류**: Items in the second set but not the first:
'카론'
'피닉스'
'오리븐'
'오닉셀'

```python
Traceback (most recent call last):
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 1320, in run_all_tests
    await getattr(test_instance, test_method)()
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 510, in test_skill_permission_system
    self.assertEqual(set(allowed_skills), set(expected_skills))
  File "/usr/lib/python3.11/unittest/case.py", line 873, in assertEqual
    assertion_func(first, second, msg=msg)
  File "/usr/lib/python3.11/unittest/case.py", line 1133, in assertSetEqual
    self.fail(self._formatMessage(msg, standardMsg))
  File "/usr/lib/python3.11/unittest/case.py", line 703, in fail
    raise self.failureException(msg)
AssertionError: Items in the second set but not the first:
'카론'
'피닉스'
'오리븐'
'오닉셀'
```

### TestSkillSystem.test_skill_round_management
**오류**: 'SkillManager' object has no attribute 'decrease_skill_rounds'

```python
Traceback (most recent call last):
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 1320, in run_all_tests
    await getattr(test_instance, test_method)()
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 219, in test_skill_round_management
    skill_manager.decrease_skill_rounds(channel_id)
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'SkillManager' object has no attribute 'decrease_skill_rounds'
```

### TestBattleAdminIntegration.test_results
**오류**: 'dict' object is not callable

```python
Traceback (most recent call last):
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 1320, in run_all_tests
    await getattr(test_instance, test_method)()
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: 'dict' object is not callable
```

### TestReportGeneration.test_results
**오류**: 'dict' object is not callable

```python
Traceback (most recent call last):
  File "/home/wonsukhuh56/skills/test_skill_system.py", line 1320, in run_all_tests
    await getattr(test_instance, test_method)()
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: 'dict' object is not callable
```


## 분석 및 권장사항

- ❌ 상당수의 테스트가 실패했습니다. 시스템 점검이 필요합니다.

---
*생성 시간: 2025-08-08 00:25:37*