
# LTorrent
A pure python torrent client based on PyTorrent

- Pure Python client.
- Based on [gallexis/PyTorrent](https://github.com/gallexis/PyTorrent).
- Support [torrent file](#torrent-file) and [magnet link](#magnet-link).
- Scrape `udp` or `http` trackers with multiple thread.
- Connect to peers with multiple thread.
- Support [custom storage](https://github.com/hlf20010508/LTorrent/tree/master/examples/custom_storage.py).
- Support file selection.
- Support custom [stdout](https://github.com/hlf20010508/LTorrent/tree/master/examples/custom_stdout.py).
- Support [running as a thread](#run-as-a-thread).
- Support [asynchrony](#asynchrony).
- Support [sequential download](https://github.com/hlf20010508/LTorrent/tree/master/examples/sequential.py).

See examples [here](https://github.com/hlf20010508/LTorrent/tree/master/examples).

## Todo
- Download more than one torrent at a time.
- Pause and resume download.
- Scrape peers while downloading.
- Accept new peers while downloading.

## File Selection
Input number of files, seperated by `Space`, eg: `2 5 7`.

Range supported, linked by `-`, eg: `4 6-10 12 14-20`.

## Installation
### ltorrent
pip
```sh
pip install git+https://github.com/hlf20010508/LTorrent.git@1.6.0#subdirectory=ltorrent
```
pipenv
```sh
pipenv install "ltorrent@ git+https://github.com/hlf20010508/LTorrent.git@1.6.0#subdirectory=ltorrent"
```

### ltorrent_async
pip
```sh
pip install git+https://github.com/hlf20010508/LTorrent.git@1.6.0#subdirectory=ltorrent_async
```
pipenv
```sh
pipenv install "ltorrent_async@ git+https://github.com/hlf20010508/LTorrent.git@1.6.0#subdirectory=ltorrent_async"
```

## Start
### Run Demo
```sh
pipenv install
pipenv run python demo.py
```

### Torrent File
```py
from ltorrent.client import Client

torrent_path = "your-torrent-path"
port = 8080

client = Client(
    port=port
)

client.load(torrent_path=torrent_path)
client.list_file()
selection = input("Select file: ")
client.select_file(selection=selection)
client.run()
```

### Magnet Link
```py
from ltorrent.client import Client

magnet_link = "your-magnet-link"
port = 8080

client = Client(
    port=port
)

client.load(magnet_link=magnet_link)
client.list_file()
selection = input("Select file: ")
client.select_file(selection=selection)
client.run()
```

### Run as a Thread
```py
from ltorrent.client import Client

magnet_link = "your-magnet-link"
port = 8080

client = Client(
    port=port
)

client.load(magnet_link=magnet_link)
client.list_file()
selection = input("Select file: ")
client.select_file(selection=selection)
client.start()
```

### Asynchrony
```py
from ltorrent_async.client import Client

async def main():
    magnet_link = "your-magnet-link"
    port = 8080

    client = Client(
        port=port,
    )

    await client.load(magnet_link=magnet_link)
    await client.list_file()
    selection = input("Select file: ")
    await client.select_file(selection=selection)
    await client.run()

if __name__ == '__main__':
    asyncio.run(main())
```
