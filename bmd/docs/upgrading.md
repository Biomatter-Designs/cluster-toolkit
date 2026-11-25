# Changes and upgrades

## Branches

| Branch | What |
|---|---|
| `main` | copy of upstream; never commit to it |
| `bmd` | upstream plus our files; **this is what runs** |
| `upgrade-...` | short-lived, to test one upstream upgrade |

## How a change goes live

The operator follows `bmd` (`cluster_toolkit_version: bmd` in bmd-ansible's
`inventory/group_vars/hpc/versions.yml`). Every deploy pulls it first.

```
edit on bmd → push → deploy (plan, read it, apply, controller: deploying.md)
```

Whatever is on `bmd` is used by the next deploy, so test unfinished work on
another branch. To go back: revert on `bmd`, or point
`cluster_toolkit_version` at an older tag for a while.

## Upgrading to a new upstream release

```sh
git fetch upstream --tags
git checkout -b upgrade-v1.NNN bmd
git merge v1.NNN                       # resolve conflicts, if any
git diff v1.OLD v1.NNN -- community/examples/hpc-slurm6-hybrid.yaml docs/hybrid-slurm-cluster
```

1. Apply what concerns us from upstream's hybrid example to our blueprint.
2. Check that our patches still apply and their tests pass
   ([upstream-changes.md](upstream-changes.md)).
3. A new release usually brings a new slurm-gcp image: the node images and
   the controller's scripts must come from the same slurm-gcp version, so
   build a new base image too (bmd-ansible `hpc_base_source_image`).
4. With the operator pointed at the upgrade branch: deploy, update the
   controller, power a node up and down, run a job.

When it works:

```sh
git checkout bmd && git merge upgrade-v1.NNN
git tag bmd-YYYY.MM.N && git push origin bmd --tags
git branch -d upgrade-v1.NNN
```

The tag marks a known-good point to go back to. Tags so far:
`bmd-2026.11.1` (upstream v1.109.0).
