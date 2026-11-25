# Our changes to upstream files

We add files and change upstream ones only when there is no other way.
Three slurm-gcp files carry a patch, each marked `Biomatter:` in the code.
All are in `community/modules/scheduler/schedmd-slurm-gcp-v6-controller/modules/slurm_files/scripts/`.
**Every upgrade must keep all three.**

| File | Change | Why |
|---|---|---|
| `util.py` | a token file that isn't JSON is used as a bare access token | the controller has no key, only a 1-hour token from Vault; upstream reads only key files |
| `setup_network_storage.py` | a booting node doesn't wait for the controller to export the Slurm key when the key is already on the node | the key is in our images; upstream's wait (up to 600 s) is longer than Slurm's 300 s start timeout, so every node would be marked down |
| `setup.py` | two boot steps removed: `setup_nss_slurm()`, `setup_cloud_ops()` | the first put Slurm into `nsswitch.conf` on every boot, causing `_handle_getgr: incomplete data` errors (our users are in the images); the second configures Google's Ops Agent, which our images don't have |

Without our setup (no token file, no key on the node), the first two behave
as upstream.

One detail of the `util.py` patch: `GOOGLE_APPLICATION_CREDENTIALS` is kept
when already set. That lets the deploy on the operator (`install_hybrid.sh`)
use the deployer's token instead of the controller's path from the config;
without it the deploy fails with `FileNotFoundError: /etc/slurm/cloud/gcp-sa.json`.

## Tests

`tests/test_bmd_token_credentials.py` (token) and the `Biomatter:` tests at
the end of `tests/test_setup_network_storage.py` (key wait). Run the whole
suite after every upgrade:

```sh
cd community/modules/scheduler/schedmd-slurm-gcp-v6-controller/modules/slurm_files/scripts
python3 -m venv /tmp/sgv && /tmp/sgv/bin/pip install -r requirements.txt -r requirements-dev.txt
/tmp/sgv/bin/python -m pytest -q tests/
```

## Also not used from upstream

Upstream's image build groups, `hybrid-scripts/`, the NFS mounts from the
controller (`enable_default_mounts: false`), the Slurm key export
(`slurm_key_mount`), the Secret Manager and BigQuery parts of slurm-gcp.
