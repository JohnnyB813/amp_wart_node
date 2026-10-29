# Verification scope

The standalone updater uses Go's standard library and has no external module
dependencies. It is built for Linux amd64 with CGO disabled. Python is used
only for the one-time host integration and GitHub publishing workflows.

Offline Go tests cover release selection, retained binaries/data/configuration,
idempotent updates and rollback, read-only checks, offline startup validation,
network/genesis/epoch rejection, downgrade sequence refusal, unsafe URLs,
checksum/size/format/download failures, process detection, locks and symlinks.
Synthetic ELF payloads are never executed as node processes.

Python tests cover one-time integration against a compiled updater, byte
preservation of BOM/CRLF configuration and database/WAL fixtures, quoted AMP
stage arguments, explicit pre-reset testnet migration, refusal of wrong
applications/mainnet epochs, and recovery after bootstrap verification fails.
Publisher tests reject dynamic ELF interpreters, immutable asset collisions
and unreviewed genesis changes.

Preparation tests run without external networking. The updater executable
itself runs during verification tests; no Warthog node binary is started.
Database fixture files establish byte preservation, not real-chain state or
production schema compatibility.

Mainnet builds use the source repository's Docker build/test target. Testnet
publication verifies the official published asset's SHA-256 and size and ties
its version/genesis to the successful DeFi build commit rather than the release
tag, which historically points at the mainnet branch.

Live AMP button execution, node restart, full synchronization, mining and
transaction behavior still require verification after the one-time server
integration. No schedules should be enabled until those checks are complete.
Source-built testnet publications also verify the exact upstream commit's
version and genesis against policy. The source checkout is compiled without
consensus changes using the static testnet Docker builder, and its native
Meson tests must pass before publishing. This does not start a Warthog node
or establish real-chain/DEX synchronization. The October 24-to-October 30
migration is tested separately to retain the complete old session.
