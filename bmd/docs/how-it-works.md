# What runs on its own

Once deployed, two things happen without anyone: the controller starts and
deletes cloud nodes as jobs need them, and it keeps a fresh Google token
for that. To change something, see [deploying.md](deploying.md).

## A job starts a cloud node

```
 user (login node)          controller                       GCP
 ─────────────────          ──────────                       ───
 sbatch -p gcp4c32rspot ──► no node up: resume.py      ──►   new VM from the template
                                                             boots our newest image
                            slurmd registers   ◄── VPN ──    reads config from the bucket
                            job runs on the node
                            300 s idle: suspend.py     ──►   VM deleted
```

Logs: `/var/log/slurm/resume.log` and `suspend.log` on the controller. A
node that couldn't start goes `down~` (see [partitions.md](partitions.md),
"When a node won't start").

## The controller refreshes its Google token

```
 controller                         Vault                     Google
 ──────────                         ─────                     ──────
 timer, every 15 min          ──►   checks the controller ──► 1-hour token for
                                                              hpc-slurm-controller-node
 /etc/slurm/cloud/gcp-sa.json ◄───────────────────────────────┘
```

Set up once with the controller's playbook (`--tags slurm_gcp_token`,
bmd-ansible `roles/slurm_gcp_token_install/README.md`). No key exists. If
Vault is down for more than about 45 minutes, cloud nodes stop starting;
running jobs are not affected. Check: `journalctl -u slurm-gcp-token.service`.

## What's where

| Thing | Where |
|---|---|
| Cloud part of the Slurm config | controller: `/etc/slurm/cloud-nodes.conf`, `cloud-gres.conf`, `topology.yaml` |
| slurm-gcp's scripts and the token | controller: `/etc/slurm/cloud/` |
| Start and stop logs | controller: `/var/log/slurm/resume.log`, `suspend.log` |
| Node setup log | node: `/var/log/slurm/setup.log` |
| Last plan | operator: `/opt/cluster-toolkit-deployments/bmd-hpc-hybrid-plan.txt` |
| Terraform state | bucket `bmd-hpc-tfstate` |
