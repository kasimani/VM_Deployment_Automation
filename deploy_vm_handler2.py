import os
import sqlite3
import threading
import subprocess
import yaml
from itertools import cycle
import glob
import logging

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hv.db")

def update_vm_status(vm_name, hv_id, new_status):
    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute(
                "UPDATE vms SET status=? WHERE name=? AND hv_id=?",
                (new_status, vm_name, hv_id),
            )
            conn.commit()
        logging.info(f"Updated VM {vm_name} on HV {hv_id} → {new_status}")
    except Exception as e:
        logging.error(f"Failed to update VM {vm_name} on HV {hv_id}: {e}")

def expand_vm_bundle(base_name, count, base_spec):
    vms = []
    for i in range(1, count + 1):
        vm = base_spec.copy()
        vm['name'] = f"{base_name}{i:02d}"
        vms.append(vm)
    return vms

def spread_even(vms, hv_list):
    plan = {hv['id']: [] for hv in hv_list}
    if not vms:
        return plan
    if len(hv_list) == 1:
        plan[hv_list[0]['id']] = vms
        return plan
    idx = 0
    while idx < min(len(vms), len(hv_list)):
        hv = hv_list[idx]
        plan[hv['id']].append(vms[idx])
        idx += 1
    hv_cycle = cycle(hv_list)
    for vm in vms[idx:]:
        hv = next(hv_cycle)
        plan[hv['id']].append(vm)
    return plan

def build_deployment_plan(hv_list, bundles):
    all_vms = []
    for b in bundles:
        all_vms += expand_vm_bundle(b['base_name'], b['count'], b['spec'])
    by_hv = spread_even(all_vms, hv_list)
    return [{'hv': hv, 'hv_id': hv['id'], 'vms': by_hv[hv['id']]} for hv in hv_list]

def run_ansible_playbook(hv_ip, hv_user, run_tag, hv_id, vms):
    playbook_dir = os.path.join(os.path.dirname(__file__), "ansible-playbook")
    vars_dir = os.path.join(playbook_dir, "vars")
    os.makedirs(vars_dir, exist_ok=True)
    var_file = os.path.join(vars_dir, f"vm_vars_{run_tag}_{hv_id}.yml")
    with open(var_file, "w") as f:
        yaml.dump({"vms": vms}, f, sort_keys=False)

    prev_cwd = os.getcwd()
    try:
        os.chdir(playbook_dir)
        cmd = [
            "ansible-playbook", "playbook.yml",
            "-e", f"target_server={hv_ip}",
            "-e", f"target_server_username={hv_user}",
            "-e", f"@vars/{os.path.basename(var_file)}",
            "-e", "qcow2_image_src_dir=/home/qcow2images",
            "-e", "qcow2_image_dst_dir=/home/images",
            "-e", "vm_bridge=br0",
            "-e", "vm_interface=enp1s0",
            "-e", "libvirt_user=root",
            "-e", "libvirt_group=root",            
            "-e", "user_ssh_pub_key=~/.ssh/id_rsa.pub",
            "--forks", "5",
        ]
        logging.info(f"Running Ansible: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        for line in process.stdout:
            logging.info(f"[Ansible STDOUT][HV {hv_ip}] {line.strip()}")
        for line in process.stderr:
            logging.error(f"[Ansible STDERR][HV {hv_ip}] {line.strip()}")

        ret = process.wait()
        if ret == 0:
            logging.info(f"Ansible finished successfully for HV {hv_ip}")
            for vm in vms:
                update_vm_status(vm['name'], hv_id, "Completed")
        else:
            logging.error(f"Ansible failed for HV {hv_ip} with exit code {ret}")
            for vm in vms:
                update_vm_status(vm['name'], hv_id, "Failed")

    except Exception as e:
        logging.exception(f"Unexpected error running Ansible for HV {hv_ip}: {e}")
    finally:
        os.chdir(prev_cwd)

def deploy_vm_route(request, render_template, redirect, url_for, flash):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, name, ip, username, password FROM hypervisors ORDER BY id ASC")
        hypervisors = [dict(r) for r in cur.fetchall()]

    if request.method == "POST":
        base_name = (request.form.get("name") or "vm").strip()
        vm_type = (request.form.get("vm_type") or "other").strip()
        vm_count = int(request.form.get("vm_count") or request.form.get("count") or 1)
        cpu = int(request.form.get("cpu") or 2)
        memory_gb = int(request.form.get("memory") or 2048)
        disk = int(request.form.get("disksize") or 20480)
        ip_addr = (request.form.get("ip_addr") or "").strip()
        subnetprefix = (request.form.get("subnetprefix") or "24").strip()
        vm_gateway = (request.form.get("vm_gateway") or "").strip()
        hv_id_selected = request.form.get("hv_id") 

        qcow2_images = {
            "deployer": "NSP_K8S_PLATFORM_RHEL*.qcow2",
            "cluster": "NSP_K8S_PLATFORM_RHEL*.qcow2",
            "nfm-p": "NSP_RHEL*.qcow2",
            "other": "default.qcow2",
        }
        pattern = qcow2_images.get(vm_type, "default.qcow2")
        matches = glob.glob(os.path.join("/home/qcow2images", pattern))

        if matches:
            qcow2_image = matches[0]
            logging.info(f"Selected qcow2 image for {vm_type}: {qcow2_image}")
        else:
            flash(f"No qcow2 image found for pattern {pattern}", "danger")
            return redirect(url_for("deploy_vm"))

        lvs = request.form.getlist("lv[]")
        mounts = request.form.getlist("mount[]")
        sizes_gb = request.form.getlist("size_g[]")
        sizes_mb = [int(float(size) * 1024) for size in sizes_gb]
        memory =memory_gb * 1024


        required_partitions = []
        for lv, mount, size in zip(lvs, mounts, sizes_mb):
            try:
                required_partitions.append({
                    "lv": lv.strip(),
                    "mount": mount.strip(),
                    "size_mb": int(size or 0),
                })
            except Exception as e:
                logging.error(f"Invalid partition input: {lv}, {mount}, {size} - {e}")

        base_spec = {
            "cpu": cpu,
            "ram": memory,
            "disk": disk,
            "ipaddr": ip_addr,
            "prefix": subnetprefix,
            "gateway": vm_gateway,
            "qcow2_image": qcow2_image,
            "vg_name": "vg1",
            "vm_type": vm_type,
            "required_partitions": required_partitions,
        }

        bundles = [{"base_name": base_name, "count": vm_count, "spec": base_spec}]
        
        if hv_id_selected and hv_id_selected.lower() != "all":
            hypervisors = [hv for hv in hypervisors if str(hv["id"]) == hv_id_selected]

        plan = build_deployment_plan(hypervisors, bundles)
        logging.info(f"Deployment plan: {plan}")

        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            for entry in plan:
                hv_id = entry['hv_id']
                for vm in entry['vms']:
                    conn.execute(
                        """INSERT INTO vms 
                           (name, ip_addr, subnetprefix, vm_gateway, hv_id, cpu, memory, disk, status, vm_type) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (vm['name'], vm.get('ipaddr') or 0, vm.get('prefix') or 24,
                         vm.get('gateway') or 0, hv_id, vm['cpu'], vm['ram'],
                         vm['disk'], "In-progress", vm_type)
                    )
            conn.commit()

        for entry in plan:
            if not entry['vms']:
                continue
            threading.Thread(
                target=run_ansible_playbook,
                args=(entry['hv']['ip'], entry['hv']['username'],
                      base_name, entry['hv_id'], entry['vms']),
                daemon=True,
            ).start()

        return redirect(url_for("dashboard"))

    return render_template("deploy_vm.html", hypervisors=hypervisors)
