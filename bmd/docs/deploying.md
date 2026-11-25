# Deploying changes

How to get a change to the cloud side live: a new or changed partition, a
new shared value, new node software.

All commands run **on the operator (`hq-virt-operator`), as the `ansible`
user**, from `/opt/config-management/bmd-ansible` (`git pull` first). `-K`
asks for `ansible`'s sudo password.

## The steps

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

## What to run for which change

| Change | Edit | Run |
|---|---|---|
| Add or change a partition (machine, spot, max nodes, disk) | blueprint in this repo, push to `bmd` | playbook 1 (plan, apply), playbook 2 |
| A value both sides share (Slurm version, project, network, accounts) | bmd-ansible `inventory/group_vars/hpc/` | playbook 1, playbook 2 |
| Software in the node images | bmd-ansible image playbooks, then `hpc/build.sh cpu\|gpu update` in bmd-packer | nothing: the next node that starts uses the new image |
| Upstream Toolkit upgrade | see [upgrading.md](upgrading.md) | playbook 1, playbook 2, new images |

Read the plan before applying. A plan that wants to delete or replace more
than you changed means something else changed too: stop and ask.
