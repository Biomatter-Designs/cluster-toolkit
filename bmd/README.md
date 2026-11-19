# Biomatter: hybrid Slurm cloud nodes

This fork of Cluster Toolkit carries what Biomatter adds on top of upstream.
Our changes are new files only; upstream files are only changed when there
is no other way, and then in a separate commit that says why.

- `community/examples/bmd-hpc-hybrid.yaml`: the blueprint for the cloud side
  of the on-prem Slurm cluster `bmd-hpc`. It creates the firewall rules in
  the existing network, the cloud nodesets and partitions, and the files the
  on-prem controller needs. It sits next to upstream's
  `hpc-slurm6-hybrid.yaml`, which it is copied from, because the repo's
  rules keep blueprint copies beside their template.
- `bmd/README.md`: this file.

Values (project, Slurm version, IDs, controller address) are not edited in
the blueprint. They go into an untracked deployment file passed with `-d`,
which Ansible on the operator generates from bmd-ansible. For a manual run:

```sh
gcluster create community/examples/bmd-hpc-hybrid.yaml -d my-deployment.yaml
```

with `my-deployment.yaml` containing `ai_assisted: true` and the `vars:` to
override.

The on-prem side (controller, login node, local compute nodes) is managed in
`bmd-ansible`. That repo also holds the values both sides must agree on
(Slurm version, slurm user ID, cluster name, controller address, partition
names) and passes them to this blueprint.

## How it fits together

```
bmd-ansible (values) ─► operator: gcluster create/deploy ─► GCP: firewall, templates
                                  install_hybrid.sh       ─► config.tgz
                        controller playbook               ─► /etc/slurm/cloud/ on the controller
```

The operator runs Cluster Toolkit; the controller only receives the generated
files (`cloud.conf`, `cloud_gres.conf`, resume and suspend scripts). Cloud
nodes are started by the controller when jobs need them and deleted when
idle.

## Branches and versions

| Branch | What |
|---|---|
| `main` | Copy of upstream. Never commit to it. |
| `bmd` | Upstream plus our files. This is what we run. |
| `upgrade-...` | Short-lived, for testing one upstream upgrade. |

The operator runs a **tag** of `bmd` (e.g. `bmd-2026.11.1`), set as
`cluster_toolkit_version` in bmd-ansible `inventory/group_vars/hpc/versions.yml`.
Going back means setting the previous tag.

## Upgrading to a new upstream release

```sh
git fetch upstream --tags
git checkout -b upgrade-v1.NNN bmd
git merge v1.NNN                       # resolve conflicts, if any
git diff v1.OLD v1.NNN -- community/examples/hpc-slurm6-hybrid.yaml \
    community/examples/hybrid-scripts docs/hybrid-slurm-cluster
```

The last command shows what changed in upstream's own hybrid example; apply
what concerns us to `community/examples/bmd-hpc-hybrid.yaml`. Then, with the operator pointed at
the upgrade branch: deploy, regenerate `config.tgz`, update the controller,
and test (power a cloud node up and down, run a job). A new Toolkit release
usually comes with a new slurm-gcp image: the node images' scripts in
`/slurm/scripts` and the controller's resume/suspend scripts must come from
the same slurm-gcp version, so the base image (`hpc_base_source_image` in
bmd-ansible) and the CPU/GPU images move with it.

When it works:

```sh
git checkout bmd && git merge upgrade-v1.NNN
git tag bmd-YYYY.MM.N && git push origin bmd --tags
git branch -d upgrade-v1.NNN
```

and set the new tag in bmd-ansible.

## Differences from the upstream example

- **No network.** The nodes use the project's existing subnet
  (`network_name`, `subnetwork_name`; europe-west4, 10.2.0.0/16). The
  project is for Slurm only. The blueprint adds two firewall rules, both
  limited to the network tag `bmd-hpc-node` that every cloud node carries:
  slurmd (6818) from the on-prem controller and login node, and everything
  between cloud nodes.
- **No image build.** The nodes boot our images, families `bmd-hpc-cpu` and
  `bmd-hpc-gpu`, built by bmd-packer (`hpc/`) and bmd-ansible (Slurm
  version, slurm ids 64030, the Slurm key, users, conda, Google's agents
  removed). Upstream's image groups and its `hybrid-scripts/` are not used.
  Nodes created after a deploy take the newest image of their family.
- Paths: our controller uses the Ubuntu deb layout (`/usr/bin`,
  `/etc/slurm`, `/var/log/slurm`), not `/slurm/dev/<version>/inst`.
- **The Slurm key is in the images**, not fetched from an NFS export on the
  controller (upstream's `slurm_key_mount` is not used). No NFS between GCP
  and on-prem is needed for it. Consequences:
  - The images are a secret: anyone who can use images in the project can
    read the key. Keep GCP access to a few people.
  - **Changing the Slurm key means new images** (see bmd-ansible
    `roles/slurm_cloud_image_install/README.md`).
- **Our service account on the nodes:** `compute_service_account_email`
  (`slurm-compute@...`), with a custom role granted to it outside this
  blueprint. Scope `cloud-platform`, so only IAM decides what it can do.
- **Node metadata:** `block-project-ssh-keys=TRUE` and OS Login off. With
  project-wide SSH keys, Google's guest agent would create local users with
  sudo on the nodes; access goes through the `ansible` account and our
  users from the images instead.
- **Config bucket created beforehand** (`slurm_bucket_name`,
  `create_bucket: false`), so its IAM is set explicitly and the deployer
  needs no rights to change bucket policies.
- **Terraform state in a GCS bucket**, set by the deployment file
  (`terraform_backend_defaults`), not in the deployment folder.
- slurm user and group ID 64030 (ours), not 620.
- Shared values (project, region, network, Slurm version, slurm IDs,
  controller) have no default in the blueprint. Their only source is
  bmd-ansible; gcluster refuses to run if the deployment file does not set
  them.
- Partition names follow our scheme. The on-prem partition stays the
  default. Partitions use `exclusive: false`: a node takes several jobs and
  is deleted after 300 s idle, instead of after every job.

## Partitions (testing)

| Partition | Machine | Spot | Max nodes |
|---|---|---|---|
| `gcp8c32rspot` | n2-standard-8 (8 vCPU, 32 GB) | yes | 2 |
| `gcpl4g24r` | g2-standard-8 (1x L4 24 GB, 8 vCPU, 32 GB) | no | 1 |

## Accounts and buckets

Created by hand before the first deploy:

| What | Name | Needs |
|---|---|---|
| Node account | `slurm-compute@bmd-gcp-prod-main` | custom role; read on the config bucket (`storage.objects.get`, `storage.objects.list`) |
| Controller account (resume/suspend) | `slurm-controller@bmd-gcp-prod-main` | `roles/compute.instanceAdmin.v1` on the project; `roles/iam.serviceAccountUser` on the node account only; read on the config bucket. No key: see below |
| Deployer account (gcluster on the operator) | `hpc-deployer`, token through Vault | creates instance templates and firewall rules; reads and writes the state bucket |
| Config bucket | `bmd-hpc-slurm-config` | |
| State bucket | `bmd-hpc-tfstate` | versioning on |

## The controller's credentials

No service-account key exists for this project. Vault impersonates
`slurm-controller` (like `hpc-packer`) and hands out access tokens, valid
for one hour at Google. Vault Agent on the controller fetches a fresh token
about every 40 minutes and writes it to `/etc/slurm/cloud/gcp-sa.json`
(0600, slurm); `resume.py` and `suspend.py` start as new processes and read
it on every call.

Upstream's scripts only accept a key file there, so this needs a small
patch in slurm-gcp's `util.py` (`get_credentials()`): JSON in the file is
handled as before, anything else is read as a token. Planned, not yet in
this branch; check it on every upgrade.

If Vault or the agent is down for longer than about 20 minutes, cloud nodes
stop starting; running jobs and on-prem nodes are not affected.

## Open before the first deploy

- The controller and deployer accounts, and the controller's token
  (below).
- Firewall on the office side: cloud nodes need to reach the controller on
  6817 and the login node on 60001-63000; the controller and login node need
  to reach the cloud nodes on 6818.
- DNS: the on-prem controller must resolve the cloud nodes' names (cloud
  DNS forwarding over the VPN). The nodes reach the controller by address.
