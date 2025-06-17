# BitTorrent File Transfer Project

This project demonstrates file transfers between multiple peers using the BitTorrent protocol.

## Overview

- **Files**: Eight files named as `X_y` where `X ∈ {A, B}` and `y ∈ {10kB, 100kB, 1MB, 10MB}`.
- **File Storage**:  
    - Files starting with `A` are stored on the seeder.
    - Files starting with `B` are stored on the leechers.
- **Experiments**:
    - For each file, perform multiple transfers (different repetition counts based on file size).
    - Measure transfer time and compute throughput.
    - Record total data (including protocol overhead) to assess performance.

## Requirements

- Python 3.8 or higher
- Required Python packages:
  - libtorrent
  - flask
  - bencodepy
  - aiofiles (optional for asynchronous file support)
  - py3createtorrent

## Installation

1. Install the required packages:

```bash
pip install -r requirements.txt
```

2. Ensure `libtorrent` is installed. You can install it via pip:

```bash
sudo apt-get install python3-libtorrent
```

## Directory Setup

Create these directories:
- `./files` - Place all files to be seeded here
- `./downloads` - Where downloaded files will be saved
- `./results` - Where experiment results will be stored
- `./torrent_files` - Where torrent files will be stored

## Creating Torrent Files

The sender creates the `.torrent` file and shares it with the peers. Ensure a folder named `data_files` is present in the current working directory (CWD) containing all relevant files (e.g., `A_10kB`, `B_10kB`, ..., `B_10MB`).

Usage:
```bash
py3createtorrent -t udp://tracker.opentrackr.org:1337/announce <path-to-file>
```

Example:
```bash
py3createtorrent -t udp://tracker.opentrackr.org:1337/announce data_files/A_10kB
```

This command creates a torrent file (`A_10kB.torrent`) that is sent to the peers.

## Running the Experiment

### Step 1: Start the Tracker

```bash
python tracker.py
```

### Step 2: Start the Seeder

```bash
python main.py --role seed --tracker http://<tracker-ip>:8000/announce --port 6881
```

### Step 3: Start the Leechers

Run the following command on different terminals or machines:

```bash
python main.py --role leech --tracker http://<tracker-ip>:8000/announce --port 6882
python main.py --role leech --tracker http://<tracker-ip>:8000/announce --port 6883
python main.py --role leech --tracker http://<tracker-ip>:8000/announce --port 6884
```

The leechers will automatically:
1. Download all "A_" files from the seeder
2. Upload all "B_" files to the seeder
3. Run the appropriate number of iterations for each file
4. Measure transfer times and calculate throughput
5. Save detailed results to CSV files

## Understanding the Results

The client generates two types of result files:
1. Individual experiment CSVs: `A_10kB_leech_results.csv`, `B_10kB_seed_results.csv`, etc.
2. A summary file: `bittorrent_summary.csv`

The summary includes:
- File Size
- Download Avg (kbps)
- Download StdDev
- Upload Avg (kbps)
- Upload StdDev
- Download Overhead
- Upload Overhead

## Experiment Design Notes

- This implementation uses the BitTorrent protocol for file transfers.
- The tracker coordinates peer connections and maintains a list of active peers.
- The seeder provides the files to be downloaded by the leechers.
- All measurements are performed programmatically.
- Protocol overhead is measured by tracking the total bytes sent and received.

## Troubleshooting

- If you encounter connection issues, ensure the tracker is running and accessible.
- For peer connection issues, check firewall settings and ensure the seeder and leechers are listening on the correct ports.
- If the client can't find files, verify that files are in the correct directories with the exact names (e.g., "A_10kB").

## Notes

- The client and server are configured to use multiple TCP connections simultaneously.
- Adjust the repetition count in `BT_FILE_CONFIGS` (or use the reduced count for testing) as needed.

Use these files to test your BitTorrent file transfer project over your local network.
