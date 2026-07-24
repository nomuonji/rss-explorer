// Copy to `site/baserow.config.js` (which is gitignored) to enable LIVE feedback
// from the browser straight into Baserow. Without this file the site still works
// — it just falls back to localStorage + the "設定を書き出す" export.
//
// SECURITY: whatever token you put here is visible to anyone who loads the page.
// Use a Baserow token scoped to CREATE-ONLY on the feedback table — never your
// full-access token. Worst case if leaked: junk rows in that one table.
window.BASEROW = {
  apiUrl: "https://api.baserow.io",
  tableId: 0,                 // <- your feedback table id
  token: "CREATE_ONLY_TOKEN", // <- a create-only Baserow token, NOT the reader token
};
