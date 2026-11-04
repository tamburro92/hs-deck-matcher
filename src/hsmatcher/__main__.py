import sys
from .server import serve

if __name__ == "__main__":
    serve(open_browser="--no-open" not in sys.argv)
