# Biomatter: hybrid Slurm cloud nodes

This fork of Cluster Toolkit carries what Biomatter adds on top of upstream.
Our changes are new files only; upstream files are only changed when there
is no other way, and then in a separate commit that says why.

- `bmd/blueprints/bmd-hpc-hybrid.yaml`: the blueprint for the cloud side
  of the on-prem Slurm cluster `bmd-hpc`. It creates the cloud nodesets and
  partitions (instance templates) in the existing network, and the files
  the on-prem controller needs. No firewall rules (see below). Copied from
  upstream's `community/examples/hpc-slurm6-hybrid.yaml`; kept in our own
  folder (the "Biomatter" section of `CLAUDE.md` allows it).
- `bmd/README.md`: this file.
- `bmd/tools/disk_bench.sh`: fio disk comparison (results under
  "Boot disk speed").
- **Changed upstream files**, three, marked `Biomatter:` (see "How it
  works"); upgrades must keep all patches:
  - slurm-gcp's `util.py`, so the on-prem controller can use a 1-hour token
    from Vault instead of a key. New test file next to it:
    `tests/test_bmd_token_credentials.py`.
  - slurm-gcp's `setup_network_storage.py`, so booting nodes don't wait for
    the controller to export the key that is already in the image. Tests at
    the end of `tests/test_setup_network_storage.py`.
  - slurm-gcp's `setup.py`, so booting nodes don't add `slurm` to
    `nsswitch.conf` or configure Google's Ops Agent.

Values (project, Slurm version, IDs, controller address) are not edited in
the blueprint. They go into an untracked deployment file passed with `-d`,
which Ansible on the operator generates from bmd-ansible. For a manual run:

```sh
gcluster create bmd/blueprints/bmd-hpc-hybrid.yaml -d my-deployment.yaml
```

with `my-deployment.yaml` containing `ai_assisted: true` and the `vars:` to
override.

The on-prem side (controller, login node, local compute nodes) is managed in
`bmd-ansible`. That repo also holds the values both sides must agree on
(Slurm version, slurm user ID, cluster name, controller address, partition
names) and passes them to this blueprint.

## How it fits together

```
bmd-ansible (values) ─► operator: gcluster create/deploy ─► GCP: instance templates
                                  install_hybrid.sh       ─► config.tgz
                                  hpc_cloud_deploy        ─► scripts, venv, cloud-nodes.conf, topology.yaml
                        controller: slurm_cloud_install   ─► /etc/slurm/cloud/, /etc/slurm/
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

**The operator follows the branch `bmd`** (`cluster_toolkit_version: bmd` in
bmd-ansible `inventory/group_vars/hpc/versions.yml`). Every deploy
(`hpc_cloud_deploy`) first pulls `bmd` and rebuilds `gcluster` if it
changed. So a change here goes live as:

```
edit on bmd → push → deploy plan on the operator → read it → deploy apply
```

Whatever is on `bmd` is what the next deploy uses: test anything
unfinished on another branch. gcluster runs with `--force`, so a new commit
(a new `gcluster` version) needs no extra step. Going back: revert the
commit on `bmd`, or set `cluster_toolkit_version` to an older tag or commit
for a while.

## Upgrading to a new upstream release

```sh
git fetch upstream --tags
git checkout -b upgrade-v1.NNN bmd
git merge v1.NNN                       # resolve conflicts, if any
git diff v1.OLD v1.NNN -- community/examples/hpc-slurm6-hybrid.yaml \
    community/examples/hybrid-scripts docs/hybrid-slurm-cluster
```

The last command shows what changed in upstream's own hybrid example; apply
what concerns us to `bmd/blueprints/bmd-hpc-hybrid.yaml`. Then, with the operator pointed at
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

The next deploy on the operator picks it up. The tag only marks a known-good
point to go back to.

Tags so far: `bmd-2026.11.1` (upstream v1.109.0; hybrid blueprint, util.py
token patch).

## Differences from the upstream example

- **No network.** The nodes use the project's existing subnet
  (`network_name`, `subnetwork_name`; europe-west4, 10.2.0.0/16). The
  project is for Slurm only. **No firewall rules** from the blueprint for
  now: traffic to and between the nodes is allowed by the project's own
  rules (managed outside it). Every cloud node carries the network tag
  `bmd-hpc-node`, so rules can target the nodes later. Needed: slurmd
  (6818) from the on-prem controller and login node, and everything between
  cloud nodes.
- **No image build.** The nodes boot our images, families `bmd-hpc-cpu` and
  `bmd-hpc-gpu`, built by bmd-packer (`hpc/`) and bmd-ansible (Slurm
  version, slurm ids 64030, the Slurm key, users, conda, Google's agents
  removed). Upstream's image groups and its `hybrid-scripts/` are not used.
  **A node boots the newest image of its family when it is created, no
  deploy needed:** the module writes the family's newest image name into
  the instance template at deploy time, so each nodeset also sets
  `instance_properties.disks` with the family URL
  (`projects/<project>/global/images/family/bmd-hpc-cpu`). `resume.py`
  sends these properties with every VM request and GCP resolves the family
  then. They replace the template's disk list: size and type are repeated
  there. Nodes already running keep their image until they power down. A bad
  image is rolled back with `gcloud compute images deprecate <name>
  --state=DEPRECATED`: the family falls back to the previous one.
- Paths: our controller uses the Ubuntu deb layout (`/usr/bin`,
  `/etc/slurm`, `/var/log/slurm`), not `/slurm/dev/<version>/inst`.
- **The Slurm key is in the images**, not fetched from an NFS export on the
  controller (upstream's `slurm_key_mount` is not used). No NFS between GCP
  and on-prem is needed for it. Consequences:
  - The images are a secret: anyone who can use images in the project can
    read the key. Keep GCP access to a few people.
  - **Changing the Slurm key means new images** (see bmd-ansible
    `roles/slurm_cloud_image_install/README.md`).
  - Since upstream #6315 (Nov 2026) a booting node first waits up to 600 s
    for the controller's NFS export of the key, before noticing the key is
    already there. Longer than `ResumeTimeout` (300 s): every node would be
    marked down. Our patch leaves the key out of that wait when it's on the
    node (hybrid only, the same check the key handler makes).
- **No NFS from the controller** (`enable_default_mounts: false`): upstream
  mounts `/home` and `/opt/apps` from the controller on every node. Ours
  exports nothing; users and tools are in the images.
- **Our service account on the nodes:** `compute_service_account_email`
  (`hpc-slurm-compute-node@...`), with a custom role granted to it outside this
  blueprint. Scope `cloud-platform`, so only IAM decides what it can do.
- **Node metadata:** `block-project-ssh-keys=TRUE` and OS Login off. With
  project-wide SSH keys, Google's guest agent would create local users with
  sudo on the nodes; access goes through the `ansible` account and our
  users from the images instead.
- **Config bucket created beforehand** (`slurm_bucket_name`,
  `create_bucket: false`). The controller module still grants read on it
  (Storage Object Viewer and Legacy Bucket Reader) to the controller's and
  the nodes' accounts; there is no setting to turn that off. So the
  deployer has Storage Admin on this bucket only.
- **The controller's account is set** in `hybrid_conf.service_account_email`
  (`controller_service_account_email`, `hpc-slurm-controller-node@...`).
  In hybrid mode the module grants that account the bucket read; unset, it
  grants it to the project's default compute account. (The controller's
  top-level `service_account_email` is not used for this in hybrid mode.)
- **Preempted spot VMs are deleted** (`spot_instance_config`,
  `termination_action: DELETE`), not left stopped with their disk. Slurm
  sees the node gone and requeues its jobs. It must be set: unset, GCP
  fills in STOP and every plan would replace the template.
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

Hyperthreading off by default, as on-prem: Slurm sees the physical cores,
half the machine type's vCPUs (`threads_per_core: 1`, the module's default,
set explicitly). Where it stays on (`threads_per_core: 2`), Slurm sees all
vCPUs. The partition names always count physical cores.

| Partition | Machine | Hyperthreading | Boot disk | Spot | Max nodes |
|---|---|---|---|---|---|
| `gcp4c32rspot` | n2-standard-8 (4 cores, 32 GB) | off (4 CPUs) | pd-balanced | yes | 2 |
| `gcp8c64rspot` | n4-standard-16 (8 cores, 64 GB) | on (16 CPUs) | hyperdisk-balanced (N4 takes only Hyperdisk), 32000 IOPS (the most a 64 GiB disk allows), 1000 MiB/s | yes | 2 |
| `gcpl4g24r` | g2-standard-8 (1x L4 24 GB, 4 cores, 32 GB) | off (4 CPUs) | pd-balanced | no | 1 |

### Boot disk speed (measured 2026-11-25)

64 GiB boot disks, measured on the nodes with fio:
`bmd/tools/disk_bench.sh <dir>` (4 GiB test file, 30 s per test, direct
I/O). PD: pd-balanced (`gcp4c32rspot`); Hyperdisk: Hyperdisk Balanced on
`gcp8c64rspot` at three settings (IOPS / MiB/s provisioned). Random 4k:
queue depth 64 × 4 jobs; sequential 1M: the read test, 32 × 4; "queue
depth 1": one job, one request at a time; "at saturation": the average
latency of the random 4k read test, 256 requests in flight. That one
follows from the IOPS (256 / IOPS: 256 / 3578 = 71.5 ms), so it shows the
same limit as the IOPS row, seen from the waiting side.

| | PD | Hyperdisk, default (3000 / 140) | Hyperdisk, 6000 / 280 | Hyperdisk, 32000 / 1000 (current) |
|---|---|---|---|---|
| Random read 4k | 3,578 IOPS | 3,579 IOPS | 6,344 IOPS | 33,900 IOPS |
| Random write 4k | 3,416 IOPS | 3,413 IOPS | 6,055 IOPS | 32,300 IOPS |
| Sequential read 1M | 159 MiB/s | 237 MiB/s | 281 MiB/s | 1,002 MiB/s |
| Latency, queue depth 1 (avg) | 370 µs | 570 µs | 576 µs | 565 µs |
| Latency at saturation | 71.5 ms | 71.5 ms | 40.3 ms | 7.6 ms |

What it shows:
- The disks deliver what is provisioned: IOPS and throughput follow the
  setting almost exactly (the N4 machine did not cap 32000 / 1000).
- Default Hyperdisk is no faster than PD in IOPS, only in sequential
  throughput (237 vs 159 MiB/s).
- A single request is not faster on Hyperdisk (about 570 µs vs 370 µs on
  PD) and doesn't improve with provisioning. What improves is how many
  requests are served at once: with 256 in flight each waits 7.6 ms
  instead of 71.5 ms.
- So the provisioned limits pay off for parallel I/O (many processes,
  conda installs, scratch on `/`), not for single-threaded small reads.

## Accounts and buckets

Project `bmd-gcp-prod-main`. All set up by hand in the console; no account
has a key except Vault's own (`vault-gcp`).

| Account | Used by | Granted | Key |
|---|---|---|---|
| `hpc-slurm-compute-node` | the cloud nodes (attached to the VM) | custom role `tagger` on the project; Storage Object Viewer on `bmd-hpc-slurm-config` | none; GCE gives the VM its tokens |
| `hpc-slurm-controller-node` | the on-prem controller (`resume.py`, `suspend.py`), token through Vault | Compute Instance Admin (v1) on the project; Service Account User on `hpc-slurm-compute-node` only; Storage Object Viewer on `bmd-hpc-slurm-config` | none |
| `hpc-packer` | Packer on the operator, token through Vault | builds images (bmd-packer `hpc/`) | none |
| `vault-gcp` | Vault itself | Service Account Token Creator on `hpc-packer`, `hpc-deployer` and `hpc-slurm-controller-node`, each granted on that account, not on the project | one, stored only inside Vault |
| `hpc-deployer` | gcluster on the operator, token through Vault | Compute Instance Admin (v1), Service Usage Viewer on the project; Service Account User on `hpc-slurm-compute-node` only; Storage Admin on `bmd-hpc-slurm-config` (writes the files and grants the read access below); Storage Object Admin and Storage Legacy Bucket Reader on `bmd-hpc-tfstate` | none |

The controller's and the nodes' rights were checked where they run; known
extras and how to check: bmd-ansible `docs/infrastructure.md`, "Checked
rights".

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
- **The controller cannot change templates, images or the network**;
  that is the deployer's job. A leaked controller token can start and
  delete VMs from the existing templates, for at most an hour.

| Bucket | For | Who reads/writes |
|---|---|---|
| `bmd-hpc-slurm-config` | the cluster's config files (`config.yaml` and the like), written at deploy | nodes and controller read (granted by hand, and again by the deploy); the deployer writes and grants |
| `bmd-hpc-tfstate` | Terraform state of the deployment; versioning on | the deployer |

## How it works

**Deploy** (rare, when the blueprint or a value changes):

```
operator: bmd-ansible hpc_cloud_deploy writes the deployment file
  └─► hpc-cloud-deploy plan|apply, as hpc-deployer (token from Vault)
        gcluster create + checks; plan: terraform plan; apply: gcluster deploy
        (state in bmd-hpc-tfstate)
        ├─► GCP: one instance template per nodeset
        ├─► bmd-hpc-slurm-config: config.yaml
        └─► operator: config.tgz (cloud.conf, resume.py, suspend.py, ...)
              └─► bmd-ansible unpacks it into /etc/slurm/cloud on the controller
```

**A job for a cloud partition** (every time):

```
sbatch -p gcp4c32rspot ...
  └─► slurmctld: no node up → runs resume.py as slurm
        reads the token in /etc/slurm/cloud/gcp-sa.json
        └─► Compute API, as hpc-slurm-controller-node:
            create bmd-hpc-gcp4c32rspot-0 from the template,
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
- `Lookup.compute` sets `GOOGLE_APPLICATION_CREDENTIALS` from
  `google_app_cred_path` only if it isn't set already. That path is the
  controller's; `setup.py --hybrid` run by `install_hybrid.sh` on the
  operator gets the deployer's token file in the variable instead
  (bmd-ansible `hpc_cloud_deploy`). On the controller nothing changes.

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

`setup_network_storage.py` (same folder) carries the second patch, marked
`Biomatter:`. `_hybrid_key_in_place()` makes the same check as
`slurm_key_mount_handler()`: hybrid, and the key file already on the node
(`/usr/local/etc/slurm/slurm.key`, from our images). If so, the key mount
is left out of the wait for the controller's NFS exports (upstream #6315)
and the handler then skips it as before. Without the key on the node,
upstream behaviour is unchanged. Tests: the `Biomatter:` ones at the end of
`tests/test_setup_network_storage.py`.

`setup.py` (same folder) carries the third patch, marked `Biomatter:`: two
calls removed from a booting node's setup:
- `setup_nss_slurm()`: it added `slurm` to the `passwd` and `group` lines of
  `/etc/nsswitch.conf` on every boot. That needs
  `LaunchParameters=enable_nss_slurm`, which bmd-ansible leaves out (the
  users are in the images); without it every lookup logged
  `_handle_getgr: incomplete data`. Our images also take `slurm` out of
  `nsswitch.conf` (bmd-ansible `slurm_cloud_image_install`).
- `setup_cloud_ops()`: configures Google's Ops Agent, which our images
  don't have.

## Open before the first deploy

- The controller's token: run bmd-ansible's Vault roles (`--tags vault_gcp`,
  `--tags vault_config`) and `slurm_gcp_token_install` on the controller.
- State bucket `bmd-hpc-tfstate`, if not created yet.
- Firewall on the office side: cloud nodes need to reach the controller on
  6817 and the login node on 60001-63000; the controller and login node need
  to reach the cloud nodes on 6818.
- DNS: not needed. The controller gets `SlurmctldParameters=cloud_reg_addrs`
  (bmd-ansible `hpc_cloud_deploy` writes it into `cloud-nodes.conf`), so a
  cloud node's address comes from its registration. The nodes reach the controller by address.
