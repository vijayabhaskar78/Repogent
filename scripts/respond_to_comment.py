#!/usr/bin/env python3
"""
Respond to Comment Script - GitHub Actions version
Provides intelligent responses to issue comments
"""
import os
import sys
import json
from groq import Groq

# Import shared constants
from config_constants import (
    MAX_CONVERSATION_CONTEXT,
    HTTP_TIMEOUT_SECONDS,
    MODEL_COMMENT_RESPONSE
)

# Local constants
MAX_RESPONSE_LENGTH = 5000  # Maximum response length

def is_bot_user(username: str, user_type: str = '') -> bool:
    """Consistently detect bot users across all scripts"""
    if user_type == 'Bot':
        return True
    # Defensive check: ensure username is not None or empty
    if not username:
        return False
    if username.endswith('[bot]'):
        return True
    # Whitelist known bot patterns (more specific than substring matching)
    bot_names = ['github-actions', 'dependabot', 'renovate', 'greenkeeper', 'codecov', 'repogent']
    return any(bot in username.lower() for bot in bot_names)


def get_issue_comments(token, repo, issue_number):
    """Get all comments from the issue, excluding bot comments"""
    import requests
    
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Repogent-Bot/1.0'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        comments = response.json()
    except requests.exceptions.Timeout:
        print(f"Error fetching issue comments: timeout after {HTTP_TIMEOUT_SECONDS}s")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching issue comments: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding comments response: {e}")
        return []
    conversation = []
    for comment in comments:
        # Safe dict access with validation
        if not isinstance(comment, dict):
            continue
        
        user = comment.get('user', {})
        if not isinstance(user, dict):
            continue
            
        author = user.get('login', 'unknown')
        user_type = user.get('type', '')
        body = comment.get('body', '')
        created_at = comment.get('created_at', '')
        
        # Use consistent bot detection
        if not is_bot_user(author, user_type):
            conversation.append({
                'author': author,
                'body': body,
                'created_at': created_at
            })
    return conversation

def generate_response(client, issue_title, issue_body, comment_body, conversation_history):
    """Generate intelligent response using Groq"""
    
    # Build conversation context
    context = f"Issue Title: {issue_title}\n\nIssue Description:\n{issue_body}\n\n"
    
    # Exclude the most recent comment (the one we're responding to) to avoid duplication
    if conversation_history and conversation_history[-1].get('body') == comment_body:
        context_history = conversation_history[:-1]
    else:
        context_history = conversation_history
    
    if context_history:
        context += "Previous Comments:\n"
        for msg in context_history[-MAX_CONVERSATION_CONTEXT:]:
            author = msg.get('author', 'unknown')
            body = msg.get('body', '')
            # Safely slice with bounds check
            body_preview = body[:200] if body else '(no content)'
            context += f"- {author}: {body_preview}\n"
    
    system_prompt = """You are Repogent, a helpful AI assistant for GitHub repositories. 
Your role is to provide helpful, technical responses to issue comments.

Guidelines:
- Be concise and technical
- Provide actionable advice when possible
- Ask clarifying questions if needed
- Reference code, documentation, or error messages
- Be friendly but professional

Keep responses under 300 words."""

    user_content = f"""{context}

Latest Comment: {comment_body}

Please provide a helpful response to this comment."""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=os.getenv('GROQ_MODEL', MODEL_COMMENT_RESPONSE),
            max_tokens=1024,
            temperature=0.7
        )
        
        if not response.choices:
            print(f"⚠️ No response choices from LLM", file=sys.stderr)
            return None
        
        content = response.choices[0].message.content
        if not content:
            print(f"⚠️ Empty response content from LLM", file=sys.stderr)
            return None
        
        return content.strip()
        
    except Exception as e:
        print(f"❌ Response generation error: {e}", file=sys.stderr)
        return None

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
        print(f"Error decoding post response: {e}")
        return None

def main():
    # Get environment variables
    groq_api_key = os.environ.get('GROQ_API_KEY')
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    issue_number_str = os.environ.get('ISSUE_NUMBER')
    comment_body = os.environ.get('COMMENT_BODY', '')
    comment_author = os.environ.get('COMMENT_AUTHOR', '')
    issue_title = os.environ.get('ISSUE_TITLE', '')
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
    
    if not all([groq_api_key, github_token, repo, comment_body]):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)
    
    # Skip if comment is from a bot (use consistent detection)
    # Check for None, empty string, or bot user
    if not comment_author or not comment_author.strip():
        print("Comment author is empty, skipping", file=sys.stderr)
        sys.exit(0)
    
    if is_bot_user(comment_author):
        print("Comment is from a bot, skipping to avoid loops", file=sys.stderr)
        sys.exit(0)
    
    # Initialize Groq client
    client = Groq(api_key=groq_api_key)
    
    print(f"💬 Responding to comment on issue #{issue_number}", file=sys.stderr)
    
    # Get conversation history
    try:
        conversation = get_issue_comments(github_token, repo, issue_number)
    except Exception as e:
        print(f"⚠️ Could not fetch conversation history: {e}", file=sys.stderr)
        conversation = []
    
    # Generate response
    response_text = generate_response(client, issue_title, issue_body, comment_body, conversation)
    
    if not response_text:
        print("❌ Failed to generate response", file=sys.stderr)
        sys.exit(1)
    
    # Limit response length to prevent abuse
    if len(response_text) > MAX_RESPONSE_LENGTH:
        response_text = response_text[:MAX_RESPONSE_LENGTH] + "\n\n... (response truncated for length)"
    
    # Format response with signature
    formatted_response = f"""{response_text}

---
*🤖 Response generated by Repogent AI powered by Groq*"""
    
    # Post comment
    try:
        post_comment(github_token, repo, issue_number, formatted_response)
        print(f"✅ Posted response", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to post comment: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"🎉 Successfully responded to comment on issue #{issue_number}", file=sys.stderr)

if __name__ == '__main__':
    main()
