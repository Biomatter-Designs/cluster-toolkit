# Biomatter: tests for the access-token file at google_app_cred_path
# (util._token_credentials, get_credentials, storage_client, Lookup.compute).

import pytest
from mock import Mock

from common import TstCfg  # noqa: F401  needed to import util
import util
import google.oauth2.credentials


@pytest.fixture(autouse=True)
def fresh_credentials(monkeypatch):
    util.get_credentials.cache_clear()
    monkeypatch.setattr(util, "universe_domain", lambda: "googleapis.com")
    yield
    util.get_credentials.cache_clear()


def test_token_file_gives_token_credentials(tmp_path, monkeypatch):
    f = tmp_path / "gcp-sa.json"
    f.write_text("ya29.test-token\n")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(f))

    creds = util.get_credentials()

    assert isinstance(creds, google.oauth2.credentials.Credentials)
    assert creds.token == "ya29.test-token"


def test_json_file_keeps_upstream_key_handling(tmp_path, monkeypatch):
    f = tmp_path / "key.json"
    f.write_text('{"type": "service_account"}')
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(f))
    from_file = Mock(return_value="key-credentials")
    monkeypatch.setattr(util.service_account.Credentials,
                        "from_service_account_file", from_file)

    assert util.get_credentials() == "key-credentials"
    from_file.assert_called_once()


def test_storage_client_uses_token(tmp_path, monkeypatch):
    f = tmp_path / "gcp-sa.json"
    f.write_text("ya29.test-token")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(f))
    client = Mock()
    monkeypatch.setattr(util.storage, "Client", client)

    util.storage_client()

    kwargs = client.call_args.kwargs
    assert kwargs["project"] is None
    assert kwargs["credentials"].token == "ya29.test-token"


def test_storage_client_unchanged_without_token(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    client = Mock()
    monkeypatch.setattr(util.storage, "Client", client)

    util.storage_client()

    assert "credentials" not in client.call_args.kwargs
    assert "project" not in client.call_args.kwargs


def test_compute_keeps_caller_credentials(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/run/deployer-token")
    monkeypatch.setattr(util, "compute_service", Mock(return_value="compute"))
    lkp = util.Lookup(TstCfg(google_app_cred_path="/etc/slurm/cloud/gcp-sa.json"))

    assert lkp.compute == "compute"
    assert util.os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == "/run/deployer-token"


def test_compute_sets_cred_path_when_unset(monkeypatch):
    # setenv first, so monkeypatch removes what compute sets afterwards.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "placeholder")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS")
    monkeypatch.setattr(util, "compute_service", Mock(return_value="compute"))
    lkp = util.Lookup(TstCfg(google_app_cred_path="/etc/slurm/cloud/gcp-sa.json"))

    assert lkp.compute == "compute"
    assert util.os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == "/etc/slurm/cloud/gcp-sa.json"
