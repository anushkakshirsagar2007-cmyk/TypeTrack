(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const body = document.body;

  // toasts
  $$('.toast').forEach(t => new bootstrap.Toast(t).show());

  // sidebar
  const toggle = $('#sidebarToggle');
  if (toggle) {
    const desktop = () => window.matchMedia('(min-width: 992px)').matches;
    if (desktop() && localStorage.getItem('tt-sb') === '1') body.classList.add('sb-collapsed');
    toggle.addEventListener('click', () => {
      if (desktop()) { body.classList.toggle('sb-collapsed'); localStorage.setItem('tt-sb', body.classList.contains('sb-collapsed') ? '1' : '0'); }
      else body.classList.toggle('sb-open');
    });
    $('#backdrop').addEventListener('click', () => body.classList.remove('sb-open'));
  }

  // confirmation dialogs + loading indicator
  const modalEl = $('#confirmModal'); let pending = null;
  if (modalEl) {
    const modal = new bootstrap.Modal(modalEl);
    $('#confirmYes').addEventListener('click', () => { modal.hide(); if (pending) { pending.dataset.ok = '1'; showLoader(); pending.submit(); } });
    document.addEventListener('submit', e => {
      const f = e.target;
      if (f.dataset.confirm && f.dataset.ok !== '1') { e.preventDefault(); pending = f; $('#confirmText').textContent = f.dataset.confirm; modal.show(); }
    }, true);
  }
  function showLoader() { const l = $('#loader'); if (l) l.classList.add('show'); }
  document.addEventListener('submit', e => {
    const f = e.target;
    if (e.defaultPrevented || f.hasAttribute('data-no-loader') || f.dataset.confirm) return;
    if (f.hasAttribute('data-validate') && !f.checkValidity()) { e.preventDefault(); f.classList.add('was-validated'); f.reportValidity(); return; }
    showLoader();
    $$('button:not([type=button])', f).forEach(b => setTimeout(() => (b.disabled = true), 0));
  });
  window.addEventListener('pageshow', () => { const l = $('#loader'); if (l) l.classList.remove('show'); });

  // global search suggestions
  const gs = $('#globalSearch'), box = $('#searchResults');
  if (gs) {
    let timer;
    gs.addEventListener('input', () => {
      clearTimeout(timer);
      const q = gs.value.trim();
      if (q.length < 2) { box.classList.remove('show'); return; }
      timer = setTimeout(async () => {
        try {
          const r = await fetch(gs.dataset.api + '?q=' + encodeURIComponent(q), { headers: { Accept: 'application/json' } });
          const items = await r.json();
          box.innerHTML = items.length ? '' : '<div class="p-3 text-muted small">No matches found.</div>';
          items.forEach(i => { const a = document.createElement('a'); a.href = i.url;
            const l = document.createElement('div'), t = document.createElement('b'), s = document.createElement('small'), k = document.createElement('small');
            t.textContent = i.title; s.textContent = ' ' + i.sub; k.textContent = i.type; l.append(t, document.createElement('br'), s); a.append(l, k); box.appendChild(a); });
          box.classList.add('show');
        } catch (e) { box.classList.remove('show'); }
      }, 250);
    });
    document.addEventListener('click', e => { if (!e.target.closest('.global-search')) box.classList.remove('show'); });
  }

  // attendance: mark all present
  const all = $('#markAll');
  if (all) all.addEventListener('click', () => $$('#attForm input[value=Present]:not(:disabled)').forEach(r => (r.checked = true)));

  // student form: course -> fees and batch filter, net fees
  const course = $('#course_id'), fees = $('#total_fees'), disc = $('#discount'), batch = $('#batch_id'), net = $('#netFees');
  if (course && fees && window.TT_COURSES) {
    const filterBatches = () => $$('option[data-course]', batch).forEach(o => {
      const hide = course.value && o.dataset.course !== course.value; o.hidden = hide; o.disabled = hide;
      if (hide && o.selected) batch.value = '';
    });
    const calc = () => { const n = (parseFloat(fees.value) || 0) - (parseFloat(disc.value) || 0); net.textContent = 'Rs. ' + n.toLocaleString('en-IN', { minimumFractionDigits: 2 }); };
    course.addEventListener('change', () => {
      const i = window.TT_COURSE_IDS.indexOf(parseInt(course.value));
      if (i >= 0 && (!window.TT_EDIT || !fees.value || fees.dataset.touched !== '1') && fees.dataset.touched !== '1') fees.value = window.TT_COURSES[i];
      filterBatches(); calc();
    });
    fees.addEventListener('input', () => { fees.dataset.touched = '1'; calc(); }); disc.addEventListener('input', calc);
    filterBatches(); calc();
  }

  // payment form: balance hint
  const stu = $('#student_id'), amt = $('#amount'), hint = $('#balHint');
  if (stu && amt) {
    const upd = () => { const o = stu.selectedOptions[0]; const b = o && o.dataset.balance; if (b !== undefined) { hint.textContent = 'Pending balance: Rs. ' + parseFloat(b).toLocaleString('en-IN', { minimumFractionDigits: 2 }); amt.max = b; } else hint.textContent = ''; };
    stu.addEventListener('change', upd); upd();
    const fb = $('#fullBal'); if (fb) fb.addEventListener('click', () => { const o = stu.selectedOptions[0]; if (o && o.dataset.balance) amt.value = parseFloat(o.dataset.balance).toFixed(2); });
  }
})();
