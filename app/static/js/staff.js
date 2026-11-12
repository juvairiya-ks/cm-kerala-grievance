const STAFF_TOKEN_KEY = "grievance_access_token";
let activeAdminGrievanceId = null;
let activeOfficerGrievanceId = null;
let departmentOptions = [];

function staffMessage(text, isError = false) {
  const element = document.querySelector("#staff-message");
  if (!element) return;
  element.textContent = text;
  element.classList.toggle("is-error", isError);
  element.classList.toggle("is-success", !isError);
}

async function staffError(response) {
  const body = await response.json().catch(() => ({}));
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(" ");
  return body.detail || "Something went wrong. Please try again.";
}

async function staffFetch(url, options = {}) {
  const token = sessionStorage.getItem(STAFF_TOKEN_KEY);
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem(STAFF_TOKEN_KEY);
    window.location.replace("/login");
    throw new Error("Your session expired. Please sign in again.");
  }
  if (response.status === 403) {
    window.location.replace("/citizen/dashboard");
    throw new Error("This account does not have permission to access this workspace.");
  }
  return response;
}

function appendDetail(container, label, value) {
  const cell = document.createElement("div");
  cell.className = "grievance-detail";
  const heading = document.createElement("span");
  heading.textContent = label;
  const content = document.createElement("strong");
  content.textContent = value || "Not assigned";
  cell.append(heading, content);
  container.append(cell);
}

function renderHistory(target, entries) {
  target.replaceChildren();
  for (const entry of entries) {
    const item = document.createElement("li");
    const state = document.createElement("strong");
    state.textContent = entry.new_status;
    const remark = document.createElement("span");
    remark.textContent = entry.remark || "";
    const time = document.createElement("small");
    time.textContent = `${new Date(`${entry.created_at}Z`).toLocaleString()} · ${entry.changed_by}`;
    item.append(state, remark, time);
    target.append(item);
  }
}

async function downloadStaffAttachment(url, filename) {
  const response = await staffFetch(url);
  if (!response.ok) {
    staffMessage(await staffError(response), true);
    return;
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function renderAttachments(container, attachments, grievanceId, reference, accessRole) {
  container.replaceChildren();
  if (!attachments.length) {
    container.textContent = "No attachments.";
    return;
  }
  for (const attachment of attachments) {
    const link = document.createElement("button");
    link.type = "button";
    link.className = "attachment-button";
    link.textContent = attachment.original_filename;
    link.addEventListener("click", () => {
      const path = accessRole === "admin"
        ? `/api/admin/grievances/${grievanceId}/attachments/${attachment.id}`
        : accessRole === "officer"
          ? `/api/officer/grievances/${grievanceId}/attachments/${attachment.id}`
          : `/api/grievances/${encodeURIComponent(reference)}/attachments/${attachment.id}`;
      downloadStaffAttachment(path, attachment.original_filename).catch(() => {
        staffMessage("Could not download the attachment. Please try again.", true);
      });
    });
    container.append(link);
  }
}

function renderAdminRows(rows) {
  const body = document.querySelector("#admin-grievances");
  body.replaceChildren();
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No grievances match these filters.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const grievance of rows) {
    const row = document.createElement("tr");
    const summary = document.createElement("td");
    const reference = document.createElement("strong");
    reference.textContent = grievance.reference_number;
    const subject = document.createElement("span");
    subject.className = "table-subtitle";
    subject.textContent = grievance.subject;
    summary.append(reference, subject);
    const district = document.createElement("td");
    district.textContent = grievance.district;
    const priority = document.createElement("td");
    priority.textContent = grievance.priority;
    const state = document.createElement("td");
    state.textContent = grievance.status;
    const department = document.createElement("td");
    department.textContent = grievance.department_name || "Not assigned";
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-outline table-action";
    button.textContent = "Review";
    button.addEventListener("click", () => loadAdminDetail(grievance.id));
    action.append(button);
    row.append(summary, district, priority, state, department, action);
    body.append(row);
  }
}

async function loadAdminGrievances() {
  const form = document.querySelector("#admin-filters");
  const params = new URLSearchParams(new FormData(form));
  for (const [key, value] of [...params.entries()]) {
    if (!value) params.delete(key);
  }
  const response = await staffFetch(`/api/admin/grievances?${params}`);
  if (!response.ok) throw new Error(await staffError(response));
  renderAdminRows(await response.json());
}

function renderCompactStats(target, rows, label) {
  target.replaceChildren();
  if (!rows.length) {
    target.textContent = "No data yet.";
    return;
  }
  for (const entry of rows) {
    const line = document.createElement("div");
    const name = document.createElement("span");
    name.textContent = entry[label];
    const count = document.createElement("strong");
    count.textContent = entry.total;
    line.append(name, count);
    target.append(line);
  }
}

async function loadAdminStats() {
  const response = await staffFetch("/api/admin/stats");
  if (!response.ok) throw new Error(await staffError(response));
  const stats = await response.json();
  document.querySelector("#admin-total").textContent = stats.total;
  document.querySelector("#admin-pending").textContent = stats.pending;
  document.querySelector("#admin-resolved").textContent = stats.resolved;
  document.querySelector("#admin-overdue").textContent = stats.overdue;
  renderCompactStats(document.querySelector("#district-stats"), stats.by_district, "district");
  renderCompactStats(document.querySelector("#department-stats"), stats.by_department, "department");
}

async function loadDepartments() {
  const response = await staffFetch("/api/admin/departments");
  if (!response.ok) throw new Error(await staffError(response));
  departmentOptions = await response.json();
  const departmentFilter = document.querySelector("#filter-district");
  const categoryFilter = document.querySelector("#filter-category");
  const form = document.querySelector("#admin-filters");
  const optionsResponse = await fetch("/api/grievances/options");
  if (!optionsResponse.ok) throw new Error(await staffError(optionsResponse));
  const options = await optionsResponse.json();
  for (const district of options.districts) departmentFilter.add(new Option(district, district));
  for (const category of options.categories) categoryFilter.add(new Option(category, category));

  const assignDepartment = document.querySelector("#assign-department");
  for (const department of departmentOptions) {
    assignDepartment.add(new Option(department.name, department.id));
  }
  assignDepartment.addEventListener("change", updateOfficerOptions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await loadAdminGrievances();
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  form.addEventListener("reset", () => window.setTimeout(() => loadAdminGrievances(), 0));
}

function updateOfficerOptions() {
  const departmentId = Number(document.querySelector("#assign-department").value);
  const select = document.querySelector("#assign-officer");
  select.replaceChildren(new Option("Any officer in department", ""));
  const department = departmentOptions.find((item) => item.id === departmentId);
  for (const officer of department?.officers || []) {
    select.add(new Option(officer.name, officer.id));
  }
}

async function loadAdminDetail(grievanceId) {
  activeAdminGrievanceId = grievanceId;
  try {
    const response = await staffFetch(`/api/admin/grievances/${grievanceId}`);
    if (!response.ok) throw new Error(await staffError(response));
    const grievance = await response.json();
    document.querySelector("#detail-subject").textContent = grievance.subject;
    document.querySelector("#detail-summary").replaceChildren();
    document.querySelector("#start-review").hidden = grievance.status !== "Submitted";
    const assignmentButton = document.querySelector("#assign-form button[type='submit']");
    const assignmentHint = document.querySelector("#assignment-hint");
    assignmentButton.disabled = grievance.status === "Submitted" || grievance.status === "Resolved";
    assignmentHint.textContent = grievance.status === "Submitted"
      ? "Start CMO review before forwarding this grievance."
      : grievance.status === "Resolved"
        ? "Reopen this grievance before assigning it again."
        : "";
    for (const [label, value] of [
      ["Reference", grievance.reference_number],
      ["Citizen", `${grievance.citizen_name} · ${grievance.citizen_email}`],
      ["District", grievance.district],
      ["Category", grievance.category],
      ["Priority", grievance.priority],
      ["Status", grievance.status],
      ["Department", grievance.department_name],
      ["Assigned officer", grievance.officer_name],
    ]) appendDetail(document.querySelector("#detail-summary"), label, value);
    document.querySelector("#detail-description").textContent = grievance.description;
    renderAdminAISuggestion(grievance.ai_suggestion);
    document.querySelector("#reopen-grievance").hidden = grievance.status !== "Resolved";
    renderHistory(document.querySelector("#admin-history"), grievance.history);

    const remarks = document.querySelector("#admin-remarks");
    remarks.replaceChildren();
    for (const entry of grievance.internal_remarks) {
      const item = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = entry.remark;
      const meta = document.createElement("small");
      meta.textContent = `${entry.author} · ${new Date(`${entry.created_at}Z`).toLocaleString()}`;
      item.append(text, meta);
      remarks.append(item);
    }
    renderAttachments(
      document.querySelector("#admin-attachments"),
      grievance.attachments,
      grievance.id,
      grievance.reference_number,
      "admin",
    );
    renderReports(grievance.reports);
    const escalations = document.querySelector("#admin-escalations");
    escalations.replaceChildren();
    for (const escalation of grievance.escalations) {
      const item = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = escalation.reason;
      const meta = document.createElement("small");
      meta.textContent = `${escalation.escalated_by} · ${new Date(`${escalation.created_at}Z`).toLocaleString()}`;
      item.append(text, meta);
      escalations.append(item);
    }
    const assigned = departmentOptions.find((item) => item.name === grievance.department_name);
    if (assigned) document.querySelector("#assign-department").value = assigned.id;
    updateOfficerOptions();
    const currentOfficer = assigned?.officers.find((item) => item.name === grievance.officer_name);
    document.querySelector("#assign-officer").value = currentOfficer?.id || "";
    document.querySelector("#admin-detail").hidden = false;
    document.querySelector("#admin-detail").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    staffMessage(error.message, true);
  }
}

function renderAdminAISuggestion(suggestion) {
  const container = document.querySelector("#admin-ai-suggestion");
  container.replaceChildren();
  container.hidden = !suggestion;
  if (!suggestion) return;
  const heading = document.createElement("strong");
  heading.textContent = "Citizen-reviewed AI assistant suggestion";
  container.append(heading);
  for (const [label, value] of [
    ["Suggested department", suggestion.suggested_department],
    ["Suggested category", suggestion.category],
    ["Suggested priority", suggestion.priority],
    ["CMO summary", suggestion.summary],
    ["Possible duplicate", suggestion.duplicate_possible ? "Flagged for human review" : "Not flagged"],
    ["Source", suggestion.source === "llm_api" ? `AI model: ${suggestion.model}` : "Rule-based fallback (not AI integration)"],
  ]) {
    const line = document.createElement("p");
    const name = document.createElement("span");
    name.textContent = `${label}: `;
    const content = document.createElement("strong");
    content.textContent = value;
    line.append(name, content);
    container.append(line);
  }
  const disclaimer = document.createElement("p");
  disclaimer.className = "field-hint";
  disclaimer.textContent = "Advisory only. Review independently; it does not assign or resolve the grievance.";
  container.append(disclaimer);
}

function renderReports(reports) {
  const container = document.querySelector("#admin-reports");
  container.replaceChildren();
  if (!reports.length) {
    container.textContent = "No department action reports submitted.";
    return;
  }
  for (const report of reports) {
    const card = document.createElement("article");
    card.className = "report-card";
    const heading = document.createElement("strong");
    heading.textContent = `${report.officer_name} · ${report.review_status}`;
    const action = document.createElement("p");
    action.textContent = `Actions taken: ${report.action_report}`;
    const resolution = document.createElement("p");
    resolution.textContent = `Proposed resolution: ${report.resolution_details}`;
    card.append(heading, action, resolution);
    if (report.review_remark) {
      const reviewRemark = document.createElement("p");
      reviewRemark.textContent = `Review note: ${report.review_remark}`;
      card.append(reviewRemark);
    }
    if (report.review_status === "Pending Review") {
      const actions = document.createElement("div");
      actions.className = "report-actions";
      for (const [decision, label] of [["accept", "Accept & resolve"], ["return", "Return for more work"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = decision === "accept" ? "button button-primary" : "button button-outline";
        button.textContent = label;
        button.addEventListener("click", () => reviewReport(report.id, decision));
        actions.append(button);
      }
      card.append(actions);
    }
    container.append(card);
  }
}

async function reviewReport(reportId, decision) {
  const remark = window.prompt(decision === "accept" ? "Add a review note:" : "Explain what further action is required:");
  if (remark === null || !remark.trim()) return;
  try {
    const response = await staffFetch(`/api/admin/reports/${reportId}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, remark }),
    });
    if (!response.ok) throw new Error(await staffError(response));
    staffMessage((await response.json()).message);
    await Promise.all([loadAdminStats(), loadAdminGrievances(), loadAdminDetail(activeAdminGrievanceId)]);
  } catch (error) {
    staffMessage(error.message, true);
  }
}

function setupAdminForms() {
  document.querySelector("#start-review").addEventListener("click", async () => {
    const remark = window.prompt("Add an optional CMO review note:", "Grievance review started");
    if (remark === null) return;
    try {
      const response = await staffFetch(`/api/admin/grievances/${activeAdminGrievanceId}/review`, {
        method: "POST",
        body: JSON.stringify({ remark: remark.trim() || "Grievance review started" }),
      });
      if (!response.ok) throw new Error(await staffError(response));
      staffMessage((await response.json()).message);
      await Promise.all([loadAdminStats(), loadAdminGrievances(), loadAdminDetail(activeAdminGrievanceId)]);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  document.querySelector("#assign-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    payload.department_id = Number(payload.department_id);
    payload.officer_id = payload.officer_id ? Number(payload.officer_id) : null;
    try {
      const response = await staffFetch(`/api/admin/grievances/${activeAdminGrievanceId}/assign`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await staffError(response));
      staffMessage((await response.json()).message);
      await Promise.all([loadAdminStats(), loadAdminGrievances(), loadAdminDetail(activeAdminGrievanceId)]);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  document.querySelector("#remark-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const remark = new FormData(form).get("remark");
    try {
      const response = await staffFetch(`/api/admin/grievances/${activeAdminGrievanceId}/remarks`, {
        method: "POST",
        body: JSON.stringify({ remark }),
      });
      if (!response.ok) throw new Error(await staffError(response));
      form.reset();
      staffMessage((await response.json()).message);
      await loadAdminDetail(activeAdminGrievanceId);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  document.querySelector("#close-detail").addEventListener("click", () => {
    document.querySelector("#admin-detail").hidden = true;
    activeAdminGrievanceId = null;
  });
  document.querySelector("#reopen-grievance").addEventListener("click", async () => {
    const remark = window.prompt("Why is this resolved grievance being reopened?");
    if (remark === null || !remark.trim()) return;
    try {
      const response = await staffFetch(`/api/admin/grievances/${activeAdminGrievanceId}/reopen`, {
        method: "POST",
        body: JSON.stringify({ remark }),
      });
      if (!response.ok) throw new Error(await staffError(response));
      staffMessage((await response.json()).message);
      await Promise.all([loadAdminStats(), loadAdminGrievances(), loadAdminDetail(activeAdminGrievanceId)]);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  document.querySelector("#escalate-grievance").addEventListener("click", async () => {
    const reason = window.prompt("Why should this delayed grievance be escalated?");
    if (reason === null || !reason.trim()) return;
    try {
      const response = await staffFetch(`/api/admin/grievances/${activeAdminGrievanceId}/escalate`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      if (!response.ok) throw new Error(await staffError(response));
      staffMessage((await response.json()).message);
      await loadAdminDetail(activeAdminGrievanceId);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
}

async function setupAdminDashboard() {
  const response = await staffFetch("/api/auth/me");
  if (!response.ok) throw new Error(await staffError(response));
  const user = await response.json();
  if (user.role !== "admin") {
    window.location.replace(user.role === "officer" ? "/officer/dashboard" : "/citizen/dashboard");
    return;
  }
  document.querySelector("#staff-user").textContent = user.name;
  setupAdminForms();
  await loadDepartments();
  await Promise.all([loadAdminStats(), loadAdminGrievances()]);
}

function renderOfficerRows(rows) {
  const body = document.querySelector("#officer-grievances");
  body.replaceChildren();
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No grievances are assigned to your department yet.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const grievance of rows) {
    const row = document.createElement("tr");
    const summary = document.createElement("td");
    const reference = document.createElement("strong");
    reference.textContent = grievance.reference_number;
    const subject = document.createElement("span");
    subject.className = "table-subtitle";
    subject.textContent = grievance.subject;
    summary.append(reference, subject);
    const citizen = document.createElement("td");
    citizen.textContent = grievance.citizen_name;
    const district = document.createElement("td");
    district.textContent = grievance.district;
    const priority = document.createElement("td");
    priority.textContent = grievance.priority;
    const state = document.createElement("td");
    state.textContent = grievance.status;
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-outline table-action";
    button.textContent = "Open";
    button.addEventListener("click", () => loadOfficerDetail(grievance.id));
    action.append(button);
    row.append(summary, citizen, district, priority, state, action);
    body.append(row);
  }
}

async function loadOfficerGrievances() {
  const response = await staffFetch("/api/officer/grievances");
  if (!response.ok) throw new Error(await staffError(response));
  renderOfficerRows(await response.json());
}

async function loadOfficerDetail(grievanceId) {
  activeOfficerGrievanceId = grievanceId;
  try {
    const response = await staffFetch(`/api/officer/grievances/${grievanceId}`);
    if (!response.ok) throw new Error(await staffError(response));
    const grievance = await response.json();
    document.querySelector("#officer-subject").textContent = grievance.subject;
    const summary = document.querySelector("#officer-summary");
    summary.replaceChildren();
    for (const [label, value] of [
      ["Reference", grievance.reference_number],
      ["Citizen", grievance.citizen_name],
      ["District", grievance.district],
      ["Category", grievance.category],
      ["Priority", grievance.priority],
      ["Status", grievance.status],
    ]) appendDetail(summary, label, value);
    document.querySelector("#officer-description").textContent = grievance.description;
    renderHistory(document.querySelector("#officer-history"), grievance.history);
    renderAttachments(
      document.querySelector("#officer-attachments"),
      grievance.attachments,
      grievance.id,
      grievance.reference_number,
      "officer",
    );
    document.querySelector("#officer-detail").hidden = false;
    document.querySelector("#officer-detail").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    staffMessage(error.message, true);
  }
}

function setupOfficerForms() {
  document.querySelector("#officer-update-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const remark = new FormData(form).get("remark");
    try {
      const response = await staffFetch(`/api/officer/grievances/${activeOfficerGrievanceId}/update`, {
        method: "POST",
        body: JSON.stringify({ remark }),
      });
      if (!response.ok) throw new Error(await staffError(response));
      form.reset();
      staffMessage((await response.json()).message);
      await Promise.all([loadOfficerGrievances(), loadOfficerDetail(activeOfficerGrievanceId)]);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  document.querySelector("#action-report-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    try {
      const response = await staffFetch(`/api/officer/grievances/${activeOfficerGrievanceId}/reports`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await staffError(response));
      form.reset();
      staffMessage((await response.json()).message);
      await Promise.all([loadOfficerGrievances(), loadOfficerDetail(activeOfficerGrievanceId)]);
    } catch (error) {
      staffMessage(error.message, true);
    }
  });
  document.querySelector("#officer-close-detail").addEventListener("click", () => {
    document.querySelector("#officer-detail").hidden = true;
    activeOfficerGrievanceId = null;
  });
}

async function setupOfficerDashboard() {
  const response = await staffFetch("/api/auth/me");
  if (!response.ok) throw new Error(await staffError(response));
  const user = await response.json();
  if (user.role !== "officer") {
    window.location.replace(user.role === "admin" ? "/admin/dashboard" : "/citizen/dashboard");
    return;
  }
  document.querySelector("#staff-user").textContent = user.name;
  setupOfficerForms();
  await loadOfficerGrievances();
}

document.addEventListener("DOMContentLoaded", async () => {
  const page = document.body.dataset.staffPage;
  if (!page) return;
  const token = sessionStorage.getItem(STAFF_TOKEN_KEY);
  if (!token) {
    window.location.replace("/login");
    return;
  }
  document.querySelector("[data-logout]").addEventListener("click", async () => {
    try {
      await staffFetch("/api/auth/logout", { method: "POST" });
    } catch {
      return;
    }
    sessionStorage.removeItem(STAFF_TOKEN_KEY);
    window.location.assign("/");
  });
  try {
    if (page === "admin") await setupAdminDashboard();
    if (page === "officer") await setupOfficerDashboard();
  } catch (error) {
    staffMessage(error.message, true);
  }
});
