"""Executor settings: nvidia-smi is found under WSL even when a service's PATH lacks it."""

from pathlib import Path

import pytest

from agentic_executor import settings as settings_module
from agentic_executor.settings import ExecutorSettings


@pytest.fixture(autouse=True)
def _no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARP_NVIDIA_SMI", raising=False)


def test_nvidia_smi_on_the_path_is_used_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert ExecutorSettings().nvidia_smi == "nvidia-smi"


def test_without_it_on_the_path_the_wsl_one_is_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wsl = tmp_path / "nvidia-smi"
    wsl.write_text("")
    monkeypatch.setattr(settings_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(settings_module, "WSL_NVIDIA_SMI", str(wsl))
    assert ExecutorSettings().nvidia_smi == str(wsl)


def test_a_path_that_was_set_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.shutil, "which", lambda name: None)
    assert ExecutorSettings(nvidia_smi="/opt/bin/nvidia-smi").nvidia_smi == ("/opt/bin/nvidia-smi")
