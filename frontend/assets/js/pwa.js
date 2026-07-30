/* Registers the service worker and surfaces an "Install app" button
   when the browser offers installation. Safe to include on every page. */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const btn = document.createElement("button");
  btn.textContent = "⬇ Install app";
  btn.className = "btn btn-ghost btn-sm";
  btn.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:200;box-shadow:0 4px 12px rgba(15,23,42,.2)";
  btn.addEventListener("click", async () => {
    btn.remove();
    deferredPrompt.prompt();
    await deferredPrompt.userChoice.catch(() => {});
    deferredPrompt = null;
  });
  document.body.appendChild(btn);
});
