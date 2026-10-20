// ── 晚风 · 日历视图 ──

function toggleCalendar() {
  showCalendar = !showCalendar;
  const btn = document.getElementById('btn-cal');
  if (showCalendar) {
    btn.classList.add('active');
    const now = new Date();
    calYear = now.getFullYear();
    calMonth = now.getMonth();
    calSelectedDate = null;
    renderCalendar();
  } else {
    btn.classList.remove('active');
    if (calView) calView.classList.remove('active');
    listEl.classList.remove('hidden');
    render(searchEl.value);
  }
}
document.getElementById('btn-cal').addEventListener('click', toggleCalendar);

// 本地时区的 YYYY-MM-DD，避免再硬编码 +08:00
function dayKey(date) {
  return date.getFullYear() + '-' +
    String(date.getMonth() + 1).padStart(2, '0') + '-' +
    String(date.getDate()).padStart(2, '0');
}

function renderCalendar() {
  calView.classList.add('active');
  listEl.classList.add('hidden');
  if (countEl) countEl.textContent = notes.length + ' 篇';

  const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
  calView.querySelector('.cal-header').innerHTML = `
    <button id="cal-prev" type="button">◀</button>
    <span class="month-label">${calYear}年 ${months[calMonth]}</span>
    <button id="cal-next" type="button">▶</button>`;
  calView.querySelector('#cal-prev').addEventListener('click', () => {
    calMonth--;
    if (calMonth < 0) { calMonth = 11; calYear--; }
    renderCalendar();
  });
  calView.querySelector('#cal-next').addEventListener('click', () => {
    calMonth++;
    if (calMonth > 11) { calMonth = 0; calYear++; }
    renderCalendar();
  });

  calView.querySelector('.cal-day-labels').innerHTML =
    ['日', '一', '二', '三', '四', '五', '六'].map(d => `<div class="cal-day-label">${d}</div>`).join('');

  const firstDay = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const todayStr = dayKey(new Date());

  // 哪些天有笔记：与列表一致，用创建时间
  const noteDates = new Set();
  for (const n of notes) {
    const d = new Date(n.created_ts || n.ts);
    if (!isNaN(d.getTime())) noteDates.add(dayKey(d));
  }

  let daysHtml = '';
  for (let i = 0; i < firstDay; i++) daysHtml += '<div class="cal-day other-month"></div>';
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
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

  if (calSelectedDate) {
    const [y, m, d] = calSelectedDate.split('-').map(Number);
    const startTs = new Date(y, m - 1, d).getTime();
    const endTs = new Date(y, m - 1, d + 1).getTime();
    const dayNotes = notes.filter(n => {
      const ts = n.created_ts || n.ts;
      return ts >= startTs && ts < endTs;
    }).sort(compareNotes);
    calView.querySelector('.cal-notes-title').textContent = `📝 ${calSelectedDate} · ${dayNotes.length} 条笔记`;
    calView.querySelector('.cal-notes-list').innerHTML = dayNotes.map(n => {
      const imgs = (n.images || []).map(safeImage).filter(Boolean);
      const imgHtml = imgs.length
        ? `<div class="card-images">${imgs.map(f => `<img src="/uploads/${esc(f)}" loading="lazy" data-img="${esc(f)}" alt="">`).join('')}</div>`
        : '';
      return `<div class="card" data-id="${esc(n.id)}">
        <div class="body short">${n.group ? '<span class="group-badge">' + esc(n.group) + '</span>' : ''}${esc(n.body)}</div>
        ${imgHtml}
      </div>`;
    }).join('') || '<div style="color:var(--text-muted);font-size:13px;text-align:center;padding:20px">这天没有笔记</div>';
    calView.querySelectorAll('.cal-notes-list .card-images img').forEach(img => {
      img.addEventListener('click', e => {
        e.stopPropagation();
        openLightbox(img.dataset.img);
      });
    });
  } else {
    calView.querySelector('.cal-notes-title').textContent = '点击日期查看笔记';
    calView.querySelector('.cal-notes-list').innerHTML = '';
  }
}
