# Mainnet AMP update: 0.8.20, source c90717de

This package builds `JohnnyB813/core` master commit
`c90717deac2a00fcec8f126065362c2344e00898` for Linux x86-64 AMP instances.
The upstream project version remains **0.8.20**; identify this build by its
source commit and binary checksum rather than the version number alone.

[Source changes](https://github.com/JohnnyB813/core/compare/51d5d1d789dd03c876967f6a51676f940ae6690a...c90717deac2a00fcec8f126065362c2344e00898)
fix transaction hash-collision lookup, mempool API lifetime/sender handling,
and add confirmed transaction lookup by history ID. The build embeds the
full checkout revision for accurate `/tools/version` reporting.

There is no mainnet genesis change or database schema change from the
previously released `51d5d1d7` build. Keep the existing database session.

## Published package

[Download the AMP release](https://github.com/JohnnyB813/amp_wart_node/releases/tag/mainnet-0.8.20-c90717deac2a-55b3bcd5d805).
The release contains the UPX-packed static Linux x86-64 executable, its
pinned manifest, and `SHA256SUMS`.

- Binary SHA-256: `55b3bcd5d805dc441e42abcf0259f067a45be7610a675919cc5216f2019a7f2e`
- Binary size: 4,380,768 bytes
- Source: `c90717deac2a00fcec8f126065362c2344e00898`
- [Build and test run](https://github.com/JohnnyB813/amp_wart_node/actions/runs/41243204509)

All 29 native tests and the AMP updater/installer checks passed. Disposable
Linux fixtures using the inspected launch configuration and exact published
old/new binaries verified public download, update, offline verification,
repeat-update idempotence, and rollback for both symlink and physical
`current` directory layouts. Database/sidecar fixture bytes, flags, ports,
minfee and startup settings were preserved. Static inspection confirmed the
embedded full commit. These checks did not execute a Warthog node binary.
Live synchronization and API behavior remain post-deployment checks.

## Inspected AMP configuration

Read-only inspection on October 31, 2026 found `warthog-mainnet01` running
with:

- Selected source: `51d5d1d789dd03c876967f6a51676f940ae6690a`
- Selected binary SHA-256: `55ca417110629fafd180f6a2d71ca16eb67a76df805e50c9d332da20bbba9fc1`
- Executable: `current/wart-node`
- Databases: `--chain-db="./data/chain.db3" --peers-db="./data/peers.db3"`
- Minfee: `--minfee=0.00009992`
- Assigned ports: 9186 / 3000 / 3001 / 3456
- Private RPC, public API backend and Stratum bindings on loopback.

Its current Update stage only verifies the selected binary; it does not
download a new build. Connect it once to the public mainnet channel using
the following steps. The installer keeps all existing launch flags, ports,
API bindings and startup settings. It does not alter Nginx or reset data.

## Connect the mainnet Update button once

Run on the Linux host as the AMP owner (`amp`). Use `sudo -iu amp` from an
administrator login if needed. Stop the mainnet node application cleanly
in its own management panel, then stop only its managed AMP instance:

```sh
ampinstmgr stop warthog-mainnet01
umask 077
mkdir -p /home/amp/amp-channel-backups
df -h /home/amp
tar -czf "/home/amp/amp-channel-backups/warthog-mainnet01-before-c90717de-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C /home/amp/.ampdata/instances warthog-mainnet01
```

Continue only after the full cold backup succeeds. Download the pinned
installer and verify it:

```sh
cd /home/amp
curl -fL --output install-amp-updates.py https://github.com/JohnnyB813/amp_wart_node/releases/download/updater-v0.1.0/install-amp-updates.py
printf '%s  %s\n' a04992f8e72767b5b82b16a628cf9a5ca5a3612dbe461c7889cc0ab50aeef493 install-amp-updates.py | sha256sum -c -
python3 install-amp-updates.py --network mainnet --instance /home/amp/.ampdata/instances/warthog-mainnet01 --check
```

The preview must report network `mainnet`, epoch `mainnet-v1`,
`testnet_reset: false` and the retained current binary hash `55ca4171...`.
Integration deliberately preserves that current selection; the AMP Update
button selects the promoted build afterward.

```sh
python3 install-amp-updates.py --network mainnet --instance /home/amp/.ampdata/instances/warthog-mainnet01
ampinstmgr start warthog-mainnet01
```

Open **Manage** for `warthog-mainnet`. Its startup setting may automatically
start the retained old node, so stop that application cleanly if it is
running. Then use the application's **Update** button, wait for success,
and press **Start**. Leave the managed AMP panel running during normal
application updates. ADS and other instances stay running throughout.

The ADS tile's Update/Update All buttons update AMP/module configuration;
they are not the node application updater described here. No restart schedule,
timer or cron task is added.

## Confirm the new selection

Run as `amp` from the application directory:

```sh
cd /home/amp/.ampdata/instances/warthog-mainnet01/warthog-mainnet
./amp-wart-update verify --root "$PWD" --network mainnet
./amp-wart-update check --root "$PWD" --network mainnet
curl -fsS http://127.0.0.1:3000/tools/version
curl -fsS http://127.0.0.1:3000/chain/head
curl -fsS http://127.0.0.1:3000/transaction/minfee
```

Expect selected source `c90717deac2a00fcec8f126065362c2344e00898`, the matching
published SHA-256, version 0.8.20 with that commit in the version response,
and the retained minfee. Confirm synchronization and advancing chain height
in the API and AMP console. Existing Nginx routing continues to use port 3001.

The mainnet genesis identifier remains
`b29988793c29118a842ba38ea4ab13d43e3dce3f04511ba6ca3340542dfd8537`.
No testnet data, flags or reset options are used.

## Rollback

The updater keeps the previous selected release. With the mainnet node
application stopped, run:

```sh
cd /home/amp/.ampdata/instances/warthog-mainnet01/warthog-mainnet
./amp-wart-update rollback --root "$PWD" --network mainnet
./amp-wart-update verify --root "$PWD" --network mainnet
```

Then start the application in AMP. Binary rollback does not restore databases;
keep the complete cold backup for data recovery. Repeating rollback does not
toggle between releases. Future approved same-epoch releases use
**Stop application -> Update -> Start**.
