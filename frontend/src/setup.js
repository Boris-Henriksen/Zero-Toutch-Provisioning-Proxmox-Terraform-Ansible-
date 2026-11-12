// Setup-side: vises før portalen indtil serveren har en Proxmox ISO og et discovery-image (Ubuntu).
// Filer kan trækkes ind, vælges, eller hentes af serveren via et download-link.

const CARDS = [
  {
    kind: 'proxmox',
    title: '1. Proxmox VE ISO',
    help: 'Den Proxmox-version der installeres på noderne. Hent den fra proxmox.com/downloads (højreklik på "Download" og kopiér linket).',
    placeholder: 'https://enterprise.proxmox.com/iso/proxmox-ve_9.2-1.iso',
  },
  {
    kind: 'ubuntu',
    title: '2. Ubuntu Server live ISO (discovery)',
    help: 'Bruges til at scanne nodernes diske før installationen. Skal være Ubuntu Server amd64 "live-server". Serveren udpakker den selv bagefter.',
    placeholder: 'https://releases.ubuntu.com/26.04/ubuntu-26.04-live-server-amd64.iso',
  },
];

const STRIPES = 'linear-gradient(45deg, rgba(255,255,255,.25) 25%, transparent 25%, transparent 50%, rgba(255,255,255,.25) 50%, rgba(255,255,255,.25) 75%, transparent 75%, transparent)';

const STAGE_TEXT = {
  uploading: 'Uploader',
  downloading: 'Downloader',
  verifying: 'Tjekker ISO-filen...',
  preparing: 'Udpakker kernel/initrd og klargør discovery-image...',
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function formatBytes(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

export function initSetup({ onShowPortal }) {
  const page = document.getElementById('setup-page');
  const portal = document.getElementById('portal-page');
  let pollTimer = null;
  const localError = {};

  page.innerHTML = `
    <div style="max-width: 950px; margin: 2rem auto; font-family: sans-serif;">
      <h2>Infrastruktur Portal - Setup</h2>
      <p style="color: #555; font-size: 14px;">
        Før portalen kan bruges, skal serveren have en <b>Proxmox VE ISO</b> og en <b>Ubuntu Server live ISO</b>.
        Træk filerne ind herunder, eller indsæt et download-link, så henter serveren dem selv.
      </p>
      ${CARDS.map(card => `
        <div class="setup-card" data-kind="${card.kind}" style="border: 1px solid #ccc; border-radius: 6px; padding: 1.2rem; margin-bottom: 1.2rem;">
          <h3 style="margin-top: 0;">${card.title}</h3>
          <p style="font-size: 13px; color: #666; margin-top: -0.4rem;">${card.help}</p>
          <div class="setup-current" style="font-size: 13px; margin-bottom: 0.8rem;"></div>
          <div class="setup-drop" style="border: 2px dashed #9bb7d4; border-radius: 6px; padding: 1.4rem; text-align: center; color: #446; background: #f5f9fd; cursor: pointer;">
            Træk <b>.iso</b>-filen hertil, eller klik for at vælge den
            <input type="file" class="setup-file" accept=".iso" style="display: none;">
          </div>
          <div style="display: flex; gap: 8px; margin-top: 0.8rem; align-items: center;">
            <span style="font-size: 13px; white-space: nowrap;">eller download-link:</span>
            <input type="url" class="setup-url" placeholder="${card.placeholder}" style="flex-grow: 1; padding: 6px;">
            <button class="setup-download" style="padding: 6px 14px; cursor: pointer;">Hent</button>
          </div>
          <div class="setup-progress" style="display: none; margin-top: 0.9rem;">
            <div style="height: 16px; background: #fff; border: 1px solid #cfd8e3; border-radius: 8px; overflow: hidden;">
              <div class="setup-bar" style="height: 100%; width: 0%; transition: width 0.6s ease; background-size: 16px 16px;"></div>
            </div>
            <div class="setup-text" style="font-size: 12px; color: #444; margin-top: 3px;"></div>
          </div>
        </div>`).join('')}
      <div style="display: flex; gap: 12px; align-items: center;">
        <button id="setup-continue" style="padding: 10px 20px; background: #28a745; color: white; border: none; cursor: pointer; font-weight: bold;">
          Fortsæt til portalen →
        </button>
        <span id="setup-continue-info" style="font-size: 13px; color: #666;"></span>
      </div>
    </div>`;

  function show(setup) {
    page.style.display = setup ? 'block' : 'none';
    portal.style.display = setup ? 'none' : 'block';
    clearInterval(pollTimer);
    if (setup) {
      refresh();
      pollTimer = setInterval(refresh, 1500);
    } else {
      onShowPortal();
    }
  }

  function renderCard(card, status) {
    const el = page.querySelector(`.setup-card[data-kind="${card.kind}"]`);
    const files = card.kind === 'proxmox' ? status.proxmox_isos : status.ubuntu_isos;
    const ok = card.kind === 'proxmox' ? files.length > 0 : status.discovery_ready;
    let current = ok ? '✅ ' : '⚠ Mangler. ';
    if (card.kind === 'proxmox') {
      current += files.length ? `På serveren: ${files.map(escapeHtml).join(', ')}` : 'Ingen Proxmox ISO på serveren endnu.';
    } else {
      current += status.discovery_ready
        ? `Discovery-image klar fra ${escapeHtml(status.discovery_source)}.${files.length > 1 ? ' Uploader du en ny, bruges den i stedet.' : ''}`
        : 'Discovery-image er ikke klar endnu.';
    }
    const currentEl = el.querySelector('.setup-current');
    currentEl.innerHTML = current;
    currentEl.style.color = ok ? '#155724' : '#856404';

    const job = status.jobs.find(j => j.kind === card.kind);
    const box = el.querySelector('.setup-progress');
    const bar = el.querySelector('.setup-bar');
    const text = el.querySelector('.setup-text');
    const busy = job && !['done', 'error'].includes(job.stage);
    el.querySelectorAll('.setup-download, .setup-url, .setup-file').forEach(i => { i.disabled = busy; });
    el.querySelector('.setup-drop').style.opacity = busy ? '0.5' : '1';

    if (localError[card.kind]) {
      box.style.display = 'block';
      bar.style.width = '100%';
      bar.style.backgroundColor = '#dc3545';
      bar.style.backgroundImage = 'none';
      text.textContent = localError[card.kind];
      text.style.color = '#dc3545';
      return;
    }
    if (!job) {
      box.style.display = 'none';
      return;
    }
    box.style.display = 'block';
    text.style.color = job.stage === 'error' ? '#dc3545' : '#444';
    let percent = 100;
    let label;
    if (job.stage === 'uploading' || job.stage === 'downloading') {
      percent = job.total ? (100 * job.done) / job.total : 0;
      label = `${STAGE_TEXT[job.stage]} ${escapeHtml(job.filename)}: ${formatBytes(job.done)}${job.total ? ' / ' + formatBytes(job.total) : ''}`;
      if (job.rate > 0) {
        label += ` (${(job.rate / 1e6).toFixed(1)} MB/s`;
        if (job.total) {
          const eta = Math.round((job.total - job.done) / job.rate);
          label += `, ca. ${Math.floor(eta / 60)}:${String(eta % 60).padStart(2, '0')} tilbage`;
        }
        label += ')';
      }
      label = `${Math.round(percent)}% - ${label}`;
    } else if (job.stage === 'verifying' || job.stage === 'preparing') {
      label = STAGE_TEXT[job.stage];
    } else {
      label = job.message || job.stage;
    }
    const striped = job.stage === 'verifying' || job.stage === 'preparing' || (!job.total && busy);
    bar.style.width = `${Math.min(100, percent)}%`;
    bar.style.backgroundColor = job.stage === 'error' ? '#dc3545' : job.stage === 'done' ? '#28a745' : '#007bff';
    bar.style.backgroundImage = striped ? STRIPES : 'none';
    bar.style.animation = striped ? 'node-progress-stripes 1s linear infinite' : 'none';
    text.innerHTML = label;
  }

  async function refresh() {
    try {
      const res = await fetch('/api/setup/status');
      if (!res.ok) return null;
      const status = await res.json();
      CARDS.forEach(card => renderCard(card, status));
      const button = document.getElementById('setup-continue');
      button.disabled = !status.ready;
      button.style.opacity = status.ready ? '1' : '0.5';
      button.style.cursor = status.ready ? 'pointer' : 'not-allowed';
      document.getElementById('setup-continue-info').textContent = status.ready
        ? '' : 'Bliver aktiv når begge filer er klar.';
      return status;
    } catch {
      return null;
    }
  }

  async function upload(kind, file) {
    localError[kind] = '';
    if (!file.name.toLowerCase().endsWith('.iso')) {
      localError[kind] = `${file.name} er ikke en .iso-fil.`;
      refresh();
      return;
    }
    // Lad polling vise fremskridtet - serveren opretter jobbet så snart uploaden starter.
    setTimeout(refresh, 500);
    try {
      const res = await fetch(`/api/setup/upload/${kind}?filename=${encodeURIComponent(file.name)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        localError[kind] = res.status === 413
          ? 'Filen er for stor til webserveren (nginx). Kør "sudo ./install.sh" igen for at hæve grænsen.'
          : (data.detail || `Upload fejlede (HTTP ${res.status}).`);
      }
    } catch (err) {
      localError[kind] = `Upload fejlede: ${err.message}`;
    }
    refresh();
  }

  async function download(kind, url) {
    localError[kind] = '';
    if (!url) {
      localError[kind] = 'Indsæt et download-link først.';
      refresh();
      return;
    }
    const res = await fetch('/api/setup/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, url }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      localError[kind] = data.detail || `Download kunne ikke startes (HTTP ${res.status}).`;
    }
    refresh();
  }

  page.querySelectorAll('.setup-card').forEach(el => {
    const kind = el.dataset.kind;
    const drop = el.querySelector('.setup-drop');
    const fileInput = el.querySelector('.setup-file');
    drop.addEventListener('click', () => { if (!fileInput.disabled) fileInput.click(); });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) upload(kind, fileInput.files[0]);
      fileInput.value = '';
    });
    drop.addEventListener('dragover', (e) => {
      e.preventDefault();
      drop.style.background = '#e2eefa';
    });
    drop.addEventListener('dragleave', () => { drop.style.background = '#f5f9fd'; });
    drop.addEventListener('drop', (e) => {
      e.preventDefault();
      drop.style.background = '#f5f9fd';
      if (fileInput.disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) upload(kind, file);
    });
    el.querySelector('.setup-download').addEventListener('click', () => {
      download(kind, el.querySelector('.setup-url').value.trim());
    });
  });

  document.getElementById('setup-continue').addEventListener('click', () => show(false));
  // En upload i gang må ikke afbrydes ved et uheld.
  window.addEventListener('beforeunload', (e) => {
    if (page.style.display !== 'none' && page.querySelector('.setup-download:disabled')) e.preventDefault();
  });

  // Er backend utilgængelig, vises portalen som før (den viser selv fejl).
  refresh().then(status => show(status ? !status.ready : false));

  return { open: () => show(true) };
}
