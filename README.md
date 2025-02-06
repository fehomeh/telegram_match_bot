DB structure:

Member record:
```json
{
  "name": "John",
  "surname": "Doe",
  "phone": "+1234567890",
  "email": "john@example.com",
  "group_id": -1001234567890,
  "telegram_id": 987654321,
  "first_name": "John",
  "last_name": "Doe",
  "created_at": "2024-01-11T10:00:00",
  "status": "active",
  "comment": "",
  "blocked_till": null
}
```

## TODOs:

- Global access:
  - split user private functions.
  - group functions - functions that can be used by anyone in the group.
  - admin functions and scopes of their usage.
- Lists:
  - Admins can list participants for a group for a date or period
  - Admins can list groups with respective settings
  - Members can see their groups and status in the group
  - Members can see matches on date or range of dates
- Administration:
  - Admins can ban and un-ban members for a period or permanently
- More validation:
  - Amount of groups
  - Amount of registered players per group
  - Amount of matches to keep in the DB
  - Bot throttling
- Exception handling:
  - Handle Telegram timeouts