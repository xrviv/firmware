from public_constants import *

# LEGACY ADDRESS 1....
assert AF_CLASSIC & AFC_PUBKEY
assert AF_CLASSIC & AFC_SEGWIT == 0
assert AF_CLASSIC & AFC_BECH32 == 0
assert AF_CLASSIC & AFC_SCRIPT == 0
assert AF_CLASSIC & AFC_WRAPPED == 0
assert AF_CLASSIC & AFC_BECH32M == 0

# SCRIPT HASH
assert AF_P2SH & AFC_PUBKEY == 0
assert AF_P2SH & AFC_SEGWIT == 0
assert AF_P2SH & AFC_BECH32 == 0
assert AF_P2SH & AFC_SCRIPT
assert AF_P2SH & AFC_WRAPPED == 0
assert AF_P2SH & AFC_BECH32M == 0

# WITNESS KEY HASH
assert AF_P2WPKH & AFC_PUBKEY
assert AF_P2WPKH & AFC_SEGWIT
assert AF_P2WPKH & AFC_BECH32
assert AF_P2WPKH & AFC_SCRIPT == 0
assert AF_P2WPKH & AFC_WRAPPED == 0
assert AF_P2WPKH & AFC_BECH32M == 0

# WITNESS SCRIPT HASH
assert AF_P2WSH & AFC_PUBKEY == 0
assert AF_P2WSH & AFC_SEGWIT
assert AF_P2WSH & AFC_BECH32
assert AF_P2WSH & AFC_SCRIPT
assert AF_P2WSH & AFC_WRAPPED == 0
assert AF_P2WSH & AFC_BECH32M == 0

# WRAPPED WITNESS KEY HASH
assert AF_P2WPKH_P2SH & AFC_PUBKEY
assert AF_P2WPKH_P2SH & AFC_SEGWIT
assert AF_P2WPKH_P2SH & AFC_BECH32 == 0
assert AF_P2WPKH_P2SH & AFC_SCRIPT == 0
assert AF_P2WPKH_P2SH & AFC_WRAPPED
assert AF_P2WPKH_P2SH & AFC_BECH32M == 0

# WRAPPED WITNESS SCRIPT HASH
assert AF_P2WSH_P2SH & AFC_PUBKEY == 0
assert AF_P2WSH_P2SH & AFC_SEGWIT
assert AF_P2WSH_P2SH & AFC_BECH32 == 0
assert AF_P2WSH_P2SH & AFC_SCRIPT
assert AF_P2WSH_P2SH & AFC_WRAPPED
assert AF_P2WSH_P2SH & AFC_BECH32M == 0

# TAPROOT
assert AF_P2TR & AFC_PUBKEY
assert AF_P2TR & AFC_SEGWIT
assert AF_P2TR & AFC_BECH32 == 0
assert AF_P2TR & AFC_SCRIPT == 0
assert AF_P2TR & AFC_WRAPPED == 0
assert AF_P2TR & AFC_BECH32M