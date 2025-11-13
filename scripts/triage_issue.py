#!/usr/bin/env python3
"""
Triage Issue Script - GitHub Actions version
Adapted from repogent-issue-manager for GitHub Actions
"""
import os
import sys
import json
from groq import Groq

# Import shared constants
from config_constants import MODEL_ISSUE_TRIAGE

# Constants
HTTP_TIMEOUT_SECONDS = 30  # HTTP request timeout

def load_config():
    """Load label configuration"""
    try:
        with open('config/labels.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"labels": ["Bug", "Enhancement", "Question"], "default_label": "Question"}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ Error loading config: {e}, using defaults", file=sys.stderr)
        return {"labels": ["Bug", "Enhancement", "Question"], "default_label": "Question"}

def classify_issue(client, title, body, allowed_labels, default_label='Question'):
    """Use Groq LLM to classify the issue"""
    labels_list = ", ".join(allowed_labels)
    
    system_prompt = f"""You are 'Repogent - Issue Manager Agent', an AI-powered GitHub issue triager using Groq's ultra-fast LLM inference.

Your task is to classify GitHub issues into ONE of these categories: {labels_list}

Classification Guidelines:
- Bug: User reports a crash, error, unexpected behavior, or something is broken
- Enhancement: User requests a new feature, improvement, or change to existing functionality
- Question: User asks for help, clarification, documentation, or how to use something
- Documentation: Specifically about improving or fixing documentation

IMPORTANT: Respond ONLY with valid JSON in this exact format:
{{"classification": "<one of the allowed labels>", "reason": "<brief explanation in one sentence>"}}

Do NOT include any other text, formatting, or explanation outside the JSON."""

    user_content = f"""Issue Title: {title}

Issue Body:
{body if body else '(No description provided)'}

Classify this issue and respond with JSON only."""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=os.getenv('GROQ_MODEL', MODEL_ISSUE_TRIAGE),
            max_tokens=512,
            temperature=0
        )
        
        if not response.choices:
            raise ValueError("No response from LLM")
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content from LLM")
        result_text = content.strip()
        
        # Extract JSON if wrapped - safe extraction
        if "```json" in result_text:
            # Find first ```json and corresponding closing ```
            json_start = result_text.find("```json")
            if json_start != -1:
                # Start after ```json and newline
                content_start = json_start + 7  # len("```json")
                # Skip any whitespace/newline after ```json
                while content_start < len(result_text) and result_text[content_start] in '\n\r\t ':
                    content_start += 1
                # Find closing ```
                json_end = result_text.find("```", content_start)
                if json_end != -1:
                    result_text = result_text[content_start:json_end].strip()
        elif "```" in result_text:
            parts = result_text.split("```")
            if len(parts) >= 3:
                result_text = parts[1].strip()
        
        result = json.loads(result_text)
        classification = result.get('classification', '')
        
        # Validate classification - use first label as default if invalid
        if classification not in allowed_labels:
            classification = allowed_labels[0] if allowed_labels else 'Question'
        
        return {
            "classification": classification,
            "reason": result.get('reason', 'Automatically classified by Repogent AI')
        }
        
    except Exception as e:
        print(f"❌ Classification error: {e}", file=sys.stderr)
        # Use config default_label for consistency
        return {
            "classification": default_label,
            "reason": "Classification failed, manual review needed"
        }

def post_comment(token, repo, issue_number, body):
    """Post a comment to the issue"""
    import requests
    
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Repogent-Bot/1.0'
    }
    
    try:
        response = requests.post(url, headers=headers, json={'body': body}, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print(f"Error posting comment: timeout after {HTTP_TIMEOUT_SECONDS}s")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error posting comment: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding response: {e}")
        return None

def add_labels(token, repo, issue_number, labels):
    """Add labels to the issue"""
    import requests
    
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Repogent-Bot/1.0'
    }
    
    try:
        response = requests.post(url, headers=headers, json={'labels': labels}, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print(f"Error adding labels: timeout after {HTTP_TIMEOUT_SECONDS}s")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error adding labels: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding response: {e}")
        return None

def main():
    # Get environment variables
    groq_api_key = os.environ.get('GROQ_API_KEY')
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    issue_number_str = os.environ.get('ISSUE_NUMBER')
    issue_title = os.environ.get('ISSUE_TITLE')
    issue_body = os.environ.get('ISSUE_BODY', '')
    
    # Validate and convert issue_number
    try:
        issue_number = int(issue_number_str) if issue_number_str else None
        if not issue_number or issue_number <= 0:
            print("Invalid issue number", file=sys.stderr)
            sys.exit(1)
    except (ValueError, TypeError):
        print(f"Invalid issue number format: {issue_number_str}", file=sys.stderr)
        sys.exit(1)
    
    if not all([groq_api_key, github_token, repo, issue_title]):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)
    
    # Load config and initialize Groq client
    config = load_config()
    allowed_labels = config.get('labels', ['Bug', 'Enhancement', 'Question'])
    default_label = config.get('default_label', 'Question')
    client = Groq(api_key=groq_api_key)
    
    print(f"🔍 Triaging issue #{issue_number}: {issue_title}", file=sys.stderr)
    
    # Classify the issue
    result = classify_issue(client, issue_title, issue_body, allowed_labels, default_label)
    classification = result['classification']
    reason = result['reason']
    
    print(f"🏷️ Classification: {classification}", file=sys.stderr)
    print(f"💭 Reason: {reason}", file=sys.stderr)
    
    # Add labels
    try:
        add_labels(github_token, repo, issue_number, [classification])
        print(f"✅ Added label: {classification}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to add label: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Sanitize classification and reason for Markdown (escape special chars)
    def escape_markdown(text):
        """Escape Markdown special characters"""
        replacements = [
            ('\\', '\\\\'),  # Backslash first
            ('*', '\\*'),
            ('_', '\\_'),
            ('[', '\\['),
            (']', '\\]'),
            ('(', '\\('),
            (')', '\\)'),
            ('`', '\\`'),
            ('#', '\\#'),
            ('>', '\\>'),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text
    
    safe_classification = escape_markdown(classification)
    safe_reason = escape_markdown(reason)
    
    # Post comment
    comment = f"""🤖 **Beep boop! Repogent here.**

I've automatically triaged this issue as: **{safe_classification}**

**Reason:** {safe_reason}

My fellow agents and human maintainers will take it from here. Thanks for your contribution! ⚡

---
*Powered by Groq's ultra-fast LLM inference. If this classification seems incorrect, please adjust the labels manually.*"""
    
    try:
        post_comment(github_token, repo, issue_number, comment)
        print(f"💬 Posted comment", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to post comment: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"🎉 Successfully triaged issue #{issue_number} as {classification}", file=sys.stderr)

if __name__ == '__main__':
    main()
