import frappe
from frappe import _

MISTRAL_CHAT_MODEL_DEFAULT = "mistral-small-latest"


def trigger_interview_summary(doc, _method=None):
    """doc_events handler: regenerate AI summary on the parent Interview."""
    if not doc.interview:
        return
    try:
        generate_interview_ai_summary(doc.interview)
    except Exception:
        frappe.log_error(
            title=_("Interview AI Summary: Generation Failed"),
            message=frappe.get_traceback(),
        )


def generate_interview_ai_summary(interview_name):
    """Fetch all non-cancelled feedbacks for an Interview and write an AI summary."""
    from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings

    settings = _get_phamos_settings()
    if not settings:
        return

    interview = frappe.get_doc("Interview", interview_name)

    applicant_name = ""
    if interview.job_applicant:
        applicant_name = (
            frappe.db.get_value("Job Applicant", interview.job_applicant, "applicant_name")
            or interview.job_applicant
        )

    job_title = ""
    if interview.job_opening:
        job_title = (
            frappe.db.get_value("Job Opening", interview.job_opening, "job_title")
            or interview.job_opening
        )

    feedbacks = frappe.get_all(
        "Interview Feedback",
        filters={"interview": interview_name, "docstatus": ["!=", 2]},
        fields=["name", "interviewer", "result", "average_rating", "feedback", "docstatus"],
        order_by="creation asc",
    )

    if not feedbacks:
        return

    for fb in feedbacks:
        fb["skills"] = frappe.get_all(
            "Skill Assessment",
            filters={"parent": fb.name, "parenttype": "Interview Feedback"},
            fields=["skill", "rating"],
            order_by="idx asc",
        )
        fb["interviewer_label"] = (
            frappe.db.get_value("User", fb.interviewer, "full_name") or fb.interviewer
            if fb.interviewer
            else "Unknown"
        )

    context_lines = [
        f"Candidate: {applicant_name or 'N/A'}",
        f"Position: {job_title or 'N/A'}",
        f"Interview Round: {interview.interview_round or 'N/A'}",
        f"Scheduled On: {interview.scheduled_on or 'N/A'}",
        f"Total Feedbacks: {len(feedbacks)}",
        "",
    ]

    for i, fb in enumerate(feedbacks, 1):
        status = "Submitted" if fb.docstatus == 1 else "Draft"
        context_lines += [
            f"--- Feedback #{i} ({status}) ---",
            f"Interviewer: {fb['interviewer_label']}",
            f"Result: {fb.result or 'Not specified'}",
            f"Average Rating: {float(fb.average_rating or 0):.2f} / 1.00",
        ]
        if fb["skills"]:
            context_lines.append("Skill Assessments:")
            for s in fb["skills"]:
                context_lines.append(f"  • {s.skill}: {float(s.rating or 0):.2f} / 1.00")
        if fb.feedback and fb.feedback.strip():
            context_lines.append(f"Interviewer Notes:\n{fb.feedback.strip()}")
        context_lines.append("")

    feedback_block = "\n".join(context_lines)

    prompt = f"""You are an HR analyst preparing an interview summary for management review.

Below are the interview feedbacks collected for a candidate.

{feedback_block}

Write a clear, structured summary (max 350 words) using exactly these four sections:

**Overall Recommendation** — Summarise the interviewers' collective assessment of the candidate (e.g. Hire / Hold / Reject) based purely on what the interviewers reported. Explain the reasoning briefly.

**Key Strengths** — 3–5 concrete positives observed and noted by interviewers, backed by the feedback data.

**Concerns & Gaps** — Factual account of any skill gaps, uncertainties, or concerns raised by interviewers.

**Interviewer Consensus** — Summarise where interviewers agree and where they differ. Highlight any conflicting opinions.

Rules: Do NOT include a "Suggested Next Steps" section or any action items. Management will decide next steps. Be factual and concise. Use markdown bold for section headers exactly as shown above. Use numbered lists for strengths and bullet points for concerns."""

    summary = _call_mistral_chat(settings, prompt)
    if not summary:
        return

    summary = frappe.utils.markdown(summary)

    frappe.db.set_value(
        "Interview",
        interview_name,
        "custom_interview_summary",
        summary,
        update_modified=False,
    )
    frappe.db.commit()


def _call_mistral_chat(settings, prompt):
    import requests

    model = settings["model"]
    if not model or "ocr" in model.lower():
        model = MISTRAL_CHAT_MODEL_DEFAULT

    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    if not resp.ok:
        raise Exception(f"Mistral API error ({resp.status_code}): {resp.text[:400]}")
    data = resp.json()
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
