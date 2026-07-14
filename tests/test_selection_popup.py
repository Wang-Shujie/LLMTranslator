"""划词弹窗关闭逻辑：150ms 防抖(挡住弹出瞬间的伪失活) + 可复用自动隐藏定时器。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtWidgets import QApplication

from llm_translator.ui.selection_popup import SelectionPopup


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _ev(t):
    return QEvent(t)


def test_deactivate_closes_when_armed(qapp):
    """武装后(弹出满 150ms)失活 → 立刻隐藏。"""
    p = SelectionPopup()
    p.show_at(QPoint(100, 100))
    qapp.processEvents()
    p._armed = True  # 模拟防抖计时器已到
    p.event(_ev(QEvent.WindowDeactivate))
    qapp.processEvents()
    assert p.isVisible() is False


def test_deactivate_ignored_during_debounce(qapp):
    """弹出瞬间的防抖窗口内失活（前台锁弹回的伪失活）→ 忽略，不闪退。"""
    p = SelectionPopup()
    p.show_at(QPoint(100, 100))
    qapp.processEvents()
    p._armed = False  # 防抖未结束
    p.event(_ev(QEvent.WindowDeactivate))
    qapp.processEvents()
    assert p.isVisible() is True


def test_show_at_disarms(qapp):
    """show_at 同步解除武装（新一轮防抖从头计），不沿用上轮残留。"""
    p = SelectionPopup()
    p._armed = True
    p.show_at(QPoint(100, 100))  # 不 processEvents，观察同步重置
    assert p._armed is False


def test_reshow_rearms_via_timer(qapp):
    """复用弹窗（连划第二个词）：show_at 解除武装，但防抖计时器重新启动，
    到时再次武装——不会像 _active 方案那样卡死在 False。"""
    p = SelectionPopup()
    p.show_at(QPoint(100, 100))
    qapp.processEvents()
    p._armed = True
    p.show_at(QPoint(200, 200))  # 复用
    assert p._armed is False  # 先解除
    assert p._arm_timer.isActive() is True  # 但计时器已重启，到时会重新武装


def test_autohide_reused_not_orphaned(qapp):
    """关键回归：复用弹窗时，上一轮的自动隐藏定时器被取消，不会误关新内容。"""
    p = SelectionPopup()
    p.show_at(QPoint(100, 100))
    qapp.processEvents()
    p._on_finished("译文A", p._gen)       # 排一个 15s 自动隐藏
    assert p._autohide.isActive() is True
    p.show_at(QPoint(200, 200))           # 用户在 15s 内又划了第二个词 → 复用
    qapp.processEvents()
    assert p._autohide.isActive() is False  # 上一轮定时器已取消
    assert p.isVisible() is True


def test_hide_cancels_timers(qapp):
    """任何方式隐藏都应取消挂起的自动隐藏 + 防抖定时器。"""
    p = SelectionPopup()
    p.show_at(QPoint(100, 100))
    qapp.processEvents()
    p._on_finished("译文", p._gen)
    assert p._autohide.isActive() is True
    p.hide()
    qapp.processEvents()
    assert p._autohide.isActive() is False
    assert p._arm_timer.isActive() is False


def test_stale_worker_tokens_ignored(qapp):
    """复用弹窗开启新翻译时，上一轮未完成 worker 的迟到 token 必须被丢弃，不串内容。"""
    p = SelectionPopup()
    # 第一轮翻译（gen=1）
    p._gen = 1
    p._label.setText("翻译中…")
    p._token.emit("你好", 1)
    assert p._label.text() == "你好"
    # 第二轮开始（gen=2），label 重置为"翻译中…"
    p._gen = 2
    p._label.setText("翻译中…")
    # 第一轮的迟到 token（gen=1）必须被忽略
    p._token.emit("旧内容", 1)
    assert "旧内容" not in p._label.text()
    assert p._label.text() == "翻译中…"
    # 第二轮的正常 token（gen=2）正常追加
    p._token.emit("新内容", 2)
    assert "新内容" in p._label.text()
    assert "旧内容" not in p._label.text()


def test_stale_finished_does_not_overwrite_tgt(qapp):
    """旧 worker 的迟到 _finished 不得覆盖当前 _tgt（否则复制出来是旧译文）。"""
    p = SelectionPopup()
    p._gen = 2
    p._tgt = "当前译文"
    p._finished.emit("旧译文", 1)   # stale
    assert p._tgt == "当前译文"     # 未被覆盖
    p._finished.emit("真正译文", 2)  # 当前代
    assert p._tgt == "真正译文"


def test_show_source_invalidates_inflight_translate(qapp):
    """show_source（已是默认语言）应作废可能还在跑的翻译 worker。"""
    p = SelectionPopup()
    p._gen = 5
    p.show_source("原文")
    assert p._gen == 6  # 自增 → 旧 worker(gen≤5) 的输出会被丢弃
