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
## Official 0.10.38 preparation (October 30, 2026)

The successful upstream job 124349245888 in run 41139261907 tested and
published source `dff967eacad0efe4140bcf76beff32b5d5f27290`. The official Linux
asset is 7,351,192 bytes, SHA-256
`a8ad1e26cb5b16546fefdfa313ee765b038d9dd828bf049b39ecb335b3f0ce20`.
The publisher verified the static ELF, version and October 30 genesis directly
against that source. No node source was modified or rebuilt.

Go race tests and vet passed; 11 Python integration/publisher tests passed.
Additional disposable Linux fixtures used the exact real 0.10.32/0.10.36 and
0.10.38 binaries and the published updater-v0.1.0 installer/helper. Migration
was verified from legacy 0.10.32, legacy 0.10.36 (the server's configuration
shape), and already integrated 0.10.36. Checks confirmed explicit reset
acceptance, offline selected-binary verification, unchanged database/WAL/SHM
and trade-history fixture bytes, retained launch flags/ports/settings, and
cross-epoch rollback refusal. No Warthog binary was executed.

The AMP testnet configuration was inspected read-only: 0.10.36 download/hash
hooks, October 24 session, minfee 0.00000001 and trade-history flag enabled.
The instance displayed idle. No live configuration, executable, session or
process state was changed. Production synchronization and transactions remain
post-deployment checks in [the upgrade guide](UPGRADE-0.10.38.md).
