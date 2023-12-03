from traceback import print_exc
from io import StringIO

class LoggerMustException(Exception):
    pass

class LoggerBase:
    def __init__(self, *args):
        pass

    async def ERROR(self, *args):
        pass

    async def WARNING(self, *args):
        pass

    async def INFO(self, *args):
        pass

    async def DEBUG(self, *args):
        pass

    async def PROGRESS(self, *args):
        pass

    async def MUST(self, *args):
        raise LoggerMustException


class Logger(LoggerBase):
    def __init__(self):
        LoggerBase.__init__(self)
    
    async def ERROR(self, *args):
        buffer = StringIO()
        print_exc(file=buffer)
        print("ERROR:", *args)
        print(buffer.getvalue())
        with open('log', 'a+') as file:
            file.write(' '.join(map(str, args)) + '\n')
            file.write(buffer.getvalue() + '\n')

    
    async def WARNING(self, *args):
        print("WARNING:", *args)
        
    async def INFO(self, *args):
        print("INFO:", *args)

    async def DEBUG(self, *args):
        print("DEBUG:", *args)
    
    async def PROGRESS(self, *args):
        print("PROGRESS:", *args)

    async def MUST(self, *args):
        print(*args)
