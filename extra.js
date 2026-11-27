// Extra features. Uses read, write, esc, me, ideas and page from app.js

const profiles = read('profiles', {});  // investor criteria
const views = read('views', {});        // pitch views
const tracker = read('tracker', {});    // developer's investor list
const sectors = ['Any', 'AgriTech', 'FinTech', 'EdTech', 'HealthTech', 'Other'];
const options = (list, chosen) => list.map(x => '<option' + (x === chosen ? ' selected' : '') + '>' + x + '</option>').join('');
const rupees = n => 'Rs ' + Number(n).toLocaleString('en-IN');

// ---------- 1. Count pitch views ----------
let viewed = page.startsWith('pitch-') && page !== 'pitch-form' ? page.replace('pitch-', '') : '';
if (page === 'idea') viewed = read('selected', '');
const own = ideas.some(i => i.id === viewed && me && i.owner === me.name);
if (viewed && !own) {
  views[viewed] = (views[viewed] || 0) + 1;
  write('views', views);
}

// ---------- 2. Search box on Browse ----------
if (page === 'browse') {
  const grid = document.querySelector('.filter .grid');
  document.querySelector('.filter .top').insertAdjacentHTML('afterend', '<input id="search" class="search" placeholder="Search ideas">');
  document.getElementById('search').oninput = function () {
    const word = this.value.toLowerCase();
    [...grid.children].forEach(card => card.style.display = card.textContent.toLowerCase().includes(word) ? '' : 'none');
  };
}

// ---------- 3. Investor: deal criteria and matching ideas ----------
if (page === 'dashboard-investor' && me && me.role === 'investor') {
  const mine = profiles[me.name] || { sector: 'Any', max: 1000000 };
  const all = ideas.concat([
    { id: 'waterwise', title: 'WaterWise Drip', cat: 'AgriTech', ask: 400000 },
    { id: 'rentcircle', title: 'RentCircle', cat: 'FinTech', ask: 750000 },
    { id: 'classpulse', title: 'ClassPulse', cat: 'EdTech', ask: 250000 }
  ]);
  const matches = profiles[me.name] ? all.filter(i => (mine.sector === 'Any' || i.cat === mine.sector) && i.ask <= mine.max) : [];
  document.querySelector('.panel').insertAdjacentHTML('beforeend',
    '<h3 class="part">Your deal criteria</h3><form id="criteria"><label>Sector<select>' + options(sectors, mine.sector) + '</select></label>' +
    '<label>Largest amount you invest (Rs)<input type="number" min="1000" required value="' + Number(mine.max) + '"></label>' +
    '<button class="btn full">Save criteria</button></form><h3 class="part">Matching ideas</h3>' +
    (matches.map(i => '<div class="box"><b>' + esc(i.title) + '</b> · ' + rupees(i.ask) + ' <a href="' +
      (['waterwise', 'rentcircle', 'classpulse'].includes(i.id) ? 'pitch-' + i.id + '.html' : 'idea.html') +
      '" data-view="' + i.id + '">View</a></div>').join('') || '<p class="muted">Save your criteria to see matches.</p>'));
  const form = document.getElementById('criteria');
  form.onsubmit = function (event) {
    event.preventDefault();
    profiles[me.name] = { sector: form.querySelector('select').value, max: Number(form.querySelector('input').value) };
    write('profiles', profiles);
    location.reload();
  };
  document.querySelectorAll('[data-view]').forEach(a => a.onclick = () => write('selected', a.dataset.view));
}

// ---------- 4. Developer: views and fundraising tracker ----------
if (page === 'dashboard-developer' && me && me.role === 'developer') {
  const stages = ['To contact', 'Contacted', 'In talks', 'Funded', 'Passed'];
  const rows = tracker[me.name] || [];
  const seen = ideas.filter(i => i.owner === me.name)
    .map(i => '<div class="box"><b>' + esc(i.title) + '</b>: ' + (views[i.id] || 0) + ' views</div>').join('');
  document.querySelector('.panel').insertAdjacentHTML('beforeend',
    '<h3 class="part">Pitch views</h3>' + (seen || '<p class="muted">No ideas yet.</p>') +
    '<h3 class="part">Fundraising tracker</h3><div id="rows"></div>' +
    '<form id="add"><label>Investor name<input required maxlength="40"></label><button class="btn full">Add to tracker</button></form>');
  const area = document.getElementById('rows');
  function save() {
    tracker[me.name] = rows;
    write('tracker', tracker);
    area.innerHTML = rows.map((r, n) => '<div class="box"><b>' + esc(r.name) + '</b><select data-n="' + n + '">' +
      options(stages, r.stage) + '</select><button class="btn small" data-del="' + n + '">Remove</button></div>').join('') ||
      '<p class="muted">Add the investors you are talking to.</p>';
  }
  area.onchange = e => { rows[e.target.dataset.n].stage = e.target.value; save(); };
  area.onclick = e => { if (e.target.dataset.del) { rows.splice(e.target.dataset.del, 1); save(); } };
  const add = document.getElementById('add');
  add.onsubmit = function (event) {
    event.preventDefault();
    const name = add.querySelector('input').value.trim();
    if (!name) return;
    rows.push({ name, stage: stages[0] });
    add.reset();
    save();
  };
  save();
}
