import datetime
from request import Request
from routes import bind_handler
from response import http_response


@bind_handler("/hello")
def hello_handler(req: Request):
    return http_response("<h1>Hello, World!</h1>", 200, "text/html")


@bind_handler("/")
def root_handler(req: Request):
    return http_response("Welcome to the nginx clone", 200, "text/plain")

@bind_handler("/time")
def time_handler(req: Request):
    # Let's change the time handler to also return the query_params so we know if they are working
    return http_response(
        {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query_params": req.query_params,
        }
    )

_ = ...  # placeholder for dummy import