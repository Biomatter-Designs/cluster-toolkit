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
- **Changed upstream file**, the only one: slurm-gcp's `util.py`, so the
  on-prem controller can use a 1-hour token from Vault instead of a key
  (see "How it works"). New test file next to it:
  `tests/test_bmd_token_credentials.py`. Upgrades must keep this patch.

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
  (`hpc-slurm-compute-node@...`), with a custom role granted to it outside this
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

Project `bmd-gcp-prod-main`. All set up by hand in the console; no account
has a key except Vault's own (`vault-gcp`).

| Account | Used by | Granted | Key |
|---|---|---|---|
| `hpc-slurm-compute-node` | the cloud nodes (attached to the VM) | custom role `tagger` on the project; Storage Object Viewer on `bmd-hpc-slurm-config` | none; GCE gives the VM its tokens |
| `hpc-slurm-controller-node` | the on-prem controller (`resume.py`, `suspend.py`), token through Vault | Compute Instance Admin (v1) on the project; Service Account User on `hpc-slurm-compute-node` only; Storage Object Viewer on `bmd-hpc-slurm-config` | none |
| `hpc-packer` | Packer on the operator, token through Vault | builds images (bmd-packer `hpc/`) | none |
| `vault-gcp` | Vault itself | Service Account Token Creator on `hpc-packer` and on `hpc-slurm-controller-node`, each granted on that account, not on the project | one, stored only inside Vault |
| `hpc-deployer` | gcluster on the operator, token through Vault | Compute Instance Admin (v1), Compute Security Admin, Service Usage Viewer on the project; Service Account User on `hpc-slurm-compute-node` only; Storage Object Admin and Storage Legacy Bucket Reader on `bmd-hpc-slurm-config` and `bmd-hpc-tfstate` | none |

Deploys run as `hpc-deployer` through bmd-ansible's `hpc_cloud_deploy`.
gcluster takes no bare token, so for the run a local stand-in metadata
server hands it the Vault token (details in that role's README).

Why the grants look like this:

- **Service Account User on the node account, not on the project**: to
  create a VM that runs as an account, the creator needs this right on that
  account. Granted on `hpc-slurm-compute-node` only, the controller can
  start nodes as that account and as no other (not as `hpc-packer`, not as
  the default compute account).
- **Token Creator on each account, not on the project**: Vault can mint
  tokens for exactly the accounts listed, nothing else in the project.
- **The controller cannot change firewall rules, templates or images**;
  that is the deployer's job. A leaked controller token can start and
  delete VMs from the existing templates, for at most an hour.

| Bucket | For | Who reads/writes |
|---|---|---|
| `bmd-hpc-slurm-config` | the cluster's config files (`config.yaml` and the like), written at deploy | nodes and controller read; the deployer writes |
| `bmd-hpc-tfstate` | Terraform state of the deployment; versioning on | the deployer |

## How it works

**Deploy** (rare, when the blueprint or a value changes):

```
operator: bmd-ansible hpc_cloud_deploy writes the deployment file
  └─► hpc-cloud-deploy plan|apply, as hpc-deployer (token from Vault)
        gcluster create + checks; plan: terraform plan; apply: gcluster deploy
        (state in bmd-hpc-tfstate)
        ├─► GCP: firewall rules, one instance template per nodeset
        ├─► bmd-hpc-slurm-config: config.yaml
        └─► operator: config.tgz (cloud.conf, resume.py, suspend.py, ...)
              └─► bmd-ansible unpacks it into /etc/slurm/cloud on the controller
```

**A job for a cloud partition** (every time):

```
sbatch -p gcp8c32rspot ...
  └─► slurmctld: no node up → runs resume.py as slurm
        reads the token in /etc/slurm/cloud/gcp-sa.json
        └─► Compute API, as hpc-slurm-controller-node:
            create bmd-hpc-gcp8c32rspot-0 from the template,
            running as hpc-slurm-compute-node
              └─► node boots our image (bmd-hpc-cpu), reads config.yaml
                  from the bucket, starts slurmd, which registers with the
                  controller (10.16.1.2:6817) over the VPN
  └─► job runs; after 300 s idle slurmctld runs suspend.py → VM deleted
```

**The controller's token** (all the time):

```
bmd-ansible slurm_gcp_token_install on the controller: timer every 15 min (own AppRole, only from 10.16.1.2)
  └─► Vault: gcp/impersonated-account/hpc-slurm-controller-node/token
        └─► Google IAM, as vault-gcp: "a 1-hour token for hpc-slurm-controller-node"
              └─► /etc/slurm/cloud/gcp-sa.json (0600, slurm), rewritten every 15 min
```

No service-account key exists for this project. `resume.py` and
`suspend.py` start as new processes and read the token on every call.
Upstream's scripts only accept a key file there, so slurm-gcp's
`util.py` (`community/modules/scheduler/schedmd-slurm-gcp-v6-controller/modules/slurm_files/scripts/`)
carries our patch, marked `Biomatter:`:

- `_token_credentials()`: a file that is not JSON is read as a bare token;
  a JSON key file is handled as upstream.
- `get_credentials()` (Compute calls: start and delete nodes) uses it.
- `storage_client()` (reading the config bucket) gets the token passed
  explicitly, with no project; Google's own lookup would parse the file as
  JSON.

Not changed, because we do not use them: the Secret Manager client (Cloud
SQL passwords) and the BigQuery export. Tests:
`scripts/tests/test_bmd_token_credentials.py`. On every upgrade, check that
the patch still applies and run the tests:

```sh
cd community/modules/scheduler/schedmd-slurm-gcp-v6-controller/modules/slurm_files/scripts
python3 -m venv /tmp/sgv && /tmp/sgv/bin/pip install -r requirements-dev.txt
/tmp/sgv/bin/python -m pytest -q tests/
```

If Vault or the token refresh is down for longer than about 45 minutes, cloud nodes
stop starting; running jobs and on-prem nodes are not affected.

## Open before the first deploy

- The controller's token: run bmd-ansible's Vault roles (`--tags vault_gcp`,
  `--tags vault_config`) and `slurm_gcp_token_install` on the controller.
- State bucket `bmd-hpc-tfstate`, if not created yet.
- Firewall on the office side: cloud nodes need to reach the controller on
  6817 and the login node on 60001-63000; the controller and login node need
  to reach the cloud nodes on 6818.
- DNS: the on-prem controller must resolve the cloud nodes' names (cloud
  DNS forwarding over the VPN). The nodes reach the controller by address.
