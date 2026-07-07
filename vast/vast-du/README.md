# **VAST Data: Directory Efficiency Reporter**

### **Why This Tool Exists**

Standard Linux tools like `du`, `df`, or `ls` only see "Logical" data. They cannot see the impact of VAST Data's **Global Deduplication**, **Similarity Reduction**, and **Compression**.

This script bridges that gap. It queries the VAST Element Store directly to reveal exactly how much physical space your data is consuming, and more importantly, it provides the insights needed to characterize the storage efficiency of various file formats, data structures, and computational workflows.

---

### Key Metrics Explained

| Metric | Math / Formula | Definition | Why It Matters |
| :--- | :--- | :--- | :--- |
| **Logical Size** | Total host-written bytes | The volume of data your application *thinks* it is using. | Baseline for capacity planning. |
| **Unique Size** | Post-Dedup bytes | The volume of non-redundant data held exclusively within this specific path. | Represents the "reclaimable" capacity returned to the cluster if this directory were deleted. |
| **Physical Size** | Final bytes on disk | The actual "Real" footprint occupied on the NVMe fabric after all reduction and metadata overhead. | This is the actual capacity consumed on your cluster. |
| **Total DRR** | `Logical / Physical` | The overarching efficiency ratio for the dataset. | The single number that determines your effective capacity ROI. |
| **Dedupe Ratio** | `Logical / Unique` | Efficiency gained specifically through VAST Global Deduplication. | Shows how much of your data is redundant across the cluster. |
| **Compression** | `Unique / Physical` | Efficiency gained via local algorithmic compression. | Characterizes how well your specific file types (e.g., logs vs. images) shrink. |

---

### **Installation & Setup**

1. **Install python packages:**  

```bash
pip install vastpy
```

2. **Configure Credentials:**  
   Create a hidden configuration file in your home directory. This allows the script to run securely and automatically.  
   **File:** \~/.vastconf  
```json
{
  "vms": "FQDN_OR_IP",
  "user": "USERNAME",
  "tenant": "YOUR_TENANT",
  "password": "YOUR_PASSWORD"
}
```
3. **Secure the File:**  
```bash
chmod 600 ~/.vastconf
```
---

### **Usage Guide**

#### **1\. Basic Directory Report**

Check the efficiency of a specific logical path:

```bash
python3 vast-du.py -d /kmac/nfs
```

#### **2\. Deep Efficiency Breakdown**

Use the **\-b** or **\--breakdown** flag to see exactly how much of your savings come from Deduplication versus Compression. This is essential for understanding data profile behavior.

> **Similarity metrics will be added shortly.** 

```
python3 vast-du.py -d /kmac/nfs -b
```

#### **3\. Automatic Child Discovery (Top Talkers)**

Use the **\-c** or **\--children** flag to automatically find and report on every immediate subdirectory. This is a good way to identify which datasets are your "best" or "worst" reducers.

```bash
python3 vast-du.py -d /kmac/nfs --children
```

#### **4\. Output Options**

* **CSV (Excel):** `python3 vast-du.py -d / -c -o csv > vast_report.csv`
* **JSON:** `python3 vast-du.py -d / -c -o json`

---
#### **Example Usage**
```bash
$ python3  ~/scripts/vast-du.py -d /kmac/splunk/logs/high_comp /kmac/splunk/logs/low_comp -b -o json
[
    {
        "path": "/kmac/splunk/logs/high_comp",
        "logical_gib": 290.54,
        "physical_gib": 7.98,
        "unique_gib": 8.92,
        "drr": 36.42,
        "dedup": 32.56,
        "comp": 1.12
    },
    {
        "path": "/kmac/splunk/logs/low_comp",
        "logical_gib": 212.25,
        "physical_gib": 64.21,
        "unique_gib": 68.92,
        "drr": 3.31,
        "dedup": 3.08,
        "comp": 1.07
    }
]
```

---
### API Endpoints Used

The script automatically detects cluster versioning and queries the following:

* **VOS 5.5+ (Modern):** `GET /api/latest/capacity/` using `type=usable`. Data is extracted from an index-mapped array based on the `keys` metadata (`usable`, `unique`, `logical`) provided by the system.
* **Legacy VOS:** `GET /api/capacity/capacity_estimation/`. This older endpoint provides raw capacity estimates for clusters that haven't transitioned to the latest index-based reporting structure.
* **Child Discovery:** `GET /api/folders/` to enumerate subdirectories for recursive reporting.
---

**Author:** KMac (kmac@vastdata.com), 04/07/2026

**Version:** 0.4.2
