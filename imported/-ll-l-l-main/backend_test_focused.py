#!/usr/bin/env python3
"""
Focused Backend Testing Suite for Workers System
Tests specific requirements from the review request
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import aiohttp
import sys

# Test configuration - using localhost as specified in review request
BASE_URL = "http://127.0.0.1:8001"
API_BASE_URL = f"{BASE_URL}/api"

class FocusedBackendTester:
    def __init__(self):
        self.session = None
        self.test_results = []
        self.client_user_id = None
        self.created_task_id = None
        
    async def setup(self):
        """Initialize test session"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        print("🔧 Test session initialized")
        
    async def cleanup(self):
        """Cleanup test session"""
        if self.session:
            await self.session.close()
        print("🧹 Test session cleaned up")
        
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        print(f"{status} {test_name}: {details}")
        return success
        
    async def test_1_backend_health(self):
        """1) Verify backend health: GET /api/health returns 200, ok:true, db_connected:true"""
        try:
            async with self.session.get(f"{API_BASE_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok") is True and data.get("db_connected") is True:
                        return self.log_result("1. Backend Health", True, "API healthy, MongoDB connected")
                    else:
                        return self.log_result("1. Backend Health", False, f"API response: {data}")
                else:
                    return self.log_result("1. Backend Health", False, f"HTTP {response.status}")
        except Exception as e:
            return self.log_result("1. Backend Health", False, f"Connection error: {str(e)}")
            
    async def test_2_html_pages(self):
        """2) Verify pages load valid HTML"""
        pages = [
            ("/", "Dashboard"),
            ("/orders", "Orders"),
            ("/users", "Users"),
            ("/moderation", "Moderation"),
            ("/settings", "Settings"),
            ("/webapp?user_id=test123&tab=tasks", "WebApp")
        ]
        
        all_passed = True
        results = []
        
        for path, name in pages:
            try:
                async with self.session.get(f"{BASE_URL}{path}") as response:
                    if response.status == 200:
                        content = await response.text()
                        if "<!DOCTYPE html>" in content or "<html" in content:
                            results.append(f"{name}: ✅")
                        else:
                            results.append(f"{name}: ❌ (not HTML)")
                            all_passed = False
                    else:
                        results.append(f"{name}: ❌ (HTTP {response.status})")
                        all_passed = False
            except Exception as e:
                results.append(f"{name}: ❌ ({str(e)})")
                all_passed = False
                
        return self.log_result("2. HTML Pages", all_passed, "; ".join(results))
        
    async def test_3_api_data_endpoints(self):
        """3) Verify API data endpoints: GET /api/users and /api/tasks return arrays with length > 0"""
        users_ok = False
        tasks_ok = False
        
        # Test users endpoint
        try:
            async with self.session.get(f"{API_BASE_URL}/users") as response:
                if response.status == 200:
                    users = await response.json()
                    if isinstance(users, list) and len(users) > 0:
                        users_ok = True
                        # Find a client for later tests
                        for user in users:
                            if user.get("role") == "client":
                                self.client_user_id = user.get("id")
                                break
        except Exception as e:
            pass
            
        # Test tasks endpoint
        try:
            async with self.session.get(f"{API_BASE_URL}/tasks") as response:
                if response.status == 200:
                    tasks = await response.json()
                    if isinstance(tasks, list) and len(tasks) > 0:
                        tasks_ok = True
        except Exception as e:
            pass
            
        success = users_ok and tasks_ok
        details = f"Users: {'✅' if users_ok else '❌'}, Tasks: {'✅' if tasks_ok else '❌'}"
        if self.client_user_id:
            details += f", Found client_id: {self.client_user_id}"
            
        return self.log_result("3. API Data Endpoints", success, details)
        
    async def test_4_create_task(self):
        """4) Create a new task via API"""
        if not self.client_user_id:
            return self.log_result("4. Create Task", False, "No client_id available from previous test")
            
        # Create task payload as specified in review request
        task_data = {
            "title": "Test Task Creation",
            "description": "Test task for backend testing",
            "task_type": "loading",
            "requirements": [{"worker_type": "loader", "count": 1}],
            "location": "Moscow, Test Location",
            "start_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "duration_hours": 8,
            "client_price": 4000,
            "verified_only": False,
            "client_id": self.client_user_id
        }
        
        try:
            async with self.session.post(f"{API_BASE_URL}/tasks", json=task_data) as response:
                if response.status == 200:
                    created_task = await response.json()
                    if created_task.get("status") == "pending":
                        self.created_task_id = created_task.get("id")
                        
                        # Verify task appears in pending list
                        async with self.session.get(f"{API_BASE_URL}/tasks?status=pending") as list_response:
                            if list_response.status == 200:
                                pending_tasks = await list_response.json()
                                task_found = any(task.get("id") == self.created_task_id for task in pending_tasks)
                                if task_found:
                                    return self.log_result("4. Create Task", True, 
                                                         f"Task created with ID {self.created_task_id}, status=pending, found in pending list")
                                else:
                                    return self.log_result("4. Create Task", False, 
                                                         "Task created but not found in pending list")
                            else:
                                return self.log_result("4. Create Task", False, 
                                                     f"Task created but failed to verify in pending list (HTTP {list_response.status})")
                    else:
                        return self.log_result("4. Create Task", False, 
                                             f"Task created but status is {created_task.get('status')}, expected 'pending'")
                else:
                    return self.log_result("4. Create Task", False, f"HTTP {response.status}")
        except Exception as e:
            return self.log_result("4. Create Task", False, f"Error: {str(e)}")
            
    async def test_5_moderation_patch_flow(self):
        """5) Moderation patch flow: PATCH task to approved status"""
        if not self.created_task_id:
            return self.log_result("5. Moderation Flow", False, "No task_id available from previous test")
            
        # PATCH task to approved with worker_price and moderation_notes
        patch_data = {
            "status": "approved",
            "worker_price": 3200,
            "moderation_notes": "ok"
        }
        
        try:
            async with self.session.patch(f"{API_BASE_URL}/tasks/{self.created_task_id}", json=patch_data) as response:
                if response.status == 200:
                    updated_task = await response.json()
                    
                    # Verify the task was updated correctly
                    if (updated_task.get("status") == "approved" and 
                        updated_task.get("worker_price") == 3200):
                        
                        # Verify GET /moderation no longer lists it as pending
                        async with self.session.get(f"{BASE_URL}/moderation") as mod_response:
                            if mod_response.status == 200:
                                mod_content = await mod_response.text()
                                # Check if our task ID is not in the moderation page
                                task_not_in_moderation = self.created_task_id not in mod_content
                                
                                # Verify GET /api/tasks/{id} reflects updated fields
                                async with self.session.get(f"{API_BASE_URL}/tasks/{self.created_task_id}") as get_response:
                                    if get_response.status == 200:
                                        final_task = await get_response.json()
                                        if (final_task.get("status") == "approved" and 
                                            final_task.get("worker_price") == 3200):
                                            return self.log_result("5. Moderation Flow", True, 
                                                                 f"Task approved, worker_price=3200, not in moderation page: {task_not_in_moderation}")
                                        else:
                                            return self.log_result("5. Moderation Flow", False, 
                                                                 f"Task fields not updated correctly: {final_task}")
                                    else:
                                        return self.log_result("5. Moderation Flow", False, 
                                                             f"Failed to get updated task (HTTP {get_response.status})")
                            else:
                                return self.log_result("5. Moderation Flow", False, 
                                                     f"Failed to check moderation page (HTTP {mod_response.status})")
                    else:
                        return self.log_result("5. Moderation Flow", False, 
                                             f"Task not updated correctly: {updated_task}")
                else:
                    return self.log_result("5. Moderation Flow", False, f"PATCH failed with HTTP {response.status}")
        except Exception as e:
            return self.log_result("5. Moderation Flow", False, f"Error: {str(e)}")
            
    async def run_focused_tests(self):
        """Run all focused tests in order"""
        print("🚀 Starting Focused Backend Testing Suite")
        print("Testing specific requirements from review request")
        print("=" * 60)
        
        await self.setup()
        
        # Test sequence as specified in review request
        tests = [
            self.test_1_backend_health,
            self.test_2_html_pages,
            self.test_3_api_data_endpoints,
            self.test_4_create_task,
            self.test_5_moderation_patch_flow,
        ]
        
        passed = 0
        total = len(tests)
        
        for i, test_func in enumerate(tests, 1):
            print(f"\n🧪 Running Test {i}/{total}")
            try:
                success = await test_func()
                if success:
                    passed += 1
            except Exception as e:
                self.log_result(f"Test {i}", False, f"Unexpected error: {str(e)}")
                
        await self.cleanup()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 FOCUSED TEST SUMMARY")
        print("=" * 60)
        
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']}: {result['details']}")
            
        print(f"\n🎯 Overall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All focused tests PASSED! Backend meets requirements.")
            return True
        else:
            print(f"⚠️  {total - passed} tests FAILED. Check details above.")
            return False

async def main():
    """Main test runner"""
    tester = FocusedBackendTester()
    success = await tester.run_focused_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())