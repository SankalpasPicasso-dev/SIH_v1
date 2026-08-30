import sys
sys.path.append("backend")
from app.database.seed import seed
seed(); print("Synthetic demo database is ready.")
