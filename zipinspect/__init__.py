import asyncio
import os.path
import sys
import textwrap
import time

from tabulate import tabulate
from progress.bar import Bar
from aioconsole import ainput

from .zipread import HTTPZipReader

from .utils.asyncio import TaskPool
from .utils.misc import PaginatedCollection


def dostime_to_rfc3339(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", t + (0, 0, -1))

def numfmt_iec(n):
    for u in 'BKMG':
        if abs(n) < 1024.0:
            return f'{n:3.1f}{u}'
        n /= 1024.0

def sanitized_open(path, *args, **kwargs):
    path = os.path.abspath(path)
    if os.path.commonpath((path, os.getcwd())) != os.getcwd():
        print(f"WARNING: Path {path} is dangerous; ignoring")
        return None

    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, *args, **kwargs)

def parse_repl_args(line):
    """Space delimited argument parser like the shell, but minimal."""
    parsed = []
    accum = ''
    escape = False
    quote = False

    for i, token in enumerate(line):
        if quote:
            if escape:
                if token in '\\"':
                    accum += token
                    escape = False
                else:
                    print(f"ERROR: Cannot escape {token} at column {i}")
            else:
                if token == '\\':
                    escape = True
                elif token == '"':
                    quote = False # Quote end
                else:
                    accum += token
        else:
            # Only append if accum is not empty
            if token == ' ' and accum != '':
                parsed.append(accum)
                accum = '' # Reset
            elif token == '"':
                quote = True # Quote start
            else:
                accum += token

    # Push the last argument
    if accum:
        parsed.append(accum)

    return parsed

async def extract_entries(z, entries, *, out_dir=None, concurrency=10):
    async def extract_entry(entry, *, progress_cb):
        final_path = f'{out_dir}/{entry.path}' if out_dir else entry.path

        if not (output := sanitized_open(final_path, 'wb')):
            return

        # NOTE Multiple running async-for loops (i.e. async generators) are cumbersome,
        # and thus to make matters manageable we use the good 'ol callbacks instead.
        with output:
            async for processed in z.extract(entry, output):
                progress_cb(processed)


    async with TaskPool(maxsize=concurrency) as pool:
        visited_dirs = set()
        total_tx = 0
        coros = set()
        bar = None

        # Non-obvious control flow: by the time this function is called, `bar' would've been defined.
        # This style of programming -- relying on global state -- is considered bad practice, but here
        # this saves us the burden of not introducing one more asyncio.Task in the task pool.
        def increment_done(n):
            bar.next(n)

        for info in entries:
            if info.is_dir:
                # Recursing into directories
                if info.path not in visited_dirs:
                    visited_dirs.add(info.path)

                    for nested_info in z.entries:
                        if (not nested_info.is_dir and
                                nested_info.path.startswith(info.path)):
                            coros.add(extract_entry(nested_info, progress_cb=increment_done))
                            total_tx += nested_info.file_size

            else: # Single files
                if os.path.dirname(info.path) not in visited_dirs:
                    coros.add(extract_entry(info, progress_cb=increment_done))
                    total_tx += info.file_size

        bar = Bar(max=total_tx, width=80, suffix='%(percent)d%%')
        for coro in coros:
            pool.create_task(coro)
        bar.finish()


def print_entries(pages):
    def zipinfo_to_row(info):
        size = numfmt_iec(info.file_size) \
            if not info.is_dir else 'N/A'
        timestamp = dostime_to_rfc3339(info.modified_date)

        return info.path, size, timestamp

    page = [(i, *zipinfo_to_row(info))
            for i, info in enumerate(pages.current(),
                                     start=pages.current_offset)]

    print(tabulate(page, headers=['#', 'entry', 'size', 'modified date']))
    print(f"(Page {pages.current_page + 1}/{pages.n_pages})")

def int_safe(v, *args, **kwargs):
    try:
        iv = int(v, *args, **kwargs)
    except ValueError:
        iv = None

        if v == '...':
            print("ERROR: Ellipsis (...) is used in a wrong way", file=sys.stderr)
        else:
            print(f"ERROR: {v!r} is not an integer value", file=sys.stderr)

    return iv

async def app(url):
    async with HTTPZipReader(url) as z:
        pages = PaginatedCollection(z.entries)

        while True:
            try:
                args = parse_repl_args(await ainput("> "))
            except EOFError:
                break

            # Skip empty prompts.
            if len(args) < 1:
                continue

            match args[0]:
                case 'help':
                    print(textwrap.dedent("""\
                          This is the REPL, and the following commands are available.
                          
                          list                            List entries in the current page
                          prev                            Go backward one page and show entries
                          next                            Go forward one page and show entries
                          extract <index> [dir]           Extract entry with index <index>
                          extract <start>,...,<end> [dir] Extract entries from <start> to <end>
                          extract <i0>,<i1>,...<in> [dir] Extract entries with specified indices
                          
                          NOTE: The extract command accepts an optinal path to the directory to extract into.
                          If not provided, it extracts into the current working directory"""))
                case 'list':
                    print_entries(pages)
                case 'prev':
                    pages.previous()
                    print_entries(pages)
                case 'next':
                    pages.next()
                    print_entries(pages)
                case 'extract':
                    if len(args) < 2:
                        print("ERROR: Nothing to extract, forgot an argument?", file=sys.stderr)
                        continue

                    indices = args[1].split(',')
                    out_dir = None

                    if len(args) > 2:
                        out_dir = args[2]

                    if len(indices) == 1:
                        start = int_safe(indices[0])
                        if start is None:
                            continue

                        if not 0 <= start < len(z.entries):
                            print(f"ERROR: Index {start} is out of bounds", file=sys.stderr)
                            continue

                        await extract_entries(z, (z.entries[start],), out_dir=out_dir)
                    else:
                        if len(indices) == 3 and indices[1] == '...':
                            start, end = int_safe(indices[0]), int_safe(indices[2])

                            if start is None or end is None:
                                continue
                            if not(0 <= start < end < len(z.entries)):
                                print(f"ERROR: Range {start},...,{end} is out of bounds", file=sys.stderr)
                                continue

                            await extract_entries(z, z.entries[start:end], out_dir=out_dir)
                        else:
                            # Filter out invalid and out-of-bounds indices
                            entries = [z.entries[iv] for s in indices
                                                     if (iv := int_safe(s)) is not None and 0 <= iv < len(z.entries)]
                            await extract_entries(z, entries, out_dir=out_dir)

                    # FIXME For some reason, Bar.finish() doesn't end with a newline.
                    sys.stdout.write('\n\n')
                case wrong_cmd:
                    print(f"ERROR: Not a valid command {wrong_cmd}; try again.", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        print("Forgot thy URL?", file=sys.stderr)

    asyncio.run(app(sys.argv[1]), debug=True)
