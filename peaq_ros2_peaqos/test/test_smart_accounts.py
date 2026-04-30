from __future__ import annotations

from types import SimpleNamespace

from peaq_ros2_peaqos.adapter import PeaqosAdapter


class _SmartAccountClient:
    def get_smart_account_address(self, *, owner: str, machine: str, salt: int) -> str:
        assert owner == '0x1111111111111111111111111111111111111111'
        assert machine == '0x2222222222222222222222222222222222222222'
        assert salt == 0
        return '0x3333333333333333333333333333333333333333'

    def deploy_smart_account(self, *, owner: str, machine: str, salt: int) -> str:
        assert owner == '0x1111111111111111111111111111111111111111'
        assert machine == '0x2222222222222222222222222222222222222222'
        assert salt == 0
        return '0x3333333333333333333333333333333333333333'


def _adapter() -> PeaqosAdapter:
    adapter = PeaqosAdapter.__new__(PeaqosAdapter)
    adapter.config = SimpleNamespace(default_machine_address='')
    adapter._resolve_default_proxy_signer = lambda value: value
    adapter._client_for_address = lambda signer: _SmartAccountClient()
    adapter._normalize_external_address = lambda value, field: value
    return adapter


def test_get_smart_account_address_allows_empty_legacy_daily_limit():
    address = _adapter().get_smart_account_address(
        signer_address='0x1111111111111111111111111111111111111111',
        owner='0x1111111111111111111111111111111111111111',
        machine='0x2222222222222222222222222222222222222222',
        daily_limit='',
        salt='0',
    )

    assert address == '0x3333333333333333333333333333333333333333'

def test_deploy_smart_account_allows_empty_legacy_daily_limit():
    address = _adapter().deploy_smart_account(
        signer_address='0x1111111111111111111111111111111111111111',
        owner='0x1111111111111111111111111111111111111111',
        machine='0x2222222222222222222222222222222222222222',
        daily_limit='',
        salt='0',
    )

    assert address == '0x3333333333333333333333333333333333333333'
