"""
Test script for Sanctions Screening API
Run this after starting the API to verify everything works
"""
import requests
import json
import time
from typing import Dict, Any


API_BASE_URL = "http://localhost:8080"


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    print(f"{symbol} {test_name}: {status}")
    if details:
        print(f"  {details}")


def test_health_check() -> bool:
    """Test health check endpoint"""
    print_header("Test 1: Health Check")
    
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        data = response.json()
        
        passed = (
            response.status_code == 200 and
            data.get("status") in ["healthy", "degraded"] and
            data.get("yente_status") is not None
        )
        
        print(f"Response: {json.dumps(data, indent=2)}")
        print_result("Health Check", passed, f"Status: {data.get('status')}")
        
        return passed
    
    except Exception as e:
        print_result("Health Check", False, f"Error: {str(e)}")
        return False


def test_clear_case() -> bool:
    """Test screening a clean person (should return clear)"""
    print_header("Test 2: Clear Decision (Clean Person)")
    
    payload = {
        "full_name": "Jane Elizabeth Smith",
        "country": "US",
        "date_of_birth": "1990-05-15"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/sanctions/screen/person",
            json=payload,
            timeout=15
        )
        
        data = response.json()
        
        passed = (
            response.status_code == 200 and
            data.get("decision") == "clear"
        )
        
        print(f"Request: {json.dumps(payload, indent=2)}")
        print(f"\nResponse Summary:")
        print(f"  Decision: {data.get('decision')}")
        print(f"  Risk Level: {data.get('risk_level')}")
        print(f"  Top Score: {data.get('top_score')}")
        print(f"  Matches Found: {len(data.get('matches', []))}")
        
        print_result("Clear Decision", passed)
        
        return passed
    
    except Exception as e:
        print_result("Clear Decision", False, f"Error: {str(e)}")
        return False


def test_block_case() -> bool:
    """Test screening a known sanctioned person (should return block)"""
    print_header("Test 3: Block Decision (Known Sanctions Target)")
    
    payload = {
        "full_name": "Hassan Nasrallah",
        "country": "LB",
        "date_of_birth": "1960-08-31",
        "user_id": "test_user_001",
        "transaction_context": "withdrawal"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/sanctions/screen/person",
            json=payload,
            timeout=15
        )
        
        data = response.json()
        
        # Should have high score and block/review decision
        passed = (
            response.status_code == 200 and
            data.get("decision") in ["block", "review"] and
            data.get("top_score", 0) > 0.70
        )
        
        print(f"Request: {json.dumps(payload, indent=2)}")
        print(f"\nResponse Summary:")
        print(f"  Decision: {data.get('decision')}")
        print(f"  Risk Level: {data.get('risk_level')}")
        print(f"  Top Score: {data.get('top_score')}")
        print(f"  Matches Found: {len(data.get('matches', []))}")
        
        if data.get('matches'):
            top_match = data['matches'][0]
            print(f"\nTop Match:")
            print(f"  Entity: {top_match.get('caption')}")
            print(f"  Dataset: {top_match.get('dataset')}")
            print(f"  Score: {top_match.get('score')}")
            print(f"  Programs: {', '.join(top_match.get('programs', []))}")
        
        print(f"\nReasons:")
        for reason in data.get('reasons', [])[:3]:
            print(f"  - {reason}")
        
        print_result("Block Decision", passed, 
                    f"Expected block/review with high score, got: {data.get('decision')}")
        
        return passed
    
    except Exception as e:
        print_result("Block Decision", False, f"Error: {str(e)}")
        return False


def test_minimal_request() -> bool:
    """Test with minimal data (name only)"""
    print_header("Test 4: Minimal Request (Name Only)")
    
    payload = {
        "full_name": "John Doe"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/sanctions/screen/person",
            json=payload,
            timeout=15
        )
        
        data = response.json()
        
        passed = response.status_code == 200
        
        print(f"Request: {json.dumps(payload, indent=2)}")
        print(f"\nResponse Summary:")
        print(f"  Decision: {data.get('decision')}")
        print(f"  Top Score: {data.get('top_score')}")
        print(f"  Matches Found: {len(data.get('matches', []))}")
        
        print_result("Minimal Request", passed)
        
        return passed
    
    except Exception as e:
        print_result("Minimal Request", False, f"Error: {str(e)}")
        return False


def test_request_id_tracking() -> bool:
    """Test that request IDs are properly generated and returned"""
    print_header("Test 5: Request ID Tracking")
    
    custom_request_id = "test_request_12345"
    
    payload = {
        "full_name": "Test Person",
        "request_id": custom_request_id
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/sanctions/screen/person",
            json=payload,
            timeout=15
        )
        
        data = response.json()
        
        passed = (
            response.status_code == 200 and
            data.get("request_id") == custom_request_id
        )
        
        print(f"Custom Request ID: {custom_request_id}")
        print(f"Returned Request ID: {data.get('request_id')}")
        
        print_result("Request ID Tracking", passed)
        
        return passed
    
    except Exception as e:
        print_result("Request ID Tracking", False, f"Error: {str(e)}")
        return False


def test_performance() -> bool:
    """Test API response time"""
    print_header("Test 6: Performance Check")
    
    payload = {
        "full_name": "Performance Test User",
        "country": "US"
    }
    
    try:
        start_time = time.time()
        
        response = requests.post(
            f"{API_BASE_URL}/v1/sanctions/screen/person",
            json=payload,
            timeout=15
        )
        
        elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
        
        data = response.json()
        
        # Should complete in under 5 seconds for single request
        passed = (
            response.status_code == 200 and
            elapsed_time < 5000
        )
        
        print(f"Response Time: {elapsed_time:.2f} ms")
        print(f"Datasets Checked: {', '.join(data.get('datasets_checked', []))}")
        
        print_result("Performance Check", passed, 
                    f"Target: <5000ms, Actual: {elapsed_time:.2f}ms")
        
        return passed
    
    except Exception as e:
        print_result("Performance Check", False, f"Error: {str(e)}")
        return False


def run_all_tests():
    """Run all tests and print summary"""
    print_header("SANCTIONS SCREENING API TEST SUITE")
    print("Testing API at:", API_BASE_URL)
    print("Make sure the API is running: python main.py")
    
    input("\nPress Enter to start tests...")
    
    # Run all tests
    results = []
    
    results.append(("Health Check", test_health_check()))
    time.sleep(1)
    
    results.append(("Clear Decision", test_clear_case()))
    time.sleep(1)
    
    results.append(("Block Decision", test_block_case()))
    time.sleep(1)
    
    results.append(("Minimal Request", test_minimal_request()))
    time.sleep(1)
    
    results.append(("Request ID Tracking", test_request_id_tracking()))
    time.sleep(1)
    
    results.append(("Performance Check", test_performance()))
    
    # Print summary
    print_header("TEST SUMMARY")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        symbol = "✓" if passed else "✗"
        status = "PASS" if passed else "FAIL"
        print(f"{symbol} {test_name}: {status}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All tests passed! API is working correctly.")
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Check the output above.")
    
    print("\nNext steps:")
    print("1. Check audit logs: C:\\SANCTIONS-CHECK\\logs\\api\\audit\\")
    print("2. View interactive docs: http://localhost:8080/docs")
    print("3. Integrate with your betting backend")


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")