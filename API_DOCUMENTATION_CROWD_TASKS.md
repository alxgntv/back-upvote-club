# API Documentation: Crowd Tasks

## Overview

This document describes how to work with Crowd Tasks (comments) through the Upvote Club API. Crowd Tasks allow you to attach multiple comments to a task, each with its own verification URL, status, and confirmation flags.

**Important:** 
- Crowd Tasks are currently supported only for **Reddit** and **Quora** social networks. For other social networks, use regular Engagement tasks.
- Tasks with `PENDING_REVIEW` status are only visible to the user who assigned them (`assigned_to` field). This ensures that users can only see tasks they are actively working on.

## Endpoints

### 1. Create Task (Authenticated)
**Endpoint:** `POST /api/create-task/`  
**Authentication:** Required (JWT Token)  
**Content-Type:** `application/json`

### 2. Create Task via Public API
**Endpoint:** `POST /api/public-api/create-task/`  
**Authentication:** API Key (via `X-API-Key` header or `api_key` parameter)  
**Content-Type:** `application/json`

### 3. Get Crowd Tasks
**Endpoint:** `GET /api/crowd-tasks/`  
**Authentication:** Required (JWT Token)  
**Description:** Returns all available crowd tasks with proper filtering. Tasks with `PENDING_REVIEW` status are only visible to the user who assigned them (`assigned_to`).

### 4. Save Comment URL (Step 1)
**Endpoint:** `POST /api/crowd-tasks/<crowd_task_id>/save-comment-url/`  
**Authentication:** Required (JWT Token)  
**Description:** Saves the URL of the published comment. This is the first step in the verification process.

### 5. Verify Comment (Step 2)
**Endpoint:** `POST /api/crowd-tasks/<crowd_task_id>/verify-comment-step2/`  
**Authentication:** Required (JWT Token)  
**Description:** Verifies the comment through RapidAPI Reddit API. This is the second step in the verification process.

### 6. Confirm Comment (Step 3)
**Endpoint:** `POST /api/crowd-tasks/<crowd_task_id>/confirm-comment/`  
**Authentication:** Required (JWT Token)  
**Description:** Confirms the comment by the task creator. This is the third step in the verification process.

---

## Request Structure

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `post_url` | string | URL of the post to promote |
| `type` | string | Action type: `LIKE`, `COMMENT`, `REPOST`, `FOLLOW`, `SHARE`, etc. |
| `price` | number | Price per action (in points). **For Crowd Tasks, minimum price is 100 points** |
| `actions_required` | integer | Number of actions required. For Crowd Tasks with at least one crowd task, can be `0` (task cost will be 0) |
| `social_network_code` | string | Social network code: `REDDIT`, `QUORA` (for Crowd Tasks), `TWITTER`, `LINKEDIN`, `FACEBOOK`, etc. |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `task_type` | string | Task type: `ENGAGEMENT` (default) or `CROWD` |
| `target_user_id` | string | Target user ID (for FOLLOW tasks) |
| `bonus_actions` | integer | Number of bonus actions (auto-calculated for certain countries) |
| `is_pinned` | boolean | Whether to pin the task (default: `false`) |
| `longview` | boolean | Long view option (default: `false`) |
| `meaningful_comment` | string | Single comment text (legacy field, use `crowd_tasks_data` instead) |
| `crowd_tasks_data` | array | Array of Crowd Task objects (see below) |

### Crowd Tasks Data Structure

The `crowd_tasks_data` field accepts an array of objects with the following structure:

| Field | Type | Required | Default | Description |
|-------|------|---------|--------|-------------|
| `text` | string | ✅ Yes | - | Comment text (must be non-empty) |
| `url` | string | ❌ No | `null` | URL to verify task completion (max 1000 chars) |
| `status` | string | ❌ No | `SEARCHING` | Status: `SEARCHING`, `IN_PROGRESS`, `PENDING_REVIEW`, `COMPLETED` |
| `sent` | boolean | ❌ No | `false` | Whether this comment has been used/sent |
| `confirmed_by_parser` | boolean | ❌ No | `false` | Whether confirmed by parser |
| `parser_log` | string | ❌ No | `null` | Log message from parser verification |
| `confirmed_by_user` | boolean | ❌ No | `false` | Whether confirmed by user |
| `user_log` | string | ❌ No | `null` | Log message from user verification |

**Note:** When a crowd task is moved to `PENDING_REVIEW` status, the system automatically sets the `assigned_to` field to the user who performed the verification. This ensures that only the user who started the verification process can see tasks in `PENDING_REVIEW` status.

---

## Status Values

| Status | Description |
|--------|-------------|
| `SEARCHING` | Task is being searched/assigned |
| `IN_PROGRESS` | Task is currently in progress |
| `PENDING_REVIEW` | Task is pending review |
| `COMPLETED` | Task has been completed |

---

## Example Requests

### Example 1: Task with 0 Actions and Single Crowd Task (Reddit)

**Note:** You can create a task with 0 actions (`actions_required: 0`) if it has at least one Crowd Task. This is useful when you only need to track a comment without requiring any actions.

```json
POST /api/create-task/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
  "type": "COMMENT",
  "price": 100,
  "actions_required": 0,
  "social_network_code": "REDDIT",
  "task_type": "CROWD",
  "crowd_tasks_data": [
    {
      "text": "Great post! Thanks for sharing.",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING",
      "sent": false
    }
  ]
}
```

**Important:** 
- When `actions_required` is 0, the task cost will be 0 (no balance deduction)
- You must provide at least one Crowd Task in `crowd_tasks_data`
- This only works for `task_type: "CROWD"` with Reddit or Quora

### Example 2: Basic Task with Single Crowd Task (Reddit)

```json
POST /api/create-task/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
  "type": "COMMENT",
  "price": 100,
  "actions_required": 50,
  "social_network_code": "REDDIT",
  "task_type": "CROWD",
  "crowd_tasks_data": [
    {
      "text": "Great post! Thanks for sharing.",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING",
      "sent": false
    }
  ]
}
```

### Example 3: Task with Multiple Crowd Tasks (Reddit)

```json
POST /api/create-task/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
  "type": "COMMENT",
  "price": 100,
  "actions_required": 100,
  "social_network_code": "REDDIT",
  "task_type": "CROWD",
  "crowd_tasks_data": [
    {
      "text": "Great post! Thanks for sharing.",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING",
      "sent": false
    },
    {
      "text": "Very informative content!",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING",
      "sent": false
    },
    {
      "text": "Love this!",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING",
      "sent": false
    }
  ]
}
```

### Example 4: Task with Pre-confirmed Crowd Tasks (Reddit)

```json
POST /api/create-task/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
  "type": "COMMENT",
  "price": 100,
  "actions_required": 50,
  "social_network_code": "REDDIT",
  "task_type": "CROWD",
  "crowd_tasks_data": [
    {
      "text": "Great post!",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "COMPLETED",
      "sent": true,
      "confirmed_by_parser": true,
      "parser_log": "Verified by parser at 2025-12-26 10:00:00",
      "confirmed_by_user": true,
      "user_log": "Confirmed by user John Doe"
    }
  ]
}
```

### Example 5: Engagement Task (without Crowd Tasks)

```json
POST /api/create-task/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "post_url": "https://twitter.com/user/status/1234567890",
  "type": "LIKE",
  "price": 5,
  "actions_required": 100,
  "social_network_code": "TWITTER",
  "task_type": "ENGAGEMENT"
}
```

**Note:** Engagement tasks work for all social networks. Crowd Tasks (`task_type: "CROWD"`) are only available for **Reddit** (`REDDIT`) and **Quora** (`QUORA`). For other social networks like Twitter, LinkedIn, Facebook, etc., use `task_type: "ENGAGEMENT"` without `crowd_tasks_data`.

### Example 6: Using Public API (Reddit)

```json
POST /api/public-api/create-task/
X-API-Key: <your_api_key>
Content-Type: application/json

{
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
  "type": "COMMENT",
  "price": 100,
  "actions_required": 50,
  "social_network_code": "REDDIT",
  "task_type": "CROWD",
  "crowd_tasks_data": [
    {
      "text": "Amazing content!",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING"
    }
  ]
}
```

### Example 7: Quora Task with Crowd Tasks

```json
POST /api/create-task/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "post_url": "https://www.quora.com/What-is-the-best-way-to-learn-programming",
  "type": "COMMENT",
  "price": 100,
  "actions_required": 50,
  "social_network_code": "QUORA",
  "task_type": "CROWD",
  "crowd_tasks_data": [
    {
      "text": "Great question! I recommend starting with Python.",
      "url": "https://www.quora.com/What-is-the-best-way-to-learn-programming",
      "status": "SEARCHING",
      "sent": false
    }
  ]
}
```

---

## Response Structure

### Success Response (201 Created)

```json
{
  "id": 12345,
  "type": "COMMENT",
  "task_type": "CROWD",
  "social_network": {
    "id": 1,
    "name": "Reddit",
    "code": "REDDIT",
    "icon": "reddit-icon.png"
  },
  "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
  "price": 100,
  "original_price": 5000,
  "actions_required": 50,
  "actions_completed": 0,
  "bonus_actions": 0,
  "bonus_actions_completed": 0,
  "status": "ACTIVE",
  "creator": 1,
  "created_at": "2025-12-26T10:00:00Z",
  "is_pinned": false,
  "crowd_tasks": [
    {
      "id": 1,
      "text": "Great post! Thanks for sharing.",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "SEARCHING",
      "sent": false,
      "confirmed_by_parser": false,
      "parser_log": null,
      "confirmed_by_user": false,
      "user_log": null,
      "assigned_to_id": null,
      "assigned_to_username": null,
      "created_at": "2025-12-26T10:00:00Z",
      "updated_at": "2025-12-26T10:00:00Z"
    }
  ]
}
```

### Error Response (400 Bad Request)

```json
{
  "detail": "Missing required field: post_url"
}
```

Or for validation errors:

```json
{
  "detail": "crowd_tasks_data: Each crowd task must have \"text\" field"
}
```

---

## Validation Rules

### Price Validation

1. **Crowd Tasks:**
   - Minimum price: **100 points**
   - This applies even if `actions_required` is 0
   - If price is less than 100, you'll receive an error: `"Price for Crowd Tasks must be at least 100 points"`

2. **Engagement Tasks:**
   - No minimum price requirement
   - Price can be any positive number

### Crowd Tasks Validation

1. **`text` field:**
   - Required for each crowd task
   - Must be a non-empty string
   - Cannot be only whitespace

2. **`url` field:**
   - Optional
   - Must be a valid URL string if provided
   - Maximum length: 1000 characters

3. **`status` field:**
   - Optional (defaults to `SEARCHING`)
   - Must be one of: `SEARCHING`, `IN_PROGRESS`, `PENDING_REVIEW`, `COMPLETED`

4. **`sent` field:**
   - Optional (defaults to `false`)
   - Must be a boolean value

5. **`confirmed_by_parser` field:**
   - Optional (defaults to `false`)
   - Must be a boolean value

6. **`parser_log` field:**
   - Optional
   - Must be a string if provided

7. **`confirmed_by_user` field:**
   - Optional (defaults to `false`)
   - Must be a boolean value

8. **`user_log` field:**
   - Optional
   - Must be a string if provided

---

## Frontend Integration Examples

### JavaScript/TypeScript (Fetch API)

```typescript
interface CrowdTaskData {
  text: string;
  url?: string;
  status?: 'SEARCHING' | 'IN_PROGRESS' | 'PENDING_REVIEW' | 'COMPLETED';
  sent?: boolean;
  confirmed_by_parser?: boolean;
  parser_log?: string;
  confirmed_by_user?: boolean;
  user_log?: string;
}

interface CreateTaskRequest {
  post_url: string;
  type: string;
  price: number;
  actions_required: number;
  social_network_code: string;
  task_type?: 'ENGAGEMENT' | 'CROWD';
  crowd_tasks_data?: CrowdTaskData[];
}

async function createTaskWithCrowdTasks(
  token: string,
  taskData: CreateTaskRequest
): Promise<any> {
  const response = await fetch('/api/create-task/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(taskData)
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create task');
  }

  return await response.json();
}

// Usage - Reddit Example
const taskData: CreateTaskRequest = {
  post_url: 'https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/',
  type: 'COMMENT',
  price: 100,
  actions_required: 50,
  social_network_code: 'REDDIT',
  task_type: 'CROWD',
  crowd_tasks_data: [
    {
      text: 'Great post!',
      url: 'https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/',
      status: 'SEARCHING'
    }
  ]
};

try {
  const result = await createTaskWithCrowdTasks('your_jwt_token', taskData);
  console.log('Task created:', result);
} catch (error) {
  console.error('Error:', error);
}
```

### React Hook Example

```typescript
import { useState } from 'react';

function useCreateTask() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createTask = async (taskData: CreateTaskRequest, token: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/create-task/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(taskData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create task');
      }

      const result = await response.json();
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return { createTask, loading, error };
}

// Usage in component
function TaskCreationForm() {
  const { createTask, loading, error } = useCreateTask();
  const token = 'your_jwt_token';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const taskData: CreateTaskRequest = {
      post_url: 'https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/',
      type: 'COMMENT',
      price: 100,
      actions_required: 50,
      social_network_code: 'REDDIT',
      task_type: 'CROWD',
      crowd_tasks_data: [
        {
          text: 'Great post!',
          url: 'https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/',
          status: 'SEARCHING'
        }
      ]
    };

    try {
      const result = await createTask(taskData, token);
      console.log('Task created:', result);
    } catch (err) {
      console.error('Error creating task:', err);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form fields */}
      {error && <div className="error">{error}</div>}
      <button type="submit" disabled={loading}>
        {loading ? 'Creating...' : 'Create Task'}
      </button>
    </form>
  );
}
```

### Axios Example

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('jwt_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Create task function
async function createTaskWithCrowdTasks(taskData: CreateTaskRequest) {
  try {
    const response = await api.post('/create-task/', taskData);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.detail || 'Failed to create task');
    }
    throw error;
  }
}

// Usage - Reddit Example
const taskData: CreateTaskRequest = {
  post_url: 'https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/',
  type: 'COMMENT',
  price: 100,
  actions_required: 50,
  social_network_code: 'REDDIT',
  task_type: 'CROWD',
  crowd_tasks_data: [
    {
      text: 'Great post!',
      url: 'https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/',
      status: 'SEARCHING'
    }
  ]
};

createTaskWithCrowdTasks(taskData)
  .then(result => console.log('Task created:', result))
  .catch(error => console.error('Error:', error));
```

---

## Updating Tasks with Crowd Tasks

To update a task's crowd tasks, use the `PUT` or `PATCH` method on the task endpoint:

```json
PUT /api/tasks/{task_id}/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "crowd_tasks_data": [
    {
      "text": "Updated comment text",
      "url": "https://www.reddit.com/r/programming/comments/abc123/my_awesome_post/",
      "status": "IN_PROGRESS",
      "sent": true
    }
  ]
}
```

**Note:** When updating `crowd_tasks_data`, all existing crowd tasks will be deleted and replaced with the new ones provided in the request.

---

## Best Practices

1. **Always validate data on the frontend** before sending to the API
2. **Handle errors gracefully** - check for validation errors and display user-friendly messages
3. **Use appropriate status values** - start with `SEARCHING` and update as the task progresses
4. **Include verification URLs** - always provide `url` field for crowd tasks to enable verification
5. **Monitor task status** - regularly check task status and crowd task statuses
6. **Batch operations** - when creating multiple crowd tasks, include them all in a single request
7. **Social network compatibility** - Crowd Tasks are only supported for Reddit (`REDDIT`) and Quora (`QUORA`). For other social networks, use `task_type: "ENGAGEMENT"` without `crowd_tasks_data`

---

## Common Error Codes

| Status Code | Description |
|-------------|-------------|
| 201 | Task created successfully |
| 400 | Bad request - validation error or missing required fields |
| 401 | Unauthorized - invalid or missing authentication token |
| 403 | Forbidden - insufficient permissions |
| 500 | Internal server error |

---

---

## Getting Crowd Tasks

### Get Crowd Tasks Endpoint

**Endpoint:** `GET /api/crowd-tasks/`  
**Authentication:** Required (JWT Token)

### Description

Returns all available crowd tasks with proper filtering:
- Only active tasks (`status='ACTIVE'`)
- Only tasks of type `CROWD`
- Excludes tasks created by the current user
- Excludes tasks the user has already completed
- Tasks with `PENDING_REVIEW` status are only visible to the user who assigned them (`assigned_to` field)
- Tasks with `COMPLETED` status are excluded

**Important:** When a crowd task is moved to `PENDING_REVIEW` status (after Step 2 verification), the `assigned_to_id` and `assigned_to_username` fields are automatically set to the user who performed the verification. This ensures that only that user can see the task in `PENDING_REVIEW` status when calling `/api/crowd-tasks/`.

### Response Structure

Returns an array of Task objects with their associated `crowd_tasks`:

```json
[
  {
    "id": 12345,
    "type": "COMMENT",
    "task_type": "CROWD",
    "social_network": {
      "id": 1,
      "name": "Reddit",
      "code": "REDDIT"
    },
    "post_url": "https://www.reddit.com/r/programming/comments/abc123/my_post/",
    "price": 100,
    "actions_required": 50,
    "crowd_tasks": [
      {
        "id": 1,
        "text": "Great post!",
        "url": "https://www.reddit.com/r/programming/comments/abc123/my_post/xyz789/",
        "status": "SEARCHING",
        "assigned_to_id": null,
        "assigned_to_username": null,
        "confirmed_by_parser": false,
        "confirmed_by_user": false
      },
      {
        "id": 2,
        "text": "Another comment",
        "url": "https://www.reddit.com/r/programming/comments/abc123/my_post/xyz790/",
        "status": "PENDING_REVIEW",
        "assigned_to_id": 42,
        "assigned_to_username": "firebase_uid_12345",
        "confirmed_by_parser": true,
        "confirmed_by_user": false
      }
    ]
  }
]
```

### Example Request

```bash
GET /api/crowd-tasks/
Authorization: Bearer <your_jwt_token>
```

### Frontend Integration

```typescript
async function getCrowdTasks(token: string): Promise<TaskWithCrowdTasks[]> {
  const response = await fetch('/api/crowd-tasks/', {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error('Failed to fetch crowd tasks');
  }

  return await response.json();
}
```

---

## Comment Verification

### Overview

The comment verification system allows you to verify that a Crowd Task comment has been successfully posted on Reddit. The verification process consists of 3 separate steps, each with its own endpoint. The system uses RapidAPI Reddit API to fetch comments from a post and searches for the expected comment text.

### Verification Process Flow

1. **Step 1 - Save Comment URL**: User saves the URL of the published comment
2. **Step 2 - Verify Comment**: System verifies the comment through RapidAPI
3. **Step 3 - Confirm Comment**: Task creator confirms the comment

### Step 1: Save Comment URL

**Endpoint:** `POST /api/crowd-tasks/<crowd_task_id>/save-comment-url/`  
**Authentication:** Required (JWT Token)  
**Content-Type:** `application/json`

#### URL Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `crowd_task_id` | integer | ID of the Crowd Task (in URL path) |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `comment_url` | string | ✅ Yes | URL of the comment or post on Reddit. Must contain `reddit.com` |

#### Success Response (200 OK)

```json
{
  "success": true,
  "comment_url": "https://www.reddit.com/r/programming/comments/abc123/my_post/xyz789/",
  "step1": {
    "status": "success",
    "message": "Thank you, your link has been saved",
    "error": null
  }
}
```

#### Error Responses

**400 Bad Request - Missing comment_url:**

```json
{
  "success": false,
  "error": "comment_url is required",
  "step1": {
    "status": "error",
    "message": "Error with link saving",
    "error": "comment_url is required"
  }
}
```

**400 Bad Request - Invalid URL:**

```json
{
  "success": false,
  "error": "URL must be a Reddit URL",
  "detail": "URL must be a Reddit URL. Please provide a valid Reddit comment or post URL.",
  "step1": {
    "status": "error",
    "message": "Error with link saving",
    "error": "URL must be a Reddit URL..."
  }
}
```

**404 Not Found:**

```json
{
  "success": false,
  "error": "Crowd task not found"
}
```

### Step 2: Verify Comment

**Endpoint:** `POST /api/crowd-tasks/<crowd_task_id>/verify-comment-step2/`  
**Authentication:** Required (JWT Token)  
**Content-Type:** `application/json`

#### URL Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `crowd_task_id` | integer | ID of the Crowd Task (in URL path) |

#### Request Body

Empty object `{}` or no body. The system uses the `comment_url` saved in Step 1 and the `post_url` from the task.

#### Success Response (200 OK)

**When comment is found:**

```json
{
  "success": true,
  "verified": true,
  "log": "Comment found in post...",
  "step2": {
    "status": "success",
    "message": "Comment verified successfully by Upvote Club!",
    "error": null
  }
}
```

**When comment is not found:**

```json
{
  "success": true,
  "verified": false,
  "log": "Comment not found in post...",
  "step2": {
    "status": "error",
    "message": "Error: Comment approval failed",
    "error": "Comment not found in post..."
  }
}
```

**Note:** When verification is performed (whether successful or not), the crowd task status is set to `PENDING_REVIEW` and the `assigned_to` field is set to the current user. This ensures that only the user who performed the verification can see tasks in `PENDING_REVIEW` status.

#### Error Responses

**400 Bad Request - Comment URL not saved:**

```json
{
  "success": false,
  "error": "Comment URL not saved",
  "step2": {
    "status": "error",
    "message": "Error: Comment approval failed",
    "error": "Please save comment URL first"
  }
}
```

**404 Not Found:**

```json
{
  "success": false,
  "error": "Crowd task not found"
}
```

### Step 3: Confirm Comment

**Endpoint:** `POST /api/crowd-tasks/<crowd_task_id>/confirm-comment/`  
**Authentication:** Required (JWT Token)  
**Content-Type:** `application/json`

#### URL Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `crowd_task_id` | integer | ID of the Crowd Task (in URL path) |

#### Request Body

Empty object `{}` or no body.

#### Success Response (200 OK)

```json
{
  "success": true,
  "message": "Comment confirmed successfully",
  "step3": {
    "status": "success",
    "message": "Comment verified successfully by Customer",
    "error": null
  }
}
```

**Note:** When both `confirmed_by_parser` and `confirmed_by_user` are `true`, the crowd task status is automatically set to `COMPLETED`.

#### Error Responses

**403 Forbidden - Not task creator:**

```json
{
  "success": false,
  "error": "Only task creator can confirm comments"
}
```

**404 Not Found:**

```json
{
  "success": false,
  "error": "Crowd task not found"
}
```

### How Verification Works

The verification process consists of 3 separate steps:

1. **Step 1 - Save Comment URL**: 
   - User saves the URL of the published comment
   - The URL is validated (must contain `reddit.com`)
   - The URL is saved to `CrowdTask.url` field
   - Returns success response with `step1` status

2. **Step 2 - System Verification**: 
   - System uses the saved `comment_url` and the task's `post_url`
   - Makes a request to RapidAPI Reddit API (`/getPostComments`) to fetch all comments from the post
   - Normalizes both the expected comment text (from CrowdTask) and actual comment texts from Reddit
   - Removes HTML entities, extra spaces, and normalizes case
   - Searches recursively through the comment tree (including nested replies)
   - Uses partial matching to account for minor text variations
   - Updates CrowdTask:
     - Sets `confirmed_by_parser` based on result (`True` if found, `False` if not found)
     - Sets `status = 'PENDING_REVIEW'` (regardless of verification result)
     - Sets `assigned_to = current_user` (ensures only this user can see the task in PENDING_REVIEW)
     - Saves verification log to `parser_log`
   - Returns response with `step2` status

3. **Step 3 - Customer Approval**: 
   - Task creator (customer) confirms the comment
   - Sets `confirmed_by_user = True`
   - Saves confirmation log to `user_log`
   - If both `confirmed_by_parser` and `confirmed_by_user` are `True`, sets `status = 'COMPLETED'`
   - Returns response with `step3` status

### Example Requests

#### Example 1: Complete Verification Flow

```bash
# Step 1: Save comment URL
POST /api/crowd-tasks/123/save-comment-url/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{
  "comment_url": "https://www.reddit.com/r/programming/comments/abc123/my_post/xyz789/"
}

# Step 2: Verify comment
POST /api/crowd-tasks/123/verify-comment-step2/
Authorization: Bearer <your_jwt_token>
Content-Type: application/json

{}

# Step 3: Confirm comment (by task creator)
POST /api/crowd-tasks/123/confirm-comment/
Authorization: Bearer <task_creator_jwt_token>
Content-Type: application/json

{}
```

### Frontend Integration Examples

#### JavaScript/TypeScript (Fetch API) - Complete Flow

```typescript
interface StepResponse {
  success: boolean;
  step1?: {
    status: 'waiting' | 'success' | 'error';
    message: string;
    error: string | null;
  };
  step2?: {
    status: 'waiting' | 'success' | 'error';
    message: string;
    error: string | null;
  };
  step3?: {
    status: 'waiting' | 'success' | 'error';
    message: string;
    error: string | null;
  };
}

// Step 1: Save comment URL
async function saveCommentUrl(
  crowdTaskId: number,
  commentUrl: string,
  token: string
): Promise<StepResponse> {
  const response = await fetch(
    `/api/crowd-tasks/${crowdTaskId}/save-comment-url/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        comment_url: commentUrl
      })
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to save comment URL');
  }

  return await response.json();
}

// Step 2: Verify comment
async function verifyComment(
  crowdTaskId: number,
  token: string
): Promise<StepResponse> {
  const response = await fetch(
    `/api/crowd-tasks/${crowdTaskId}/verify-comment-step2/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({})
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to verify comment');
  }

  return await response.json();
}

// Step 3: Confirm comment (by task creator)
async function confirmComment(
  crowdTaskId: number,
  token: string
): Promise<StepResponse> {
  const response = await fetch(
    `/api/crowd-tasks/${crowdTaskId}/confirm-comment/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({})
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to confirm comment');
  }

  return await response.json();
}

// Usage - Complete flow
async function completeVerificationFlow(
  crowdTaskId: number,
  commentUrl: string,
  token: string
) {
  try {
    // Step 1: Save URL
    const step1Result = await saveCommentUrl(crowdTaskId, commentUrl, token);
    console.log('Step 1:', step1Result.step1?.status, '-', step1Result.step1?.message);
    
    if (step1Result.step1?.status === 'error') {
      throw new Error(step1Result.step1.error || 'Step 1 failed');
    }
    
    // Step 2: Verify
    const step2Result = await verifyComment(crowdTaskId, token);
    console.log('Step 2:', step2Result.step2?.status, '-', step2Result.step2?.message);
    
    if (step2Result.step2?.status === 'error') {
      console.error('Verification error:', step2Result.step2.error);
    }
    
    // Step 3: Confirm (only if you are the task creator)
    // const step3Result = await confirmComment(crowdTaskId, token);
    // console.log('Step 3:', step3Result.step3?.status, '-', step3Result.step3?.message);
    
  } catch (error) {
    console.error('Verification error:', error);
  }
}
```

#### React Hook Example

```typescript
import { useState } from 'react';

interface StepResponse {
  success: boolean;
  step1?: {
    status: 'waiting' | 'success' | 'error';
    message: string;
    error: string | null;
  };
  step2?: {
    status: 'waiting' | 'success' | 'error';
    message: string;
    error: string | null;
  };
  step3?: {
    status: 'waiting' | 'success' | 'error';
    message: string;
    error: string | null;
  };
}

function useCommentVerification() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<StepResponse | null>(null);

  const saveCommentUrl = async (crowdTaskId: number, commentUrl: string, token: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/crowd-tasks/${crowdTaskId}/save-comment-url/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ comment_url: commentUrl })
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to save comment URL');
      }

      const result = await response.json();
      setSteps(result);
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const verifyComment = async (crowdTaskId: number, token: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/crowd-tasks/${crowdTaskId}/verify-comment-step2/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({})
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to verify comment');
      }

      const result = await response.json();
      setSteps(prev => ({ ...prev, ...result }));
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const confirmComment = async (crowdTaskId: number, token: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/crowd-tasks/${crowdTaskId}/confirm-comment/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({})
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to confirm comment');
      }

      const result = await response.json();
      setSteps(prev => ({ ...prev, ...result }));
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return { saveCommentUrl, verifyComment, confirmComment, loading, error, steps };
}

// Usage in component
function CommentVerificationForm({ crowdTaskId }: { crowdTaskId: number }) {
  const { saveCommentUrl, verifyComment, loading, error, steps } = useCommentVerification();
  const [commentUrl, setCommentUrl] = useState('');
  const token = localStorage.getItem('accessToken') || '';

  const handleSaveUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      await saveCommentUrl(crowdTaskId, commentUrl, token);
    } catch (err) {
      console.error('Failed to save URL:', err);
    }
  };

  const handleVerify = async () => {
    try {
      await verifyComment(crowdTaskId, token);
    } catch (err) {
      console.error('Verification failed:', err);
    }
  };

  const getStepClassName = (status?: string) => {
    if (status === 'success') return 'success';
    if (status === 'error') return 'error';
    return 'waiting';
  };

  return (
    <div>
      <form onSubmit={handleSaveUrl}>
        <input
          type="url"
          value={commentUrl}
          onChange={(e) => setCommentUrl(e.target.value)}
          placeholder="Paste link to your comment"
          required
        />
        <button type="submit" disabled={loading || !commentUrl}>
          {loading ? 'Saving...' : 'Save URL'}
        </button>
      </form>
      
      {steps?.step1?.status === 'success' && (
        <button onClick={handleVerify} disabled={loading}>
          {loading ? 'Verifying...' : 'Verify Comment'}
        </button>
      )}
      
      {error && <div className="error">{error}</div>}
      
      {steps && (
        <div className="verification-steps">
          {steps.step1 && (
            <div className={getStepClassName(steps.step1.status)}>
              {steps.step1.message}
              {steps.step1.error && <div className="error-detail">{steps.step1.error}</div>}
            </div>
          )}
          {steps.step2 && (
            <div className={getStepClassName(steps.step2.status)}>
              {steps.step2.message}
              {steps.step2.error && <div className="error-detail">{steps.step2.error}</div>}
            </div>
          )}
          {steps.step3 && (
            <div className={getStepClassName(steps.step3.status)}>
              {steps.step3.message}
              {steps.step3.error && <div className="error-detail">{steps.step3.error}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

#### Axios Example

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Step 1: Save comment URL
async function saveCommentUrl(
  crowdTaskId: number,
  commentUrl: string
): Promise<any> {
  try {
    const response = await api.post(
      `/crowd-tasks/${crowdTaskId}/save-comment-url/`,
      { comment_url: commentUrl }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.error || 'Failed to save comment URL');
    }
    throw error;
  }
}

// Step 2: Verify comment
async function verifyComment(crowdTaskId: number): Promise<any> {
  try {
    const response = await api.post(
      `/crowd-tasks/${crowdTaskId}/verify-comment-step2/`,
      {}
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.error || 'Failed to verify comment');
    }
    throw error;
  }
}

// Step 3: Confirm comment (by task creator)
async function confirmComment(crowdTaskId: number): Promise<any> {
  try {
    const response = await api.post(
      `/crowd-tasks/${crowdTaskId}/confirm-comment/`,
      {}
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.error || 'Failed to confirm comment');
    }
    throw error;
  }
}

// Usage - Complete flow
async function completeVerificationFlow(crowdTaskId: number, commentUrl: string) {
  try {
    // Step 1: Save URL
    const step1Result = await saveCommentUrl(crowdTaskId, commentUrl);
    console.log('Step 1:', step1Result.step1?.message, `(${step1Result.step1?.status})`);
    
    // Step 2: Verify
    const step2Result = await verifyComment(crowdTaskId);
    console.log('Step 2:', step2Result.step2?.message, `(${step2Result.step2?.status})`);
    
    if (step2Result.step2?.status === 'error') {
      console.error('Verification failed:', step2Result.step2.error);
    }
    
    // Step 3: Confirm (only if you are the task creator)
    // const step3Result = await confirmComment(crowdTaskId);
    // console.log('Step 3:', step3Result.step3?.message, `(${step3Result.step3?.status})`);
    
  } catch (error) {
    console.error('Error:', error);
  }
}
```

### Important Notes

1. **PENDING_REVIEW Visibility**: When a crowd task is moved to `PENDING_REVIEW` status (after Step 2), the system automatically sets the `assigned_to` field to the user who performed the verification. This ensures that:
   - Only the user who started the verification process can see tasks in `PENDING_REVIEW` status
   - Other users won't see these tasks in the `/api/crowd-tasks/` endpoint
   - The task creator can still see all tasks they created, regardless of status

2. **Text Matching**: The system uses normalized text comparison (case-insensitive, whitespace-normalized) and supports partial matching to account for minor variations.

3. **Comment Tree**: The verification searches recursively through nested comment replies, so it will find comments at any depth.

4. **Deleted Comments**: Comments marked as `[removed]` or authored by `[deleted]` are ignored during verification.

5. **RapidAPI Limits**: The system uses RapidAPI key rotation to handle rate limits. If all keys are exhausted, verification will fail with an appropriate error message.

6. **URL Format**: The URL saved in Step 1 must contain `reddit.com`. The system uses the task's `post_url` for verification, not the saved `comment_url`.

7. **Status Flow**: 
   - `SEARCHING` → User saves URL (Step 1)
   - `PENDING_REVIEW` → System verifies (Step 2) - regardless of verification result
   - `COMPLETED` → Task creator confirms (Step 3) - only if `confirmed_by_parser = True`

### Best Practices

1. **Use separate endpoints** - Use the 3 separate endpoints (`save-comment-url`, `verify-comment-step2`, `confirm-comment`) for the verification flow
2. **Handle errors gracefully** - Check for network errors, API errors, and validation errors
3. **Show loading states** - Display a loading indicator during each step
4. **Refresh task list** - After successful verification, refresh the task list using `/api/crowd-tasks/` to show updated status
5. **User feedback** - Show clear success/failure messages to users for each step
6. **Retry logic** - Consider implementing retry logic for transient API failures
7. **Check assigned_to** - When displaying tasks, check `assigned_to_id` to understand who is working on `PENDING_REVIEW` tasks
8. **PENDING_REVIEW visibility** - Remember that tasks in `PENDING_REVIEW` status are only visible to the user who assigned them (`assigned_to`)

---

## Support

For questions or issues, please contact the Upvote Club support team or refer to the main API documentation.


