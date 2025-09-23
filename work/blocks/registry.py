from django.core.handlers.wsgi import WSGIRequest


class BlockRegistry:
    def __init__(self):
        self._blocks = []

    def register(self, block_cls):
        instance = block_cls()
        self._blocks.append(instance)
        self._blocks.sort(key=lambda b: getattr(b, 'order', 0))
        return block_cls

    def get_visible_blocks(self, request: WSGIRequest):
        for block in self._blocks:
            if block.is_visible(request):
                yield block

    def clear(self):
        self._blocks.clear()


block_registry = BlockRegistry()
