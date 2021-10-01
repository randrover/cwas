"""
Test cwas.env
"""
from __future__ import annotations

from typing import OrderedDict

import pytest
from pathlib import Path
from cwas.env import Env


@pytest.fixture(scope="module")
def env_path(cwas_workspace):
    return cwas_workspace / ".env"


@pytest.fixture(scope="module")
def env_inst(env_path):
    env = Env(env_path)
    return env


def test_env_init(env_inst):
    assert isinstance(env_inst.env, OrderedDict)


def test_env_singleton(env_path):
    # Test if the two instances are the same.
    env1 = Env(env_path)
    env2 = Env(env_path)

    assert env1 is env2

    env3 = Env(Path(str(env_path) + "_new"))
    env4 = Env()

    assert env1 is env3
    assert env1 is env4
    assert str(env1.path).endswith("_new")


def test_env_setting(env_inst):
    env_key = "TEST"
    expected = "Hello!"
    env_inst.set_env(env_key, expected)
    env_value = env_inst.get_env(env_key)
    assert env_value == expected


def test_env_get_nonexist(env_inst):
    env_value = env_inst.get_env("FAKE")
    assert env_value is None


def test_env_prev_set_exists(env_inst):
    # Test if the environment variable exists.
    env_key = "TEST"
    expected = "Hello!"
    env_value = env_inst.get_env(env_key)
    assert env_value == expected


def test_env_reset(env_inst):
    env_inst.reset()
    env_key = "TEST"
    env_value = env_inst.get_env(env_key)
    assert env_value is None


def test_env_save(env_inst):
    env_key = "TEST"
    expected = "Hello!"
    env_inst.set_env(env_key, expected)
    env_inst.save()
    with env_inst.path.open() as env_file:
        env_line = env_file.read()
        env_line = env_line.strip()
    assert env_line == "TEST=Hello!"