import pytest
import subprocess
import json
import random
import sys
from pathlib import Path
from vastpy import VASTClient

# Configuration setup (matching your script)
CONFIG_FILE = Path.home() / ".vast-viewer.conf"

@pytest.fixture(scope="session")
def vast_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

@pytest.fixture(scope="session")
def client(vast_config):
    """Initializes a real client to fetch valid IDs for random testing."""
    c = VASTClient(
        address=vast_config['vast_server'],
        user=vast_config['vast_user'],
        password=vast_config['vast_passwd']
    )
    c.session.verify = False
    return c

def run_cmd(args):
    """Helper to run the CLI script and return result."""
    cmd = [sys.executable, "vast-viewer.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result

# --- Tests for Global/List Commands ---

@pytest.mark.parametrize("flag", [
    "--list-policies", 
    "--list-views", 
    "--list-tenants", 
    "--list-vippools", 
    "--list-activities",
    "--vast-dns",
    "--vast-providers"
])
def test_list_commands(flag):
    """Tests all listing and global config options."""
    res = run_cmd([flag])
    assert res.returncode == 0
    assert len(res.stdout) > 0

# --- Tests for Detail Commands with Random IDs ---

def test_view_policy_random(client):
    policies = client.viewpolicies.get()
    if not policies:
        pytest.skip("No policies found on cluster to test.")
    random_id = random.choice(policies)['id']
    res = run_cmd(["--view-policy", "--id", str(random_id)])
    assert res.returncode == 0
    # Verify we got a valid JSON object back with the correct ID
    data = json.loads(res.stdout)
    assert data['id'] == random_id

def test_view_random(client):
    views = client.views.get()
    if not views:
        pytest.skip("No views found on cluster to test.")
    random_id = random.choice(views)['id']
    res = run_cmd(["--view", "--id", str(random_id)])
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data['id'] == random_id

def test_view_tenant_random(client):
    tenants = client.tenants.get()
    if not tenants:
        pytest.skip("No tenants found on cluster to test.")
    random_id = random.choice(tenants)['id']
    res = run_cmd(["--view-tenant", "--id", str(random_id)])
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data['id'] == random_id

def test_vippool_random(client):
    pools = client.vippools.get()
    if not pools:
        pytest.skip("No VIP pools found on cluster to test.")
    random_id = random.choice(pools)['id']
    res = run_cmd(["--vippool", "--id", str(random_id)])
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data['id'] == random_id

def test_show_activity_random(client):
    activities = client.activities.get()
    if not activities:
        pytest.skip("No activities found on cluster to test.")
    random_id = random.choice(activities)['id']
    res = run_cmd(["--show-activity", "--id", str(random_id)])
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data['id'] == random_id

# --- Negative Testing ---

def test_missing_id_error():
    """Verify that calling a detail flag without an ID prints an error."""
    res = run_cmd(["--view-policy"])
    assert "Error: --view-policy requires --id" in res.stdout
