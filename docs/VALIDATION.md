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

## Mainnet c90717de preparation (October 31, 2026)

Mainnet channel source `c90717deac2a00fcec8f126065362c2344e00898` is the
latest inspected `JohnnyB813/core` master commit (version 0.8.20). The AMP
workflow now passes the exact checkout SHA as `WARTHOG_COMMIT`, so this
build's version text identifies that source rather than `unknown`.

[Publication run](https://github.com/JohnnyB813/amp_wart_node/actions/runs/41243204509)
passed all 29 native tests, including transaction hash/history-ID lookup
and mempool API snapshot ownership/sender tests, plus the Go race/vet/format
checks and 11 Python integration/publisher tests. The source repository's
[container run](https://github.com/JohnnyB813/core/actions/runs/41231930742)
also passed Stratum socket, CLI/TOML, offline replay, P2P rejection and
recovery regressions for this commit.

Published binary size is 4,380,768 bytes, SHA-256
`55b3bcd5d805dc441e42abcf0259f067a45be7610a675919cc5216f2019a7f2e`.
Public asset, manifest and checksum downloads were independently verified.
UPX integrity/decompression and unpacked ELF inspection passed; the unpacked
binary has no dynamic interpreter/library dependency and contains the exact
full source commit. Inspection did not execute the node.

Disposable Linux fixtures used the configuration inspected from
`warthog-mainnet01` and the real prior 51d5d1d7 binary. The published pinned
updater-v0.1.0 installer/helper retained the old selection on integration,
then downloaded/selected c90717de. Verification covered update idempotence,
rollback to the old binary and update again, for both symlink and physical
current-directory layouts. Database/WAL/SHM fixture bytes, database flags,
ports, minfee 0.00009992, app settings and startup settings were preserved.
The network remains mainnet-v1 with the original genesis; no reset occurred.

No live mainnet configuration, binary or process state was changed. The
inspected live configuration still has manual verification-only Update hooks;
[the guide](UPGRADE-mainnet-0.8.20-c90717de.md) describes the required one-time
channel connection before using AMP's application Update button. Live AMP
button execution and chain progress remain post-deployment checks.
