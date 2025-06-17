# HTTP/1.1 File Transfer Project

This project demonstrates file transfers between two computers over a local area network using HTTP/1.1.

## Overview

- **Files**: Eight files named as `X_y` where `X ∈ {A, B}` and `y ∈ {10kB, 100kB, 1MB, 10MB}`.
- **File Storage**:  
    - Files starting with `A` are stored on computer 1.  
    - Files starting with `B` are stored on computer 2.
- **Experiments**:
    - For each file, perform multiple transfers (different repetition counts based on file size).
    - Measure transfer time and compute throughput.
    - Record total data (including header information) to assess protocol overhead.

## Contents

- **client/client.py**: Async client using HTTP/1.1 for downloading (for files with prefix 'A') or uploading (for files with prefix 'B').
- **server/server.py**: FastAPI server serving the file endpoints.
- **requirements.txt**: Required Python packages.
- **readme.md**: This file.

## Setup

1. **Install dependencies**:  
     ```bash
     pip install -r requirements.txt
     ```

2. **Prepare Files**:  
     Place the eight files in the `files` directory.

3. **Run the Server**:  
     On one computer (or in one terminal window), run:
     ```bash
     python server/server.py
     ```
     The server will start on port 8000 using HTTP/1.1.

4. **Run the Client**:  
     On the other computer (or in another terminal window), run:
     ```bash
     python client/client.py --server http://<server-ip>:8000
     ```
     Replace `<server-ip>` with the IP address of the server computer.

## Experimentation

The client will perform file transfers based on the configured experiments, and results will be saved in the `results` directory.

## Notes

- The client and server are configured to use only one TCP connection at a time.
- Adjust the repetition count in `FILE_CONFIGS` (or use the reduced count for testing) as needed.

Use these files to test your HTTP/1.1 file transfer project over your local network.