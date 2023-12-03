import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from ltorrent.client import Client

if __name__ == '__main__':
    torrent_path = "examples/example.torrent"
    port = 8080

    client = Client(
        port=port
    )
    
    client.load(torrent_path=torrent_path)
    client.select_file()
    client.run()
