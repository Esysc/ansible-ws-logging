from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import gzip
import os
import time

app = Flask(__name__)
socketio = SocketIO(app)

# Specify your logs directory
LOGS_DIRECTORY = '/var/log/ansible'

existing_files = set(os.listdir(LOGS_DIRECTORY))

class LogFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.log') or event.src_path.endswith('.gz'):
            self.emit_log_files()

    def on_modified(self, event):
        if event.src_path.endswith('.log'):
            filename = os.path.basename(event.src_path)
            with open(event.src_path, 'r') as file:
                content = file.read()
            # Emit the updated content to all connected clients
            socketio.emit('file_content', {'name': filename, 'content': content})

    def on_deleted(self, event):
        if event.src_path.endswith('.log') or event.src_path.endswith('.gz'):
            self.emit_log_files()

    def emit_log_files(self):
        log_files = get_log_files()
        # Emit the updated list of log files to all connected clients
        socketio.emit('file_list', log_files)

def monitor_logs():
    observer = Observer()
    event_handler = LogFileHandler()
    observer.schedule(event_handler, LOGS_DIRECTORY, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)  # Keep the thread alive
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

@app.route('/')
def index():
    return render_template('index.html')

def get_log_files():
    log_files = []
    for filename in os.listdir(LOGS_DIRECTORY):
        if filename.endswith('.log') or filename.endswith('.gz'):
            log_files.append({'name': filename})
    return log_files

@socketio.on('connect')
def handle_connect():
    log_files = get_log_files()
    emit('file_list', log_files)

@socketio.on('get_file_content')
def handle_get_file_content(data):
    filename = data['name']
    filepath = os.path.join(LOGS_DIRECTORY, filename)
    try:
        with open(filepath, 'r') as file:
            content = file.read()
    except:
        with gzip.open(filepath, 'rt') as file:
            content = file.read()
    emit('file_content', {'name': filename, 'content': content})

if __name__ == '__main__':
    # Start the log monitoring in a separate thread
    socketio.start_background_task(monitor_logs)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
