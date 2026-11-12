function publicServiceMessage(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
  element.classList.toggle("is-success", !isError);
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#contact-form");
  if (!form) return;
  const message = document.querySelector("#contact-status");
  const submit = form.querySelector("button[type='submit']");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    submit.disabled = true;
    publicServiceMessage(message, "Sending your message…");
    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = Array.isArray(result.detail)
          ? result.detail.map((issue) => issue.msg).join(" ")
          : result.detail || "Could not send your message.";
        publicServiceMessage(message, detail, true);
        return;
      }
      form.reset();
      publicServiceMessage(message, result.message);
    } catch {
      publicServiceMessage(message, "Could not connect to the portal. Please try again.", true);
    } finally {
      submit.disabled = false;
    }
  });
});
