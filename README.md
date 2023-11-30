
# LTorrent
A pure python torrent client based on PyTorrent

- Pure Python client.
- Based on [gallexis/PyTorrent](https://github.com/gallexis/PyTorrent).
- Support torrent file and magnet link.
- Scrape `udp` or `http` trackers with multiple thread.
- Connect to peers with multiple thread.
- Support custome storage.
- Support file selection.

## Todo
- Download more than one torrent at a time.
- Pause and resume download.
- Scrape peers while downloading.
- Accept new peers while downloading.

## Dependencies
```sh
pipenv install
```

## Start
### Run demo
```sh
pipenv run python main.py
```
