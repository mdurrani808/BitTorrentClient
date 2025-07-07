# BitTorrent Client
- This is a Python-based BitTorrent client built from scratch using `asyncio`. It supports tracker communication, peer-to-peer file downloading, SHA-1 piece verification, and interoperability with official  BitTorrent clients!

## Features
- communicates with the tracker over HTTP (supports compact peer format)
- Downloads from both official and custom BitTorrent clients
- Supports incoming and outgoing peer connections
- Handles message protocol (handshake, bitfield, request, piece, have)
- Periodically refreshes peers from the tracker
- Visual progress bar with real-time updates
- Optional tracker scrape for seed/leecher info

## Setup Instructions
1. Clone the Repo
2. Create and activate virtual env (macOS):
    - python3 -m venv venv
    - source venv/bin/activate  
3. install dependencies
    - pip3 install -r requirements.txt

## Run the Client in the SRC directory
- python3 main.py --port_num 6881 --torrent_file /path/to/file.torrent --file_path /path/to/save/file/ [--compact] [--peer ip:port]

## --peer argument 
- This argument is for direct peer2peer testing. It will hardcode the peer into the peer_list the client receives, so that it only leeches from this peer. 

## Tracker Scrape
- If the tracker supports scraping, the client will prompt you to scrape after parsing the .torrent file. You can decide y/n to scrape or proceed to downloading directly 

## Progress Bar
- The terminal progress bar will display the progress of the downloading
- When the progress bar hits 100.0 percent, it will state download complete along with the download rate [kB/s or mB/s]

## Leeching -> Seeding
- After completeing the download, the client keeps connections open and responds to incoming peer requests. Basic piece sharing is supported, but full seeding behavior such as optimistic unchoking, upload prioritization, etc., is not implemented. 

## Testing 
- python3 main.py --port_num 4321 --torrent_file ./../torrents/flatland-http.torrent --file_path ./../resources/ --compact
- python3 main.py --port_num 6882  --torrent_file ./../torrents/flatland-http.torrent --file_path ./../downloads/  --peer 127.0.0.1:6881
- python3 main.py --port_num 6881 --torrent_file ./../torrents/Unigine_Superposition-1.1.exe.torrent --file_path ./../downloads/
- python3 main.py --port_num 6881 --torrent_file ./../torrents/ubuntu-24.04.2-desktop-amd64.iso.torrent --file_path ./../downloads/
