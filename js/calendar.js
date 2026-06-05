// ── 晚风 · 日历视图 ──

function toggleCalendar() {
  showCalendar = !showCalendar;
  const btn = document.getElementById('btn-cal');
  if (showCalendar) {
    btn.classList.add('active');
    const now = new Date();
    calYear = now.getFullYear(); calMonth = now.getMonth();
    calSelectedDate = null;
    renderCalendar();
  } else {
    btn.classList.remove('active');
    calView.classList.remove('active');
    listEl.classList.remove('hidden');
    render(searchEl.value);
  }
}
document.getElementById('btn-cal').addEventListener('click', toggleCalendar);

function renderCalendar() {
  calView.classList.add('active');
  listEl.classList.add('hidden');
  countEl.textContent = notes.length + ' 条';

  const months = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  calView.querySelector('.cal-header').innerHTML = `
    <button id="cal-prev">◀</button>
    <span class="month-label">${calYear}年 ${months[calMonth]}</span>
    <button id="cal-next">▶</button>`;
  calView.querySelector('#cal-prev').addEventListener('click', () => { calMonth--; if (calMonth < 0) { calMonth = 11; calYear--; } renderCalendar(); });
  calView.querySelector('#cal-next').addEventListener('click', () => { calMonth++; if (calMonth > 11) { calMonth = 0; calYear++; } renderCalendar(); });

  calView.querySelector('.cal-day-labels').innerHTML = ['日','一','二','三','四','五','六'].map(d => `<div class="cal-day-label">${d}</div>`).join('');

  const firstDay = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  // 哪些天有笔记
  const noteDates = new Set();
  for (const n of notes) {
    const d = new Date(n.ts);
    noteDates.add(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);
  }

  let daysHtml = '';
  for (let i = 0; i < firstDay; i++) daysHtml += '<div class="cal-day other-month"></div>';
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const isToday = dateStr === todayStr;
    const hasNote = noteDates.has(dateStr);
    const isSelected = calSelectedDate === dateStr;
    daysHtml += `<div class="cal-day${isToday ? ' today' : ''}${hasNote ? ' has-note' : ''}${isSelected ? ' selected' : ''}" data-date="${dateStr}">${d}</div>`;
  }
  calView.querySelector('.cal-days').innerHTML = daysHtml;
  calView.querySelectorAll('.cal-day[data-date]').forEach(day => {
    day.addEventListener('click', () => {
      calSelectedDate = day.dataset.date;
      renderCalendar();
    });
  });

  // 选中日期的笔记
  if (calSelectedDate) {
    const startTs = new Date(calSelectedDate + 'T00:00:00+08:00').getTime();
    const endTs = startTs + 86400000;
    const dayNotes = notes.filter(n => n.ts >= startTs && n.ts < endTs);
    calView.querySelector('.cal-notes-title').textContent = `📝 ${calSelectedDate} · ${dayNotes.length} 条笔记`;
    calView.querySelector('.cal-notes-list').innerHTML = dayNotes.map(n => {
      const imgs = n.images || [];
      const imgHtml = imgs.length ? `<div class="card-images">${imgs.map(f => `<img src="/uploads/${esc(f)}" loading="lazy" data-img="/uploads/${esc(f)}">`).join('')}</div>` : '';
      return `<div class="card" data-id="${n.id}">
        <div class="body short">${n.group ? '<span class="group-badge">'+esc(n.group)+'</span>' : ''}${esc(n.body)}</div>
        ${imgHtml}
      </div>`;
    }).join('') || '<div style="color:var(--text-muted);font-size:13px;text-align:center;padding:20px">这天没有笔记</div>';
    calView.querySelectorAll('.cal-notes-list .card-images img').forEach(img => img.addEventListener('click', e => {
      e.stopPropagation(); openLightbox(img.dataset.img);
    }));
  } else {
    calView.querySelector('.cal-notes-title').textContent = '点击日期查看笔记';
    calView.querySelector('.cal-notes-list').innerHTML = '';
  }
}
