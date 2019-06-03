from a10_config import A10Config
from a10_octavia.db import repositories
a = A10Config()
print(a.get('database_connection'))

