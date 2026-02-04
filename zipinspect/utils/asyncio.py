from asyncio import TaskGroup, Semaphore

class TaskPool(TaskGroup):
    def __init__(self, *, maxsize):
        self._semaphore = Semaphore(maxsize)
        super().__init__()

    def create_task(self, coro, **kwargs):
        async def wrapper_coro():
            await self._semaphore.acquire()
            try:
                result = await coro
            finally:
                self._semaphore.release()

            return result

        return super().create_task(wrapper_coro(), **kwargs)

