#!/usr/bin/env python3
"""
Multi-Agent System Test Suite
Validates orchestrator, agents, and communication protocol.
"""
import sys
import json
from pathlib import Path

print("🧪 MULTI-AGENT SYSTEM TEST SUITE")
print("=" * 60)

# Test 1: Import all modules
print("\n✅ TEST 1: Module Imports")
try:
    sys.path.insert(0, 'scripts')
    from orchestrator import Orchestrator, Message, ContextStore, MessageQueue
    from cicd_agent import CICDAgent, BuildLogAnalyzer
    import agent_comms
    import pr_reviewer_enhanced
    print("  ✓ All modules imported successfully")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Message Creation and Serialization
print("\n✅ TEST 2: Message System")
try:
    msg = Message(
        sender='test_agent',
        receiver='orchestrator',
        message_type='test_message',
        payload={'key': 'value'}
    )
    msg_dict = msg.to_dict()
    msg_restored = Message.from_dict(msg_dict)
    
    assert msg_restored.sender == 'test_agent'
    assert msg_restored.receiver == 'orchestrator'
    assert msg_restored.payload['key'] == 'value'
    print("  ✓ Message serialization works")
except Exception as e:
    print(f"  ✗ Message test failed: {e}")
    sys.exit(1)

# Test 3: Context Store
print("\n✅ TEST 3: Context Store")
try:
    store = ContextStore('.test_repogent/context')
    store.save_context('test_pr_1', {'status': 'reviewed', 'score': 95})
    loaded = store.load_context('test_pr_1')
    
    assert loaded['data']['status'] == 'reviewed'
    assert loaded['data']['score'] == 95
    print("  ✓ Context storage works")
    
    # Cleanup
    import shutil
    from pathlib import Path
    test_dir = Path('.test_repogent')
    if test_dir.exists():
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            print(f"  ⚠️ Cleanup warning: {e}", file=sys.stderr)
except Exception as e:
    print(f"  ✗ Context store test failed: {e}")
    sys.exit(1)

# Test 4: Message Queue
print("\n✅ TEST 4: Message Queue")
try:
    queue = MessageQueue('.test_repogent/queue')
    
    # Enqueue messages
    msg1 = Message('agent1', 'agent2', 'type1', {'data': 1})
    msg2 = Message('agent1', 'agent3', 'type2', {'data': 2})
    queue.enqueue(msg1)
    queue.enqueue(msg2)
    
    # Dequeue for specific receiver
    received = queue.dequeue('agent2')
    assert received is not None
    assert received.payload['data'] == 1
    
    # Check remaining
    remaining = queue.peek_all()
    assert len(remaining) == 1
    print("  ✓ Message queue works")
    
    # Cleanup
    import shutil
    from pathlib import Path
    test_dir = Path('.test_repogent')
    if test_dir.exists():
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            print(f"  ⚠️ Cleanup warning: {e}", file=sys.stderr)
except Exception as e:
    print(f"  ✗ Message queue test failed: {e}")
    sys.exit(1)

# Test 5: Build Log Analyzer
print("\n✅ TEST 5: Build Log Analyzer")
try:
    analyzer = BuildLogAnalyzer()
    
    # Test with sample logs
    test_logs = """
    Running tests...
    FAIL src/auth.test.js
      ● Authentication › should validate token
        Expected status 200, got 401
    Tests failed
    """
    
    analysis = analyzer.analyze(test_logs)
    
    assert analysis['failure_type'] == 'test_failure'
    assert len(analysis['suggestions']) > 0
    assert analysis['severity'] in ['CRITICAL', 'HIGH', 'MEDIUM']
    print(f"  ✓ Build log analysis works (detected: {analysis['failure_type']})")
except Exception as e:
    print(f"  ✗ Build log analyzer test failed: {e}")
    sys.exit(1)

# Test 6: Event Routing
print("\n✅ TEST 6: Event Routing")
try:
    orchestrator = Orchestrator()
    
    # Test different event types
    assert orchestrator.route_event('pull_request', {}) == 'pr_reviewer'
    assert orchestrator.route_event('issues', {}) == 'issue_manager'
    assert orchestrator.route_event('workflow_run', {}) == 'cicd_agent'
    
    # Test comment routing with @repogent
    event_data = {'comment': {'body': '@repogent how does this work?'}}
    assert orchestrator.route_event('issue_comment', event_data) == 'community_assistant'
    
    print("  ✓ Event routing works correctly")
except Exception as e:
    print(f"  ✗ Event routing test failed: {e}")
    sys.exit(1)

# Test 7: Agent Registry
print("\n✅ TEST 7: Agent Registry")
try:
    orchestrator = Orchestrator()
    
    agents = orchestrator.list_agents()
    assert 'pr_reviewer' in agents
    assert 'issue_manager' in agents
    assert 'community_assistant' in agents
    assert 'cicd_agent' in agents
    
    agent_info = orchestrator.get_agent_info('cicd_agent')
    assert agent_info is not None
    assert 'build_monitoring' in agent_info['capabilities']
    
    print(f"  ✓ Agent registry works ({len(agents)} agents registered)")
except Exception as e:
    print(f"  ✗ Agent registry test failed: {e}")
    sys.exit(1)

# Test 8: Error Pattern Detection
print("\n✅ TEST 8: Error Pattern Detection")
try:
    analyzer = BuildLogAnalyzer()
    
    test_cases = [
        ("Cannot find module 'axios'", 'dependency_error'),
        ("SyntaxError: Unexpected token", 'compile_error'),
        ("JavaScript heap out of memory", 'memory_error'),
        ("docker: Error response from daemon", 'docker_error'),
    ]
    
    for log_snippet, expected_type in test_cases:
        detected = analyzer._detect_failure_type(log_snippet)
        assert detected == expected_type, f"Expected {expected_type}, got {detected}"
    
    print(f"  ✓ Error pattern detection works ({len(test_cases)} patterns tested)")
except Exception as e:
    print(f"  ✗ Error pattern detection test failed: {e}")
    sys.exit(1)

# Test 9: Agent Communication Helpers
print("\n✅ TEST 9: Agent Communication Helpers")
try:
    # Test message sending (creates queue)
    agent_comms.send_message('test_agent', 'orchestrator', 'test', {'data': 'test'})
    
    # Test message receiving
    messages = agent_comms.receive_messages('orchestrator')
    assert len(messages) >= 1
    assert messages[0].sender == 'test_agent'
    
    print("  ✓ Agent communication helpers work")
    
    # Cleanup - use correct test directory
    import shutil
    from pathlib import Path
    test_dir = Path('.repogent')  # Actual queue directory used by agent_comms
    if test_dir.exists():
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            print(f"  ⚠️ Cleanup warning: {e}", file=sys.stderr)
except Exception as e:
    print(f"  ✗ Agent communication test failed: {e}")
    sys.exit(1)

# Final Summary
print("\n" + "=" * 60)
print("✅ ALL 9 TESTS PASSED!")
print("=" * 60)
print("\n🎉 Multi-Agent System is fully functional!")
print("\nValidated:")
print("  • Orchestrator core functionality")
print("  • Message queue and serialization")
print("  • Context storage and retrieval")
print("  • CI/CD agent log analysis")
print("  • Event routing logic")
print("  • Agent registry")
print("  • Error pattern detection")
print("  • Inter-agent communication")
print("  • All module imports")
print("\n✅ Ready for deployment!")
