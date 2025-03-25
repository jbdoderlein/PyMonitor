from .monitoringpy import init_monitoring, pymonitor, pymonitor_line
from .models import init_db
#from .db_operations import DatabaseManager

# Import web explorer if Flask is available
try:
    from .web_explorer import run_explorer
except ImportError:
    # Flask is not installed, provide a function that gives a helpful error
    def run_explorer(*args, **kwargs):
        print("Flask is required for the web explorer. Install it with: pip install flask flask-cors")
        print("Then you can use: python -m monitoringpy.web_explorer your_database.db")

__version__ = "0.1.0"
