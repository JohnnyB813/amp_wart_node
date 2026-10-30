# AMP testnet upgrade to official 0.10.38

This update uses the exact Linux x86-64 binary published by the successful
[upstream build](https://github.com/warthog-network/core/actions/runs/41139261907/job/124349245888).
It does not rebuild or patch the node source.

- Source: `dff967eacad0efe4140bcf76beff32b5d5f27290`
- Binary SHA-256: `a8ad1e26cb5b16546fefdfa313ee765b038d9dd828bf049b39ecb335b3f0ce20`
- Binary size: 7,351,192 bytes; static Linux amd64 ELF.
- New epoch: `testnet-2026-10-30`
- Genesis / height-1 header `prevHash`: `a1211be8b39466bee6947d9bd0ecf9963e7787af96f433c955b3772cdd691800`
- [AMP release assets](https://github.com/JohnnyB813/amp_wart_node/releases/tag/testnet-0.10.38-a8ad1e26cb5b)

Upstream explicitly restarted testnet after a consensus fix. The existing
October 24 session cannot be reused. This migration selects a fresh
`./data-testnet-2026-10-30` session, keeping all old databases and sidecars
intact. Old test balances, assets, orders, trade history and pending
transactions do not carry over. Do not rebroadcast old pending transactions.

## Current AMP configuration

Read-only inspection on October 30 found `warthog-testnet01` idle, configured
for official 0.10.36 at `wart-node-defi-beta-linux`, using
`--session="./data-testnet-2026-10-24"`. Its update/pre-start hooks are still
pinned to 0.10.36, so pressing Update now would reinstall 0.10.36.

The installer below connects this existing instance to the testnet channel
and performs the explicitly accepted reset. It preserves the assigned ports
19286 / 13100 / 13101 / 13457, `--minfee=0.00000001`, `{{TradesHistory}}`,
API bindings, other launch flags, and the host Nginx configuration for
`testnet.wartnode.com`. The selected executable becomes `current/wart-node`.
An already integrated October 24 instance can use the same migration.

## Apply once on the Linux host

Run as the AMP owner (`amp`), using `sudo -iu amp` from an administrator
login if needed. Stop the testnet node application cleanly first if it is
running. Then stop only its managed AMP instance and make a full cold backup:

```sh
ampinstmgr stop warthog-testnet01
umask 077
mkdir -p /home/amp/amp-channel-backups
df -h /home/amp
tar -czf "/home/amp/amp-channel-backups/warthog-testnet01-before-0.10.38-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C /home/amp/.ampdata/instances warthog-testnet01
```

Continue only if the backup succeeds. Download the pinned installer and
verify it before running it:

```sh
cd /home/amp
curl -fL --output install-amp-updates.py https://github.com/JohnnyB813/amp_wart_node/releases/download/updater-v0.1.0/install-amp-updates.py
printf '%s  %s\n' a04992f8e72767b5b82b16a628cf9a5ca5a3612dbe461c7889cc0ab50aeef493 install-amp-updates.py | sha256sum -c -
```

Preview the migration, then apply it only if the preview reports network
`testnet`, epoch `testnet-2026-10-30` and the binary SHA-256 above:

```sh
python3 install-amp-updates.py --network testnet --instance /home/amp/.ampdata/instances/warthog-testnet01 --accept-testnet-reset testnet-2026-10-30 --check
python3 install-amp-updates.py --network testnet --instance /home/amp/.ampdata/instances/warthog-testnet01 --accept-testnet-reset testnet-2026-10-30
```

The installer downloads and verifies the node and standalone updater. It
backs up the previous executable/configuration under `amp-update-backups/`.
It refuses a nonempty destination session and never deletes an old session.
It does not start any node, managed instance, ADS or host service.

Verify the installed selection offline before starting:

```sh
/home/amp/.ampdata/instances/warthog-testnet01/warthog-defi-testnet/amp-wart-update verify --root /home/amp/.ampdata/instances/warthog-testnet01/warthog-defi-testnet --network testnet
ampinstmgr start warthog-testnet01
```

Your managed-instance startup setting may start the node automatically.
Otherwise open **Manage -> Start** for `warthog-testnet`. The node creates
the fresh session and synchronizes from peers. ADS and the other managed
instances stay running throughout this procedure.

## Check the running node

```sh
curl -fsS http://127.0.0.1:13100/version
curl -fsS http://127.0.0.1:13100/chain/block/1/header
curl -fsS http://127.0.0.1:13100/chain/head
curl -fsS http://127.0.0.1:13100/transaction/minfee
curl -fsS https://testnet.wartnode.com/version
```

Expect version 0.10.38, the new genesis `prevHash` above, peer connections
and an advancing chain. The height-1 endpoint may be unavailable until the
first block is synchronized. Check the AMP console for errors as well.

For subsequent releases in this epoch, use **Stop node -> application's
Update button -> Start node** inside its management page. The ADS tile's
Update action updates AMP/module configuration and is not this application
update path. No schedules or whole-AMP restart tasks are added.

A regular update refuses another epoch change. Rollback also refuses to
select a retained binary from the retired October 24 chain. Keep the full
cold backup for recovery; binary rollback does not restore database state.
