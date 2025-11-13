#!/usr/bin/env python3
"""
Enhanced PR Reviewer with Agent Communication
Accepts messages from CI/CD Agent and provides context-aware reviews.
"""
import os
import sys
import json
from typing import Dict, Any, Optional, List
import agent_comms
import requests

# Import shared constants
from config_constants import HTTP_TIMEOUT_SECONDS


def analyze_build_failure_context(pr_number: int, failure_data: Dict[str, Any]) -> str:
    """Analyze PR in context of build failure"""
    analysis = failure_data.get('analysis', {})
    failure_type = analysis.get('failure_type', 'unknown')
    
    # Get PR context
    context = agent_comms.get_context(f"pr_{pr_number}")
    
    comment = f"""## 🔍 Build Failure Analysis

The CI/CD agent detected a **{failure_type}** after this PR was merged.

"""
    
    # Add specific guidance based on failure type
    if failure_type == 'test_failure':
        comment += """### Test Failure Context
Your changes likely broke existing tests. Please:
1. Review the failing test assertions
2. Check if your code changes match test expectations
3. Update tests if the behavior change is intentional

"""
    elif failure_type == 'compile_error':
        comment += """### Compilation Error Context
Your code has syntax or type errors. Please:
1. Fix syntax errors in the modified files
2. Ensure all types are correct (if using TypeScript)
3. Run local build: `npm run build` or `python -m py_compile`

"""
    elif failure_type == 'dependency_error':
        comment += """### Dependency Issue Context
Missing or conflicting dependencies detected. Please:
1. Update `package.json` or `requirements.txt` if you added new imports
2. Ensure all dependencies are committed
3. Run `npm install` or `pip install` locally

"""
    
    # Add error details
    error_details = analysis.get('error_details', [])
    if error_details:
        comment += "### 🐛 Specific Errors:\n"
        for i, error in enumerate(error_details[:3], 1):
            comment += f"{i}. ```\n{error}\n```\n"
    
    # Add suggestions
    suggestions = analysis.get('suggestions', [])
    if suggestions:
        comment += "\n### 💡 Recommended Actions:\n"
        for i, suggestion in enumerate(suggestions, 1):
            comment += f"{i}. {suggestion}\n"
    
    # Link to build
    job_url = failure_data.get('job_url')
    if job_url:
        comment += f"\n### 📊 Full Build Log:\n{job_url}\n"
    
    comment += "\n---\n*🤖 Analysis by PR Reviewer based on CI/CD Agent report*"
    
    return comment


def check_for_cicd_messages():
    """Check if there are any messages from CI/CD agent"""
    messages = agent_comms.receive_messages('pr_reviewer')
    
    for message in messages:
        if message.message_type == 'analyze_build_failure':
            # Process build failure
            payload = message.payload
            pr_number = payload.get('pr_number')
            
            if pr_number:
                print(f"📨 Received build failure notification for PR #{pr_number}", file=sys.stderr)
                
                # Generate analysis
                analysis_comment = analyze_build_failure_context(pr_number, payload)
                
                # Post comment
                from post_review_comments import post_comment
                github_token = os.environ.get('GITHUB_TOKEN')
                repo = os.environ.get('GITHUB_REPOSITORY')
                
                if github_token and repo:
                    # Post as issue comment (works for PRs too)
                    import requests
                    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
                    headers = {
                        'Authorization': f'Bearer {github_token}',
                        'Accept': 'application/vnd.github+json',
                        'User-Agent': 'Repogent-PRReviewer/1.0'
                    }
                    
                    try:
                        response = requests.post(url, headers=headers, 
                                               json={'body': analysis_comment}, timeout=HTTP_TIMEOUT_SECONDS)
                        response.raise_for_status()
                        print(f"✅ Posted build failure analysis to PR #{pr_number}", file=sys.stderr)
                        
                        # Log decision
                        agent_comms.log_decision('pr_reviewer', {
                            'action': 'build_failure_analysis',
                            'pr_number': pr_number,
                            'failure_type': payload.get('analysis', {}).get('failure_type')
                        })
                    except requests.exceptions.Timeout:
                        print(f"❌ Timeout posting comment (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
                    except requests.exceptions.RequestException as e:
                        print(f"❌ Failed to post comment: {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"❌ Unexpected error: {e}", file=sys.stderr)


if __name__ == '__main__':
    # Check for inter-agent messages first
    check_for_cicd_messages()
    
    # Then run normal PR review if needed
    print("✅ Enhanced PR Reviewer completed", file=sys.stderr)
