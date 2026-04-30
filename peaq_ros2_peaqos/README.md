# peaqOS ROS 2

peaqOS ROS 2 turns a robot into an on-chain machine actor.

This package maps the peaqOS Python and JavaScript SDK capability surface into ROS 2 services, while keeping signing keys local to the robot. It gives robot software a clean ROS-native way to create and fund EVM machine wallets, register machines, mint Machine NFTs, write DID attributes, submit machine events, query MCR, deploy machine smart accounts, and bridge Machine NFTs between peaq and Base.

The result is a production-oriented machine runtime: ROS 2 remains the robot control plane, peaqOS becomes the machine economy and identity plane, and private keys never travel over ROS messages.

## What This Unlocks

- **Machine onboarding**: Create local EVM wallets, register machines, and fund wallets through the peaqOS faucet flow.
- **Machine identity**: Mint Machine NFTs and write the standard DID attributes that let the MCR API understand the robot.
- **Machine telemetry**: Validate single events locally, submit events on-chain, or batch-submit them atomically through the peaq batch precompile.
- **Machine reputation**: Query MCR, machine profiles, and operator fleets from the hosted MCR API.
- **Machine accounts**: Preview and deploy deterministic ERC-4337 smart accounts through the configured `MachineAccountFactory`.
- **Cross-chain machine assets**: Bridge Machine NFTs between peaq and Base through LayerZero v2.
- **ROS-native integration**: Every capability is available as a ROS 2 service with typed request/response contracts.

## Production Design

```text
Robot process
  |
  | ROS 2 service call
  v
peaqos_node
  |
  | local wallet lookup by EVM address
  | no private keys in service requests
  v
peaq-os-sdk (PyPI)
  |
  | peaq EVM RPC, MCR API, faucet API, Base RPC
  v
peaqOS contracts and services
```

Security invariants:

- Wallet private keys are stored in one local registry file on the robot.
- Service callers pass EVM addresses, not private keys.
- The node never accepts or returns private keys over ROS.
- Wallet list/get/delete expose only public peaq EVM metadata (`address`, `account_id`, `chain_id`, `network`); SDK import/export/from-wallet flows are intentionally left to local admin tooling because they require private keys, mnemonics, or vault passphrases.
- Faucet 2FA codes are request-only values and should not be logged by callers.
- Production config belongs in a local `peaq_robot.yaml` or environment variables, not in committed files.
- Production installs use the public PyPI package `peaq-os-sdk>=0.0.2`; do not pin release docs to private GitHub SDK refs that clean robot hosts cannot access.

## Quick Start

Build the workspace:

```bash
source /opt/ros/jazzy/setup.bash
# Use /opt/ros/humble/setup.bash inside the Docker image.
colcon build --packages-select \
  peaq_ros2_interfaces \
  peaq_ros2_peaqos \
  peaq_ros2_examples
source install/setup.bash
```

Create a local config from the example:

```bash
cp peaq_ros2_examples/config/peaq_robot.example.yaml \
   peaq_ros2_examples/config/peaq_robot.yaml
```

Enable peaqOS in `peaq_robot.yaml`:

```yaml
peaq_os:
  enabled: true
  rpc_url: "https://quicknode1.peaq.xyz"
  api_url: "https://mcr.peaq.xyz"

  faucet:
    base_url: "https://depinstation.peaq.network"

  wallet_registry:
    path: "~/.peaq_robot/peaqos_wallets.json"
```

Start the node:

```bash
ros2 run peaq_ros2_peaqos peaqos_node --ros-args \
  -p config.yaml_path:=peaq_ros2_examples/config/peaq_robot.yaml
```

Create a machine wallet:

```bash
ros2 service call /peaqos_node/wallet/create \
  peaq_ros2_interfaces/srv/PeaqosCreateWallet \
  "{label: 'robot-001'}"
```

Register the machine:

```bash
ros2 service call /peaqos_node/machine/register \
  peaq_ros2_interfaces/srv/PeaqosRegisterMachine \
  "{address: '<MACHINE_EVM_ADDRESS>'}"
```

Mint the Machine NFT:

```bash
ros2 service call /peaqos_node/nft/mint \
  peaq_ros2_interfaces/srv/PeaqosMintNft \
  "{signer_address: '<OWNER_OR_PROXY_ADDRESS>', machine_id: 1, recipient: '<RECIPIENT_EVM_ADDRESS>'}"
```

Write the standard machine DID attributes:

```bash
ros2 service call /peaqos_node/did/write_machine_attributes \
  peaq_ros2_interfaces/srv/PeaqosWriteMachineDidAttributes \
  "{signer_address: '<MACHINE_EVM_ADDRESS>', machine_id: 1, nft_token_id: 1, operator_did: 'did:peaq:<OPERATOR_EVM_ADDRESS>', documentation_url: 'https://docs.example/robot-001', data_api: 'https://api.example/robot-001', data_visibility: 'onchain'}"
```

Submit a machine event:

```bash
ros2 service call /peaqos_node/events/submit \
  peaq_ros2_interfaces/srv/PeaqosSubmitEvent \
  "{signer_address: '<MACHINE_EVM_ADDRESS>', machine_id: 1, event_type: 1, value: 1, timestamp: 1770000000, raw_data_hex: '0x', trust_level: 1, source_chain_id: 3338, source_tx_hash: '', metadata_hex: '0x7b7d'}"
```

Query MCR:

```bash
ros2 service call /peaqos_node/mcr/query \
  peaq_ros2_interfaces/srv/PeaqosQueryMcr \
  "{did: 'did:peaq:<MACHINE_EVM_ADDRESS>'}"
```

MCR responses are returned as SDK JSON passthrough. Operator fleet results may
include per-machine `negative_flag` and top-level `pagination`.

## Service Map

| Area | Service | Purpose |
| --- | --- | --- |
| Wallet | `/peaqos_node/wallet/create` | Create a locally stored EVM wallet |
| Wallet | `/peaqos_node/wallet/list` | List locally stored wallet public metadata |
| Wallet | `/peaqos_node/wallet/get` | Get one wallet's public metadata |
| Wallet | `/peaqos_node/wallet/delete` | Delete one locally stored wallet |
| Faucet | `/peaqos_node/faucet/setup_2fa` | Start faucet 2FA enrollment |
| Faucet | `/peaqos_node/faucet/confirm_2fa` | Confirm faucet 2FA |
| Faucet | `/peaqos_node/wallet/fund` | Request gas-station funding |
| Registration | `/peaqos_node/machine/register` | Register the local machine wallet |
| Registration | `/peaqos_node/machine/register_for` | Register a machine through a proxy/operator |
| NFT | `/peaqos_node/nft/mint` | Mint a Machine NFT |
| NFT | `/peaqos_node/nft/token_id_of` | Read a registered machine's NFT token ID |
| DID | `/peaqos_node/did/read_attribute` | Read one DID precompile attribute |
| DID | `/peaqos_node/did/write_machine_attributes` | Write the standard machine DID attributes |
| DID | `/peaqos_node/did/write_proxy_attributes` | Write proxy/operator DID attributes |
| Events | `/peaqos_node/events/validate` | Validate event payload and compute data hash |
| Events | `/peaqos_node/events/submit` | Submit one event through EventRegistry |
| Events | `/peaqos_node/events/batch_submit` | Batch-submit events through the batch precompile |
| MCR | `/peaqos_node/mcr/query` | Query Machine Credit Rating |
| MCR | `/peaqos_node/mcr/machine` | Query machine profile |
| MCR | `/peaqos_node/mcr/operator_machines` | Query an operator's fleet |
| Smart account | `/peaqos_node/smart_account/address` | Predict deterministic machine smart-account address |
| Smart account | `/peaqos_node/smart_account/deploy` | Deploy the machine smart account |
| Bridge | `/peaqos_node/bridge/nft` | Bridge Machine NFT between peaq and Base |
| Bridge | `/peaqos_node/bridge/wait_arrival` | Poll destination chain until bridged NFT arrives |

## Contract Addresses

The example config ships the current peaq mainnet proxy defaults from the peaqOS contract docs.

| Contract | Address |
| --- | --- |
| IdentityRegistry | `0xb53Af985765031936311273599389b5B68aC9956` |
| IdentityStaking | `0x11c05A650704136786253e8685f56879A202b1C7` |
| EventRegistry | `0x43c6c12eecAf4fB3F164375A9c44f8a6Efc139b9` |
| MachineNFT | `0x2943F80e9DdB11B9Dd275499C661Df78F5F691F9` |
| DID precompile | `0x0000000000000000000000000000000000000800` |
| Batch precompile | `0x0000000000000000000000000000000000000805` |
| MachineAccountFactory | `0x4A808d5A90A2c91739E92C70aF19924e0B3D527f` |
| MachineNFTAdapter | `0x9AD5408702EC204441A88589B99ADfC2514AFAE6` |
| Base MachineNFT | `0xee8A521eA434b11F956E2402beC5eBfa753Babfa` |

Environment variable overrides are supported for deployments that pin addresses externally:

```bash
export EVENT_REGISTRY_ADDRESS=0x...
export MACHINE_ACCOUNT_FACTORY_ADDRESS=0x...
export MACHINE_NFT_ADAPTER_ADDRESS=0x...
export BATCH_PRECOMPILE_ADDRESS=0x...
```

## Bridge Flow

peaq to Base:

```bash
ros2 service call /peaqos_node/bridge/nft \
  peaq_ros2_interfaces/srv/PeaqosBridgeNft \
  "{signer_address: '<OWNER_ADDRESS>', token_id: 1, source: 'peaq', destination: 'base', recipient: '<RECIPIENT_ADDRESS>', base_rpc_url: '', base_nft_address: '', options_hex: ''}"
```

Wait for Base arrival:

```bash
ros2 service call /peaqos_node/bridge/wait_arrival \
  peaq_ros2_interfaces/srv/PeaqosWaitForBridgeArrival \
  "{dst_rpc_url: 'https://mainnet.base.org', dst_nft_address: '0xee8A521eA434b11F956E2402beC5eBfa753Babfa', token_id: 1, timeout: 900}"
```

Base to peaq requires the same EVM wallet to have enough Base ETH for gas.

## Tested Mainnet Release Path

This release path has been tested on a ROS 2 Jazzy Ubuntu server against peaq mainnet:

- Machine NFT token lookup
- Wallet create, list, get, and delete public-metadata lifecycle
- DID `readAttribute`
- MCR query, machine query, and operator machines query
- Event validation
- Single event submission
- Batch event submission through the batch precompile
- Deterministic smart-account address calculation
- Smart-account deployment through `MachineAccountFactory`
- peaq to Base Machine NFT bridge through `MachineNFTAdapter`
- Base arrival polling for the bridged Machine NFT

Known operational requirement:

- Reverse Base to peaq bridge requires Base ETH on the signer wallet.

## Production Checklist

- Use a local `peaq_robot.yaml`; do not commit machine private keys or faucet codes.
- Keep `peaq_os.wallet_registry.path` on encrypted robot storage when possible.
- Keep the registry file permission at `0600`.
- Use a reliable peaq EVM RPC endpoint and monitor rate limits.
- Record pre and post balances for any production bridge or event-spend test.
- Fund Base ETH before attempting Base to peaq bridge.
- Keep peaqOS contract addresses pinned to the current contract docs unless deployment docs change.
