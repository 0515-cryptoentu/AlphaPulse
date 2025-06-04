import types
import sys
import importlib
import os
from unittest.mock import patch
import pytest


def _patch_hvac(monkeypatch, data):
    class DummyClient:
        def __init__(self, url=None, token=None):
            pass

        def is_authenticated(self):
            return True

        class secrets:
            class kv:
                class v2:
                    @staticmethod
                    def read_secret_version(path):
                        return {"data": {"data": data}}

    dummy = types.SimpleNamespace(Client=DummyClient)
    monkeypatch.setitem(sys.modules, "hvac", dummy)


def test_load_from_vault_success(monkeypatch):
    env = {"VAULT_ADDR": "a", "VAULT_TOKEN": "t", "VAULT_SECRET_PATH": "p"}
    _patch_hvac(monkeypatch, {
        "USER_WALLET_PRIVATE_KEY": "key",
        "RPC_URL": "url"
    })
    base_env = {"RPC_URL": "http://localhost", "USER_WALLET_PRIVATE_KEY": "dummy"}
    base_env.update(env)
    with patch.dict(os.environ, base_env, clear=True):
        import config
        importlib.reload(config)
        result = config._load_from_vault(env.copy())
    assert result["USER_WALLET_PRIVATE_KEY"] == "key"
    assert result["RPC_URL"] == "url"


def test_load_from_vault_missing(monkeypatch):
    env = {"VAULT_ADDR": "a", "VAULT_TOKEN": "t", "VAULT_SECRET_PATH": "p"}
    _patch_hvac(monkeypatch, {})
    base_env = {"RPC_URL": "http://localhost", "USER_WALLET_PRIVATE_KEY": "dummy"}
    base_env.update(env)
    with patch.dict(os.environ, base_env, clear=True):
        import config
        importlib.reload(config)
        with pytest.raises(EnvironmentError):
            config._load_from_vault(env.copy())

