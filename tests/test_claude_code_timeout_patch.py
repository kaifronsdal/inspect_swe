import tarfile
from io import BytesIO

from inspect_swe.acp._agents.claude_code.agentbinary import (
    _CLAUDE_AGENT_SDK_BUNDLE_PATH,
    _CLAUDE_AGENT_SDK_TIMEOUT_ENV_VAR,
    _patch_claude_agent_sdk_timeout,
)


def _bundle_with_sdk_text(text: str) -> bytes:
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        data = text.encode("utf-8")
        info = tarfile.TarInfo(_CLAUDE_AGENT_SDK_BUNDLE_PATH)
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    return buffer.getvalue()


def _read_sdk_text(bundle_data: bytes) -> str:
    with tarfile.open(fileobj=BytesIO(bundle_data), mode="r:gz") as tar:
        extracted = tar.extractfile(_CLAUDE_AGENT_SDK_BUNDLE_PATH)
        assert extracted is not None
        return extracted.read().decode("utf-8")


def test_patch_claude_agent_sdk_timeout_adds_env_override() -> None:
    bundle = _bundle_with_sdk_text("before;var QM=60000;after;")

    patched = _patch_claude_agent_sdk_timeout(bundle)
    patched_text = _read_sdk_text(patched)

    assert f"process.env.{_CLAUDE_AGENT_SDK_TIMEOUT_ENV_VAR}" in patched_text
    assert "var QM=60000;" not in patched_text


def test_patch_claude_agent_sdk_timeout_is_idempotent() -> None:
    bundle = _bundle_with_sdk_text(
        f"before;var QM=(()=>process.env.{_CLAUDE_AGENT_SDK_TIMEOUT_ENV_VAR})();after;"
    )

    patched = _patch_claude_agent_sdk_timeout(bundle)

    assert _read_sdk_text(patched) == _read_sdk_text(bundle)
