# Stream v1 Chunk Contract

The ROS2 Stream chunk manifest uses the SDK v1 schema exactly:

- `schemaVersion`: `peaq.stream.chunks.v1`
- `chunkId`: `sha256:` hash of `schemaVersion`, `previousChunkId`, `index`, `plaintextHash`, and `encryptedDataHash` in stable JSON order
- `plaintextHash`: `sha256:` hash of the canonical plaintext chunk payload
- `encryptedDataHash`: `sha256:` hash of the encrypted chunk bytes encoded as hex
- `encryption.keyCommitment`: `sha256:` hash of the per-chunk symmetric key encoded as hex
- `signature.value`: Ed25519 signature over the UTF-8 bytes of the `encryptedDataHash` string

Each encrypted chunk is stored as one physical `.bin` file. The manifest file can be a JSON array, but every array item must be a valid `peaq.stream.chunks.v1` object.

Buyer access uses `peaq.stream.buyer-access.v1`. It only wraps the existing per-chunk key for the buyer public key; it does not re-encrypt the chunk data.
