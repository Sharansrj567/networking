from flask import Flask, request, Response
import time
import bencodepy
import ipaddress
import struct

app = Flask(__name__)

# Track active peers (info_hash -> list of peers)
peers = {}

@app.route("/announce")
def announce():
    # Extract announce parameters
    info_hash = request.args.get("info_hash", "")
    peer_id = request.args.get("peer_id", "")
    port = request.args.get("port", "6881")
    uploaded = request.args.get("uploaded", "0")
    downloaded = request.args.get("downloaded", "0")
    left = request.args.get("left", "0")
    event = request.args.get("event", "")
    
    # Get peer IP - use X-Real-IP header if available (behind proxy) or remote_addr
    ip = request.headers.get('X-Real-IP', request.remote_addr)
    
    # Initialize peer list for this info_hash if needed
    if info_hash not in peers:
        peers[info_hash] = {}
        
    # Update peer information
    peer_key = f"{ip}:{port}"
    peers[info_hash][peer_key] = {
        'ip': ip,
        'port': int(port),
        'peer_id': peer_id,
        'last_seen': time.time(),
        'left': int(left)
    }
    
    # Remove old peers (more than 30 minutes old)
    now = time.time()
    for ih in list(peers.keys()):
        for pk in list(peers[ih].keys()):
            if now - peers[ih][pk]['last_seen'] > 1800:  # 30 minutes
                del peers[ih][pk]
        if not peers[ih]:
            del peers[ih]
    
    # Count seeders and leechers
    seeders = sum(1 for p in peers.get(info_hash, {}).values() if p['left'] == 0)
    leechers = len(peers.get(info_hash, {})) - seeders
    
    # Prepare response
    response_dict = {
        b"interval": 60,  # More frequent updates for testing
        b"min interval": 30,
        b"complete": seeders,
        b"incomplete": leechers,
    }
    
    # Create compact peer list
    peer_data = bytearray()
    for peer in peers.get(info_hash, {}).values():
        # Skip self
        if peer['ip'] == ip and int(peer['port']) == int(port):
            continue
            
        try:
            # Convert IP string to binary
            ip_bytes = ipaddress.IPv4Address(peer['ip']).packed
            port_bytes = struct.pack(">H", peer['port'])
            peer_data.extend(ip_bytes + port_bytes)
        except Exception as e:
            print(f"Error adding peer {peer['ip']}:{peer['port']}: {e}")
    
    response_dict[b"peers"] = bytes(peer_data)
    
    print(f"Tracker request from {ip}:{port} for infohash {info_hash[:10]}...")
    print(f"Returning {len(peer_data)//6} peers, {seeders} seeders, {leechers} leechers")
    
    encoded = bencodepy.encode(response_dict)
    return Response(encoded, mimetype="text/plain")

@app.route("/")
def index():
    # Simple status page
    peer_count = sum(len(p) for p in peers.values())
    torrent_count = len(peers)
    return f"<h1>BitTorrent Tracker</h1><p>Active torrents: {torrent_count}</p><p>Active peers: {peer_count}</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)