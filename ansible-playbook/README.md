# 🖥️ Ansible KVM VM Deployment Automation

This project automates the deployment of KVM-based virtual machines using Ansible, `virt-install`, and offline customization with `guestfish`. It supports injecting SSH keys, setting static IP configurations, defining persistent interface names, and full image-based VM creation from QCOW2 templates.

---

## 📁 Project Structure

```bash
vm-deploy-demo/
├── ansible.cfg                # Ansible configuration file
├── inventory/
│   └── hosts                  # Static inventory file
├── group_vars/
│   └── all.yml                # Global variables (VM specs, paths, user info)
├── playbook.yml              # Main playbook for provisioning VMs
├── destroy.yml               # Playbook to destroy VMs with storage
├── roles/
│   └── vm_deploy/
│       ├── defaults/
│       │   └── main.yml
│       ├── tasks/
│       │   └── main.yml      # Full VM customization and deployment logic
│       └── templates/
│           ├── authorized_keys.j2
│           ├── hostname.j2
│           ├── ifcfg-enp1s0.j2
│           ├── network.j2
│           └── vm.xml.j2
├── qcow2_images/
│   └── centos7.qcow2         # Base QCOW2 image used for deployment
├── secrets.yml               # Encrypted secrets (via Ansible Vault)
├── assert.yml                # Assertion examples
├── blocks-1.yml              # Ansible block examples
├── blocks-2.yml
├── tags.yml                  # Tagging demo for conditional task execution
├── structure                 # Documentation or notes placeholder
└── test.yml                  # Simple testing playbook

**Getting Started**
**Clone the Repo**
git clone https://github.com/your-username/vm-deploy-demo.git
cd vm-deploy-demo

**Encrypt Secrets (optional)**
ansible-vault encrypt secrets.yml

**Run the Playbook**
ansible-playbook -i inventory/hosts playbook.yml

**Destroy VM (if needed)**
ansible-playbook -i inventory/hosts destroy.yml --tags delete_deployer

**Run selective tasks using tags**
ansible-playbook -i inventory/hosts playbook.yml --tags network_config

**Run test playbook with condition**
ansible-playbook test.yml -e "skip_specific_tasks=false"

**Ansible Vault**
Secrets file (secrets.yml) is encrypted using Ansible Vault:
ansible-vault view secrets.yml

•	Key Concepts Demonstrated
•	Jinja2 templating
•	Ansible Vault usage
•	Dynamic and static inventories
•	Custom task blocks and conditions
•	Guestfish image editing
•	Clean VM destruction

Author
Manish Singh
Automation Architect | Linux & Network Virtualization Specialist | India
