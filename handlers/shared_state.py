# This file contains shared state that needs to be accessible across different handlers.
# Using a dedicated file avoids circular import issues.

# A dictionary to track pending location requests from admins to drivers.
# Key: driver_id, Value: admin_id who made the request.
location_requests = {}

# A dictionary to track active dispatch tasks for orders.
# This allows us to cancel a task if an admin intervenes.
# Key: order_id, Value: asyncio.Task object
active_dispatch_tasks = {}
