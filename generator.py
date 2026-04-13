"""Generates job descriptions using Claude AI."""
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are an expert HR professional and technical writer who crafts compelling, professional job descriptions.

Structure every job description with exactly these sections (use the label followed by a colon as the header):

Job Overview:
Key Responsibilities:
Required Qualifications:
Preferred Qualifications:
What We Offer:

Rules:
- Job Overview: 2-3 sentences summarizing the role and its impact. If company website content is provided, weave in the company's mission, values, or culture naturally.
- Key Responsibilities: 6-8 bullet points starting with action verbs
- Required Qualifications: 5-6 bullet points (skills, experience, education)
- Preferred Qualifications: 3-4 bullet points (nice-to-haves)
- What We Offer: 4-5 bullet points — if company website content is provided, reflect the company's actual culture, benefits, or values rather than using generic language
- Use bullet points starting with "- " for all list items
- Be specific, concrete, and avoid corporate jargon
- Match tone and seniority to the experience level provided
- Do NOT repeat the job title as the first line"""


def generate_job_description(
    company_name: str,
    job_title: str,
    skills: str,
    experience_level: str,
    company_context: str = "",
) -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip())

    user_content = (
        f"Company: {company_name}\n"
        f"Job Title: {job_title}\n"
        f"Required Skills: {skills}\n"
        f"Experience / Education Level: {experience_level}"
    )
    if company_context:
        user_content += f"\n\nCompany Website Content (use to personalize the JD):\n{company_context}"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    return message.content[0].text.strip()
