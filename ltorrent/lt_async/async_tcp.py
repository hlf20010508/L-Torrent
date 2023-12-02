import asyncio

class AsyncTCPClient:
    def __init__(self):
        self.host = ''
        self.port = 0
        self.timeout = 1
        self.reader = None
        self.writer = None

    async def create_connection(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)

    async def send(self, msg):
        if not isinstance(msg, bytes):
            msg = msg.encode()
        if self.writer is not None:
            self.writer.write(msg)
            await asyncio.wait_for(self.writer.drain(), self.timeout)
        else:
            raise Exception("AsyncTCPClient not connected yet.")

    async def recv(self, buffer_size=-1):
        if self.reader is not None:
            data = await asyncio.wait_for(self.reader.read(buffer_size), timeout=self.timeout)
            return data
        else:
            raise Exception("AsyncTCPClient not connected yet.")

    async def close(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
        else:
            raise Exception("AsyncTCPClient not connected yet.")
