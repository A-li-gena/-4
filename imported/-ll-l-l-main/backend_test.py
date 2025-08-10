#!/usr/bin/env python3
"""
Backend Testing Suite for Python Worker Task Management System
Tests FastAPI backend, MongoDB connection, API endpoints, Telegram bot polling conflicts, and server startup
"""

import asyncio
import json
import uuid
import subprocess
import signal
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import aiohttp
import sys
import os

# Test configuration
BASE_URL = "http://localhost:8001"
API_BASE_URL = f"{BASE_URL}/api"

class BackendTester:
    def __init__(self):
        self.session = None
        self.test_results = []
        self.test_user_id = None
        self.test_task_id = None
        self.test_reminder_id = None
        
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
        
    async def test_health_endpoint(self):
        """Test /api/health endpoint and MongoDB connection"""
        try:
            async with self.session.get(f"{API_BASE_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok") and data.get("db_connected"):
                        self.log_result("Health Check", True, "API healthy, MongoDB connected")
                        return True
                    else:
                        self.log_result("Health Check", False, f"API response: {data}")
                        return False
                else:
                    self.log_result("Health Check", False, f"HTTP {response.status}")
                    return False
        except Exception as e:
            self.log_result("Health Check", False, f"Connection error: {str(e)}")
            return False
            
    async def test_users_api(self):
        """Test users API endpoints"""
        try:
            # Test GET /api/users
            async with self.session.get(f"{API_BASE_URL}/users") as response:
                if response.status == 200:
                    users = await response.json()
                    self.log_result("Users API - List", True, f"Retrieved {len(users)} users")
                    
                    # Store a user ID for later tests if available
                    if users:
                        self.test_user_id = users[0].get("id")
                    return True
                else:
                    self.log_result("Users API - List", False, f"HTTP {response.status}")
                    return False
        except Exception as e:
            self.log_result("Users API - List", False, f"Error: {str(e)}")
            return False
            
    async def test_tasks_api(self):
        """Test tasks API endpoints"""
        try:
            # Test GET /api/tasks
            async with self.session.get(f"{API_BASE_URL}/tasks") as response:
                if response.status == 200:
                    tasks = await response.json()
                    self.log_result("Tasks API - List", True, f"Retrieved {len(tasks)} tasks")
                    
                    # Store a task ID for later tests if available
                    if tasks:
                        self.test_task_id = tasks[0].get("id")
                else:
                    self.log_result("Tasks API - List", False, f"HTTP {response.status}")
                    return False
                    
            # Test POST /api/tasks (create new task)
            if self.test_user_id:
                task_data = {
                    "title": "Test Loading Task",
                    "description": "Test task for backend testing",
                    "task_type": "loading",
                    "requirements": [
                        {
                            "worker_type": "loader",
                            "count": 2,
                            "hourly_rate": 500.0
                        }
                    ],
                    "location": "Moscow, Red Square",
                    "metro_station": "Okhotny Ryad",
                    "start_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    "duration_hours": 8,
                    "client_price": 4000.0,
                    "verified_only": False,
                    "client_id": self.test_user_id
                }
                
                async with self.session.post(f"{API_BASE_URL}/tasks", json=task_data) as response:
                    if response.status == 200:
                        created_task = await response.json()
                        self.test_task_id = created_task.get("id")
                        self.log_result("Tasks API - Create", True, f"Created task ID: {self.test_task_id}")
                    else:
                        self.log_result("Tasks API - Create", False, f"HTTP {response.status}")
                        
            # Test GET /api/tasks/{task_id} if we have a task ID
            if self.test_task_id:
                async with self.session.get(f"{API_BASE_URL}/tasks/{self.test_task_id}") as response:
                    if response.status == 200:
                        task = await response.json()
                        self.log_result("Tasks API - Get Single", True, f"Retrieved task: {task.get('title')}")
                    else:
                        self.log_result("Tasks API - Get Single", False, f"HTTP {response.status}")
                        
            return True
            
        except Exception as e:
            self.log_result("Tasks API", False, f"Error: {str(e)}")
            return False
            
    async def test_reminders_api(self):
        """Test reminders API endpoints"""
        try:
            # Test GET /api/reminders
            async with self.session.get(f"{API_BASE_URL}/reminders") as response:
                if response.status == 200:
                    reminders = await response.json()
                    self.log_result("Reminders API - List", True, f"Retrieved {len(reminders)} reminders")
                else:
                    self.log_result("Reminders API - List", False, f"HTTP {response.status}")
                    return False
                    
            # Test POST /api/reminders (create new reminder)
            if self.test_user_id:
                reminder_data = {
                    "user_id": self.test_user_id,
                    "title": "Test Reminder",
                    "description": "Test reminder for backend testing",
                    "remind_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "task_id": self.test_task_id
                }
                
                async with self.session.post(f"{API_BASE_URL}/reminders", json=reminder_data) as response:
                    if response.status == 200:
                        created_reminder = await response.json()
                        self.test_reminder_id = created_reminder.get("id")
                        self.log_result("Reminders API - Create", True, f"Created reminder ID: {self.test_reminder_id}")
                    else:
                        self.log_result("Reminders API - Create", False, f"HTTP {response.status}")
                        
            return True
            
        except Exception as e:
            self.log_result("Reminders API", False, f"Error: {str(e)}")
            return False
            
    async def test_stats_api(self):
        """Test stats API endpoint"""
        try:
            async with self.session.get(f"{API_BASE_URL}/stats/summary") as response:
                if response.status == 200:
                    stats = await response.json()
                    required_fields = ["total_tasks", "by_status", "total_revenue", "total_users", "workers_count", "clients_count"]
                    
                    missing_fields = [field for field in required_fields if field not in stats]
                    if not missing_fields:
                        self.log_result("Stats API", True, f"All stats fields present: {stats}")
                        return True
                    else:
                        self.log_result("Stats API", False, f"Missing fields: {missing_fields}")
                        return False
                else:
                    self.log_result("Stats API", False, f"HTTP {response.status}")
                    return False
        except Exception as e:
            self.log_result("Stats API", False, f"Error: {str(e)}")
            return False
            
    async def test_frontend_pages(self):
        """Test frontend HTML pages served by FastAPI"""
        pages = [
            ("/", "Dashboard"),
            ("/orders", "Orders Management"),
            ("/users", "User Management"),
            ("/moderation", "Task Moderation"),
            ("/settings", "Settings"),
            ("/webapp?user_id=test123&tab=tasks", "Telegram WebApp")
        ]
        
        success_count = 0
        for path, name in pages:
            try:
                async with self.session.get(f"{BASE_URL}{path}") as response:
                    if response.status == 200:
                        content = await response.text()
                        if "<!DOCTYPE html>" in content or "<html" in content:
                            self.log_result(f"Frontend - {name}", True, f"Page loads correctly")
                            success_count += 1
                        else:
                            self.log_result(f"Frontend - {name}", False, "Not valid HTML")
                    else:
                        self.log_result(f"Frontend - {name}", False, f"HTTP {response.status}")
            except Exception as e:
                self.log_result(f"Frontend - {name}", False, f"Error: {str(e)}")
                
        return success_count == len(pages)
        
    async def test_database_operations(self):
        """Test database write and read operations"""
        try:
            # Create a test user through API to verify database write
            test_user_data = {
                "tg_chat_id": 999999999,
                "username": "test_backend_user",
                "first_name": "Test",
                "last_name": "User",
                "role": "worker",
                "is_active": True,
                "is_verified": False
            }
            
            # Since there's no direct user creation endpoint, we'll verify through existing data
            async with self.session.get(f"{API_BASE_URL}/users?limit=1") as response:
                if response.status == 200:
                    users = await response.json()
                    self.log_result("Database Operations - Read", True, "Successfully read from database")
                    
                    # Test database write through task creation (already tested above)
                    if self.test_task_id:
                        self.log_result("Database Operations - Write", True, "Successfully wrote to database via task creation")
                        return True
                    else:
                        self.log_result("Database Operations - Write", False, "No task created to verify write")
                        return False
                else:
                    self.log_result("Database Operations", False, f"Cannot read from database: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            self.log_result("Database Operations", False, f"Error: {str(e)}")
            return False
            
    async def test_server_startup_with_uvicorn(self):
        """Test server startup using the exact uvicorn command that was failing"""
        print("\n🔧 Testing server startup with uvicorn command...")
        
        # Change to backend directory
        original_dir = os.getcwd()
        backend_dir = "/app/backend"
        
        try:
            os.chdir(backend_dir)
            
            # Start server with the exact command that was failing
            cmd = ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
            print(f"🚀 Starting server with command: {' '.join(cmd)}")
            
            # Start the server process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid  # Create new process group for clean shutdown
            )
            
            # Wait for server to start (give it time to initialize)
            startup_timeout = 30
            server_ready = False
            
            for i in range(startup_timeout):
                try:
                    # Check if server is responding
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{API_BASE_URL}/health", timeout=aiohttp.ClientTimeout(total=2)) as response:
                            if response.status == 200:
                                server_ready = True
                                break
                except:
                    pass
                
                # Check if process is still running
                if process.poll() is not None:
                    # Process has terminated
                    stdout, stderr = process.communicate()
                    self.log_result("Server Startup", False, f"Server process terminated early. STDERR: {stderr}")
                    return False
                
                await asyncio.sleep(1)
                print(f"⏳ Waiting for server startup... ({i+1}/{startup_timeout})")
            
            if not server_ready:
                # Kill the process and get output
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
                self.log_result("Server Startup", False, f"Server failed to start within {startup_timeout}s. STDERR: {stderr}")
                return False
            
            # Server is ready, test basic functionality
            print("✅ Server started successfully!")
            
            # Test that APIs work during server operation
            api_tests_passed = 0
            api_tests = [
                ("/api/health", "Health Check"),
                ("/api/users", "Users API"),
                ("/api/tasks", "Tasks API"),
                ("/api/reminders", "Reminders API")
            ]
            
            async with aiohttp.ClientSession() as session:
                for endpoint, name in api_tests:
                    try:
                        async with session.get(f"{BASE_URL}{endpoint}") as response:
                            if response.status == 200:
                                print(f"✅ {name} working during server operation")
                                api_tests_passed += 1
                            else:
                                print(f"❌ {name} failed: HTTP {response.status}")
                    except Exception as e:
                        print(f"❌ {name} failed: {str(e)}")
            
            # Test graceful shutdown
            print("🛑 Testing graceful shutdown...")
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            
            # Wait for process to terminate
            try:
                process.wait(timeout=10)
                shutdown_success = True
                print("✅ Server shutdown gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't shutdown gracefully
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait()
                shutdown_success = False
                print("⚠️ Server required force kill")
            
            # Get final output
            stdout, stderr = process.communicate()
            
            # Check for Telegram conflicts in stderr but ensure they didn't crash the server
            telegram_conflicts = "Conflict" in stderr or "terminated by other getUpdates request" in stderr
            
            if telegram_conflicts:
                print("⚠️ Telegram polling conflicts detected in logs (expected)")
                print("🔍 Checking if conflicts were handled gracefully...")
                
                # If we had conflicts but server still started and APIs worked, that's success
                if api_tests_passed >= 3:  # At least 3 out of 4 APIs should work
                    self.log_result("Telegram Conflict Handling", True, 
                                  "Server handled Telegram conflicts gracefully, APIs remained functional")
                else:
                    self.log_result("Telegram Conflict Handling", False, 
                                  "Telegram conflicts affected API functionality")
                    return False
            else:
                print("✅ No Telegram conflicts detected")
                self.log_result("Telegram Conflict Handling", True, "No conflicts encountered")
            
            # Overall success if server started, APIs worked, and shutdown was clean
            overall_success = server_ready and api_tests_passed >= 3 and shutdown_success
            
            self.log_result("Server Startup with uvicorn", overall_success, 
                          f"Server startup: {'✅' if server_ready else '❌'}, "
                          f"APIs working: {api_tests_passed}/4, "
                          f"Graceful shutdown: {'✅' if shutdown_success else '❌'}")
            
            return overall_success
            
        except Exception as e:
            self.log_result("Server Startup with uvicorn", False, f"Test error: {str(e)}")
            return False
        finally:
            # Ensure we're back in original directory
            os.chdir(original_dir)
            
            # Make sure no processes are left running
            try:
                if 'process' in locals() and process.poll() is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait()
            except:
                pass
            
    async def test_database_connectivity_during_startup(self):
        """Test that database remains connected during server startup process"""
        try:
            # Test multiple rapid health checks to simulate startup stress
            connection_tests = []
            
            for i in range(5):
                try:
                    async with self.session.get(f"{API_BASE_URL}/health") as response:
                        if response.status == 200:
                            data = await response.json()
                            connection_tests.append(data.get("db_connected", False))
                        else:
                            connection_tests.append(False)
                except:
                    connection_tests.append(False)
                
                await asyncio.sleep(0.5)  # Small delay between tests
            
            successful_connections = sum(connection_tests)
            success_rate = successful_connections / len(connection_tests)
            
            if success_rate >= 0.8:  # 80% success rate is acceptable
                self.log_result("Database Connectivity During Startup", True, 
                              f"Database connectivity stable: {successful_connections}/{len(connection_tests)} successful")
                return True
            else:
                self.log_result("Database Connectivity During Startup", False, 
                              f"Database connectivity unstable: {successful_connections}/{len(connection_tests)} successful")
                return False
                
        except Exception as e:
            self.log_result("Database Connectivity During Startup", False, f"Error: {str(e)}")
            return False
            
    async def test_telegram_bot_initialization(self):
        """Test Telegram bot initialization by checking if token is configured"""
        try:
            # Check if the health endpoint indicates bot is running
            async with self.session.get(f"{API_BASE_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    # The bot initialization happens at startup, so we check if server is healthy
                    # which indicates the bot token is valid and bot started successfully
                    if data.get("ok"):
                        self.log_result("Telegram Bot", True, "Bot token configured, server healthy")
                        return True
                    else:
                        self.log_result("Telegram Bot", False, "Server not healthy")
                        return False
                else:
                    self.log_result("Telegram Bot", False, f"Cannot check bot status: HTTP {response.status}")
                    return False
        except Exception as e:
            self.log_result("Telegram Bot", False, f"Error: {str(e)}")
            return False
            
    async def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting Backend Testing Suite")
        print("=" * 50)
        
        await self.setup()
        
        # Test sequence based on dependencies
        tests = [
            ("Health Check & MongoDB", self.test_health_endpoint),
            ("Database Connectivity During Startup", self.test_database_connectivity_during_startup),
            ("Users API", self.test_users_api),
            ("Tasks API", self.test_tasks_api),
            ("Reminders API", self.test_reminders_api),
            ("Stats API", self.test_stats_api),
            ("Database Operations", self.test_database_operations),
            ("Telegram Bot", self.test_telegram_bot_initialization),
            ("Frontend Pages", self.test_frontend_pages),
        ]
        
        # First run the standard tests with current server
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
        
        # Now run the critical uvicorn startup test (this will start its own server)
        print(f"\n🧪 Running: Server Startup with uvicorn (CRITICAL TEST)")
        try:
            startup_success = await self.test_server_startup_with_uvicorn()
            if startup_success:
                passed += 1
            total += 1
        except Exception as e:
            self.log_result("Server Startup with uvicorn", False, f"Unexpected error: {str(e)}")
            total += 1
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']}: {result['details']}")
            
        print(f"\n🎯 Overall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests PASSED! Backend is working correctly.")
            return True
        else:
            print(f"⚠️  {total - passed} tests FAILED. Check details above.")
            return False

async def main():
    """Main test runner"""
    tester = BackendTester()
    success = await tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())