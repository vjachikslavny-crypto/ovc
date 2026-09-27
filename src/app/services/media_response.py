"""Use Starlette's streaming implementation; normalize malformed byte ranges to 416."""
import os
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import FileResponse as BaseFileResponse, Response, MalformedRangeHeader, RangeNotSatisfiable


class FileResponse(BaseFileResponse):
    async def __call__(self, scope, receive, send):
        if scope['method'] == 'HEAD':
            scope = dict(scope, headers=[(k,v) for k,v in scope['headers'] if k.lower() != b'range'])
        headers = Headers(scope=scope)
        value = headers.get('range')
        if value and scope['method'] != 'HEAD':
            stat = self.stat_result or await run_in_threadpool(os.stat, self.path)
            try:
                if len(value) > 1024 or value.count(',') > 15:
                    raise MalformedRangeHeader()
                self._parse_range_header(value, stat.st_size)
            except (MalformedRangeHeader, RangeNotSatisfiable, ValueError):
                return await Response(status_code=416, headers={
                    'Content-Range':f'bytes */{stat.st_size}', 'Accept-Ranges':'bytes',
                    'X-Content-Type-Options':'nosniff'})(scope, receive, send)
        return await super().__call__(scope, receive, send)
