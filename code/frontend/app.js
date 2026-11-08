// ============================================================================
// ANA特典航空券 空席サーチ - フロントエンド制御スクリプト
// （検索条件プレビュー・SSE進捗受信・リアルタイム絞込＆ソート・CSV出力）
// ============================================================================

const $ = (s) => document.querySelector(s);
const form = $('#search-form');

let es = null;
let jobId = null;
let results = [];
let view = 'list';
let range = null;
let selectedDateFilter = null; // カレンダーのマスをクリックした際の日付フィルタ

// マスタ情報（/api/areas から取得）
let masterOrigins = {};
let masterAreas = {};
let airportNames = {};
let directFlightsMap = {};

// ANA国際線特典航空券の検索画面URL
const ANA_AWARD_URL = 'https://aswbe-i.ana.co.jp/international_asw/pages/award/search/roundtrip/award_search_roundtrip_input.xhtml?CONNECTION_KIND=JPN&LANG=ja';

// HTMLエスケープ処理
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ローカル日付を YYYY-MM-DD に整形
const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

// 曜日を取得
const DOW_NAMES = ['日', '月', '火', '水', '木', '金', '土'];
function getDowInfo(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const idx = new Date(y, m - 1, d).getDay();
  const cls = idx === 0 ? 'dow-sun' : idx === 6 ? 'dow-sat' : '';
  return { label: DOW_NAMES[idx], cls };
}

// 空港コードから「都市名 (コード)」を返すヘルパー
function formatAirport(code) {
  const name = airportNames[code];
  return name ? `${name} (${code})` : code;
}

// フローティング・トースト通知を表示
let toastTimer = null;
function showToast(msg) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
}

// ステータスメッセージバナーの表示更新
function setBannerMessage(msg) {
  const el = $('#message');
  if (!msg) {
    el.hidden = true;
    el.textContent = '';
  } else {
    el.textContent = msg;
    el.hidden = false;
  }
}

// --- 初期化：マスタ情報の取得と初期日付セット ---
(async () => {
  try {
    const data = await (await fetch('/api/areas')).json();
    masterOrigins = data.origins || {};
    masterAreas = data.areas || {};
    airportNames = data.airport_names || {};
    directFlightsMap = data.direct_flights || {};

    $('#origin').innerHTML = Object.entries(masterOrigins)
      .map(([k, v]) => `<option value="${esc(k)}">${esc(v.label)}</option>`).join('');

    const allAirports = [...new Set(Object.values(masterAreas).flatMap((a) => a.airports))];
    $('#destination').innerHTML =
      '<optgroup label="🌍 広域エリア（一括検索）">' +
      Object.entries(masterAreas)
        .map(([k, v]) => `<option value="${esc(k)}">${esc(v.label)}（${v.airports.length}都市）</option>`).join('') +
      '</optgroup><optgroup label="📍 個別都市・空港（ピンポイント検索）">' +
      allAirports
        .map((c) => `<option value="${esc(c)}">${esc(c)} - ${esc(airportNames[c] || c)}</option>`).join('') +
      '</optgroup>';

    // デフォルトで「1ヶ月後から3日間」を初期セット
    const d1 = new Date();
    d1.setDate(d1.getDate() + 30);
    const d2 = new Date(d1);
    d2.setDate(d2.getDate() + 2);
    form.start_date.value = fmt(d1);
    form.end_date.value = fmt(d2);

    updateQueryPreview();
  } catch (e) {
    console.error('マスタ情報の取得に失敗:', e);
  }
})();

// --- 予定検索件数と所要時間のリアルタイムプレビュー計算 ---
function calcExpectedQueries() {
  const origKey = form.origin.value;
  const destKey = form.destination.value;
  const sVal = form.start_date.value;
  const eVal = form.end_date.value;
  const directOnly = form.direct_only.checked;

  if (!origKey || !destKey || !sVal || !eVal) return 0;
  const sDate = new Date(sVal);
  const eDate = new Date(eVal);
  if (eDate < sDate) return -1;

  const days = Math.round((eDate - sDate) / (1000 * 60 * 60 * 24)) + 1;
  if (days > 366) return -2;

  const origList = masterOrigins[origKey]?.airports || [origKey];
  const destList = masterAreas[destKey]?.airports || [destKey];

  let routesPerDay = 0;
  for (const d of destList) {
    // どのエリアに属するか探す
    let areaName = '';
    for (const [ak, av] of Object.entries(masterAreas)) {
      if (av.airports.includes(d)) { areaName = ak; break; }
    }
    const validOrigs = (directOnly && areaName && directFlightsMap[areaName]?.[d])
      ? directFlightsMap[areaName][d]
      : origList;

    for (const o of origList) {
      if (directOnly && (o === 'HND' || o === 'NRT') && !validOrigs.includes(o)) continue;
      if (o !== d) routesPerDay++;
    }
  }
  return days * routesPerDay;
}

function updateQueryPreview() {
  const badge = $('#query-preview');
  const count = calcExpectedQueries();
  badge.classList.remove('warn');

  if (count === -1) {
    badge.textContent = '⚠️ 終了日は開始日以降にしてください';
    badge.classList.add('warn');
  } else if (count === -2) {
    badge.textContent = '⚠️ 検索期間は1年以内にしてください';
    badge.classList.add('warn');
  } else if (count === 0) {
    badge.textContent = '予定検索数：0件';
  } else {
    const estMin = Math.max(1, Math.ceil((count * 35) / 60));
    if (count > 60) {
      badge.textContent = `⚠️ 予定検索数：${count}件（目安 約${estMin}分・件数が多いため個別空港または短期間がおすすめ）`;
      badge.classList.add('warn');
    } else {
      badge.textContent = `予定検索数：${count}区間（目安：約${estMin}分）`;
    }
  }
}

form.addEventListener('change', updateQueryPreview);
form.addEventListener('input', updateQueryPreview);

// --- 期間プリセットボタンの動作 ---
document.querySelectorAll('[data-days]').forEach((btn) => {
  btn.onclick = () => {
    const base = form.start_date.value ? new Date(form.start_date.value) : new Date();
    if (!form.start_date.value) form.start_date.value = fmt(base);
    const end = new Date(base);
    end.setDate(end.getDate() + Number(btn.dataset.days) - 1);
    form.end_date.value = fmt(end);
    updateQueryPreview();
  };
});

$('#btn-month').onclick = () => {
  const v = $('#month-pick').value;
  if (!v) {
    showToast('📅 先に左側の年月を選択してください');
    return;
  }
  const [y, m] = v.split('-').map(Number);
  form.start_date.value = `${v}-01`;
  form.end_date.value = fmt(new Date(y, m, 0));
  updateQueryPreview();
};

document.querySelectorAll('[data-months]').forEach((btn) => {
  btn.onclick = () => {
    const s = new Date(), t = new Date();
    t.setMonth(t.getMonth() + Number(btn.dataset.months));
    form.start_date.value = fmt(s);
    form.end_date.value = fmt(t);
    updateQueryPreview();
  };
});

// --- 検索開始 ---
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (es) { es.close(); es = null; }

  const body = Object.fromEntries(new FormData(form));
  body.passengers = Number(body.passengers);
  body.direct_only = form.direct_only.checked;
  selectedDateFilter = null;
  $('#btn-reset-filter').hidden = true;
  setBannerMessage('');
  $('#btn-search').disabled = true;

  try {
    const res = await fetch('/api/searches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      const d = data.detail;
      setBannerMessage(Array.isArray(d) ? d.map((x) => x.msg).join(' / ') : d);
      $('#btn-search').disabled = false;
      return;
    }
    range = { start: body.start_date, end: body.end_date };
    startStream(data.job_id);
  } catch (err) {
    setBannerMessage('⚠️ 検索リクエストに失敗しました。もう一度お試しください。');
    $('#btn-search').disabled = false;
  }
});

// --- キャンセルボタン（無条件で即座にロック解除） ---
$('#btn-cancel').onclick = () => {
  if (jobId) {
    fetch(`/api/searches/${jobId}/cancel`, { method: 'POST' }).catch(() => {});
  }
  if (es) { es.close(); es = null; }
  $('#btn-search').disabled = false;
  $('#progress-spinner').style.display = 'none';
  setBannerMessage('⏹ 検索をキャンセルしました。すぐに別の条件で再検索できます。');
  showToast('⏹ 検索をキャンセルしました');
};

// --- SSEで進捗と結果を受け取る ---
function startStream(id) {
  es?.close();
  jobId = id;
  results = [];
  $('#progress-box').hidden = false;
  $('#results-box').hidden = false;
  $('#progress-spinner').style.display = 'inline-block';
  $('#btn-search').disabled = true;
  updateDestinationFilterOptions();
  render();

  es = new EventSource(`/api/searches/${id}/events`);
  es.onerror = () => {
    if ($('#btn-search').disabled) {
      finish('failed', 'サーバーとの通信が切れました。再度お試しください。');
    }
  };

  const on = (t, fn) => es.addEventListener(t, (e) => fn(JSON.parse(e.data)));
  on('snapshot', (s) => {
    results = s.results || [];
    updateProgress(s);
    updateDestinationFilterOptions();
    render();
    if (['done', 'failed', 'cancelled'].includes(s.status)) finish(s.status);
  });
  on('progress', updateProgress);
  on('result', (d) => {
    results.push(d.result);
    updateDestinationFilterOptions();
    render();
  });
  on('error', (d) => {
    console.warn('検索エラー', d.current, d.message);
    const msg = d.message || '';
    if (msg.includes('現金表示') || msg.includes('409') || msg.includes('マイル表示')) {
      showToast(`⚠️ 【要切替】${d.current}: UA画面が現金表示になっています`);
    } else {
      showToast(`⚠️ エラー発生: ${d.current}`);
    }
  });
  on('done', (d) => { updateProgress({ ...d, current: '' }); finish('done'); });
  on('failed', (d) => finish('failed', d.message));
  on('cancelled', () => finish('cancelled'));
}

function updateProgress({ done, total, current, eta_sec }) {
  const pct = total ? Math.floor((done / total) * 100) : 0;
  $('#bar-fill').style.width = `${pct}%`;
  const eta = eta_sec ? ` ／ 残り約${Math.ceil(eta_sec / 60)}分` : '';
  $('#progress-text').textContent = current
    ? `${current} を検索中…（${done}/${total}件・${pct}%完了${eta}）`
    : `検索完了：${done}/${total}件（${pct}%）`;
}

function finish(status, msg = '') {
  es?.close();
  es = null;
  $('#btn-search').disabled = false;
  $('#progress-spinner').style.display = 'none';
  const label = {
    done: '✅ すべての検索が完了しました！',
    failed: `⚠️ 検索を中断しました：${msg}`,
    cancelled: '⏹ 検索をキャンセルしました',
  }[status];
  setBannerMessage(label);
}

// --- フィルタ・ソート・タブ切替イベント ---
document.querySelectorAll('.tabs [data-view]').forEach((b) => {
  b.onclick = () => {
    view = b.dataset.view;
    document.querySelectorAll('.tabs [data-view]').forEach((x) => x.classList.toggle('active', x === b));
    render();
  };
});

$('#filter-type').onchange = render;
$('#filter-dest').onchange = render;
$('#sort-by').onchange = render;

$('#btn-reset-filter').onclick = () => {
  selectedDateFilter = null;
  $('#btn-reset-filter').hidden = true;
  render();
};

// 結果に含まれる目的地のプルダウン選択肢を動的に更新
function updateDestinationFilterOptions() {
  const sel = $('#filter-dest');
  const currentVal = sel.value;
  const dests = [...new Set(results.map((r) => r.query.destination))].sort();
  sel.innerHTML = '<option value="all">すべての空港</option>' +
    dests.map((c) => `<option value="${esc(c)}">${esc(formatAirport(c))}</option>`).join('');
  if (dests.includes(currentVal)) sel.value = currentVal;
}

// --- フライト情報の正規化（古い形式のデータでも安全に表示するための補完） ---
function normalizeFlight(f, query) {
  if (f.miles && f.stop_label !== undefined) return f;
  const raw = f.flight_no || '';
  const mMiles = raw.match(/([\d\.]+k)/i);
  const miles = mMiles ? mMiles[1] : '空席あり';
  const milesNum = mMiles ? parseFloat(mMiles[1]) : 9999;
  const isDirect = raw.includes('直行便');
  const mTime = raw.match(/\((.*?)発/);
  return {
    flight_no: raw,
    miles,
    miles_num: milesNum,
    orig_code: query.origin,
    dest_code: query.destination,
    dep_time: mTime ? mTime[1] : '',
    arr_time: '',
    is_direct: isDirect,
    stop_label: isDirect ? '直行便' : '経由便',
  };
}

// --- 統計サマリーと画面全体の描画 ---
function render() {
  // 統計集計
  let totalFlights = 0;
  let directFlights = 0;
  let minMilesNum = Infinity;
  let minMilesStr = '-';

  results.forEach((r) => {
    const queryDirectOnly = r.query?.direct_only !== false;
    (r.flights || []).forEach((rawF) => {
      const f = normalizeFlight(rawF, r.query);
      if (queryDirectOnly && !f.is_direct) return;
      totalFlights++;
      if (f.is_direct) directFlights++;
      if (f.miles_num < minMilesNum) {
        minMilesNum = f.miles_num;
        minMilesStr = f.miles;
      }
    });
  });

  $('#stat-days').textContent = `${results.length}区間`;
  $('#stat-flights').textContent = `${totalFlights}便`;
  $('#stat-direct').textContent = `${directFlights}便`;
  $('#stat-min-miles').textContent = minMilesStr;

  $('#view-list').hidden = view !== 'list';
  $('#view-calendar').hidden = view !== 'calendar';
  view === 'list' ? renderList() : renderCalendar();
}

// --- フィルタ＆ソート済みの結果リストを取得 ---
function getFilteredRows() {
  const typeFilter = $('#filter-type').value;
  const destFilter = $('#filter-dest').value;
  const sortBy = $('#sort-by').value;

  const filtered = [];
  for (const r of results) {
    if (destFilter !== 'all' && r.query.destination !== destFilter) continue;
    if (selectedDateFilter && r.query.date !== selectedDateFilter) continue;

    const queryDirectOnly = r.query?.direct_only !== false;
    const normFlights = (r.flights || []).map((f) => normalizeFlight(f, r.query)).filter((f) => {
      if (queryDirectOnly && !f.is_direct) return false;
      if (typeFilter === 'direct') return f.is_direct;
      if (typeFilter === 'connecting') return !f.is_direct;
      return true;
    });

    if (normFlights.length > 0) {
      const minM = Math.min(...normFlights.map((f) => f.miles_num));
      const hasDirect = normFlights.some((f) => f.is_direct);
      filtered.push({
        query: r.query,
        seats_text: r.seats_text,
        flights: normFlights,
        minMiles: minM,
        hasDirect,
      });
    }
  }

  filtered.sort((a, b) => {
    if (sortBy === 'miles') {
      return a.minMiles - b.minMiles || a.query.date.localeCompare(b.query.date);
    }
    if (sortBy === 'direct') {
      if (a.hasDirect !== b.hasDirect) return a.hasDirect ? -1 : 1;
      return a.query.date.localeCompare(b.query.date);
    }
    return a.query.date.localeCompare(b.query.date);
  });

  return filtered;
}

// --- 空席リスト表示の描画 ---
function renderList() {
  const rows = getFilteredRows();
  if (!rows.length) {
    $('#view-list').innerHTML = `<div class="empty-state">${
      results.length ? '条件に一致する便がありません（フィルタ条件を変更してみてください）。' : 'まだ空席は見つかっていません。検索結果が入り次第ここに表示されます。'
    }</div>`;
    return;
  }

  const tbody = rows.map((r) => {
    const q = r.query;
    const dow = getDowInfo(q.date);
    const px = q.passengers || 1;
    const uaUrl = `https://www.united.com/en/us/fsr/choose-flights?f=${encodeURIComponent(q.origin)}&t=${encodeURIComponent(q.destination)}&d=${encodeURIComponent(q.date)}&tt=1&at=1&rm=1&act=0&px=${px}&taxng=1&newHP=True&clm=7&st=bestmatches&fareWheel=False`;
    const copyText = `${q.origin} → ${q.destination} ${q.date}`;

    const flightsHtml = r.flights.map((f) => {
      const timeStr = f.dep_time && f.arr_time
        ? `${esc(f.dep_time)}発 → ${esc(f.arr_time)}着`
        : f.dep_time ? `${esc(f.dep_time)}発` : '時刻詳細は予約画面で確認';

      const stopBadgeClass = f.is_direct ? 'stop-direct' : 'stop-conn';
      const itemClass = f.is_direct ? 'flight-item is-direct' : 'flight-item';
      const fareClassBadge = f.fare_class
        ? `<span class="fare-badge" title="予約クラス: ${esc(f.fare_class)}">クラス: ${esc(f.fare_class)}</span>`
        : '';

      // 他クラスの参考マイル表示
      let otherClassHint = '';
      if (q.cabin === 'economy' && f.business_miles && f.business_miles !== 'N/A') {
        const bCls = f.business_fare_class ? ` (${esc(f.business_fare_class)})` : '';
        otherClassHint = `<span class="sub-miles-hint">（ビジネス: ${esc(f.business_miles)}${bCls}）</span>`;
      } else if (q.cabin !== 'economy' && f.economy_miles && f.economy_miles !== 'N/A') {
        const eCls = f.economy_fare_class ? ` (${esc(f.economy_fare_class)})` : '';
        otherClassHint = `<span class="sub-miles-hint">（エコノミー: ${esc(f.economy_miles)}${eCls}）</span>`;
      }

      return `
        <div class="${itemClass}">
          <div class="flight-info">
            <span class="miles-badge">💺 ${esc(f.miles)}</span>
            ${fareClassBadge}
            <span class="stop-badge ${stopBadgeClass}">${esc(f.stop_label)}</span>
            <span class="time-text">${timeStr}</span>
            ${otherClassHint}
          </div>
          <div class="flight-actions">
            <a href="${ANA_AWARD_URL}" target="_blank" rel="noopener" class="btn-book-ana ana-link" data-origin="${esc(q.origin)}" data-dest="${esc(q.destination)}" data-date="${esc(q.date)}" data-cabin="${esc(q.cabin || 'economy')}" data-passengers="${esc(String(px))}" data-copy="${esc(copyText)}" title="ChromeでANA特典予約画面を開き、検索条件（区間・日付・クラス・人数）を自動入力します">ANA特典予約へ（自動入力） ↗</a>
            <a href="${uaUrl}" target="_blank" rel="noopener" class="btn-book-ua" title="ユナイテッド航空の検索結果ページで便名・詳細を確認します">UAで確認 ↗</a>
          </div>
        </div>`;
    }).join('');

    return `
      <tr>
        <td class="date-cell">
          ${esc(q.date)}
          <span class="dow-badge ${dow.cls}">${dow.label}</span>
        </td>
        <td class="route-cell">
          <span class="route-codes">${esc(q.origin)} → ${esc(q.destination)}</span>
          <span class="route-names">${esc(airportNames[q.origin] || q.origin)} ✈ ${esc(airportNames[q.destination] || q.destination)}</span>
        </td>
        <td>
          <div class="flight-list">${flightsHtml}</div>
        </td>
      </tr>`;
  }).join('');

  $('#view-list').innerHTML = `
    <div class="results-table-wrap">
      <table class="flights-table">
        <thead>
          <tr>
            <th>出発日</th>
            <th>区間（都市名）</th>
            <th>空席フライト詳細（必要マイル・直行/経由・発着時刻・予約リンク）</th>
          </tr>
        </thead>
        <tbody>${tbody}</tbody>
      </table>
    </div>`;
}

// --- ANAボタン押下時：ChromeでANA特典予約画面を開いて検索条件を自動入力（＋クリップボードコピー） ---
document.addEventListener('click', async (e) => {
  const a = e.target.closest('a.ana-link');
  if (!a) return;
  e.preventDefault();

  const text = a.dataset.copy || '';
  navigator.clipboard?.writeText(text).catch(() => {});

  const payload = {
    origin: a.dataset.origin,
    destination: a.dataset.dest,
    date: a.dataset.date,
    cabin: a.dataset.cabin || 'economy',
    passengers: Number(a.dataset.passengers || 1),
  };

  showToast(`✈️ ANA特典予約画面を開き、「${payload.origin} → ${payload.destination}（${payload.date}）」を自動入力しています…`);
  try {
    const res = await fetch('/api/ana-autofill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('ANA autofill request failed');
    showToast(`✅ ChromeでANA検索画面を開きました！条件が自動入力されます（クリップボードにもコピー済み）。`);
  } catch (err) {
    window.open(ANA_AWARD_URL, '_blank', 'noopener');
    showToast(`📋 「${text}」をコピーしてANA画面を開きました。`);
  }
});

// --- カレンダー表示の描画（クリックでその日のリストへ連動） ---
function renderCalendar() {
  if (!range) return;
  const byDate = {};
  results.forEach((r) => {
    const queryDirectOnly = r.query?.direct_only !== false;
    const validFlights = (r.flights || []).map((f) => normalizeFlight(f, r.query)).filter((f) => !queryDirectOnly || f.is_direct);
    if (validFlights.length > 0) {
      (byDate[r.query.date] ??= []).push(r.query.destination);
    }
  });

  const [sy, sm] = range.start.split('-').map(Number);
  const [ey, em] = range.end.split('-').map(Number);
  let html = '<div class="calendar-grid-wrap">';
  let y = sy, m = sm - 1;

  while (y < ey || (y === ey && m <= em - 1)) {
    const days = new Date(y, m + 1, 0).getDate();
    html += `<div class="month-card"><h3>${y}年 ${m + 1}月</h3><div class="cal-grid">` +
      DOW_NAMES.map((w) => `<div class="cal-wd">${w}</div>`).join('') +
      '<div class="cal-day empty"></div>'.repeat(new Date(y, m, 1).getDay());

    for (let d = 1; d <= days; d++) {
      const key = `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const hits = [...new Set(byDate[key] || [])];
      const tags = hits.slice(0, 4).map((c) => `<span class="cal-hit-tag">${esc(c)}</span>`).join('');
      const more = hits.length > 4 ? `<span class="cal-hit-tag">+${hits.length - 4}</span>` : '';

      html += `
        <div class="cal-day ${hits.length ? 'ok' : ''}" data-date="${hits.length ? key : ''}" title="${hits.length ? `${key} の空席（クリックで一覧表示）: ${hits.join(', ')}` : ''}">
          <span class="cal-day-num">${d}</span>
          <div class="cal-hits">${tags}${more}</div>
        </div>`;
    }
    html += '</div></div>';
    m++;
    if (m > 11) { m = 0; y++; }
  }
  html += '</div>';
  $('#view-calendar').innerHTML = html;

  // 空席がある日付マスをクリックしたら、その日で絞り込んでリスト表示へ切り替え
  document.querySelectorAll('.cal-day.ok').forEach((cell) => {
    cell.onclick = () => {
      selectedDateFilter = cell.dataset.date;
      $('#btn-reset-filter').hidden = false;
      $('#btn-reset-filter').textContent = `📅 ${selectedDateFilter} のみ表示中（× 解除）`;
      view = 'list';
      document.querySelectorAll('.tabs [data-view]').forEach((x) => x.classList.toggle('active', x.dataset.view === 'list'));
      render();
      showToast(`📅 ${selectedDateFilter} の空席フライトを表示しています`);
    };
  });
}

// --- CSV出力（Excel対応BOM付きUTF-8） ---
$('#btn-export-csv').onclick = () => {
  const rows = getFilteredRows();
  if (!rows.length) {
    showToast('⚠️ 出力する空席データがありません');
    return;
  }
  const csvLines = [['日付', '曜日', '出発地コード', '出発都市', '目的地コード', '目的都市', '予約クラス', '種別', '必要マイル', '出発時刻', '到着時刻']];
  for (const r of rows) {
    const q = r.query;
    const dow = getDowInfo(q.date).label;
    for (const f of r.flights) {
      csvLines.push([
        q.date,
        dow,
        q.origin,
        airportNames[q.origin] || q.origin,
        q.destination,
        airportNames[q.destination] || q.destination,
        f.fare_class || '',
        f.stop_label,
        f.miles,
        f.dep_time || '',
        f.arr_time || '',
      ]);
    }
  }
  const csvContent = '\uFEFF' + csvLines.map((line) => line.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `ana_award_flights_${fmt(new Date())}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('📥 CSVファイルをダウンロードしました！');
};
