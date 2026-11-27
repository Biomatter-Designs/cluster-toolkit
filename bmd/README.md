# Biomatter: hybrid Slurm cloud nodes

This fork of Cluster Toolkit adds GCP cloud nodes to Biomatter's on-prem
Slurm cluster `bmd-hpc`. The controller, the login node and the local
compute nodes stay on-prem and are managed by **bmd-ansible**; this repo
only describes the cloud side.

When a job needs a cloud partition, the on-prem controller starts a VM in
GCP. The VM joins the cluster over the VPN, runs the job, and is deleted
after 300 s idle.

## What's here

| Path | What |
|---|---|
| `bmd/blueprints/bmd-hpc-hybrid.yaml` | the blueprint: cloud partitions (instance templates) and the files the controller needs |
| `bmd/docs/` | the pages linked below |
| `bmd/tools/disk_bench.sh` | fio disk comparison |
| three upstream files, marked `Biomatter:` | small patches to slurm-gcp ([upstream-changes.md](docs/upstream-changes.md)) |

Everything else is upstream, unchanged.

## How it fits together

```
bmd-ansible (all values) ──► operator: gcluster deploy ──► GCP: instance templates, config bucket
                                       └─► config.tgz ──► controller: cloud-nodes.conf, resume/suspend scripts
job for a cloud partition ──► controller: resume.py ──► GCP: VM from the template ──► joins over the VPN
```

Values (project, Slurm version, IDs, controller address, network) are never
edited in the blueprint. bmd-ansible's `hpc_cloud_deploy` writes them into
an untracked deployment file on the operator and runs the deploy from there.

## How it differs from upstream's hybrid example

- **No network and no firewall rules:** nodes use the project's existing
  subnet in each region (europe-west4 10.2.0.0/16, europe-west1
  10.3.0.0/16); firewall rules are managed outside.
- **Our own images** (bmd-packer `hpc/`): our Slurm build, users, the Slurm
  key. A node boots the newest image of its family, without a deploy.
- **No NFS from the controller:** the key and the users are in the images.
- **No service-account keys anywhere:** the controller uses a 1-hour token
  from Vault, the deploy too.
- **Spot VMs are deleted** when preempted; Slurm requeues their jobs.
- **Nodes take several jobs** (`exclusive: false`) and stay up until idle.

## Pages

| Page | Read it for |
|---|---|
| [deploying.md](docs/deploying.md) | **you want to change something**: which playbooks, in which order |
| [partitions.md](docs/partitions.md) | the cloud partitions, adding or changing one |
| [how-it-works.md](docs/how-it-works.md) | what runs on its own: nodes starting and stopping, the token |
| [accounts.md](docs/accounts.md) | GCP service accounts and buckets |
| [storage.md](docs/storage.md) | data and job output on cloud nodes (pilot in progress) |
| [upgrading.md](docs/upgrading.md) | branches, upstream upgrades |
| [upstream-changes.md](docs/upstream-changes.md) | our patches to upstream files, and their tests |
| [disk-benchmark.md](docs/disk-benchmark.md) | PD vs Hyperdisk measurements |

The on-prem side, and how each step is run: bmd-ansible's
`roles/hpc_cloud_deploy/README.md` (deploy) and
`roles/slurm_cloud_install/README.md` (controller).
