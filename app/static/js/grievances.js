const GRIEVANCE_TOKEN_KEY = "grievance_access_token";

function grievanceMessage(element, text, isError = false) {
  element.textContent = text;
  element.classList.toggle("is-error", isError);
  element.classList.toggle("is-success", !isError);
}

async function grievanceError(response) {
  const body = await response.json().catch(() => ({}));
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(" ");
  return body.detail || "Something went wrong. Please try again.";
}

function requireCitizenSession() {
  const token = sessionStorage.getItem(GRIEVANCE_TOKEN_KEY);
  if (!token) {
    window.location.replace("/login");
    return null;
  }
  return token;
}

function addDetail(parent, label, value) {
  const item = document.createElement("div");
  item.className = "grievance-detail";
  const heading = document.createElement("span");
  heading.textContent = label;
  const content = document.createElement("strong");
  content.textContent = value || "Not assigned";
  item.append(heading, content);
  parent.append(item);
}

function renderGrievanceCard(grievance) {
  const card = document.createElement("article");
  card.className = "grievance-card";
  const header = document.createElement("div");
  header.className = "grievance-card-header";
  const reference = document.createElement("strong");
  reference.textContent = grievance.reference_number;
  const status = document.createElement("span");
  status.className = "status-pill";
  status.textContent = grievance.status;
  header.append(reference, status);
  const subject = document.createElement("h3");
  subject.textContent = grievance.subject;
  const meta = document.createElement("p");
  meta.textContent = `${grievance.district} · ${grievance.category}`;
  const track = document.createElement("a");
  track.href = `/citizen/track?reference=${encodeURIComponent(grievance.reference_number)}`;
  track.textContent = "View status →";
  card.append(header, subject, meta, track);
  return card;
}

async function loadCitizenGrievances() {
  const list = document.querySelector("#grievance-list");
  if (!list) return;
  const token = requireCitizenSession();
  if (!token) return;
  const message = document.querySelector("#dashboard-message");

  try {
    const response = await fetch("/api/grievances", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.status === 401) {
      sessionStorage.removeItem(GRIEVANCE_TOKEN_KEY);
      window.location.replace("/login");
      return;
    }
    if (!response.ok) {
      grievanceMessage(message, await grievanceError(response), true);
      return;
    }
    const result = await response.json();
    document.querySelector("#total-count").textContent = result.total;
    document.querySelector("#pending-count").textContent = result.pending;
    document.querySelector("#resolved-count").textContent = result.resolved;
    list.replaceChildren();
    if (result.grievances.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "You haven’t submitted any grievances yet.";
      list.append(empty);
      return;
    }
    for (const grievance of result.grievances) list.append(renderGrievanceCard(grievance));
  } catch {
    grievanceMessage(message, "Could not connect to the portal. Check that the server is running.", true);
  }
}

async function setupGrievanceForm() {
  const form = document.querySelector("#grievance-form");
  if (!form) return;
  const token = requireCitizenSession();
  if (!token) return;
  const message = document.querySelector("#grievance-message");
  const districtSelect = document.querySelector("#district");
  const categorySelect = document.querySelector("#category");
  const analysisButton = document.querySelector("#analyze-grievance");
  const aiAvailability = document.querySelector("#ai-availability");
  const consentRow = document.querySelector("#ai-consent-row");
  const consentInput = document.querySelector("#ai-consent");
  const aiSuggestion = document.querySelector("#ai-suggestion");
  const suggestionId = document.querySelector("#ai-suggestion-id");

  try {
    const [optionsResponse, aiStatusResponse] = await Promise.all([
      fetch("/api/grievances/options"),
      fetch("/api/ai/status", { headers: { Authorization: `Bearer ${token}` } }),
    ]);
    if (!optionsResponse.ok) {
      grievanceMessage(message, await grievanceError(optionsResponse), true);
      return;
    }
    if (aiStatusResponse.status === 401) {
      sessionStorage.removeItem(GRIEVANCE_TOKEN_KEY);
      window.location.replace("/login");
      return;
    }
    if (!aiStatusResponse.ok) {
      grievanceMessage(message, await grievanceError(aiStatusResponse), true);
      return;
    }
    const [options, aiStatus] = await Promise.all([
      optionsResponse.json(),
      aiStatusResponse.json(),
    ]);
    for (const district of options.districts) districtSelect.add(new Option(district, district));
    for (const category of options.categories) categorySelect.add(new Option(category, category));
    if (aiStatus.provider_configured) {
      aiAvailability.textContent = `${aiStatus.external_data_notice} Suggestions are advisory and require your review.`;
      consentRow.hidden = false;
    } else {
      aiAvailability.textContent = aiStatus.fallback_notice;
    }
    analysisButton.disabled = false;
  } catch {
    aiAvailability.textContent = "Could not check AI provider configuration.";
    grievanceMessage(message, "Could not load form options. Check that the server is running.", true);
    return;
  }

  const clearSuggestion = () => {
    suggestionId.value = "";
    aiSuggestion.hidden = true;
  };
  for (const field of [form.elements.subject, form.elements.description]) {
    field.addEventListener("input", clearSuggestion);
  }
  document.querySelector("#apply-ai-category").addEventListener("click", () => {
    const suggestedCategory = aiSuggestion.dataset.category;
    if (suggestedCategory) categorySelect.value = suggestedCategory;
  });

  analysisButton.addEventListener("click", async () => {
    const subject = form.elements.subject.value.trim();
    const description = form.elements.description.value.trim();
    if (subject.length < 5 || description.length < 20) {
      grievanceMessage(message, "Enter a subject and at least 20 characters of description first.", true);
      return;
    }
    if (consentRow.hidden === false && !consentInput.checked) {
      grievanceMessage(message, "Please provide consent before using the configured external AI provider.", true);
      consentInput.focus();
      return;
    }
    analysisButton.disabled = true;
    clearSuggestion();
    grievanceMessage(message, "Analyzing complaint text…");
    try {
      const response = await fetch("/api/ai/analyze", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          subject,
          description,
          consent_to_external_ai: consentInput.checked,
        }),
      });
      if (response.status === 401) {
        sessionStorage.removeItem(GRIEVANCE_TOKEN_KEY);
        window.location.replace("/login");
        return;
      }
      if (!response.ok) {
        grievanceMessage(message, await grievanceError(response), true);
        return;
      }
      const suggestion = await response.json();
      suggestionId.value = suggestion.suggestion_id;
      aiSuggestion.dataset.category = suggestion.category;
      const details = document.querySelector("#ai-suggestion-details");
      details.replaceChildren();
      for (const [label, value] of [
        ["Department", suggestion.suggested_department],
        ["Category", suggestion.category],
        ["Priority", suggestion.priority],
        ["CMO summary", suggestion.summary],
        [
          "Possible duplicate",
          suggestion.duplicate_possible
            ? "A similar open complaint may exist; please review."
            : "No likely duplicate detected.",
        ],
      ]) {
        const row = document.createElement("div");
        row.className = "ai-suggestion-item";
        const name = document.createElement("span");
        name.textContent = label;
        const content = document.createElement("strong");
        content.textContent = value;
        row.append(name, content);
        details.append(row);
      }
      document.querySelector("#ai-source-label").textContent =
        suggestion.source === "llm_api"
          ? `AI model: ${suggestion.model}`
          : "Rule-based fallback";
      document.querySelector("#ai-suggestion-notice").textContent = suggestion.notice;
      aiSuggestion.hidden = false;
      grievanceMessage(message, "Review the suggestions below; they do not make an official decision.");
    } catch {
      grievanceMessage(message, "Could not connect to the assistant. Please try again.", true);
    } finally {
      analysisButton.disabled = false;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    grievanceMessage(message, "Submitting your grievance…");
    try {
      const response = await fetch("/api/grievances", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: new FormData(form),
      });
      if (response.status === 401) {
        sessionStorage.removeItem(GRIEVANCE_TOKEN_KEY);
        window.location.replace("/login");
        return;
      }
      if (!response.ok) {
        grievanceMessage(message, await grievanceError(response), true);
        return;
      }
      const result = await response.json();
      document.querySelector("#submission-reference").textContent = result.reference_number;
      document.querySelector("#submission-track-link").href =
        `/citizen/track?reference=${encodeURIComponent(result.reference_number)}`;
      document.querySelector("#submission-result").hidden = false;
      form.reset();
      clearSuggestion();
      grievanceMessage(message, "Your grievance has been recorded.");
    } catch {
      grievanceMessage(message, "Could not connect to the portal. Check that the server is running.", true);
    } finally {
      submit.disabled = false;
    }
  });
}

function renderTrackResult(grievance) {
  const section = document.querySelector("#track-result");
  section.replaceChildren();
  const heading = document.createElement("h2");
  heading.textContent = grievance.subject;
  section.append(heading);
  const details = document.createElement("div");
  details.className = "grievance-details-grid";
  addDetail(details, "Reference", grievance.reference_number);
  addDetail(details, "Status", grievance.status);
  addDetail(details, "District", grievance.district);
  addDetail(details, "Category", grievance.category);
  addDetail(details, "Department", grievance.department);
  addDetail(details, "Submitted", new Date(`${grievance.created_at}Z`).toLocaleString());
  section.append(details);
  const description = document.createElement("p");
  description.className = "track-description";
  description.textContent = grievance.description;
  section.append(description);
  if (grievance.resolution_details) {
    const resolutionHeading = document.createElement("h3");
    resolutionHeading.textContent = "Resolution details";
    const resolution = document.createElement("p");
    resolution.className = "track-description";
    resolution.textContent = grievance.resolution_details;
    section.append(resolutionHeading, resolution);
  }
  if (grievance.ai_suggestion) {
    const suggestionHeading = document.createElement("h3");
    suggestionHeading.textContent = "AI assistant suggestion";
    const suggestion = document.createElement("div");
    suggestion.className = "ai-suggestion ai-tracking";
    suggestion.append(suggestionHeading);
    for (const [label, value] of [
      ["Suggested department", grievance.ai_suggestion.suggested_department],
      ["Suggested category", grievance.ai_suggestion.category],
      ["Suggested priority", grievance.ai_suggestion.priority],
      ["CMO summary", grievance.ai_suggestion.summary],
      ["Possible duplicate", grievance.ai_suggestion.duplicate_possible ? "Flagged for human review" : "Not flagged"],
      ["Analysis", grievance.ai_suggestion.source === "llm_api" ? `AI model: ${grievance.ai_suggestion.model}` : "Rule-based fallback (not AI integration)"],
    ]) {
      const line = document.createElement("p");
      const labelElement = document.createElement("strong");
      labelElement.textContent = `${label}: `;
      const valueElement = document.createElement("span");
      valueElement.textContent = value;
      line.append(labelElement, valueElement);
      suggestion.append(line);
    }
    const disclaimer = document.createElement("p");
    disclaimer.className = "field-hint";
    disclaimer.textContent = "Advisory only. This suggestion did not assign a department or determine the grievance outcome.";
    suggestion.append(disclaimer);
    section.append(suggestionHeading, suggestion);
  }

  const historyHeading = document.createElement("h3");
  historyHeading.textContent = "Status history";
  section.append(historyHeading);
  const history = document.createElement("ol");
  history.className = "history-list";
  for (const entry of grievance.history) {
    const item = document.createElement("li");
    const status = document.createElement("strong");
    status.textContent = entry.new_status;
    const remark = document.createElement("span");
    remark.textContent = entry.remark || "";
    const timestamp = document.createElement("small");
    timestamp.textContent = `${new Date(`${entry.created_at}Z`).toLocaleString()} · ${entry.changed_by}`;
    item.append(status, remark, timestamp);
    history.append(item);
  }
  section.append(history);

  if (grievance.status === "Resolved" && !grievance.feedback_submitted) {
    const feedbackForm = document.createElement("form");
    feedbackForm.className = "feedback-form";
    const feedbackHeading = document.createElement("h3");
    feedbackHeading.textContent = "Share your feedback";
    const ratingLabel = document.createElement("label");
    ratingLabel.textContent = "Rating";
    ratingLabel.htmlFor = "feedback-rating";
    const rating = document.createElement("select");
    rating.id = "feedback-rating";
    rating.required = true;
    for (let score = 5; score >= 1; score -= 1) {
      rating.add(new Option(`${score} - ${["", "Poor", "Fair", "Good", "Very good", "Excellent"][score]}`, String(score)));
    }
    const commentLabel = document.createElement("label");
    commentLabel.textContent = "Comment (optional)";
    commentLabel.htmlFor = "feedback-comment";
    const comment = document.createElement("textarea");
    comment.id = "feedback-comment";
    comment.maxLength = 2000;
    comment.rows = 3;
    const feedbackMessage = document.createElement("p");
    feedbackMessage.className = "dashboard-message";
    feedbackMessage.setAttribute("role", "status");
    const submitFeedback = document.createElement("button");
    submitFeedback.type = "submit";
    submitFeedback.className = "button button-primary";
    submitFeedback.textContent = "Submit feedback";
    feedbackForm.append(feedbackHeading, ratingLabel, rating, commentLabel, comment, feedbackMessage, submitFeedback);
    feedbackForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      submitFeedback.disabled = true;
      try {
        const response = await fetch(
          `/api/grievances/${encodeURIComponent(grievance.reference_number)}/feedback`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${sessionStorage.getItem(GRIEVANCE_TOKEN_KEY)}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ rating: Number(rating.value), comment: comment.value }),
          },
        );
        if (!response.ok) {
          grievanceMessage(feedbackMessage, await grievanceError(response), true);
          return;
        }
        feedbackForm.replaceChildren(document.createTextNode("Thank you for sharing your feedback."));
      } catch {
        grievanceMessage(feedbackMessage, "Could not connect to the portal. Please try again.", true);
      } finally {
        submitFeedback.disabled = false;
      }
    });
    section.append(feedbackForm);
  }

  if (grievance.attachments.length > 0) {
    const attachmentHeading = document.createElement("h3");
    attachmentHeading.textContent = "Attachments";
    section.append(attachmentHeading);
    for (const attachment of grievance.attachments) {
      const link = document.createElement("a");
      link.href = `/api/grievances/${encodeURIComponent(grievance.reference_number)}/attachments/${attachment.id}`;
      link.textContent = attachment.original_filename;
      link.dataset.attachmentId = attachment.id;
      link.className = "attachment-link";
      link.addEventListener("click", async (event) => {
        event.preventDefault();
        const token = sessionStorage.getItem(GRIEVANCE_TOKEN_KEY);
        try {
          const response = await fetch(link.href, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!response.ok) {
            grievanceMessage(
              document.querySelector("#track-message"),
              await grievanceError(response),
              true,
            );
            return;
          }
          const objectUrl = URL.createObjectURL(await response.blob());
          const download = document.createElement("a");
          download.href = objectUrl;
          download.download = link.textContent;
          download.click();
          window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        } catch {
          grievanceMessage(
            document.querySelector("#track-message"),
            "Could not download the attachment. Check your connection and try again.",
            true,
          );
        }
      });
      section.append(link);
    }
  }
  section.hidden = false;
}

async function setupTrackForm() {
  const form = document.querySelector("#track-form");
  if (!form) return;
  const token = requireCitizenSession();
  if (!token) return;
  const input = document.querySelector("#reference-number");
  const message = document.querySelector("#track-message");
  const queryReference = new URLSearchParams(window.location.search).get("reference");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const reference = input.value.trim().toUpperCase();
    const section = document.querySelector("#track-result");
    section.hidden = true;
    grievanceMessage(message, "Looking up your grievance…");
    try {
      const response = await fetch(`/api/grievances/${encodeURIComponent(reference)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 401) {
        sessionStorage.removeItem(GRIEVANCE_TOKEN_KEY);
        window.location.replace("/login");
        return;
      }
      if (!response.ok) {
        grievanceMessage(message, await grievanceError(response), true);
        return;
      }
      renderTrackResult(await response.json());
      grievanceMessage(message, "Grievance found.");
    } catch {
      grievanceMessage(message, "Could not connect to the portal. Check that the server is running.", true);
    }
  });
  if (queryReference) {
    input.value = queryReference;
    form.requestSubmit();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadCitizenGrievances();
  setupGrievanceForm();
  setupTrackForm();
});
