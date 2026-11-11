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

      <div id="bm-general-settings" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; opacity: 0.55;">
        <div>
          <label><b>Vælg Proxmox ISO Version:</b></label><br>
          <select id="bm-iso-version" disabled style="padding: 6px; width: 95%;">
            <option value="">Indlæser ISO-filer...</option>
          </select>
        </div>
        <div>
          <label><b>Automations Netværkskort:</b></label><br>
          <input type="text" id="bm-interface" placeholder="Automatisk valgt ved Discovery" disabled style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Gateway IP:</b></label><br>
          <input type="text" id="bm-gateway" placeholder="f.eks. 10.20.10.1" disabled style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>DNS IP:</b></label><br>
          <input type="text" id="bm-dns" placeholder="f.eks. 10.20.10.1" disabled style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Proxmox Root Password:</b></label><br>
          <input type="password" id="bm-password" placeholder="Mindst 8 tegn" disabled style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Domæne:</b></label><br>
          <input type="text" id="bm-domain" value="lab.local" placeholder="f.eks. lab.local" disabled style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Admin e-mail:</b></label><br>
          <input type="text" id="bm-mailto" value="admin@lab.local" disabled style="padding: 6px; width: 90%;">
        </div>
        <div>
          <label><b>Filsystem (OS-disk):</b></label><br>
          <select id="bm-filesystem" disabled style="padding: 6px; width: 95%;">
            <option value="ext4">ext4</option>
            <option value="xfs">xfs</option>
            <option value="zfs">zfs</option>
          </select>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 0.5rem; width: 95%;">
          <div>
            <label><b>Tastatur:</b></label><br>
            <input type="text" id="bm-keyboard" value="dk" disabled style="padding: 6px; width: 80%;">
          </div>
          <div>
            <label><b>Land:</b></label><br>
            <input type="text" id="bm-country" value="dk" disabled style="padding: 6px; width: 80%;">
          </div>
          <div>
            <label><b>Tidszone:</b></label><br>
            <input type="text" id="bm-timezone" value="Europe/Copenhagen" disabled style="padding: 6px; width: 90%;">
          </div>
        </div>

        <div style="grid-column: 1 / -1; border-top: 1px solid #ddd; padding-top: 0.8rem;">
          <label style="cursor: pointer;">
            <input type="checkbox" id="bm-create-cluster" disabled>
            <b>Opret Cluster?</b>
          </label>
          <div id="bm-cluster-options" style="display: none; margin-top: 0.6rem; padding: 0.8rem; background: #f0f4f8; border-left: 3px solid #007bff;">
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 0.5rem;">
              <div>
                <label style="font-size: 13px;"><b>Clusternavn:</b></label><br>
                <input type="text" id="bm-cluster-name" value="pve-cluster" disabled style="padding: 5px; width: 85%;">
              </div>
              <div>
                <label style="font-size: 13px;"><b>Ceph pool-navn:</b></label><br>
                <input type="text" id="bm-ceph-pool" value="ceph-vm" disabled style="padding: 5px; width: 85%;">
              </div>
              <div>
                <label style="font-size: 13px;"><b>Ceph replika (size):</b></label><br>
                <input type="number" id="bm-ceph-size" value="3" min="1" max="10" disabled style="padding: 5px; width: 60px;">
              </div>
              <div>
                <label style="font-size: 13px;"><b>Ceph min_size:</b></label><br>
                <input type="number" id="bm-ceph-min-size" value="2" min="1" max="10" disabled style="padding: 5px; width: 60px;">
              </div>
            </div>
            <p id="bm-ceph-info" style="font-size: 12px; color: #555; margin: 0.6rem 0 0 0;">
              Vælg under hver node om den skal bruges i Ceph. Ceph-netværket beregnes automatisk ud fra nodernes IP.
              Cluster og Ceph oprettes automatisk når alle noder er installeret.
            </p>
          </div>
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

      <div id="bm-progress" style="display: none; margin-bottom: 1rem; padding: 0.8rem 1rem; border-radius: 6px; border: 1px solid #b8daff; background: #e7f1ff; font-size: 14px;">
        <div id="bm-phase-message"></div>
        <div id="bm-cluster-message" style="margin-top: 4px;"></div>
        <button id="btn-retry-cluster" style="display: none; margin-top: 6px; padding: 4px 10px; cursor: pointer;">Prøv cluster-opsætning igen</button>
        <details id="bm-cluster-log-box" style="display: none; margin-top: 6px;">
          <summary style="cursor: pointer; font-size: 12px;">Vis log</summary>
          <pre id="bm-cluster-log" style="font-size: 11px; white-space: pre-wrap; max-height: 200px; overflow: auto; margin: 4px 0 0 0;"></pre>
        </details>
      </div>

      <div style="display: flex; gap: 10px; background: #f8f9fa; padding: 1rem; border-radius: 6px; border: 1px solid #e9ecef;">
        <button id="btn-start-discovery" style="padding: 10px 20px; background: #17a2b8; color: white; border: none; cursor: pointer; font-weight: bold;">
          1. Start Discovery Mode (Hent Diske)
        </button>
        <button id="btn-start-pxe" disabled style="padding: 10px 20px; background: #28a745; color: white; border: none; cursor: pointer; font-weight: bold;">
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
      const savedIso = loadState()?.general?.iso;
      const proxmoxIso = data.versions.find(v => v.toLowerCase().includes('proxmox'));
      if (savedIso && data.versions.includes(savedIso)) select.value = savedIso;
      else if (proxmoxIso) select.value = proxmoxIso;
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

let activeStep = 1;

function showStep(step) {
  activeStep = step;
  sec1.style.display = step === 1 ? 'block' : 'none';
  sec2.style.display = step === 2 ? 'block' : 'none';
  btn1.style.background = step === 1 ? '#007bff' : '#6c757d';
  btn2.style.background = step === 2 ? '#007bff' : '#6c757d';
}

btn1.addEventListener('click', () => { showStep(1); saveState(); });
btn2.addEventListener('click', () => { showStep(2); saveState(); });

// --- Gem/gendan formular i browserens localStorage (root password gemmes bevidst ikke) ---
const STATE_KEY = 'portal-form-state-v1';
let restoring = false;

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STATE_KEY)) || null;
  } catch {
    return null;
  }
}

function collectNodeStates() {
  return Array.from(document.querySelectorAll('.node-card')).map(card => {
    const diskSelect = card.querySelector('.bm-node-disk');
    const osdSelects = Array.from(card.querySelectorAll('.bm-ceph-osd-select'));
    return {
      mac: card.querySelector('.bm-node-mac').value,
      host: card.querySelector('.bm-node-host').value,
      ip: card.querySelector('.bm-node-ip').value,
      // Før discovery findes diskene ikke i dropdown'en endnu - behold den gemte værdi.
      disk: diskSelect.value || card.dataset.savedDisk || '',
      ceph: card.querySelector('.bm-ceph-toggle').checked,
      cephDisks: osdSelects.length > 0
        ? osdSelects.map(s => s.value).filter(v => v !== '')
        : JSON.parse(card.dataset.savedCephDisks || '[]')
    };
  });
}

function collectState() {
  const vms = {};
  document.querySelectorAll('.vm-toggle').forEach(cb => {
    const row = cb.closest('tr');
    vms[cb.getAttribute('data-id')] = {
      active: cb.checked,
      node: row.querySelector('.vm-node').value,
      cores: row.querySelector('.vm-cores').value,
      ram: row.querySelector('.vm-ram').value,
      disk: row.querySelector('.vm-disk').value
    };
  });

  return {
    activeStep,
    general: {
      iso: document.getElementById('bm-iso-version').value || loadState()?.general?.iso || '',
      interface: document.getElementById('bm-interface').value,
      gateway: document.getElementById('bm-gateway').value,
      dns: document.getElementById('bm-dns').value,
      domain: document.getElementById('bm-domain').value,
      mailto: document.getElementById('bm-mailto').value,
      filesystem: document.getElementById('bm-filesystem').value,
      keyboard: document.getElementById('bm-keyboard').value,
      country: document.getElementById('bm-country').value,
      timezone: document.getElementById('bm-timezone').value
    },
    cluster: {
      enabled: isClusterEnabled(),
      name: document.getElementById('bm-cluster-name').value,
      pool: document.getElementById('bm-ceph-pool').value,
      size: document.getElementById('bm-ceph-size').value,
      minSize: document.getElementById('bm-ceph-min-size').value,
      sizeEdited: document.getElementById('bm-ceph-size').dataset.edited === 'true',
      minSizeEdited: document.getElementById('bm-ceph-min-size').dataset.edited === 'true'
    },
    nodeCount: document.getElementById('bm-node-count').value,
    nodes: collectNodeStates(),
    step2: {
      proxmoxIp: document.getElementById('proxmox-ip').value,
      subnetPrefix: document.getElementById('subnet-prefix').value,
      startIp: document.getElementById('start-ip').value,
      sshKeys: document.getElementById('ssh-keys').value,
      vms
    }
  };
}

function saveState() {
  if (restoring) return;
  try {
    localStorage.setItem(STATE_KEY, JSON.stringify(collectState()));
  } catch {
    // localStorage utilgængelig (f.eks. privat browsing) - ignorer
  }
}

function applyNodeStates(nodeStates) {
  document.querySelectorAll('.node-card').forEach((card, i) => {
    const node = nodeStates[i];
    if (!node) return;
    card.querySelector('.bm-node-mac').value = node.mac || '';
    card.querySelector('.bm-node-host').value = node.host || '';
    card.querySelector('.bm-node-ip').value = node.ip || '';
    card.dataset.savedDisk = node.disk || '';
    card.dataset.savedCephDisks = JSON.stringify(node.cephDisks || []);
    const cephToggle = card.querySelector('.bm-ceph-toggle');
    cephToggle.checked = !!node.ceph;
    document.getElementById(`ceph-options-${i}`).style.display = node.ceph ? 'block' : 'none';
  });
}

function applyClusterState(cluster) {
  if (!cluster) return;
  document.getElementById('bm-create-cluster').checked = !!cluster.enabled;
  if (cluster.name) document.getElementById('bm-cluster-name').value = cluster.name;
  if (cluster.pool) document.getElementById('bm-ceph-pool').value = cluster.pool;
  if (cluster.size) document.getElementById('bm-ceph-size').value = cluster.size;
  if (cluster.minSize) document.getElementById('bm-ceph-min-size').value = cluster.minSize;
  document.getElementById('bm-ceph-size').dataset.edited = cluster.sizeEdited ? 'true' : '';
  document.getElementById('bm-ceph-min-size').dataset.edited = cluster.minSizeEdited ? 'true' : '';
}

async function restoreState() {
  restoring = true;
  const state = loadState();
  try {
    if (state) {
      showStep(state.activeStep === 2 ? 2 : 1);
      const g = state.general || {};
      document.getElementById('bm-interface').value = g.interface || '';
      document.getElementById('bm-gateway').value = g.gateway || '';
      document.getElementById('bm-dns').value = g.dns || '';
      ['domain', 'mailto', 'filesystem', 'keyboard', 'country', 'timezone'].forEach(key => {
        if (g[key]) document.getElementById(`bm-${key}`).value = g[key];
      });
      applyClusterState(state.cluster);

      const nodes = state.nodes || [];
      const count = Math.max(1, nodes.length || parseInt(state.nodeCount) || 1);
      document.getElementById('bm-node-count').value = count;
      renderNodeRows(count);
      applyNodeStates(nodes);

      const s2 = state.step2 || {};
      if (s2.proxmoxIp !== undefined) document.getElementById('proxmox-ip').value = s2.proxmoxIp;
      if (s2.subnetPrefix !== undefined) document.getElementById('subnet-prefix').value = s2.subnetPrefix;
      if (s2.startIp !== undefined) document.getElementById('start-ip').value = s2.startIp;
      if (s2.sshKeys !== undefined) document.getElementById('ssh-keys').value = s2.sshKeys;
      Object.entries(s2.vms || {}).forEach(([id, vm]) => {
        const row = document.getElementById(`row-${id}`);
        if (!row) return;
        row.querySelector('.vm-toggle').checked = !!vm.active;
        row.querySelector('.vm-node').value = vm.node;
        row.querySelector('.vm-cores').value = vm.cores;
        row.querySelector('.vm-ram').value = vm.ram;
        row.querySelector('.vm-disk').value = vm.disk;
      });
    }

    // Intet gemt i denne browser: hent MAC-adresserne fra den aktive PXE-session på serveren.
    const hasMacs = (state?.nodes || []).some(n => n.mac);
    if (!hasMacs) {
      const res = await fetch('/api/baremetal/nodes');
      const data = await res.json();
      if (data.nodes && data.nodes.length > 0) {
        if (data.create_cluster) applyClusterState({ enabled: true });
        document.getElementById('bm-node-count').value = data.nodes.length;
        renderNodeRows(data.nodes.length);
        applyNodeStates(data.nodes.map(n => ({
          mac: n.mac_address,
          host: n.hostname === 'discovery-temp' ? '' : n.hostname,
          ip: data.mode === 'install' ? n.ip : '',
          disk: data.mode === 'install' ? n.disk : '',
          ceph: !!n.enable_ceph,
          cephDisks: n.ceph_disks || []
        })));
      }
    }
  } catch {
    // Backend utilgængelig - behold det der er gendannet lokalt
  } finally {
    restoring = false;
  }
  updateClusterVisibility();
  saveState();
  checkDiscoveredDisks();
}

document.getElementById('app').addEventListener('input', saveState);
document.getElementById('app').addEventListener('change', saveState);
// Fjern-OSD knappen ændrer DOM'en uden input/change event
document.getElementById('app').addEventListener('click', () => setTimeout(saveState, 0));

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
        <div class="node-status" style="display: none; font-size: 12px; margin: -0.4rem 0 0.6rem 0; color: #004085;"></div>

        <!-- System- & Netværksindstillinger (Skjult indtil Discovery) -->
        <div class="config-section" style="border-top: 1px solid #eee; padding-top: 0.8rem; margin-top: 0.5rem; opacity: 0.6;">
          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; margin-bottom: 0.8rem;">
            <div>
              <label style="font-size:12px;"><b>Hostname:</b></label><br>
              <input type="text" class="bm-node-host" placeholder="f.eks. proxmox-node${i+1}" disabled style="width: 90%; padding: 4px;">
            </div>
            <div>
              <label style="font-size:12px;"><b>Statisk IP:</b></label><br>
              <input type="text" class="bm-node-ip" placeholder="f.eks. 10.20.10.${10+i}" disabled style="width: 90%; padding: 4px;">
            </div>
            <div>
              <label style="font-size:12px;"><b>OS-disk (Proxmox):</b></label><br>
              <select class="bm-node-disk" disabled style="width: 95%; padding: 4px;">
                <option value="">Start Discovery for at vælge disk...</option>
              </select>
            </div>
          </div>

          <!-- Ceph Sektion (vises kun når "Opret Cluster?" er valgt) -->
          <div class="ceph-section" style="display: ${isClusterEnabled() ? 'block' : 'none'}; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px dashed #ccc;">
            <label style="font-size: 13px; cursor: pointer;">
              <input type="checkbox" class="bm-ceph-toggle" data-index="${i}" disabled>
              <b>Brug denne node i Ceph</b> <span style="color: #dc3545; font-size: 12px;">(valgte OSD-diske slettes)</span>
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
      refreshCephDefaults();
    });
  });

  // Tilføj OSD Knap lytter
  document.querySelectorAll('.btn-add-osd').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = e.target.getAttribute('data-index');
      addOsdDropdown(idx);
    });
  });

  updateProvisioningGate();
}

function updateProvisioningGate() {
  const cards = Array.from(document.querySelectorAll('.node-card'));
  const allDiscovered = cards.length > 0 && cards.every(card => card.dataset.discovered === 'true');
  const generalSettings = document.getElementById('bm-general-settings');

  generalSettings.style.opacity = allDiscovered ? '1' : '0.55';
  generalSettings.querySelectorAll('input, select').forEach(input => {
    input.disabled = !allDiscovered;
  });
  document.getElementById('btn-start-pxe').disabled = !allDiscovered;

  cards.forEach(card => {
    const enabled = allDiscovered && card.dataset.discovered === 'true';
    card.querySelector('.config-section').style.opacity = enabled ? '1' : '0.6';
    card.querySelectorAll('.bm-node-host, .bm-node-ip, .bm-node-disk, .bm-ceph-toggle').forEach(input => {
      input.disabled = !enabled;
    });
  });
}

function isClusterEnabled() {
  const checkbox = document.getElementById('bm-create-cluster');
  return !!(checkbox && checkbox.checked);
}

function updateClusterVisibility() {
  const enabled = isClusterEnabled();
  document.getElementById('bm-cluster-options').style.display = enabled ? 'block' : 'none';
  document.querySelectorAll('.ceph-section').forEach(section => {
    section.style.display = enabled ? 'block' : 'none';
  });
  refreshCephDefaults();
}

function cephNodeCount() {
  if (!isClusterEnabled()) return 0;
  return Array.from(document.querySelectorAll('.bm-ceph-toggle')).filter(cb => cb.checked).length;
}

// Replika-felterne auto-udfyldes ud fra antal Ceph-noder, indtil brugeren selv ændrer dem.
function refreshCephDefaults() {
  const sizeInput = document.getElementById('bm-ceph-size');
  const minInput = document.getElementById('bm-ceph-min-size');
  const count = cephNodeCount();
  if (sizeInput.dataset.edited !== 'true' && count > 0) {
    sizeInput.value = Math.min(3, count);
  }
  if (minInput.dataset.edited !== 'true') {
    const currentSize = parseInt(sizeInput.value) || 1;
    minInput.value = currentSize - Math.floor(currentSize / 2);
  }
  const info = document.getElementById('bm-ceph-info');
  const size = parseInt(sizeInput.value) || 0;
  let warning = '';
  if (count > 0 && count < 3) warning = ` ⚠ Kun ${count} Ceph-node(r) valgt - Ceph anbefaler mindst 3.`;
  if (count > 0 && size > count) warning += ` ⚠ Replika size (${size}) er større end antal Ceph-noder (${count}).`;
  info.innerHTML = 'Vælg under hver node om den skal bruges i Ceph. Ceph-netværket beregnes automatisk ud fra nodernes IP. '
    + 'Cluster og Ceph oprettes automatisk når alle noder er installeret.'
    + (warning ? `<br><b style="color: #b45309;">${warning}</b>` : '');
}

document.getElementById('bm-create-cluster').addEventListener('change', updateClusterVisibility);
['bm-ceph-size', 'bm-ceph-min-size'].forEach(id => {
  document.getElementById(id).addEventListener('input', (e) => {
    e.target.dataset.edited = 'true';
    refreshCephDefaults();
  });
});

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
  return div.querySelector('select');
}

renderNodeRows(1);

document.getElementById('btn-render-nodes').addEventListener('click', () => {
  const count = parseInt(document.getElementById('bm-node-count').value) || 1;
  // Bevar allerede indtastede MAC'er m.m. når antallet ændres
  const existing = collectNodeStates();
  renderNodeRows(count);
  applyNodeStates(existing);
  saveState();
  checkDiscoveredDisks();
});

// Automatisk Polling for fundne diske fra Micro-Image
async function checkDiscoveredDisks() {
  try {
    const res = await fetch('/api/baremetal/nodes');
    const data = await res.json();
    if (!data.nodes) return;
    renderProgress(data);

    document.querySelectorAll('.node-card').forEach(card => {
      const macInput = card.querySelector('.bm-node-mac').value.toLowerCase().trim();
      if (!macInput) return;

      const matchingNode = data.nodes.find(n => n.mac_address && n.mac_address.toLowerCase() === macInput);
      renderNodeStatus(card, matchingNode);

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
        card.dataset.discovered = 'true';

        const currentOsVal = osSelect.value;

        // Indsæt fundne diske i dropdown
        let diskOptionsHtml = matchingNode.discovered_disks.map(d => 
          `<option value="${d.name}">${d.name} (${d.size} - ${d.model})</option>`
        ).join('');

        osSelect.innerHTML = diskOptionsHtml;
        const wantedOsVal = currentOsVal || card.dataset.savedDisk;
        if (wantedOsVal && matchingNode.discovered_disks.some(d => d.name === wantedOsVal)) {
          osSelect.value = wantedOsVal;
        }

        // Gem options til brug for Ceph
        card.setAttribute('data-disk-options', diskOptionsHtml);

        const cephContainer = card.querySelector('.ceph-dropdown-container');
        if (cephContainer.children.length === 0) {
          const savedCephDisks = JSON.parse(card.dataset.savedCephDisks || '[]');
          if (savedCephDisks.length === 0) {
            addOsdDropdown(card.getAttribute('data-index'), diskOptionsHtml);
          } else {
            savedCephDisks.forEach(diskName => {
              const select = addOsdDropdown(card.getAttribute('data-index'), diskOptionsHtml);
              select.value = diskName;
            });
          }
          saveState();
        }
      }
    });
    updateProvisioningGate();
  } catch (e) {
    // Stille fejlhåndtering
  }
}

const NODE_STATUS_LABELS = {
  waiting_discovery: ['Afventer discovery', '#856404'],
  discovered: ['Diske fundet', '#155724'],
  waiting_install: ['Afventer genstart til installation', '#856404'],
  install_requested: ['Genstarter til installation', '#004085'],
  installing: ['Installerer Proxmox', '#004085'],
  installed: ['Proxmox installeret - første opstart', '#004085'],
  ready: ['Klar', '#155724'],
  clustered: ['I cluster', '#155724'],
  ceph_ready: ['Cluster + Ceph klar', '#155724'],
  error: ['Fejl', '#dc3545']
};

function renderNodeStatus(card, node) {
  const line = card.querySelector('.node-status');
  if (!node || !node.status || node.status === 'waiting_discovery' || node.status === 'discovered') {
    line.style.display = 'none';
    return;
  }
  const [label, color] = NODE_STATUS_LABELS[node.status] || [node.status, '#333'];
  line.style.display = 'block';
  line.style.color = color;
  line.textContent = `Status: ${node.status_message || label}`;
}

function renderProgress(data) {
  const box = document.getElementById('bm-progress');
  if (data.mode !== 'install') {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'block';
  box.style.background = data.phase === 'error' ? '#f8d7da' : '#e7f1ff';
  document.getElementById('bm-phase-message').textContent = `Installation: ${data.phase_message || data.phase || ''}`;

  const cluster = data.cluster || {};
  const clusterLine = document.getElementById('bm-cluster-message');
  const retryButton = document.getElementById('btn-retry-cluster');
  const logBox = document.getElementById('bm-cluster-log-box');
  if (!data.create_cluster || cluster.status === 'disabled') {
    clusterLine.textContent = '';
    retryButton.style.display = 'none';
    logBox.style.display = 'none';
    return;
  }
  const clusterLabels = {
    pending: 'Venter på at alle noder er installeret',
    running: 'Opretter...',
    done: 'Færdig',
    error: 'Fejlet'
  };
  clusterLine.textContent = `Cluster/Ceph: ${clusterLabels[cluster.status] || cluster.status || ''}${cluster.message ? ' - ' + cluster.message : ''}`;
  clusterLine.style.color = cluster.status === 'error' ? '#dc3545' : '';
  retryButton.style.display = cluster.status === 'error' ? 'inline-block' : 'none';
  const log = cluster.log || [];
  logBox.style.display = log.length ? 'block' : 'none';
  document.getElementById('bm-cluster-log').textContent = log.join('\n');
}

document.getElementById('btn-retry-cluster').addEventListener('click', async () => {
  const res = await fetch('/api/baremetal/cluster/retry', { method: 'POST' });
  const data = await res.json();
  if (!res.ok) alert(data.detail || 'Kunne ikke starte cluster-opsætning igen.');
  checkDiscoveredDisks();
});

// Tjek for diske hvert 3. sekund
setInterval(checkDiscoveredDisks, 3000);

restoreState();

// 1. Start Discovery Mode
document.getElementById('btn-start-discovery').addEventListener('click', async () => {
  const nodes = [];
  document.querySelectorAll('.node-card').forEach(card => {
    const mac = card.querySelector('.bm-node-mac').value.trim();
    if (mac) {
      nodes.push({
        hostname: "discovery-temp",
        mac_address: mac,
        ip: "0.0.0.0", // Backend udleder og overskriver denne ud fra NIC'ets faktiske subnet
        disk: "sda"
      });
    }
  });

  if (nodes.length === 0) {
    alert("Indtast venligst mindst én MAC-adresse først!");
    return;
  }

  const payload = {
    interface: document.getElementById('bm-interface').value.trim() || null,
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
  if (!res.ok) {
    if (data.detail && data.detail.includes('PXE-interface')) {
      const interfaceInput = document.getElementById('bm-interface');
      interfaceInput.disabled = false;
      interfaceInput.placeholder = 'Angiv PXE-interface, f.eks. enp1s0';
      document.getElementById('bm-general-settings').style.opacity = '1';
    }
    alert(data.detail || data.message || "Discovery PXE kunne ikke startes.");
    return;
  }
  alert("Discovery PXE startet! Tænd nu serverne. De rapporterer deres diske og bliver derefter tændt og venter, indtil du starter Proxmox installationen.");
});

// 2. Start Proxmox Auto-Installation
document.getElementById('btn-start-pxe').addEventListener('click', async () => {
  const selectedIso = document.getElementById('bm-iso-version').value;
  if (!selectedIso) {
    alert('Vælg venligst en Proxmox ISO-fil!');
    return;
  }

  const createCluster = isClusterEnabled();
  const nodes = [];
  document.querySelectorAll('.node-card').forEach(card => {
    const cephToggle = createCluster && card.querySelector('.bm-ceph-toggle').checked;
    const osdSelects = card.querySelectorAll('.bm-ceph-osd-select');
    const selectedCephDisks = cephToggle ? Array.from(osdSelects).map(s => s.value).filter(v => v !== "") : [];

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
    domain: document.getElementById('bm-domain').value.trim(),
    mailto: document.getElementById('bm-mailto').value.trim(),
    filesystem: document.getElementById('bm-filesystem').value,
    keyboard: document.getElementById('bm-keyboard').value.trim(),
    country: document.getElementById('bm-country').value.trim().toLowerCase(),
    timezone: document.getElementById('bm-timezone').value.trim(),
    create_cluster: createCluster,
    cluster_name: document.getElementById('bm-cluster-name').value.trim(),
    ceph_pool: document.getElementById('bm-ceph-pool').value.trim(),
    ceph_size: parseInt(document.getElementById('bm-ceph-size').value) || 3,
    ceph_min_size: parseInt(document.getElementById('bm-ceph-min-size').value) || 2,
    nodes: nodes
  };

  const osDisks = nodes.map(n => `${n.hostname || n.mac_address}: ${n.disk}${n.enable_ceph ? ' + OSD ' + n.ceph_disks.join(', ') : ''}`).join('\n');
  if (!confirm(`ADVARSEL: Følgende diske bliver SLETTET og Proxmox installeres:\n\n${osDisks}\n\nFortsæt?`)) {
    return;
  }

  const res = await fetch('/api/baremetal/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || data.message || "Proxmox PXE kunne ikke startes.");
    return;
  }
  alert(data.message || 'Proxmox PXE Installation startet!');
  checkDiscoveredDisks();
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
