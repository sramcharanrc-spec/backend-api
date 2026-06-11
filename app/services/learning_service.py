from sqlalchemy.orm import Session
from app.models.learning_metrics_model import LearningMetrics
import logging

logger = logging.getLogger(__name__)

class LearningService:
    def __init__(self, db: Session):
        self.db = db

    def create_metrics(self, metrics_data: dict) -> LearningMetrics:
        allowed_columns = {
            column.name
            for column in LearningMetrics.__table__.columns
        }

        clean_data = {
            key: value
            for key, value in (metrics_data or {}).items()
            if key in allowed_columns
        }

        extra_data = {
            key: value
            for key, value in (metrics_data or {}).items()
            if key not in allowed_columns
        }

        if extra_data:
            for json_field in [
                "improvement_signals",
                "correction_history",
                "confidence_trends",
                "denial_patterns",
            ]:
                if json_field in allowed_columns:
                    existing = clean_data.get(json_field)
                    if not isinstance(existing, dict):
                        existing = {"value": existing} if existing is not None else {}
                    if not isinstance(existing.get("extra_metrics"), dict):
                        existing["extra_metrics"] = {}
                    existing["extra_metrics"].update(extra_data)
                    clean_data[json_field] = existing
                    break
            else:
                logger.warning(
                    "Dropping unsupported learning metric fields: %s",
                    sorted(extra_data.keys()),
                )

        metrics = LearningMetrics(**clean_data)
        self.db.add(metrics)
        self.db.commit()
        self.db.refresh(metrics)
        return metrics

    def get_all_metrics(self):
        return self.db.query(LearningMetrics).all()

    def get_patterns(self):
        metrics = self.db.query(LearningMetrics).all()
        patterns = []
        for m in metrics:
            if m.denial_patterns:
                patterns.extend(m.denial_patterns)
        return list(set(patterns))  # unique
