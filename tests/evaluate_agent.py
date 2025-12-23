#!/usr/bin/env python
"""
RAG Evaluation Framework for Safety Agent
==========================================

This script evaluates the quality of the RAG agent's responses.
Run: python tests/evaluate_agent.py

Metrics:
- Topic Coverage: Does the answer mention expected key topics?
- Response Quality: Is the response well-structured and relevant?
- Dynamic Retrieval: Does the agent use more context for summaries?

Usage:
    # Run all tests
    python tests/evaluate_agent.py

    # Run with verbose output
    python tests/evaluate_agent.py --verbose

    # Run specific test
    python tests/evaluate_agent.py --test 1
"""
import os
import sys
import json
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Safety_agent_Django.settings')

import django
django.setup()

from chatlog.langgraph_agent import construct_agent_graph, is_summary_request
from langchain_core.messages import HumanMessage


# ===================================
# EVALUATION DATASET
# ===================================

EVAL_DATA = [
    {
        "id": 1,
        "question": "What PPE is required for underground mining?",
        "expected_topics": ["hard hat", "helmet", "safety glasses", "boots", "vest", "gloves"],
        "category": "PPE",
        "is_summary": False
    },
    {
        "id": 2,
        "question": "What are the MSHA requirements for mine inspections?",
        "expected_topics": ["inspection", "cfr", "msha", "quarterly", "hazard", "compliance"],
        "category": "Regulations",
        "is_summary": False
    },
    {
        "id": 3,
        "question": "Give me a summary of all fire safety procedures",
        "expected_topics": ["fire", "evacuation", "extinguisher", "alarm", "emergency", "escape"],
        "category": "Fire Safety",
        "is_summary": True
    },
    {
        "id": 4,
        "question": "What are the ventilation requirements in underground mines?",
        "expected_topics": ["ventilation", "air", "methane", "cfr", "oxygen", "dust"],
        "category": "Ventilation",
        "is_summary": False
    },
    {
        "id": 5,
        "question": "Summarize the key points about electrical safety in mining",
        "expected_topics": ["electrical", "grounding", "lockout", "tagout", "shock", "cable"],
        "category": "Electrical Safety",
        "is_summary": True
    },
    {
        "id": 6,
        "question": "What should I do in case of a roof fall emergency?",
        "expected_topics": ["roof", "fall", "emergency", "evacuate", "rescue", "support"],
        "category": "Emergency Response",
        "is_summary": False
    },
    {
        "id": 7,
        "question": "Provide an overview of training requirements for new miners",
        "expected_topics": ["training", "hours", "certification", "annual", "refresher", "msha"],
        "category": "Training",
        "is_summary": True
    },
]


# ===================================
# EVALUATION FUNCTIONS
# ===================================

def calculate_topic_coverage(answer: str, expected_topics: list) -> tuple:
    """
    Calculate what percentage of expected topics are mentioned in the answer.
    Returns (coverage_score, found_topics, missing_topics)
    """
    answer_lower = answer.lower()
    found_topics = []
    missing_topics = []

    for topic in expected_topics:
        if topic.lower() in answer_lower:
            found_topics.append(topic)
        else:
            missing_topics.append(topic)

    coverage = len(found_topics) / len(expected_topics) if expected_topics else 0
    return coverage, found_topics, missing_topics


def evaluate_response_quality(answer: str) -> dict:
    """
    Evaluate response quality based on structure and content.
    """
    quality = {
        "has_structure": False,
        "has_citations": False,
        "has_action_items": False,
        "appropriate_length": False,
        "score": 0.0
    }

    # Check for structured formatting
    if any(marker in answer for marker in ["##", "**", "1.", "- ", "* "]):
        quality["has_structure"] = True
        quality["score"] += 0.25

    # Check for regulation citations
    if any(marker in answer.upper() for marker in ["CFR", "MSHA", "OSHA", "30 CFR"]):
        quality["has_citations"] = True
        quality["score"] += 0.25

    # Check for action items or recommendations
    if any(marker in answer.lower() for marker in ["recommend", "action", "should", "must", "required"]):
        quality["has_action_items"] = True
        quality["score"] += 0.25

    # Check for appropriate length (not too short, not too long)
    word_count = len(answer.split())
    if 50 <= word_count <= 1500:
        quality["appropriate_length"] = True
        quality["score"] += 0.25

    return quality


def test_intent_detection():
    """Test the is_summary_request function."""
    print("\n" + "=" * 50)
    print("TESTING INTENT DETECTION")
    print("=" * 50)

    test_cases = [
        ("What is PPE?", False),
        ("Give me a summary", True),
        ("Summarize the documents", True),
        ("What are the key points?", True),
        ("Explain the regulation", False),
        ("Provide an overview", True),
        ("Tell me about fire safety", False),
        ("Tell me about all safety procedures", True),
    ]

    passed = 0
    for query, expected in test_cases:
        result = is_summary_request(query)
        status = "PASS" if result == expected else "FAIL"
        if result == expected:
            passed += 1
        print(f"  [{status}] '{query[:40]}...' -> {result} (expected: {expected})")

    print(f"\nIntent Detection: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def run_evaluation(collection_name: str = "test_evaluation_kb", verbose: bool = False, test_id: int = None):
    """
    Run the full evaluation suite.
    """
    print("\n" + "=" * 60)
    print("RAG EVALUATION FRAMEWORK - Safety Agent")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Collection: {collection_name}")

    # Test intent detection first
    intent_passed = test_intent_detection()

    # Initialize agent
    print("\n" + "=" * 50)
    print("INITIALIZING AGENT")
    print("=" * 50)

    try:
        agent = construct_agent_graph(collection_name)
        print("Agent initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize agent: {e}")
        return None

    # Run evaluations
    print("\n" + "=" * 50)
    print("RUNNING EVALUATIONS")
    print("=" * 50)

    results = []
    test_data = EVAL_DATA if test_id is None else [t for t in EVAL_DATA if t["id"] == test_id]

    for test_case in test_data:
        print(f"\n[Test {test_case['id']}] {test_case['category']}")
        print(f"  Question: {test_case['question'][:60]}...")
        print(f"  Expected summary request: {test_case['is_summary']}")

        try:
            # Invoke agent
            response = agent.invoke({
                "messages": [HumanMessage(content=test_case['question'])]
            })
            answer = response["messages"][-1].content

            # Calculate metrics
            coverage, found, missing = calculate_topic_coverage(
                answer, test_case['expected_topics']
            )
            quality = evaluate_response_quality(answer)

            # Combined score
            combined_score = (coverage * 0.6) + (quality["score"] * 0.4)
            passed = combined_score >= 0.5

            result = {
                "test_id": test_case['id'],
                "category": test_case['category'],
                "question": test_case['question'],
                "coverage_score": coverage,
                "topics_found": found,
                "topics_missing": missing,
                "quality": quality,
                "combined_score": combined_score,
                "passed": passed
            }
            results.append(result)

            # Print results
            status = "PASS" if passed else "FAIL"
            print(f"  Result: [{status}]")
            print(f"    Topic Coverage: {coverage*100:.0f}% ({len(found)}/{len(test_case['expected_topics'])})")
            print(f"    Quality Score: {quality['score']*100:.0f}%")
            print(f"    Combined Score: {combined_score*100:.0f}%")

            if verbose:
                print(f"    Found: {found}")
                print(f"    Missing: {missing}")
                print(f"    Answer preview: {answer[:200]}...")

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "test_id": test_case['id'],
                "category": test_case['category'],
                "error": str(e),
                "passed": False
            })

    # Summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.get('passed', False))
    avg_coverage = sum(r.get('coverage_score', 0) for r in results) / total_tests if total_tests > 0 else 0
    avg_quality = sum(r.get('quality', {}).get('score', 0) for r in results) / total_tests if total_tests > 0 else 0

    print(f"Tests Passed: {passed_tests}/{total_tests}")
    print(f"Average Topic Coverage: {avg_coverage*100:.1f}%")
    print(f"Average Quality Score: {avg_quality*100:.1f}%")
    print(f"Intent Detection: {'PASS' if intent_passed else 'FAIL'}")

    overall_pass = passed_tests >= (total_tests * 0.7) and intent_passed
    print(f"\nOVERALL: {'PASS' if overall_pass else 'FAIL'}")

    return {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "avg_coverage": avg_coverage,
        "avg_quality": avg_quality,
        "intent_detection_passed": intent_passed,
        "overall_passed": overall_pass,
        "results": results
    }


# ===================================
# MAIN
# ===================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG Evaluation Framework")
    parser.add_argument("--collection", default="test_evaluation_kb",
                        help="Vector store collection to use")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--test", type=int,
                        help="Run specific test by ID")
    parser.add_argument("--output", "-o",
                        help="Save results to JSON file")

    args = parser.parse_args()

    results = run_evaluation(
        collection_name=args.collection,
        verbose=args.verbose,
        test_id=args.test
    )

    if args.output and results:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")

    # Exit with appropriate code
    if results and results.get('overall_passed'):
        sys.exit(0)
    else:
        sys.exit(1)
