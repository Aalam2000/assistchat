# src/app/workers/base.py

class BaseWorker:
    def __init__(self, resource):
        self.resource = resource
        self.running = False

    async def start(self):
        self.running = True
        # TODO: инициализация

    async def stop(self):
        self.running = False
        # TODO: остановка процесса

    def check_ready(self) -> bool:
        # TODO: проверить готовность ресурса
        return True
