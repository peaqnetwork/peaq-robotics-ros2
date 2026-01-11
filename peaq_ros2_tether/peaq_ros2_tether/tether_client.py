from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TetherCliResult:
    ok: bool
    data: Dict[str, Any]
    error: str


class TetherWDKClient:
    """
    Thin Python wrapper around Node.js CLI (subprocess).

    We keep Node.js/Tether WDK logic out of ROS2 runtime and avoid binding
    JS libraries into Python.
    """

    def __init__(
        self,
        *,
        node_bin: str,
        cli_path: str,
        evm_rpc_url: str,
        usdt_contract: str,
        usdt_decimals: int,
        wallet_registry_path: str,
        unsafe_export_mnemonic: bool,
        timeout_sec: float = 45.0,
    ) -> None:
        self._node_bin = node_bin or 'node'
        self._cli_path = cli_path
        self._evm_rpc_url = evm_rpc_url
        self._usdt_contract = usdt_contract
        self._usdt_decimals = usdt_decimals
        self._wallet_registry_path = wallet_registry_path
        self._unsafe_export_mnemonic = unsafe_export_mnemonic
        self._timeout_sec = timeout_sec

    def _run(self, args: list[str], *, stdin_text: Optional[str] = None) -> TetherCliResult:
        env = os.environ.copy()
        env['PEAQ_TETHER_EVM_RPC'] = self._evm_rpc_url
        env['PEAQ_TETHER_USDT_CONTRACT'] = self._usdt_contract
        env['PEAQ_TETHER_USDT_DECIMALS'] = str(self._usdt_decimals)
        env['PEAQ_TETHER_WALLET_REGISTRY'] = self._wallet_registry_path
        env['PEAQ_TETHER_UNSAFE_EXPORT_MNEMONIC'] = 'true' if self._unsafe_export_mnemonic else 'false'

        cmd = [self._node_bin, self._cli_path, *args]
        try:
            proc = subprocess.run(
                cmd,
                input=stdin_text.encode('utf-8') if stdin_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=self._timeout_sec,
                check=False,
            )
        except Exception as e:  # noqa: BLE001
            return TetherCliResult(ok=False, data={}, error=str(e))

        out = (proc.stdout or b'').decode('utf-8', errors='replace').strip()
        err = (proc.stderr or b'').decode('utf-8', errors='replace').strip()

        if proc.returncode != 0:
            # If the CLI emitted JSON on stdout, include it for debugging.
            try:
                js = json.loads(out) if out else {}
            except Exception:
                js = {}
            msg = err or (js.get('error') if isinstance(js, dict) else '') or f'CLI exited {proc.returncode}'
            return TetherCliResult(ok=False, data=js if isinstance(js, dict) else {}, error=msg)

        try:
            js = json.loads(out) if out else {}
        except Exception as e:
            return TetherCliResult(ok=False, data={}, error=f'Invalid JSON from tether CLI: {e}. stdout={out!r}')

        if not isinstance(js, dict):
            return TetherCliResult(ok=False, data={}, error='Invalid JSON payload from tether CLI (expected object)')

        if js.get('ok') is True:
            return TetherCliResult(ok=True, data=js, error='')
        return TetherCliResult(ok=False, data=js, error=str(js.get('error') or 'Unknown tether CLI error'))

    def create_wallet(self, *, label: str, export_mnemonic: bool) -> TetherCliResult:
        return self._run(['wallet', 'create', '--label', label, '--export-mnemonic', 'true' if export_mnemonic else 'false'])

    def get_usdt_balance(self, *, wallet_id: str = '', address: str = '') -> TetherCliResult:
        args = ['usdt', 'balance']
        if wallet_id:
            args += ['--wallet-id', wallet_id]
        if address:
            args += ['--address', address]
        return self._run(args)

    def transfer_usdt(self, *, wallet_id: str, to_address: str, amount: str, dry_run: bool) -> TetherCliResult:
        return self._run([
            'usdt',
            'transfer',
            '--wallet-id',
            wallet_id,
            '--to',
            to_address,
            '--amount',
            amount,
            '--dry-run',
            'true' if dry_run else 'false',
        ])


def resolve_installed_cli_path() -> str:
    """
    Resolve CLI path as installed with the package data_files.

    During development (common for this repo), CLI is located at:
      `<workspace_root>/peaq_ros2_tether/js/peaq_tether_cli.mjs`
    and `npm install` is executed in `<workspace_root>/peaq_ros2_tether/js`.

    IMPORTANT:
    - Node's ESM module resolution will look for `node_modules/` relative to the
      CLI script location. Therefore, when developing/running from a source
      checkout (e.g., Docker mounting `/work`), we prefer the source CLI path so
      that it can find `/work/peaq_ros2_tether/js/node_modules`.
    """
    # Explicit override (for production deployments)
    env_path = os.getenv('PEAQ_TETHER_CLI_PATH', '').strip()
    if env_path:
        return env_path

    # Prefer source checkout path if present (Docker mounts typically use /work).
    candidates = [
        Path('/work/peaq_ros2_tether/js/peaq_tether_cli.mjs'),
        Path.cwd() / 'peaq_ros2_tether' / 'js' / 'peaq_tether_cli.mjs',
    ]
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except Exception:
            pass

    # Avoid importing ament_index_python at runtime unless needed.
    try:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory('peaq_ros2_tether'))
        return str(share / 'js' / 'peaq_tether_cli.mjs')
    except Exception:
        # Fallback: relative to this file (source tree).
        here = Path(__file__).resolve()
        return str(here.parents[2] / 'js' / 'peaq_tether_cli.mjs')

