# Generic event message
# Used for streaming blockchain events and triggers to ROS topics

# Source of the event (e.g., 'blockchain', 'robot', 'operator')
string source

# Type of event (e.g., 'intent_received', 'telemetry_update', 'error')
string type

# JSON payload containing event data
string payload_json
