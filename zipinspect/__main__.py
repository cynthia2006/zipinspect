import sys
import time

from zipfile import ZipFile, ZipInfo

from tabulate import tabulate

from .http import HTTPRandom
from .pages import PaginatedCollection
from .repl import parse_args


def zipinfo_time_to_iso8601(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", t + (0, 0, -1))

def numfmt_iec(n):
    for u in 'BKMG':
        if abs(n) < 1024.0:
            return f'{n:3.1f}{u}'
        n /= 1024.0

if __name__ == "__main__":
    with (HTTPRandom(sys.argv[1]) as handle, ZipFile(handle, 'r') as z):
        infos = PaginatedCollection(z.infolist())

        while True:
            try:
                args = parse_args(input('> '))
            except EOFError:
                break

            if len(args) < 1:
                continue

            match args[0]:
                case 'list':
                    def zipinfo_to_row(info: ZipInfo):
                        size = numfmt_iec(info.file_size) if not info.is_dir() else 'N/A'
                        timestamp = zipinfo_time_to_iso8601(info.date_time)

                        return info.filename, size, timestamp

                    page = [(index, *zipinfo_to_row(info))
                            for index, info in enumerate(infos.current(),
                                                         start=infos.current_offset)]

                    print(tabulate(page, headers=['#', 'entry', 'size', 'modified date']))
                case 'prev':
                    infos.previous()
                case 'next':
                    infos.next()
                case 'extract':
                    if len(args) < 2:
                        print("ERROR: No index provided; retry.")
                        continue

                    ilist = z.infolist()
                    index = int(args[1])

                    if 0 <= index <= len(ilist):
                        info = infos.seq[index]

                        if info.is_dir():
                            for info1 in ilist:
                                if info1.filename.startswith(info.filename):
                                    z.extract(info1)

                        else:
                            z.extract(infos.seq[index])
                    else:
                        print(f"ERROR: Index out of bounds, max {len(ilist)}")

