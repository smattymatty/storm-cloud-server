# Ansible Module Tests

Unit tests for custom Ansible modules.

## Running Tests

### All Tests

```bash
cd deploy/ansible/tests
python3 test_dotenv_parser.py
```

### With pytest (if installed)

```bash
python3 -m pytest deploy/ansible/tests/ -v
```

### Specific Test

```bash
cd deploy/ansible/tests
python3 test_dotenv_parser.py TestDotenvParser.test_complex_real_world_example
```

## Test Coverage

**`test_dotenv_parser.py`** - Tests for the custom `.env` file parser

- Basic key=value parsing
- Quoted values (single and double quotes)
- Multiline values
- Comments (full-line and inline)
- Special characters and edge cases
- Real-world .env file examples

19 test cases covering extended format support.

## Adding Tests

When modifying `deploy/ansible/library/read_dotenv.py`, add corresponding test cases to verify:

1. **Happy path** - Normal usage works
2. **Edge cases** - Unusual but valid input
3. **Error handling** - Invalid input fails gracefully
4. **Real-world examples** - Actual .env file formats

Example:

```python
def test_my_feature(self):
    """Test description."""
    content = "KEY=value"
    parser = DotenvParser(content)
    result = parser.parse()
    self.assertEqual(result["KEY"], "value")
```
