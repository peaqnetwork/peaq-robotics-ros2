# Stream v1 Chunk Contract

The ROS2 Stream chunk manifest uses the SDK v1 schema exactly:

- `schemaVersion`: `peaq.stream.chunks.v1`
- `chunkId`: `sha256:` hash of `schemaVersion`, `previousChunkId`, `index`, `plaintextHash`, and `encryptedDataHash` in stable JSON order
- `plaintextHash`: `sha256:` hash of the canonical plaintext chunk payload
- `encryptedDataHash`: `sha256:` hash of the encrypted chunk bytes encoded as hex
- `encryption.keyCommitment`: `sha256:` hash of the per-chunk symmetric key bytes
- `signature.value`: Ed25519 signature over the UTF-8 bytes of the `encryptedDataHash` string

Each encrypted chunk is stored as one physical `.bin` file. The manifest file can be a JSON array, but every array item must be a valid `peaq.stream.chunks.v1` object.

Buyer access uses `peaq.stream.buyer-access.v1`. It only wraps the existing per-chunk key for the buyer public key; it does not re-encrypt the chunk data.

## Seller Startup

Use the bootstrap command after the machine is already active in peaqOS and has an `identityRef`:

```bash
ros2 run peaq_ros2_stream stream_bootstrap \
  --config ~/.peaq_robot/peaq_stream.yaml \
  --api-base-url https://api.example.com \
  --machine-id mach_123 \
  --storage-backend s3
```

The command enrolls a Stream runtime agent, writes the returned `agent_id` and `agent_token` into the config file, and prints the launch command:

```bash
ros2 launch peaq_ros2_stream peaq_stream.launch.py config_yaml:=~/.peaq_robot/peaq_stream.yaml
```

If the config has no `key_recipients`, bootstrap creates a local machine X25519 recipient key at `~/.peaq_robot/stream_machine_x25519_key.json` and adds the machine public key to `encryption.keyRecipients`. Owner and operator recipients can be added during bootstrap with `--owner-recipient-id`, `--owner-public-key-hex`, `--operator-recipient-id`, and `--operator-public-key-hex`.

`peaq_stream.launch.py` starts both `peaqos_node` and `stream_agent_node` with the same config file. Wallet creation, machine registration, DID setup, and EventRegistry submission remain owned by `peaqos_node`.
