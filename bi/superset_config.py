import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=Path(os.environ.get('SUPERSET_HOME', ROOT/'.runtime/superset')).absolute()
DATA_DIR=str(STATE)
SECRET_KEY=(STATE/'secret-key').read_text().strip()
SQLALCHEMY_DATABASE_URI='sqlite:///'+str(STATE/'metadata.sqlite')
APP_NAME='Site DSS · BI'
WTF_CSRF_ENABLED=True
TALISMAN_ENABLED=False
PREVENT_UNSAFE_DB_CONNECTIONS=False
FEATURE_FLAGS={'DASHBOARD_RBAC':True}
SUPERSET_WEBSERVER_ADDRESS='127.0.0.1'
SUPERSET_WEBSERVER_PORT=8089
ALERT_REPORTS_NOTIFICATION_DRY_RUN=True
