(function () {
  var data = window.GEA_EXAMPLES || [];
  var tabs = document.getElementById("tabs");
  var box = document.getElementById("svgbox");
  var rep = document.getElementById("report");
  if (!tabs || !data.length) return;
  var COLOR = { healthy: "#43c59e", blocked: "#ff6b6b", at_risk: "#f5b84a" };
  var LABEL = { healthy: "健康", blocked: "阻断", at_risk: "有风险" };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function show(i) {
    var d = data[i];
    Array.prototype.forEach.call(tabs.children, function (b, k) { b.setAttribute("aria-selected", k === i ? "true" : "false"); });
    box.innerHTML = d.svg;
    var h = '<h3>' + esc(d.name) + ' <span class="status st-' + d.status + '">diagnose：' + LABEL[d.status] + '</span></h3>';
    h += '<p class="desc">' + esc(d.desc) + '</p>';
    h += '<div class="muted">validate：' + d.errors.length + ' 个错误 · ' + d.warnings.length + ' 个提醒 · <a href="' + encodeURI(d.file) + '">查看 JSON</a></div>';
    var li = "";
    d.patterns.forEach(function (p) { li += '<li class="p"><b>[' + p.repair_layer + '] ' + esc(p.pattern) + '</b>' + esc(p.evidence) + '</li>'; });
    d.errors.forEach(function (e) { li += '<li class="e"><b>' + esc(e.code) + '</b>' + esc(e.msg) + '</li>'; });
    d.warnings.slice(0, 6).forEach(function (w) { li += '<li class="w"><b>' + esc(w.code) + '</b>' + esc(w.msg) + '</li>'; });
    if (!li) li = '<li class="p"><b>无</b>结构上没有发现自欺漏洞（不证明结论正确）。</li>';
    rep.innerHTML = h + '<ul class="rows">' + li + '</ul>';
  }
  data.forEach(function (d, i) {
    var b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "tab");
    b.innerHTML = '<span class="dot" style="background:' + COLOR[d.status] + '"></span>' + esc(d.name);
    b.addEventListener("click", function () { show(i); });
    tabs.appendChild(b);
  });
  var start = Math.max(0, data.findIndex(function (d) { return d.slug === (location.hash.replace("#ex-", "") || "broken-circular"); }));
  show(start);
})();
