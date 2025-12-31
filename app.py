import errno
import glob
import gzip
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Union, cast

import click
from flask import Flask, render_template
from flask_socketio import SocketIO
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Type alias to keep signatures shorter and within line-length limits
SkipSid = Optional[Union[str, List[str]]]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "secret!")

# Configure basic logging for the application
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Create a small typed wrapper delegating to the real Flask-SocketIO
class SocketIOLike(Protocol):
    def emit(
        self,
        event: str,
        *args: Any,
        namespace: str = "/",
        to: Optional[str] = None,
        include_self: bool = True,
        skip_sid: Optional[Union[str, List[str]]] = None,
        callback: Optional[Callable[..., Any]] = None,
    ) -> None: ...

    def start_background_task(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any: ...

    def on(self, event: str) -> Any: ...

    def run(
        self,
        app: Any,
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        debug: bool = True,
        use_reloader: bool = False,
        reloader_options: Optional[Dict[str, Any]] = None,
        log_output: bool = True,
        allow_unsafe_werkzeug: bool = False,
        **kwargs: Any,
    ) -> None: ...


_raw_socketio: SocketIOLike = cast(
    SocketIOLike, SocketIO(app, cors_allowed_origins="*")
)  # actual instance (cast to Protocol for Pylance)


class SocketIOWrapper:
    """Typed wrapper delegating to _raw_socketio.

    This helps editors and type-checkers resolve commonly used methods
    like `emit`, `on`, `start_background_task`, and `run`.
    """

    def __init__(self, inner: SocketIOLike) -> None:
        self._inner: SocketIOLike = inner

    def emit(
        self,
        event: str,
        *args: Any,
        namespace: str = "/",
        to: Optional[str] = None,
        include_self: bool = True,
        skip_sid: SkipSid = None,
        callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        # Forward args/kwargs to the real SocketIO.emit
        self._inner.emit(
            event,
            *args,
            namespace=namespace,
            to=to,
            include_self=include_self,
            skip_sid=skip_sid,
            callback=callback,
        )

    def start_background_task(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        return self._inner.start_background_task(func, *args, **kwargs)

    def on(self, event: str) -> Any:
        return self._inner.on(event)

    def run(
        self,
        app: Any,
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        debug: bool = True,
        use_reloader: bool = False,
        reloader_options: Optional[Dict[str, Any]] = None,
        log_output: bool = True,
        allow_unsafe_werkzeug: bool = False,
        **kwargs: Any,
    ) -> None:
        """Run the wrapped SocketIO server, forwarding all supported kwargs.

        The signature mirrors Flask-SocketIO's `run` to keep editors and type
        checkers happy and to accept any future keyword options.
        """
        self._inner.run(
            app,
            host=host,
            port=port,
            debug=debug,
            use_reloader=use_reloader,
            reloader_options=reloader_options or {},
            log_output=log_output,
            allow_unsafe_werkzeug=allow_unsafe_werkzeug,
            **kwargs,
        )


socketio: SocketIOWrapper = SocketIOWrapper(_raw_socketio)

# Specify your logs directory via environment variable or default
LOGS_DIRECTORY = os.environ.get("ANSIBLE_LOGS_DIR", "/var/log/ansible")
# Initial port to try when starting the server.
# Can be overridden with the env var INITIAL_PORT
INITIAL_PORT = int(os.environ.get("INITIAL_PORT", "5000"))
# How many consecutive ports to try before giving up.
# Can be overridden with the env var MAX_PORT_TRIES
MAX_PORT_TRIES = int(os.environ.get("MAX_PORT_TRIES", "20"))


class LogFileHandler(FileSystemEventHandler):
    def _src_path_to_str(self, src_path: Any) -> str:
        """Return a decoded `str` for src_path which may be bytes-like.

        Handle `bytes` and `bytearray` directly and treat `memoryview`
        explicitly using `tobytes()` to avoid leaving a
        `memoryview[Unknown]` argument type in downstream checks that some
        language servers report as partially unknown.
        """
        # bytes-like objects need explicit decoding
        if isinstance(src_path, (bytes, bytearray)):
            return src_path.decode()
        if isinstance(src_path, memoryview):
            # Use tobytes() which returns concrete bytes
            return src_path.tobytes().decode()
        # Guarantee we return a str
        return src_path if isinstance(src_path, str) else str(src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = self._src_path_to_str(event.src_path)
        if src.endswith((".log", ".gz")):
            self.emit_log_files()

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_path_str = self._src_path_to_str(event.src_path)
        if not src_path_str.endswith(".log"):
            return
        filename: str = os.path.basename(src_path_str)
        # For simplicity we send the whole file content in this version.
        # We could optimize this to send only new lines if needed.
        content: str = read_file_content(src_path_str)
        socketio.emit(
            "file_content",
            {"name": filename, "content": content},
        )

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = self._src_path_to_str(event.src_path)
        if src.endswith(".log") or src.endswith(".gz"):
            self.emit_log_files()

    def emit_log_files(self) -> None:
        log_files: List[Dict[str, str]] = get_log_files()
        socketio.emit("file_list", log_files)


def read_file_content(filepath: str) -> str:
    try:
        if filepath.endswith(".gz"):
            # Read gz in binary and decode explicitly to avoid Any return types
            with gzip.open(filepath, "rb") as file:
                raw: bytes = file.read()
                return raw.decode("utf-8", errors="replace")
        else:
            with open(
                filepath,
                "r",
                encoding="utf-8",
                errors="replace",
            ) as file:
                return file.read()
    except Exception as e:
        # Keep the error short and safe for returning to clients
        return f"Error reading file: {e}"


def monitor_logs() -> None:
    if not os.path.exists(LOGS_DIRECTORY):
        logger.warning("Directory %s does not exist.", LOGS_DIRECTORY)
        return

    observer = Observer()
    event_handler = LogFileHandler()
    observer.schedule(event_handler, LOGS_DIRECTORY, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


@app.route("/")
def index() -> Any:
    return render_template("index.html")


def get_log_files() -> List[Dict[str, str]]:
    if not os.path.exists(LOGS_DIRECTORY):
        return []

    files: List[str] = []
    for extension in ("*.log", "*.gz"):
        files.extend(glob.glob(os.path.join(LOGS_DIRECTORY, extension)))

    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)

    log_files: List[Dict[str, str]] = []
    for f in files:
        if os.path.isfile(f):
            log_files.append({"name": os.path.basename(f)})
    return log_files


@socketio.on("connect")
def handle_connect() -> None:
    log_files = get_log_files()
    socketio.emit("file_list", log_files)


@socketio.on("get_file_content")
def handle_get_file_content(data: Dict[str, Any]) -> None:
    filename = data.get("name")
    if not filename:
        return

    filepath = os.path.join(LOGS_DIRECTORY, filename)
    # Security check to prevent directory traversal
    abs_filepath = os.path.abspath(filepath)
    abs_logs_dir = os.path.abspath(LOGS_DIRECTORY)
    if not abs_filepath.startswith(abs_logs_dir):
        socketio.emit("file_content_error", {"message": "Invalid file path"})
        return

    content = read_file_content(filepath)
    socketio.emit("file_content", {"name": filename, "content": content})


def run_server_with_retries(
    host: str = "0.0.0.0",
    start_port: int = INITIAL_PORT,
    max_tries: int = MAX_PORT_TRIES,
) -> None:
    """Try to find a free port by attempting a simple bind before
    starting the server.

    This avoids a failure happening in a background thread inside the
    WSGI server (which would not be caught by an exception raised inside
    socketio.run).
    """
    import socket

    def port_is_free(h: str, p: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((h, p))
            s.close()
            return True
        except OSError as e:
            if getattr(e, "errno", None) == errno.EADDRINUSE:
                return False
            raise

    port = start_port
    for attempt in range(max_tries):
        logger.info("Checking port %d", port)
        logger.info("(attempt %d/%d)", attempt + 1, max_tries)
        if port_is_free(host, port):
            # Log short messages (keeps line lengths compact)
            logger.info("Port %d appears free", port)
            logger.info("Starting server on %s:%d", host, port)
            # Disable the reloader to avoid duplicate start attempts from the
            # automatic watchdog/reloader which can spawn extra processes.
            socketio.run(
                app,
                host=host,
                port=port,
                debug=True,
                use_reloader=False,
            )
            return
        else:
            logger.info("Port %d already in use", port)
            logger.info("Trying %d", port + 1)
            port += 1

    logger.error("Failed to bind to any port in range %d-%d", start_port, port)
    raise SystemExit(1)


@click.command()
@click.option(
    "--initial-port",
    "-p",
    type=int,
    default=None,
    help="Initial port to try (overrides env INITIAL_PORT)",
)
@click.option(
    "--max-port-tries",
    "-m",
    type=int,
    default=None,
    help="How many consecutive ports to try (overrides env MAX_PORT_TRIES)",
)
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--debug/--no-debug", default=True, help="Run with Flask debug")
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="INFO",
    help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
)
def main(
    initial_port: Optional[int],
    max_port_tries: Optional[int],
    host: str,
    debug: bool,
    log_level: str,
) -> None:
    """Run the server. Options override environment variables."""
    # Resolve values: CLI > ENV defaults
    start_port = initial_port if initial_port is not None else INITIAL_PORT
    tries = max_port_tries if max_port_tries is not None else MAX_PORT_TRIES

    # Configure log level from the CLI option
    level_name = (log_level or "INFO").upper()
    numeric_level = getattr(logging, level_name, logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    logger.info("Log level set to %s", level_name)

    logger.info(
        (
            "Starting server with host=%s",
            " initial_port=%d",
            " max_port_tries=%d",
            " debug=%s",
        ),
        host,
        start_port,
        tries,
        debug,
    )

    # Start watcher background task
    socketio.start_background_task(monitor_logs)
    # Start server. run_server_with_retries performs a short bind-check.
    run_server_with_retries(host=host, start_port=start_port, max_tries=tries)


if __name__ == "__main__":
    main()
