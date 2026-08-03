const SPREADSHEET_ID = '1UGN1Jo1cCXodrx7CPrXReP4ChD7PSo7q_dHsM6pNsQ4';
const ACCESS_KEY = 'SUBSTITUA_POR_UMA_CHAVE_LONGA_E_SECRETA';
const MONTHS = [
  'JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN',
  'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'
];

function doPost(event) {
  const lock = LockService.getScriptLock();
  try {
    const payload = JSON.parse(event.postData.contents || '{}');
    if (payload.access_key !== ACCESS_KEY) {
      return response({ok: false, error: 'Chave de acesso inválida.'});
    }
    const records = Array.isArray(payload.records) ? payload.records : [];
    if (!records.length) {
      return response({ok: false, error: 'Nenhum registro recebido.'});
    }

    lock.waitLock(20000);
    const now = new Date();
    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const timeZone = spreadsheet.getSpreadsheetTimeZone();
    const month = Number(Utilities.formatDate(now, timeZone, 'M')) - 1;
    const year = Utilities.formatDate(now, timeZone, 'yyyy');
    const tabName = `${MONTHS[month]} ${year}`;
    const sheet = spreadsheet.getSheetByName(tabName);
    if (!sheet) {
      return response({ok: false, error: `A aba ${tabName} ainda não existe.`});
    }

    const lastRow = Math.max(sheet.getLastRow(), 3);
    const existing = sheet.getRange(3, 3, lastRow - 2, 1)
      .getDisplayValues().flat().map(normalize);
    const duplicates = records
      .filter(record => existing.includes(normalize(record.name)))
      .map(record => record.name);
    if (duplicates.length && !payload.allow_duplicates) {
      return response({ok: false, duplicates: duplicates});
    }

    const used = sheet.getRange(3, 1, sheet.getMaxRows() - 2, 7).getValues();
    let searchIndex = 0;
    records.forEach(record => {
      while (searchIndex < used.length && used[searchIndex].some(value => value !== '')) {
        searchIndex++;
      }
      if (searchIndex >= used.length) {
        throw new Error('Não há linhas vazias disponíveis na aba mensal.');
      }
      const row = searchIndex + 3;
      sheet.getRange(row, 1).setValue(Number(record.day));
      sheet.getRange(row, 2).setValue('Mariane');
      sheet.getRange(row, 3).setValue(String(record.name || ''));
      sheet.getRange(row, 6).setValue(Number(record.front));
      sheet.getRange(row, 7).setValue(Number(record.back));
      used[searchIndex][0] = record.day;
      searchIndex++;
    });
    SpreadsheetApp.flush();
    return response({ok: true, tab: tabName, count: records.length});
  } catch (error) {
    return response({ok: false, error: String(error.message || error)});
  } finally {
    try {
      lock.releaseLock();
    } catch (_) {}
  }
}

function normalize(value) {
  return String(value || '').trim().toLocaleLowerCase('pt-PT');
}

function response(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
