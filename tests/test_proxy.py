from llm_translator.utils.proxy import decide_force_direct


def test_no_proxy_means_no_force():
    # 没配代理 → 不强制直连（走默认）
    assert decide_force_direct(None, lambda h, p: False) is False


def test_reachable_proxy_means_no_force():
    # 代理在监听 → 尊重系统代理，不强制直连
    assert decide_force_direct(("127.0.0.1", 7890), lambda h, p: True) is False


def test_dead_proxy_forces_direct():
    # 配了代理但连不上 → 强制直连（BUG4 的核心场景）
    assert decide_force_direct(("127.0.0.1", 7890), lambda h, p: False) is True


def test_reachable_check_raising_forces_direct():
    # 探测抛异常（如被防火墙静默丢包）→ 视为不可达，强制直连
    def boom(h, p):
        raise OSError("blocked")
    assert decide_force_direct(("127.0.0.1", 7890), boom) is True
