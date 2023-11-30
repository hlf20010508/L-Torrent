import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from ltorrent.client import Client

if __name__ == '__main__':
    magnet_link = "your-magnet-link"
    port = 8080
    timeout = 1

    client = Client(
        port,
        magnet_link=magnet_link,
        timeout=timeout,
    )
    client.start()
