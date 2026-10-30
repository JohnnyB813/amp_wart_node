# One-time setup for the existing AMP nodes

After this one-time connection, application updates use AMP's own Update
button. No archive copying or unpacking is required for later node releases.
This first phase creates no timer, cron entry, or automatic restart schedule.

## Prerequisites

- Linux x86-64 AMP host, outbound HTTPS to GitHub, and Python 3 on the host.
- Existing mainnet/testnet templates with the known application IDs and paths.
- Use the AMP owner account, normally `amp` (`sudo -iu amp` from an admin login).
- Keep the normal AMP Docker/Podman image and host networking. The standalone
  updater has no Python, curl, or package-manager requirement inside it.

The one-time installer changes only update/pre-start hooks and the executable
selection, plus the testnet session argument if you explicitly accept a reset.
It preserves assigned ports, minfee, API bindings, and startup settings.

## Download the pinned installer once

```sh
curl -fL --output install-amp-updates.py https://github.com/JohnnyB813/amp_wart_node/releases/download/updater-v0.1.0/install-amp-updates.py
```

The installer downloads the matching versioned standalone updater and verifies
its published SHA-256. It does not require a GitHub token for this public repo.

## Mainnet: preserve the existing chain and selected binary

1. Stop the node application cleanly in its own AMP panel, then stop only the
   managed mainnet AMP instance. ADS and other instances can stay running.
2. Take a complete cold backup outside the instance. Confirm free space first.

```sh
ampinstmgr stop warthog-mainnet01
umask 077
mkdir -p /home/amp/amp-channel-backups
tar -czf "/home/amp/amp-channel-backups/warthog-mainnet01-before-channel-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C /home/amp/.ampdata/instances warthog-mainnet01
```

3. After the backup succeeds, preview and integrate:

```sh
python3 install-amp-updates.py --network mainnet --instance /home/amp/.ampdata/instances/warthog-mainnet01 --check
python3 install-amp-updates.py --network mainnet --instance /home/amp/.ampdata/instances/warthog-mainnet01
ampinstmgr start warthog-mainnet01
```

Integration retains the selected mainnet binary. It leaves
`--chain-db="./data/chain.db3"`, `--peers-db="./data/peers.db3"`, and the existing
`--minfee=0.00009992` unchanged. It saves original executable/configuration
copies under the instance's `amp-update-backups/` directory.

4. Manage the mainnet instance, **stop its node application**, click that
   application's **Update**, then **Start**. This selects the promoted mainnet
   build. Leave the managed AMP panel running for these normal updates.

Use the application's update control inside its management page. The ADS
instance-tile Update/Update All actions update AMP/module configuration and
are not the node update path described here.

## Testnet: migrate to the October 30 reset chain (0.10.38)

Official 0.10.38 resets the testnet again. Both the pre-October-24 releases
(0.10.32/0.10.33) and the October 24 releases (0.10.34-0.10.36) require an
explicit fresh session. An existing channel integration also blocks this
reset until you rerun the installer with the new epoch.

Follow [the 0.10.38 upgrade guide](UPGRADE-0.10.38.md) for the current server's
0.10.36 configuration, cold backup, download verification, preview and migration.
The same commands work for an already integrated October 24 instance.

For an instance already bound to the verified October 30 chain, rerun the
installer without a reset option if needed:

```sh
python3 install-amp-updates.py --network testnet --instance /home/amp/.ampdata/instances/warthog-testnet01 --check
python3 install-amp-updates.py --network testnet --instance /home/amp/.ampdata/instances/warthog-testnet01
```

Future updates within this epoch use **Stop node -> Update -> Start node**.
A future testnet genesis/epoch change is blocked until another explicitly
accepted migration. Normal updates never reset data.

## Check after starting

From the node's application directory, `amp-wart-update verify` checks the
selected binary offline, and `check` compares it to the remote channel.

Mainnet API checks:

```sh
curl -fsS http://127.0.0.1:3000/tools/version
curl -fsS http://127.0.0.1:3000/chain/head
curl -fsS http://127.0.0.1:3000/transaction/minfee
```

Testnet API checks:

```sh
curl -fsS http://127.0.0.1:13100/version
curl -fsS http://127.0.0.1:13100/chain/block/1/header
curl -fsS http://127.0.0.1:13100/chain/head
```

The approved reset chain's height-1 header `prevHash` is
`a1211be8b39466bee6947d9bd0ecf9963e7787af96f433c955b3772cdd691800`.
Check peer connections and chain progress as well as the version string.
Mainnet's custom 0.8.20 build is identified by its source commit/hash; the
version string alone cannot distinguish two custom builds.

## Rollback and recovery

With the node stopped, run from its application directory:

```sh
./amp-wart-update rollback --root "$PWD" --network mainnet
```

Use `--network testnet` for testnet. This selects the retained previous release
within the same epoch and does not touch databases. Repeating rollback is
idempotent. A reset migration provides no automatic rollback
to the retired chain; any retained previous pointer from that epoch is refused.
Keep its original configuration/binary backup
for archival recovery; it does not make that retired network current again.

If one-time integration must be undone, stop this node and managed AMP
instance, restore the saved `GenericModule.kvp` and its matching executable
selection from `amp-update-backups/`, then restart only this instance. If data
recovery is needed, use a complete matching cold backup and keep each SQLite
snapshot with its own sidecars. Do not mix old/new snapshots.

The repository does not install a whole-AMP restart task or host service.