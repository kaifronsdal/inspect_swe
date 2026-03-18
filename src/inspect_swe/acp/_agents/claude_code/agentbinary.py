"""Build and install the claude-agent-acp ACP adapter in sandboxes.

Downloads Node.js if needed, builds the npm bundle on the host (with
caching), and copies both into each sandbox.
"""

import logging

from inspect_ai.util import SandboxEnvironment, concurrency

from inspect_swe._util.node import (
    create_npm_bundle,
    ensure_node_available,
    install_npm_bundle,
    patch_npm_bundle_file,
    resolve_npm_package_version,
)
from inspect_swe._util.sandbox import (
    SANDBOX_INSTALL_DIR,
    SandboxPlatform,
    bash_command,
    detect_sandbox_platform,
)

logger = logging.getLogger(__name__)

_ACP_ADAPTER_PACKAGE = "@zed-industries/claude-agent-acp"
_CLAUDE_AGENT_SDK_TIMEOUT_ENV_VAR = "CLAUDE_AGENT_SDK_TIMEOUT_MS"
_CLAUDE_AGENT_SDK_BUNDLE_PATH = "node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs"
_CLAUDE_AGENT_SDK_DEFAULT_TIMEOUT_MS = 60000


def _patch_claude_agent_sdk_timeout(bundle_data: bytes) -> bytes:
    original = f"var QM={_CLAUDE_AGENT_SDK_DEFAULT_TIMEOUT_MS};"
    replacement = (
        "var QM=(()=>{"
        f"let value=Number.parseInt(process.env.{_CLAUDE_AGENT_SDK_TIMEOUT_ENV_VAR}??\"\",10);"
        f"return Number.isFinite(value)&&value>0?value:{_CLAUDE_AGENT_SDK_DEFAULT_TIMEOUT_MS}"
        "})();"
    )

    def patch(text: str) -> str:
        if _CLAUDE_AGENT_SDK_TIMEOUT_ENV_VAR in text:
            return text
        if original not in text:
            raise RuntimeError("Unable to locate Claude SDK timeout constant in bundled sdk.mjs")
        return text.replace(original, replacement, 1)

    return patch_npm_bundle_file(
        bundle_data=bundle_data,
        path=_CLAUDE_AGENT_SDK_BUNDLE_PATH,
        transform=patch,
    )


async def ensure_claude_code_acp_setup(
    sandbox: SandboxEnvironment,
    user: str | None = None,
) -> tuple[str, str]:
    """Install node and claude-agent-acp in the sandbox.

    Returns (acp_binary, node_binary) paths.
    """
    platform = await detect_sandbox_platform(sandbox)
    node_binary = await ensure_node_available(sandbox, platform, user)
    acp_binary = await _ensure_acp_installed(sandbox, platform, user)
    return acp_binary, node_binary


async def _ensure_acp_installed(
    sandbox: SandboxEnvironment,
    platform: SandboxPlatform,
    user: str | None = None,
) -> str:
    """Install claude-agent-acp via locally-built npm bundle."""
    install_dir = f"{SANDBOX_INSTALL_DIR}/claude-agent-acp"
    acp_binary = f"{install_dir}/node_modules/.bin/claude-agent-acp"

    result = await sandbox.exec(bash_command(f"test -x {acp_binary}"), user=user)
    if result.success:
        return acp_binary

    async with concurrency("claude-agent-acp-install", 1, visible=False):
        version = resolve_npm_package_version(_ACP_ADAPTER_PACKAGE)
        bundle_data = create_npm_bundle(
            package=_ACP_ADAPTER_PACKAGE,
            version=version,
            platform=platform,
            cache_name="claude-agent-acp-bundles",
        )
        bundle_data = _patch_claude_agent_sdk_timeout(bundle_data)
        return await install_npm_bundle(
            sandbox=sandbox,
            bundle_data=bundle_data,
            install_dir=install_dir,
            binary_name="claude-agent-acp",
            user=user,
        )
