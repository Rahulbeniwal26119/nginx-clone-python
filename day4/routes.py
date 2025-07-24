from collections import namedtuple

Route = namedtuple("Route", ["path", "handler_function"])

handlers = {}

def bind_handler(path):
    def decorator(handler_function):
        handlers[path] = Route(path=path, handler_function=handler_function)
        return handler_function
    return decorator


def get_handler(path):
    """Get the handler function by path."""
    route = handlers.get(path)
    return route.handler_function if route else None

