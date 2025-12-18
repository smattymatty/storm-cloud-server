# Bulk File Operations

Perform operations on multiple files and folders in a single API request. Perfect for implementing multi-select UI patterns.

## Overview

The bulk operations endpoint (`POST /api/v1/bulk/`) allows you to:

- Delete multiple files/folders at once
- Move multiple items to a new location
- Copy multiple items with automatic collision handling

**Key Features:**
- Partial success - individual failures don't abort the entire batch
- Up to 250 files per request
- Automatic async execution for large batches (>50 items)
- Full support for recursive directory operations

## Endpoint

```
POST /api/v1/bulk/
```

**Authentication Required:** Yes (API key or session)

## Request Format

```json
{
  "operation": "delete|move|copy",
  "paths": ["file1.txt", "folder/file2.txt"],
  "options": {
    "destination": "target/path"  // Required for move/copy
  }
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `operation` | string | Yes | Operation to perform: `delete`, `move`, or `copy` |
| `paths` | array | Yes | List of file/directory paths (1-250 items) |
| `options` | object | No | Operation-specific options |
| `options.destination` | string | For move/copy | Target directory path |

### Validation Rules

- **operation**: Must be one of: `delete`, `move`, `copy`
- **paths**: 
  - Minimum 1 path, maximum 250 paths
  - All paths must be strings
  - Duplicate paths are automatically deduplicated
- **move/copy**: Require `destination` in options

## Response Format

### Synchronous Response (≤50 paths)

```json
{
  "operation": "delete",
  "total": 5,
  "succeeded": 4,
  "failed": 1,
  "results": [
    {
      "path": "file1.txt",
      "success": true
    },
    {
      "path": "missing.txt",
      "success": false,
      "error_code": "NOT_FOUND",
      "error_message": "File not found"
    },
    {
      "path": "file2.txt",
      "success": true,
      "data": {
        "new_path": "dest/file2.txt"
      }
    }
  ]
}
```

### Asynchronous Response (>50 paths)

When processing more than 50 paths, the operation runs asynchronously:

```json
{
  "async": true,
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "total": 150,
  "status_url": "/api/v1/bulk/status/550e8400-e29b-41d4-a716-446655440000/"
}
```

Use the `status_url` to check operation status:

```bash
GET /api/v1/bulk/status/{task_id}/
```

## Operations

### Delete

Remove files and directories. Directories are deleted recursively (all contents removed).

```bash
curl -X POST https://your-server.com/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "delete",
    "paths": ["old-file.txt", "temp-folder/", "archive/"]
  }'
```

**Behavior:**
- Files and directories are deleted from filesystem first, then database
- ShareLinks are automatically deleted (CASCADE)
- Missing files result in individual failures (not errors)

### Move

Move files or directories to a new location.

```bash
curl -X POST https://your-server.com/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "move",
    "paths": ["file1.txt", "file2.txt", "docs/"],
    "options": {
      "destination": "archive"
    }
  }'
```

**Behavior:**
- Preserves original filename
- Fails if file with same name exists at destination
- Updates database paths after filesystem move
- Creates destination directory if it doesn't exist

**Move to Root:**
Use empty string for destination to move to user's root directory:

```json
{
  "operation": "move",
  "paths": ["subfolder/file.txt"],
  "options": {
    "destination": ""
  }
}
```

### Copy

Duplicate files or directories to a new location.

```bash
curl -X POST https://your-server.com/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "copy",
    "paths": ["important-doc.txt", "project-folder/"],
    "options": {
      "destination": "backup"
    }
  }'
```

**Behavior:**
- Automatically handles name collisions with " (copy)" suffix
- Example: `doc.txt` → `doc (copy).txt` → `doc (copy 2).txt`
- Respects user storage quotas
- Does NOT copy ShareLinks (copies are new files)
- Creates new database records for copied items

## Error Codes

Individual file operations may fail with these error codes:

| Error Code | Description |
|------------|-------------|
| `INVALID_PATH` | Path validation failed (e.g., path traversal attempt) |
| `NOT_FOUND` | Source file doesn't exist |
| `DESTINATION_NOT_FOUND` | Target directory doesn't exist |
| `ALREADY_EXISTS` | File with same name exists at destination (move only) |
| `QUOTA_EXCEEDED` | Copy operation would exceed user's storage quota |
| `PERMISSION_DENIED` | User doesn't own the file |
| `DELETE_FAILED` | Filesystem error during delete |
| `MOVE_FAILED` | Filesystem error during move |
| `COPY_FAILED` | Filesystem error during copy |

## Examples

### Delete Multiple Files

```bash
curl -X POST https://your-server.com/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "delete",
    "paths": [
      "temp-file-1.txt",
      "temp-file-2.txt",
      "old-project/"
    ]
  }'
```

### Organize Files into Archive

```bash
curl -X POST https://your-server.com/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "move",
    "paths": [
      "2023-report.pdf",
      "2023-data.csv",
      "2023-analysis/"
    ],
    "options": {
      "destination": "archive/2023"
    }
  }'
```

### Create Backups

```bash
curl -X POST https://your-server.com/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "copy",
    "paths": [
      "important-document.txt",
      "critical-data.csv"
    ],
    "options": {
      "destination": "backups"
    }
  }'
```

## Partial Success Handling

Operations continue even if individual files fail. This allows you to safely perform bulk operations without worrying about one bad path aborting everything.

**Example Response:**

```json
{
  "operation": "delete",
  "total": 5,
  "succeeded": 3,
  "failed": 2,
  "results": [
    {"path": "file1.txt", "success": true},
    {"path": "file2.txt", "success": true},
    {"path": "missing.txt", "success": false, "error_code": "NOT_FOUND"},
    {"path": "file3.txt", "success": true},
    {"path": "forbidden.txt", "success": false, "error_code": "PERMISSION_DENIED"}
  ]
}
```

Check the `succeeded` and `failed` counts, then examine individual `results` to see which operations failed and why.

## Limits

- **Maximum paths per request:** 250
- **Async threshold:** Operations with >50 paths run asynchronously
- **Path validation:** All paths are validated to prevent directory traversal attacks
- **Quota enforcement:** Copy operations check user storage quotas per-file

## Best Practices

1. **Check Results:** Always examine the `results` array for partial failures
2. **Handle Async:** For operations >50 paths, poll the status endpoint
3. **Deduplicate:** The API automatically deduplicates paths, but avoid sending duplicates
4. **Batch Smartly:** Keep batches under 50 items for immediate response, or use async endpoint for progress tracking
5. **Error Recovery:** Failed operations include error codes and messages for user feedback

## CLI Integration

These operations map to CLI commands:

```bash
# Delete
stormcloud files rm file1.txt file2.txt folder/

# Move
stormcloud files mv file1.txt file2.txt archive/

# Copy
stormcloud files cp important.txt backup/
```

The CLI should use the bulk API for multi-file operations to provide consistent behavior and better performance.
