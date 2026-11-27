// Idea Hub: front-end only. Everything is saved in this browser (localStorage).

// ---------- 1. Saving and reading data ----------
function read(key, fallback) {
  return JSON.parse(localStorage.getItem(key)) || fallback;
}
function write(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}
// stops people typing HTML into the forms
function esc(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function go(page) {
  location.href = page;
}

const users = read('users', []);        // all accounts
const ideas = read('ideas', []);        // ideas pitched by developers
const unlocks = read('unlocks', []);    // who unlocked what
const messages = read('messages', []);  // messages from investors
const me = users.find(u => u.name === read('loggedIn', ''));
const page = location.pathname.split('/').pop().replace('.html', '') || 'index';

const samples = { waterwise: 'WaterWise Drip', rentcircle: 'RentCircle', classpulse: 'ClassPulse' };
function titleOf(id) {
  const idea = ideas.find(i => i.id === id);
  return idea ? idea.title : samples[id];
}
function hasUnlocked(id) {
  return me && unlocks.some(u => u.id === id && u.by === me.name);
}

// ---------- 2. Top buttons: Log in / Log out ----------
if (me) {
  const box = document.querySelector('.actions');
  box.innerHTML = '<a class="btn" href="dashboard-' + me.role + '.html">Dashboard (' + esc(me.name) + ')</a>' +
                  '<button class="btn dark" id="logout">Log out</button>';
  document.getElementById('logout').onclick = function () {
    localStorage.removeItem('loggedIn');
    go('index.html');
  };
}

// "Pitch your idea" goes straight to the form if a developer is logged in
if (me && me.role === 'developer') {
  document.querySelectorAll('a[href="signup-developer.html"]').forEach(a => a.href = 'pitch-form.html');
}

// ---------- 3. Pages that need an account ----------
function needRole(role) {
  if (me && me.role === role) return true;
  write('next', page + '.html');   // come back here afterwards
  go('signup-' + role + '.html');
  return false;
}

function showError(form, text) {
  let p = form.querySelector('.error');
  if (!p) {
    p = document.createElement('p');
    p.className = 'error';
    form.appendChild(p);
  }
  p.textContent = text;
}

// reads the form boxes from top to bottom
function onSubmit(action) {
  const form = document.querySelector('form');
  form.onsubmit = function (event) {
    event.preventDefault();
    const values = [...form.querySelectorAll('input, select, textarea')].map(box => box.value.trim());
    if (values.slice(0, -1).includes('')) return showError(form, 'Please fill in every box.');
    action(values, form);
  };
}

// log the user in, then open the right page
function enter(user, defaultPage) {
  write('loggedIn', user.name);
  const next = read('next', '');
  localStorage.removeItem('next');
  const fits = user.role === 'investor' ? /^(pay|chat|idea)/ : /^pitch-form/;
  go(fits.test(next) ? next : defaultPage);
}

// ---------- 4. Sign up and log in ----------
if (page.startsWith('signup-')) {
  const role = page.replace('signup-', '');
  onSubmit(function ([name, password, email, phone], form) {
    if (!name || !email || !phone) return showError(form, 'Please fill in every box.');
    const taken = users.some(u => u.name.toLowerCase() === name.toLowerCase());
    if (taken || name.startsWith('demo_')) return showError(form, 'That username is taken.');
    const user = { name, password, email, phone, role };
    users.push(user);
    write('users', users);
    enter(user, role === 'developer' ? 'pitch-form.html' : 'dashboard-investor.html');
  });
}

if (page.startsWith('login-')) {
  const role = page.replace('login-', '');
  onSubmit(function ([name, password], form) {
    const user = users.find(u => u.name === name && u.password === password && u.role === role);
    if (!user) return showError(form, 'Wrong username or password for a ' + role + ' account.');
    enter(user, 'dashboard-' + role + '.html');
  });
}

// ---------- 5. Pitch a new idea ----------
if (page === 'pitch-form' && needRole('developer')) {
  onSubmit(function ([title, cat, problem, solution, ask, equity, link]) {
    ideas.push({ id: 'i' + Date.now(), owner: me.name, title, cat, problem, solution, ask: Number(ask), equity, link });
    write('ideas', ideas);
    go('published.html');
  });
}

// ---------- 6. Show new ideas on the Browse page ----------
if (page === 'browse') {
  const grid = document.querySelector('.filter .grid');
  ideas.forEach(function (i) {
    grid.insertAdjacentHTML('afterbegin',
      '<div class="card ' + esc(i.cat) + '"><span class="cat">' + esc(i.cat) + '</span><h3>' + esc(i.title) + '</h3>' +
      '<div class="row"><span class="pill">Rs ' + i.ask.toLocaleString('en-IN') + '</span><span class="pill">' + esc(i.equity) + '%</span></div>' +
      '<p class="muted">' + esc(i.problem) + '</p><button class="btn full" data-id="' + i.id + '">View pitch</button></div>');
  });
  grid.onclick = function (event) {
    const id = event.target.dataset.id;
    if (id) { write('selected', id); go('idea.html'); }
  };
}

// ---------- 7. Page for a newly pitched idea ----------
if (page === 'idea') {
  const i = ideas.find(x => x.id === read('selected', ''));
  if (!i) {
    go('browse.html');
  } else {
    const fee = Math.round(Math.min(1000, Math.max(100, i.ask * 0.001)));
    const founder = users.find(u => u.name === i.owner);
    const link = /^https?:\/\//i.test(i.link) ? '<p><a href="' + esc(i.link) + '" target="_blank" rel="noopener">See the creation</a></p>' : '';
    document.getElementById('idea').innerHTML =
      '<h2>' + esc(i.title) + '</h2><span class="cat">' + esc(i.cat) + ' · by ' + esc(i.owner) + '</span>' +
      '<div class="row"><span class="pill">Asking Rs ' + i.ask.toLocaleString('en-IN') + '</span><span class="pill">' + esc(i.equity) + '% equity</span></div>' +
      '<div class="box"><b>Problem</b><br>' + esc(i.problem) + '</div><div class="box"><b>Solution</b><br>' + esc(i.solution) + '</div>' + link +
      (hasUnlocked(i.id) ? '<div class="box"><b>Contact</b><br>' + esc(founder.email) + '<br>' + esc(founder.phone) + '</div>' : '') +
      '<div class="row"><button class="btn" id="pdf">Pitch PDF</button><button class="btn dark" id="unlock">' +
      (hasUnlocked(i.id) ? 'Send a message' : 'Unlock chat · Rs ' + fee + ' (simulated)') + '</button></div><div id="chat"></div>';

    document.getElementById('pdf').onclick = () => window.print();  // choose "Save as PDF"
    document.getElementById('unlock').onclick = function () {
      if (!needRole('investor')) return;
      if (!hasUnlocked(i.id)) {
        unlocks.push({ id: i.id, by: me.name });
        write('unlocks', unlocks);
        location.reload();
        return;
      }
      document.getElementById('chat').innerHTML =
        '<form><label>Message<textarea maxlength="500"></textarea></label><button class="btn dark full">Send message</button></form>';
      onSubmit(function ([text], form) {
        if (!text) return showError(form, 'Write a message first.');
        messages.push({ id: i.id, from: me.name, text });
        write('messages', messages);
        go('message-sent.html');
      });
    };
  }
}

// ---------- 8. Pay and chat pages for the sample ideas ----------
if (page.startsWith('pay-') && needRole('investor')) {
  const id = page.replace('pay-', '');
  if (hasUnlocked(id)) go('chat-' + id + '.html');
  document.querySelector('a[href="chat-' + id + '.html"]').onclick = function () {
    if (!hasUnlocked(id)) {
      unlocks.push({ id, by: me.name });
      write('unlocks', unlocks);
    }
  };
}

if (page.startsWith('chat-') && needRole('investor')) {
  const id = page.replace('chat-', '');
  if (!hasUnlocked(id)) {
    go('pay-' + id + '.html');
  } else {
    onSubmit(function ([text], form) {
      if (!text) return showError(form, 'Write a message first.');
      messages.push({ id, from: me.name, text });
      write('messages', messages);
      go('message-sent.html');
    });
  }
}

// ---------- 9. Dashboards (you only see your own) ----------
if (page === 'dashboard-developer' && needRole('developer')) {
  const mine = ideas.filter(i => i.owner === me.name);
  const html = mine.map(function (i) {
    const count = unlocks.filter(u => u.id === i.id).length;
    const inbox = messages.filter(m => m.id === i.id).map(m => '<br>' + esc(m.from) + ': ' + esc(m.text)).join('');
    return '<div class="box"><b>' + esc(i.title) + '</b><br>Unlocks: ' + count + inbox + '</div>';
  }).join('');
  document.getElementById('mine').innerHTML = html || '<p class="muted">No ideas yet.</p><br>';
}

if (page === 'dashboard-investor' && needRole('investor')) {
  const mine = unlocks.filter(u => u.by === me.name);
  const html = mine.map(function (u) {
    const link = samples[u.id] ? 'chat-' + u.id + '.html' : 'idea.html';
    return '<div class="box"><b>' + esc(titleOf(u.id)) + '</b><p style="margin-top:8px"><a class="btn" href="' + link + '" data-id="' + u.id + '">Open chat</a></p></div>';
  }).join('');
  const area = document.getElementById('mine');
  area.innerHTML = html || '<p class="muted">You have not unlocked any ideas yet.</p><br>';
  area.onclick = event => { if (event.target.dataset.id) write('selected', event.target.dataset.id); };
}
