(function () {
  "use strict";

  function fallbackCopy(text) {
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    return copied;
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    return fallbackCopy(text);
  }

  document.addEventListener("click", async function (event) {
    const button = event.target.closest("[data-copy-target]");
    if (!button) return;

    const target = document.getElementById(button.dataset.copyTarget);
    if (!target) return;

    const original = button.dataset.copyLabel || button.textContent.trim();
    try {
      const copied = await copyText(
        "value" in target ? target.value : target.innerText,
      );
      button.textContent = copied ? "Copied!" : "Copy unavailable";
    } catch (_error) {
      button.textContent = "Copy unavailable";
    }
    window.setTimeout(function () {
      button.textContent = original;
    }, 1600);
  });
})();
