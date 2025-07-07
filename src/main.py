import random
import argparse
import asyncio
import sys
import time
import tqdm
from torrent import Torrent
from tracker import Tracker
from piece_manager import PieceManager
from torrent_client import TorrentClient
from message import MessageType

BLOCK_SIZE = 16384
KEEP_ALIVE_INTERVAL = 120
PEER_REFRESH_INTERVAL = 300

class DownloadProgressBar:
    def __init__(self, total_size: int):
        self.progress_bar = tqdm.tqdm(
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            desc="Downloading",
            bar_format='{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'
        )
        self.last_downloaded = 0

    def update(self, downloaded: int):
        delta = downloaded - self.last_downloaded
        if delta > 0:
            self.progress_bar.update(delta)
            self.last_downloaded = downloaded

    def close(self):
        self.progress_bar.close()

async def keep_alive_loop(torrent_client):
    while True:
        try:
            now = time.time()
            for peer_id, peer in torrent_client.peerObjects.items():
                if peer.has_handshaked and now - peer.last_sent > KEEP_ALIVE_INTERVAL:
                    try:
                        await peer.send_message(peer.writer, -1)
                    except Exception as e:
                        print(f"Error sending keep-alive: {e}")
        except Exception as e:
            print(f"Error in keep-alive loop: {e}")
        await asyncio.sleep(30)

async def refresh_peers(tracker: Tracker, torrent_client: TorrentClient, piece_manager: PieceManager):
    metrics = piece_manager.get_metrics()
    updated_peers, interval = await tracker.announce(
        uploaded=metrics["uploaded"],
        downloaded=metrics["downloaded"],
        left=metrics["left"],
        compact=True
    )

    current_peers = torrent_client.get_peer_connections()
    new_peers = []
    for peer in updated_peers:
        peer_id = peer[2] if peer[2] else (peer[0], peer[1])
        if peer_id not in current_peers:
            new_peers.append(peer)

    if new_peers:
        await torrent_client.start_downloading(new_peers)

    return interval

async def maintain_peer_list(tracker: Tracker, torrent_client: TorrentClient, piece_manager: PieceManager):
    if(torrent_client.port != 1234):
        while True:
            try:
                interval = await refresh_peers(tracker, torrent_client, piece_manager)
                await asyncio.sleep(min(interval, PEER_REFRESH_INTERVAL))
            except Exception as e:
                print(f"Error refreshing peers: {e}")
                await asyncio.sleep(60)

async def update_progress(piece_manager, progress_bar):
    while True:
        metrics = piece_manager.get_metrics()
        progress_bar.update(metrics["downloaded"])
        if metrics["left"] == 0:
            progress_bar.close()
            print("\nDownload complete!")
            # sys.exit(0)
            return
        await asyncio.sleep(0.5)

async def main():
    # parse cli for torrent file path, client port num
    parser = argparse.ArgumentParser()
    parser.add_argument("--file_path", type=str, help="folder you want to save downloaded file at, with leading slash", required=True) # Required parameter
    parser.add_argument("--port_num", type=int, help="port number you want the client to listen on", required=True)
    parser.add_argument("--torrent_file", type=str, help="path to the torrent file", required=True)
    parser.add_argument("--peer", type=str, help="peer in ip:port format (for direct testing)", default=None)
    parser.add_argument("--compact", action="store_true", help="enable compact mode")
    args = parser.parse_args()

    print("File Path:", args.file_path)

    test_file = args.torrent_file

    # parse through torrent file 
    torrent = Torrent(test_file)
    print("Torrent Tracker URL:", torrent.getTrackerURL())
    print("Torrent File Size:", torrent.getFileSize())
    print("Torrent Piece Length:", torrent.getPieceLen())

    if(not args.peer):
        client_id = '-PY0001-' + ''.join([str(random.randint(0, 9)) for _ in range(12)])
    else:
        client_id = '-PY0001-' + ''.join([str(0) for _ in range(12)])

    piece_manager = PieceManager(
        block_size=BLOCK_SIZE,
        hashes=torrent.getPieces(),
        filepath=f"{args.file_path}{torrent.getFileName()}",
        total_length=torrent.getFileSize(),
        piece_length=torrent.getPieceLen()
    )

    progress_bar = DownloadProgressBar(torrent.getFileSize())

    tracker = Tracker(
        peer_id=client_id,
        client_port=args.port_num,
        info_hash=torrent.getInfoHash(),
        tracker_url=torrent.getTrackerURL(),
        tracker_port=torrent.getTrackerPort()
    )

    if torrent.canScrape():
        while True:
            sendScrape = input("Would you like to scrape the tracker? (y/n): ")
            if sendScrape == 'y':
                try:
                    info = await tracker.scrape()
                except:
                    print("Could not scrape, moving to download...")
                    break
                for key, val in info.items():
                    data = val
                print(f'Peers with entire file: {data[b"complete"]}')
                print(f"Registered completions: {data[b'downloaded']}")
                print(f"Number of leechers: {data[b'incomplete']}")
                while True:
                    moveToDownload = input("Would you like to continue to download? (y/n): ")
                    if moveToDownload == 'y':
                        break
                    elif moveToDownload == 'n':
                        print("Goodbye...")
                        sys.exit(0)
                break
                
            elif sendScrape == 'n':
                print("Moving to downloading...")
                break
    
    if args.peer:
        ip, port = args.peer.split(":")
        peers = [(ip, int(port), "manual-peer")]
        interval = 9999
    else:
        peers, interval = await tracker.announce(
            uploaded=0,
            downloaded=0,
            left=torrent.getFileSize(),
            compact=args.compact
        )

    torrent_client = TorrentClient(
        info_hash=torrent.getInfoHash(),
        my_id=client_id,
        pieceManager = piece_manager,
        listen_port=args.port_num
    )

    for peer in peers:
        print(f"{peer[0], peer[1], peer[2]}")

    try:
        await asyncio.gather(
            torrent_client.run(peers),
            update_progress(piece_manager, progress_bar),
            maintain_peer_list(tracker, torrent_client, piece_manager),
            keep_alive_loop(torrent_client)
        )
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        progress_bar.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")