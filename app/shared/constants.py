"""Application-wide constants (non-configurable values only)."""

# Tax rates (can be moved to tenant config for multi-country support)
DEFAULT_TAX_RATE_PCT = 18  # GST in India

# Booking hold timeout (pending → auto-cancel if unpaid)
BOOKING_HOLD_TIMEOUT_MINUTES = 10

# Maximum date range for availability queries
MAX_AVAILABILITY_RANGE_DAYS = 14

# Cache TTLs (seconds)
CACHE_TTL_AVAILABILITY_TODAY = 30
CACHE_TTL_AVAILABILITY_WEEK = 120
CACHE_TTL_AVAILABILITY_BEYOND = 300
CACHE_TTL_STANDINGS = 60
