import os
import json
import urllib3

def load_vast_config(path="~/.vastconf"):
    """Loads and normalizes VAST config for Global or Tenant admins."""
    full_path = os.path.expanduser(path)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Config not found: {full_path}")
        
    with open(full_path, 'r') as f:
        conf = json.load(f)
        
    # Standard VAST normalization for Global Admin
    raw_tenant = conf.get("tenant", "").strip()
    conf["tenant"] = raw_tenant if raw_tenant and raw_tenant.lower() != "default" else None
    
    # Disable SSL warnings globally when this is called
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    return conf
