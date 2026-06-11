from app.db.database import engine
from app.models.base import Base
from app.models.claim_model import Claim
from app.models.feedback_model import Feedback
from app.models.compliance_audit_model import ComplianceAudit
from app.models.learning_metrics_model import LearningMetrics
from app.models.pipeline_events_model import PipelineEvent

print("🚀 Creating tables...")
Base.metadata.create_all(bind=engine)
print("✅ Tables created")