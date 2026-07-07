# vast-sniff

Leader-node packet-capture helper for VAST clusters. Wraps `tcpdump` with input
validation, a timestamped output filename, and a capture summary on exit.

> Part of the [kmactools](../../docs/README.md) toolkit.

---

## What it does

`vast-sniff.sh` captures traffic to/from a single client IP on the cluster leader node and
writes a `.pcap` to `/vast/log/` for later analysis in Wireshark.

- Requires **root** (`sudo`).
- Validates that `CLIENT_IP` and `LABEL` are set and that `LABEL` is alphanumeric.
- Prints a capture summary (duration, destination, file size) on `Ctrl-C`.

---

## Prerequisites

Run on the cluster leader node, inside the platform container:

```bash
# 1. Find and log onto the leader node
find-leader

# 2. Attach to the platform container
/vast/data/attachdocker.sh
```

---

## Usage

Edit the variables at the top of the script (`CLIENT_IP`, `LABEL`, `OUT_DIR`) to target the
client you want to trace, then run:

```bash
sudo ./vast-sniff.sh
# Press Ctrl-C to stop; the .pcap path and size are printed on exit.
```

Output: `/vast/log/tcpdump_<LABEL>_<YYYYMMDDHHMM>.pcap`

---

## Safety

Read-only packet capture — it does not modify cluster state. Capture files may contain
sensitive payloads; treat and store them accordingly.

---

**Author:** KMac · kmac@vastdata.com
