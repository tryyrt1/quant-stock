"""一次性修复 index.html：添加实时追踪 Tab + 页面 + JS"""
import json

with open('static/index.html', 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Add tab button
tab_btn = '''
\t  <div class="tab" data-tab="intraday" onclick="switchTab('intraday');loadIntradayMonitor()"><span class="tab-icon">⚡</span>实时追踪</div>'''
c = c.replace('预测统计</span></div>\n\t</div>', '预测统计</span></div>' + tab_btn + '\n\t</div>')
print('1. Tab button added')

# 2. Add page-intraday
intraday_html = '''  <div id="page-intraday" class="hide">
    <div class="card" style="margin-bottom:8px">
      <div onclick="toggleCollapse('cpool')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none">
        <div>
          <span style="font-size:15px;font-weight:600">📋 候选池</span>
          <span id="candidateCount" style="font-size:12px;color:#aaa;margin-left:8px">加载中...</span>
        </div>
        <span id="cpoolToggle" style="font-size:14px;color:#888">▼</span>
      </div>
      <div id="cpoolBody" style="margin-top:8px">
        <div id="candidateSummary" style="display:flex;gap:16px;font-size:12px;color:#888;margin-bottom:8px;flex-wrap:wrap"></div>
        <div id="candidateList" style="max-height:300px;overflow-y:auto;font-size:12px"></div>
      </div>
    </div>
    <div class="card">
      <div onclick="toggleCollapse('alertBody')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none">
        <div>
          <span style="font-size:15px;font-weight:600">⚡ 实时异动</span>
          <span id="alertCount" style="font-size:12px;color:#ff6b81;margin-left:8px"></span>
          <span id="intradayStatus" style="font-size:11px;color:#888;margin-left:8px"></span>
        </div>
        <span id="alertToggle" style="font-size:14px;color:#888">▼</span>
      </div>
      <div id="alertBody" style="margin-top:8px">
        <div id="alertList" style="display:flex;flex-direction:column;gap:6px">
          <div style="text-align:center;padding:20px;color:#666;font-size:13px">加载中...</div>
        </div>
      </div>
    </div>
  </div>
'''
c = c.replace('<div id="page-predictions" class="hide">', intraday_html + '<div id="page-predictions" class="hide">')
print('2. Intraday page added')

# 3. Switch logic
c = c.replace(
    "document.getElementById('page-predictions').classList.toggle('hide',tab!=='predictions')",
    "document.getElementById('page-intraday').classList.toggle('hide',tab!=='intraday')\n    document.getElementById('page-predictions').classList.toggle('hide',tab!=='predictions')"
)
print('3. Switch logic added')

# 4. JS
js_code = '''
function toggleCollapse(id) {
  var body = document.getElementById(id)
  var toggle = document.getElementById(id + 'Toggle')
  if (!body || !toggle) return
  if (body.style.display === 'none') {
    body.style.display = 'block'
    toggle.textContent = '▼'
  } else {
    body.style.display = 'none'
    toggle.textContent = '▶'
  }
}

var _intradayTimer = null

function loadIntradayMonitor() {
  api('/api/intraday/candidates').then(function(data) {
    if (!data) return
    var cand = data.candidates || []
    document.getElementById('candidateCount').textContent = '候选池: ' + data.count + '只'
    if (cand.length > 0) {
      var totalRoe = 0, goodLiab = 0
      for (var j = 0; j < cand.length; j++) {
        totalRoe += (cand[j].roe || 0)
        if ((cand[j].liab_ratio || 1) < 0.5) goodLiab++
      }
      var avgRoe = (totalRoe / cand.length * 100).toFixed(1)
      document.getElementById('candidateSummary').innerHTML =
        '<span>平均ROE: ' + avgRoe + '%</span>' +
        '<span>负债<50%: ' + goodLiab + '/' + cand.length + '</span>'

      var html = ''
      for (var i = 0; i < cand.length; i++) {
        var s = cand[i]
        var roeStr = s.roe ? (s.roe * 100).toFixed(1) + '%' : '-'
        var liabStr = s.liab_ratio ? (s.liab_ratio * 100).toFixed(0) + '%' : '-'
        var gpStr = s.gp_margin ? (s.gp_margin * 100).toFixed(0) + '%' : '-'
        var grStr = s.profit_growth ? (s.profit_growth * 100).toFixed(1) + '%' : '-'
        var priceStr = s.price > 0 ? '¥' + s.price.toFixed(2) : ''
        var chgCls = s.change_pct > 0 ? 'up' : (s.change_pct < 0 ? 'down' : '')
        var chg = s.change_pct ? (s.change_pct > 0 ? '+' : '') + s.change_pct.toFixed(1) + '%' : ''
        var liabColor = (s.liab_ratio || 1) < 0.5 ? '#2ed573' : '#ffa502'
        html += '<div style="display:flex;align-items:center;padding:2px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:12px">' +
          '<span style="width:24px;color:#666">' + (i+1) + '</span>' +
          '<span style="width:110px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (s.name||s.code) + '</span>' +
          '<span style="color:#888;font-size:11px">(' + s.code + ')</span>' +
          '<span style="margin-left:6px;font-weight:500">' + priceStr + '</span>' +
          '<span class="' + chgCls + '" style="margin-left:4px;font-size:11px">' + chg + '</span>' +
          '<span style="margin-left:10px;color:#4fc3f7;font-size:11px">ROE ' + roeStr + '</span>' +
          '<span style="margin-left:6px;color:' + liabColor + ';font-size:11px">负债 ' + liabStr + '</span>' +
          '<span style="margin-left:6px;color:#888;font-size:11px">毛利 ' + gpStr + '</span>' +
          '<span style="margin-left:6px;color:#888;font-size:11px">增长 ' + grStr + '</span></div>'
      }
      document.getElementById('candidateList').innerHTML = html
    }
  })
  loadAlerts()
  if (_intradayTimer) clearInterval(_intradayTimer)
  _intradayTimer = setInterval(loadAlerts, 300000)
}

function loadAlerts() {
  api('/api/intraday/monitor').then(function(data) {
    if (!data) return
    var alerts = data.alerts || []
    var status = data.status || {}
    document.getElementById('intradayStatus').textContent = (status.last_scan || '--') + ' | ' + (status.market_open ? '交易中' : '已收盘')
    document.getElementById('alertCount').textContent = alerts.length > 0 ? '异动: ' + alerts.length + '只' : ''
    if (alerts.length === 0) {
      document.getElementById('alertList').innerHTML = '<div style="text-align:center;padding:20px;color:#666;font-size:13px">暂无异动' + (status.market_open ? ', 下次扫描: ' + (status.last_scan || '等待中...') : '') + '</div>'
      return
    }
    var html = ''
    for (var k = 0; k < alerts.length; k++) {
      var a = alerts[k]
      var pctCls = a.change_pct > 0 ? 'up' : 'down'
      var pctStr = (a.change_pct > 0 ? '+' : '') + a.change_pct.toFixed(1) + '%'
      var sigTags = ''
      var sigColors = {'放量':'#ff4757','异动':'#ffa502','活跃':'#2ed573','冲高':'#4fc3f7'}
      for (var si = 0; si < (a.sigs||[]).length; si++) {
        var s = a.sigs[si]
        sigTags += '<span style="font-size:10px;padding:1px 5px;background:' + (sigColors[s]||'#888') + '22;color:' + (sigColors[s]||'#888') + ';border-radius:3px;margin-right:3px">' + s + '</span>'
      }
      var reasons = (a.reasons||[]).map(function(r) { return '<span style="font-size:10px;color:#666;margin-left:4px">' + r + '</span>' }).join('')
      html += '<div class="card" style="padding:8px 12px;margin-bottom:4px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center">' +
        '<div><span style="font-weight:600;font-size:14px">' + a.name + '</span>' +
        '<span style="font-size:11px;color:#888;margin-left:6px">' + a.code + '</span></div>' +
        '<span class="' + pctCls + '" style="font-weight:700;font-size:15px">' + pctStr + '</span></div>' +
        '<div style="display:flex;gap:12px;font-size:11px;color:#aaa;margin-top:3px">' +
        '<span>换手: ' + (a.turnover||'-') + '%</span>' +
        '<span>金额: ' + (a.amount ? (a.amount/10000).toFixed(1) + '亿' : '-') + '</span>' +
        '<span>发现: ' + (a.time||'') + '</span></div>' +
        '<div style="margin-top:3px">' + sigTags + reasons + '</div></div>'
    }
    document.getElementById('alertList').innerHTML = html
  })
}
'''
c = c.replace('</script>', js_code + '\n</script>')
print('4. JS added')

with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('5. Saved!')
