(maxRows) => {
  // Read rendered report content only. No cookies, hidden application state or network calls.
  const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
  const root = document.getElementById('keywords-table');
  const tableRows = root ? Array.from(root.querySelectorAll('[role="row"],tr')).filter(visible) : [];
  const cells = row => Array.from(row.querySelectorAll('[role="cell"],[role="columnheader"],td,th')).filter(visible).map(c => c.innerText.trim());
  const headers = tableRows.length ? cells(tableRows[0]) : [];
  const rows = tableRows.slice(1).map(cells).filter(r => r.length === headers.length && r.some(Boolean));
  const country = document.querySelector('[aria-label^="Select country"]');
  return {
    schemaVersion: 1, kind: 'toolspd_keywordmagic_ui', sourceUrl: location.href,
    heading: document.querySelector('h1')?.innerText || '', countryLabel: country?.innerText?.trim() || '',
    headers, rows: rows.slice(0, maxRows), renderedRows: rows.length,
    tableText: root?.innerText?.slice(0, 20000) || '', pageText: document.body.innerText.slice(0, 10000),
    observedAt: new Date().toISOString(), coverage: 'Rendered report rows only; provider omissions and additional pages are not collected.'
  };
}
