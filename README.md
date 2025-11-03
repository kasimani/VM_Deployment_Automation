**Work In Progress**

**Python Flask based VM Deployment Automation with Ansible on KVM**

Thiss project provides a framework to automate VM provisioning on KVM hypervisors using Ansible.
It integrates with a Flask-based UI that collects VM and hypervisor details from users (via web forms or Excel import) and then executes automated deployment workflows.

**Project Structure**
```bash
├── ansible-playbook
│   ├── ansible.cfg
│   ├── bm_rhel_install.yml
│   ├── destroy.yml
│   ├── hosts
│   ├── hosts.yml
│   ├── hv.db
│   ├── playbook.yml
│   ├── README.md
│   ├── roles
│   │   ├── kvm_install    ## WIP
│   │   │   └── tasks
│   │   │       └── main.yml 
│   │   └── vm_deploy
│   │       ├── defaults
│   │       │   └── main.yml
│   │       ├── tasks
│   │       │   ├── main.yml
│   │       │   └── vm_creation.yml
│   │       └── templates
│   │           ├── authorized_keys.j2
│   │           ├── hostname.j2
│   │           ├── ifcfg-enp1s0.j2
│   │           ├── network.j2
│   │           └── vm.xml.j2
│   └── vars
│       ├── vm_vars_Cluster_VM_1.yml  ##Dynamic Inventory File for VMs
├── app.py
├── delete_vm.py
├── deploy_vm_handler2.py
├── README.md
├── rhel8-minimal.ks
├── Structure.txt
├── templates
│   ├── add_hv.html
│   ├── base.html
│   ├── dashboard.html
│   ├── deploy_vm.html
│   └── index.html
└── vm_deploy.log

---

## 🚀 Features

**Present goals:**
•	VM provisioning based on user input **- Done**
•	Option to select number of VMs to provision **- Done**
•	Option to select HV for VM destination **- Done**
•	HV selection based Round-Robin if VMs are more than 1 **- Done**
•	Input of IP details per VM **- Done**
•	Partitioning scheme per VM type - Done
•	Query HVs for existing VMs and H/W resources (total vs. remaining, VM mappings, resource allocation) **- Done**

**Once these are achieved, the plan is to containerize the whole solution into a Docker instance.**

**(Note: The only gap I’m still hitting is finding a clean way to query existing VM IP details.)**

**Future add-ons: **
•	Application installation (NSP, NFM-P, etc.)
•	Upgrade of existing NSP and NFM-P (together or individually)
•	Patching NSP and NFM-P (together or individually)


---

## ⚙️ Prerequisites

- Python 3.8+
- Flask
- Ansible 2.9+
- libvirt & KVM installed on target hypervisors
- SSH access to hypervisors (password/SSH key)

Install Python dependencies:

```bash
pip install flask paramiko



**Running the Web App**
python app.py

The app will be available at:
👉 http://127.0.0.1:5000/



📦 Deploying a VM

- Add hypervisors in the Dashboard → Add Hypervisor
- Provide VM details in the Deploy VM section
- Click Deploy to trigger the Ansible playbook
- Monitor progress via logs in vm_deploy.log


Author
Manish Singh
Automation Architect | Linux & Network Virtualization Specialist | India
