# How it works

Three things happen: **you deploy a change** (by hand, with playbooks),
**a job starts a cloud node** (automatic), and **the controller refreshes
its Google token** (automatic). Only the first needs people.

All playbook commands run **on the operator (`hq-virt-operator`), as the
`ansible` user**, from `/opt/config-management/bmd-ansible` (`git pull`
first). `-K` asks for `ansible`'s sudo password.

## 1. Deploying a change (by hand)

```
 you                        operator                         GCP / controller
 ───                        ────────                         ────────────────
 edit the blueprint   ──►   PLAYBOOK 1: plan           ──►   nothing changes; read the plan
 (push to branch bmd)       PLAYBOOK 1: apply          ──►   GCP: instance templates, config bucket
                                                             operator: files for the controller
                            PLAYBOOK 2: slurm_cloud    ──►   controller: new cloud config,
                                                             scontrol reconfigure
```

**Playbook 1, the cloud deploy** (role `hpc_cloud_deploy`, runs as
`hpc-deployer` with a token from Vault):

```sh
# plan: shows what would change, changes nothing
ansible-playbook playbooks/infra/hosts/hq-virt-operator.biomatter.com_playbook.yml -K --tags hpc_cloud_deploy
# apply: makes the change
ansible-playbook playbooks/infra/hosts/hq-virt-operator.biomatter.com_playbook.yml -K --tags hpc_cloud_deploy -e hpc_cloud_deploy_apply=true
```

**Playbook 2, the controller** (role `slurm_cloud_install`):

```sh
ansible-playbook playbooks/infra/hosts/hq-virt-slurm-ctrl.biomatter.com_playbook.yml -K --tags slurm_cloud
```

Always both, in this order. Running jobs are not affected.

### What to run for which change

| Change | Edit | Run |
|---|---|---|
| Add or change a partition (machine, spot, max nodes, disk) | blueprint in this repo, push to `bmd` | playbook 1 (plan, apply), playbook 2 |
| A value both sides share (Slurm version, project, network, accounts) | bmd-ansible `inventory/group_vars/hpc/` | playbook 1, playbook 2 |
| Software in the node images | bmd-ansible image playbooks, then `hpc/build.sh cpu\|gpu update` in bmd-packer | nothing: the next node that starts uses the new image |
| Upstream Toolkit upgrade | see [upgrading.md](upgrading.md) | playbook 1, playbook 2, new images |

Read the plan before applying. A plan that wants to delete or replace more
than you changed means something else changed too: stop and ask.

## 2. A job starts a cloud node (automatic)

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

## 3. The controller's token (automatic)

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
