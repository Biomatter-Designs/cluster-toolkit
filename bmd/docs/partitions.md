# Cloud partitions

All defined in `bmd/blueprints/bmd-hpc-hybrid.yaml`. The on-prem partition
stays the default; cloud partitions are chosen with `-p`.

| Partition | Machine | CPUs in Slurm | Boot disk | Spot | Max nodes |
|---|---|---|---|---|---|
| `gcp4c32rspot` | n2-standard-8 (4 cores, 32 GB) | 4 | pd-balanced | yes | 2 |
| `gcp8c64rspot` | n4-standard-16 (8 cores, 64 GB) | 16 (hyperthreading on) | Hyperdisk Balanced, 32000 IOPS, 1000 MiB/s | yes | 2 |
| `gcpl4g24r` | g2-standard-8 (1× L4 24 GB, 4 cores, 32 GB) | 4 | pd-balanced | no | 10 |
| `gcpl4g24rspot` | as `gcpl4g24r` | 4 | pd-balanced | yes | 10 |

Node names: `bmd-hpc-<partition>-<n>`, e.g. `bmd-hpc-gcpl4g24r-0`.

## Rules every partition follows

- **Names** follow the cluster-wide scheme (bmd-ansible,
  `roles/slurmctld_install/README.md`): `<where><cores>c<RAM GB>r[spot]`,
  GPUs `<where><model>g<GPU GB>r[spot]`. The name counts physical cores.
- **Hyperthreading off** by default (`threads_per_core: 1`), as on-prem:
  Slurm gets the physical cores. Where it stays on (`threads_per_core: 2`),
  Slurm gets all vCPUs.
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
   change name, machine, spot and max nodes. Keep the image block
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

N4 machines take only Hyperdisk. `gcp8c64rspot` provisions 32000 IOPS (the
most a 64 GiB disk allows) and 1000 MiB/s (`hyperdisk_iops`,
`hyperdisk_throughput`); above the baseline of 3000 / 140 it is paid.
Measured: the disk delivers what is provisioned, and helps parallel I/O
(many processes, conda installs), not single small reads.
Details: [disk-benchmark.md](disk-benchmark.md).

## When a node won't start

On the controller, `/var/log/slurm/resume.log`:

| Message | Meaning |
|---|---|
| `ZONE_RESOURCE_POOL_EXHAUSTED` / `STOCKOUT` | GCP has no capacity right now; try again later or another partition |
| `QUOTA_EXCEEDED` | raise the quota in the GCP console |

A failed node goes `down~` and stays there until reset:
`scontrol update nodename=<node> state=power_down_force`.
