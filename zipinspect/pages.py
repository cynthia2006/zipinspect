from typing import Collection, Any, Sequence


class PaginatedCollection:
    def __init__(self, seq: Sequence[Any], *, page_size = 25):
        self.seq = seq
        self.current_page = 0
        self.n_pages = len(seq) // page_size + 1
        self.page_size = page_size

    def previous(self):
        """Seek to previous page; wrap around if at first page."""
        if self.current_page == 0:
            self.current_page = self.n_pages
        else:
            self.current_page -= 1

    def next(self):
        """Seek to next page; wrap around if at last page."""
        if self.current_page == self.n_pages-1:
            self.current_page = 0
        else:
            self.current_page += 1

    @property
    def current_offset(self):
        return self.current_page * self.page_size

    def current(self) -> Collection[Any]:
        return self.index(self.current_page)

    def index(self, page: int) -> Sequence[Any]:
        if 0 <= page <= self.n_pages:
            begin = page * self.page_size
            end = (page + 1) * self.page_size

            return self.seq[begin:end]
        else:
            raise ValueError("Page index out of bounds")