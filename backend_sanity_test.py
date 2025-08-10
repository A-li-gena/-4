#!/usr/bin/env python3
"""
Backend E2E Sanity Testing for FastAPI service
Tests the exact requirements from the review request
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
import aiohttp

# Test configuration - using localhost as specified in review request
BASE_URL = "http://localhost:8001"
API_BASE_URL = f"{BASE_URL}/api"

class BackendSanityTester:
    def __init__(self):
        self.session = None
        self.test_results = []
        self.test_task_id = None
        
    async def setup(self):
        """Initialize test session"""
        self.session = aiohttp.ClientSession()
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
        
    async def test_health_endpoint(self):
        """1) Health - GET /api/health => expect 200, json.ok==true, json.storage.using=="json" """
        try:
            async with self.session.get(f"{API_BASE_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Check required fields from review request
                    if (data.get("ok") == True and 
                        data.get("storage", {}).get("using") == "json"):
                        return self.log_result("Health Check", True, 
                                      f"OK: {data.get('ok')}, Storage: {data.get('storage', {}).get('using')}")
                    else:
                        return self.log_result("Health Check", False, 
                                      f"Expected ok=true and storage.using='json', got: {data}")
                else:
                    return self.log_result("Health Check", False, f"HTTP {response.status}")
        except Exception as e:
            return self.log_result("Health Check", False, f"Connection error: {str(e)}")
            
    async def test_tasks_crud(self):
        """2) Tasks CRUD (JSON storage) - Complete CRUD flow as specified"""
        try:
            # POST /api/tasks with exact payload from review request
            task_payload = {
                "title": "Перевозка мебели",
                "description": "Нужно перенести 3 шкафа",
                "task_type": "loading",
                "requirements": [{"worker_type": "loader", "count": 2}],
                "location": "Москва, центр",
                "metro_station": None,
                "start_datetime": "2025-03-01T09:00:00+00:00",
                "duration_hours": 6,
                "client_price": 5000,
                "worker_price": None,
                "verified_only": False,
                "additional_info": None,
                "client_id": "test-client-123"
            }
            
            # Step 1: POST create task
            async with self.session.post(f"{API_BASE_URL}/tasks", json=task_payload) as response:
                if response.status != 200:
                    return self.log_result("Tasks CRUD - Create", False, f"HTTP {response.status}")
                
                created_task = await response.json()
                task_id = created_task.get("id")
                if not task_id:
                    return self.log_result("Tasks CRUD - Create", False, "No ID in response")
                
                self.test_task_id = task_id  # Save as TID
                self.log_result("Tasks CRUD - Create", True, f"Created task ID: {task_id}")
            
            # Step 2: GET /api/tasks?client_id=test-client-123 => expect array with the created task
            async with self.session.get(f"{API_BASE_URL}/tasks?client_id=test-client-123") as response:
                if response.status != 200:
                    return self.log_result("Tasks CRUD - List by Client", False, f"HTTP {response.status}")
                
                tasks = await response.json()
                if not isinstance(tasks, list) or len(tasks) == 0:
                    return self.log_result("Tasks CRUD - List by Client", False, 
                                  f"Expected array with tasks, got: {tasks}")
                
                found_task = any(task.get("id") == self.test_task_id for task in tasks)
                if not found_task:
                    return self.log_result("Tasks CRUD - List by Client", False, 
                                  "Created task not found in client's tasks")
                
                self.log_result("Tasks CRUD - List by Client", True, 
                              f"Found {len(tasks)} tasks for client, including created task")
            
            # Step 3: GET /api/tasks/{TID} => expect 200 with same id
            async with self.session.get(f"{API_BASE_URL}/tasks/{self.test_task_id}") as response:
                if response.status != 200:
                    return self.log_result("Tasks CRUD - Get Single", False, f"HTTP {response.status}")
                
                task = await response.json()
                if task.get("id") != self.test_task_id:
                    return self.log_result("Tasks CRUD - Get Single", False, 
                                  f"ID mismatch: expected {self.test_task_id}, got {task.get('id')}")
                
                self.log_result("Tasks CRUD - Get Single", True, 
                              f"Retrieved task with correct ID: {self.test_task_id}")
            
            # Step 4: PATCH /api/tasks/{TID} body {"status":"approved"} => expect 200 and status=="approved"
            update_payload = {"status": "approved"}
            async with self.session.patch(f"{API_BASE_URL}/tasks/{self.test_task_id}", 
                                        json=update_payload) as response:
                if response.status != 200:
                    return self.log_result("Tasks CRUD - Update Status", False, f"HTTP {response.status}")
                
                updated_task = await response.json()
                if updated_task.get("status") != "approved":
                    return self.log_result("Tasks CRUD - Update Status", False, 
                                  f"Expected status 'approved', got: {updated_task.get('status')}")
                
                self.log_result("Tasks CRUD - Update Status", True, 
                              f"Status updated to: {updated_task.get('status')}")
            
            # Step 5: GET /api/tasks/{TID} again => check status persisted
            async with self.session.get(f"{API_BASE_URL}/tasks/{self.test_task_id}") as response:
                if response.status != 200:
                    return self.log_result("Tasks CRUD - Verify Persistence", False, f"HTTP {response.status}")
                
                task = await response.json()
                if task.get("status") != "approved":
                    return self.log_result("Tasks CRUD - Verify Persistence", False, 
                                  f"Status not persisted: expected 'approved', got {task.get('status')}")
                
                return self.log_result("Tasks CRUD - Verify Persistence", True, 
                              f"Status persisted correctly: {task.get('status')}")
                    
        except Exception as e:
            return self.log_result("Tasks CRUD", False, f"Error: {str(e)}")
            
    async def test_html_pages(self):
        """3) HTML pages - GET /, /orders, /settings => expect 200"""
        pages = [
            ("/", "Dashboard"),
            ("/orders", "Orders Page"),
            ("/settings", "Settings Page")
        ]
        
        all_passed = True
        results = []
        
        for path, name in pages:
            try:
                async with self.session.get(f"{BASE_URL}{path}") as response:
                    if response.status == 200:
                        content = await response.text()
                        # Check for HTML content and known elements (dash heading)
                        if ("<!DOCTYPE html>" in content or "<html" in content) and len(content) > 100:
                            results.append(f"{name}: ✅")
                        else:
                            results.append(f"{name}: ❌ (Invalid HTML)")
                            all_passed = False
                    else:
                        results.append(f"{name}: ❌ (HTTP {response.status})")
                        all_passed = False
            except Exception as e:
                results.append(f"{name}: ❌ ({str(e)})")
                all_passed = False
                
        return self.log_result("HTML Pages", all_passed, "; ".join(results))
        
    async def test_storage_files(self):
        """4) Storage files - Verify files in /app/backend/data contain valid JSON"""
        data_dir = "/app/backend/data"
        required_files = ["users.json", "tasks.json", "reminders.json"]
        
        all_passed = True
        results = []
        
        for filename in required_files:
            filepath = os.path.join(data_dir, filename)
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Verify it's valid JSON and is a dict (as expected by JsonStorage)
                        if isinstance(data, dict):
                            results.append(f"{filename}: ✅ ({len(data)} entries)")
                        else:
                            results.append(f"{filename}: ❌ (Invalid structure: {type(data)})")
                            all_passed = False
                else:
                    results.append(f"{filename}: ❌ (File not found)")
                    all_passed = False
            except json.JSONDecodeError as e:
                results.append(f"{filename}: ❌ (Invalid JSON: {str(e)})")
                all_passed = False
            except Exception as e:
                results.append(f"{filename}: ❌ (Error: {str(e)})")
                all_passed = False
                
        return self.log_result("Storage Files", all_passed, "; ".join(results))
        
    async def run_sanity_tests(self):
        """Run all sanity tests as specified in review request"""
        print("🚀 Starting Backend E2E Sanity Tests")
        print("FastAPI service at http://localhost:8001")
        print("Scope: no frontend React; HTML templates in FastAPI")
        print("=" * 60)
        
        await self.setup()
        
        # Test sequence exactly as specified in review request
        tests = [
            ("1) Health", self.test_health_endpoint),
            ("2) Tasks CRUD (JSON storage)", self.test_tasks_crud),
            ("3) HTML pages", self.test_html_pages),
            ("4) Storage files", self.test_storage_files),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 Running: {test_name}")
            try:
                success = await test_func()
                if success:
                    passed += 1
            except Exception as e:
                self.log_result(test_name, False, f"Unexpected error: {str(e)}")
                
        await self.cleanup()
        
        # Print concise report
        print("\n" + "=" * 60)
        print("📊 BACKEND E2E SANITY REPORT")
        print("=" * 60)
        
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']}: {result['details']}")
            
        print(f"\n🎯 Overall: {passed}/{total} test groups passed")
        
        if passed == total:
            print("🎉 All sanity tests PASSED! Backend is working correctly.")
            return True
        else:
            print(f"⚠️  {total - passed} test groups FAILED.")
            return False

async def main():
    """Main test runner"""
    tester = BackendSanityTester()
    success = await tester.run_sanity_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())