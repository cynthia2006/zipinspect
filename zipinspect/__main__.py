import asyncio
import os.path
import time

import click
import tabulate

from .zipread import HTTPZipReader
from .utils import TaskQueue, PaginatedCollection
from .repl import parse_args

def zipinfo_time_to_iso8601(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", t + (0, 0, -1))

def numfmt_iec(n):
    for u in 'BKMG':
        if abs(n) < 1024.0:
            return f'{n:3.1f}{u}'
        n /= 1024.0

def sanitized_open(path, **kwargs):
    path = os.path.abspath(path)
    if os.path.commonpath((path, os.getcwd())) != os.getcwd():
        raise UnsafePathError(path)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, **kwargs)

class UnsafePathError(Exception):
    def __init__(self, path):
        self.path = path
        
        super().__init__()

async def amain(url):
    async with HTTPZipReader(url) as z:
        infos = PaginatedCollection(z.entries)

        while True:
            try:
                args = parse_args(input('> '))
            except EOFError:
                break

            if len(args) < 1:
                continue

            match args[0]:
                case 'list':
                    def zipinfo_to_row(info):
                        size = numfmt_iec(info.file_size) if not info.is_dir else 'N/A'
                        timestamp = zipinfo_time_to_iso8601(info.modified_date)

                        return info.path, size, timestamp

                    page = [(index, *zipinfo_to_row(info))
                            for index, info in enumerate(infos.current(),
                                                         start=infos.current_offset)]

                    print(tabulate.tabulate(page, headers=['#', 'entry', 'size', 'modified date']))
                case 'prev':
                    infos.previous()
                case 'next':
                    infos.next()
                case 'extract':
                    # TODO Implement a method of specifying path.
                    if len(args) < 2:
                        print("ERROR: No index provided; retry.")
                        continue

                    ilist = z.entries
                    index = int(args[1])

                    if 0 <= index <= len(ilist):
                        info = infos.seq[index]

                        async def download_job(info):
                            with sanitized_open(info.path, mode='wb') as output:
                                await z.extract(info, output)

                        try:
                            if info.is_dir:
                                async with TaskQueue(maxsize=10) as tg:
                                    for info1 in ilist:
                                        if info1.path.startswith(info.path) and not info1.is_dir:
                                            tg.create_task(download_job(info1))

                            else:
                                await download_job(info)
                        except UnsafePathError as e:
                            print(f"Path {e.path} is potentially dangerous, not proceeding.")
                    else:
                        print(f"ERROR: Index out of bounds, max {len(ilist)}")

                case wrong_cmd:
                    print(f'Not a valid command {wrong_cmd}; try again.')

@click.command()
@click.argument('url')
def main(url):
    asyncio.run(amain(url), debug=True)

if __name__ == "__main__":
    main()

