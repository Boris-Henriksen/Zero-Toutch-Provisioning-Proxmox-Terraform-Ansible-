const availableVMs = [
  { id: "zabbix", name: "Zabbix" },
  { id: "ca-server", name: "CA-Server" },
  { id: "passbolt", name: "Passbolt" },
  { id: "pxe", name: "PXE" },
  { id: "ipam", name: "IPAM" },
  { id: "ntp", name: "NTP" },
  { id: "graylog", name: "Graylog" },
  { id: "nginx", name: "Nginx" },
  { id: "bind9", name: "Bind9" },
  { id: "bind9-slave", name: "Bind9-slave" },
  { id: "nginx-reverseproxy", name: "nginx-reverseproxy" }
];

document.querySelector('#app').innerHTML = `
  <div style="max-width: 950px; margin: 2rem auto; font-family: sans-serif;">
    <h2>Infrastruktur Portal</h2>

    <!-- Trin-Vælger -->
    <div style="display: flex; gap: 10px; margin-bottom: 2rem;">
      <button id="btn-step1" style="padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; font-weight: bold;">
        Step 1: Bare Metal Proxmox
      </button>
      <button id="btn-step2" style="padding: 10px 20px; background: #6c757d; color: white; border: none; cursor: pointer; font-weight: bold;">
        Step 2: VM & Terraform Config
      </button>
    </div>

    <!-- STEP 1 SEKTION -->
    <div id="section-step1" style="border: 1px solid #ccc; padding: 1.5rem; border-radius: 6px;">
      <h3>Step 1: Zero-Touch Bare Metal Provisioning (PXE)</h3>
      <p style="color: #666; font-size: 14px;">
        Indtast godkendte MAC-adresser. Boot maskinerne til <b>Discovery</b>. Når diskene er fundet, låses Hostname, IP og Disk-valg op.
      </p>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem;">
        <div>
          <label><b>Vælg Proxmox ISO Version:</b></label><br>
          <select id="bm-iso-version" style="padding: 6px; width: 95%;">
            <option value="">Indlæser ISO-filer...</option>
          </select>
        </div>
        <div>
          <label><b>Automations Netværkskort:</b></label><br>
          <input type="text" id="bm-interface" value="eth0" style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Gateway IP:</b></label><br>
          <input type="text" id="bm-gateway" value="10.20.10.1" style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>DNS IP:</b></label><br>
          <input type="text" id="bm-dns" value="10.20.10.1" style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Proxmox Root Password:</b></label><br>
          <input type="password" id="bm-password" value="SecretPassword123!" style="padding: 6px; width: 90%;">
        </div>
      </div>

      <h4>1. Angiv MAC-adresser for godkendelse:</h4>
      <div style="margin-bottom: 1rem;">
        <label>Antal Noder:</label>
        <input type="number" id="bm-node-count" value="1" min="1" max="10" style="padding: 4px; width: 60px;">
        <button id="btn-render-nodes" style="padding: 4px 10px;">Opdater Antal</button>
      </div>

      <div id="bm-nodes-container" style="margin-bottom: 1.5rem;">
        <!-- Node kort oprettes her -->
      </div>

      <div style="display: flex; gap: 10px; background: #f8f9fa; padding: 1rem; border-radius: 6px; border: 1px solid #e9ecef;">
        <button id="btn-start-discovery" style="padding: 10px 20px; background: #17a2b8; color: white; border: none; cursor: pointer; font-weight: bold;">
          1. Start Discovery Mode (Hent Diske)
        </button>
        <button id="btn-start-pxe" style="padding: 10px 20px; background: #28a745; color: white; border: none; cursor: pointer; font-weight: bold;">
          2. Start Proxmox Auto-Installation
        </button>
        <button id="btn-stop-pxe" style="padding: 10px 20px; background: #dc3545; color: white; border: none; cursor: pointer;">
          Stop PXE Tjeneste
        </button>
      </div>
    </div>

    <!-- STEP 2 SEKTION -->
    <div id="section-step2" style="display: none; border: 1px solid #ccc; padding: 1.5rem; border-radius: 6px;">
      <h3>Step 2: Vælg og konfigurer VM'er</h3>

      <div style="margin-bottom: 1.5rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
        <div>
          <label><b>Proxmox Host IP / API:</b></label><br>
          <input type="text" id="proxmox-ip" placeholder="f.eks. 10.20.10.10" style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Subnet Prefix:</b></label><br>
          <input type="text" id="subnet-prefix" value="10.20.10" style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Start IP Host-tal:</b></label><br>
          <input type="number" id="start-ip" value="101" style="padding: 6px; width: 90%;">
        </div>
      </div>

      <div style="margin-bottom: 1.5rem;">
        <label><b>Public SSH Keys (Indsæt én eller flere offentlige nøgler, én pr. linje):</b></label><br>
        <textarea id="ssh-keys" rows="3" style="width: 98%; padding: 6px; font-family: monospace; font-size: 12px;" placeholder="ssh-rsa AAAAB3NzaC1yc2E... user@host"></textarea>
      </div>

      <table style="width: 100%; border-collapse: collapse; margin-bottom: 1.5rem;" border="1" cellpadding="6">
        <thead>
          <tr style="background: #f4f4f4;">
            <th>Aktiv</th>
            <th>Navn</th>
            <th>Node</th>
            <th>Cores</th>
            <th>RAM (MB)</th>
            <th>Disk (GB)</th>
          </tr>
        </thead>
        <tbody>
          ${availableVMs.map(vm => `
            <tr id="row-${vm.id}">
              <td align="center"><input type="checkbox" class="vm-toggle" data-id="${vm.id}"></td>
              <td><input type="text" value="${vm.name}" class="vm-name" readonly style="width: 150px; background-color: #e9ecef; border: 1px solid #ced4da; cursor: not-allowed;"></td>
              <td>
                <select class="vm-node">
                  <option value="proxmox-node1">proxmox-node1</option>
                  <option value="proxmox-node2">proxmox-node2</option>
                  <option value="proxmox-node3">proxmox-node3</option>
                </select>
              </td>
              <td><input type="number" value="2" class="vm-cores" style="width: 50px;"></td>
              <td><input type="number" value="2048" class="vm-ram" style="width: 70px;"></td>
              <td><input type="number" value="20" class="vm-disk" style="width: 50px;"></td>
            </tr>
          `).join('')}
        </tbody>
      </table>

      <button id="submit-btn" style="padding: 10px 20px; background: #28a745; color: white; border: none; cursor: pointer; font-size: 16px;">
        Generér Terraform & Ansible Konfiguration
      </button>
    </div>
  </div>
`;

// Hent ISO-versioner
async function loadIsoVersions() {
  const select = document.getElementById('bm-iso-version');
  try {
    const res = await fetch('/api/proxmox/versions');
    const data = await res.json();
    if (data.versions && data.versions.length > 0) {
      select.innerHTML = data.versions.map(v => `<option value="${v}">${v}</option>`).join('');
    } else {
      select.innerHTML = '<option value="">Ingen .iso filer fundet i storage/isos/</option>';
    }
  } catch (err) {
    select.innerHTML = '<option value="">Fejl ved indlæsning af ISO-filer</option>';
  }
}
loadIsoVersions();

// Fanebladsskift
const sec1 = document.getElementById('section-step1');
const sec2 = document.getElementById('section-step2');
const btn1 = document.getElementById('btn-step1');
const btn2 = document.getElementById('btn-step2');

btn1.addEventListener('click', () => {
  sec1.style.display = 'block';
  sec2.style.display = 'none';
  btn1.style.background = '#007bff';
  btn2.style.background = '#6c757d';
});

btn2.addEventListener('click', () => {
  sec1.style.display = 'none';
  sec2.style.display = 'block';
  btn1.style.background = '#6c757d';
  btn2.style.background = '#007bff';
});

// Render Node kort (Kun MAC-adresse er åben fra start!)
function renderNodeRows(count) {
  const container = document.getElementById('bm-nodes-container');
  let html = '';

  for (let i = 0; i < count; i++) {
    html += `
      <div class="node-card" data-index="${i}" style="border: 1px solid #ddd; padding: 1rem; margin-bottom: 1rem; border-radius: 4px; background: #fafafa;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.8rem;">
          <div style="flex-grow: 1; margin-right: 15px;">
            <label style="font-size:12px;"><b>MAC-adresse (Godkendelse):</b></label><br>
            <input type="text" class="bm-node-mac" placeholder="52:54:00:12:34:5${i+1}" style="width: 100%; padding: 5px; font-weight: bold;">
          </div>
          <div>
            <span class="discovery-status" style="font-size: 12px; color: #856404; background: #fff3cd; padding: 4px 10px; border-radius: 4px; font-weight: bold;">
              Afventer Discovery...
            </span>
          </div>
        </div>

        <!-- System- & Netværksindstillinger (Skjult indtil Discovery) -->
        <div class="config-section" style="border-top: 1px solid #eee; padding-top: 0.8rem; margin-top: 0.5rem; opacity: 0.6;">
          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; margin-bottom: 0.8rem;">
            <div>
              <label style="font-size:12px;"><b>Hostname:</b></label><br>
              <input type="text" class="bm-node-host" value="proxmox-node${i+1}" disabled style="width: 90%; padding: 4px;">
            </div>
            <div>
              <label style="font-size:12px;"><b>Statisk IP:</b></label><br>
              <input type="text" class="bm-node-ip" value="10.20.10.${10+i}" disabled style="width: 90%; padding: 4px;">
            </div>
            <div>
              <label style="font-size:12px;"><b>OS-disk (Proxmox):</b></label><br>
              <select class="bm-node-disk" disabled style="width: 95%; padding: 4px;">
                <option value="">Start Discovery for at vælge disk...</option>
              </select>
            </div>
          </div>

          <!-- Ceph Sektion -->
          <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px dashed #ccc;">
            <label style="font-size: 13px; cursor: pointer;">
              <input type="checkbox" class="bm-ceph-toggle" data-index="${i}" disabled> 
              <b>Opret Ceph Cluster på denne node</b>
            </label>

            <div id="ceph-options-${i}" style="display: none; margin-top: 8px; padding: 8px; background: #f0f4f8; border-left: 3px solid #007bff;">
              <label style="font-size: 12px;"><b>Vælg OSD-diske til Ceph:</b></label>
              <div class="ceph-dropdown-container" style="margin-top: 5px;">
                <!-- Dynamiske OSD Dropdowns indsættes her -->
              </div>
              <button type="button" class="btn-add-osd" data-index="${i}" style="margin-top: 6px; padding: 3px 8px; font-size: 11px; cursor: pointer;">
                + Tilføj endnu en OSD disk
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;

  // Ceph Toggle lytter
  document.querySelectorAll('.bm-ceph-toggle').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const idx = e.target.getAttribute('data-index');
      const box = document.getElementById(`ceph-options-${idx}`);
      box.style.display = e.target.checked ? 'block' : 'none';
    });
  });

  // Tilføj OSD Knap lytter
  document.querySelectorAll('.btn-add-osd').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = e.target.getAttribute('data-index');
      addOsdDropdown(idx);
    });
  });
}

// Hjælpefunktion til at tilføje OSD Dropdown
function addOsdDropdown(nodeIdx, optionsHtml = '') {
  const container = document.querySelector(`.node-card[data-index="${nodeIdx}"] .ceph-dropdown-container`);
  const div = document.createElement('div');
  div.style.cssText = 'display: flex; gap: 5px; margin-bottom: 5px; align-items: center;';
  div.innerHTML = `
    <select class="bm-ceph-osd-select" style="padding: 4px; flex-grow: 1;">
      ${optionsHtml || '<option value="">Vælg OSD disk...</option>'}
    </select>
    <button type="button" onclick="this.parentElement.remove()" style="background: #dc3545; color: white; border: none; padding: 4px 8px; cursor: pointer; border-radius: 3px;">✕</button>
  `;
  container.appendChild(div);
}

renderNodeRows(1);

document.getElementById('btn-render-nodes').addEventListener('click', () => {
  const count = parseInt(document.getElementById('bm-node-count').value) || 1;
  renderNodeRows(count);
});

// Automatisk Polling for fundne diske fra Micro-Image
async function checkDiscoveredDisks() {
  try {
    const res = await fetch('/api/baremetal/nodes');
    const data = await res.json();
    if (!data.nodes) return;

    document.querySelectorAll('.node-card').forEach(card => {
      const macInput = card.querySelector('.bm-node-mac').value.toLowerCase().trim();
      if (!macInput) return;

      const matchingNode = data.nodes.find(n => n.mac_address && n.mac_address.toLowerCase() === macInput);

      if (matchingNode && matchingNode.discovered_disks && matchingNode.discovered_disks.length > 0) {
        const statusBadge = card.querySelector('.discovery-status');
        const configSection = card.querySelector('.config-section');
        const hostInput = card.querySelector('.bm-node-host');
        const ipInput = card.querySelector('.bm-node-ip');
        const osSelect = card.querySelector('.bm-node-disk');
        const cephToggle = card.querySelector('.bm-ceph-toggle');

        // Opdater status badge og gennemsigtighed
        statusBadge.innerText = `Klar til install (${matchingNode.discovered_disks.length} diske fundet)`;
        statusBadge.style.background = '#d4edda';
        statusBadge.style.color = '#155724';
        configSection.style.opacity = '1.0';

        // LÅS ALT OP NÅR DISKE ER FUNDET
        hostInput.disabled = false;
        ipInput.disabled = false;
        osSelect.disabled = false;
        cephToggle.disabled = false;

        const currentOsVal = osSelect.value;

        // Indsæt fundne diske i dropdown
        let diskOptionsHtml = matchingNode.discovered_disks.map(d => 
          `<option value="${d.name}">${d.name} (${d.size} - ${d.model})</option>`
        ).join('');

        osSelect.innerHTML = diskOptionsHtml;
        if (currentOsVal) osSelect.value = currentOsVal;

        // Gem options til brug for Ceph
        card.setAttribute('data-disk-options', diskOptionsHtml);

        const cephContainer = card.querySelector('.ceph-dropdown-container');
        if (cephContainer.children.length === 0) {
          addOsdDropdown(card.getAttribute('data-index'), diskOptionsHtml);
        }
      }
    });
  } catch (e) {
    // Stille fejlhåndtering
  }
}

// Tjek for diske hvert 3. sekund
setInterval(checkDiscoveredDisks, 3000);

// 1. Start Discovery Mode
document.getElementById('btn-start-discovery').addEventListener('click', async () => {
  const nodes = [];
  document.querySelectorAll('.node-card').forEach(card => {
    const mac = card.querySelector('.bm-node-mac').value.trim();
    if (mac) {
      nodes.push({
        hostname: "discovery-temp",
        mac_address: mac,
        ip: "10.20.10.200", // Dynamisk DHCP IP under discovery
        disk: "sda"
      });
    }
  });

  if (nodes.length === 0) {
    alert("Indtast venligst mindst én MAC-adresse først!");
    return;
  }

  const payload = {
    interface: document.getElementById('bm-interface').value,
    gateway: document.getElementById('bm-gateway').value,
    dns: document.getElementById('bm-dns').value,
    root_password: document.getElementById('bm-password').value,
    selected_iso: "discovery.iso",
    nodes: nodes
  };

  const res = await fetch('/api/baremetal/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  alert("Discovery PXE startet! Tænd nu serverne så de kan hente Micro-Image'et og rapportere deres diske.");
});

// 2. Start Proxmox Auto-Installation
document.getElementById('btn-start-pxe').addEventListener('click', async () => {
  const selectedIso = document.getElementById('bm-iso-version').value;
  if (!selectedIso) {
    alert('Vælg venligst en Proxmox ISO-fil!');
    return;
  }

  const nodes = [];
  document.querySelectorAll('.node-card').forEach(card => {
    const cephToggle = card.querySelector('.bm-ceph-toggle').checked;
    const osdSelects = card.querySelectorAll('.bm-ceph-osd-select');
    const selectedCephDisks = Array.from(osdSelects).map(s => s.value).filter(v => v !== "");

    nodes.push({
      hostname: card.querySelector('.bm-node-host').value,
      mac_address: card.querySelector('.bm-node-mac').value,
      ip: card.querySelector('.bm-node-ip').value,
      disk: card.querySelector('.bm-node-disk').value || "sda",
      enable_ceph: cephToggle,
      ceph_disks: selectedCephDisks
    });
  });

  const payload = {
    interface: document.getElementById('bm-interface').value,
    gateway: document.getElementById('bm-gateway').value,
    dns: document.getElementById('bm-dns').value,
    root_password: document.getElementById('bm-password').value,
    selected_iso: selectedIso,
    nodes: nodes
  };

  const res = await fetch('/api/baremetal/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  alert(data.message || 'Proxmox PXE Installation startet!');
});

// Stop PXE
document.getElementById('btn-stop-pxe').addEventListener('click', async () => {
  const res = await fetch('/api/baremetal/stop', { method: 'POST' });
  const data = await res.json();
  alert(data.message || 'PXE Stoppet');
});

// Step 2 Submit
document.getElementById('submit-btn').addEventListener('click', async () => {
  const proxmoxIp = document.getElementById('proxmox-ip').value;
  const prefix = document.getElementById('subnet-prefix').value;
  const startIp = parseInt(document.getElementById('start-ip').value) || 101;
  const rawSshKeys = document.getElementById('ssh-keys').value;

  const sshKeysList = rawSshKeys.split('\n').map(k => k.trim()).filter(k => k.length > 0);

  if (!proxmoxIp) {
    alert('Angiv venligst IP-adressen på din Proxmox host!');
    return;
  }

  const selectedVMs = [];
  document.querySelectorAll('.vm-toggle:checked').forEach(cb => {
    const row = cb.closest('tr');
    selectedVMs.push({
      key: cb.getAttribute('data-id'),
      name: row.querySelector('.vm-name').value,
      node: row.querySelector('.vm-node').value,
      cores: parseInt(row.querySelector('.vm-cores').value),
      sockets: 1,
      memory: parseInt(row.querySelector('.vm-ram').value),
      disk: parseInt(row.querySelector('.vm-disk').value)
    });
  });

  if (selectedVMs.length === 0) {
    alert('Vælg venligst mindst én VM!');
    return;
  }

  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      proxmox_api_ip: proxmoxIp,
      subnet_prefix: prefix,
      start_ip: startIp,
      ssh_keys: sshKeysList,
      vms: selectedVMs
    })
  });

  if (res.ok) {
    alert(`Konfiguration oprettet for ${selectedVMs.length} VM('er)!`);
  } else {
    alert('Der opstod en fejl.');
  }
});
