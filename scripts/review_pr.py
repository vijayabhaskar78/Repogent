#!/usr/bin/env python3
# Copyright 2025 vijayabhaskar78
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import json
from groq import Groq

# Import shared constants
from config_constants import MODEL_PR_REVIEW

# Set up Groq credentials
if not os.environ.get("GROQ_API_KEY"):
    print("No Groq API key found", file=sys.stderr)
    sys.exit(1)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Use shared constant for model selection
model_engine = os.environ.get("MODEL", MODEL_PR_REVIEW)
commit_title = os.environ.get("COMMIT_TITLE", "")
commit_message = os.environ.get("COMMIT_BODY", "")
try:
    max_length = int(os.environ.get("MAX_LENGTH", "8000"))
    # Validate bounds - too small and prompts are truncated too much, too large and API fails
    if max_length < 1000:
        print(f"⚠️ MAX_LENGTH too small ({max_length}), using minimum 1000", file=sys.stderr)
        max_length = 1000
    elif max_length > 100000:
        print(f"⚠️ MAX_LENGTH too large ({max_length}), using maximum 100000", file=sys.stderr)
        max_length = 100000
except ValueError:
    print("⚠️ Invalid MAX_LENGTH, using default 8000", file=sys.stderr)
    max_length = 8000

# Analyze the code changes
code = sys.stdin.read()

# Check if diff is empty
if not code or not code.strip():
    print(json.dumps([]))
    sys.exit(0)

# Enhanced prompt for structured output
enhanced_prompt = f"""You are an expert code reviewer. Review the following git diff and provide structured feedback.

For each issue you find, provide:
1. The file path (relative path from repository root)
2. The line number in the NEW version of the file (look for lines starting with + in the diff)
3. Severity level: CRITICAL (security/bugs), WARNING (performance/code smell), or SUGGESTION (style/best practices)
4. A clear description of the issue
5. An optional code suggestion to fix it

Format your response as a JSON array like this:
[
  {{
    "file": "path/to/file.py",
    "line": 42,
    "severity": "CRITICAL",
    "message": "Potential SQL injection vulnerability",
    "suggestion": "Use parameterized queries instead"
  }}
]

IMPORTANT: The "line" field should be the actual line number in the new file (from the +line_number in @@ headers), not a relative position.
If you cannot determine a specific line number, use 0 and the comment will be posted as a general review comment.

If there are no issues, return an empty array: []

Git diff to review:
```
{code}
```

Commit context:
- Title: {commit_title}
- Message: {commit_message}

Return ONLY the JSON array, no other text."""

if len(enhanced_prompt) > max_length:
    # Truncate the code portion safely, not the JSON template
    code_start = enhanced_prompt.find("```\n") + 4
    code_end = enhanced_prompt.rfind("\n```")
    
    # Validate bounds FIRST before any operations
    if code_start <= 4 or code_end <= code_start or code_end >= len(enhanced_prompt):
        # Invalid diff structure - cannot safely truncate
        print(f"❌ Cannot safely truncate prompt (invalid diff structure)", file=sys.stderr)
        print(json.dumps([{
            "file": "general",
            "line": 0,
            "severity": "WARNING",
            "message": "Diff structure invalid for processing. Please review manually.",
            "suggestion": ""
        }]))
        sys.exit(0)
    
    # Calculate how much code we can keep
    template_size = len(enhanced_prompt) - (code_end - code_start)
    available_for_code = max_length - template_size - 100  # 100 byte safety margin
    
    # Minimum viable code size - need at least this to make sense
    MIN_CODE_SIZE = 200
    
    if available_for_code > MIN_CODE_SIZE and len(code) > available_for_code:
        # Truncate code intelligently - try to keep complete lines
        truncated_code = code[:available_for_code]
        # Find last complete line to avoid breaking mid-line
        last_newline = truncated_code.rfind('\n')
        if last_newline > MIN_CODE_SIZE // 2:
            truncated_code = truncated_code[:last_newline]
        truncated_code += "\n... (truncated - diff too large)"
        
        enhanced_prompt = enhanced_prompt[:code_start] + truncated_code + enhanced_prompt[code_end:]
        print(f"⚠️ Prompt truncated to ~{len(enhanced_prompt)} characters", file=sys.stderr)
    else:
        print(f"❌ Diff too large to process (>{max_length} chars, need >{MIN_CODE_SIZE} for code)", file=sys.stderr)
        print(json.dumps([{
            "file": "general",
            "line": 0,
            "severity": "WARNING",
            "message": "Diff too large for AI review. Please review manually or split into smaller PRs.",
            "suggestion": ""
        }]))
        sys.exit(0)

kwargs = {'model': model_engine}
# Lower temperature for more consistent JSON output (configurable via env)
try:
    temp_str = os.environ.get("REVIEW_TEMPERATURE", "0.3")
    if temp_str:  # Check for empty string
        temperature = float(temp_str)
        kwargs['temperature'] = max(0.0, min(1.0, temperature))  # Clamp to valid range
    else:
        kwargs['temperature'] = 0.3
except (ValueError, TypeError):
    kwargs['temperature'] = 0.3
kwargs['max_tokens'] = 2048  # More tokens for detailed reviews
kwargs['messages'] = [
    {"role": "system",
     "content": "You are an expert code reviewer. Always respond with valid JSON."},
    {"role": "user", "content": enhanced_prompt},
]

try:
    response = client.chat.completions.create(**kwargs)
    if response.choices:
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content from LLM")
        review_text = content.strip()
        
        # Try to parse as JSON
        try:
            # Extract JSON if wrapped in markdown code blocks
            if "```json" in review_text:
                # Find first ```json and corresponding closing ```
                json_start = review_text.find("```json")
                if json_start != -1:
                    # Start after ```json and newline
                    content_start = json_start + 7  # len("```json")
                    # Skip any whitespace/newline after ```json
                    while content_start < len(review_text) and review_text[content_start] in '\n\r\t ':
                        content_start += 1
                    # Find closing ```
                    json_end = review_text.find("```", content_start)
                    if json_end != -1:
                        review_text = review_text[content_start:json_end].strip()
            elif "```" in review_text:
                # Generic code block
                parts = review_text.split("```")
                if len(parts) >= 3:
                    review_text = parts[1].strip()
            
            reviews = json.loads(review_text)
            
            # Validate that reviews is a list
            if not isinstance(reviews, list):
                reviews = [{
                    "file": "general",
                    "line": 0,
                    "severity": "SUGGESTION",
                    "message": str(reviews),
                    "suggestion": ""
                }]
            
            # Output structured JSON for processing
            print(json.dumps(reviews, indent=2))
            
        except json.JSONDecodeError as e:
            # Fallback: treat as plain text review but warn about parsing failure
            print(f"⚠️ Failed to parse LLM response as JSON: {e}", file=sys.stderr)
            print(json.dumps([{
                "file": "general",
                "line": 0,
                "severity": "WARNING",
                "message": f"⚠️ AI Review (JSON parsing failed, showing raw output):\n\n{review_text}",
                "suggestion": "The LLM did not return valid JSON. Please review manually."
            }], indent=2))
    else:
        print(json.dumps([{
            "file": "error",
            "line": 0,
            "severity": "CRITICAL",
            "message": f"No response from Groq: {response}",
            "suggestion": ""
        }], indent=2))
except Exception as e:
    print(json.dumps([{
        "file": "error",
        "line": 0,
        "severity": "CRITICAL",
        "message": f"Groq API error: {e}",
        "suggestion": ""
    }], indent=2))
