from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
import paramiko
import logging
import subprocess
from deploy_vm_handler2 import deploy_vm_route
from delete_vm import delete_vm_handler
import pandas as pd
#from werkzeug.utils import secure_filename


LOG_FILE = "vm_deploy.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

app = Flask(__name__)
app.secret_key = "supersecret"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "hv.db")

def get_db_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn



def init_db():
    conn = get_db_conn()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS hypervisors
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, ip TEXT, username TEXT, password TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS vms
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT, ip_addr INTEGER, subnetprefix INTEGER, vm_gateway INTEGER, hv_id INTEGER,
              cpu INTEGER, memory INTEGER, disk INTEGER,
              status TEXT, vm_type TEXT,
              FOREIGN KEY (hv_id) REFERENCES hypervisors(id))''')

    
    conn.commit()
    try:
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_vms_unique ON vms (name, hv_id)')
        conn.commit()
    except Exception:
        pass

    conn.close()


@app.route('/')
def index():
    return render_template("index.html")

def check_kvm(ip, username, password):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=10)
        
        stdin, stdout, stderr = ssh.exec_command("lsmod | grep kvm")
        output = stdout.read().decode().strip()
        ssh.close()
        
        return bool(output)
    except Exception as e:
        print(f"KVM check failed: {e}")
        return False

@app.route('/add_hv', methods=['GET', 'POST'])
def add_hv():
    if request.method == 'POST':
        name = request.form['name']
        ip = request.form['ip']
        username = request.form['username']
        password = request.form['password']

        if not check_kvm(ip, username, password):
            return "KVM not installed or not accessible on this host", 400
            
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("INSERT INTO hypervisors (name, ip, username, password) VALUES (?,?,?,?)",
                  (name, ip, username, password))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template("add_hv.html")

@app.route('/delete_hv', methods=['POST'])
def delete_hv():
    selected = request.form.getlist("selected_hvs")
    if not selected:
        flash("No Hypervisors selected for deletion!", "error")
        return redirect(url_for("dashboard"))

    for hv_info in selected:
        try:
            hv_id, hv_name = hv_info.split("::")
        except ValueError:
            flash(f"Invalid HV info: {hv_info}", "error")
            continue

        remove_hv_from_db(hv_id)

    flash("Selected Hypervisors removed successfully.", "success")
    return redirect(url_for("dashboard"))

def remove_hv_from_db(hv_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM hypervisors WHERE id=?", (hv_id,))
        conn.commit()
        conn.close()
        flash(f"Hypervisor {hv_id} removed from DB.", "success")
    except Exception as e:
        flash(f"Failed to remove HV {hv_id}: {e}", "error")


@app.route('/deploy_vm', methods=['GET', 'POST'])
def deploy_vm():
    return deploy_vm_route(request, render_template, redirect, url_for, flash)

@app.route('/delete_vm', methods=['POST'])
def delete_vm():
    selected = request.form.getlist("selected_vms")

    if not selected:
        flash("No VMs selected for deletion!", "error")
        return redirect(url_for("dashboard"))

    for vm_info in selected:
        try:
            vm_name, hv_ip = vm_info.split("::")
        except ValueError:
            flash(f"Invalid VM info: {vm_info}", "error")
            continue
        delete_vm_handler(vm_name, hv_ip)

    return redirect(url_for('dashboard'))


def get_hv_resources(ip, username, password):
    """Fetch hypervisor resources via SSH + virsh."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password, timeout=10)

        stdin, stdout, _ = ssh.exec_command("virsh nodeinfo")
        output = stdout.read().decode()
        hv_info = {}
        for line in output.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                hv_info[key.strip()] = value.strip()

        total_cpu = int(hv_info.get("CPU(s)", 0))
        total_mem = int(hv_info.get("Memory size", "0").split()[0]) // 1024 // 1024
        total_disk = 5000

        stdin, stdout, _ = ssh.exec_command("virsh list --name | grep -v guestfs")
        vms = [v.strip() for v in stdout.read().decode().splitlines() if v.strip()]

        used_cpu, used_mem = 0, 0
        for vm in vms:
            stdin, stdout, _ = ssh.exec_command(f"virsh dominfo {vm}")
            dominfo = stdout.read().decode()
            if not dominfo.strip():
                continue
            vm_cpu, vm_mem = 0, 0
            for line in dominfo.splitlines():
                if "CPU(s)" in line and not "CPU time" in line:
                    vm_cpu = int(line.split(":")[1].strip())
                elif line.strip().startswith("Max memory:"):
                    vm_mem = int(line.split(":")[1].strip().split()[0]) // 1024 // 1024

            used_cpu += vm_cpu
            used_mem += vm_mem
        ssh.close()

        return total_cpu, total_mem, total_disk, used_cpu, used_mem

    except Exception as e:
        print(f"[WARN] Could not fetch HV resources from {ip}: {e}")
        return 0, 0, 0, 0, 0


def sync_vms_from_hv(hv_id, hv_ip, hv_user, hv_pass):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hv_ip, username=hv_user, password=hv_pass)

    stdin, stdout, stderr = ssh.exec_command("virsh list --name")
    vm_list = [vm.strip() for vm in stdout.readlines() if vm.strip()]

    conn = get_db_conn()
    c = conn.cursor()

    for vm in vm_list:
        cpu, memory, disk = 0, 0, 0

        stdin, stdout, stderr = ssh.exec_command(f"virsh dominfo {vm}")
        dominfo = stdout.read().decode()
        for line in dominfo.splitlines():
            if line.startswith("CPU(s):"):
                cpu = int(line.split(":")[1].strip())
            if line.startswith("Max memory:"):
                memory = int(line.split(":")[1].strip().split()[0]) // 1024 // 1024

        stdin, stdout, stderr = ssh.exec_command(f"virsh domblklist {vm} --details")
        blk_lines = stdout.read().decode().splitlines()
        for line in blk_lines:
            if "disk" in line and ".qcow2" in line:
                parts = line.split()
                if len(parts) >= 4:
                    disk_file = parts[3]
                    stdin2, stdout2, stderr2 = ssh.exec_command(f"virsh domblkinfo {vm} {disk_file}")
                    info = stdout2.read().decode()
                    disk = 0
                    for l in info.splitlines():
                        if l.startswith("Capacity:"):
                            disk = int(l.split()[1]) // (1024 ** 3)
                            break
        c.execute(
            "SELECT id FROM vms WHERE name=? AND hv_id=?", (vm, hv_id)
        )
        row = c.fetchone()
        if row:
            c.execute(
                "UPDATE vms SET cpu=?, memory=?, disk=? WHERE id=?",
                (cpu, memory, disk, row[0]),
            )
        else:
            c.execute(
                "INSERT INTO vms (name, hv_id, cpu, memory, disk) VALUES (?, ?, ?, ?, ?)",
                (vm, hv_id, cpu, memory, disk),
            )

    conn.commit()
    conn.close()
    ssh.close()

def refresh_vm_status(hv_ip, hv_user, hv_pass, hv_id):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hv_ip, username=hv_user, password=hv_pass, timeout=10)

    conn = get_db_conn()
    c = conn.cursor()

    c.execute("SELECT name FROM vms WHERE hv_id=?", (hv_id,))
    vms = [row[0] for row in c.fetchall()]

    for vm in vms:
        stdin, stdout, _ = ssh.exec_command(f"virsh domstate {vm}")
        state = stdout.read().decode().strip() or "Unknown"
        c.execute("UPDATE vms SET status=? WHERE name=? AND hv_id=?", (state, vm, hv_id))
    
    conn.commit()
    conn.close()
    ssh.close()

@app.route('/dashboard')
def dashboard():
    conn = get_db_conn()
    c = conn.cursor()

    c.execute("SELECT id, name, ip, username, password FROM hypervisors")
    hypervisors = c.fetchall()

    for hv in hypervisors:
        hv_id, hv_name, hv_ip, hv_user, hv_pass = hv
        try:
            sync_vms_from_hv(hv_id, hv_ip, hv_user, hv_pass)
            refresh_vm_status(hv_ip, hv_user, hv_pass, hv_id)
        except Exception as e:
            app.logger.exception(f"Failed to sync hypervisor {hv_ip}: {e}")

    c.execute("""SELECT vms.name, vms.ip_addr, vms.subnetprefix, vms.vm_gateway,
                        vms.cpu, vms.memory, vms.disk, vms.status, hypervisors.name
                 FROM vms JOIN hypervisors ON vms.hv_id = hypervisors.id""")
    vms = c.fetchall()
    conn.close()

    hv_resources = {}
    all_vm_resources = [] 

    for hv in hypervisors:
        hv_id, hv_name, hv_ip, hv_user, hv_pass = hv
        total_cpu, total_mem, total_disk, used_cpu, used_mem = get_hv_resources(hv_ip, hv_user, hv_pass)
        hv_vms = [vm for vm in vms if vm[8] == hv_name]
        used_disk = sum([vm[6] for vm in hv_vms])
        
        hv_resources[hv_name] = {
            "id": hv_id,
            "total_cpu": total_cpu,
            "used_cpu": used_cpu,
            "remaining_cpu": total_cpu - used_cpu,
            "total_mem": total_mem,
            "used_mem": used_mem,
            "remaining_mem": total_mem - used_mem,
            "total_disk": total_disk,
            "used_disk": used_disk,
            "remaining_disk": total_disk - used_disk,
        }

        conn = get_db_conn()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name, cpu, memory, disk, status, ip_addr FROM vms WHERE hv_id=?", (hv_id,))
        db_vms = c.fetchall()
        conn.close()

        for vm in db_vms:
            all_vm_resources.append({
                "name": vm["name"],
                "cpu": vm["cpu"],
                "memory": vm["memory"],
                "disk": vm["disk"],
                "status": vm["status"],
                "ip_addr": vm["ip_addr"],
                "hv_ip": hv_ip
            })    

    total_remaining = {
        "cpu": sum(res["remaining_cpu"] for res in hv_resources.values()),
        "memory": sum(res["remaining_mem"] for res in hv_resources.values()),
        "disk": sum(res["remaining_disk"] for res in hv_resources.values())
    }

    total_cpu = sum(res["total_cpu"] for res in hv_resources.values())
    total_mem = sum(res["total_mem"] for res in hv_resources.values())
    total_disk = sum(res["total_disk"] for res in hv_resources.values())
    used_cpu = sum(res["used_cpu"] for res in hv_resources.values())
    used_mem = sum(res["used_mem"] for res in hv_resources.values())

    return render_template(
        "dashboard.html",
        hv_resources=hv_resources,
        vms=vms,
        remaining=total_remaining,
        total_cpu=total_cpu,
        total_mem=total_mem,
        total_disk=total_disk,
        used_cpu=used_cpu,
        used_mem=used_mem,
        hv_vm_resources=all_vm_resources
    )

# @app.route('/refresh_hv/<int:hv_id>', methods=['POST'])
# def refresh_hv(hv_id):
#     conn = get_db_conn()
#     c = conn.cursor()
#     c.execute("SELECT ip, username, password FROM hypervisors WHERE id=?", (hv_id,))
#     hv = c.fetchone()
#     conn.close()

#     if not hv:
#         return redirect(url_for('dashboard'))

#     hv_ip, hv_user, hv_pass = hv
#     sync_vms_from_hv(hv_id, hv_ip, hv_user, hv_pass)
#     refresh_vm_status(hv_ip, hv_user, hv_pass, hv_id)

#     return redirect(url_for('dashboard'))

# @app.route("/status")
# def status():
#     conn = get_db_conn()
#     conn.row_factory = sqlite3.Row
#     c = conn.cursor()
#     c.execute("SELECT name, status, hv_id FROM vms ORDER BY id DESC")
#     rows = [dict(r) for r in c.fetchall()]
#     conn.close()
#     return {"vms": rows}


if __name__ == "__main__":
    init_db()
    app.run(debug=False)
