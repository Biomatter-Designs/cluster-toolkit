# How it works

## Deploy (when the blueprint or a value changes)

```
operator: bmd-ansible hpc_cloud_deploy writes the deployment file
  └─► plan or apply, as hpc-deployer (1-hour token from Vault)
        ├─► GCP: one instance template per node set
        ├─► bucket bmd-hpc-slurm-config: config.yaml
        └─► operator: config.tgz (cloud.conf, resume.py, suspend.py, ...)
              └─► bmd-ansible slurm_cloud_install puts it on the controller
```

Terraform state is in the bucket `bmd-hpc-tfstate`. The deploy always pulls
the branch `bmd` first ([upgrading.md](upgrading.md)).

## A job on a cloud partition (every time)

```
sbatch -p gcp4c32rspot ...
  └─► slurmctld: no node up → resume.py (as slurm, with the controller's token)
        └─► GCP: VM bmd-hpc-gcp4c32rspot-0 from the template,
            running as hpc-slurm-compute-node
              └─► boots our image, reads config.yaml from the bucket,
                  slurmd registers with the controller over the VPN
  └─► job runs; after 300 s idle: suspend.py → VM deleted
```

The node's address reaches the controller with its registration
(`cloud_reg_addrs`), so no DNS is needed. Job output and interactive
sessions go back to the login node directly.

## The controller's token (all the time)

```
controller: timer every 15 min (bmd-ansible slurm_gcp_token_install)
  └─► Vault, with the controller's own login
        └─► Google, as vault-gcp: a 1-hour token for hpc-slurm-controller-node
              └─► /etc/slurm/cloud/gcp-sa.json, read by resume.py and suspend.py
```

There is no service-account key. If Vault or the refresh is down for more
than about 45 minutes, cloud nodes stop starting; running jobs and on-prem
nodes are not affected.

## What's where

| Thing | Where |
|---|---|
| Cloud part of the Slurm config | controller: `/etc/slurm/cloud-nodes.conf`, `cloud-gres.conf`, `topology.yaml` |
| slurm-gcp's scripts and token | controller: `/etc/slurm/cloud/` |
| Start/stop logs | controller: `/var/log/slurm/resume.log`, `suspend.log` |
| Node setup log | node: `/var/log/slurm/setup.log` |
| Cluster config for nodes | bucket `bmd-hpc-slurm-config` |
