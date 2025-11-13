#!/usr/bin/env python3
"""
Agent Communication Helper
Shared utilities for agent-to-agent communication via orchestrator.
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Lazy imports to avoid circular dependency
_orchestrator_instance = None


def _get_orchestrator():
    """Get or create singleton orchestrator instance"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        # Import here to avoid circular dependency
        from orchestrator import Orchestrator
        _orchestrator_instance = Orchestrator()
    return _orchestrator_instance


def send_message(sender: str, receiver: str, message_type: str, payload: Dict[str, Any]):
    """Send message to another agent via orchestrator"""
    from orchestrator import Message
    orchestrator = _get_orchestrator()
    message = Message(sender, receiver, message_type, payload)
    orchestrator.message_queue.enqueue(message)


def receive_messages(agent_name: str) -> List['Message']:
    """Receive all pending messages for this agent"""
    orchestrator = _get_orchestrator()
    return orchestrator.receive_messages(agent_name)


def get_context(context_id: str) -> Optional[Dict[str, Any]]:
    """Request context from orchestrator"""
    orchestrator = _get_orchestrator()
    return orchestrator.context_store.load_context(context_id)


def save_context(context_id: str, data: Dict[str, Any]):
    """Save context via orchestrator"""
    orchestrator = _get_orchestrator()
    orchestrator.context_store.save_context(context_id, data)


def log_decision(agent_name: str, decision: Dict[str, Any]):
    """Log agent decision to orchestrator"""
    send_message(
        sender=agent_name,
        receiver='orchestrator',
        message_type='log_decision',
        payload=decision
    )
