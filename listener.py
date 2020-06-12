#!/usr/bin/env python3
import os
import sys
import stat
import socket
import json
import pycriu
import psutil
import subprocess

if (os.getuid() != 0):
    print('Please run with sudo.')
    sys.exit(1)

SCIUNIT_HOME = os.path.expanduser('~/sciunit/')
SCIUNIT_PROJECT_FILE = os.path.join(SCIUNIT_HOME, '.activated')
SCIUNIT_SOCKET_FILE = os.path.join(SCIUNIT_HOME, 'listener.socket')

try:
    os.unlink(SCIUNIT_SOCKET_FILE)
except OSError:
    if os.path.exists(SCIUNIT_SOCKET_FILE):
        raise

# Check CRIU
if not os.path.exists('/var/run/criu_service.socket'):
    pid = os.fork()
    if (pid == 0):
        subprocess.call(['criu', 'service', '-d', '--address', '/var/run/criu_service.socket'])
        sys.exit(0)

# Launch Notebook
pid = os.fork()
if (pid == 0):
    existing = False
    if (os.path.exists(SCIUNIT_PROJECT_FILE)):
        project = open(SCIUNIT_PROJECT_FILE).read().strip()
        project_name = os.path.basename(os.path.normpath(project))
        if (os.path.exists(os.path.join(project, 'kernel'))):
            existing = True
    if existing:
        criu_path = os.path.join(project, 'criu0')
        subprocess.call(['criu', 'restore', '--link-remap', '--tcp-established', '--shell-job', '-D', criu_path])
    else:
        uid, gid = os.getenv('SUDO_UID'), os.getenv('SUDO_GID')
        if not uid: uid = 0
        if not gid: gid = 0
        os.setgid(int(gid))
        os.setuid(int(uid))
        subprocess.call(['jupyter', 'notebook'])
    sys.exit(0)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SCIUNIT_SOCKET_FILE)
os.chmod(SCIUNIT_SOCKET_FILE, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

def kill_fds(pid):
    proc = psutil.Process(pid)
    files = proc.open_files()
    for f in files:
        print(f)
        if os.path.exists(f.path):
            os.unlink(f.path)
    conns = proc.connections()
    for conn in conns:
        if conn.fd != 6 and conn.status != 'LISTEN':
            subprocess.call(['ss', '-K',
                             'src', f'{conn.laddr.ip}',
                             'sport', '=', f'{conn.laddr.port}',
                             'dst', f'{conn.raddr.ip}',
                             'dport', '=', f'{conn.raddr.port}'], stdout=subprocess.DEVNULL)

while True:
    server.listen(1)
    conn, addr = server.accept()
    data = json.loads(conn.recv(1024).decode())
    
    op, pid, ppid, criu_path, jid = data
    
    criu = pycriu.criu()
    criu.use_sk('/var/run/criu_service.socket')
    criu.opts.leave_running = True
    criu.opts.tcp_established = True
    criu.opts.shell_job = True
    criu.opts.track_mem = True
    criu.opts.link_remap = True
    criu.opts.tcp_skip_in_flight = True
    
    
    if op == 'Dump':
        kill_fds(pid)
        kill_fds(ppid)
        
        criu.opts.pid = ppid
        
        os.mkdir(criu_path)
        criu_fd = os.open(criu_path, os.O_DIRECTORY)
        criu.opts.images_dir_fd = criu_fd
        if jid > 0:
            criu.opts.parent_img = f'../criu{jid - 1}'.encode()
        criu.dump()
        os.close(criu_fd)
    elif op == 'Restore':
        os.kill(pid, 9)
        os.kill(ppid, 9)
        pid = os.fork()
        if (pid == 0):
            subprocess.call(['criu', 'restore', '--link-remap', '--tcp-established', '--shell-job', '-D', criu_path])
            sys.exit(0)
        # criu_fd = os.open(criu_path, os.O_DIRECTORY)
        # criu.opts.images_dir_fd = criu_fd
        # criu.restore()