from sqlalchemy.orm import Session
from app.models.feedback_model import Feedback
from typing import List

class FeedbackService:
    def __init__(self, db: Session):
        self.db = db

    def create_feedback(self, feedback_data: dict) -> Feedback:
        feedback = Feedback(**feedback_data)
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def get_feedback_by_claim(self, claim_id: str) -> List[Feedback]:
        return self.db.query(Feedback).filter(Feedback.claim_id == claim_id).all()

    def get_all_feedback(self) -> List[Feedback]:
        return self.db.query(Feedback).all()