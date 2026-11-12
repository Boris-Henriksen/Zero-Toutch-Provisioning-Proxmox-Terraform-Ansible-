// Søgbar dropdown oven på et almindeligt <input>. Inputtets value er altid en gyldig kode,
// så eksisterende kode der læser/sætter .value virker uændret.

const normalize = (s) => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

export function createCombobox(input, options) {
  const byCode = new Map(options.map(o => [o.value.toLowerCase(), o]));
  let lastValid = input.value;
  let filtered = [];
  let active = -1;

  const wrapper = document.createElement('div');
  wrapper.style.cssText = `position: relative; width: ${input.style.width || '100%'};`;
  input.parentNode.insertBefore(wrapper, input);
  const field = document.createElement('div');
  field.style.cssText = 'position: relative;';
  wrapper.appendChild(field);
  field.appendChild(input);
  input.style.width = '100%';
  input.style.boxSizing = 'border-box';
  input.style.paddingRight = '22px';

  // Pilen lader klik gå igennem til inputtet, som så åbner listen.
  const arrow = document.createElement('span');
  arrow.textContent = '▾';
  arrow.setAttribute('aria-hidden', 'true');
  arrow.style.cssText = 'position: absolute; right: 7px; top: 50%; transform: translateY(-50%); pointer-events: none; font-size: 12px; color: #555;';
  field.appendChild(arrow);
  input.setAttribute('autocomplete', 'off');
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  input.placeholder = input.placeholder || 'Søg...';

  const list = document.createElement('ul');
  list.setAttribute('role', 'listbox');
  list.style.cssText = 'display: none; position: absolute; z-index: 1000; left: 0; top: 100%; min-width: 100%; width: max-content; max-width: 340px;'
    + ' max-height: 240px; overflow-y: auto; margin: 2px 0 0; padding: 0; list-style: none; background: #fff; color: #222;'
    + ' border: 1px solid #aaa; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.15); font-size: 13px;';
  field.appendChild(list);

  const hint = document.createElement('div');
  hint.style.cssText = 'font-size: 12px; color: #666; margin-top: 2px; min-height: 1em;';
  wrapper.appendChild(hint);

  function refresh() {
    const opt = byCode.get(input.value.trim().toLowerCase());
    if (opt) {
      input.value = opt.value;
      lastValid = opt.value;
    }
    hint.textContent = opt && opt.label !== opt.value ? opt.label : '';
    input.title = hint.textContent;
  }

  function render() {
    list.innerHTML = '';
    if (filtered.length === 0) {
      const li = document.createElement('li');
      li.textContent = 'Ingen match';
      li.style.cssText = 'padding: 5px 8px; color: #888;';
      list.appendChild(li);
      return;
    }
    filtered.forEach((opt, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.style.cssText = `padding: 5px 8px; cursor: pointer; white-space: nowrap; background: ${i === active ? '#007bff' : 'transparent'}; color: ${i === active ? '#fff' : 'inherit'};`;
      const code = document.createElement('b');
      code.textContent = opt.value;
      li.appendChild(code);
      if (opt.label !== opt.value) li.appendChild(document.createTextNode(` – ${opt.label}`));
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        choose(opt);
      });
      list.appendChild(li);
    });
    list.children[active]?.scrollIntoView({ block: 'nearest' });
  }

  function open(query) {
    const q = normalize(query.trim());
    filtered = q ? options.filter(o => o.search.includes(q)) : options;
    const current = filtered.findIndex(o => o.value === lastValid);
    active = q ? 0 : Math.max(current, 0);
    list.style.display = 'block';
    input.setAttribute('aria-expanded', 'true');
    render();
  }

  function close() {
    list.style.display = 'none';
    input.setAttribute('aria-expanded', 'false');
  }

  function choose(opt) {
    input.value = opt.value;
    refresh();
    close();
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  input.addEventListener('focus', () => {
    input.select();
    open('');
  });
  input.addEventListener('click', () => {
    if (list.style.display === 'none') open('');
  });
  input.addEventListener('input', () => open(input.value));
  input.addEventListener('blur', () => {
    close();
    // Ugyldig fritekst afvises - vend tilbage til sidst valgte værdi.
    if (!byCode.has(input.value.trim().toLowerCase())) input.value = lastValid;
    refresh();
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  input.addEventListener('keydown', (e) => {
    if (list.style.display === 'none') {
      if (e.key === 'ArrowDown') open('');
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (filtered.length === 0) return;
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + filtered.length) % filtered.length;
      render();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[active]) choose(filtered[active]);
    } else if (e.key === 'Escape') {
      input.value = lastValid;
      close();
    }
  });

  refresh();
  return { refresh };
}

export function toOptions(entries) {
  return entries.map(([value, label, extra = '']) => ({ value, label, search: normalize(`${value} ${label} ${extra}`) }));
}

export const KEYBOARD_OPTIONS = toOptions([
  ['de', 'Tysk'], ['de-ch', 'Tysk (Schweiz)'], ['dk', 'Dansk'], ['en-gb', 'Engelsk (UK)'],
  ['en-us', 'Engelsk (US)'], ['es', 'Spansk'], ['fi', 'Finsk'], ['fr', 'Fransk'],
  ['fr-be', 'Fransk (Belgien)'], ['fr-ca', 'Fransk (Canada)'], ['fr-ch', 'Fransk (Schweiz)'],
  ['hu', 'Ungarsk'], ['is', 'Islandsk'], ['it', 'Italiensk'], ['jp', 'Japansk'], ['lt', 'Litauisk'],
  ['mk', 'Makedonsk'], ['nl', 'Hollandsk'], ['no', 'Norsk'], ['pl', 'Polsk'], ['pt', 'Portugisisk'],
  ['pt-br', 'Portugisisk (Brasilien)'], ['se', 'Svensk'], ['si', 'Slovensk'], ['tr', 'Tyrkisk']
]);

const COUNTRY_CODES = ('ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz '
  + 'ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg eh er es et fi fj fk fm fo fr '
  + 'ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp '
  + 'ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml mm mn mo mp mq mr ms mt '
  + 'mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw '
  + 'sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug '
  + 'um us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw').split(' ');

function countryOptions() {
  let names = null;
  try {
    names = new Intl.DisplayNames(['da'], { type: 'region' });
  } catch {
    // Ældre browser uden Intl.DisplayNames - vis kun koderne
  }
  const entries = COUNTRY_CODES.map(code => [code, names?.of(code.toUpperCase()) || code]);
  entries.sort((a, b) => a[1].localeCompare(b[1], 'da'));
  return toOptions(entries);
}

function timezoneOptions() {
  let zones = [];
  try {
    zones = Intl.supportedValuesOf('timeZone');
  } catch {
    // Fallback hvis browseren ikke kan liste tidszoner
  }
  const all = new Set([...zones, 'UTC', 'Europe/Copenhagen']);
  return toOptions([...all].sort().map(tz => [tz, tz, tz.replace(/_/g, ' ')]));
}

export const COUNTRY_OPTIONS = countryOptions();
export const TIMEZONE_OPTIONS = timezoneOptions();
