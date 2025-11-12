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

"""
Repogent PR Review Script
Version: 1.0.0
Analyzes pull request diffs using Groq LLM and provides structured code review feedback.
"""

import os
import sys
import json
from groq import Groq

__version__ = "1.0.0"

# Set up Groq credentials
if not os.environ.get("GROQ_API_KEY"):
    print("No Groq API key found", file=sys.stderr)
    sys.exit(1)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

model_engine = os.environ.get("MODEL", "llama-3.3-70b-versatile")
commit_title = os.environ.get("COMMIT_TITLE", "")
commit_message = os.environ.get("COMMIT_BODY", "")
try:
    max_length = int(os.environ.get("MAX_LENGTH", "8000"))
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
    
    if code_start > 4 and code_end > code_start:
        # Calculate how much code we can keep
        template_size = len(enhanced_prompt) - (code_end - code_start)
        available_for_code = max_length - template_size - 100  # 100 byte safety margin
        
        if available_for_code > 500:  # Minimum viable code size
            truncated_code = code[:available_for_code] + "\n... (truncated)"
            enhanced_prompt = enhanced_prompt[:code_start] + truncated_code + enhanced_prompt[code_end:]
            print(f"⚠️ Prompt truncated to {max_length} characters", file=sys.stderr)
        else:
            print(f"❌ Diff too large to process (>{max_length} chars)", file=sys.stderr)
            print(json.dumps([{
                "file": "general",
                "line": 0,
                "severity": "WARNING",
                "message": "Diff too large for AI review. Please review manually.",
                "suggestion": ""
            }]))
            sys.exit(0)

kwargs = {'model': model_engine}
kwargs['temperature'] = 0.3  # Lower for more consistent JSON
kwargs['max_tokens'] = 2048  # More tokens for detailed reviews
kwargs['messages'] = [
    {"role": "system",
     "content": "You are an expert code reviewer. Always respond with valid JSON."},
    {"role": "user", "content": enhanced_prompt},
]

try:
    response = client.chat.completions.create(**kwargs)
    if response.choices and len(response.choices) > 0:
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content from LLM")
        review_text = content.strip()
        
        # Try to parse as JSON
        try:
            # Extract JSON if wrapped in markdown code blocks
            if "```json" in review_text:
                parts = review_text.split("```json")
                if len(parts) > 1:
                    inner_parts = parts[1].split("```")
                    if len(inner_parts) > 0:
                        review_text = inner_parts[0].strip()
            elif "```" in review_text:
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
            
        except json.JSONDecodeError:
            # Fallback: treat as plain text review
            print(json.dumps([{
                "file": "general",
                "line": 0,
                "severity": "SUGGESTION",
                "message": review_text,
                "suggestion": ""
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
