def pytest_configure(config):
    config.addinivalue_line("markers", "slow: needs the frozen Kite frames, takes minutes")
