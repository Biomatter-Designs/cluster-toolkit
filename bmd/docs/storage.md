# Storage on cloud nodes

> **Status: pilot in progress.** This page describes the agreed design; the
> pilot runs in europe-west4 on `gcp-euw4-8c32rspot` with the CPU image, and
> europe-west1 (`gcp-euw1-8c32rspot`) for the bucket copy. Done so
> far: the data bucket `bmd-hpc-data-europe-west4`; the node side of its
> mount is written (bmd-ansible role `hpc_cloud_storage_install`), the image
> not built yet. Paths and intervals marked *TBD* are still open.

Cloud nodes can't see on-prem storage, and a spot VM's disk is gone when it
is preempted. The design gives them three things:

| Need | How |
|---|---|
| read-only data (datasets, DBs, models) | regional bucket, mounted read-only with gcsfuse on `/mnt/shared/bucket_data` |
| job output that survives preemption | local disk `/scratch/<jobid>`, copied to a results bucket during the job |
| results back on-prem | login node pulls them from the bucket into the results path (*TBD*) |

## Read-only data

```
on-prem NFS ──► Semaphore publish job ──► primary bucket ──► bmd-hpc-data-<region> (one per GPU region)
                                                               │  versioned prefix, _READY written last
                                          cloud node ◄──────────┘  gcsfuse, read-only, mounted by root
```

Each region has its own copy with the same layout inside:

```
gs://bmd-hpc-data-<region>/v0001/{datasets,db,models}/...
                           v0001/_READY        ← written last; nodes use the newest ready version
```

Nodes don't derive the bucket from their region: the blueprint passes it
as node metadata (`hpc-data-bucket`, from `vars.data_bucket_<region>` via
`node_metadata_<region>`, per nodeset), and the
mount reads that. The region in the name is only for people.

At boot the node mounts the newest ready version on
`/mnt/shared/bucket_data`, read-only for everyone:
`gs://<bucket>/v0001/datasets/x` is `/mnt/shared/bucket_data/datasets/x`.
A new version reaches only nodes that boot after it is published. If the
mount fails the node still joins (for now, to keep troubleshooting
simple); `journalctl -u hpc-data-mount` on the node says why.

Bucket settings: regional, Standard, uniform access, public access
prevention, hierarchical namespace, no versioning, no soft delete (the data
can be rebuilt from NFS). `hpc-slurm-compute-node` has Storage Object
Viewer on it, nothing more.

Users only see files; no `gs://` in their tools.

## Job output

```
 node (root)                                      bucket gs://bmd-hpc-results/<user>/<jobid>/
 ───────────                                      ──────
 Prolog: create /scratch/<jobid> (user, 0700),
         restore from bucket if requeued    ◄──
 timer, every N min (TBD)                   ──►   copy
 shutdown hook (preemption)                 ──►   last copy
 Epilog: final copy, delete local           ──►   (retry; keep local on failure)

 login node (root timer) ◄── pull into <results path>/<user>/<jobid>/, delete bucket copy
```

A requeued job keeps its job id, so it finds its earlier output in the
bucket. Symlinks are never followed.

**Defaults for users:** a `cli_filter` (Lua) on the login node sets
`--chdir=/scratch/%j` and `--output=/scratch/%j/slurm-%j.out` for jobs on
`gcp*` partitions, unless the user set them. Without it, a cloud job starts
in the submit directory (usually the on-prem home), which doesn't exist on
cloud nodes. It runs as the user, so it's a convenience, not a control.

## Who can read what

Users never get Google credentials: the metadata server is blocked for
non-root users by an nftables table of its own (DNS and NTP stay open). Only root on the node copies to and from
buckets. Users are kept apart by Unix ownership, the same as on-prem.

## Why not ...

- **Slurm burst buffer (`#BB stage_in/stage_out`, `burst_buffer/lua`).**
  The Lua hooks run in slurmctld on the controller, not on the node, so
  they can't reach the node's local disk. Stage-in runs before the job
  starts, when the cloud VM may not exist yet. Stage-out runs once at the
  end; after a preemption the VM and its disk are already gone, and there's
  no periodic copy. A requeued job lands on a new VM with nothing restored.
  It would also need bucket credentials on the controller. Burst buffers
  assume an always-up shared filesystem; we have per-node disk.
- **Shared filesystem (Filestore etc.).** Cost per region, no cross-region.
- **rsync to an on-prem share in Prolog/Epilog.** Output lost on
  preemption; nodes would need on-prem write access.
- **Per-user service accounts or per-job buckets.** Too complicated, and
  they don't solve users reaching the node's credentials.
- **Storage Transfer Service** for the data sync: `gcloud storage rsync`
  from a Semaphore job is enough.
