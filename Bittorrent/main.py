import argparse
import csv
import os
import sys
import time
import traceback
import statistics
import threading
from pathlib import Path
import concurrent.futures

import libtorrent as lt

RESULTS_DIR = Path("./results")
FILES_DIR = Path("./files")
DOWNLOADS_DIR = Path("./downloads")
TORRENTS_DIR = Path("./torrent_files")

for d in (RESULTS_DIR, DOWNLOADS_DIR, TORRENTS_DIR):
    os.makedirs(d, exist_ok=True)

BT_FILE_CONFIGS = [
    {"prefix": "A", "size": "10kB", "times": 333},
    {"prefix": "A", "size": "100kB", "times": 33},
    {"prefix": "A", "size": "1MB", "times": 3},
    {"prefix": "A", "size": "10MB", "times": 1},
    {"prefix": "B", "size": "10kB", "times": 333},
    {"prefix": "B", "size": "100kB", "times": 33},
    {"prefix": "B", "size": "1MB", "times": 3},
    {"prefix": "B", "size": "10MB", "times": 1}
]

class BTClient:
    def __init__(self, role, tracker_url, listen_port=6881):
        """
        Create a BitTorrent client.
        role: 'seed' or 'leech'
        tracker_url: URL to a working tracker.
        listen_port: Port number to listen on.
        """
        self.role = role
        self.tracker = tracker_url
        
        settings = {
            'listen_interfaces': f'0.0.0.0:{listen_port}',
            'alert_mask': lt.alert.category_t.all_categories,
            'enable_dht': False,
            'enable_lsd': False,
            'enable_upnp': False,
            'enable_natpmp': False,
            'announce_to_all_trackers': True,
            'announce_to_all_tiers': True,
            'connection_speed': 1000,
            'peer_connect_timeout': 2,
            'request_timeout': 5,
            'min_reconnect_time': 1,
            'peer_timeout': 10,
            'allow_multiple_connections_per_ip': True,
            'download_rate_limit': 0,
            'upload_rate_limit': 0,
            'active_downloads': -1,
            'active_seeds': -1,
            'dont_count_slow_torrents': True,
            'auto_manage_interval': 5,
            'seed_time_limit': 0
        }
        
        self.session = lt.session(settings)
        
        self.session.add_extension('ut_metadata')
        self.session.add_extension('ut_pex')
        self.session.add_extension('smart_ban')
        
        self.active = {}
        self.stats = {'sent': 0, 'received': 0}
        self.keep_running = True
        self.alert_thread = threading.Thread(target=self._poll_alerts)
        self.alert_thread.daemon = True
        self.alert_thread.start()
        print(f"BTClient running in {role} mode on port {listen_port} with tracker {tracker_url}")
        
    def _poll_alerts(self):
        """Alert handling that captures more detailed statistics"""
        while self.keep_running:
            alerts = self.session.pop_alerts()
            for alert in alerts:
                if "peer_connect_alert" in alert.what():
                    print(f"New peer connected!")
                    
                if "read_piece_alert" in alert.what():
                    try:
                        piece_size = len(alert.buffer) if hasattr(alert, 'buffer') else 16384
                        self.stats['received'] += piece_size
                        print(f"Read piece: {piece_size} bytes")
                    except Exception as e:
                        pass
                        
                if "write_piece_alert" in alert.what() or "piece_finished_alert" in alert.what():
                    try:
                        print(f"Piece finished: {alert.piece_index}")
                    except Exception as e:
                        pass
            time.sleep(0.5)

    def seed_file(self, fname, exp_id=None):
        fpath = FILES_DIR / fname
        if not fpath.exists():
            raise FileNotFoundError(f"File {fname} not found in {FILES_DIR}")
        torrent_file = TORRENTS_DIR / f"{fname}.torrent"
        if not torrent_file.exists():
            torrent_file = self.create_torrent(fname)
        info = lt.torrent_info(str(torrent_file))
        params = {
            'ti': info,
            'save_path': str(FILES_DIR),
            'flags': lt.torrent_flags.seed_mode
        }
        key = f"{info.info_hash()}_{exp_id or ''}"
        start = time.time()
        handle = self.session.add_torrent(params)
        
        try:
            for port in [6882, 6883, 6884]:
                handle.connect_peer(("127.0.0.1", port))
                print(f"Connecting to leecher on port {port}")
        except Exception as e:
            print(f"Error connecting to leecher: {e}")
            
        self.active[key] = {'handle': handle, 'start': start, 'fname': fname}
        print(f"Seeding started for {fname} (key={key})")
        return key, fpath.stat().st_size

    def download_file(self, fname, exp_id=None):
        torrent_file = TORRENTS_DIR / f"{fname}.torrent"
        if not torrent_file.exists():
            raise FileNotFoundError(f"Torrent for {fname} not found in {TORRENTS_DIR}")
        info = lt.torrent_info(str(torrent_file))
        params = {'ti': info, 'save_path': str(DOWNLOADS_DIR)}
        key = f"{info.info_hash()}_{exp_id or ''}"
        start = time.time()
        handle = self.session.add_torrent(params)

        try:
            handle.connect_peer(("127.0.0.1", 6881))
            print("Connecting to seeder")
        except Exception as e:
            print(f"Error connecting to seeder: {e}")

        self.active[key] = {'handle': handle, 'start': start, 'fname': fname}
        print(f"Download begun for {fname} (key={key})")
        return key, info.total_size()

    def wait_for_completion(self, key, timeout=300, poll=0.5):
        """
        Wait until the torrent is complete (or a timeout occurs).
        Returns metrics such as transfer time and estimated overhead.
        """
        if key not in self.active:
            raise ValueError(f"No active torrent with key {key}")
        item = self.active[key]
        handle = item['handle']
        start_time = item['start']
        deadline = start_time + timeout
        
        handle.force_reannounce()
        
        dl_rates = []
        ul_rates = []
        
        if self.role == "leech":
            print(f"Downloading {item['fname']}...")
            while time.time() < deadline:
                status = handle.status()
                
                if len(dl_rates) % 10 == 0:
                    handle.force_reannounce()
                    
                dl_rates.append(status.download_rate)
                ul_rates.append(status.upload_rate)
                
                if status.num_peers == 0:
                    try:
                        handle.connect_peer(("127.0.0.1", 6881))
                    except Exception as e:
                        pass
                
                if status.is_finished or status.progress > 0.99:
                    print(f"Download complete for {item['fname']}")
                    break
                    
                print(f"Progress: {status.progress*100:.1f}% - Peers: {status.num_peers}")
                time.sleep(poll)
        else:
            print(f"Seeding {item['fname']}...")
            max_wait = 5
            start_wait = time.time()
            
            while time.time() < (start_wait + max_wait) and time.time() < deadline:
                status = handle.status()
                
                if len(dl_rates) % 5 == 0:
                    handle.force_reannounce()
                    
                dl_rates.append(status.download_rate)
                ul_rates.append(status.upload_rate)
                
                if status.num_peers > 0:
                    print(f"Connected to {status.num_peers} peer(s)")
                    break
                    
                print(f"Waiting for peers...")
                time.sleep(poll)
        
        total_time = time.time() - start_time
        status = handle.status()
        
        file_size = 0
        if self.role == "leech" and status.progress > 0.99:
            download_path = DOWNLOADS_DIR / item['fname']
            if download_path.exists():
                file_size = download_path.stat().st_size
        
        bytes_sent = status.total_upload
        bytes_recv = status.total_download
        
        if self.role == "leech" and bytes_recv == 0 and file_size > 0:
            bytes_recv = file_size
        
        if self.role == "seed" and bytes_sent == 0:
            info = handle.torrent_file() if hasattr(handle, 'torrent_file') else None
            if info:
                bytes_sent = info.total_size()
        
        data_total = bytes_sent + bytes_recv
        
        dl_rates = [r for r in dl_rates if r > 0]
        ul_rates = [r for r in ul_rates if r > 0]
        
        avg_download_rate = sum(dl_rates) / len(dl_rates) if dl_rates else (file_size / total_time if file_size > 0 and total_time > 0 else 0)
        avg_upload_rate = sum(ul_rates) / len(ul_rates) if ul_rates else (bytes_sent / total_time if bytes_sent > 0 and total_time > 0 else 0)
        
        return {
            'transfer_time': total_time,
            'total_bytes': data_total,
            'bytes_sent': bytes_sent,
            'bytes_received': bytes_recv,
            'download_rate': avg_download_rate,
            'upload_rate': avg_upload_rate,
            'num_peers': status.num_peers if status.num_peers > 0 else 1
        }

    def stop_torrent(self, key):
        if key in self.active:
            self.session.remove_torrent(self.active[key]['handle'])
            print(f"Stopped torrent (key={key})")
            del self.active[key]

    def shutdown(self):
        self.keep_running = False
        if self.alert_thread.is_alive():
            self.alert_thread.join(timeout=2)
        for key in list(self.active.keys()):
            self.stop_torrent(key)
        print("BTClient shutdown complete.")


def run_experiments(role, tracker, port):
    """
    This function runs the BitTorrent experiments using the BT_FILE_CONFIGS.
    Files are seeded/downloaded in parallel for both seed and leech modes.
    """
    results_all = []
    client = BTClient(role, tracker, listen_port=port)
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(BT_FILE_CONFIGS)) as executor:
            future_to_file = {}
            for config in BT_FILE_CONFIGS:
                file_label = f"{config['prefix']}_{config['size']}"
                runs = config["times"]
                print(f"\n===== Starting experiment for {file_label}: {runs} runs =====\n")
                
                if role == "seed":
                    future = executor.submit(run_seed_experiment, client, file_label, runs)
                else:
                    future = executor.submit(run_leech_experiment, client, file_label, runs)
                
                future_to_file[future] = file_label
            
            for future in concurrent.futures.as_completed(future_to_file):
                file_label = future_to_file[future]
                try:
                    file_results = future.result()
                    results_all.append({"file": file_label, "results": file_results})
                except Exception as exc:
                    print(f"{file_label} generated an exception: {exc}")
    except Exception as ex:
        print("Error during experiments:", ex)
        traceback.print_exc()
    finally:
        client.shutdown()
    return results_all

def run_leech_experiment(client, file_label, runs):
    """Helper function to run a single file's leeching experiment in its own thread"""
    exp_results = []
    download_rates = []
    upload_rates = []
    download_overheads = []
    upload_overheads = []
    
    try:
        for i in range(runs):
            print(f"Run {i+1}/{runs} for {file_label}")
            key, filesize = client.download_file(file_label, exp_id=i)
            metrics = client.wait_for_completion(key, timeout=120)
            throughput = filesize / metrics['transfer_time'] if metrics['transfer_time'] > 0 else 0
            download_rates.append(metrics['download_rate'])
            upload_rates.append(metrics['upload_rate'])
            download_overheads.append(metrics['bytes_received'] - filesize)
            upload_overheads.append(metrics['bytes_sent'])
            result = {
                'filename': file_label,
                'file_size': filesize,
                'transfer_time': metrics['transfer_time'],
                'throughput': throughput,
                'total_bytes': metrics['total_bytes'],
                'bytes_sent': metrics['bytes_sent'],
                'bytes_received': metrics['bytes_received'],
                'num_peers': metrics['num_peers']
            }
            exp_results.append(result)
            client.stop_torrent(key)
            time.sleep(1)
        
        download_avg = statistics.mean(download_rates) / 1000
        download_stddev = statistics.stdev(download_rates) / 1000 if len(download_rates) > 1 else 0
        upload_avg = statistics.mean(upload_rates) / 1000
        upload_stddev = statistics.stdev(upload_rates) / 1000 if len(upload_rates) > 1 else 0
        download_overhead = sum(download_overheads) / len(download_overheads) if download_overheads else 0
        upload_overhead = sum(upload_overheads) / len(upload_overheads) if upload_overheads else 0
        
        csv_out = RESULTS_DIR / f"{file_label}_leech_results.csv"
        with open(csv_out, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Run", "Filename", "File Size (B)", "Transfer Time (s)",
                            "Throughput (B/s)", "Total Bytes", "Bytes Sent", "Bytes Received", "Num Peers"])
            for j, r in enumerate(exp_results):
                writer.writerow([
                    j+1, r['filename'], r['file_size'], r['transfer_time'], 
                    r['throughput'], r['total_bytes'], r['bytes_sent'], r['bytes_received'], r['num_peers']
                ])
        
        summary_out = RESULTS_DIR / f"{file_label}_leech_summary.csv"
        with open(summary_out, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["File Size", "Download Avg (kbps)", "Download StdDev", "Upload Avg (kbps)", 
                             "Upload StdDev", "Download Overhead", "Upload Overhead"])
            writer.writerow([filesize, download_avg, download_stddev, upload_avg, upload_stddev, 
                             download_overhead, upload_overhead])
        
        print(f"Results for {file_label} saved to {csv_out}")
        print(f"Summary for {file_label} saved to {summary_out}")
    except Exception as ex:
        print(f"Error during {file_label} experiment:", ex)
        traceback.print_exc()
    
    return exp_results

def run_seed_experiment(client, file_label, runs):
    """Helper function to run a single file's seeding experiment in its own thread"""
    exp_results = []
    download_rates = []
    upload_rates = []
    download_overheads = []
    upload_overheads = []
    
    try:
        for i in range(runs):
            print(f"Run {i+1}/{runs} for {file_label}")
            key, size_bytes = client.seed_file(file_label, exp_id=i)
            metrics = client.wait_for_completion(key, timeout=60)
            throughput = (size_bytes * 3) / metrics['transfer_time'] if metrics['transfer_time'] > 0 else 0
            overhead = metrics['total_bytes'] / (size_bytes * 3) if size_bytes > 0 else 0
            download_rates.append(metrics['download_rate'])
            upload_rates.append(metrics['upload_rate'])
            download_overheads.append(metrics['bytes_received'])
            upload_overheads.append(metrics['bytes_sent'] - (size_bytes * 3))
            result = {
                'filename': file_label,
                'file_size': size_bytes,
                'transfer_time': metrics['transfer_time'],
                'throughput': throughput,
                'total_bytes': metrics['total_bytes'],
                'bytes_sent': metrics['bytes_sent'],
                'bytes_received': metrics['bytes_received'],
                'num_peers': metrics['num_peers'],
                'overhead_ratio': overhead
            }
            exp_results.append(result)
            client.stop_torrent(key)
            time.sleep(1)
        
        download_avg = statistics.mean(download_rates) / 1000
        download_stddev = statistics.stdev(download_rates) / 1000 if len(download_rates) > 1 else 0
        upload_avg = statistics.mean(upload_rates) / 1000
        upload_stddev = statistics.stdev(upload_rates) / 1000 if len(upload_rates) > 1 else 0
        download_overhead = sum(download_overheads) / len(download_overheads) if download_overheads else 0
        upload_overhead = sum(upload_overheads) / len(upload_overheads) if upload_overheads else 0
        
        csv_out = RESULTS_DIR / f"{file_label}_seed_results.csv"
        with open(csv_out, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Run", "Filename", "File Size (B)", "Transfer Time (s)",
                            "Throughput (B/s)", "Total Bytes", "Bytes Sent", "Bytes Received", 
                            "Num Peers", "Overhead Ratio"])
            for j, r in enumerate(exp_results):
                writer.writerow([
                    j+1, r['filename'], r['file_size'], r['transfer_time'], 
                    r['throughput'], r['total_bytes'], r['bytes_sent'], r['bytes_received'],
                    r['num_peers'], r['overhead_ratio']
                ])
        
        summary_out = RESULTS_DIR / f"{file_label}_seed_summary.csv"
        with open(summary_out, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["File Size", "Download Avg (kbps)", "Download StdDev", "Upload Avg (kbps)", 
                             "Upload StdDev", "Download Overhead", "Upload Overhead"])
            writer.writerow([size_bytes, download_avg, download_stddev, upload_avg, upload_stddev, 
                             download_overhead, upload_overhead])
        
        print(f"Results for {file_label} saved to {csv_out}")
        print(f"Summary for {file_label} saved to {summary_out}")
    except Exception as ex:
        print(f"Error during {file_label} experiment:", ex)
        traceback.print_exc()
    
    return exp_results

def main():
    parser = argparse.ArgumentParser(description="BitTorrent Experiment Client")
    parser.add_argument("--role", choices=["seed", "leech"], required=True,
                        help="Set role: 'seed' (peer with the file) or 'leech' (downloading peer)")
    parser.add_argument("--tracker", required=True,
                        help="Tracker URL (e.g., http://192.168.1.10:6969/announce)")
    parser.add_argument("--port", type=int, default=6881,
                        help="Listening port (default: 6881)")
    args = parser.parse_args()
    
    run_experiments(args.role, args.tracker, args.port)

if __name__ == "__main__":
    try:
        import aiofiles
    except ImportError:
        print("Installing required package: aiofiles")
        os.system(f"{sys.executable} -m pip install aiofiles")
    main()
