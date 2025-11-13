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

# Constants
HTTP_TIMEOUT_SECONDS = 30  # HTTP request timeout
MAX_INLINE_COMMENTS = 50  # Maximum inline comments per review
LINE_DISTANCE_THRESHOLD = 3  # Maximum distance for approximate line matches

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
        elif line.startswith('+++'):
            # Extract file path (remove +++ b/ prefix), skip deleted files
            match = re.match(r'\+\+\+ b/(.*)', line)
            if match:
                file_path = match.group(1)
                # Skip /dev/null (deleted files) or empty paths
                if file_path == '/dev/null' or not file_path or not file_path.strip():
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
            # Only process if we have a valid current_file
            if current_file is not None:
                match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                if match:
                    current_line = int(match.group(1))
        elif current_file is not None and current_line > 0:
            if line.startswith('+') and not line.startswith('+++'):
                # Added line
                file_lines[current_file]['added'].append(current_line)
                file_lines[current_file]['all'].append(current_line)
                current_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                # Removed line - don't increment current_line (refers to new file)
                pass
            elif line.startswith(' '):
                # Context line (space prefix) - these exist in both old and new file
                file_lines[current_file]['context'].append(current_line)
                file_lines[current_file]['all'].append(current_line)
                current_line += 1
            # Empty lines in diff output are typically between hunks or at end
            # Don't treat them as actual file lines to avoid off-by-one errors
            # Ignore diff metadata lines (e.g., "\ No newline at end of file")
    
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
            
            # Additional safety check - ensure we have lines to work with
            if not available_lines:
                general_comment_parts.append(f"**{file}:{line}**\n{format_review_comment(review)}")
                continue
            
            # Strategy 1: Exact match - use directly, no distance check needed
            if line in available_lines:
                comment_body = format_review_comment(review)
                comments.append({
                    'path': file,
                    'line': line,
                    'body': comment_body
                })
            # Strategy 2: Find closest available line
            else:
                # Prefer added lines over context lines
                if added_lines:
                    target_line = min(added_lines, key=lambda x: abs(x - line))
                else:
                    target_line = min(available_lines, key=lambda x: abs(x - line))
                
                distance = abs(target_line - line)
                # Use constant for threshold
                if distance <= LINE_DISTANCE_THRESHOLD:
                    comment_body = f"*Note: Original line {line} not in diff, commenting on nearest changed line {target_line}*\n\n" + format_review_comment(review)
                    comments.append({
                        'path': file,
                        'line': target_line,
                        'body': comment_body
                    })
                else:
                    # Too far, use general comment
                    general_comment_parts.append(f"**{file}:~{line}** *(line not in diff)*\n{format_review_comment(review)}")
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
    
    # Limit inline comments to avoid overwhelming the review
    if len(comments) > MAX_INLINE_COMMENTS:
        print(f"⚠️ Too many inline comments ({len(comments)}), limiting to {MAX_INLINE_COMMENTS}", file=sys.stderr)
        # Move excess comments to general comments
        excess_comments = comments[MAX_INLINE_COMMENTS:]
        for comment in excess_comments:
            general_comment_parts.append(f"**{comment['path']}:{comment['line']}**\n{comment['body']}")
        comments = comments[:MAX_INLINE_COMMENTS]
        # Update review data
        review_data['comments'] = comments
        review_title = os.environ.get('REVIEW_TITLE', '# Code Review by Repogent AI')
        review_data['body'] = f"{review_title}\n\n" + "\n\n---\n\n".join(general_comment_parts)
    
    # Only post if we have comments or a body
    if comments or general_comment_parts:
        try:
            response = requests.post(api_url, headers=headers, json=review_data, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            print(f"✅ Posted review with {len(comments)} inline comments", file=sys.stderr)
            return True
        except requests.exceptions.Timeout:
            print(f"❌ Timeout posting review (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return False
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
    pr_number_str = os.environ.get('PR_NUMBER')
    commit_sha = os.environ.get('COMMIT_SHA')
    
    # Validate and convert pr_number
    try:
        pr_number = int(pr_number_str) if pr_number_str else None
        if not pr_number or pr_number <= 0:
            print("Invalid PR number", file=sys.stderr)
            sys.exit(1)
    except (ValueError, TypeError):
        print(f"Invalid PR number format: {pr_number_str}", file=sys.stderr)
        sys.exit(1)
    
    if not all([github_token, repo, commit_sha]):
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
