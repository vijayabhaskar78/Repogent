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
import requests
import re

def parse_diff_for_line_mapping(diff_text):
    """
    Parse git diff to map file paths to changed and context line numbers.
    Returns a dict: {file_path: {'added': [lines], 'context': [lines], 'all': [lines]}}
    """
    file_lines = {}
    current_file = None
    current_line = 0
    
    for line in diff_text.split('\n'):
        # New file - reset state
        if line.startswith('diff --git'):
            current_file = None
            current_line = 0
        elif line.startswith('---'):
            # Check for deleted files (--- a/file vs --- /dev/null)
            if '/dev/null' in line:
                current_file = None
        elif line.startswith('+++'):
            # Extract file path (remove +++ b/ prefix), skip deleted files
            match = re.match(r'\+\+\+ b/(.*)', line)
            if match:
                file_path = match.group(1)
                # Skip /dev/null (deleted files)
                if file_path == '/dev/null':
                    current_file = None
                    continue
                current_file = file_path
                if current_file not in file_lines:
                    file_lines[current_file] = {
                        'added': [],
                        'context': [],
                        'all': []
                    }
        elif line.startswith('@@'):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            if match:
                current_line = int(match.group(1))
        elif current_file and current_line > 0 and line.startswith('+') and not line.startswith('+++'):
            # This is an added line (only process if we've seen a hunk header)
            file_lines[current_file]['added'].append(current_line)
            file_lines[current_file]['all'].append(current_line)
            current_line += 1
        elif current_file and current_line > 0 and not line.startswith('-'):
            # Context line (not removed) - only process if we've seen a hunk header
            file_lines[current_file]['context'].append(current_line)
            file_lines[current_file]['all'].append(current_line)
            current_line += 1
    
    return file_lines

def severity_emoji(severity):
    """Return emoji for severity level"""
    emoji_map = {
        'CRITICAL': '🔴',
        'WARNING': '🟡',
        'SUGGESTION': '🟢',
        'INFO': '💡'
    }
    # Safe handling of None or non-string severity
    if severity is None or not isinstance(severity, str):
        return '💬'
    return emoji_map.get(severity.upper(), '💬')

def format_review_comment(review):
    """Format a review comment with severity and suggestion"""
    emoji = severity_emoji(review.get('severity', 'INFO'))
    severity = review.get('severity', 'INFO')
    message = review.get('message', '')
    suggestion = review.get('suggestion', '')
    
    comment = f"{emoji} **{severity}**\n\n{message}"
    
    if suggestion:
        comment += f"\n\n**Suggested fix:**\n```\n{suggestion}\n```"
    
    return comment

def post_review_comments(github_token, repo, pr_number, commit_sha, reviews, diff_text):
    """
    Post inline review comments to GitHub PR.
    Uses GitHub's Pull Request Review API.
    """
    # Parse diff to get line mappings
    file_lines = parse_diff_for_line_mapping(diff_text)
    
    # Prepare review comments
    comments = []
    general_comment_parts = []
    
    # Validate reviews is a list
    if not isinstance(reviews, list):
        print("⚠️ Reviews is not a list, skipping", file=sys.stderr)
        return True
    
    for review in reviews:
        if not isinstance(review, dict):
            continue
        
        file = review.get('file', '')
        # Ensure line is an integer
        try:
            line = int(review.get('line', 0))
        except (ValueError, TypeError):
            line = 0
        
        # Skip error entries
        if file in ['error', 'general'] or line == 0:
            general_comment_parts.append(format_review_comment(review))
            continue
        
        # Try to find the best line to comment on
        if file in file_lines and file_lines[file]['all']:
            available_lines = file_lines[file]['all']
            added_lines = file_lines[file]['added']
            
            # Strategy 1: If the line is in the diff, use it directly
            if line in available_lines:
                target_line = line
            # Strategy 2: Prefer added lines over context lines
            elif added_lines:
                # Find closest added line
                target_line = min(added_lines, key=lambda x: abs(x - line))
            # Strategy 3: Fall back to any available line
            else:
                target_line = min(available_lines, key=lambda x: abs(x - line))
            
            # Only add comment if target line is reasonably close (within 10 lines)
            if abs(target_line - line) <= 10:
                comments.append({
                    'path': file,
                    'line': target_line,
                    'body': format_review_comment(review)
                })
            else:
                # Too far away, add to general comments
                general_comment_parts.append(f"**{file}:{line}**\n{format_review_comment(review)}")
        else:
            # File not in diff or no available lines
            general_comment_parts.append(f"**{file}:{line}**\n{format_review_comment(review)}")
    
    # Create the review
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    headers = {
        'Authorization': f'Bearer {github_token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Repogent-Bot/1.0'
    }
    
    review_data = {
        'commit_id': commit_sha,
        'event': 'COMMENT'
    }
    
    # Add inline comments only if we have them
    if comments:
        review_data['comments'] = comments
    
    # Add general comment body if there are general issues
    if general_comment_parts:
        review_title = os.environ.get('REVIEW_TITLE', '# Code Review by Repogent AI')
        review_data['body'] = f"{review_title}\n\n" + "\n\n---\n\n".join(general_comment_parts)
    
    # Only post if we have comments or a body
    if comments or general_comment_parts:
        try:
            response = requests.post(api_url, headers=headers, json=review_data, timeout=30)
            response.raise_for_status()
            print(f"✅ Posted review with {len(comments)} inline comments", file=sys.stderr)
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to post review: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    print(f"Response: {e.response.text}", file=sys.stderr)
                except Exception:
                    print(f"Response code: {e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'}", file=sys.stderr)
            return False
    else:
        print("✅ No issues found - PR looks good!", file=sys.stderr)
        return True

def main():
    # Get environment variables
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    pr_number = os.environ.get('PR_NUMBER')
    commit_sha = os.environ.get('COMMIT_SHA')
    
    if not all([github_token, repo, pr_number, commit_sha]):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)
    
    # Read reviews JSON from file
    try:
        with open('reviews.json', 'r', encoding='utf-8') as f:
            reviews = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to read reviews JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"Unicode error reading reviews JSON: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Read diff file
    diff_file = 'diff.txt'
    try:
        with open(diff_file, 'r', encoding='utf-8', errors='replace') as f:
            diff_text = f.read()
    except FileNotFoundError:
        print(f"Diff file not found: {diff_file}", file=sys.stderr)
        diff_text = ""
    
    # Post comments
    success = post_review_comments(github_token, repo, pr_number, commit_sha, reviews, diff_text)
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
