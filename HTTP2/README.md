# HTTP/2 Bidirectional File Transfer Implementation

This implementation enables file transfers between two computers using HTTP/2 protocol while maintaining a single TCP connection. It allows files to be transferred in both directions:
- Computer 1 (Server) to Computer 2 (Client) using GET requests
- Computer 2 (Client) to Computer 1 (Server) using POST requests

## Requirements

- Python 3.8 or higher
- Required Python packages:
  - httpx
  - fastapi
  - uvicorn[standard]
  - pydantic
  - aiofiles
  - h2
  - hypercorn

## Installation

1. Install the required packages:

```bash
pip install -r requirements.txt
```

2. Generate a self-signed certificate (HTTP/2 requires TLS):

```bash
# Run this script to generate key.pem and cert.pem
openssl genrsa -out key.pem 2048
openssl req -new -x509 -key key.pem -out cert.pem -days 365 -subj "/CN=localhost"
```

## Directory Setup

### On Computer 1 (Server)
Create these directories:
- `./files` - Place all "A_" files here
- `./uploads` - Where "B_" files will be received
- `./results` - Optional for storing results if needed

### On Computer 2 (Client)
Create these directories:
- `./files` - Place all "B_" files here
- `./downloads` - Where "A_" files will be saved
- `./results` - Where experiment results will be stored

## Running the Experiment

### Step 1: Start the Server on Computer 1
```bash
python server.py
```

### Step 2: Run the Client on Computer 2
```bash
python client.py --server https://COMPUTER1_IP:8000
```

The client will automatically:
1. Download all "A_" files from the server (GET requests)
2. Upload all "B_" files to the server (POST requests)
3. Run the appropriate number of iterations for each file
4. Measure transfer times and calculate throughput
5. Save detailed results to CSV files

## Understanding the Results

The client generates two types of result files:
1. Individual experiment CSVs: `A_10kB_download_results.csv`, `B_10kB_upload_results.csv`, etc.
2. A summary file: `http2_summary.csv`

The summary includes:
- Average throughput (bytes/second)
- Protocol overhead (total bytes transferred / file size)
- Average transfer time
- Number of successful repetitions

## Experiment Design Notes

- This implementation maintains a single TCP connection between the computers by using HTTP/2's connection multiplexing
- GET requests transfer files from server to client
- POST requests transfer files from client to server
- All measurements are performed programmatically
- Protocol overhead is measured by tracking header sizes and multipart form encoding overhead

## Troubleshooting

- If you encounter SSL certificate errors, ensure that both computers have the same `key.pem` and `cert.pem` files
- For connection issues, check firewall settings and ensure the server is listening on all interfaces
- If the client can't find files, verify that files are in the correct directories with the exact names (e.g., "A_10kB")