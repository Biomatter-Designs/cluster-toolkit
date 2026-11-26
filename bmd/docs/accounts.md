# GCP accounts and buckets

Project `bmd-gcp-prod-main`, set up by hand in the console. No account has
a key except Vault's own; everyone else gets 1-hour tokens from Vault.

| Account | Used by | Can |
|---|---|---|
| `hpc-slurm-controller-node` | the on-prem controller (`resume.py`, `suspend.py`) | start and delete VMs (Compute Instance Admin), run them as the node account only, read the config bucket |
| `hpc-slurm-compute-node` | the cloud nodes themselves | read the config bucket and the data bucket; labels and tags (custom role `tagger`) |
| `hpc-deployer` | deploys from the operator | instance templates, write the config bucket, Terraform state |
| `hpc-packer` | image builds from the operator | build VMs and images |
| `vault-gcp` | Vault | only create tokens for the three accounts above that use them |

| Bucket | Holds | Written by |
|---|---|---|
| `bmd-hpc-slurm-config` | the cluster config the nodes read at boot | the deployer |
| `bmd-hpc-tfstate` | Terraform state (versioned) | the deployer |
| `bmd-hpc-data-europe-west4` | read-only data for jobs ([storage.md](storage.md)); one such bucket per region | by hand for now |

## Why it's set up like this

- **No keys:** a leaked token stops working within the hour.
- **"Act as" only on the node account:** the controller can start VMs as
  `hpc-slurm-compute-node` and as no other account.
- **Token rights per account, not per project:** Vault can only mint tokens
  for the accounts listed.
- **The controller can't change the network or the setup:** that's the
  deployer's job.

The controller's and the nodes' rights were checked where they run, with
known extras and how to check: bmd-ansible `docs/infrastructure.md`,
"Checked rights". Exact grants: same file, "Google Cloud access".
