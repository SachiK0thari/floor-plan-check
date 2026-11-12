'use strict';
const $ = id => document.getElementById(id);
let current = null, evidence = null, proposal = null, uploadId = null;
let saved = [], dirty = false, busy = false;
const textFields = ['site_address', 'country', 'region', 'city', 'authority', 'facility_type', 'occupancy'];
function message(text) { $('message').textContent = text; }
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
async function api(path, body) {
  const response = await fetch('/api/' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Request failed');
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
function renderEvidence() {
  const box = $('evidence'); box.replaceChildren();
  if (!evidence) return;
  for (const candidate of evidence.candidates) {
    box.append(node('h3', candidate.field + ': ' + candidate.value));
    for (const item of candidate.evidence) box.append(node('pre', JSON.stringify(item, null, 2)));
  }
  if (!evidence.candidates.length) box.append(node('p', 'No labelled location hints found. Enter location manually.'));
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
  const downloads = node('div', ''); downloads.className = 'downloads';
  for (const filename of ['report.html', 'report.md', 'run.json', 'model.dxf', 'model.ifc', 'model.glb', 'issues.bcfzip']) {
    const link = node('a', filename); link.href = '/api/download/' + current.id + '/' + result.id + '/' + filename;
    link.download = filename; downloads.append(link);
  }
  box.append(downloads);
  const coverage = node('details', ''); coverage.open = true;
  coverage.append(node('summary', 'Coverage, missing inputs and unchecked provisions'), node('pre', JSON.stringify(report.coverage, null, 2)));
  box.append(coverage);
  const findings = [...report.findings, ...report.group_findings];
  const counts = {};
  for (const finding of findings) counts[finding.verdict] = (counts[finding.verdict] || 0) + 1;
  box.append(node('p', 'Findings: ' + (Object.entries(counts).map(([k,v]) => k + ': ' + v).join(' · ') || 'none')));
  const wrap = node('div', ''); wrap.className = 'table-wrap';
  const table = node('table', ''), head = node('thead', ''), row = node('tr', '');
  for (const title of ['Verdict / element', 'Requirement', 'Measurement', 'Reason / citation']) row.append(node('th', title));
  head.append(row); table.append(head);
  const body = node('tbody', '');
  for (const finding of findings) {
    const row = node('tr', '');
    row.append(node('td', finding.verdict + '\n' + (finding.element_ids.join(', ') || 'Project / group')));
    row.append(node('td', finding.title + ' · ' + (finding.required || 'Unresolved')));
    row.append(node('td', finding.measured ? finding.measured.value_mm + ' mm ± ' + finding.measured.sigma_mm + ' mm standard uncertainty' : 'Not measured'));
    const reason = node('td', [finding.reason, ...finding.surfaced_exceptions, ...finding.obligations].filter(Boolean).join('\n'));
    const citation = finding.citation;
    if (citation) {
      const label = [citation.code, citation.edition, '§ ' + citation.section].join(' ');
      reason.append(node('br', ''), citation.source_url ? safeLink(citation.source_url, label) : node('span', label));
    }
    row.append(reason); body.append(row);
  }
  table.append(body); wrap.append(table); box.append(wrap);
  const governing = node('details', '');
  governing.append(node('summary', 'Governing requirements and comparison limits'), node('pre', JSON.stringify({
    governing_requirements: report.governing_requirements, governing_not_derived: report.governing_not_derived
  }, null, 2)));
  box.append(governing);
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
  } catch (error) { message(error.message); }
  controls();
})();
