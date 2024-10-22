# Real-Time Ansible Logs Viewer

This Flask application captures and displays real-time logs from Ansible playbook executions in a web browser. By utilizing Flask-SocketIO, the app streams log output directly to connected clients, providing an interactive and live view of the Ansible execution process.

## Features

- **Real-Time Log Streaming**: View logs as they are generated during Ansible playbook execution.
- **User-Friendly Interface**: Simple and intuitive web interface for monitoring logs.
- **WebSocket Support**: Efficiently handles real-time data transmission using Flask-SocketIO.

## Installation

To set up the project locally, follow these steps:

1. **Clone the repository**:
```bash
   git clone https://github.com/Esysc/ansible-ws-logging
```
2. **Navigate to the project directory**:
```bash
cd ansible-ws-logging
```
3. **Create a virtual environment** (optional but recommended):
```bash
python3.12 -m venv virtualenv
source virtualenv/bin/activate  # On Windows use venv\Scripts\activate
```
4. **Install the required dependencies**:
```bash
pip install -r requirements.txt
```

## Usage
1. **Start the Flask application**:
```bash
python app.py
```
2. **Open your web browser and navigate to**: `http://<hostname>:5000`

**NOTE**: the root Ansible logs directory is set to `/var/log/ansible`, change it following your path or change the ansible.cfg configuration.


