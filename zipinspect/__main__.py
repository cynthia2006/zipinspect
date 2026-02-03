import asyncio
import os.path
import time

import click
import tabulate
from tqdm import tqdm

from .zipread import HTTPZipReader
from .utils.asyncio import TaskQueue
from .utils.misc import PaginatedCollection
from .utils.repl import parse_args

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
        infopages = PaginatedCollection(z.entries)

        while True:
            try:
                args = parse_args(input('> '))
            except EOFError:
                break

            if len(args) < 1:
                continue

            def print_entries():
                def zipinfo_to_row(info):
                    size = numfmt_iec(info.file_size) if not info.is_dir else 'N/A'
                    timestamp = zipinfo_time_to_iso8601(info.modified_date)

                    return info.path, size, timestamp

                page = [(i, *zipinfo_to_row(info))
                        for i, info in enumerate(infopages.current(),
                                                     start=infopages.current_offset)]

                print(tabulate.tabulate(page, headers=['#', 'entry', 'size', 'modified date']))
                print(f"(Page {infopages.current_page + 1}/{infopages.n_pages})")

            async def download_job(info):
                with (sanitized_open(info.path, mode='wb') as output,
                      tqdm(desc=os.path.basename(info.path),
                           total=info.file_size, unit='B', unit_scale=True) as pbar):
                    async for processed in z.extract(info, output):
                        pbar.update(processed)

            match args[0]:
                case 'help':
                    print("This is the REPL, and the following commands are available.\n"
                          "\n"
                          "list                     List entries in the current page\n"
                          "prev                     Go backward one page, and list\n"
                          "next                     Go forward one page, and list\n"  
                          "extract <index>          Extract entry with index <index>\n"   
                          "extract <start>[-<end>]  Extract entires from <start> upto end")
                case 'list':
                    print_entries()
                case 'prev':
                    infopages.previous()
                    print_entries()
                case 'next':
                    infopages.next()
                    print_entries()
                case 'extract':
                    # TODO Implement a method of specifying path.
                    if len(args) < 2:
                        print("ERROR: No index provided; retry.")
                        continue

                    ilist = z.entries
                    index = args[1].split('-')

                    start = int(index[0])
                    if len(index) > 1:
                        end = int(index[1] or len(ilist))
                    else:
                        end = start + 1

                    if 0 <= start < len(ilist) and start < end <= len(ilist):
                        async with TaskQueue(maxsize=10) as tg:
                            for info in ilist[start:end]:
                                try:
                                    if info.is_dir:
                                        for info1 in ilist:
                                            if info1.path.startswith(info.path) and not info1.is_dir:
                                                tg.create_task(download_job(info1))

                                    else:
                                        tg.create_task(download_job(info))
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

