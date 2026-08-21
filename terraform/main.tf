terraform {
  required_providers {
    proxmox = {
      source  = "Telmate/proxmox"
      version = "2.9.14"
    }
  }
}

provider "proxmox" {
  pm_api_url      = "https://10.20.10.2:8006/api2/json"
  pm_user         = "root@pam"
  pm_tls_insecure = true
}


resource "proxmox_vm_qemu" "zabbix" {
  name        = "Zabbix"
  target_node = "proxmox-node1"
  clone       = "ubuntu-cloudinit-template"

  cores   = 2
  sockets = 1
  memory  = 2048

  disk {
    size    = "20G"
    type    = "scsi"
    storage = "local-lvm"
  }

  network {
    model  = "virtio"
    bridge = "vmbr0"
  }

  ipconfig0 = "ip=10.20.10.101/24,gw=10.20.10.1"
  sshkeys   = file("~/.ssh/id_rsa.pub")
}

resource "proxmox_vm_qemu" "ipam" {
  name        = "IPAM"
  target_node = "proxmox-node1"
  clone       = "ubuntu-cloudinit-template"

  cores   = 2
  sockets = 1
  memory  = 2048

  disk {
    size    = "20G"
    type    = "scsi"
    storage = "local-lvm"
  }

  network {
    model  = "virtio"
    bridge = "vmbr0"
  }

  ipconfig0 = "ip=10.20.10.102/24,gw=10.20.10.1"
  sshkeys   = file("~/.ssh/id_rsa.pub")
}

resource "proxmox_vm_qemu" "nginx" {
  name        = "Nginx"
  target_node = "proxmox-node1"
  clone       = "ubuntu-cloudinit-template"

  cores   = 2
  sockets = 1
  memory  = 2048

  disk {
    size    = "20G"
    type    = "scsi"
    storage = "local-lvm"
  }

  network {
    model  = "virtio"
    bridge = "vmbr0"
  }

  ipconfig0 = "ip=10.20.10.103/24,gw=10.20.10.1"
  sshkeys   = file("~/.ssh/id_rsa.pub")
}

resource "proxmox_vm_qemu" "bind9" {
  name        = "Bind9"
  target_node = "proxmox-node1"
  clone       = "ubuntu-cloudinit-template"

  cores   = 2
  sockets = 1
  memory  = 2048

  disk {
    size    = "20G"
    type    = "scsi"
    storage = "local-lvm"
  }

  network {
    model  = "virtio"
    bridge = "vmbr0"
  }

  ipconfig0 = "ip=10.20.10.104/24,gw=10.20.10.1"
  sshkeys   = file("~/.ssh/id_rsa.pub")
}
