SUPPORTED_FLAVOR_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Octavia Amphora Driver Flavor Metadata Schema",
    "description": "This schema is used to validate new flavor profiles "
                   "submitted for use in an a10 driver flavor profile.",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "listener": {
        "type": "object",
        "properties": {
            "tcp_template": {
                "type": "string",
                "description": "TCP Template name for TCP listener"
                },
            "http_template": {
                "type": "string",
                "description": "HTTP Template name for HTTP listener"
                },
            "http_template_regex": {
                "type": "boolean",
                "description": "use http template with regex"
                }
            }
        },
    }
}
