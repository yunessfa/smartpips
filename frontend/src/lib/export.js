/*
 * Dependency-free spreadsheet export.
 *
 * The project has no build-time access to an npm registry in this environment,
 * and pulling a ~500KB library (SheetJS/exceljs) into the bundle just to write
 * a flat table would be a poor trade. XLSX is a ZIP of a few XML parts, so we
 * write the ZIP ourselves with STORE (no compression). That keeps the writer
 * small and produces a genuine .xlsx that Excel, Numbers and LibreOffice open
 * natively -- unlike renaming a CSV to .xls, which triggers a format warning.
 *
 * Numbers are written as real numeric cells (t="n") so Excel can sum/sort them.
 * Everything else is written as an inline string, which keeps Persian text
 * correct without needing a shared-strings table.
 */

/* ---------------------------------------------------------------- CRC-32 */

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/* ------------------------------------------------------------ ZIP (store) */

const utf8 = (s) => new TextEncoder().encode(s);

function dosDateTime(d) {
  const time = (d.getHours() << 11) | (d.getMinutes() << 5) | (Math.floor(d.getSeconds() / 2) & 0x1f);
  const date = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  return { time, date };
}

/**
 * Build a ZIP archive from `[{ name, data: Uint8Array }]` using STORE.
 * Returns a Blob. Sizes stay well under the 4GB ZIP64 boundary for a journal
 * export, so the classic 32-bit headers are sufficient.
 */
function zipStore(files) {
  const now = dosDateTime(new Date());
  const locals = [];
  const centrals = [];
  let offset = 0;

  files.forEach((file) => {
    const nameBytes = utf8(file.name);
    const crc = crc32(file.data);
    const size = file.data.length;

    const local = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true); // version needed
    lv.setUint16(6, 0x0800, true); // UTF-8 filename flag
    lv.setUint16(8, 0, true); // STORE
    lv.setUint16(10, now.time, true);
    lv.setUint16(12, now.date, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, size, true);
    lv.setUint32(22, size, true);
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);
    local.set(nameBytes, 30);

    const central = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(central.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, now.time, true);
    cv.setUint16(14, now.date, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, size, true);
    cv.setUint32(24, size, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(42, offset, true);
    central.set(nameBytes, 46);

    locals.push(local, file.data);
    centrals.push(central);
    offset += local.length + size;
  });

  const centralSize = centrals.reduce((a, c) => a + c.length, 0);
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, offset, true);

  return new Blob([...locals, ...centrals, end], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

/* ----------------------------------------------------------------- XLSX */

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    // Control characters are illegal in XML 1.0 and would corrupt the file.
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
}

function colName(index) {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function cellXml(ref, value) {
  if (value == null || value === "") return `<c r="${ref}"/>`;
  if (typeof value === "number" && Number.isFinite(value)) {
    return `<c r="${ref}" t="n"><v>${value}</v></c>`;
  }
  if (typeof value === "boolean") {
    return `<c r="${ref}" t="b"><v>${value ? 1 : 0}</v></c>`;
  }
  // xml:space="preserve" protects leading/trailing spaces in free-text notes.
  return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value)}</t></is></c>`;
}

/**
 * @param {string} sheetName
 * @param {Array<{ key: string, label: string }>} columns
 * @param {Array<Record<string, unknown>>} rows
 */
export function buildXlsxBlob(sheetName, columns, rows) {
  const header = columns
    .map((col, i) => cellXml(`${colName(i)}1`, col.label))
    .join("");

  const body = rows
    .map((row, r) => {
      const cells = columns
        .map((col, i) => cellXml(`${colName(i)}${r + 2}`, row[col.key]))
        .join("");
      return `<row r="${r + 2}">${cells}</row>`;
    })
    .join("");

  const widths = columns
    .map((col, i) => `<col min="${i + 1}" max="${i + 1}" width="${Math.min(38, Math.max(11, col.label.length + 4))}" customWidth="1"/>`)
    .join("");

  const sheet =
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">` +
    `<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>` +
    `<cols>${widths}</cols>` +
    `<sheetData><row r="1">${header}</row>${body}</sheetData>` +
    `</worksheet>`;

  const workbook =
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ` +
    `xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
    `<sheets><sheet name="${xmlEscape(sheetName).slice(0, 31)}" sheetId="1" r:id="rId1"/></sheets>` +
    `</workbook>`;

  const workbookRels =
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
    `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>` +
    `</Relationships>`;

  const rootRels =
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
    `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>` +
    `</Relationships>`;

  const contentTypes =
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
    `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
    `<Default Extension="xml" ContentType="application/xml"/>` +
    `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
    `<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>` +
    `</Types>`;

  return zipStore([
    { name: "[Content_Types].xml", data: utf8(contentTypes) },
    { name: "_rels/.rels", data: utf8(rootRels) },
    { name: "xl/workbook.xml", data: utf8(workbook) },
    { name: "xl/_rels/workbook.xml.rels", data: utf8(workbookRels) },
    { name: "xl/worksheets/sheet1.xml", data: utf8(sheet) },
  ]);
}

/* ------------------------------------------------------------------ CSV */

function csvCell(value) {
  if (value == null) return "";
  const s = String(value);
  // A leading =, +, - or @ makes Excel treat the cell as a formula. Prefixing
  // an apostrophe neutralises CSV injection without altering what is shown.
  const safe = /^[=+\-@]/.test(s) ? `'${s}` : s;
  return /[",\n\r;]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function buildCsvBlob(columns, rows) {
  const lines = [columns.map((c) => csvCell(c.label)).join(",")];
  rows.forEach((row) => {
    lines.push(columns.map((c) => csvCell(row[c.key])).join(","));
  });
  // The BOM is what makes Excel on Windows read the file as UTF-8; without it
  // Persian column values arrive as mojibake.
  return new Blob(["\uFEFF", lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
}

/* -------------------------------------------------------------- download */

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoking immediately can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function timestampSlug(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}` +
    `-${pad(date.getHours())}${pad(date.getMinutes())}`
  );
}
