"""
Tests of the 'Start' step
"""
import os
from pathlib import Path

import pytest
from cwas.start import Start


@pytest.fixture(scope="module")
def args(cwas_workspace: Path) -> list:
    return ["-w", str(cwas_workspace)]


@pytest.fixture(scope="module", autouse=True)
def run_start(args: list):
    inst = Start.get_instance(args)
    inst.run()
    yield
    cwas_env_path = Path.home() / ".cwas_env"
    cwas_env_path.unlink()
    os.unsetenv("CWAS_WORKSPACE")


def test_initial_file_exist(cwas_workspace: Path):
    cwas_env_path = Path.home() / ".cwas_env"
    cwas_config_path = cwas_workspace / "configuration.txt"
    assert cwas_env_path.is_file()
    assert cwas_workspace.is_dir()
    assert cwas_config_path.is_file()


def test_os_environ(cwas_workspace: Path):
    assert os.getenv("CWAS_WORKSPACE") == str(cwas_workspace)


def test_config_keys(cwas_workspace: Path):
    config_key_set = set()
    cwas_config_path = cwas_workspace / "configuration.txt"
    with cwas_config_path.open() as config_file:
        for line in config_file:
            config_key, _ = line.strip().split("=")
            config_key_set.add(config_key)

    expected_key_set = {
        "ANNOTATION_DATA_DIR",
        "GENE_MATRIX",
        "ANNOTATION_KEY_CONFIG",
        "BIGWIG_CUTOFF_CONFIG",
        "VEP",
    }
    assert config_key_set == expected_key_set


def test_run_without_args():
    inst = Start.get_instance()
    inst.run()

    expect_default_workspace = Path.home() / ".cwas"
    actual_workspace = getattr(inst, "workspace")

    assert expect_default_workspace == actual_workspace
    assert expect_default_workspace.is_dir()

    # Teardown
    for f in expect_default_workspace.glob("*"):
        f.unlink()
    expect_default_workspace.rmdir()
