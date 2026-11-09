"use strict";
const $ = id => document.getElementById(id);
const maxBytes = 10 * 1024 * 1024;
let busy = false;
let automatic = false, autoTimer = null, autoController = null, autoRevision = '', autoGeneration = 0, autoUpdates = 0;
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function failure(message) { $("error").textContent = message; $("error").hidden = false; }
function setBusy(value) {
  busy = value;
  for (const id of ["analyze", "sample", "reset", "log-file", "log-text"]) $(id).disabled = value;
  $("auto-start").disabled = value || automatic;
  $("analysis-form").setAttribute("aria-busy", String(value));
}
function render(data, focus = true) {
  $("error-count").textContent = data.summary.error_count;
  $("warning-count").textContent = data.summary.warning_count;
  $("info-count").textContent = data.summary.info_count;
  $("group-count").textContent = data.summary.group_count;
  $("line-count").textContent = data.summary.line_count;
  $("rule-version").textContent = `진단 규칙 ${data.rules_version}`;
  $("result-notice").textContent = data.notice;
  $("groups").replaceChildren();
  if (!data.groups.length) $("groups").append(node("p", "현재 규칙으로 검출된 오류가 없습니다. 로그 일부가 누락되었거나 지원하지 않는 형식일 수 있습니다.", "panel"));
  for (const g of data.groups) {
    const card = node("article", undefined, "error-group");
    const heading = node("div", undefined, "group-heading");
    heading.append(node("h3", g.title), node("span", `${({error:'오류',warning:'확인 필요',info:'참고'})[g.severity]} · ${g.count}회`, "badge"));
    card.append(heading, node("p", g.preview, "preview"), node("p", g.explanation));
    card.append(node("p", "관련 모드 후보", "label"), node("p", g.related_mod_candidates.join(", ") || "명시적 모드 표기 없음"), node("p", g.candidate_note, "small muted"));
    card.append(node("p", "다음 확인", "label"));
    const steps = node("ul"); for (const step of g.next_steps) steps.append(node("li", step)); card.append(steps);
    const details = node("details");
    details.append(node("summary", `원문 근거 보기 · 최초 ${g.occurrences[0].start_line}–${g.occurrences[0].end_line}줄 · ${g.count}회`));
    // Lazy rendering prevents thousands of repeated stack traces from blocking initial display.
    details.addEventListener("toggle", () => {
      if (!details.open || details.dataset.loaded) return;
      details.dataset.loaded = "true";
      let shown = 0;
      const more = node("button", "다음 20개 발생 위치 보기"); more.type = "button";
      function page() {
        const end = Math.min(shown + 20, g.occurrences.length);
        for (; shown < end; shown++) {
          const occurrence = g.occurrences[shown];
          details.append(node("p", `${shown + 1}번째 · ${occurrence.start_line}–${occurrence.end_line}줄`, "small"));
          details.append(node("pre", occurrence.raw.split("\n").map((line, i) => `${occurrence.start_line + i} | ${line}`).join("\n")));
        }
        more.remove(); if (shown < g.occurrences.length) details.append(more);
      }
      more.addEventListener("click", page); page();
    });
    card.append(details); $("groups").append(card);
  }
  $("results").hidden = false; if (focus) $("results-title").focus();
}
function stopAutomatic() {
  automatic = false; autoGeneration++;
  clearTimeout(autoTimer); autoController?.abort();
  $("auto-start").disabled = busy; $("auto-stop").disabled = true;
  $("auto-status").textContent = '자동 입력을 중지했습니다. 다시 시작하면 현재 로그를 읽습니다.';
  $("status").textContent = '자동 입력 중지 · 화면에는 마지막 분석 결과가 남아 있습니다.';
}
async function pollAutomatic(generation) {
  if (!automatic || generation !== autoGeneration) return;
  const controller = new AbortController(); autoController = controller;
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/api/autolog?known=' + encodeURIComponent(autoRevision), {signal:controller.signal});
    const data = await response.json();
    if (!automatic || generation !== autoGeneration) return;
    if (!response.ok) throw new Error(data.error || '자동 입력 요청에 실패했습니다.');
    $("error").hidden = true;
    if (data.state !== 'ready') {
      autoRevision = ''; $("results").hidden = true; $("auto-source").hidden = true;
      $("auto-status").textContent = data.message;
      $("status").textContent = '자동 입력 대기 중 · 2초마다 다시 확인합니다.';
    } else {
      if (data.changed) { render(data.result, false); autoRevision = data.revision; autoUpdates++; }
      $("auto-status").textContent = `자동 입력 중 · 2초마다 변경 확인 · 분석 갱신 ${autoUpdates}회`;
      $("auto-source").textContent = `Player.log · ${data.source.bytes.toLocaleString()}바이트 · 파일 수정 ${new Date(data.source.modified_at).toLocaleString()}`;
      $("auto-source").hidden = false;
      $("status").textContent = data.changed ? 'Player.log를 자동으로 읽어 분석했습니다. 다음 변경을 기다립니다.' : '새 변경 없음 · 자동 확인 중입니다.';
    }
  } catch (e) {
    if (automatic && generation === autoGeneration) {
      $("auto-status").textContent = '연결을 확인하고 있습니다. 2초 후 자동으로 다시 시도합니다.';
      $("status").textContent = '현재 결과는 마지막 분석 결과입니다.';
    }
  } finally {
    clearTimeout(timeout);
    if (automatic && generation === autoGeneration) autoTimer = setTimeout(() => pollAutomatic(generation), 2000);
  }
}
$("auto-start").addEventListener('click', () => {
  if (busy || automatic) return;
  automatic = true; autoRevision = ''; autoUpdates = 0; autoGeneration++;
  $("auto-start").disabled = true; $("auto-stop").disabled = false;
  $("manual-input").open = false; $("error").hidden = true; $("results").hidden = true;
  $("auto-status").textContent = 'Player.log를 확인하고 있습니다.';
  pollAutomatic(autoGeneration);
});
$("auto-stop").addEventListener('click', stopAutomatic);
async function analyze(body, headers) {
  if (busy) return;
  $("error").hidden = true; $("results").hidden = true;
  const size = body instanceof Blob ? body.size : new TextEncoder().encode(body).length;
  if (size > maxBytes) { failure("입력은 최대 10MB까지 가능합니다."); return; }
  setBusy(true); $("status").textContent = "로그를 분석하고 있습니다.";
  try {
    const response = await fetch("/api/analyze", {method:"POST", headers, body, signal:AbortSignal.timeout(60000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "분석에 실패했습니다.");
    render(data); $("status").textContent = "분석이 완료됐습니다. 입력한 로그는 서버에 저장되지 않습니다.";
  } catch (e) {
    failure(e.name === "TimeoutError" ? "응답 시간이 초과됐습니다. 잠시 후 다시 시도하세요." : e.message === "Failed to fetch" ? "서버에 연결하지 못했습니다. 연결 상태를 확인하세요." : e.message);
    $("status").textContent = "분석을 완료하지 못했습니다.";
  } finally { setBusy(false); }
}
$("analysis-form").addEventListener("submit", event => {
  if (automatic) stopAutomatic();
  event.preventDefault(); const file = $("log-file").files[0]; const text = $("log-text").value;
  if (file && text.trim()) { failure("파일과 붙여넣기 중 하나만 입력해 주세요."); return; }
  if (file) {
    if (!/\.(log|txt)$/i.test(file.name)) { failure(".log 또는 .txt 파일만 분석할 수 있습니다."); return; }
    analyze(file, {"Content-Type":"application/octet-stream", "X-File-Name":encodeURIComponent(file.name)});
  } else analyze(text, {"Content-Type":"text/plain;charset=UTF-8"});
});
$("sample").addEventListener("click", async () => {
  if (busy) return;
  if (automatic) stopAutomatic();
  setBusy(true);
  try {
    const r = await fetch("/static/sample.log"); if (!r.ok) throw new Error("샘플을 불러오지 못했습니다.");
    $("log-file").value = ""; $("log-text").value = await r.text();
    setBusy(false);
    await analyze($("log-text").value, {"Content-Type":"text/plain;charset=UTF-8"});
  } catch { failure("샘플을 불러오지 못했습니다. 서버 연결을 확인하세요."); }
  finally { setBusy(false); }
});
$("reset").addEventListener("click", () => { if (automatic) stopAutomatic(); HTMLFormElement.prototype.reset.call($("analysis-form")); $("groups").replaceChildren(); $("results").hidden = true; $("error").hidden = true; $("status").textContent = "입력을 기다리고 있습니다."; $("log-file").focus(); });
fetch("/health").then(r => r.json()).then(data => { $("app-version").textContent = `버전 ${data.version.slice(0,12)}`; }).catch(() => { $("app-version").textContent = "프로그램 버전 확인 불가"; });
