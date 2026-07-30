/* Serviceflow runtime config — sets the backend API base URL.
 *
 * This is a plain (non-module) script loaded in the <head> BEFORE the app's
 * ES modules, so `window.SERVICEFLOW_API` is defined by the time api.js reads
 * it. Editing this file is the ONLY wiring step between the Netlify frontend
 * and the deployed backend — no rebuild required.
 *
 *   • Local dev:  leave this empty/absent → api.js falls back to
 *                 http://127.0.0.1:8000
 *   • Deployed:   set it to your Render service URL (shown on the Render
 *                 dashboard once the backend is live). It usually looks like
 *                 https://serviceflow-api.onrender.com — confirm the exact
 *                 host, since Render appends a suffix if the name is taken.
 */
window.SERVICEFLOW_API = "https://serviceflow-api-xezx.onrender.com";
