# KMACTools

KMac's bag of scripts.  

## Structure

```text
.
├── scripts/             # General utility shell scripts
├── tests/               # Pytest suite for core logic
└── vast/                # Primary VAST toolkit
    ├── auth/            # Authentication and token management
    ├── common/          # Shared internal utilities
    ├── identity/        # Ad configuration and identity tools
    ├── vast-du/         # Disk usage and entropy simulation
    ├── vast-sniff/      # Network/Stream sniffing utilities
    └── vast-viewer/     # VAST inspection tool
```

---

## Getting Started

### Prerequisites
* **Python 3.14+**
* **Virtual Environment** (recommended)

### Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd kmactools
   ```
2. Set up your environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## Tool Modules

### VAST Toolkit (`/vast`)

| Module | Description |
| :--- | :--- |
| **`auth`** | Handles token retrieval via `vast_get_token.py`. |
| **`identity`** | Inspects ad configurations using `show_ad_configs.py`. |
| **`vast-du`** | Tools for data unit analysis and entropy simulation (`vast-entropy-sim.py`). |
| **`vast-sniff`** | Shell-based stream sniffing and traffic analysis. |
| **`vast-viewer`** | The primary UI/CLI for auditing and viewing VAST XML structures. |

### General Scripts (`/scripts`)
* **`yt-transcribe.sh`**: A utility for handling YouTube transcription workflows.

---

## Testing

Testing is handled via `pytest`. The suite covers utility functions and core VAST data unit logic.

To run the tests:
```bash
pytest tests/
```

---

## License
This project is licensed under the **LICENSE** file included in the root directory.

---

**Note:** Ensure you have the proper credentials configured before running `vast/auth/vast_get_token.py`. Refer to the module-specific `README.md` files within the `vast/` subdirectories for detailed usage instructions.


