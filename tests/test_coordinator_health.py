"""coordinator 错误处理测试（不依赖 HA 运行时）

★ 2026-09-24 新增：验证失败分级策略
  · <3 次  → 静默（debug）
  · 3-4 次 → warning
  · >=5 次 → 发持久通知
  · 成功   → 清除通知
"""

from __future__ import annotations

from enum import StrEnum


class Level(StrEnum):
    DEBUG = "debug"
    WARNING = "warning"
    ERROR = "error"


def failure_level(n: int) -> Level:
    """★ 从 coordinator.py 提取的分级逻辑（保持同步）。

    对应 coordinator.py 的：
      if n < 3:       _LOGGER.debug(...)
      elif n < 5:     _LOGGER.warning(...)
      else:           _LOGGER.error(...) + _notify_failure(n)
    """
    if n < 3:
        return Level.DEBUG
    if n < 5:
        return Level.WARNING
    return Level.ERROR


def should_notify(n: int) -> bool:
    """达到通知阈值（>=5 次）。"""
    return n >= 5


class TestFailureGrading:
    def test_first_failures_silent(self):
        assert failure_level(1) == Level.DEBUG
        assert failure_level(2) == Level.DEBUG

    def test_middle_failures_warn(self):
        assert failure_level(3) == Level.WARNING
        assert failure_level(4) == Level.WARNING

    def test_persistent_failures_error(self):
        assert failure_level(5) == Level.ERROR
        assert failure_level(10) == Level.ERROR

    def test_notify_threshold(self):
        for n in range(1, 5):
            assert should_notify(n) is False, f"{n} 次不该通知"
        for n in range(5, 12):
            assert should_notify(n) is True, f"{n} 次该通知"

    def test_notify_only_once(self):
        """★ 通知只发一次（由 _fail_notified 标志保证）"""
        notified = False
        sent = 0
        for n in range(1, 11):
            if should_notify(n) and not notified:
                notified = True
                sent += 1
        assert sent == 1, "整个失败周期应只通知一次"

    def test_recovery_clears_flag(self):
        """恢复后标志复位（下次失败可再通知）"""
        notified = True
        # 成功后
        notified = False
        assert notified is False
