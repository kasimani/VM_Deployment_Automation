import os
import subprocess
import logging
import sqlite3
from flask import request, flash, redirect, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "hv.db")

def delete_vm_handler(vm_name, hv_ip):
    #vm_name = request.form.get('vm_name')
    if not vm_name:
        flash("VM name not provided!", "error")
        #return redirect(url_for('dashboard'))

    prev_cwd = os.getcwd()
    try:
        os.chdir("ansible-playbook")
        cmd = [
            "ansible-playbook", "destroy.yml",
            "-e", f"vm_name={vm_name}",
            "-e", f"target_server={hv_ip}",
            "-e", "target_server_username=root",
            "-e", "libvirt_user=root",
            "-e", "libvirt_group=root"
        ]
        logging.info(f"Running Ansible: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        for line in process.stdout:
            logging.info(f"[Ansible STDOUT] {line.strip()}")

        for line in process.stderr:
            logging.error(f"[Ansible STDERR] {line.strip()}")

        process.wait()

        if process.returncode == 0:
            flash(f"VM '{vm_name}' deleted successfully!", "success")
            remove_vm_from_db(vm_name)
        else:
            flash(f"Failed to delete VM '{vm_name}'. Exit code: {process.returncode}", "error")

    except Exception as e:
        flash(f"Error deleting VM '{vm_name}': {e}", "error")

    finally:
        os.chdir(prev_cwd)

    return redirect(url_for('dashboard'))


def remove_vm_from_db(vm_name):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM vms WHERE name=?", (vm_name,))
        conn.commit()
        conn.close()
        flash(f"Database entry for VM '{vm_name}' removed successfully.", "success")
    except Exception as e:
        flash(f"Failed to remove VM '{vm_name}' from DB: {e}", "error")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python delete_vm.py <vm_name>")
    else:
        vm_name = sys.argv[1]
        remove_vm_from_db(vm_name)