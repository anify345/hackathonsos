// Idea Hub: the server stores application data in SQLite; localStorage is used
// only for the selected pitch and the post-login return path.

window.IdeaHubReady = (async function () {
  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The request could not be completed.');
    return result;
  }

  function esc(text) {
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function go(page) {
    location.href = page;
  }

  async function demoUnlock(id) {
    return api('/api/unlocks', {
      method: 'POST',
      body: JSON.stringify({ id })
    });
  }

  function showError(form, text) {
    let message = form.querySelector('.error');
    if (!message) {
      message = document.createElement('p');
      message.className = 'error';
      form.appendChild(message);
    }
    message.textContent = text;
  }

  let state;
  try {
    state = await api('/api/state');
  } catch (error) {
    console.error(error);
    const main = document.querySelector('main');
    if (main) {
      const notice = document.createElement('p');
      notice.className = 'error';
      notice.textContent = 'Could not load website data. Please refresh and try again.';
      main.prepend(notice);
    }
    throw error;
  }

  const me = state.user;
  const ideas = state.ideas;
  const unlocks = state.unlocks;
  const messages = state.messages;
  const sampleContacts = state.sample_contacts || {};
  const page = location.pathname.split('/').pop().replace('.html', '') || 'index';
  const selected = () => new URLSearchParams(location.search).get('id') ||
    localStorage.getItem('selected') || '';
  const selectIdea = id => localStorage.setItem('selected', id);
  const samples = {
    waterwise: 'WaterWise Drip',
    rentcircle: 'RentCircle',
    classpulse: 'ClassPulse'
  };
  const titleOf = id => (ideas.find(idea => idea.id === id) || {}).title || samples[id];
  const hasUnlocked = id => Boolean(
    me && unlocks.some(unlock => unlock.id === id && unlock.by === me.name)
  );
  const showErrorForForm = showError;
  document.querySelectorAll('[data-print]').forEach(button => {
    button.onclick = () => window.print();
  });

  function onSubmit(action) {
    const form = document.querySelector('form');
    if (!form) return;
    form.onsubmit = async function (event) {
      event.preventDefault();
      const values = [...form.querySelectorAll('input, select, textarea')]
        .map(box => box.value.trim());
      try {
        await action(values, form);
      } catch (error) {
        showError(form, error.message);
      }
    };
  }

  function needRole(role) {
    if (me && me.role === role) return true;
    localStorage.setItem('next', page + '.html');
    go('signup-' + role + '.html');
    return false;
  }

  function enter(defaultPage, role) {
    const next = localStorage.getItem('next') || '';
    localStorage.removeItem('next');
    const fits = role === 'investor'
      ? /^(pay|chat|idea)/.test(next)
      : /^pitch-form/.test(next);
    go(fits ? next : defaultPage);
  }

  if (me) {
    const box = document.querySelector('.actions');
    if (box) {
      box.innerHTML = '<a class="btn" href="dashboard-' + me.role + '.html">Dashboard (' +
        esc(me.name) + ')</a><button class="btn dark" id="logout">Log out</button>';
      document.getElementById('logout').onclick = async function () {
        try {
          await api('/api/logout', { method: 'POST', body: '{}' });
          go('index.html');
        } catch (error) {
          console.error(error);
        }
      };
    }
  }

  if (me && me.role === 'developer') {
    document.querySelectorAll('a[href="signup-developer.html"]')
      .forEach(anchor => { anchor.href = 'pitch-form.html'; });
  }

  if (page.startsWith('signup-')) {
    const role = page.replace('signup-', '');
    onSubmit(async function ([name, password, email, phone], form) {
      if (!name || !password || !email || !phone) {
        return showError(form, 'Please fill in every box.');
      }
      const result = await api('/api/signup', {
        method: 'POST',
        body: JSON.stringify({ name, password, email, phone, role })
      });
      enter(
        role === 'developer' ? 'pitch-form.html' : 'dashboard-investor.html',
        result.user.role
      );
    });
  }

  if (page.startsWith('login-')) {
    const role = page.replace('login-', '');
    onSubmit(async function ([name, password], form) {
      const result = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ name, password, role })
      });
      enter('dashboard-' + role + '.html', result.user.role);
    });
  }

  if (page === 'pitch-form' && needRole('developer')) {
    onSubmit(async function ([title, cat, problem, solution, ask, equity, link]) {
      await api('/api/pitches', {
        method: 'POST',
        body: JSON.stringify({
          title, cat, problem, solution, ask: Number(ask), equity: Number(equity), link
        })
      });
      go('published.html');
    });
  }

  if (page === 'browse') {
    const grid = document.querySelector('.filter .grid');
    ideas.forEach(function (idea) {
      grid.insertAdjacentHTML('afterbegin',
        '<div class="card ' + esc(idea.cat) + '"><span class="cat">' + esc(idea.cat) +
        '</span><h3>' + esc(idea.title) + '</h3><div class="row"><span class="pill">Rs ' +
        Number(idea.ask).toLocaleString('en-IN') + '</span><span class="pill">' +
        esc(idea.equity) + '%</span></div><p class="muted">' + esc(idea.problem) +
        '</p><button class="btn full" data-id="' + esc(idea.id) +
        '">View pitch</button></div>');
    });
    grid.onclick = function (event) {
      const id = event.target.dataset.id;
      if (id) {
        selectIdea(id);
        go('idea.html');
      }
    };
  }

  if (page === 'idea') {
    const idea = ideas.find(item => item.id === selected());
    if (!idea) {
      go('browse.html');
    } else {
      const fee = Math.round(Math.min(1000, Math.max(100, idea.ask * 0.015)));
      const link = /^https?:\/\//i.test(idea.link)
        ? '<p><a href="' + esc(idea.link) + '" target="_blank" rel="noopener">See the creation</a></p>'
        : '';
      const identity = idea.owner
        ? ' · by ' + esc(idea.owner)
        : ' · identity hidden until demo unlock';
      document.getElementById('idea').innerHTML =
        '<h2>' + esc(idea.title) + '</h2><span class="cat">' + esc(idea.cat) + identity +
        '</span><div class="row"><span class="pill">Asking Rs ' +
        Number(idea.ask).toLocaleString('en-IN') + '</span><span class="pill">' +
        esc(idea.equity) + '% equity</span></div><div class="box"><b>Problem</b><br>' +
        esc(idea.problem) + '</div><div class="box"><b>Solution</b><br>' +
        esc(idea.solution) + '</div>' + link +
        (hasUnlocked(idea.id) ? '' :
          '<p class="muted">Demo unlock only; no money moves.</p>') +
        (hasUnlocked(idea.id) ? '<div class="box"><b>Contact</b><br>' +
          esc(idea.email || '') + '<br>' + esc(idea.phone || '') + '</div>' : '') +
        '<div class="row"><button class="btn" id="pdf">Print pitch</button><button class="btn dark" id="unlock">' +
        (hasUnlocked(idea.id) ? 'Send a message' : 'Pay (demo) · Rs ' + fee) +
        '</button></div><div id="chat"></div>';

      document.getElementById('pdf').onclick = () => window.print();
      document.getElementById('unlock').onclick = async function () {
        if (!needRole('investor')) return;
        if (!hasUnlocked(idea.id)) {
          try {
            await demoUnlock(idea.id);
            location.reload();
          } catch (error) {
            showErrorForForm(document.getElementById('idea'), error.message);
          }
          return;
        }
        document.getElementById('chat').innerHTML =
          '<form><label>Message<textarea maxlength="500"></textarea></label>' +
          '<button class="btn dark full">Send message</button></form>';
        onSubmit(async function ([text], form) {
          if (!text) return showError(form, 'Write a message first.');
          await api('/api/messages', {
            method: 'POST',
            body: JSON.stringify({ id: idea.id, text })
          });
          go('message-sent.html');
        });
      };
    }
  }

  if (page.startsWith('pay-') && needRole('investor')) {
    const id = page.replace('pay-', '');
    if (hasUnlocked(id)) go('chat-' + id + '.html');
    const button = document.getElementById('pay');
    if (button) {
      button.onclick = async function () {
        try {
          await demoUnlock(id);
          go('chat-' + id + '.html');
        } catch (error) {
          const panel = document.querySelector('.panel');
          if (panel) {
            const notice = document.createElement('p');
            notice.className = 'error';
            notice.textContent = error.message;
            panel.appendChild(notice);
          }
        }
      };
    }
  }

  if (page.startsWith('chat-') && needRole('investor')) {
    const id = page.replace('chat-', '');
    if (!hasUnlocked(id)) {
      go('pay-' + id + '.html');
    } else {
      const contact = sampleContacts[id];
      const panel = document.querySelector('.panel');
      const form = panel && panel.querySelector('form');
      if (contact && panel && form) {
        const box = document.createElement('div');
        box.className = 'box';
        box.innerHTML = '<b>' + esc(contact.name) + '</b><br>' +
          esc(contact.email) + '<br>Sample contact';
        panel.insertBefore(box, form);
      }
      onSubmit(async function ([text], form) {
        if (!text) return showError(form, 'Write a message first.');
        await api('/api/messages', {
          method: 'POST',
          body: JSON.stringify({ id, text })
        });
        go('message-sent.html');
      });
    }
  }

  if (page === 'dashboard-developer' && needRole('developer')) {
    const mine = ideas.filter(idea => idea.owner === me.name);
    const html = mine.map(function (idea) {
      const count = state.views[idea.id] || 0;
      const inbox = messages.filter(message => message.id === idea.id)
        .map(message => '<br>' + esc(message.from) + ': ' + esc(message.text)).join('');
      return '<div class="box"><b>' + esc(idea.title) + '</b><br>Unlocks: ' +
        unlocks.filter(unlock => unlock.id === idea.id).length + inbox + '</div>';
    }).join('');
    document.getElementById('mine').innerHTML = html || '<p class="muted">No ideas yet.</p><br>';
  }

  if (page === 'dashboard-investor' && needRole('investor')) {
    const mine = unlocks.filter(unlock => unlock.by === me.name);
    const html = mine.map(function (unlock) {
      const link = samples[unlock.id] ? 'chat-' + unlock.id + '.html' : 'idea.html';
      return '<div class="box"><b>' + esc(titleOf(unlock.id)) +
        '</b><p style="margin-top:8px"><a class="btn" href="' + link +
        '" data-id="' + esc(unlock.id) + '">Open chat</a></p></div>';
    }).join('');
    const area = document.getElementById('mine');
    area.innerHTML = html || '<p class="muted">You have not unlocked any ideas yet.</p><br>';
    area.onclick = event => {
      if (event.target.dataset.id) selectIdea(event.target.dataset.id);
    };
  }

  window.IdeaHub = {
    api, state, me, ideas, unlocks, messages, page, samples, titleOf,
    esc, showError, selectIdea
  };
  return window.IdeaHub;
})().catch(error => {
  console.error('Website initialization failed:', error);
});
