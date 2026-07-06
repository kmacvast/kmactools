# SMB Phase 0 — Live Discovery Results

**Status:** Pending live run (no `~/.vastconf` on dev host as of 2026-07-06)  
**Run on lab:**

```bash
cd vast/vast-opstat
python3 smb_phase0_discover.py --vms var203.selab.vastdata.com --user admin
# or with ~/.vastconf present:
python3 smb_phase0_discover.py
```

This file will be overwritten by the discovery script with live inventory.

## Pre-discovery hypotheses (from vastpy / VMS docs)

| FQN | Expected role |
|-----|---------------|
| `ProtoMetrics,proto_name=SMB,iops` | Cluster SMB aggregate |
| `ProtoMetrics,proto_name=SMB,bw` | Cluster SMB bandwidth |
| `ProtoMetrics,proto_name=SMB,latency` | Cluster SMB latency |
| `ProtoMetrics,proto_name=SMBCommon,rd_iops/wr_iops` | Data-path rates |
| `ProtoMetrics,proto_name=SMBCommon,md_iops` | Metadata workload |
| `SmbMetrics,smb_{cmd}_latency__rate/__avg` | Per-command table |

## Checklist (fill after live run)

- [ ] Metrics catalog SMB entries captured
- [ ] SmbMetrics per-command export table
- [ ] ProtoMetrics SMBCommon confirmed
- [ ] Client REST endpoint identified for `--clients` scoping
- [ ] View/tenant/cnode monitor scope validated
- [ ] Proxy panel gaps documented
