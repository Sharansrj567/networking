import asyncio
import csv
import os
import time
from pathlib import Path
import argparse
import sys
import aiofiles

import httpx

RESULTS_DIR = Path("./results")
FILES_DIR = Path("./files")
DOWNLOADS_DIR = Path("./downloads")

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

FILE_CONFIGS = [
    {"prefix": "A", "size": "10kB", "times": 1000},
    {"prefix": "A", "size": "100kB", "times": 100},
    {"prefix": "A", "size": "1MB", "times": 10},
    {"prefix": "A", "size": "10MB", "times": 1},
    {"prefix": "B", "size": "10kB", "times": 1000},
    {"prefix": "B", "size": "100kB", "times": 100},
    {"prefix": "B", "size": "1MB", "times": 10},
    {"prefix": "B", "size": "10MB", "times": 1}
]

class HTTP2Client:
    def __init__(self, server_url):
        self.server_url = server_url
        self.client = httpx.AsyncClient(
            http2=True,
            verify=False,
            limits=httpx.Limits(max_connections=1)
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
        
    async def download_file(self, filename: str):
        """
        Download a file from server to client via GET request
        """
        start_time = time.time()
        
        response = await self.client.get(f"{self.server_url}/files/{filename}")
        response.raise_for_status()
        
        headers_size = sum(len(k) + len(v) for k, v in response.headers.items())
        total_bytes_transferred = len(response.content) + headers_size
        
        file_path = DOWNLOADS_DIR / filename
        with open(file_path, "wb") as f:
            f.write(response.content)
        
        end_time = time.time()
        transfer_time = end_time - start_time
        
        file_size = len(response.content)
        throughput = file_size / transfer_time if transfer_time > 0 else 0
        
        return {
            "filename": filename,
            "file_size": file_size,
            "transfer_time": transfer_time,
            "throughput": throughput,
            "total_bytes": total_bytes_transferred,
            "direction": "download"
        }

    async def upload_file(self, filename: str):
        """
        Upload a file from client to server via POST request
        """
        file_path = FILES_DIR / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"File {filename} not found in {FILES_DIR}")
        
        start_time = time.time()
        
        async with aiofiles.open(file_path, "rb") as f:
            file_content = await f.read()
        
        files = {"file": (filename, file_content, "application/octet-stream")}
        
        response = await self.client.post(
            f"{self.server_url}/upload/{filename}",
            files=files
        )
        response.raise_for_status()
        
        end_time = time.time()
        transfer_time = end_time - start_time
        
        file_size = len(file_content)
        
        headers_size = sum(len(k) + len(v) for k, v in response.request.headers.items())
        multipart_overhead = 0
        if hasattr(response.request, '_content'):
            request_body = response.request._content.decode('utf-8', errors='ignore')
            multipart_overhead = len(request_body) - file_size
        else:
            boundary = response.request.headers.get('Content-Type', '').split('boundary=')[-1]
            multipart_overhead = (len(boundary) + 40) * 2
            multipart_overhead += len(f'Content-Disposition: form-data; name="file"; filename="{filename}"') + 40        
        multipart_overhead = 200 if multipart_overhead == 0 else multipart_overhead
        total_bytes_transferred = file_size + headers_size + multipart_overhead
        
        throughput = file_size / transfer_time if transfer_time > 0 else 0
        
        return {
            "filename": filename,
            "file_size": file_size,
            "transfer_time": transfer_time,
            "throughput": throughput,
            "total_bytes": total_bytes_transferred,
            "direction": "upload"
        }

    async def run_experiment(self, prefix: str, size: str, repetitions: int):
        """
        Run experiment for a specific file
        """
        filename = f"{prefix}_{size}"
        print(f"Starting experiment for {filename}, {repetitions} repetitions")
        
        results = []
        
        if prefix == "A":
            transfer_func = self.download_file
        else:
            transfer_func = self.upload_file
        
        tasks = []
        for i in range(repetitions):
            print(f"Scheduling transfer {i+1}/{repetitions} for {filename}")
            tasks.append(transfer_func(filename))
        
        # Run all transfers concurrently
        transfer_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in transfer_results:
            if isinstance(result, Exception):
                print(f"Error transferring {filename}: {result}")
            else:
                results.append(result)
                print(f"  Throughput: {result['throughput']/1024:.2f} KB/s")
        
        if results:
            avg_throughput = sum(r["throughput"] for r in results) / len(results)
            avg_transfer_time = sum(r["transfer_time"] for r in results) / len(results)
            avg_total_bytes = sum(r["total_bytes"] for r in results) / len(results)
            avg_file_size = sum(r["file_size"] for r in results) / len(results)
            overhead_ratio = avg_total_bytes / avg_file_size if avg_file_size > 0 else 0
            
            csv_path = RESULTS_DIR / f"{filename}_{results[0]['direction']}_results.csv"
            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "Filename", "Direction", "File Size (B)", "Transfer Time (s)", 
                    "Throughput (B/s)", "Total Bytes (B)"
                ])
                for r in results:
                    writer.writerow([
                        r["filename"], r["direction"], r["file_size"], 
                        r["transfer_time"], r["throughput"], r["total_bytes"]
                    ])
            
            return {
                "filename": filename,
                "direction": results[0]["direction"],
                "avg_throughput": avg_throughput,
                "avg_transfer_time": avg_transfer_time,
                "avg_file_size": avg_file_size,
                "avg_total_bytes": avg_total_bytes,
                "overhead_ratio": overhead_ratio,
                "repetitions": len(results)
            }
        
        return None

async def main():
    parser = argparse.ArgumentParser(description="HTTP/2 File Transfer Client")
    parser.add_argument("--server", required=True, help="Server URL (e.g., https://192.168.1.2:8000)")
    args = parser.parse_args()
    
    async with HTTP2Client(args.server) as client:
        response = await client.client.get(f"{args.server}/list")
        
        if hasattr(response, "http_version"):
            version = response.http_version
        else:
            version = "unknown"
            try:
                if hasattr(client.client, "_connections"):
                    for conn in client.client._connections.values():
                        if hasattr(conn, "http_version"):
                            version = conn.http_version
                            break
            except:
                pass
        
        print(f"Connected using {version}")
        if version != "HTTP/2" and version != "2":
            print("WARNING: Not using HTTP/2!")
        
        throughput_data = {
            "10kB": {"download": [], "upload": []},
            "100kB": {"download": [], "upload": []},
            "1MB": {"download": [], "upload": []},
            "10MB": {"download": [], "upload": []}
        }
        
        overhead_data = {
            "10kB": {"download": [], "upload": []},
            "100kB": {"download": [], "upload": []},
            "1MB": {"download": [], "upload": []},
            "10MB": {"download": [], "upload": []}
        }
        
        all_results = []
        
        for config in FILE_CONFIGS:
            prefix = config["prefix"]
            size = config["size"]
            times = config["times"]
            
            result = await client.run_experiment(prefix, size, times)
            if result:
                all_results.append(result)
                
                direction = result["direction"]
                throughput_kbps = result["avg_throughput"] * 8 / 1000
                throughput_data[size][direction].append(throughput_kbps)
                
                overhead_data[size][direction].append(result["overhead_ratio"])
        
        print("\n========== HTTP/2 THROUGHPUT (kilobits per second) ==========")
        print("File Size | Download Avg | Download StdDev | Upload Avg | Upload StdDev")
        print("--------|------------|--------------|----------|------------")
        
        for size in ["10kB", "100kB", "1MB", "10MB"]:
            download_values = throughput_data[size]["download"]
            if download_values:
                download_avg = sum(download_values) / len(download_values)
                if len(download_values) > 1:
                    download_stddev = (sum((x - download_avg) ** 2 for x in download_values) / (len(download_values) - 1)) ** 0.5
                else:
                    download_stddev = 0
            else:
                download_avg = 0
                download_stddev = 0
                
            upload_values = throughput_data[size]["upload"]
            if upload_values:
                upload_avg = sum(upload_values) / len(upload_values)
                if len(upload_values) > 1:
                    upload_stddev = (sum((x - upload_avg) ** 2 for x in upload_values) / (len(upload_values) - 1)) ** 0.5
                else:
                    upload_stddev = 0
            else:
                upload_avg = 0
                upload_stddev = 0
                
            print(f"{size} | {download_avg:.2f} | {download_stddev:.2f} | {upload_avg:.2f} | {upload_stddev:.2f}")
        
        print("\n========== HTTP/2 OVERHEAD RATIO ==========")
        print("File Size | Download | Upload")
        print("--------|----------|-------")
        
        for size in ["10kB", "100kB", "1MB", "10MB"]:
            download_ratios = overhead_data[size]["download"]
            download_avg = sum(download_ratios) / len(download_ratios) if download_ratios else 0
            
            upload_ratios = overhead_data[size]["upload"]
            upload_avg = sum(upload_ratios) / len(upload_ratios) if upload_ratios else 0
            
            print(f"{size} | {download_avg:.4f} | {upload_avg:.4f}")
        
        table_path = RESULTS_DIR / "http2_table_data.csv"
        with open(table_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["File Size", "Download Avg (kbps)", "Download StdDev", "Upload Avg (kbps)", "Upload StdDev", 
                            "Download Overhead", "Upload Overhead"])
            
            for size in ["10kB", "100kB", "1MB", "10MB"]:
                download_values = throughput_data[size]["download"]
                download_avg = sum(download_values) / len(download_values) if download_values else 0
                download_stddev = (sum((x - download_avg) ** 2 for x in download_values) / (len(download_values) - 1)) ** 0.5 if len(download_values) > 1 else 0
                
                upload_values = throughput_data[size]["upload"]
                upload_avg = sum(upload_values) / len(upload_values) if upload_values else 0
                upload_stddev = (sum((x - upload_avg) ** 2 for x in upload_values) / (len(upload_values) - 1)) ** 0.5 if len(upload_values) > 1 else 0
                
                download_ratios = overhead_data[size]["download"]
                download_overhead = sum(download_ratios) / len(download_ratios) if download_ratios else 0
                
                upload_ratios = overhead_data[size]["upload"]
                upload_overhead = sum(upload_ratios) / len(upload_ratios) if upload_ratios else 0
                
                writer.writerow([size, f"{download_avg:.2f}", f"{download_stddev:.2f}", 
                                f"{upload_avg:.2f}", f"{upload_stddev:.2f}",
                                f"{download_overhead:.4f}", f"{upload_overhead:.4f}"])
        
        print(f"\nDetailed results saved to {table_path}")

if __name__ == "__main__":
    try:
        import aiofiles
    except ImportError:
        print("Installing required package: aiofiles")
        os.system(f"{sys.executable} -m pip install aiofiles")
        import aiofiles
    
    asyncio.run(main())