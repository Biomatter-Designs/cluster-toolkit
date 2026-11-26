# Cloud partitions

All defined in `bmd/blueprints/bmd-hpc-hybrid.yaml`. The on-prem partition
stays the default; cloud partitions are chosen with `-p`.

| Partition | Machine | CPUs in Slurm | Boot disk | Spot | Max nodes |
|---|---|---|---|---|---|
| `gcp8c32rspot` | n2-standard-8 (4 cores, 32 GB) | 8 | pd-balanced | yes | 2 |
| `gcp16c64rspot` | n4-standard-16 (8 cores, 64 GB) | 16 | Hyperdisk Balanced, 32000 IOPS, 1000 MiB/s | yes | 2 |
| `gcpl4g24r` | g2-standard-8 (1× L4 24 GB, 4 cores, 32 GB) | 8 | pd-balanced | no | 10 |
| `gcpl4g24rspot` | as `gcpl4g24r` | 8 | pd-balanced | yes | 10 |

Node features (shown by `sinfo`, selected with `-C`):

| Partition | GRES | Features |
|---|---|---|
| `gcp8c32rspot`, `gcp16c64rspot` | none | `spot` |
| `gcpl4g24r` | `gpu:nvidia-l4:1` | `l4,gpumem_24,sm_89,ondemand` |
| `gcpl4g24rspot` | `gpu:nvidia-l4:1` | `l4,gpumem_24,sm_89,spot` |

Users ask for the model by feature and the count untyped: `-C l4
--gres=gpu:1`. The scheme is cluster-wide (bmd-ansible,
`roles/slurmctld_install/README.md`, "Node features").

Node names: `gcp-<partition without gcp>-<n>`, e.g. `gcp-l4g24r-0` in
`gcpl4g24r`. The `gcp` prefix is `hpc_cloud_node_prefix` in bmd-ansible
(`inventory/group_vars/hpc/cloud.yml`); it is not Slurm's cluster name.

## Rules every partition follows

- **Names** follow the cluster-wide scheme (bmd-ansible,
  `roles/slurmctld_install/README.md`): `<where><cores>c<RAM GB>r[spot]`,
  GPUs `<where><model>g<GPU GB>r[spot]`. The name counts vCPUs, as `sinfo`
  shows them and as in the machine type (n2-standard-**8** → `gcp8c32rspot`).
- **Hyperthreading on** (`threads_per_core: 2`, set explicitly: the module's
  default is 1), as on-prem: Slurm gets all vCPUs and hands out whole cores,
  so `-c 1` gets 2 CPUs and two jobs never share a core. GCP bills the
  vCPUs either way.
- **Newest image, no deploy:** each node set boots the newest image of its
  family (`bmd-hpc-cpu`, `bmd-hpc-gpu`) when a VM is created. A new image
  from bmd-packer goes live at the next node start. Bad image: `gcloud
  compute images deprecate <name> --state=DEPRECATED`, and the family falls
  back to the previous one.
- **Spot nodes are deleted** when GCP takes them back; Slurm requeues.
- **Shared nodes:** `exclusive: false`; a node is deleted after 300 s idle.
- **GPU partitions use three zones** (europe-west4-a, -b, -c): L4s often
  run out in one zone, and GCP then picks a zone that has them. CPU
  partitions stay in -b.

## Adding or changing a partition

1. Copy a node set and partition pair in the blueprint (the closest match),
   change the names (partition `gcpXYZ`, node set `XYZ`), machine, spot,
   max nodes and `node_conf` (features; for GPUs also `Gres` with GCP's
   accelerator name). Keep the image block
   (`instance_properties`) and set its disk type to the node set's.
2. Add the partition to the controller module's `partitions` and `nodeset`
   lists at the end of the blueprint.
3. Validate offline (`gcluster expand`, see the repo's `CLAUDE.md`), push to
   `bmd`.
4. Deploy: plan, apply, then the controller ([deploying.md](deploying.md)).
5. Check quota in GCP for new machine types and GPUs (on-demand and spot
   are separate quotas).

Also list the new name in bmd-ansible's `slurmctld_install` and
`hpc_cloud_deploy` READMEs.

## Hyperdisk

N4 machines take only Hyperdisk. `gcp16c64rspot` provisions 32000 IOPS (the
most a 64 GiB disk allows) and 1000 MiB/s (`hyperdisk_iops`,
`hyperdisk_throughput`); above the baseline of 3000 / 140 it is paid.
Measured: the disk delivers what is provisioned, and helps parallel I/O
(many processes, conda installs), not single small reads.
Details: [disk-benchmark.md](disk-benchmark.md).

## When a node won't start or disappears

On the controller, `/var/log/slurm/resume.log` says why. What happens next
depends on the case:

| Case | What happens | Action |
|---|---|---|
| **No capacity** (`ZONE_RESOURCE_POOL_EXHAUSTED`, stockout) or **quota exceeded** | `resume.py` powers the node down again (`%` in `sinfo`), after 300 s it is `idle~` and usable. Batch jobs go back to the queue and retry by themselves | none for `sbatch`; `srun`/`salloc` fail at once, start them again. Quota: raise it in the GCP console |
| **Any other start error** (template, permissions, token) | node marked `down~` | fix the cause, then `scontrol update nodename=<node> state=power_down_force` |
| **A running VM disappears** (spot preemption, VM deleted) | slurmctld marks the node down and requeues its jobs; the node stays down | `scontrol update nodename=<node> state=power_down_force` |

The last two are not reset automatically yet (bmd-ansible
`docs/infrastructure.md`, "Not built yet"). For GPUs that are hard to get:
submit with `sbatch` and wait.
