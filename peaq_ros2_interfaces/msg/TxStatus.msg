# Transaction status message
# Provides real-time updates on blockchain transaction progress

# Phase of the transaction
# PENDING: Transaction submitted but not yet in block
# IN_BLOCK: Transaction included in a block
# FINALIZED: Transaction finalized
# FAILED: Transaction failed
# DROPPED: Transaction was dropped
string phase

# Transaction hash (optional, may be empty for some phases)
string tx_hash

# Block number where transaction was included (0 if not in block yet)
uint64 block

# Error message if transaction failed (empty if successful)
string error
