################################################################################
# Script Name:    test_utils.py
# Description:    Unit tests for VAST common utilities using mocks.
#
# Author:         KMac kmac@vastdata.com
# Version:        0.1.0
################################################################################

import pytest
import json
from vast.common.utils import load_vast_config

def test_load_vast_config_normalization(mocker):
    """Test that 'default' tenant is normalized to None."""
    # Mock data with 'default' tenant
    mock_conf = {
        "vms": "var203.selab.vastdata.com",
        "user": "admin",
        "tenant": "default",
        "password": "test"
    }
    
    # Mock open and json.load
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", mocker.mock_open(read_data=json.dumps(mock_conf)))
    
    conf = load_vast_config("~/.vastconf")
    
    assert conf["tenant"] is None
    assert conf["user"] == "admin"

def test_load_vast_config_custom_tenant(mocker):
    """Test that specific tenants are preserved."""
    mock_conf = {"vms": "v", "user": "u", "tenant": "us-central", "password": "p"}
    
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", mocker.mock_open(read_data=json.dumps(mock_conf)))
    
    conf = load_vast_config("~/.vastconf")
    assert conf["tenant"] == "us-central"
