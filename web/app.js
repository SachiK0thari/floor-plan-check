'use strict';
const $ = id => document.getElementById(id);
let current = null, evidence = null, proposal = null, uploadId = null;
let saved = [], dirty = false, busy = false, explainerInfo = null;
const textFields = ['site_address', 'country', 'region', 'city', 'authority', 'facility_type', 'occupancy'];
function message(text) { $('message').textContent = text; }
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
async function api(path, body) {
  const response = await fetch('/api/' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const text = await response.text();
  let data = null;
  try { data = JSON.parse(text); } catch { /* a server fault may not be JSON */ }
  if (!response.ok || data === null) throw Error(data?.error || text.slice(0, 300) || 'Request failed (' + response.status + ')');
  return data;
}
function controls() {
  for (const el of document.querySelectorAll('input,select,button')) el.disabled = busy;
  $('run').disabled = busy || dirty || !current?.drawing || !current.settings.confirmed ||
    !current.settings.ada_reference;
}
function setBusy(value) { busy = value; controls(); }
function markDirty() {
  dirty = true;
  $('results').replaceChildren();
  $('run-status').textContent = 'Unsaved changes. Save and confirm before running again.';
  controls();
}
function fill(settings) {
  for (const field of textFields) $(field).value = settings[field] || '';
  $('permit_date').value = settings.permit_date || '';
  $('work_type').value = settings.work_type || '';
  $('sprinklered').value = settings.sprinklered == null ? '' : String(settings.sprinklered);
  $('scale_mm_per_point').value = settings.scale_mm_per_point ?? '';
  $('confirmed').checked = !!settings.confirmed;
  $('ada_reference').checked = !!settings.ada_reference;
}
function settingsFromForm() {
  const settings = Object.fromEntries(textFields.map(field => [field, $(field).value]));
  settings.country = settings.country.trim().toUpperCase();
  settings.permit_date = $('permit_date').value || null;
  settings.work_type = $('work_type').value || null;
  settings.sprinklered = $('sprinklered').value === '' ? null : $('sprinklered').value === 'true';
  settings.scale_mm_per_point = $('scale_mm_per_point').value === '' ? null : Number($('scale_mm_per_point').value);
  settings.confirmed = $('confirmed').checked;
  settings.ada_reference = $('ada_reference').checked;
  return settings;
}
function table(titles) {
  const wrap = node('div', ''); wrap.className = 'table-wrap';
  const el = node('table', ''), head = node('thead', ''), row = node('tr', ''), body = node('tbody', '');
  for (const title of titles) row.append(node('th', title));
  head.append(row); el.append(head, body); wrap.append(el);
  return {wrap, body};
}
function addRow(body, cells) {
  const row = node('tr', '');
  for (const cell of cells) row.append(cell instanceof Node ? cell : node('td', cell ?? ''));
  body.append(row);
  return row;
}
function renderEvidence() {
  const box = $('evidence'); box.replaceChildren();
  if (!evidence) return;
  if (evidence.candidates.length) {
    const {wrap, body} = table(['Field', 'Value (unconfirmed)', 'Text found on the drawing', 'Where']);
    for (const candidate of evidence.candidates) for (const item of candidate.evidence) {
      const where = [item.page ? 'page ' + item.page : null, item.layout ? 'layout ' + item.layout : null,
        item.anchor ? 'at ' + item.anchor.map(v => Math.round(v)).join(', ') : null].filter(Boolean).join(' · ');
      addRow(body, [candidate.field, candidate.value, item.raw_text, where]);
    }
    box.append(wrap);
  } else box.append(node('p', 'No labelled location hints found. Enter location manually.'));
  if (evidence.pages_without_text.length) box.append(node('p', 'OCR pending — pages without text: ' + evidence.pages_without_text.join(', ')));
}
function safeLink(url, text) {
  try {
    const parsed = new URL(url);
    if (!['http:', 'https:'].includes(parsed.protocol)) return node('span', text);
    const link = node('a', text); link.href = parsed.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    return link;
  } catch { return node('span', text); }
}
function showAvailability(availability) {
  const box = $('availability'); box.replaceChildren();
  box.append(node('p', 'Local code: not checked. ' + (availability.adoption_available ?
    'Adoption metadata available; local compliance execution is not enabled in this flow.' : availability.notes.join(' '))));
  for (const record of availability.records) {
    const p = node('p', [record.name, record.base_code, record.base_edition, 'Effective: ' + record.effective_date].join(' · '));
    if (record.source_url) p.append(safeLink(record.source_url, ' Official source'));
    box.append(p);
  }
}
const VERDICTS = {fail: ['✕', 'Fail'], borderline: ['!', 'Borderline'], unknown: ['?', 'Unknown'],
  pass: ['✓', 'Pass'], not_applicable: ['–', 'Not applicable']};
function fmt(value) { return String(Math.round(value * 10) / 10); }
function measurementText(finding) {
  const m = finding.measured;
  return m ? fmt(m.value_mm) + ' mm (' + (m.value_mm / 25.4).toFixed(2) + ' in) ± ' + fmt(m.sigma_mm) + ' mm' : 'Not measured';
}
function requirementText(finding) {
  if (!finding.required) return 'Not determined';
  return finding.required + (finding.required_mm == null ? '' : ' (' + fmt(finding.required_mm) + ' mm)');
}
function verdictCell(finding) {
  const [symbol, label] = VERDICTS[finding.verdict] || ['', finding.verdict];
  const cell = node('td', ''), strong = node('strong', symbol + ' ' + label);
  cell.className = 'v-' + finding.verdict; cell.append(strong);
  if (finding.provisional) cell.append(node('div', 'PROVISIONAL'));
  return cell;
}
function notesCell(finding, explanation) {
  const cell = node('td', '');
  if (finding.reason) cell.append(node('div', finding.reason));
  const more = [...finding.surfaced_exceptions.map(name => 'Exception not checked: ' + name),
    ...finding.obligations.map(why => 'Tested because: ' + why)];
  if (more.length) {
    const details = node('details', '');
    details.append(node('summary', 'Exceptions and scoping (' + more.length + ')'));
    for (const line of more) details.append(node('div', line));
    cell.append(details);
  }
  const citation = finding.citation;
  if (citation) {
    const label = [citation.code, citation.edition + ',', '§' + citation.section].join(' ');
    cell.append(citation.source_url ? safeLink(citation.source_url, label) : node('span', label));
  }
  if (explanation) {
    const box = node('div', ''); box.className = 'ai';
    box.append(node('small', 'Explanation (language model)'), node('span', explanation.text));
    cell.append(box);
  }
  return cell;
}
function explainControls(box, result) {
  const wrap = node('div', ''); wrap.className = 'explain';
  const run = result.explanations;
  if (run) {
    wrap.append(node('p', 'Explanations written by ' + run.model_id + ' through ' + run.service + '. PlanCheck filled in every value and citation; the model did not decide any verdict. ' +
      run.explanations.length + ' explained, ' + run.rejections.length + ' outputs rejected by the validator, ' + run.unexplained.length + ' left unexplained.'));
  } else if (explainerInfo && explainerInfo.available) {
    const button = node('button', 'Explain findings in plain language'); button.className = 'secondary'; button.id = 'explain';
    button.onclick = () => explainFindings(result.id);
    wrap.append(button, node('small', 'Sends each finding’s check, verdict, measurements and the cited ADA text to ' + explainerInfo.service +
      ' (model ' + explainerInfo.model + '). No drawing text, room labels, element ids or address are sent. The model never decides a verdict.'));
  } else if (explainerInfo) {
    wrap.append(node('small', 'Plain-language explanations are off. Set ' + explainerInfo.key_name + ' in .env and restart the server to turn them on.'));
  }
  box.append(wrap);
}
async function explainFindings(runId) {
  if (!current || dirty) return;
  setBusy(true); message('Asking ' + explainerInfo.service + ' to explain the findings…');
  try {
    current = await api('explain', {id: current.id, run_id: runId});
    renderResults(); await refresh(); message('Explanations added. The verdicts are unchanged.');
  } catch (error) { message(error.message); }
  finally { setBusy(false); }
}
// Selecting a finding highlights its row and its evidence on the plan; selecting it again clears it.
function selectFinding(number, scroll) {
  const box = $('results');
  const same = box.querySelector('tr.selected')?.dataset.finding === String(number);
  for (const el of box.querySelectorAll('.pc-active, tr.selected')) el.classList.remove('pc-active', 'selected');
  if (same) return;
  box.querySelector('#pc-f' + number)?.classList.add('pc-active');
  const row = box.querySelector('#pc-row-' + number);
  if (row) { row.classList.add('selected'); if (scroll) row.scrollIntoView({block: 'nearest'}); }
}
async function loadPlan(holder, projectId, runId) {
  try {
    const response = await fetch('/api/download/' + projectId + '/' + runId + '/plan.svg');
    if (!response.ok) throw Error('Plan drawing unavailable');
    const doc = new DOMParser().parseFromString(await response.text(), 'image/svg+xml');
    if (doc.documentElement.nodeName !== 'svg') throw Error('Plan drawing unavailable');
    holder.replaceChildren(document.importNode(doc.documentElement, true));
    holder.onclick = event => {
      const finding = event.target.closest('.pc-finding');
      if (!finding) return;
      event.preventDefault(); selectFinding(finding.dataset.finding, true);
    };
  } catch (error) { holder.textContent = error.message; }
}
function renderCoverage(box, report) {
  const coverage = report.coverage, details = node('details', '');
  details.append(node('summary', 'Coverage, missing inputs and unchecked provisions'));
  const list = node('ul', '');
  list.append(node('li', 'Not visible on a plan: ' + (coverage.not_visible_on_a_plan || []).join('; ')));
  list.append(node('li', 'Unimplemented provisions: ' + ((coverage.not_implemented || []).join(', ') || 'none in the selected rulesets')));
  for (const note of coverage.notes || []) list.append(node('li', note));
  details.append(list);
  const unresolved = coverage.unresolved || [];
  if (unresolved.length) {
    details.append(node('p', 'Needs an answer or a measurement (' + unresolved.length + '):'));
    const {wrap, body} = table(['Rule', 'Elements', 'Reason']);
    for (const item of unresolved) addRow(body, [item.rule_id, item.element_ids.join(', ') || 'Project', item.reason]);
    details.append(wrap);
  }
  details.append(node('p', 'Excluded by scoping or applicability: ' + (coverage.excluded || []).length + ' records. The downloadable report lists each one.'));
  box.append(details);
}
function renderGoverning(box, report) {
  const details = node('details', '');
  details.append(node('summary', 'Governing requirements and comparison limits'));
  if (report.governing_requirements.length) {
    const {wrap, body} = table(['Element', 'Quantity', 'Required', 'Governing rules', 'Reason']);
    for (const item of report.governing_requirements) addRow(body, [item.element_id, item.quantity + ' (' + item.relation + ')',
      item.required + ' (' + fmt(item.required_mm) + ' mm)', item.governing_rule_ids.join(', '), item.reason]);
    details.append(wrap);
  } else details.append(node('p', 'None derived. A governing requirement needs two regimes testing the same quantity on the same element.'));
  if (report.governing_not_derived.length) {
    const {wrap, body} = table(['Element', 'Quantity', 'Rules', 'Why no comparison']);
    for (const item of report.governing_not_derived) addRow(body, [item.element_id, item.quantity, item.rule_ids.join(', '), item.reason]);
    details.append(wrap);
  }
  box.append(details);
}
function renderResults() {
  const box = $('results'); box.replaceChildren();
  if (!current) { $('run-status').textContent = 'Save a drawing and confirmed location to begin.'; return; }
  const source = current.drawing ? 'Saved drawing: ' + current.drawing.name + '. ' : 'No saved drawing. ';
  $('run-status').textContent = source + 'Revision ' + current.revision + ' · ' + current.status +
    (current.error ? ' · ' + current.error : '') + (current.requires_new_run ? ' · New run required.' : '');
  const result = current.check_results;
  if (!result || current.requires_new_run) return;
  const report = result.report;
  box.append(node('p', 'ADA reference comparison only. Local building code: not checked. Results reflect saved revision ' + result.revision + '.'));
  const numbered = report.findings.map((finding, index) => ({finding, number: index + 1}));
  const counts = {};
  for (const {finding} of numbered) counts[finding.verdict] = (counts[finding.verdict] || 0) + 1;
  const chips = node('ul', ''); chips.className = 'chips';
  for (const [verdict, [symbol, label]] of Object.entries(VERDICTS)) if (counts[verdict]) {
    const chip = node('li', symbol + ' ' + label + ': ' + counts[verdict]); chip.className = 'chip v-' + verdict; chips.append(chip);
  }
  box.append(chips);
  explainControls(box, result);
  const explained = {};
  for (const item of result.explanations?.explanations || []) explained[item.finding] = item;
  const review = node('div', ''); review.className = 'review';
  const plan = node('div', 'Loading the plan…'); plan.className = 'plan';
  const side = node('div', ''); side.className = 'plan-side';
  side.append(plan, node('small', 'Solid red with a number: fail. Dashed amber with a number: borderline. Dotted grey: checked, result unknown. Thin green: pass. Select a row or a shape to highlight it.'));
  const order = Object.keys(VERDICTS);
  const shown = numbered.filter(item => item.finding.verdict !== 'not_applicable')
    .sort((a, b) => order.indexOf(a.finding.verdict) - order.indexOf(b.finding.verdict));
  const {wrap, body} = table(['#', 'Verdict', 'Element', 'Check', 'Measured ± standard uncertainty', 'Required', 'Notes and citation']);
  for (const {finding, number} of shown) {
    const row = addRow(body, [String(number), verdictCell(finding), finding.element_ids.join(', ') || 'Project',
      finding.title, measurementText(finding), requirementText(finding), notesCell(finding, explained[number])]);
    row.id = 'pc-row-' + number; row.dataset.finding = number; row.tabIndex = 0;
    row.onclick = event => { if (!event.target.closest('a')) selectFinding(number, false); };
    row.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectFinding(number, false); } };
  }
  const findings = node('div', ''); findings.className = 'findings';
  findings.append(wrap, node('small', (counts.not_applicable || 0) + ' findings were not applicable; the downloadable report lists them.'));
  review.append(side, findings); box.append(review);
  loadPlan(plan, current.id, result.id);
  if (report.group_findings.length) {
    const groups = node('details', '');
    groups.append(node('summary', 'Group obligations (' + report.group_findings.length + ')'));
    const grouped = table(['Verdict', 'Group', 'Check', 'Notes and citation']);
    for (const finding of report.group_findings) addRow(grouped.body, [verdictCell(finding), finding.group || '', finding.title, notesCell(finding)]);
    groups.append(grouped.wrap); box.append(groups);
  }
  renderCoverage(box, report); renderGoverning(box, report);
  const downloads = node('div', ''); downloads.className = 'downloads';
  for (const filename of ['report.html', 'report.md', 'plan.svg', 'run.json', 'model.dxf', 'model.ifc', 'model.glb', 'issues.bcfzip']) {
    const link = node('a', filename); link.href = '/api/download/' + current.id + '/' + result.id + '/' + filename;
    link.download = filename; downloads.append(link);
  }
  box.append(node('h3', 'Downloads'), downloads);
}
async function refresh() {
  saved = await api('projects');
  $('projects').replaceChildren(new Option('New plan', ''));
  for (const project of saved) $('projects').add(new Option(project.name, project.id));
  $('projects').value = current?.id || '';
}
$('projects').onchange = () => {
  current = saved.find(project => project.id === $('projects').value) || null;
  evidence = current?.evidence || null; uploadId = null; proposal = null; dirty = false;
  $('upload').value = ''; $('apply').hidden = true;
  $('proposal').textContent = current ? 'Saved drawing evidence. Review settings before reconfirming.' : 'Upload a drawing to see unconfirmed location hints.';
  $('name').value = current?.name || 'Untitled plan'; fill(current?.settings || {});
  renderEvidence(); renderResults(); controls();
  showAvailability(current?.availability || {notes: ['Select and confirm project details.'], records: []});
  message('');
};
$('upload').onchange = async () => {
  const file = $('upload').files[0]; if (!file) return;
  setBusy(true); markDirty();
  try {
    if (file.size > 14000000) throw Error('Use a drawing smaller than 14 MB.');
    message('Uploading and extracting vector text…');
    const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
    for (const byte of bytes) binary += String.fromCharCode(byte);
    const data = await api('extract', {name: file.name, data: btoa(binary)});
    uploadId = data.upload_id; evidence = data.extraction; proposal = data.proposal;
    renderEvidence();
    $('proposal').textContent = proposal.notes.join(' ') + ' Conflicting fields: ' + (proposal.conflicts.join(', ') || 'none') +
      '. Matched records: ' + (proposal.matched_slugs.join(', ') || 'none');
    $('apply').hidden = false; $('confirmed').checked = false;
    message('Drawing uploaded. Review hints and save to attach it to this project.');
  } catch (error) { message(error.message); }
  finally { setBusy(false); }
};
$('apply').onclick = () => { fill(proposal.settings); markDirty(); message('Hints applied as unconfirmed draft fields. Review and correct before saving.'); };
$('settings').addEventListener('input', event => {
  if (event.target.id !== 'confirmed') $('confirmed').checked = false;
  markDirty();
});
$('name').addEventListener('input', markDirty);
async function save(draft) {
  setBusy(true);
  try {
    const settings = settingsFromForm(); if (draft) settings.confirmed = false;
    if (!draft && !settings.confirmed) throw Error('Confirm the reviewed details, or save as draft.');
    current = await api('save', {id: current?.id || null, name: $('name').value, settings, evidence, upload_id: uploadId});
    uploadId = null; dirty = false; fill(current.settings);
    showAvailability(current.availability); renderResults(); await refresh();
    message(draft ? 'Draft saved.' : 'Project saved. You can now run an explicit ADA reference comparison if selected.');
  } catch (error) { message(error.message); }
  finally { setBusy(false); }
}
$('settings').onsubmit = event => { event.preventDefault(); save(false); };
$('draft').onclick = () => save(true);
$('run').onclick = async () => {
  if (!current || dirty) return;
  setBusy(true); $('results').replaceChildren(); message('Processing saved drawing, running ADA reference checks and preparing exports…');
  try {
    current = await api('run', {id: current.id, revision: current.revision});
    renderResults(); await refresh(); message('Reference comparison complete. Review unknown findings and coverage. Local code is not checked.');
  } catch (error) {
    message(error.message);
    try { await refresh(); current = saved.find(project => project.id === current.id); renderResults(); } catch { /* keep original error visible */ }
  } finally { setBusy(false); }
};
(async () => {
  try {
    await refresh();
    for (const record of await api('authorities')) $('authorities').append(new Option(record.name, record.name));
    try { explainerInfo = await api('explainer'); } catch { explainerInfo = null; }
    // ?project=<id> reopens that saved plan, so a reload or a shared local link keeps its place.
    const wanted = new URLSearchParams(location.search).get('project');
    if (wanted && saved.some(project => project.id === wanted)) { $('projects').value = wanted; $('projects').onchange(); }
  } catch (error) { message(error.message); }
  controls();
})();
