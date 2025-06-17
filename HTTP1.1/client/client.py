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

class HTTP1Client:
    def __init__(self, server_url):
        self.server_url = server_url
        self.client = httpx.AsyncClient(verify=False,
                                        limits=httpx.Limits(max_connections=1))
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
        
    async def download_file(self, filename: str):
        """
        Download a file from server via GET request
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
        Upload a file to server via POST request
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
        
        transfer_func = self.download_file if prefix == "A" else self.upload_file
        
        for i in range(repetitions):
            print(f"Transfer {i+1}/{repetitions} for {filename}")
            try:
                result = await transfer_func(filename)
                results.append(result)
                print(f"  Throughput: {result['throughput']/1024:.2f} KB/s")
            except Exception as e:
                print(f"Error transferring {filename}: {e}")
            await asyncio.sleep(0.1)
        
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
    parser = argparse.ArgumentParser(description="HTTP/1.1 File Transfer Client")
    parser.add_argument("--server", required=True, help="Server URL (e.g., https://192.168.1.2:8000)")
    args = parser.parse_args()
    
    async with HTTP1Client(args.server) as client:
        response = await client.client.get(f"{args.server}/list")
        if hasattr(response, "http_version"):
            version = response.http_version
        else:
            version = "HTTP/1.1"
        print(f"Connected using {version}")
        if version != "HTTP/1.1":
            print("WARNING: Not using HTTP/1.1!")
        
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
        
        print("\n========== HTTP/1.1 THROUGHPUT (kilobits per second) ==========")
        print("File Size | Download Avg | Download StdDev | Upload Avg | Upload StdDev")
        print("---------|--------------|-----------------|------------|------------")
        
        for size in ["10kB", "100kB", "1MB", "10MB"]:
            d_values = throughput_data[size]["download"]
            if d_values:
                d_avg = sum(d_values) / len(d_values)
                d_std = (sum((x - d_avg) ** 2 for x in d_values) / (len(d_values) - 1)) ** 0.5 if len(d_values) > 1 else 0
            else:
                d_avg, d_std = 0, 0
            
            u_values = throughput_data[size]["upload"]
            if u_values:
                u_avg = sum(u_values) / len(u_values)
                u_std = (sum((x - u_avg) ** 2 for x in u_values) / (len(u_values) - 1)) ** 0.5 if len(u_values) > 1 else 0
            else:
                u_avg, u_std = 0, 0
                
            print(f"{size} | {d_avg:.2f} | {d_std:.2f} | {u_avg:.2f} | {u_std:.2f}")
        
        print("\n========== HTTP/1.1 OVERHEAD RATIO ==========")
        print("File Size | Download | Upload")
        print("---------|----------|-------")
        for size in ["10kB", "100kB", "1MB", "10MB"]:
            d_ratios = overhead_data[size]["download"]
            d_overhead = sum(d_ratios) / len(d_ratios) if d_ratios else 0
            
            u_ratios = overhead_data[size]["upload"]
            u_overhead = sum(u_ratios) / len(u_ratios) if u_ratios else 0
            
            print(f"{size} | {d_overhead:.4f} | {u_overhead:.4f}")
        
        table_path = RESULTS_DIR / "http1_table_data.csv"
        with open(table_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "File Size", "Download Avg (kbps)", "Download StdDev",
                "Upload Avg (kbps)", "Upload StdDev", "Download Overhead", "Upload Overhead"
            ])
            for size in ["10kB", "100kB", "1MB", "10MB"]:
                d_values = throughput_data[size]["download"]
                d_avg = sum(d_values) / len(d_values) if d_values else 0
                d_std = (sum((x - d_avg) ** 2 for x in d_values) / (len(d_values) - 1)) ** 0.5 if len(d_values) > 1 else 0
                
                u_values = throughput_data[size]["upload"]
                u_avg = sum(u_values) / len(u_values) if u_values else 0
                u_std = (sum((x - u_avg) ** 2 for x in u_values) / (len(u_values) - 1)) ** 0.5 if len(u_values) > 1 else 0
                
                d_ratios = overhead_data[size]["download"]
                d_overhead = sum(d_ratios) / len(d_ratios) if d_ratios else 0
                u_ratios = overhead_data[size]["upload"]
                u_overhead = sum(u_ratios) / len(u_ratios) if u_ratios else 0
                
                writer.writerow([
                    size, f"{d_avg:.2f}", f"{d_std:.2f}",
                    f"{u_avg:.2f}", f"{u_std:.2f}",
                    f"{d_overhead:.4f}", f"{u_overhead:.4f}"
                ])
        
        print(f"\nDetailed results saved to {table_path}")

if __name__ == "__main__":
    try:
        import aiofiles
    except ImportError:
        print("Installing required package: aiofiles")
        os.system(f"{sys.executable} -m pip install aiofiles")
        import aiofiles
    asyncio.run(main())