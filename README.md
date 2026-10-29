# Warthog node updates for AMP

This repository delivers **separate mainnet and DeFi testnet release channels**
for existing Linux x86-64 AMP instances. After one-time integration, node
updates download, verify and install through the application's **Update**
button. No manual archive transfer or unpacking is needed for later releases.

The first phase deliberately has **no schedules**. Updates do not restart ADS,
other instances, or the host AMP service. Stop the node application, click its
Update button, then start it. The managed AMP panel remains running. The
updater refuses to replace a running node executable.

## How releases reach AMP

1. In **Actions → Publish AMP release → Run workflow**, choose:
   - **mainnet**: builds/tests the selected `JohnnyB813/core` ref (default `master`).
   - **testnet**: verifies the latest official `warthog-network/core` DeFi asset
     against GitHub's published SHA-256 and the successful DeFi build source.
   - **updater**: publishes a new explicitly versioned installer/runtime pair.
2. A successful node publication creates versioned release assets and promotes
   only its own `channels/mainnet.json` or `channels/testnet.json`.
3. The corresponding AMP application's Update button reads that channel,
   downloads the binary, checks SHA-256/size/static ELF format, and selects a
   new `releases/<sha256>/` directory through an atomic `current` symlink.
4. Offline pre-start verification checks the selected build every time it starts.
   The old release remains available for rollback.

Publishing a release **does not deploy it**. Mainnet follows your fork; testnet
follows official DeFi releases. Versions/source commits and hashes are pinned
in every release manifest. Existing flags, minfee, ports and Nginx settings
remain under the existing AMP configuration.

## Connect the existing instances once

See **[docs/SETUP.md](docs/SETUP.md)**. Initial integration needs Linux host
access as the AMP owner, a complete cold backup, and a brief stop of the target
node and its managed AMP instance. ADS and other nodes stay running. The
installer downloads the standalone updater itself; Python is needed only for
that one-time host installation, not inside AMP containers.

The installer recognizes the existing app IDs, paths and manually selected
mainnet builds used on this server. It saves the original configuration and
executable before changing update/pre-start hooks. Mainnet retains
`--minfee=0.00009992` and its existing databases. Testnet retains its own flags
except when an explicitly accepted network reset selects a fresh session.

## Testnet resets require explicit migration

The current approved testnet epoch is **testnet-2026-10-24**. A pre-reset
0.10.32/0.10.33 instance requires the setup guide's explicit reset option after
its backup. The old session is kept intact; balances, assets, orders and
pending transactions do not migrate to the new chain.

Future genesis changes are blocked twice: the publisher requires a reviewed
`channels/policy.json` change, and each installed updater refuses a channel
whose network/epoch/genesis hash differs from its local binding. A normal
Update button click never deletes a database or accepts a testnet reset.

## Inspect or roll back

Run inside the instance application directory as its owner:

```sh
./amp-wart-update check --root "$PWD" --network mainnet
./amp-wart-update verify --root "$PWD" --network mainnet
./amp-wart-update rollback --root "$PWD" --network mainnet
```

Use `--network testnet` for the testnet application. Stop the node before a
rollback. Rollback selects the previous binary in the same network epoch; it
does not restore database state. Retain complete cold backups for recovery.

## Development

Go 1.27.3 and Python 3 are used for preparation and CI. There are no third-party
Go module dependencies.

```sh
go test -race ./...
go vet ./...
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -buildvcs=false -ldflags='-s -w' -o dist/amp-wart-update-linux-amd64 ./cmd/amp-wart-update
python3 -B -m unittest discover -s tests -v
```

Tests exercise downloads, checksums, network/reset refusal, process guards,
locking, rollback, interrupted downloads and byte-preservation fixtures.
They do not start a Warthog node or prove live AMP deployment/synchronization.
See [docs/VALIDATION.md](docs/VALIDATION.md) for the verified scope.