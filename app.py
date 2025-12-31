# Ensure eventlet monkey-patching happens as early as possible when available.
# Apply the patch via a small helper module so flake8 doesn't report
# "module level import not at top of file" when monkey_patch runs.
import errno
import glob
import gzip
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Protocol, Union, cast

import click
from flask import Flask, render_template
from flask_socketio import SocketIO
from watchdog.events import FileSystemEvent, FileSystemEventHandler

import patch_eventlet  # noqa: F401

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

    def sleep(self, seconds: float) -> None: ...

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
)


class SocketIOWrapper:
    """Typed wrapper delegating to _raw_socketio."""

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

    def sleep(self, seconds: float) -> None:
        try:
            getattr(self._inner, "sleep")(seconds)
        except Exception:
            import time

            time.sleep(seconds)


socketio: SocketIOWrapper = SocketIOWrapper(_raw_socketio)

# Log a message that the playbook's wait_for task can detect
logger.info("Starting server on 127.0.0.1 (via gunicorn/eventlet)")

# Specify your logs directory via environment variable or default
LOGS_DIRECTORY = os.environ.get("ANSIBLE_LOGS_DIR", "/var/log/ansible")
INITIAL_PORT = int(os.environ.get("INITIAL_PORT", "5000"))
MAX_PORT_TRIES = int(os.environ.get("MAX_PORT_TRIES", "20"))


class LogFileHandler(FileSystemEventHandler):
    def _src_path_to_str(self, src_path: Any) -> str:
        if isinstance(src_path, (bytes, bytearray)):
            return src_path.decode()
        if isinstance(src_path, memoryview):
            return src_path.tobytes().decode()
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
        content: str = read_file_content(src_path_str)
        socketio.emit("file_content", {"name": filename, "content": content})

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
        return f"Error reading file: {e}"


def monitor_logs() -> None:
    """Pure Eventlet-compatible poller - NO watchdog, NO blocking FS ops."""
    if not os.path.exists(LOGS_DIRECTORY):
        logger.warning("Directory %s does not exist.", LOGS_DIRECTORY)
        return

    poll_interval = 2.0  # Less aggressive polling
    mtimes: Dict[str, float] = {}
    event_handler = LogFileHandler()

    def snapshot_files() -> List[str]:
        """Non-blocking file list using os.listdir instead of glob."""
        try:
            return [
                os.path.join(LOGS_DIRECTORY, f)
                for f in os.listdir(LOGS_DIRECTORY)
                if f.endswith((".log", ".gz"))
            ]
        except OSError:
            return []

    # Initial snapshot (non-blocking)
    for f in snapshot_files():
        try:
            mtimes[f] = os.path.getmtime(f)
        except OSError:
            pass

    logger.info("monitor_logs started (pure Eventlet poller)")

    while True:  # Let Gunicorn manage shutdown
        try:
            current_files = set(snapshot_files())

            # Detect new/removed files
            new_files = [f for f in current_files if f not in mtimes]
            removed_files = [f for f in list(mtimes) if f not in current_files]

            if new_files or removed_files:
                for f in new_files:
                    try:
                        mtimes[f] = os.path.getmtime(f)
                    except OSError:
                        mtimes[f] = 0.0
                for f in removed_files:
                    mtimes.pop(f, None)
                event_handler.emit_log_files()
                logger.debug(
                    "File list updated: +%d -%d",
                    len(new_files),
                    len(removed_files),
                )

            # Detect modified files (most important)
            for f in list(current_files):
                try:
                    mtime = os.path.getmtime(f)
                    old_mtime = mtimes.get(f)
                    if old_mtime is None or mtime > old_mtime:
                        mtimes[f] = mtime
                        filename = os.path.basename(f)
                        content = read_file_content(f)
                        socketio.emit(
                            "file_content",
                            {"name": filename, "content": content},
                        )
                        logger.debug("Emitted update for %s", filename)
                except OSError:
                    mtimes.pop(f, None)

        except Exception as e:
            logger.exception("Error in monitor_logs: %s", e)

        socketio.sleep(poll_interval)  # Yields to Eventlet event loop


@app.route("/")
def index() -> Any:
    return render_template("index.html")


def get_log_files() -> List[Dict[str, str]]:
    if not os.path.exists(LOGS_DIRECTORY):
        return []

    files: List[str] = []
    for extension in ("*.log", "*.gz"):
        files.extend(glob.glob(os.path.join(LOGS_DIRECTORY, extension)))
    files.sort(key=os.path.getmtime, reverse=True)

    log_files: List[Dict[str, str]] = []
    for f in files:
        if os.path.isfile(f):
            log_files.append({"name": os.path.basename(f)})
    return log_files


_monitor_started = False


@socketio.on("connect")
def handle_connect() -> None:
    global _monitor_started
    if not _monitor_started:
        try:
            socketio.start_background_task(monitor_logs)
            logger.info("monitor_logs started on connect (worker)")
        except Exception as e:
            logger.exception("Failed to start monitor_logs on connect: %s", e)
        _monitor_started = True

    log_files = get_log_files()
    socketio.emit("file_list", log_files)


@socketio.on("get_file_content")
def handle_get_file_content(data: Dict[str, Any]) -> None:
    filename = data.get("name")
    if not filename:
        return

    filepath = os.path.join(LOGS_DIRECTORY, filename)
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
        logger.info(
            "Checking port %d (attempt %d/%d)",
            port,
            attempt + 1,
            max_tries,
        )
        if port_is_free(host, port):
            logger.info(
                "Port %d free, starting server on %s:%d",
                port,
                host,
                port,
            )
            socketio.run(
                app,
                host=host,
                port=port,
                debug=True,
                use_reloader=False,
            )
            return
        port += 1

    logger.error("Failed to bind to any port in range %d-%d", start_port, port)
    raise SystemExit(1)


@click.command()
@click.option("--initial-port", "-p", type=int, default=None)
@click.option("--max-port-tries", "-m", type=int, default=None)
@click.option("--host", default="0.0.0.0")
@click.option("--debug/--no-debug", default=True)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="INFO",
)
def main(
    initial_port: Optional[int],
    max_port_tries: Optional[int],
    host: str,
    debug: bool,
    log_level: str,
) -> None:
    start_port = initial_port if initial_port is not None else INITIAL_PORT
    tries = max_port_tries if max_port_tries is not None else MAX_PORT_TRIES
    level_name = (log_level or "INFO").upper()
    numeric_level = getattr(logging, level_name, logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    logger.info("Log level set to %s", level_name)
    msg = (
        f"Starting server with host={host} initial_port={start_port} "
        f"max_port_tries={tries} debug={debug}"
    )
    logger.info(msg)

    socketio.start_background_task(monitor_logs)
    run_server_with_retries(host=host, start_port=start_port, max_tries=tries)


if __name__ == "__main__":
    main()
