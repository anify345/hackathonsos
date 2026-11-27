// Search, investor criteria, pitch views, and the fundraising tracker.

window.IdeaHubReady.then(async function (hub) {
  const { api, state, me, ideas, page, samples, esc, selectIdea } = hub;
  const sectors = ['Any', 'AgriTech', 'FinTech', 'EdTech', 'HealthTech', 'Other'];
  const stages = ['To contact', 'Contacted', 'In talks', 'Funded', 'Passed'];
  const options = (list, chosen) => list.map(value =>
    '<option' + (value === chosen ? ' selected' : '') + '>' + value + '</option>'
  ).join('');
  const rupees = amount => 'Rs ' + Number(amount).toLocaleString('en-IN');

  let viewed = page.startsWith('pitch-') && page !== 'pitch-form'
    ? page.replace('pitch-', '')
    : '';
  if (page === 'idea') viewed = localStorage.getItem('selected') || '';
  const own = ideas.some(idea => idea.id === viewed && me && idea.owner === me.name);
  if (viewed && !own) {
    try {
      await api('/api/views', {
        method: 'POST',
        body: JSON.stringify({ id: viewed })
      });
    } catch (error) {
      console.error(error);
    }
  }

  if (page === 'browse') {
    const grid = document.querySelector('.filter .grid');
    document.querySelector('.filter .top')
      .insertAdjacentHTML('afterend', '<input id="search" class="search" placeholder="Search ideas">');
    document.getElementById('search').oninput = function () {
      const word = this.value.toLowerCase();
      [...grid.children].forEach(card => {
        card.style.display = card.textContent.toLowerCase().includes(word) ? '' : 'none';
      });
    };
  }

  if (page === 'dashboard-investor' && me && me.role === 'investor') {
    const mine = state.profile || { sector: 'Any', max: 1000000 };
    const all = ideas.concat([
      { id: 'waterwise', title: 'WaterWise Drip', cat: 'AgriTech', ask: 400000 },
      { id: 'rentcircle', title: 'RentCircle', cat: 'FinTech', ask: 750000 },
      { id: 'classpulse', title: 'ClassPulse', cat: 'EdTech', ask: 250000 }
    ]);
    const matches = state.profile
      ? all.filter(idea =>
        (mine.sector === 'Any' || idea.cat === mine.sector) && idea.ask <= mine.max)
      : [];
    document.querySelector('.panel').insertAdjacentHTML('beforeend',
      '<h3 class="part">Your deal criteria</h3><form id="criteria"><label>Sector<select>' +
      options(sectors, mine.sector) + '</select></label><label>Largest amount you invest (Rs)' +
      '<input type="number" min="1000" required value="' + Number(mine.max) + '">' +
      '</label><button class="btn full">Save criteria</button></form>' +
      '<h3 class="part">Matching ideas</h3>' +
      (matches.map(idea =>
        '<div class="box"><b>' + esc(idea.title) + '</b> · ' + rupees(idea.ask) +
        ' <a href="' + (samples[idea.id] ? 'pitch-' + idea.id + '.html' : 'idea.html') +
        '" data-view="' + esc(idea.id) + '">View</a></div>'
      ).join('') || '<p class="muted">Save your criteria to see matches.</p>'));
    const form = document.getElementById('criteria');
    form.onsubmit = async function (event) {
      event.preventDefault();
      try {
        await api('/api/profile', {
          method: 'PUT',
          body: JSON.stringify({
            sector: form.querySelector('select').value,
            max: Number(form.querySelector('input').value)
          })
        });
        location.reload();
      } catch (error) {
        hub.showError(form, error.message);
      }
    };
    document.querySelectorAll('[data-view]').forEach(anchor => {
      anchor.onclick = () => selectIdea(anchor.dataset.view);
    });
  }

  if (page === 'dashboard-developer' && me && me.role === 'developer') {
    const tracker = state.tracker.slice();
    const seen = ideas.filter(idea => idea.owner === me.name)
      .map(idea => '<div class="box"><b>' + esc(idea.title) + '</b>: ' +
        (state.views[idea.id] || 0) + ' views</div>').join('');
    document.querySelector('.panel').insertAdjacentHTML('beforeend',
      '<h3 class="part">Pitch views</h3>' + (seen || '<p class="muted">No ideas yet.</p>') +
      '<h3 class="part">Fundraising tracker</h3><div id="rows"></div>' +
      '<form id="add"><label>Investor name<input required maxlength="40"></label>' +
      '<button class="btn full">Add to tracker</button></form>');
    const area = document.getElementById('rows');
    function renderTracker() {
      area.innerHTML = tracker.map(entry =>
        '<div class="box"><b>' + esc(entry.name) + '</b><select data-id="' + entry.id +
        '">' + options(stages, entry.stage) + '</select><button class="btn small" data-del="' +
        entry.id + '">Remove</button></div>'
      ).join('') || '<p class="muted">Add the investors you are talking to.</p>';
    }
    area.onchange = async function (event) {
      const entry = tracker.find(item => String(item.id) === event.target.dataset.id);
      if (!entry) return;
      try {
        await api('/api/tracker/' + entry.id, {
          method: 'PATCH',
          body: JSON.stringify({ stage: event.target.value })
        });
        entry.stage = event.target.value;
      } catch (error) {
        hub.showError(area, error.message);
        renderTracker();
      }
    };
    area.onclick = async function (event) {
      const id = event.target.dataset.del;
      if (!id) return;
      try {
        await api('/api/tracker/' + id, { method: 'DELETE' });
        const index = tracker.findIndex(entry => String(entry.id) === id);
        if (index !== -1) tracker.splice(index, 1);
        renderTracker();
      } catch (error) {
        hub.showError(area, error.message);
      }
    };
    const add = document.getElementById('add');
    add.onsubmit = async function (event) {
      event.preventDefault();
      const name = add.querySelector('input').value.trim();
      if (!name) return;
      try {
        tracker.push(await api('/api/tracker', {
          method: 'POST',
          body: JSON.stringify({ name })
        }));
        add.reset();
        renderTracker();
      } catch (error) {
        hub.showError(add, error.message);
      }
    };
    renderTracker();
  }
}).catch(error => {
  console.error('Website features failed to initialize:', error);
});
