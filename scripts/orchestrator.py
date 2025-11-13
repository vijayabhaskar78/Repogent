#!/usr/bin/env python3
"""
Repogent Orchestrator Agent
Central coordinator for all sub-agents in the Repogent ecosystem.
Manages agent-to-agent communication, context, and workflow routing.
"""
import os
import sys
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

# Import shared constants
from config_constants import (
    MAX_PAYLOAD_SIZE_BYTES,
    MAX_CONTEXT_SIZE_BYTES,
    MAX_CONTEXT_FILES,
    MAX_QUEUE_DEPTH,
    HTTP_TIMEOUT_SECONDS
)

__version__ = "1.0.0"

# Agent Registry
AGENTS = {
    'pr_reviewer': {
        'name': 'PR Reviewer',
        'script': 'review_pr.py',
        'capabilities': ['code_review', 'pr_analysis', 'inline_comments']
    },
    'issue_manager': {
        'name': 'Issue Manager',
        'script': 'triage_issue.py',
        'capabilities': ['issue_classification', 'labeling', 'triage']
    },
    'community_assistant': {
        'name': 'Community Assistant',
        'script': 'community_assistant.py',
        'capabilities': ['codebase_search', 'qa', 'documentation']
    },
    'cicd_agent': {
        'name': 'CI/CD Agent',
        'script': 'cicd_agent.py',
        'capabilities': ['build_monitoring', 'failure_analysis', 'deployment_tracking']
    }
}

class Message:
    """Standard message format for agent communication"""
    MAX_PAYLOAD_SIZE = MAX_PAYLOAD_SIZE_BYTES
    
    def __init__(self, sender: str, receiver: str, message_type: str, payload: Dict[str, Any]):
        # Validate inputs
        if not isinstance(sender, str) or not isinstance(receiver, str):
            raise ValueError("sender and receiver must be strings")
        if not isinstance(message_type, str):
            raise ValueError("message_type must be a string")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")
        
        # Check payload size
        payload_size = len(json.dumps(payload, default=str))
        if payload_size > self.MAX_PAYLOAD_SIZE:
            raise ValueError(f"Payload too large: {payload_size} bytes (max {self.MAX_PAYLOAD_SIZE})")
        
        # Generate unique ID with microsecond precision to avoid collisions
        now = datetime.now()
        self.id = f"{sender}_{receiver}_{now.timestamp()}_{id(payload)}"
        self.sender = sender
        self.receiver = receiver
        self.message_type = message_type
        self.payload = payload
        self.timestamp = now.isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'sender': self.sender,
            'receiver': self.receiver,
            'type': self.message_type,
            'payload': self.payload,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        # Validate required fields
        required_fields = ['sender', 'receiver', 'type', 'payload']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields in message data: {missing_fields}")
        
        # Validate payload is a dictionary
        if not isinstance(data['payload'], dict):
            raise ValueError(f"Payload must be a dictionary, got {type(data['payload'])}")
        
        msg = cls(
            sender=data['sender'],
            receiver=data['receiver'],
            message_type=data['type'],
            payload=data['payload']
        )
        msg.id = data.get('id', msg.id)
        msg.timestamp = data.get('timestamp', msg.timestamp)
        return msg


class ContextStore:
    """Manages context and state across agent interactions"""
    def __init__(self, storage_path: str = '.repogent/context'):
        self.storage_path = Path(storage_path).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_contexts = MAX_CONTEXT_FILES
        self.max_context_size = MAX_CONTEXT_SIZE_BYTES
    
    def _sanitize_context_id(self, context_id: str) -> str:
        """Sanitize context ID to prevent directory traversal"""
        # Remove dangerous characters
        safe_id = context_id.replace('..', '').replace('/', '_').replace('\\', '_')
        # Limit length
        return safe_id[:100]
    
    def save_context(self, context_id: str, data: Dict[str, Any]):
        """Save context data"""
        safe_id = self._sanitize_context_id(context_id)
        file_path = self.storage_path / f"{safe_id}.json"
        
        # Validate path BEFORE resolving to prevent symlink attacks
        try:
            # Check if path is within storage_path without following symlinks
            file_path.relative_to(self.storage_path)
        except ValueError:
            raise ValueError("Invalid context path - directory traversal detected")
        
        # Check storage limits
        existing_contexts = list(self.storage_path.glob('*.json'))
        if len(existing_contexts) >= self.max_contexts:
            # Cleanup oldest contexts (protect against TOCTOU by catching errors)
            oldest = sorted(existing_contexts, key=lambda p: p.stat().st_mtime)[:100]
            for old_file in oldest:
                try:
                    old_file.unlink()
                except FileNotFoundError:
                    # File already deleted by another process, ignore
                    pass
                except Exception as e:
                    # Handle other potential errors during deletion
                    print(f"⚠️ Error deleting {old_file}: {e}", file=sys.stderr)
        
        # Validate data size
        data_json = json.dumps({
            'id': safe_id,
            'data': data,
            'updated_at': datetime.now().isoformat()
        }, indent=2, default=str)  # default=str handles complex objects
        
        if len(data_json) > self.max_context_size:
            raise ValueError(f"Context data too large: {len(data_json)} bytes")
        
        # Now safe to resolve and save atomically
        file_path = file_path.resolve()
        
        # Use atomic write to prevent corruption
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', 
                                            dir=self.storage_path, delete=False) as tmp:
                tmp.write(data_json)
                tmp_path = tmp.name
            # Atomic rename (on POSIX systems)
            os.replace(tmp_path, file_path)
        except Exception as e:
            # Clean up temp file on error
            try:
                if 'tmp_path' in locals():
                    os.unlink(tmp_path)
            except Exception:
                pass
            raise e
    
    def load_context(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Load context data"""
        safe_id = self._sanitize_context_id(context_id)
        file_path = self.storage_path / f"{safe_id}.json"
        
        # Validate path BEFORE resolving - Python 3.8 compatible
        try:
            file_path.relative_to(self.storage_path)
        except ValueError:
            print(f"⚠️ Invalid context path rejected: {context_id}", file=sys.stderr)
            return None
        
        # Now safe to resolve
        file_path = file_path.resolve()
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Failed to load context {context_id}: {e}", file=sys.stderr)
            return None
    
    def get_pr_context(self, pr_number: int) -> Optional[Dict[str, Any]]:
        """Get all context related to a PR"""
        # Validate pr_number is a positive integer
        if not isinstance(pr_number, int) or pr_number <= 0:
            print(f"⚠️ Invalid PR number: {pr_number}", file=sys.stderr)
            return None
        return self.load_context(f"pr_{pr_number}")
    
    def save_pr_context(self, pr_number: int, data: Dict[str, Any]):
        """Save PR-related context"""
        # Validate pr_number is a positive integer
        if not isinstance(pr_number, int) or pr_number <= 0:
            print(f"⚠️ Invalid PR number: {pr_number}", file=sys.stderr)
            return
        existing = self.get_pr_context(pr_number)
        if existing and isinstance(existing, dict) and 'data' in existing:
            # Validate that existing['data'] is actually a dict before updating
            if isinstance(existing['data'], dict) and isinstance(data, dict):
                # Deep merge: create new dict to avoid mutation issues
                merged_data = {}
                merged_data.update(existing['data'])
                # Only update with new data, preserving nested structures
                for key, value in data.items():
                    if key in merged_data and isinstance(merged_data[key], dict) and isinstance(value, dict):
                        # Deep merge nested dicts
                        merged_data[key] = {**merged_data[key], **value}
                    else:
                        # Simple overwrite for non-dict values
                        merged_data[key] = value
                self.save_context(f"pr_{pr_number}", merged_data)
            else:
                # Existing data is malformed, start fresh
                print(f"⚠️ Malformed existing context for PR {pr_number}, resetting", file=sys.stderr)
                self.save_context(f"pr_{pr_number}", data)
        else:
            # Start fresh if no valid existing context
            self.save_context(f"pr_{pr_number}", data)


class MessageQueue:
    """Simple message queue for agent communication"""
    MAX_QUEUE_DEPTH = MAX_QUEUE_DEPTH
    
    # Message priority levels
    PRIORITY_CRITICAL = ['build_failure', 'security_alert']
    PRIORITY_HIGH = ['analyze_build_failure', 'request_context']
    
    def __init__(self, storage_path: str = '.repogent/queue'):
        self.storage_path = Path(storage_path).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def _get_message_priority(self, message: Message) -> int:
        """Get priority level (lower number = higher priority)"""
        if message.message_type in self.PRIORITY_CRITICAL:
            return 1
        elif message.message_type in self.PRIORITY_HIGH:
            return 2
        else:
            return 3
    
    def enqueue(self, message: Message):
        """Add message to queue"""
        # Check queue depth
        existing_messages = list(self.storage_path.glob('*.json'))
        if len(existing_messages) >= self.MAX_QUEUE_DEPTH:
            print(f"⚠️ Queue full ({len(existing_messages)} messages), dropping lowest priority message", file=sys.stderr)
            # Remove lowest priority oldest message instead of just oldest
            lowest_priority_msg = None
            lowest_priority = 0  # Initialize to highest possible priority
            oldest_time = float('inf')
            
            for msg_file in existing_messages:
                try:
                    with open(msg_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    temp_msg = Message.from_dict(data)
                    priority = self._get_message_priority(temp_msg)
                    msg_time = msg_file.stat().st_mtime
                    
                    # Select lowest priority (higher number = lower priority), and oldest within that priority
                    # First iteration (lowest_priority_msg is None) OR lower priority (higher number) OR same priority but older
                    if lowest_priority_msg is None or priority > lowest_priority or (priority == lowest_priority and msg_time < oldest_time):
                        lowest_priority = priority
                        oldest_time = msg_time
                        lowest_priority_msg = msg_file
                except Exception:
                    # If we can't read it, it's safe to delete
                    lowest_priority_msg = msg_file
                    break
            
            if lowest_priority_msg:
                print(f"  Dropping message: {lowest_priority_msg.name}", file=sys.stderr)
                try:
                    lowest_priority_msg.unlink()
                except FileNotFoundError:
                    # Already deleted by another process, that's fine
                    print(f"  Message already removed: {lowest_priority_msg.name}", file=sys.stderr)
        
        # Use atomic write to prevent corruption
        file_path = self.storage_path / f"{message.id}.json"
        # Write to temp file first, then atomic rename
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', 
                                            dir=self.storage_path, delete=False) as tmp:
                json.dump(message.to_dict(), tmp, indent=2)
                tmp_path = tmp.name
            # Atomic rename (on POSIX systems)
            os.replace(tmp_path, file_path)
        except Exception as e:
            # Clean up temp file on error
            try:
                if 'tmp_path' in locals():
                    os.unlink(tmp_path)
            except Exception:
                pass
            raise e
    
    def dequeue(self, receiver: str) -> Optional[Message]:
        """Get next message for receiver (highest priority first)"""
        # Collect all messages for this receiver with their priorities
        candidate_messages = []
        
        for file_path in self.storage_path.glob('*.json'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Safely check receiver field
                if data.get('receiver') == receiver:
                    message = Message.from_dict(data)
                    priority = self._get_message_priority(message)
                    msg_time = file_path.stat().st_mtime
                    candidate_messages.append((priority, msg_time, file_path, message))
            except FileNotFoundError:
                # File was deleted between glob and open
                continue
            except Exception as e:
                print(f"⚠️ Error reading message {file_path}: {e}", file=sys.stderr)
                # Optionally remove corrupted message file
                try:
                    file_path.unlink()
                    print(f"  Removed corrupted message file: {file_path.name}", file=sys.stderr)
                except FileNotFoundError:
                    pass
                except Exception:
                    pass
                continue
        
        # If no messages found, return None
        if not candidate_messages:
            return None
        
        # Sort by priority (lower number first = higher priority), then by time (older first)
        candidate_messages.sort(key=lambda x: (x[0], x[1]))
        
        # Get the highest priority, oldest message
        _, _, file_path, message = candidate_messages[0]
        
        # Remove from queue - handle race condition
        try:
            file_path.unlink()
        except FileNotFoundError:
            # Already deleted by another process, but we have the message
            print(f"⚠️ Message file already removed: {file_path.name}", file=sys.stderr)
        
        return message
    
    def peek_all(self, receiver: Optional[str] = None) -> List[Message]:
        """View all messages without removing"""
        messages = []
        for file_path in self.storage_path.glob('*.json'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Safely check receiver field
                if receiver is None or data.get('receiver') == receiver:
                    messages.append(Message.from_dict(data))
            except Exception:
                continue
        
        return messages


class Orchestrator:
    """Central orchestrator managing all agents"""
    
    def __init__(self):
        self.context_store = ContextStore()
        self.message_queue = MessageQueue()
        self.github_token = os.environ.get('GITHUB_TOKEN')
        self.repo = os.environ.get('GITHUB_REPOSITORY')
    
    def route_event(self, event_type: str, event_data: Dict[str, Any]) -> str:
        """Route GitHub events to appropriate agents"""
        
        routing_rules = {
            'pull_request': 'pr_reviewer',
            'pull_request_review': 'pr_reviewer',
            'issues': 'issue_manager',
            'issue_comment': self._route_comment,
            'workflow_run': 'cicd_agent',
            'workflow_job': 'cicd_agent',
            'check_run': 'cicd_agent',
        }
        
        handler = routing_rules.get(event_type)
        
        if callable(handler):
            return handler(event_data)
        
        return handler or 'unknown'
    
    def _route_comment(self, event_data: Dict[str, Any]) -> str:
        """Smart routing for comments based on content"""
        comment_body = event_data.get('comment', {}).get('body', '')
        
        # Validate comment_body is a string
        if not isinstance(comment_body, str):
            print(f"⚠️ Invalid comment body type: {type(comment_body)}", file=sys.stderr)
            return 'issue_manager'
        
        # If mentions @repogent, route to community assistant
        if '@repogent' in comment_body.lower():
            return 'community_assistant'
        
        # Otherwise, route to issue manager for response
        return 'issue_manager'
    
    def send_message(self, sender: str, receiver: str, message_type: str, payload: Dict[str, Any]):
        """Send message from one agent to another"""
        try:
            message = Message(sender, receiver, message_type, payload)
            self.message_queue.enqueue(message)
            print(f"📨 Message queued: {sender} → {receiver} ({message_type})", file=sys.stderr)
        except ValueError as e:
            print(f"❌ Failed to send message: {e}", file=sys.stderr)
    
    def receive_messages(self, agent_name: str) -> List[Message]:
        """Receive all pending messages for an agent"""
        messages = []
        while True:
            message = self.message_queue.dequeue(agent_name)
            if message is None:
                break
            messages.append(message)
        return messages
    
    def handle_agent_communication(self, message: Message):
        """Process inter-agent communication"""
        receiver = message.receiver
        
        if receiver == 'orchestrator':
            # Handle messages to orchestrator
            self._handle_orchestrator_message(message)
        else:
            # Forward to target agent
            print(f"🔄 Forwarding message to {receiver}", file=sys.stderr)
    
    def _handle_orchestrator_message(self, message: Message):
        """Handle messages directed to orchestrator"""
        msg_type = message.message_type
        payload = message.payload
        
        if msg_type == 'build_failure':
            self._handle_build_failure(payload)
        elif msg_type == 'request_context':
            self._handle_context_request(message)
        elif msg_type == 'log_decision':
            self._log_agent_decision(message)
    
    def _handle_build_failure(self, payload: Dict[str, Any]):
        """Handle build failure from CI/CD agent"""
        pr_number = payload.get('pr_number')
        
        # Only save context if we have a valid PR number
        if pr_number is not None:
            # Save context
            self.context_store.save_pr_context(pr_number, {
                'build_status': 'failed',
                'failure_details': payload,
                'timestamp': datetime.now().isoformat()
            })
            
            # Send to PR Reviewer for analysis
            self.send_message(
                sender='orchestrator',
                receiver='pr_reviewer',
                message_type='analyze_build_failure',
                payload=payload
            )
        else:
            print(f"⚠️ Build failure has no associated PR, skipping context save", file=sys.stderr)
    
    def _handle_context_request(self, message: Message):
        """Respond to context requests from agents"""
        context_id = message.payload.get('context_id')
        context_data = self.context_store.load_context(context_id)
        
        # Send back to requester
        self.send_message(
            sender='orchestrator',
            receiver=message.sender,
            message_type='context_response',
            payload={'context': context_data}
        )
    
    def _log_agent_decision(self, message: Message):
        """Log agent decisions for learning"""
        log_path = Path('.repogent/logs')
        log_path.mkdir(parents=True, exist_ok=True)
        
        log_file = log_path / f"decisions_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'agent': message.sender,
                'decision': message.payload
            }) + '\n')
    
    def post_github_comment(self, issue_number: int, body: str):
        """Post comment to GitHub issue/PR"""
        # Validate issue_number
        if not isinstance(issue_number, int) or issue_number <= 0:
            print(f"⚠️ Invalid issue number: {issue_number}", file=sys.stderr)
            return False
        if not self.github_token or not self.repo:
            print("⚠️ Missing GitHub credentials", file=sys.stderr)
            return False
        
        url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}/comments"
        headers = {
            'Authorization': f'Bearer {self.github_token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Repogent-Orchestrator/1.0'
        }
        
        try:
            response = requests.post(url, headers=headers, json={'body': body}, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return True
        except requests.exceptions.Timeout:
            print(f"❌ Timeout posting comment (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to post comment: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"❌ Unexpected error posting comment: {e}", file=sys.stderr)
            return False
    
    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get information about an agent"""
        return AGENTS.get(agent_name)
    
    def list_agents(self) -> List[str]:
        """List all registered agents"""
        return list(AGENTS.keys())


def main():
    """Main orchestrator entry point"""
    orchestrator = Orchestrator()
    
    # Get event type from environment
    event_type = os.environ.get('GITHUB_EVENT_NAME', '')
    event_path = os.environ.get('GITHUB_EVENT_PATH', '')
    
    if not event_type:
        print("❌ No event type provided", file=sys.stderr)
        sys.exit(1)
    
    # Load event data with validation
    event_data = {}
    if event_path:
        # Resolve and validate path
        try:
            event_path_obj = Path(event_path).resolve()
            if event_path_obj.exists():
                with open(event_path_obj, 'r', encoding='utf-8') as f:
                    event_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load event data: {e}", file=sys.stderr)
    
    print(f"🎭 Orchestrator processing: {event_type}", file=sys.stderr)
    
    # Route event to appropriate agent
    target_agent = orchestrator.route_event(event_type, event_data)
    print(f"🎯 Routing to: {target_agent}", file=sys.stderr)
    
    # Check for pending messages
    messages = orchestrator.receive_messages('orchestrator')
    for message in messages:
        orchestrator.handle_agent_communication(message)
    
    print(f"✅ Orchestrator processed {len(messages)} messages", file=sys.stderr)


if __name__ == '__main__':
    main()
