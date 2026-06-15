# Test Configuration for Phamos App

## Quick Start

Run all tests with the provided script:
```bash
# From the phamos app directory
./run_tests.sh [site-name]

# Example
./run_tests.sh phamos.localhost
```

## Running Tests Locally

### Setup
Before running tests, ensure your site is properly set up:

```bash
# Install the app if not already installed
bench --site [your-site] install-app phamos

# Run migrations
bench --site [your-site] migrate
```

### Running All Tests (Recommended Approach)

Due to dependency chain issues when running all tests together, it's recommended to run specific test modules:

```bash
# Run all test modules individually
bench --site [your-site] run-tests --app phamos --module phamos.tests.test_api
bench --site [your-site] run-tests --app phamos --module phamos.okr_addon.doctype.okr.test_okr
bench --site [your-site] run-tests --app phamos --module phamos.okr_addon.doctype.kr.test_kr
bench --site [your-site] run-tests --app phamos --module phamos.okr_addon.doctype.okr_team.test_okr_team
```

### Running Specific Test Files
```bash
# Run API tests
bench --site [your-site] run-tests --app phamos --module phamos.tests.test_api

# Run OKR tests
bench --site [your-site] run-tests --app phamos --module phamos.okr_addon.doctype.okr.test_okr

# Run OKR Team tests
bench --site [your-site] run-tests --app phamos --module phamos.okr_addon.doctype.okr_team.test_okr_team

# Run KR tests
bench --site [your-site] run-tests --app phamos --module phamos.okr_addon.doctype.kr.test_kr
```

### Known Issues

**Running all tests together:**
```bash
# This may fail due to ERPNext dependency chain issues
bench --site [your-site] run-tests --app phamos
```

The issue occurs because Frappe's test runner tries to recursively load test records for all doctypes, including ERPNext dependencies that may reference non-existent doctypes in the test environment.

**Workaround:** Run tests module by module as shown above.

### Test Data Setup

The `before_tests` hook in `phamos/install.py` automatically creates the following master records:
- Warehouse Types (Transit, Stores, etc.)
- Opportunity Types (Sales, Support, Vertrieb)
- Customer Groups (Commercial, Government, Non Profit)
- Territories (Germany, United States, etc.)
- Activity Types (Development, Testing, etc.)
- Employment Types (Full-time, Part-time, etc.)
- Departments (Engineering, Sales, etc.) - automatically associated with a test company

**Note:** Departments require a company in ERPNext/HRMS. The setup automatically finds or creates a test company to associate with departments.

### Troubleshooting

If you encounter `LinkValidationError` for missing records:

1. Check if ERPNext/HRMS are properly installed:
   ```bash
   bench --site [your-site] list-apps
   ```

2. Run migrations:
   ```bash
   bench --site [your-site] migrate
   ```

3. Clear cache:
   ```bash
   bench --site [your-site] clear-cache
   ```

4. Check if required apps are in the correct order in `hooks.py`:
   ```python
   required_apps = ["erpnext", "hrms"]
   ```

### CI/CD Tests

The GitHub Actions workflow (`.github/workflows/test.yml`) automatically:
1. Sets up MariaDB and Redis
2. Installs Frappe Bench
3. Installs ERPNext and HRMS
4. Installs Phamos
5. Runs all tests with coverage
6. Uploads coverage reports

### Writing New Tests

When writing new tests:

1. Always call `frappe.set_user("Administrator")` in `setUp()`
2. Use `frappe.db.rollback()` in `tearDown()` to clean up
3. Create necessary master records in `setUp()` if they don't exist
4. Use `ignore_permissions=True` when creating test documents
5. Test both success and failure scenarios

Example test structure:
```python
class TestMyDoctype(FrappeTestCase):
    def setUp(self):
        """Set up test data before each test."""
        frappe.set_user("Administrator")
        # Create any necessary master records
    
    def test_something(self):
        """Test description."""
        # Your test code here
        pass
    
    def tearDown(self):
        """Clean up test data."""
        frappe.set_user("Administrator")
        frappe.db.rollback()
```
